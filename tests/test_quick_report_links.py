from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock

from app.bot.router import MaxWebhookRouter


class _FakeReportService:
    def generate_manager_report(self, *, user_id: str, role: str, period: str):
        return SimpleNamespace(
            title="Недельный отчет",
            summary_text="Недельный отчет\nПериод: 2026-05-01 - 2026-05-05\nВсего случаев: 2",
            file_path="/tmp/report.xlsx",
            pdf_file_path="/tmp/report.pdf",
        )

    def generate_division_report(self, *, user_id: str, role: str, period: str):
        return SimpleNamespace(
            title="Отчет по подразделениям",
            summary_text="Отчет по подразделениям\nПериод: 2026-05-01 - 2026-05-31\nВсего случаев: 5",
            file_path="/tmp/division-report.xlsx",
            pdf_file_path="/tmp/division-report.pdf",
        )


class QuickReportLinkTests(unittest.TestCase):
    def test_quick_report_includes_download_url(self) -> None:
        router = MaxWebhookRouter()
        router.report_service = _FakeReportService()
        router.max_client = MagicMock()
        router.max_client.is_configured.return_value = False

        response = router._quick_report("manager", "mgr-1", "777", "reports.week")

        self.assertIn("Я уже отправил его в чат.", response.outbound.text)
        router.max_client.send_file_message.assert_not_called()

    def test_division_reports_includes_download_url(self) -> None:
        router = MaxWebhookRouter()
        router.report_service = _FakeReportService()
        router.max_client = MagicMock()
        router.max_client.is_configured.return_value = False

        response = router._division_reports("manager", "mgr-1", "777")

        self.assertIn("Отчет по подразделениям готов.", response.outbound.text)
        self.assertIn("Я уже отправил его в чат.", response.outbound.text)
        router.max_client.send_file_message.assert_not_called()

    def test_quick_report_sends_xlsx_and_pdf_files_when_max_is_configured(self) -> None:
        router = MaxWebhookRouter()
        router.report_service = _FakeReportService()
        router.max_client = MagicMock()
        router.max_client.is_configured.return_value = True
        router.max_client.send_file_message = MagicMock()

        response = router._quick_report("manager", "mgr-1", "777", "reports.week")

        self.assertIn("Я уже отправил его в чат.", response.outbound.text)
        self.assertEqual(router.max_client.send_file_message.call_count, 2)
        first_call = router.max_client.send_file_message.call_args_list[0].kwargs
        second_call = router.max_client.send_file_message.call_args_list[1].kwargs
        self.assertEqual(first_call["file_path"], "/tmp/report.xlsx")
        self.assertEqual(second_call["file_path"], "/tmp/report.pdf")

    def test_division_report_sends_xlsx_and_pdf_files_when_max_is_configured(self) -> None:
        router = MaxWebhookRouter()
        router.report_service = _FakeReportService()
        router.max_client = MagicMock()
        router.max_client.is_configured.return_value = True
        router.max_client.send_file_message = MagicMock()

        response = router._division_reports("admin", "mgr-1", "777")

        self.assertIn("Я уже отправил его в чат.", response.outbound.text)
        self.assertEqual(router.max_client.send_file_message.call_count, 2)
        first_call = router.max_client.send_file_message.call_args_list[0].kwargs
        second_call = router.max_client.send_file_message.call_args_list[1].kwargs
        self.assertEqual(first_call["file_path"], "/tmp/division-report.xlsx")
        self.assertEqual(second_call["file_path"], "/tmp/division-report.pdf")


if __name__ == "__main__":
    unittest.main()
