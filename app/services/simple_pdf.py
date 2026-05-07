from __future__ import annotations

import struct
import textwrap
import zlib
from dataclasses import dataclass
from math import ceil
from pathlib import Path
from typing import Dict, Iterable, List, Sequence


DEFAULT_FONT_PATHS = [
    Path("/System/Library/Fonts/Supplemental/Arial Unicode.ttf"),
    Path("/Library/Fonts/Arial Unicode.ttf"),
    Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
    Path("/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf"),
]


@dataclass(frozen=True)
class TtfFontMetrics:
    font_bytes: bytes
    units_per_em: int
    ascent: int
    descent: int
    bbox: tuple[int, int, int, int]
    num_glyphs: int
    number_of_hmetrics: int
    cmap: Dict[int, int]
    widths: List[int]


class SimplePdfWriter:
    def __init__(self, font_path: Path | None = None) -> None:
        self.font_path = self._resolve_font_path(font_path)
        self.metrics = self._load_metrics(self.font_path)

    def build_pdf(self, title: str, lines: Sequence[str]) -> bytes:
        wrapped_lines = self._wrap_lines([title, "", *lines], width=96)
        pages = [wrapped_lines[i : i + 48] for i in range(0, len(wrapped_lines), 48)] or [[]]
        page_count = len(pages)

        required_codepoints = self._collect_codepoints([title, *lines])
        used_cids = sorted(required_codepoints)

        font_file_obj = 1
        font_descriptor_obj = 2
        cid_to_gid_obj = 3
        to_unicode_obj = 4
        cid_font_obj = 5
        type0_font_obj = 6
        first_page_content_obj = 7
        first_page_obj = first_page_content_obj + page_count
        pages_obj = first_page_obj + page_count
        catalog_obj = pages_obj + 1

        objects: List[bytes] = []
        objects.append(self._stream_object(self.metrics.font_bytes, flate=True))
        objects.append(self._font_descriptor_object(font_file_obj))
        objects.append(self._stream_object(self._build_cid_to_gid_map(used_cids), flate=True))
        objects.append(self._stream_object(self._build_to_unicode_cmap(used_cids).encode("utf-8"), flate=True))
        objects.append(self._cid_font_object(font_descriptor_obj, cid_to_gid_obj, used_cids))
        objects.append(self._type0_font_object(cid_font_obj, to_unicode_obj))

        page_obj_numbers: List[int] = []
        for page_index, page_lines in enumerate(pages):
            content_obj_num = first_page_content_obj + page_index
            page_obj_num = first_page_obj + page_index
            content_stream = self._build_content_stream(page_lines)
            objects.append(self._stream_object(content_stream, flate=True))
            objects.append(self._page_object(page_obj_num=page_obj_num, pages_obj=pages_obj, content_obj=content_obj_num, font_obj=type0_font_obj))
            page_obj_numbers.append(page_obj_num)

        objects.append(self._pages_object(page_obj_numbers))
        objects.append(self._catalog_object(pages_obj))

        return self._serialize(objects, catalog_obj)

    def _resolve_font_path(self, font_path: Path | None) -> Path:
        if font_path and font_path.exists():
            return font_path
        for candidate in DEFAULT_FONT_PATHS:
            if candidate.exists():
                return candidate
        raise FileNotFoundError("No usable Unicode TTF font found for PDF generation")

    def _load_metrics(self, font_path: Path) -> TtfFontMetrics:
        font_bytes = font_path.read_bytes()
        tables = self._parse_table_directory(font_bytes)
        head = tables["head"]
        hhea = tables["hhea"]
        maxp = tables["maxp"]
        cmap = self._parse_cmap(tables["cmap"])
        widths = self._parse_hmtx(tables["hmtx"], maxp["num_glyphs"], hhea["number_of_hmetrics"])
        return TtfFontMetrics(
            font_bytes=font_bytes,
            units_per_em=head["units_per_em"],
            ascent=hhea["ascent"],
            descent=hhea["descent"],
            bbox=head["bbox"],
            num_glyphs=maxp["num_glyphs"],
            number_of_hmetrics=hhea["number_of_hmetrics"],
            cmap=cmap,
            widths=widths,
        )

    def _parse_table_directory(self, font_bytes: bytes) -> Dict[str, Dict[str, object]]:
        num_tables = struct.unpack_from(">H", font_bytes, 4)[0]
        tables: Dict[str, Dict[str, object]] = {}
        for index in range(num_tables):
            offset = 12 + index * 16
            tag = font_bytes[offset : offset + 4].decode("latin-1")
            table_offset, table_length = struct.unpack_from(">II", font_bytes, offset + 8)
            tables[tag] = {"offset": table_offset, "length": table_length}

        def get_table(tag: str) -> bytes:
            info = tables[tag]
            start = int(info["offset"])
            length = int(info["length"])
            return font_bytes[start : start + length]

        head = get_table("head")
        tables["head"] = {
            "units_per_em": struct.unpack_from(">H", head, 18)[0],
            "bbox": struct.unpack_from(">hhhh", head, 36),
        }

        hhea = get_table("hhea")
        tables["hhea"] = {
            "ascent": struct.unpack_from(">h", hhea, 4)[0],
            "descent": struct.unpack_from(">h", hhea, 6)[0],
            "number_of_hmetrics": struct.unpack_from(">H", hhea, 34)[0],
        }

        maxp = get_table("maxp")
        tables["maxp"] = {
            "num_glyphs": struct.unpack_from(">H", maxp, 4)[0],
        }

        tables["cmap"] = get_table("cmap")
        tables["hmtx"] = get_table("hmtx")
        tables["font_bytes"] = font_bytes
        return tables

    def _parse_cmap(self, cmap_table: bytes) -> Dict[int, int]:
        num_tables = struct.unpack_from(">H", cmap_table, 2)[0]
        chosen_offset = None
        chosen_format = None
        for index in range(num_tables):
            platform_id, encoding_id, offset = struct.unpack_from(">HHI", cmap_table, 4 + index * 8)
            fmt = struct.unpack_from(">H", cmap_table, offset)[0]
            if fmt == 12:
                chosen_offset = offset
                chosen_format = 12
                break
            if fmt == 4 and chosen_offset is None:
                chosen_offset = offset
                chosen_format = 4
        if chosen_offset is None or chosen_format is None:
            return {}
        if chosen_format == 12:
            return self._parse_cmap_format_12(cmap_table, chosen_offset)
        return self._parse_cmap_format_4(cmap_table, chosen_offset)

    def _parse_cmap_format_12(self, cmap_table: bytes, offset: int) -> Dict[int, int]:
        n_groups = struct.unpack_from(">I", cmap_table, offset + 12)[0]
        mapping: Dict[int, int] = {}
        for index in range(n_groups):
            start_char, end_char, start_gid = struct.unpack_from(">III", cmap_table, offset + 16 + index * 12)
            for codepoint in range(start_char, end_char + 1):
                mapping[codepoint] = start_gid + (codepoint - start_char)
        return mapping

    def _parse_cmap_format_4(self, cmap_table: bytes, offset: int) -> Dict[int, int]:
        seg_count_x2 = struct.unpack_from(">H", cmap_table, offset + 6)[0]
        seg_count = seg_count_x2 // 2
        end_codes = struct.unpack_from(f">{seg_count}H", cmap_table, offset + 14)
        start_code_offset = offset + 16 + seg_count * 2
        start_codes = struct.unpack_from(f">{seg_count}H", cmap_table, start_code_offset)
        id_delta_offset = start_code_offset + seg_count * 2
        id_deltas = struct.unpack_from(f">{seg_count}h", cmap_table, id_delta_offset)
        id_range_offset_offset = id_delta_offset + seg_count * 2
        id_range_offsets = struct.unpack_from(f">{seg_count}H", cmap_table, id_range_offset_offset)
        glyph_array_offset = id_range_offset_offset + seg_count * 2

        mapping: Dict[int, int] = {}
        for segment_index in range(seg_count):
            start_code = start_codes[segment_index]
            end_code = end_codes[segment_index]
            delta = id_deltas[segment_index]
            range_offset = id_range_offsets[segment_index]
            for codepoint in range(start_code, end_code + 1):
                if codepoint == 0xFFFF:
                    continue
                if range_offset == 0:
                    glyph_id = (codepoint + delta) % 65536
                else:
                    index = (
                        id_range_offset_offset
                        + segment_index * 2
                        + range_offset
                        + 2 * (codepoint - start_code)
                    )
                    if index + 2 > len(cmap_table):
                        continue
                    glyph_index = struct.unpack_from(">H", cmap_table, index)[0]
                    if glyph_index == 0:
                        continue
                    glyph_id = (glyph_index + delta) % 65536
                mapping[codepoint] = glyph_id
        return mapping

    def _parse_hmtx(self, hmtx_table: bytes, num_glyphs: int, number_of_hmetrics: int) -> List[int]:
        widths: List[int] = []
        offset = 0
        last_width = 0
        for glyph_index in range(num_glyphs):
            if glyph_index < number_of_hmetrics:
                if offset + 4 > len(hmtx_table):
                    widths.append(last_width)
                    continue
                advance, _ = struct.unpack_from(">HH", hmtx_table, offset)
                offset += 4
                last_width = advance
            else:
                if offset + 2 > len(hmtx_table):
                    widths.append(last_width)
                    continue
                struct.unpack_from(">h", hmtx_table, offset)
                offset += 2
            widths.append(last_width)
        return widths

    def _collect_codepoints(self, texts: Iterable[str]) -> set[int]:
        codepoints: set[int] = set()
        for text in texts:
            for char in text:
                codepoints.add(ord(char))
        return codepoints

    def _build_cid_to_gid_map(self, used_cids: Sequence[int]) -> bytes:
        max_cid = max(used_cids) if used_cids else 0
        mapping = bytearray((max_cid + 1) * 2)
        for cid in range(max_cid + 1):
            gid = self.metrics.cmap.get(cid, 0)
            struct.pack_into(">H", mapping, cid * 2, gid)
        return bytes(mapping)

    def _build_to_unicode_cmap(self, used_cids: Sequence[int]) -> str:
        chunks = []
        mappings = [f"<{cid:04X}> <{cid:04X}>" for cid in used_cids]
        for index in range(0, len(mappings), 100):
            chunk = mappings[index : index + 100]
            if not chunk:
                continue
            chunks.append(f"{len(chunk)} beginbfchar\n" + "\n".join(chunk) + "\nendbfchar")
        body = "\n".join(chunks)
        return f""" /CIDInit /ProcSet findresource begin
12 dict begin
begincmap
/CIDSystemInfo << /Registry (Adobe) /Ordering (UCS) /Supplement 0 >> def
/CMapName /Adobe-Identity-UCS def
/CMapType 2 def
1 begincodespacerange
<0000> <FFFF>
endcodespacerange
{body}
endcmap
CMapName currentdict /CMap defineresource pop
end
end
"""

    def _build_widths_array(self, used_cids: Sequence[int]) -> str:
        parts = []
        for cid in used_cids:
            gid = self.metrics.cmap.get(cid, 0)
            width = 1000
            if 0 <= gid < len(self.metrics.widths):
                width = int(round(self.metrics.widths[gid] * 1000 / self.metrics.units_per_em))
            parts.append(f"{cid} [{width}]")
        return "[ " + " ".join(parts) + " ]"

    def _stream_object(self, stream_bytes: bytes, flate: bool = False) -> bytes:
        if flate:
            stream_bytes = zlib.compress(stream_bytes)
        dict_text = f"<< /Length {len(stream_bytes)}"
        if flate:
            dict_text += " /Filter /FlateDecode"
        dict_text += " >>"
        return dict_text.encode("utf-8") + b"\nstream\n" + stream_bytes + b"\nendstream"

    def _font_descriptor_object(self, font_file_obj: int) -> bytes:
        ascent = int(round(self.metrics.ascent * 1000 / self.metrics.units_per_em))
        descent = int(round(self.metrics.descent * 1000 / self.metrics.units_per_em))
        x_min, y_min, x_max, y_max = self.metrics.bbox
        bbox = [
            int(round(x_min * 1000 / self.metrics.units_per_em)),
            int(round(y_min * 1000 / self.metrics.units_per_em)),
            int(round(x_max * 1000 / self.metrics.units_per_em)),
            int(round(y_max * 1000 / self.metrics.units_per_em)),
        ]
        descriptor = (
            "<< /Type /FontDescriptor "
            "/FontName /ArialUnicode "
            "/Flags 32 "
            f"/FontBBox [{' '.join(str(v) for v in bbox)}] "
            f"/Ascent {ascent} /Descent {descent} "
            f"/CapHeight {ascent} "
            "/ItalicAngle 0 /StemV 80 "
            f"/FontFile2 {font_file_obj} 0 R >>"
        )
        return descriptor.encode("utf-8")

    def _cid_font_object(self, font_descriptor_obj: int, cid_to_gid_obj: int, used_cids: Sequence[int]) -> bytes:
        default_width = 1000
        widths_array = self._build_widths_array(used_cids)
        cid_font = (
            "<< /Type /Font /Subtype /CIDFontType2 "
            "/BaseFont /ArialUnicode "
            "/CIDSystemInfo << /Registry (Adobe) /Ordering (Identity) /Supplement 0 >> "
            f"/FontDescriptor {font_descriptor_obj} 0 R "
            f"/DW {default_width} "
            f"/W {widths_array} "
            f"/CIDToGIDMap {cid_to_gid_obj} 0 R >>"
        )
        return cid_font.encode("utf-8")

    def _type0_font_object(self, cid_font_obj: int, to_unicode_obj: int) -> bytes:
        type0_font = (
            "<< /Type /Font /Subtype /Type0 /BaseFont /ArialUnicode "
            "/Encoding /Identity-H "
            f"/DescendantFonts [{cid_font_obj} 0 R] "
            f"/ToUnicode {to_unicode_obj} 0 R >>"
        )
        return type0_font.encode("utf-8")

    def _wrap_lines(self, lines: Sequence[str], width: int) -> List[str]:
        wrapped: List[str] = []
        for line in lines:
            if not line:
                wrapped.append("")
                continue
            wrapped.extend(textwrap.wrap(line, width=width, break_long_words=False, drop_whitespace=False) or [""])
        return wrapped

    def _build_content_stream(self, lines: Sequence[str]) -> bytes:
        commands = [
            "BT",
            "/F1 10 Tf",
            "14 TL",
            "40 800 Td",
        ]
        first = True
        for line in lines:
            if not first:
                commands.append("T*")
            first = False
            if not line:
                continue
            commands.append(f"<{self._encode_text(line)}> Tj")
        commands.append("ET")
        return "\n".join(commands).encode("utf-8")

    def _encode_text(self, text: str) -> str:
        payload = bytearray()
        for char in text:
            payload += struct.pack(">H", ord(char))
        return payload.hex().upper()

    def _page_object(self, page_obj_num: int, pages_obj: int, content_obj: int, font_obj: int) -> bytes:
        page = (
            f"<< /Type /Page /Parent {pages_obj} 0 R "
            "/MediaBox [0 0 595 842] "
            f"/Resources << /Font << /F1 {font_obj} 0 R >> >> "
            f"/Contents {content_obj} 0 R >>"
        )
        return page.encode("utf-8")

    def _pages_object(self, page_obj_numbers: Sequence[int]) -> bytes:
        kids = " ".join(f"{page} 0 R" for page in page_obj_numbers)
        pages = f"<< /Type /Pages /Kids [{kids}] /Count {len(page_obj_numbers)} >>"
        return pages.encode("utf-8")

    def _catalog_object(self, pages_obj: int) -> bytes:
        catalog = f"<< /Type /Catalog /Pages {pages_obj} 0 R >>"
        return catalog.encode("utf-8")

    def _serialize(self, objects: List[bytes], catalog_obj: int) -> bytes:
        output = bytearray(b"%PDF-1.4\n")
        offsets = [0]
        for index, obj in enumerate(objects, start=1):
            offsets.append(len(output))
            output.extend(f"{index} 0 obj\n".encode("utf-8"))
            output.extend(obj)
            output.extend(b"\nendobj\n")
        xref_offset = len(output)
        output.extend(f"xref\n0 {len(objects) + 1}\n".encode("utf-8"))
        output.extend(b"0000000000 65535 f \n")
        for offset in offsets[1:]:
            output.extend(f"{offset:010d} 00000 n \n".encode("utf-8"))
        output.extend(
            (
                f"trailer\n<< /Size {len(objects) + 1} /Root {catalog_obj} 0 R >>\n"
                f"startxref\n{xref_offset}\n%%EOF\n"
            ).encode("utf-8")
        )
        return bytes(output)
