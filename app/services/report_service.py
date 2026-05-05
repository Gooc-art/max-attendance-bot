from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from collections import defaultdict
from pathlib import Path
from typing import List, Sequence, Tuple
from xml.sax.saxutils import escape
import zipfile

from app.config import BASE_DIR, get_settings
from app.domain.enums import AttendanceCaseStatus
from app.repositories.attendance_case_repository import AttendanceCaseRepository
from app.repositories.report_repository import ReportRepository


SAFE_USER_RE = re.compile(r"[^A-Za-z0-9._-]+")


@dataclass(frozen=True)
class ReportArtifact:
    report_id: int
    token: str
    title: str
    file_name: str
    file_path: str
    period_start: str
    period_end: str
    summary_text: str
    download_url: str


class ReportService:
    def __init__(self) -> None:
        self.case_repository = AttendanceCaseRepository()
        self.report_repository = ReportRepository()
        self.reports_dir = BASE_DIR / "data" / "reports"
        self.reports_dir.mkdir(parents=True, exist_ok=True)

    def generate_manager_report(self, *, user_id: str, role: str, period: str) -> ReportArtifact:
        rows = self.case_repository.list_for_manager_user(user_id, limit=500)
        period_start, period_end = self._resolve_period_range(period)
        filtered = self._filter_cases_by_period(rows, period_start, period_end)
        title = self._build_title(period)
        summary_rows = self._build_summary_rows(filtered, title, period_start, period_end)
        detail_rows = self._build_detail_rows(filtered)
        summary_text = self._rows_to_text(summary_rows)
        return self._create_report_artifact(
            user_id=user_id,
            role=role,
            report_type=period,
            title=title,
            summary_rows=summary_rows,
            detail_rows=detail_rows,
            summary_text=summary_text,
            filename_prefix=period,
            period_start=period_start,
            period_end=period_end,
            sheet1_name="Сводка",
        )

    def generate_division_report(self, *, user_id: str, role: str, period: str) -> ReportArtifact:
        rows = self.case_repository.list_for_manager_user(user_id, limit=500)
        period_start, period_end = self._resolve_period_range(period)
        filtered = self._filter_cases_by_period(rows, period_start, period_end)
        title = "Отчет по подразделениям"
        summary_rows, department_rows = self._build_division_summary_rows(filtered, title, period_start, period_end)
        detail_rows = self._build_detail_rows(filtered)
        summary_text = self._rows_to_text(summary_rows + [["Разрез по подразделениям", ""]])
        if department_rows:
            summary_text = summary_text + "\n" + self._rows_to_text(department_rows)
        return self._create_report_artifact(
            user_id=user_id,
            role=role,
            report_type=f"division_{period}",
            title=title,
            summary_rows=summary_rows,
            detail_rows=detail_rows,
            summary_text=summary_text,
            filename_prefix=f"division_{period}",
            period_start=period_start,
            period_end=period_end,
            sheet1_name="Подразделения",
            extra_rows=department_rows,
        )

    def get_report_path(self, token: str) -> Path | None:
        report = self.report_repository.get_by_token(token)
        if report is None:
            return None
        path = Path(report.file_path)
        if not path.exists():
            return None
        return path

    def _resolve_period_range(self, period: str) -> Tuple[date, date]:
        today = date.today()
        if period == "month":
            return today - timedelta(days=30), today
        if period == "quarter":
            return today - timedelta(days=90), today
        return today - timedelta(days=7), today

    def _event_date_in_range(self, value: str, start: date, end: date) -> bool:
        try:
            event_date = date.fromisoformat(str(value))
        except Exception:
            return True
        return start <= event_date <= end

    def _build_title(self, period: str) -> str:
        return {
            "week": "Недельный отчет",
            "month": "Месячный отчет",
            "quarter": "Квартальный отчет",
        }.get(period, "Отчет")

    def _build_file_name(self, period: str, user_id: str, token: str) -> str:
        safe_user = SAFE_USER_RE.sub("_", user_id).strip("._") or "user"
        return f"{period}_{safe_user}_{token[:8]}.xlsx"

    def _create_report_artifact(
        self,
        *,
        user_id: str,
        role: str,
        report_type: str,
        title: str,
        summary_rows: List[List[str]],
        detail_rows: List[List[str]],
        summary_text: str,
        filename_prefix: str,
        period_start: date,
        period_end: date,
        sheet1_name: str,
        extra_rows: List[List[str]] | None = None,
    ) -> ReportArtifact:
        token = uuid.uuid4().hex
        file_name = self._build_file_name(filename_prefix, user_id, token)
        file_path = self.reports_dir / file_name
        self._write_workbook(file_path, sheet1_name, summary_rows, detail_rows, extra_rows or [])
        report_id = self.report_repository.create(
            token=token,
            report_type=report_type,
            user_id=user_id,
            role=role,
            title=title,
            period_start=period_start.isoformat(),
            period_end=period_end.isoformat(),
            file_name=file_name,
            file_path=str(file_path),
            summary_text=summary_text,
        )
        return ReportArtifact(
            report_id=report_id,
            token=token,
            title=title,
            file_name=file_name,
            file_path=str(file_path),
            period_start=period_start.isoformat(),
            period_end=period_end.isoformat(),
            summary_text=summary_text,
            download_url=self._build_download_url(token),
        )

    def _filter_cases_by_period(self, rows, period_start: date, period_end: date):
        return [
            case
            for case in rows
            if self._event_date_in_range(case.event_date, period_start, period_end)
        ]

    def _build_summary_rows(self, rows, title: str, period_start: date, period_end: date) -> List[List[str]]:
        total = len(rows)
        late = sum(1 for case in rows if case.case_type == "late")
        absent = sum(1 for case in rows if case.case_type == "absent")
        pending = sum(1 for case in rows if case.status == AttendanceCaseStatus.AWAITING_MANAGER_APPROVAL.value)
        justified = sum(1 for case in rows if case.status == AttendanceCaseStatus.JUSTIFIED.value)
        return [
            ["Параметр", "Значение"],
            ["Название", title],
            ["Период с", period_start.isoformat()],
            ["Период по", period_end.isoformat()],
            ["Всего случаев", str(total)],
            ["Опоздания", str(late)],
            ["Неявки", str(absent)],
            ["На согласовании", str(pending)],
            ["Подтверждено уважительно", str(justified)],
        ]

    def _build_division_summary_rows(
        self,
        rows,
        title: str,
        period_start: date,
        period_end: date,
    ) -> Tuple[List[List[str]], List[List[str]]]:
        summary_rows = self._build_summary_rows(rows, title, period_start, period_end)
        grouped = defaultdict(list)
        for case in rows:
            grouped[case.department_name or "Не указано"].append(case)

        department_rows: List[List[str]] = [["Подразделение", "Всего", "Опоздания", "Неявки", "На согласовании", "Подтверждено уважительно"]]
        for department_name in sorted(grouped.keys()):
            department_cases = grouped[department_name]
            department_rows.append(
                [
                    department_name,
                    str(len(department_cases)),
                    str(sum(1 for case in department_cases if case.case_type == "late")),
                    str(sum(1 for case in department_cases if case.case_type == "absent")),
                    str(sum(1 for case in department_cases if case.status == AttendanceCaseStatus.AWAITING_MANAGER_APPROVAL.value)),
                    str(sum(1 for case in department_cases if case.status == AttendanceCaseStatus.JUSTIFIED.value)),
                ]
            )

        return summary_rows, department_rows

    def _build_detail_rows(self, rows) -> List[List[str]]:
        detail_rows = [
            [
                "ID",
                "Сотрудник",
                "Подразделение",
                "Руководитель",
                "Дата",
                "Тип",
                "Статус",
                "План",
                "Факт",
                "Минут",
                "Причина",
            ]
        ]
        for case in rows:
            detail_rows.append(
                [
                    str(case.id),
                    case.employee_name,
                    case.department_name,
                    case.manager_name or "",
                    case.event_date,
                    "Опоздание" if case.case_type == "late" else "Неявка",
                    case.status,
                    case.planned_start,
                    case.actual_start,
                    str(case.delay_minutes),
                    case.employee_reason,
                ]
            )
        return detail_rows

    def _rows_to_text(self, rows: Sequence[Sequence[str]]) -> str:
        return "\n".join(" | ".join(cell for cell in row) for row in rows)

    def _write_workbook(self, file_path: Path, sheet1_name: str, summary_rows: List[List[str]], detail_rows: List[List[str]], extra_rows: List[List[str]] | None = None) -> None:
        file_path.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(file_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("[Content_Types].xml", self._content_types_xml())
            archive.writestr("_rels/.rels", self._rels_xml())
            sheet_names = [sheet1_name, "Случаи"]
            if extra_rows:
                sheet_names.insert(1, "Разрез")
            archive.writestr("xl/workbook.xml", self._workbook_xml(sheet_names))
            archive.writestr("xl/_rels/workbook.xml.rels", self._workbook_rels_xml(include_extra=bool(extra_rows)))
            archive.writestr("xl/styles.xml", self._styles_xml())
            archive.writestr("xl/worksheets/sheet1.xml", self._sheet_xml(summary_rows))
            if extra_rows:
                archive.writestr("xl/worksheets/sheet2.xml", self._sheet_xml(extra_rows))
                archive.writestr("xl/worksheets/sheet3.xml", self._sheet_xml(detail_rows))
            else:
                archive.writestr("xl/worksheets/sheet2.xml", self._sheet_xml(detail_rows))

    def _content_types_xml(self) -> str:
        return """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
  <Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
  <Override PartName="/xl/worksheets/sheet2.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
  <Override PartName="/xl/worksheets/sheet3.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
  <Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>
</Types>
"""

    def _rels_xml(self) -> str:
        return """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>
</Relationships>
"""

    def _workbook_xml(self, sheet_names: List[str]) -> str:
        sheets_xml = []
        for index, sheet_name in enumerate(sheet_names, start=1):
            sheets_xml.append(
                f'<sheet name="{escape(sheet_name)}" sheetId="{index}" r:id="rId{index}"/>'
            )
        return """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <sheets>{sheets}</sheets>
</workbook>
""".format(sheets="".join(sheets_xml))

    def _workbook_rels_xml(self, include_extra: bool = False) -> str:
        relationships = [
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>',
            '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet2.xml"/>',
        ]
        if include_extra:
            relationships.append(
                '<Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet3.xml"/>'
            )
            relationships.append(
                '<Relationship Id="rId4" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>'
            )
        else:
            relationships.append(
                '<Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>'
            )
        return """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  {relationships}
</Relationships>
""".format(relationships="\n  ".join(relationships))

    def _styles_xml(self) -> str:
        return """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
  <fonts count="1"><font><sz val="11"/><name val="Calibri"/></font></fonts>
  <fills count="1"><fill><patternFill patternType="none"/></fill></fills>
  <borders count="1"><border/></borders>
  <cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>
  <cellXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/></cellXfs>
</styleSheet>
"""

    def _sheet_xml(self, rows: List[List[str]]) -> str:
        sheet_rows = []
        for row_index, row in enumerate(rows, start=1):
            cells = []
            for col_index, value in enumerate(row, start=1):
                ref = f"{self._column_letter(col_index)}{row_index}"
                cells.append(
                    f'<c r="{ref}" t="inlineStr"><is><t>{escape(str(value))}</t></is></c>'
                )
            sheet_rows.append(f"<row r=\"{row_index}\">{''.join(cells)}</row>")
        return """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
  <sheetData>{rows}</sheetData>
</worksheet>
""".format(rows="".join(sheet_rows))

    def _column_letter(self, index: int) -> str:
        result = ""
        while index:
            index, remainder = divmod(index - 1, 26)
            result = chr(65 + remainder) + result
        return result

    def _build_download_url(self, token: str) -> str:
        settings = get_settings()
        base = settings.max_bot_webhook_url.rstrip("/")
        suffix = "/api/webhooks/max"
        if base.endswith(suffix):
            base = base[: -len(suffix)]
        return f"{base}/api/reports/{token}/download"
