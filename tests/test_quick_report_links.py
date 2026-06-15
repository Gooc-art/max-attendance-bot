from __future__ import annotations

import logging
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock

from app.bot.router import MaxWebhookRouter


class _FakeReportService:
    def generate_manager_report(self, *, user_id: str, role: str, period: str, date_from: str = "", date_to: str = ""):
        return SimpleNamespace(
            title="Недельный отчет",
            summary_text="Недельный отчет\nПериод: 2026-05-01 - 2026-05-05\nВсего случаев: 2",
            file_path="/tmp/report.xlsx",
            pdf_file_path="/tmp/report.pdf",
        )

    def generate_division_report(self, *, user_id: str, role: str, period: str, date_from: str = "", date_to: str = ""):
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
        router._queue_manager_report = MagicMock()
        router.max_client = MagicMock()
        router.max_client.is_configured.return_value = False

        response = router._quick_report("manager", "mgr-1", "777", "reports.week")

        self.assertIn("формируется", response.outbound.text)
        router._queue_manager_report.assert_called_once_with(chat_id="777", user_id="mgr-1", role="manager", period="week")
        router.max_client.send_file_message.assert_not_called()

    def test_division_reports_includes_download_url(self) -> None:
        router = MaxWebhookRouter()
        router.report_service = _FakeReportService()
        router.max_client = MagicMock()
        router.max_client.is_configured.return_value = False

        response = router._division_reports("manager", "mgr-1", "777")

        self.assertIn("Введи дату начала", response.outbound.text)
        router.max_client.send_file_message.assert_not_called()

    def test_quick_report_queues_background_generation(self) -> None:
        router = MaxWebhookRouter()
        router.report_service = _FakeReportService()
        router._queue_manager_report = MagicMock()

        response = router._quick_report("manager", "mgr-1", "777", "reports.week")

        self.assertIn("формируется", response.outbound.text)
        router._queue_manager_report.assert_called_once_with(chat_id="777", user_id="mgr-1", role="manager", period="week")

    def test_division_report_queues_background_generation(self) -> None:
        router = MaxWebhookRouter()
        router.report_service = _FakeReportService()

        response = router._division_reports("admin", "mgr-1", "777")

        self.assertIn("Введи дату начала", response.outbound.text)

    def test_handle_report_period_flow_queues_custom_manager_report(self) -> None:
        router = MaxWebhookRouter()
        router._queue_manager_report = MagicMock()
        from app.domain.dialog_state import UserDialogState

        state = UserDialogState(flow="report_period", step="enter_date_from", data={"report_kind": "manager", "chat_id": "777"})
        response = router._handle_report_period_flow("manager", "mgr-1", "01.05.2026", "", state)
        self.assertIn("Дата начала: 2026-05-01", response.outbound.text)
        self.assertEqual(state.step, "enter_date_to")

        finish = router._handle_report_period_flow("manager", "mgr-1", "05.05.2026", "", state)
        self.assertIn("Отчет за период формируется", finish.outbound.text)
        router._queue_manager_report.assert_called_once_with(
            chat_id="777",
            user_id="mgr-1",
            role="manager",
            period="custom",
            date_from="2026-05-01",
            date_to="2026-05-05",
        )

    def test_handle_report_period_flow_queues_custom_division_report(self) -> None:
        router = MaxWebhookRouter()
        router._queue_division_report = MagicMock()
        from app.domain.dialog_state import UserDialogState

        state = UserDialogState(flow="report_period", step="enter_date_from", data={"report_kind": "division", "chat_id": "777"})
        router._handle_report_period_flow("admin", "mgr-1", "2026-05-01", "", state)
        finish = router._handle_report_period_flow("admin", "mgr-1", "2026-05-31", "", state)

        self.assertIn("Отчет по подразделениям за период формируется", finish.outbound.text)
        router._queue_division_report.assert_called_once_with(
            chat_id="777",
            user_id="mgr-1",
            role="admin",
            period="custom",
            date_from="2026-05-01",
            date_to="2026-05-31",
        )

    def test_send_report_files_keeps_xlsx_delivery_when_pdf_fails(self) -> None:
        router = MaxWebhookRouter()
        router.max_client = MagicMock()
        router.max_client.is_configured.return_value = True
        router.max_client.send_file_message.side_effect = [
            {"status": "ok"},
            RuntimeError("pdf failed"),
        ]
        router.logger = MagicMock(spec=logging.Logger)

        router._send_report_files("777", "888", "Недельный отчет", "/tmp/report.xlsx", "/tmp/report.pdf")

        self.assertEqual(router.max_client.send_file_message.call_count, 2)
        first_call = router.max_client.send_file_message.call_args_list[0].kwargs
        second_call = router.max_client.send_file_message.call_args_list[1].kwargs
        self.assertEqual(first_call["chat_id"], 777)
        self.assertEqual(first_call["file_path"], "/tmp/report.xlsx")
        self.assertEqual(second_call["chat_id"], 777)
        self.assertEqual(second_call["file_path"], "/tmp/report.pdf")
        router.logger.warning.assert_called_once()

    def test_send_report_files_falls_back_to_download_links_when_all_uploads_fail(self) -> None:
        router = MaxWebhookRouter()
        router.max_client = MagicMock()
        router.max_client.is_configured.return_value = True
        router.max_client.send_file_message.side_effect = RuntimeError("upload failed")
        router._send_report_message = MagicMock()
        router.logger = MagicMock(spec=logging.Logger)

        router._send_report_files(
            "777",
            "888",
            "Месячный отчет",
            "/tmp/report.xlsx",
            "/tmp/report.pdf",
            "https://example.com/report.xlsx",
            "https://example.com/report.pdf",
        )

        router._send_report_message.assert_called_once()
        args = router._send_report_message.call_args.args
        self.assertEqual(args[0], "777")
        self.assertEqual(args[1], "888")
        self.assertIn("MAX не принял вложения", args[2])
        self.assertIn("https://example.com/report.xlsx", args[2])
        self.assertIn("https://example.com/report.pdf", args[2])


if __name__ == "__main__":
    unittest.main()
