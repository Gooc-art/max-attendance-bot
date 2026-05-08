from __future__ import annotations

import tempfile
import unittest
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path
from types import SimpleNamespace

from app.services.report_service import ReportService


class _FakeVisitRepository:
    def __init__(self):
        self.list_all_called = False

    def list_for_manager_user(self, user_id: str, limit: int = 500):
        return [
            SimpleNamespace(
                id=1,
                employee_user_id="emp_1",
                employee_name="Иванов Иван Иванович",
                department_name="Отдел продаж",
                manager_name="Петров Петр Сергеевич",
                event_date="2026-05-01",
                planned_start="08:30",
                planned_end="17:15",
                first_entry_time="08:44",
                arrival_status="late",
                arrival_delta_minutes=14,
                last_exit_time="17:40",
                departure_status="late",
                departure_delta_minutes=25,
                total_passes=12,
            ),
            SimpleNamespace(
                id=2,
                employee_user_id="emp_2",
                employee_name="Смирнов Сергей Олегович",
                department_name="Отдел продаж",
                manager_name="Петров Петр Сергеевич",
                event_date="2026-05-02",
                planned_start="08:30",
                planned_end="17:15",
                first_entry_time="08:20",
                arrival_status="early",
                arrival_delta_minutes=-10,
                last_exit_time="17:15",
                departure_status="on_time",
                departure_delta_minutes=0,
                total_passes=10,
            ),
        ]

    def list_all(self, limit: int = 5000):
        self.list_all_called = True
        return self.list_for_manager_user("all", limit=limit)


class _FakeReportRepository:
    def __init__(self):
        self.created = []
        self.records = {}

    def create(self, **kwargs):
        self.created.append(kwargs)
        record = SimpleNamespace(id=len(self.created), **kwargs)
        self.records[kwargs["token"]] = record
        return record.id

    def get_by_token(self, token: str):
        return self.records.get(token)


class ReportServiceTests(unittest.TestCase):
    def test_generate_manager_report_creates_xlsx_and_download_link(self) -> None:
        service = ReportService()
        service.visit_repository = _FakeVisitRepository()
        service.report_repository = _FakeReportRepository()

        with tempfile.TemporaryDirectory() as tmpdir:
            service.reports_dir = Path(tmpdir)
            artifact = service.generate_manager_report(user_id="mgr-1", role="manager", period="week")

            self.assertTrue(Path(artifact.file_path).exists())
            self.assertTrue(Path(artifact.pdf_file_path).exists())
            self.assertIn("/api/reports/", artifact.download_url)
            self.assertIn("/api/reports/", artifact.pdf_download_url)
            self.assertTrue(artifact.download_url.endswith("/download"))
            self.assertTrue(artifact.pdf_download_url.endswith("/download/pdf"))

            with zipfile.ZipFile(artifact.file_path) as archive:
                workbook_xml = archive.read("xl/workbook.xml")
                root = ET.fromstring(workbook_xml)
                sheet_names = [
                    sheet.attrib["name"]
                    for sheet in root.findall(".//{http://schemas.openxmlformats.org/spreadsheetml/2006/main}sheet")
                ]
                self.assertIn("Сводка", sheet_names)
                self.assertIn("Случаи", sheet_names)
                summary_xml = archive.read("xl/worksheets/sheet1.xml")
                self.assertIn("Недельный отчет", summary_xml.decode("utf-8"))
                self.assertIn("Пришли раньше", summary_xml.decode("utf-8"))
                self.assertIn("Ушли позже", summary_xml.decode("utf-8"))

            pdf_bytes = Path(artifact.pdf_file_path).read_bytes()
            self.assertTrue(pdf_bytes.startswith(b"%PDF-"))

    def test_generate_division_report_creates_department_breakdown(self) -> None:
        repo = _FakeVisitRepository()
        service = ReportService()
        service.visit_repository = repo
        service.report_repository = _FakeReportRepository()

        with tempfile.TemporaryDirectory() as tmpdir:
            service.reports_dir = Path(tmpdir)
            artifact = service.generate_division_report(user_id="mgr-1", role="admin", period="month")

            self.assertTrue(Path(artifact.file_path).exists())
            self.assertTrue(Path(artifact.pdf_file_path).exists())
            self.assertIn("/api/reports/", artifact.download_url)
            self.assertIn("/api/reports/", artifact.pdf_download_url)
            self.assertIn("division_month", artifact.file_name)

            with zipfile.ZipFile(artifact.file_path) as archive:
                workbook_xml = archive.read("xl/workbook.xml")
                root = ET.fromstring(workbook_xml)
                sheet_names = [
                    sheet.attrib["name"]
                    for sheet in root.findall(".//{http://schemas.openxmlformats.org/spreadsheetml/2006/main}sheet")
                ]
                self.assertIn("Подразделения", sheet_names)
                self.assertIn("Разрез", sheet_names)
                self.assertIn("Случаи", sheet_names)
                self.assertTrue(repo.list_all_called)
                summary_xml = archive.read("xl/worksheets/sheet1.xml")
                self.assertIn("Отчет по подразделениям", summary_xml.decode("utf-8"))
                breakdown_xml = archive.read("xl/worksheets/sheet2.xml")
                self.assertIn("Отдел продаж", breakdown_xml.decode("utf-8"))
                self.assertIn("Ушли позже", breakdown_xml.decode("utf-8"))
            pdf_bytes = Path(artifact.pdf_file_path).read_bytes()
            self.assertTrue(pdf_bytes.startswith(b"%PDF-"))

    def test_get_report_path_uses_token_lookup(self) -> None:
        service = ReportService()
        repo = _FakeReportRepository()
        service.report_repository = repo

        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = Path(tmpdir) / "report.xlsx"
            file_path.write_text("test")
            pdf_path = file_path.with_suffix(".pdf")
            pdf_path.write_text("%PDF-1.4")
            repo.create(
                token="abc123",
                report_type="week",
                user_id="mgr-1",
                role="manager",
                title="Недельный отчет",
                period_start="2026-05-01",
                period_end="2026-05-05",
                file_name="report.xlsx",
                file_path=str(file_path),
                summary_text="summary",
            )

            self.assertEqual(service.get_report_path("abc123"), file_path)
            self.assertEqual(service.get_report_path("abc123", format="pdf"), pdf_path)


if __name__ == "__main__":
    unittest.main()
