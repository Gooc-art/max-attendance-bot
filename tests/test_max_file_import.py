from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.integrations.max.client import MaxApiClient
from app.schemas.max import MaxAttachment, MaxAttachmentPayload
from app.services.max_file_import import MaxFileImportService


class MaxFileImportTests(unittest.TestCase):
    def test_import_attachment_uses_message_fallback_when_url_missing(self) -> None:
        service = MaxFileImportService()
        service.max_client = MagicMock()
        service.max_client.get_message.return_value = {
            "body": {
                "attachments": [
                    {
                        "type": "file",
                        "filename": "Отчет по проходам.xlsx",
                        "payload": {"url": "https://example.com/report.xlsx", "token": "abc"},
                    }
                ]
            }
        }
        service.skud_import_service = MagicMock()
        service.skud_import_service.import_csv.return_value = SimpleNamespace(
            filename="Отчет по проходам.xlsx",
            period_start="2026-05-01",
            period_end="2026-05-01",
            unique_employees=1,
            total_rows=1,
            created_cases=1,
            error_rows=0,
            arrivals_early=1,
            arrivals_on_time=0,
            arrivals_late=0,
            departures_early=0,
            departures_on_time=1,
            departures_late=0,
            samples=[],
        )

        attachment = MaxAttachment(
            type="file",
            filename="Отчет по проходам.xlsx",
            payload=MaxAttachmentPayload(token="abc"),
        )

        with patch.object(service, "_download_file", return_value=b"content") as download_file:
            with patch.object(service, "_xlsx_to_csv_bytes", return_value=b"csv") as xlsx_to_csv:
                with patch.object(service, "_store_file") as store_file:
                    store_file.return_value = None
                    result = service._import_file_attachment(attachment, "203302812", message_id="mid-1")

        service.max_client.get_message.assert_called_once_with("mid-1")
        download_file.assert_called_once_with("https://example.com/report.xlsx")
        xlsx_to_csv.assert_called_once_with(b"content")
        self.assertEqual(result.status, "imported")
        self.assertIn("Файл `Отчет по проходам.xlsx` обработан.", result.message)
        self.assertIn("Пришли раньше", result.message)
        self.assertIn("Ушли позже", result.message)

    def test_get_message_uses_expected_endpoint(self) -> None:
        client = MaxApiClient(
            token="token",
            secret="secret",
            base_url="https://platform-api.max.ru/",
            version="1.2.5",
        )

        response = MagicMock()
        response.__enter__.return_value = response
        response.read.return_value = b"{}"
        response.status = 200

        with patch("app.integrations.max.client.urlopen", return_value=response) as mocked:
            client.get_message("mid-123")

        request = mocked.call_args.args[0]
        self.assertIn("messages/mid-123", request.full_url)
        self.assertIn("v=1.2.5", request.full_url)

    def test_document_attachment_is_resolved_from_message(self) -> None:
        service = MaxFileImportService()
        service.max_client = MagicMock()
        service.max_client.get_message.return_value = {
            "body": {
                "attachments": [
                    {
                        "type": "document",
                        "filename": "Отчет.xlsx",
                        "payload": {"url": "https://example.com/report.xlsx", "token": "abc"},
                    }
                ]
            }
        }

        attachment = MaxAttachment(
            type="document",
            filename="Отчет.xlsx",
            payload=MaxAttachmentPayload(token="abc"),
        )

        resolved = service._resolve_attachment_from_message("mid-document", attachment)

        self.assertIsNotNone(resolved)
        self.assertEqual(resolved.payload.url, "https://example.com/report.xlsx")


if __name__ == "__main__":
    unittest.main()
