from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from io import BytesIO, StringIO
from pathlib import Path
from typing import Iterable, List
from urllib.request import Request, urlopen

from app.config import BASE_DIR
from app.integrations.max.client import MaxApiClient
from app.schemas.max import MaxAttachment
from app.services.skud_import import SkudImportResult, SkudImportService


SAFE_FILENAME_RE = re.compile(r"[^A-Za-z0-9._-]+")


@dataclass
class AttachmentImportResult:
    filename: str
    status: str
    message: str
    import_result: SkudImportResult | None = None


class MaxFileImportService:
    def __init__(self) -> None:
        self.max_client = MaxApiClient.from_settings()
        self.skud_import_service = SkudImportService()
        self.upload_dir = BASE_DIR / "data" / "uploads" / "skud"
        self.upload_dir.mkdir(parents=True, exist_ok=True)

    def import_attachments(self, attachments: Iterable[MaxAttachment], created_by_user_id: str) -> List[AttachmentImportResult]:
        results: List[AttachmentImportResult] = []
        for attachment in attachments:
            if attachment.type != "file":
                continue
            results.append(self._import_file_attachment(attachment, created_by_user_id))
        return results

    def _import_file_attachment(self, attachment: MaxAttachment, created_by_user_id: str) -> AttachmentImportResult:
        if not attachment.payload or not attachment.payload.url:
            return AttachmentImportResult(
                filename=attachment.filename or "unknown",
                status="error",
                message="Во вложении нет URL для скачивания.",
            )

        filename = attachment.filename or "attachment"
        try:
            file_bytes = self._download_file(attachment.payload.url)
            saved_path = self._store_file(filename, file_bytes)
            suffix = Path(filename).suffix.lower()

            if suffix == ".csv":
                result = self.skud_import_service.import_csv(
                    filename=filename,
                    content=file_bytes,
                    created_by_user_id=created_by_user_id,
                )
                return AttachmentImportResult(
                    filename=filename,
                    status="imported",
                    message=self._format_import_message(result),
                    import_result=result,
                )

            if suffix == ".xlsx":
                csv_bytes = self._xlsx_to_csv_bytes(file_bytes)
                result = self.skud_import_service.import_csv(
                    filename=filename,
                    content=csv_bytes,
                    created_by_user_id=created_by_user_id,
                )
                return AttachmentImportResult(
                    filename=filename,
                    status="imported",
                    message=self._format_import_message(result),
                    import_result=result,
                )

            return AttachmentImportResult(
                filename=filename,
                status="unsupported",
                message="Файл `{0}` сохранен в `{1}`, но формат пока не поддержан. Поддерживаются `.csv` и `.xlsx`.".format(
                    filename,
                    saved_path.name,
                ),
            )
        except Exception as exc:
            return AttachmentImportResult(
                filename=filename,
                status="error",
                message="Не удалось обработать файл `{0}`: {1}".format(filename, exc),
            )

    def _download_file(self, url: str) -> bytes:
        headers = {"User-Agent": "attendance-bot/0.1.0"}
        request = Request(url=url, headers=headers, method="GET")
        try:
            with urlopen(request, timeout=60) as response:
                return response.read()
        except Exception:
            if self.max_client.token:
                request = Request(
                    url=url,
                    headers={
                        "User-Agent": "attendance-bot/0.1.0",
                        "Authorization": self.max_client.token,
                    },
                    method="GET",
                )
                with urlopen(request, timeout=60) as response:
                    return response.read()
            raise

    def _store_file(self, filename: str, content: bytes) -> Path:
        safe_name = SAFE_FILENAME_RE.sub("_", filename).strip("._") or "attachment"
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        target = self.upload_dir / f"{timestamp}_{safe_name}"
        target.write_bytes(content)
        return target

    def _xlsx_to_csv_bytes(self, content: bytes) -> bytes:
        from openpyxl import load_workbook

        workbook = load_workbook(filename=BytesIO(content), read_only=True, data_only=True)
        sheet = workbook.worksheets[0]
        output = StringIO()
        rows = sheet.iter_rows(values_only=True)
        for row in rows:
            values = ["" if value is None else str(value) for value in row]
            output.write(";".join(values))
            output.write("\n")
        workbook.close()
        return output.getvalue().encode("utf-8")

    @staticmethod
    def _format_import_message(result: SkudImportResult) -> str:
        return (
            "Импорт `{filename}` завершен.\n"
            "Строк обработано: {total}\n"
            "Кейсов создано: {created}\n"
            "Ошибок: {errors}"
        ).format(
            filename=result.filename,
            total=result.total_rows,
            created=result.created_cases,
            errors=result.error_rows,
        )
