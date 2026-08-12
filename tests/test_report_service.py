from __future__ import annotations

import tempfile
import unittest
import zipfile
import xml.etree.ElementTree as ET
from datetime import date
from pathlib import Path
from types import SimpleNamespace

from app.services.report_service import ReportService


class _FakeVisitRepository:
    def __init__(self):
        self.list_all_called = False
        self.calls = []

    def list_for_manager_user(self, user_id: str, limit: int = 500, date_from: str = "", date_to: str = ""):
        self.calls.append(("manager", date_from, date_to))
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
                worked_minutes=446,
                planned_minutes=375,
                lunch_minutes=90,
                balance_minutes=71,
                late_compensated=True,
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
                worked_minutes=375,
                planned_minutes=375,
                lunch_minutes=90,
                balance_minutes=0,
                late_compensated=False,
                total_passes=10,
            ),
        ]

    def list_all(self, limit: int = 5000, date_from: str = "", date_to: str = ""):
        self.list_all_called = True
        self.calls.append(("all", date_from, date_to))
        return self.list_for_manager_user("all", limit=limit)


class _EmptyVisitRepository:
    def list_for_manager_user(self, user_id: str, limit: int = 500, date_from: str = "", date_to: str = ""):
        return []

    def list_all(self, limit: int = 5000, date_from: str = "", date_to: str = ""):
        return []


class _PeriodFilteredVisitRepository(_FakeVisitRepository):
    def list_for_manager_user(self, user_id: str, limit: int = 500, date_from: str = "", date_to: str = ""):
        self.calls.append(("manager", date_from, date_to))
        if date_from == "2026-05-01" and date_to == "2026-05-02":
            return super().list_for_manager_user(user_id, limit=limit, date_from=date_from, date_to=date_to)
        return []

    def list_all(self, limit: int = 5000, date_from: str = "", date_to: str = ""):
        self.list_all_called = True
        self.calls.append(("all", date_from, date_to))
        return self.list_for_manager_user("all", limit=limit, date_from=date_from, date_to=date_to)


class _FakeCaseRepository:
    def __init__(self):
        self.list_all_called = False
        self.list_for_manager_called = False
        self.calls = []

    def list_for_manager_user(self, user_id: str, limit: int = 500, date_from: str = "", date_to: str = ""):
        self.list_for_manager_called = True
        self.calls.append(("manager", date_from, date_to))
        return [
            SimpleNamespace(
                id=1,
                employee_user_id="emp_1",
                employee_name="Иванов Иван Иванович",
                department_name="Отдел продаж",
                manager_user_id="mgr-1",
                manager_name="Петров Петр Сергеевич",
                case_type="late",
                employee_reason="Был у врача",
                event_date="2026-05-01",
                source="late_notice_matched",
                planned_start="08:30",
                actual_start="08:44",
                delay_minutes=14,
            ),
            SimpleNamespace(
                id=2,
                employee_user_id="emp_2",
                employee_name="Смирнов Сергей Олегович",
                department_name="Отдел продаж",
                manager_user_id="mgr-1",
                manager_name="Петров Петр Сергеевич",
                case_type="late",
                employee_reason="Согласованное опоздание",
                event_date="2026-05-02",
                source="skud_report",
                planned_start="08:30",
                actual_start="08:20",
                delay_minutes=0,
            ),
        ]

    def list_all(self, limit: int = 5000, date_from: str = "", date_to: str = ""):
        self.list_all_called = True
        self.calls.append(("all", date_from, date_to))
        return self.list_for_manager_user("all", limit=limit)


class _CaseRepositoryWithOutsidePeriod:
    def list_for_manager_user(self, user_id: str, limit: int = 500, date_from: str = "", date_to: str = ""):
        return [
            SimpleNamespace(
                id=1,
                employee_user_id="emp_1",
                employee_name="Иванов Иван Иванович",
                department_name="Отдел продаж",
                manager_user_id="mgr-1",
                manager_name="Петров Петр Сергеевич",
                case_type="late",
                employee_reason="В периоде",
                event_date="2026-05-01",
                source="manual",
                planned_start="08:30",
                actual_start="08:44",
                delay_minutes=14,
            ),
            SimpleNamespace(
                id=2,
                employee_user_id="emp_2",
                employee_name="Смирнов Сергей Олегович",
                department_name="Отдел продаж",
                manager_user_id="mgr-1",
                manager_name="Петров Петр Сергеевич",
                case_type="late",
                employee_reason="Вне периода",
                event_date="2026-06-01",
                source="manual",
                planned_start="08:30",
                actual_start="08:50",
                delay_minutes=20,
            ),
        ]

    def list_all(self, limit: int = 5000, date_from: str = "", date_to: str = ""):
        return self.list_for_manager_user("all", limit=limit)


