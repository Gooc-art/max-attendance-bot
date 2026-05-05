from __future__ import annotations

import unittest
from types import SimpleNamespace

from app.bot.router import MaxWebhookRouter


class _FakeReportService:
    def generate_manager_report(self, *, user_id: str, role: str, period: str):
        return SimpleNamespace(
            summary_text="Недельный отчет\nПериод: 2026-05-01 - 2026-05-05\nВсего случаев: 2",
            download_url="https://example.com/api/reports/token/download",
        )


class QuickReportLinkTests(unittest.TestCase):
    def test_quick_report_includes_download_url(self) -> None:
        router = MaxWebhookRouter()
        router.report_service = _FakeReportService()

        response = router._quick_report("manager", "mgr-1", "reports.week")

        self.assertIn("Скачать файл:", response.outbound.text)
        self.assertIn("https://example.com/api/reports/token/download", response.outbound.text)


if __name__ == "__main__":
    unittest.main()