class _EmptyCaseRepository:
    def list_for_manager_user(self, user_id: str, limit: int = 500, date_from: str = "", date_to: str = ""):
        return []

    def list_all(self, limit: int = 5000, date_from: str = "", date_to: str = ""):
        return []


class _FakeApprovalRepository:
    def __init__(self):
        self.list_all_called = False
        self.list_for_manager_called = False
        self.calls = []

    def list_for_manager_user(self, manager_user_id: str, limit: int = 500, date_from: str = "", date_to: str = ""):
        self.list_for_manager_called = True
        self.calls.append(("manager", date_from, date_to))
        cases = _FakeCaseRepository().list_for_manager_user(manager_user_id, limit=limit)
        return [
            (
                SimpleNamespace(case_id=case.id, manager_name="Петров Петр Сергеевич", status="approved", comment=""),
                case,
            )
            for case in cases
        ]

    def list_all(self, limit: int = 5000, date_from: str = "", date_to: str = ""):
        self.list_all_called = True
        self.calls.append(("all", date_from, date_to))
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

    def list_by_user_and_type(self, user_id: str, report_type: str):
        return [
            record
            for record in self.records.values()
            if record.user_id == user_id and record.report_type == report_type
        ]

    def delete_by_user_and_type(self, user_id: str, report_type: str, exclude_token: str | None = None):
        removed = []
        for token, record in list(self.records.items()):
            if record.user_id != user_id or record.report_type != report_type:
                continue
            if exclude_token is not None and token == exclude_token:
                continue
            removed.append(Path(record.file_path))
            removed.append(Path(record.file_path).with_suffix(".pdf"))
            self.records.pop(token, None)
        return removed


class _NoSuccessfulImportRepository:
    def get_latest_successful_for_user(self, user_id: str):
        return None


class _SuccessfulImportRepository:
    def get_latest_successful_for_user(self, user_id: str):
        return SimpleNamespace(period_start="2026-05-01", period_end="2026-05-02")


class _GlobalSuccessfulImportRepository:
    def get_latest_successful_for_user(self, user_id: str):
        return None

    def get_latest_successful(self):
        return SimpleNamespace(period_start="2026-05-01", period_end="2026-05-02")


class ReportServiceTests(unittest.TestCase):
    @staticmethod
    def _sheet_xml_by_name(archive: zipfile.ZipFile, sheet_name: str) -> str:
        workbook_xml = archive.read("xl/workbook.xml")
        root = ET.fromstring(workbook_xml)
        sheets = root.findall(".//{http://schemas.openxmlformats.org/spreadsheetml/2006/main}sheet")
        for index, sheet in enumerate(sheets, start=1):
            if sheet.attrib["name"] == sheet_name:
                return archive.read(f"xl/worksheets/sheet{index}.xml").decode("utf-8")
        raise AssertionError(f"sheet not found: {sheet_name}")

    def test_generate_manager_report_creates_xlsx_and_download_link(self) -> None:
        service = ReportService()
        service.visit_repository = _FakeVisitRepository()
        service.case_repository = _FakeCaseRepository()
        service.approval_repository = _FakeApprovalRepository()
        service.report_repository = _FakeReportRepository()

        with tempfile.TemporaryDirectory() as tmpdir:
            service.reports_dir = Path(tmpdir)
            artifact = service.generate_manager_report(
                user_id="mgr-1",
                role="manager",
                period="custom",
                date_from="2026-05-01",
                date_to="2026-05-02",
            )

            self.assertTrue(Path(artifact.file_path).exists())
            self.assertTrue(Path(artifact.pdf_file_path).exists())
            self.assertIn("/api/reports/", artifact.download_url)
            self.assertIn("/api/reports/", artifact.pdf_download_url)
            self.assertTrue(artifact.download_url.endswith("/download"))
            self.assertTrue(artifact.pdf_download_url.endswith("/download/pdf"))
            self.assertIn(("manager", "2026-05-01", "2026-05-02"), service.visit_repository.calls)
            self.assertIn(("manager", "2026-05-01", "2026-05-02"), service.case_repository.calls)
            self.assertIn(("manager", "2026-05-01", "2026-05-02"), service.approval_repository.calls)

            with zipfile.ZipFile(artifact.file_path) as archive:
                workbook_xml = archive.read("xl/workbook.xml")
                root = ET.fromstring(workbook_xml)
                sheet_names = [
                    sheet.attrib["name"]
                    for sheet in root.findall(".//{http://schemas.openxmlformats.org/spreadsheetml/2006/main}sheet")
                ]
                self.assertIn("Сводка", sheet_names)
                self.assertIn("2026-05-01", sheet_names)
                self.assertIn("Случаи", sheet_names)
                summary_xml = archive.read("xl/worksheets/sheet1.xml")
                self.assertIn("Отчет за период 2026-05-01 - 2026-05-02", summary_xml.decode("utf-8"))
                self.assertIn("<autoFilter", summary_xml.decode("utf-8"))
                self.assertIn("state=\"frozen\"", summary_xml.decode("utf-8"))
                self.assertIn("Несогласовано, мин", summary_xml.decode("utf-8"))
                day_xml = self._sheet_xml_by_name(archive, "2026-05-01")
                self.assertIn("Приход", day_xml)
                self.assertIn("Согласовано, мин", day_xml)
                cases_xml = self._sheet_xml_by_name(archive, "Случаи")
                self.assertIn("Заявка/объяснение", cases_xml)

            entries = service._build_visit_entries(service.visit_repository.list_for_manager_user("mgr-1"), service.case_repository.list_for_manager_user("mgr-1"), service.approval_repository.list_for_manager_user("mgr-1"))
            summary_rows, detail_rows, _tabs = service._build_late_report_rows(entries, "Недельный отчет", date(2026, 5, 1), date(2026, 5, 2))
            pdf_lines = service._build_pdf_lines("Недельный отчет", summary_rows, detail_rows, [])
            self.assertIn("Сводка по опоздавшим", "\n".join(pdf_lines))
            self.assertIn("Иванов Иван Иванович", "\n".join(pdf_lines))
            self.assertIn("Согласование: Согласовано", "\n".join(pdf_lines))

    def test_generate_division_report_creates_department_breakdown(self) -> None:
        repo = _FakeVisitRepository()
        service = ReportService()
        service.visit_repository = repo
        service.case_repository = _FakeCaseRepository()
        service.approval_repository = _FakeApprovalRepository()
        service.report_repository = _FakeReportRepository()

        with tempfile.TemporaryDirectory() as tmpdir:
            service.reports_dir = Path(tmpdir)
            artifact = service.generate_division_report(
                user_id="mgr-1",
                role="admin",
                period="custom",
                date_from="2026-05-01",
                date_to="2026-05-02",
            )

            self.assertTrue(Path(artifact.file_path).exists())
            self.assertTrue(Path(artifact.pdf_file_path).exists())
            self.assertIn("/api/reports/", artifact.download_url)
            self.assertIn("/api/reports/", artifact.pdf_download_url)
            self.assertIn("division_custom", artifact.file_name)

            with zipfile.ZipFile(artifact.file_path) as archive:
                workbook_xml = archive.read("xl/workbook.xml")
                root = ET.fromstring(workbook_xml)
                sheet_names = [
                    sheet.attrib["name"]
                    for sheet in root.findall(".//{http://schemas.openxmlformats.org/spreadsheetml/2006/main}sheet")
                ]
                self.assertIn("Сводка", sheet_names)
                self.assertIn("2026-05-01", sheet_names)
                self.assertIn("Случаи", sheet_names)
                self.assertTrue(repo.list_all_called)
                summary_xml = archive.read("xl/worksheets/sheet1.xml")
                self.assertIn("Отчет по подразделениям", summary_xml.decode("utf-8"))
                cases_xml = self._sheet_xml_by_name(archive, "Случаи")
                self.assertIn("Заявка/объяснение", cases_xml)
                self.assertIn("Кто согласовал", cases_xml)
            entries = service._build_visit_entries(service.visit_repository.list_all(), service.case_repository.list_all(), service.approval_repository.list_all())
            summary_rows, detail_rows, _tabs = service._build_late_report_rows(entries, "Отчет по подразделениям", date(2026, 5, 1), date(2026, 5, 2))
            pdf_lines = service._build_pdf_lines("Отчет по подразделениям", summary_rows, detail_rows, [])
            self.assertIn("Сводка по опоздавшим", "\n".join(pdf_lines))
            self.assertIn("Опоздание: 14 мин", "\n".join(pdf_lines))

    def test_generate_manager_report_falls_back_to_cases_when_day_records_are_empty(self) -> None:
        service = ReportService()
        service.visit_repository = _EmptyVisitRepository()
        service.case_repository = _FakeCaseRepository()
        service.approval_repository = _FakeApprovalRepository()
        service.skud_import_repository = _NoSuccessfulImportRepository()
        service.report_repository = _FakeReportRepository()

        with tempfile.TemporaryDirectory() as tmpdir:
            service.reports_dir = Path(tmpdir)
            artifact = service.generate_manager_report(
                user_id="mgr-1",
                role="manager",
                period="custom",
                date_from="2026-05-01",
                date_to="2026-05-02",
            )

            self.assertTrue(Path(artifact.file_path).exists())
            self.assertTrue(Path(artifact.pdf_file_path).exists())
            with zipfile.ZipFile(artifact.file_path) as archive:
                workbook_xml = archive.read("xl/workbook.xml")
                root = ET.fromstring(workbook_xml)
                sheet_names = [
                    sheet.attrib["name"]
                    for sheet in root.findall(".//{http://schemas.openxmlformats.org/spreadsheetml/2006/main}sheet")
                ]
                self.assertIn("2026-05-01", sheet_names)
                self.assertIn("Случаи", sheet_names)
                summary_xml = archive.read("xl/worksheets/sheet1.xml").decode("utf-8")
                cases_xml = self._sheet_xml_by_name(archive, "Случаи")
                self.assertIn("Отчет за период 2026-05-01 - 2026-05-02", summary_xml)
                self.assertIn("Иванов Иван Иванович", cases_xml)
                self.assertIn("Заявка/объяснение", cases_xml)
                self.assertIn("Статус согласования", cases_xml)

    def test_case_only_report_filters_cases_by_selected_period(self) -> None:
        service = ReportService()
        service.visit_repository = _EmptyVisitRepository()
        service.case_repository = _CaseRepositoryWithOutsidePeriod()
        service.approval_repository = _FakeApprovalRepository()
        service.skud_import_repository = _NoSuccessfulImportRepository()
        service.report_repository = _FakeReportRepository()

        with tempfile.TemporaryDirectory() as tmpdir:
            service.reports_dir = Path(tmpdir)
            artifact = service.generate_manager_report(
                user_id="mgr-1",
                role="manager",
                period="custom",
                date_from="2026-05-01",
                date_to="2026-05-02",
            )

            with zipfile.ZipFile(artifact.file_path) as archive:
                cases_xml = self._sheet_xml_by_name(archive, "Случаи")
                self.assertIn("Иванов Иван Иванович", cases_xml)
                self.assertNotIn("Смирнов Сергей Олегович", cases_xml)

    def test_manager_without_team_uses_latest_successful_upload_period(self) -> None:
        visit_repo = _FakeVisitRepository()
        case_repo = _FakeCaseRepository()
        approval_repo = _FakeApprovalRepository()
        service = ReportService()
        service.visit_repository = _EmptyVisitRepository()
        service.case_repository = SimpleNamespace(
            list_for_manager_user=lambda user_id, limit=500, date_from="", date_to="": [],
            list_all=case_repo.list_all,
        )
        service.approval_repository = SimpleNamespace(
            list_for_manager_user=lambda user_id, limit=500, date_from="", date_to="": [],
            list_all=approval_repo.list_all,
        )
        service.skud_import_repository = _SuccessfulImportRepository()
        service.report_repository = _FakeReportRepository()
        service.visit_repository.list_all = visit_repo.list_all

        with tempfile.TemporaryDirectory() as tmpdir:
            service.reports_dir = Path(tmpdir)
            artifact = service.generate_manager_report(
                user_id="manager-with-upload",
                role="manager",
                period="week",
            )

        self.assertEqual(artifact.period_start, "2026-05-01")
        self.assertEqual(artifact.period_end, "2026-05-02")
        self.assertTrue(visit_repo.list_all_called)
        self.assertTrue(case_repo.list_all_called)
        self.assertTrue(approval_repo.list_all_called)
        self.assertIn("Иванов Иван Иванович", artifact.summary_text)
        self.assertIn("Согласовано", artifact.summary_text)

    def test_empty_quick_report_uses_latest_global_upload_period(self) -> None:
        service = ReportService()
        service.visit_repository = _PeriodFilteredVisitRepository()
        service.case_repository = _EmptyCaseRepository()
        service.approval_repository = _FakeApprovalRepository()
        service.skud_import_repository = _GlobalSuccessfulImportRepository()
        service.report_repository = _FakeReportRepository()

        with tempfile.TemporaryDirectory() as tmpdir:
            service.reports_dir = Path(tmpdir)
            artifact = service.generate_manager_report(user_id="mgr-1", role="manager", period="week")

        self.assertEqual(artifact.period_start, "2026-05-01")
        self.assertEqual(artifact.period_end, "2026-05-02")
        self.assertIn("Иванов Иван Иванович", artifact.summary_text)

    def test_generate_manager_report_uses_global_scope_for_top_manager(self) -> None:
        visit_repo = _FakeVisitRepository()
        case_repo = _FakeCaseRepository()
        approval_repo = _FakeApprovalRepository()
        service = ReportService()
        service.visit_repository = visit_repo
        service.case_repository = case_repo
        service.approval_repository = approval_repo
        service.report_repository = _FakeReportRepository()

        with tempfile.TemporaryDirectory() as tmpdir:
            service.reports_dir = Path(tmpdir)
            artifact = service.generate_manager_report(user_id="23325864", role="top_manager", period="week")

            self.assertTrue(Path(artifact.file_path).exists())
            self.assertIn("Недельный отчет", artifact.summary_text)
            self.assertTrue(visit_repo.list_all_called)
            self.assertTrue(case_repo.list_all_called)
            self.assertTrue(approval_repo.list_all_called)

    def test_visit_entries_mark_approved_substitution_without_cases(self) -> None:
        service = ReportService()
        rows = [
            SimpleNamespace(
                id=99,
                employee_user_id="mgr-1",
                employee_name="Петров Петр Сергеевич",
                department_name="Отдел продаж",
                manager_name="Сидоров Сидор Сидорович",
                event_date="2026-05-04",
                planned_start="08:30",
                planned_end="17:15",
                first_entry_time="",
                arrival_status="",
                arrival_delta_minutes=0,
                last_exit_time="",
                departure_status="",
                departure_delta_minutes=0,
                total_passes=0,
                worked_minutes=0,
                planned_minutes=375,
                lunch_minutes=0,
                balance_minutes=-375,
                late_compensated=False,
                source="approved_substitution",
            )
        ]

        entries = service._build_visit_entries(rows, [], [])

        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0].kinds_text, "Замещение")
        self.assertEqual(entries[0].reason_text, "Согласованное замещение")

    def test_visit_entries_label_short_leave_sources(self) -> None:
        service = ReportService()
        rows = [
            SimpleNamespace(
                id=100,
                employee_user_id="emp-100",
                employee_name="Иванова Ирина",
                department_name="Отдел продаж",
                manager_name="Петров Петр",
                event_date="2026-05-04",
                planned_start="08:30",
                planned_end="17:15",
                first_entry_time="08:20",
                arrival_status="on_time",
                arrival_delta_minutes=0,
                last_exit_time="17:20",
                departure_status="on_time",
                departure_delta_minutes=0,
                total_passes=6,
            )
        ]
        cases = [
            SimpleNamespace(
                id=1001,
                employee_user_id="emp-100",
                employee_name="Иванова Ирина",
                event_date="2026-05-04",
                case_type="absent",
                employee_reason="К врачу",
                source="short_leave_notice",
            ),
            SimpleNamespace(
                id=1002,
                employee_user_id="emp-100",
                employee_name="Иванова Ирина",
                event_date="2026-05-04",
                case_type="absent",
                employee_reason="Вернулась в 14:10",
                source="short_leave_notice_matched",
            ),
        ]

        entries = service._build_visit_entries(rows, cases, [])

        self.assertEqual(entries[0].kinds_text, "Отпроситься; Согласованная отлучка")
        self.assertEqual(entries[0].matched_text, "Да")

    def test_workhours_rows_include_weekly_compensation_columns(self) -> None:
        service = ReportService()
        rows = _FakeVisitRepository().list_for_manager_user("mgr-1")

        result = service._build_workhours_rows(rows)

        self.assertEqual(result[0][4], "Тип дня")
        self.assertEqual(result[0][10], "Итог недели, мин")
        self.assertEqual(result[0][11], "Опоздание недели, мин")
        self.assertEqual(result[0][12], "Компенсировано")
        self.assertEqual(result[1][0]["value"], "Нейтрально")
        self.assertEqual(result[3][0]["value"], "Переработка")
        compensated_rows = [row for row in result[1:] if isinstance(row[12], dict) and row[12]["value"] == "Да"]
        self.assertTrue(compensated_rows)
        self.assertEqual(compensated_rows[0][12]["style"], 1)
        self.assertEqual(compensated_rows[0][8]["value"], "+71")

    def test_problem_days_are_separated_from_regular_status_tabs(self) -> None:
        service = ReportService()
        rows = [
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
                worked_minutes=446,
                planned_minutes=375,
                lunch_minutes=90,
                balance_minutes=71,
                late_compensated=True,
                total_passes=12,
                source="skud_report",
            ),
            SimpleNamespace(
                id=2,
                employee_user_id="emp_2",
                employee_name="Петров Петр Сергеевич",
                department_name="Отдел продаж",
                manager_name="Сидоров Сидор Сидорович",
                event_date="2026-05-02",
                planned_start="08:30",
                planned_end="17:15",
                first_entry_time="08:31",
                arrival_status="late",
                arrival_delta_minutes=1,
                last_exit_time="",
                departure_status="",
                departure_delta_minutes=0,
                worked_minutes=0,
                planned_minutes=375,
                lunch_minutes=0,
                balance_minutes=-375,
                late_compensated=False,
                total_passes=3,
                source="skud_employee_summary",
            ),
        ]

        entries = service._build_visit_entries(rows, [], [])
        summary = service._build_visit_summary_rows(entries, "Недельный отчет", date(2026, 5, 1), date(2026, 5, 7))
        tabs = dict(service._build_visit_status_tabs(entries))

        summary_map = {row[0]: row[1] for row in summary[1:]}
        self.assertEqual(summary_map["Всего дней учета"], "2")
        self.assertEqual(summary_map["Проблемных дней"], "1")
        self.assertEqual(summary_map["Нет выхода"], "1")
        self.assertEqual(summary_map["Пришли с опозданием"], "1")
        self.assertEqual(len(tabs["Проблемные дни"]), 2)
        self.assertEqual(len(tabs["Опоздавшие"]), 2)
        self.assertEqual(tabs["Проблемные дни"][1][5], "Нет выхода")
        self.assertEqual(tabs["Опоздавшие"][1][1], "Иванов Иван Иванович")

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

    def test_new_report_removes_previous_same_type_files(self) -> None:
        service = ReportService()
        service.visit_repository = _FakeVisitRepository()
        service.case_repository = _FakeCaseRepository()
        service.approval_repository = _FakeApprovalRepository()
        service.report_repository = _FakeReportRepository()

        with tempfile.TemporaryDirectory() as tmpdir:
            service.reports_dir = Path(tmpdir)
            old_xlsx = Path(tmpdir) / "week_mgr-1_old.xlsx"
            old_pdf = old_xlsx.with_suffix(".pdf")
            old_xlsx.write_text("old")
            old_pdf.write_text("old")
            service.report_repository.records["oldtoken"] = SimpleNamespace(
                id=1,
                token="oldtoken",
                report_type="week",
                user_id="mgr-1",
                role="manager",
                title="Недельный отчет",
                period_start="2026-05-01",
                period_end="2026-05-05",
                file_name=old_xlsx.name,
                file_path=str(old_xlsx),
                summary_text="summary",
                status="ready",
            )

            artifact = service.generate_manager_report(user_id="mgr-1", role="manager", period="week")

            self.assertFalse(old_xlsx.exists())
            self.assertFalse(old_pdf.exists())
            self.assertTrue(Path(artifact.file_path).exists())
            self.assertTrue(Path(artifact.pdf_file_path).exists())
            self.assertEqual(len(service.report_repository.records), 1)


if __name__ == "__main__":
    unittest.main()
