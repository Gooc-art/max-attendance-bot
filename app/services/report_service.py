from __future__ import annotations

import logging
import re
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from collections import defaultdict
from pathlib import Path
import textwrap
from types import SimpleNamespace
from typing import List, Sequence, Tuple
from xml.sax.saxutils import escape
import zipfile

from app.config import BASE_DIR, get_settings
from app.repositories.approval_repository import ApprovalRepository
from app.repositories.attendance_case_repository import AttendanceCaseRepository
from app.repositories.attendance_day_record_repository import AttendanceDayRecordRepository
from app.repositories.report_repository import ReportRepository
from app.repositories.skud_import_repository import SkudImportRepository
from app.repositories.substitution_repository import SubstitutionRepository
from app.services.simple_pdf import SimplePdfWriter


SAFE_USER_RE = re.compile(r"[^A-Za-z0-9._-]+")
XLSX_STYLE_DEFAULT = 0
XLSX_STYLE_POSITIVE = 1
XLSX_STYLE_NEGATIVE = 2


@dataclass(frozen=True)
class ReportArtifact:
    report_id: int
    token: str
    title: str
    file_name: str
    file_path: str
    pdf_file_name: str
    pdf_file_path: str
    period_start: str
    period_end: str
    summary_text: str
    download_url: str
    pdf_download_url: str


@dataclass(frozen=True)
class VisitReportRow:
    record: object
    case_count: int
    kinds_text: str
    reason_text: str
    warned_text: str
    matched_text: str
    approval_status_text: str
    approver_text: str
    approval_comment_text: str


DETAIL_COL_ID = 0
DETAIL_COL_EMPLOYEE = 1
DETAIL_COL_DEPARTMENT = 2
DETAIL_COL_MANAGER = 3
DETAIL_COL_DATE = 4
DETAIL_COL_DAY_TYPE = 5
DETAIL_COL_ARRIVAL_TIME = 6
DETAIL_COL_ARRIVAL_STATUS = 7
DETAIL_COL_PLANNED_START = 8
DETAIL_COL_ARRIVAL_DELTA = 9
DETAIL_COL_DEPARTURE_TIME = 10
DETAIL_COL_DEPARTURE_STATUS = 11
DETAIL_COL_PLANNED_END = 12
DETAIL_COL_DEPARTURE_DELTA = 13
DETAIL_COL_TOTAL_PASSES = 14
DETAIL_COL_KINDS = 15
DETAIL_COL_REASON = 16
DETAIL_COL_WARNED = 17
DETAIL_COL_MATCHED = 18
DETAIL_COL_APPROVAL_STATUS = 19
DETAIL_COL_APPROVER = 20
DETAIL_COL_APPROVAL_COMMENT = 21


def _styled_cell(value: object, style: int = XLSX_STYLE_DEFAULT) -> dict[str, object]:
    return {"value": value, "style": style}


class ReportService:
    def __init__(self) -> None:
        self.logger = logging.getLogger(__name__)
        self.visit_repository = AttendanceDayRecordRepository()
        self.case_repository = AttendanceCaseRepository()
        self.approval_repository = ApprovalRepository()
        self.substitution_repository = SubstitutionRepository()
        self.skud_import_repository = SkudImportRepository()
        self.report_repository = ReportRepository()
        self.reports_dir = BASE_DIR / "data" / "reports"
        self.reports_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _case_kind_label(case) -> str:
        source = str(getattr(case, "source", "") or "").strip()
        case_type = str(getattr(case, "case_type", "") or "").strip()
        if source == "approved_substitution":
            return "Замещение"
        if source == "forgot_chip":
            return "Забыл карточку СКУД"
        if source.startswith("late_notice"):
            return "Опаздываю"
        if case_type == "late":
            return "Опоздание"
        if case_type == "absent":
            return "Неявка"
        return case_type or "Нарушение"

    def _active_curated_departments(self, user_id: str, date_from: str, date_to: str) -> List[str]:
        drafts = self.substitution_repository.list_approved_overlapping(date_from, date_to)
        departments: List[str] = []
        seen: set[str] = set()
        for draft in drafts:
            if getattr(draft, "replacement_user_id", "") != user_id:
                continue
            for department in self.substitution_repository.departments_for_draft(draft):
                if department not in seen:
                    seen.add(department)
                    departments.append(department)
        return departments

    @staticmethod
    def _merge_by_id(primary, secondary):
        merged = []
        seen: set[str] = set()
        for row in list(primary or []) + list(secondary or []):
            key = str(getattr(row, "id", "") or id(row))
            if key in seen:
                continue
            seen.add(key)
            merged.append(row)
        return merged

    @staticmethod
    def _merge_approval_rows(primary, secondary):
        merged = []
        seen: set[str] = set()
        for approval, case in list(primary or []) + list(secondary or []):
            key = str(getattr(approval, "id", "") or id(approval))
            if key in seen:
                continue
            seen.add(key)
            merged.append((approval, case))
        return merged

    def generate_manager_report(
        self,
        *,
        user_id: str,
        role: str,
        period: str,
        date_from: str = "",
        date_to: str = "",
    ) -> ReportArtifact:
        period_start, period_end = self._resolve_period_range(period, date_from=date_from, date_to=date_to)
        if role in {"admin", "top_manager"}:
            rows = self.visit_repository.list_all(limit=5000)
            case_rows = self.case_repository.list_all(limit=5000)
            approval_rows = self.approval_repository.list_all(limit=5000)
        else:
            rows = self.visit_repository.list_for_manager_user(user_id, limit=500)
            case_rows = self.case_repository.list_for_manager_user(user_id, limit=500)
            approval_rows = self.approval_repository.list_for_manager_user(user_id, limit=500)
            departments = self._active_curated_departments(user_id, period_start.isoformat(), period_end.isoformat())
            if departments:
                rows = self._merge_by_id(rows, self.visit_repository.list_for_department_names(departments, limit=500))
                case_rows = self._merge_by_id(case_rows, self.case_repository.list_for_department_names(departments, limit=500))
                approval_rows = self._merge_approval_rows(
                    approval_rows,
                    self.approval_repository.list_for_department_names(departments, limit=500),
                )
        filtered = self._filter_cases_by_period(rows, period_start, period_end)
        if role == "manager" and not rows and not case_rows:
            latest_import = self.skud_import_repository.get_latest_successful_for_user(user_id)
            if latest_import is not None:
                uploaded_start = self._parse_report_date(latest_import.period_start)
                uploaded_end = self._parse_report_date(latest_import.period_end)
                if uploaded_start is not None and uploaded_end is not None:
                    period_start, period_end = uploaded_start, uploaded_end
                    rows = self.visit_repository.list_all(limit=5000)
                    case_rows = self.case_repository.list_all(limit=5000)
                    approval_rows = self.approval_repository.list_all(limit=5000)
                    filtered = self._filter_cases_by_period(rows, period_start, period_end)
        entries = self._build_visit_entries(filtered, case_rows, approval_rows)
        if not entries and case_rows:
            entries = self._build_visit_entries_from_cases(case_rows, approval_rows)
        entries = self._sort_visit_rows(entries, primary="arrival")
        title = self._build_title(period, date_from=period_start.isoformat(), date_to=period_end.isoformat())
        summary_rows, detail_rows, detail_tabs = self._build_late_report_rows(entries, title, period_start, period_end)
        summary_text = self._rows_to_text(summary_rows)
        return self._create_report_artifact(
            user_id=user_id,
            role=role,
            report_type=period,
            title=title,
            summary_rows=summary_rows,
            detail_rows=detail_rows,
            detail_tabs=detail_tabs,
            summary_text=summary_text,
            filename_prefix=period,
            period_start=period_start,
            period_end=period_end,
            sheet1_name="Сводка",
            html_title="Недельный отчет" if period == "week" else "Месячный отчет" if period == "month" else "Квартальный отчет",
        )

    def generate_division_report(
        self,
        *,
        user_id: str,
        role: str,
        period: str,
        date_from: str = "",
        date_to: str = "",
    ) -> ReportArtifact:
        period_start, period_end = self._resolve_period_range(period, date_from=date_from, date_to=date_to)
        if role in {"admin", "top_manager"}:
            rows = self.visit_repository.list_all(limit=5000)
            case_rows = self.case_repository.list_all(limit=5000)
            approval_rows = self.approval_repository.list_all(limit=5000)
        else:
            rows = self.visit_repository.list_for_manager_user(user_id, limit=500)
            case_rows = self.case_repository.list_for_manager_user(user_id, limit=500)
            approval_rows = self.approval_repository.list_for_manager_user(user_id, limit=500)
            departments = self._active_curated_departments(user_id, period_start.isoformat(), period_end.isoformat())
            if departments:
                rows = self._merge_by_id(rows, self.visit_repository.list_for_department_names(departments, limit=500))
                case_rows = self._merge_by_id(case_rows, self.case_repository.list_for_department_names(departments, limit=500))
                approval_rows = self._merge_approval_rows(
                    approval_rows,
                    self.approval_repository.list_for_department_names(departments, limit=500),
                )
        filtered = self._filter_cases_by_period(rows, period_start, period_end)
        title = "Отчет по подразделениям" if period != "custom" else "Отчет по подразделениям за период"
        entries = self._build_visit_entries(filtered, case_rows, approval_rows)
        if not entries and case_rows:
            entries = self._build_visit_entries_from_cases(case_rows, approval_rows)
        entries = self._sort_visit_rows(entries, primary="arrival")
        summary_rows, detail_rows, detail_tabs = self._build_late_report_rows(entries, title, period_start, period_end)
        summary_text = self._rows_to_text(summary_rows + [["Разрез по подразделениям", ""]])
        return self._create_report_artifact(
            user_id=user_id,
            role=role,
            report_type=f"division_{period}",
            title=title,
            summary_rows=summary_rows,
            detail_rows=detail_rows,
            detail_tabs=detail_tabs,
            summary_text=summary_text,
            filename_prefix=f"division_{period}",
            period_start=period_start,
            period_end=period_end,
            sheet1_name="Сводка",
            html_title="Отчет по подразделениям",
        )

    def get_report_path(self, token: str, format: str = "xlsx") -> Path | None:
        report = self.report_repository.get_by_token(token)
        if report is None:
            return None
        path = Path(report.file_path)
        if format == "pdf":
            path = path.with_suffix(".pdf")
        if not path.exists():
            return None
        return path

    def _resolve_period_range(self, period: str, *, date_from: str = "", date_to: str = "") -> Tuple[date, date]:
        today = date.today()
        if period == "custom":
            start = self._parse_report_date(date_from)
            end = self._parse_report_date(date_to)
            if start is None or end is None:
                return today - timedelta(days=7), today
            if end < start:
                start, end = end, start
            return start, end
        if period == "month":
            return today - timedelta(days=30), today
        if period == "quarter":
            return today - timedelta(days=90), today
        return today - timedelta(days=7), today

    def _event_date_in_range(self, value: str, start: date, end: date) -> bool:
        try:
            event_date = date.fromisoformat(str(value))
        except Exception:
            return False
        return start <= event_date <= end

    def _build_title(self, period: str, *, date_from: str = "", date_to: str = "") -> str:
        if period == "custom":
            if date_from and date_to:
                return f"Отчет за период {date_from} - {date_to}"
            return "Отчет за период"
        return {
            "week": "Недельный отчет",
            "month": "Месячный отчет",
            "quarter": "Квартальный отчет",
        }.get(period, "Отчет")

    @staticmethod
    def _parse_report_date(value: str) -> date | None:
        raw = str(value or "").strip()
        if not raw:
            return None
        try:
            return date.fromisoformat(raw)
        except ValueError:
            return None

    def _build_file_name(self, period: str, user_id: str, token: str) -> str:
        safe_user = SAFE_USER_RE.sub("_", user_id).strip("._") or "user"
        return f"{period}_{safe_user}_{token[:8]}.xlsx"

    def _cleanup_previous_reports(self, *, user_id: str, report_type: str, keep_token: str) -> None:
        removed_paths = self.report_repository.delete_by_user_and_type(
            user_id,
            report_type,
            exclude_token=keep_token,
        )
        for path in removed_paths:
            try:
                if path.exists():
                    path.unlink()
            except Exception as exc:  # pragma: no cover - best effort cleanup
                self.logger.warning("Failed to remove old report file %s: %s", path, exc)

    def _create_report_artifact(
        self,
        *,
        user_id: str,
        role: str,
        report_type: str,
        title: str,
        summary_rows: List[List[str]],
        detail_rows: List[List[str]],
        detail_tabs: List[Tuple[str, List[List[str]]]] | None = None,
        summary_text: str,
        filename_prefix: str,
        period_start: date,
        period_end: date,
        sheet1_name: str,
        html_title: str,
        extra_rows: List[List[str]] | None = None,
    ) -> ReportArtifact:
        token = uuid.uuid4().hex
        file_name = self._build_file_name(filename_prefix, user_id, token)
        file_path = self.reports_dir / file_name
        pdf_file_name = file_path.with_suffix(".pdf").name
        pdf_file_path = self.reports_dir / pdf_file_name
        self._write_workbook(file_path, sheet1_name, summary_rows, detail_rows, detail_tabs or [], extra_rows or [])
        self._write_pdf(pdf_file_path, html_title, summary_rows, detail_rows, extra_rows or [])
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
        self._cleanup_previous_reports(user_id=user_id, report_type=report_type, keep_token=token)
        return ReportArtifact(
            report_id=report_id,
            token=token,
            title=title,
            file_name=file_name,
            file_path=str(file_path),
            pdf_file_name=pdf_file_name,
            pdf_file_path=str(pdf_file_path),
            period_start=period_start.isoformat(),
            period_end=period_end.isoformat(),
            summary_text=summary_text,
            download_url=self._build_download_url(token),
            pdf_download_url=self._build_download_url(token, format="pdf"),
        )

    def _filter_cases_by_period(self, rows, period_start: date, period_end: date):
        return [
            case
            for case in rows
            if self._event_date_in_range(case.event_date, period_start, period_end)
        ]

    def _build_visit_summary_rows(self, rows, title: str, period_start: date, period_end: date) -> List[List[str]]:
        total = len(rows)
        ordinary_rows = [row for row in rows if self._row_day_type(row) == "Обычный"]
        arrival_early = sum(1 for row in ordinary_rows if row.record.arrival_status == "early")
        arrival_on_time = sum(1 for row in ordinary_rows if row.record.arrival_status == "on_time")
        arrival_late = sum(1 for row in ordinary_rows if row.record.arrival_status == "late")
        departure_early = sum(1 for row in ordinary_rows if row.record.departure_status == "early")
        departure_on_time = sum(1 for row in ordinary_rows if row.record.departure_status == "on_time")
        departure_late = sum(1 for row in ordinary_rows if row.record.departure_status == "late")
        missing_exit = sum(1 for row in rows if self._row_day_type(row) == "Нет выхода")
        missing_entry = sum(1 for row in rows if self._row_day_type(row) == "Нет входа")
        no_passes = sum(1 for row in rows if self._row_day_type(row) == "Нет проходов")
        substitutions = sum(1 for row in rows if self._row_day_type(row) == "Замещение")
        problem_days = missing_exit + missing_entry + no_passes
        with_reason = sum(1 for row in rows if row.reason_text != "-")
        warned = sum(1 for row in rows if row.warned_text == "Да")
        matched = sum(1 for row in rows if row.matched_text == "Да")
        approved_warnings = sum(1 for row in rows if self._is_approved_late_notice(row))
        approved = sum(1 for row in rows if row.approval_status_text == "Согласовано")
        pending = sum(1 for row in rows if row.approval_status_text == "Ожидает")
        rejected = sum(1 for row in rows if row.approval_status_text == "Отклонено")
        return [
            ["Параметр", "Значение"],
            ["Название", title],
            ["Период с", period_start.isoformat()],
            ["Период по", period_end.isoformat()],
            ["Всего дней учета", str(total)],
            ["Проблемных дней", str(problem_days)],
            ["Нет выхода", str(missing_exit)],
            ["Нет входа", str(missing_entry)],
            ["Нет проходов", str(no_passes)],
            ["Замещения", str(substitutions)],
            ["Пришли раньше", str(arrival_early)],
            ["Пришли вовремя", str(arrival_on_time)],
            ["Пришли с опозданием", str(arrival_late)],
            ["Ушли раньше", str(departure_early)],
            ["Ушли вовремя", str(departure_on_time)],
            ["Ушли позже", str(departure_late)],
            ["Дней с причиной", str(with_reason)],
            ["Предупреждали заранее", str(warned)],
            ["Согласованные предупреждения", str(approved_warnings)],
            ["Сопоставлено со СКУД", str(matched)],
            ["Согласовано", str(approved)],
            ["На согласовании", str(pending)],
            ["Отклонено", str(rejected)],
        ]

    def _build_division_summary_rows(
        self,
        rows,
        title: str,
        period_start: date,
        period_end: date,
    ) -> Tuple[List[List[str]], List[List[str]]]:
        summary_rows = self._build_visit_summary_rows(rows, title, period_start, period_end)
        grouped = defaultdict(list)
        for row in rows:
            grouped[row.record.department_name or "Не указано"].append(row)

        department_rows: List[List[str]] = [[
            "Подразделение",
            "Всего дней",
            "Проблемных дней",
            "Нет выхода",
            "Нет проходов",
            "Замещения",
            "С опозданием",
            "С причиной",
            "Предупреждали",
            "Согласованные предупреждения",
            "Совпало со СКУД",
            "Согласовано",
            "На согласовании",
            "Отклонено",
            "Ушли позже",
        ]]
        department_order = sorted(
            grouped.items(),
            key=lambda item: (
                -sum(1 for case in item[1] if self._row_day_type(case) != "Обычный"),
                -len(item[1]),
                -sum(1 for case in item[1] if case.record.arrival_status == "late"),
                item[0],
            ),
        )
        for department_name, department_cases in department_order:
            department_rows.append(
                [
                    department_name,
                    str(len(department_cases)),
                    str(sum(1 for case in department_cases if self._row_day_type(case) != "Обычный" and self._row_day_type(case) != "Замещение")),
                    str(sum(1 for case in department_cases if self._row_day_type(case) == "Нет выхода")),
                    str(sum(1 for case in department_cases if self._row_day_type(case) == "Нет проходов")),
                    str(sum(1 for case in department_cases if self._row_day_type(case) == "Замещение")),
                    str(sum(1 for case in department_cases if case.record.arrival_status == "late")),
                    str(sum(1 for case in department_cases if case.reason_text != "-")),
                    str(sum(1 for case in department_cases if case.warned_text == "Да")),
                    str(sum(1 for case in department_cases if self._is_approved_late_notice(case))),
                    str(sum(1 for case in department_cases if case.matched_text == "Да")),
                    str(sum(1 for case in department_cases if case.approval_status_text == "Согласовано")),
                    str(sum(1 for case in department_cases if case.approval_status_text == "Ожидает")),
                    str(sum(1 for case in department_cases if case.approval_status_text == "Отклонено")),
                    str(sum(1 for case in department_cases if case.record.departure_status == "late")),
                ]
            )

        return summary_rows, department_rows

    def _build_late_report_rows(
        self,
        rows: List[VisitReportRow],
        title: str,
        period_start: date,
        period_end: date,
    ) -> Tuple[List[List[str]], List[List[str]], List[Tuple[str, List[List[str]]]]]:
        late_rows = [row for row in rows if self._is_late_report_row(row)]
        detail_rows = [self._late_detail_header()]
        grouped: dict[tuple[str, str], dict[str, object]] = defaultdict(
            lambda: {
                "employee": "",
                "department": "",
                "count": 0,
                "late": 0,
                "approved": 0,
                "unapproved": 0,
                "cases": [],
            }
        )
        by_date: dict[str, List[List[str]]] = defaultdict(lambda: [self._late_detail_header()])
        for row in late_rows:
            detail = self._late_detail_row(row)
            detail_rows.append(detail)
            by_date[detail[0]].append(detail)
            key = (
                str(getattr(row.record, "employee_user_id", "") or getattr(row.record, "employee_name", "") or ""),
                str(getattr(row.record, "employee_name", "") or ""),
            )
            bucket = grouped[key]
            bucket["employee"] = detail[1]
            bucket["department"] = detail[2]
            bucket["count"] = int(bucket["count"]) + 1
            bucket["late"] = int(bucket["late"]) + int(detail[6])
            bucket["approved"] = int(bucket["approved"]) + int(detail[7])
            bucket["unapproved"] = int(bucket["unapproved"]) + int(detail[8])
            bucket["cases"].append(f"{detail[0]}: {detail[9]} - {detail[10]}")

        summary_rows = [
            ["Сотрудник", "Подразделение", "Опозданий", "Опоздание по СКУД, мин", "Согласовано, мин", "Несогласовано, мин", "Случаи согласования"],
            ["Отчет", title, "", "", "", "", f"{period_start.isoformat()} - {period_end.isoformat()}"],
        ]
        for bucket in sorted(grouped.values(), key=lambda item: (-int(item["unapproved"]), -int(item["late"]), str(item["employee"]))):
            summary_rows.append(
                [
                    str(bucket["employee"]),
                    str(bucket["department"]),
                    str(bucket["count"]),
                    str(bucket["late"]),
                    str(bucket["approved"]),
                    str(bucket["unapproved"]),
                    "; ".join(str(item) for item in bucket["cases"]),
                ]
            )
        if len(summary_rows) == 2:
            summary_rows.append(["Опоздавших за период нет", "", "0", "0", "0", "0", ""])

        tabs = [(event_date, by_date[event_date]) for event_date in sorted(by_date)]
        return summary_rows, detail_rows, tabs

    @staticmethod
    def _late_detail_header() -> List[str]:
        return [
            "Дата",
            "Сотрудник",
            "Подразделение",
            "Приход",
            "Уход",
            "План прихода",
            "Опоздание, мин",
            "Согласовано, мин",
            "Несогласовано, мин",
            "Заявка/объяснение",
            "Статус согласования",
            "Кто согласовал",
            "Комментарий",
        ]

    def _late_detail_row(self, row: VisitReportRow) -> List[str]:
        late_minutes = max(int(getattr(row.record, "arrival_delta_minutes", 0) or 0), 0)
        approved = self._late_is_approved(row)
        return [
            str(getattr(row.record, "event_date", "") or "-"),
            str(getattr(row.record, "employee_name", "") or "-"),
            str(getattr(row.record, "department_name", "") or "-"),
            str(getattr(row.record, "first_entry_time", "") or "-"),
            str(getattr(row.record, "last_exit_time", "") or "-"),
            str(getattr(row.record, "planned_start", "") or "-"),
            str(late_minutes),
            str(late_minutes if approved else 0),
            str(0 if approved else late_minutes),
            row.kinds_text if row.kinds_text != "-" else "Нет заявки",
            row.approval_status_text if row.approval_status_text != "-" else "Нет",
            row.approver_text,
            row.approval_comment_text,
        ]

    def _is_late_report_row(self, row: VisitReportRow) -> bool:
        return (
            self._row_day_type(row) == "Обычный"
            and str(getattr(row.record, "arrival_status", "") or "") == "late"
            and int(getattr(row.record, "arrival_delta_minutes", 0) or 0) > 0
        )

    @staticmethod
    def _late_is_approved(row: VisitReportRow) -> bool:
        return row.case_count > 0 and row.approval_status_text == "Согласовано"

    def _build_visit_detail_rows(self, rows) -> List[List[str]]:
        detail_rows = [
            [
                "ID",
                "Сотрудник",
                "Подразделение",
                "Руководитель",
                "Дата",
                "Тип дня",
                "Приход",
                "Статус прихода",
                "План прихода",
                "Приход к плану, мин",
                "Уход",
                "Статус ухода",
                "План ухода",
                "Уход к плану, мин",
                "Количество проходов",
                "Нарушения",
                "Причина",
                "Предупреждал",
                "Сопоставлено со СКУД",
                "Статус согласования",
                "Кто согласовал",
                "Комментарий согласующего",
            ]
        ]
        for row in rows:
            detail_rows.append(
                [
                    str(row.record.id),
                    row.record.employee_name,
                    row.record.department_name,
                    row.record.manager_name or "",
                    row.record.event_date,
                    self._row_day_type(row),
                    row.record.first_entry_time or "-",
                    self._status_label(row.record.arrival_status),
                    row.record.planned_start or "-",
                    self._format_signed_minutes(row.record.arrival_delta_minutes),
                    row.record.last_exit_time or "-",
                    self._status_label(row.record.departure_status),
                    row.record.planned_end or "-",
                    self._format_signed_minutes(row.record.departure_delta_minutes),
                    str(row.record.total_passes),
                    row.kinds_text,
                    row.reason_text,
                    row.warned_text,
                    row.matched_text,
                    row.approval_status_text,
                    row.approver_text,
                    row.approval_comment_text,
                ]
            )
        return detail_rows

    def _build_visit_status_tabs(self, rows: List[VisitReportRow]) -> List[Tuple[str, List[List[str]]]]:
        tabs: List[Tuple[str, List[List[str]]]] = []
        problem_rows = self._sort_visit_rows(self._filter_problem_rows(rows), primary="arrival")
        tabs.append(("Проблемные дни", self._build_visit_detail_rows(problem_rows)))
        arrival_tabs = [
            ("Опоздавшие", "late"),
            ("Вовремя", "on_time"),
            ("Раньше", "early"),
        ]
        departure_tabs = [
            ("Ушли позже", "late"),
            ("Ушли вовремя", "on_time"),
            ("Ушли раньше", "early"),
        ]
        for title, status in arrival_tabs:
            filtered = self._sort_visit_rows(self._filter_visit_rows(rows, arrival_status=status, ordinary_only=True), primary="arrival")
            tabs.append((title, self._build_visit_detail_rows(filtered)))
            if status == "late":
                approved_late_notice_rows = self._sort_visit_rows(
                    [row for row in filtered if self._is_approved_late_notice(row)],
                    primary="arrival",
                )
                tabs.append(("Согласованные опоздания", self._build_visit_detail_rows(approved_late_notice_rows)))
        for title, status in departure_tabs:
            filtered = self._sort_visit_rows(self._filter_visit_rows(rows, departure_status=status, ordinary_only=True), primary="departure")
            tabs.append((title, self._build_visit_detail_rows(filtered)))
        return tabs

    def _build_workhours_rows(self, rows) -> List[List[str]]:
        header = [
            "Сотрудник",
            "Подразделение",
            "Неделя",
            "Дата",
            "Тип дня",
            "План, мин",
            "Факт, мин",
            "Обед, мин",
            "Итог дня, мин",
            "Опоздание, мин",
            "Итог недели, мин",
            "Опоздание недели, мин",
            "Компенсировано",
            "Первый вход",
            "Последний выход",
            "Проходов",
        ]
        result = [header]
        weekly: dict[tuple[str, int, int], dict[str, int]] = defaultdict(lambda: {"balance": 0, "late": 0, "overwork": 0})
        for row in rows:
            employee_key = str(getattr(row, "employee_user_id", "") or getattr(row, "employee_name", "")).strip()
            try:
                event_date = date.fromisoformat(str(getattr(row, "event_date", "") or ""))
            except ValueError:
                continue
            iso = event_date.isocalendar()
            key = (employee_key, iso.year, iso.week)
            balance_value = int(getattr(row, "balance_minutes", 0) or 0)
            weekly[key]["balance"] += balance_value
            if self._record_day_type(row) == "Обычный" and balance_value > 0:
                weekly[key]["overwork"] += balance_value
            if str(getattr(row, "arrival_status", "") or "") == "late":
                weekly[key]["late"] += int(getattr(row, "arrival_delta_minutes", 0) or 0)

        for row in rows:
            try:
                event_date = date.fromisoformat(str(getattr(row, "event_date", "") or ""))
            except ValueError:
                continue
            employee_key = str(getattr(row, "employee_user_id", "") or getattr(row, "employee_name", "")).strip()
            iso = event_date.isocalendar()
            week_stats = weekly[(employee_key, iso.year, iso.week)]
            day_type = self._record_day_type(row)
            compensated = (
                day_type == "Обычный"
                and
                str(getattr(row, "arrival_status", "") or "") == "late"
                and week_stats["late"] > 0
                and week_stats["overwork"] >= week_stats["late"]
            )
            day_balance = int(getattr(row, "balance_minutes", 0) or 0)
            week_balance = int(week_stats["balance"])
            day_balance_style = self._balance_style(day_balance)
            week_balance_style = self._balance_style(week_balance)
            result.append(
                [
                    _styled_cell(str(getattr(row, "employee_name", "") or "-"), day_balance_style),
                    _styled_cell(str(getattr(row, "department_name", "") or "-"), day_balance_style),
                    f"{iso.year}-W{iso.week:02d}",
                    str(getattr(row, "event_date", "") or "-"),
                    _styled_cell(day_type, XLSX_STYLE_NEGATIVE if day_type not in {"Обычный", "Замещение"} else day_balance_style),
                    str(int(getattr(row, "planned_minutes", 0) or 0)),
                    str(int(getattr(row, "worked_minutes", 0) or 0)),
                    str(int(getattr(row, "lunch_minutes", 0) or 0)),
                    _styled_cell(self._format_signed_minutes(day_balance), day_balance_style),
                    self._format_signed_minutes(int(getattr(row, "arrival_delta_minutes", 0) or 0) if str(getattr(row, "arrival_status", "") or "") == "late" else 0),
                    _styled_cell(self._format_signed_minutes(week_balance), week_balance_style),
                    self._format_signed_minutes(week_stats["late"]),
                    _styled_cell(
                        "Да" if compensated or bool(getattr(row, "late_compensated", False)) else "Нет",
                        XLSX_STYLE_POSITIVE if compensated or bool(getattr(row, "late_compensated", False)) else XLSX_STYLE_DEFAULT,
                    ),
                    str(getattr(row, "first_entry_time", "") or "-"),
                    str(getattr(row, "last_exit_time", "") or "-"),
                    str(int(getattr(row, "total_passes", 0) or 0)),
                ]
            )
        data_rows = result[1:]
        negative_rows = []
        neutral_rows = []
        positive_rows = []
        for row in data_rows:
            day_type = self._cell_text(row[4])
            day_balance = self._cell_int(row[8])
            if day_type in {"Нет выхода", "Нет входа", "Нет проходов"} or day_balance < 0:
                negative_rows.append(row)
            elif day_balance > 0:
                positive_rows.append(row)
            else:
                neutral_rows.append(row)
        negative_rows.sort(
            key=lambda row: (
                self._workhours_priority(self._cell_text(row[4]), self._cell_int(row[8])),
                self._cell_int(row[8]),
                -self._cell_int(row[9]),
                str(self._cell_text(row[0])),
                str(self._cell_text(row[3])),
            )
        )
        neutral_rows.sort(
            key=lambda row: (
                self._workhours_priority(self._cell_text(row[4]), self._cell_int(row[8])),
                -self._cell_int(row[9]),
                str(self._cell_text(row[0])),
                str(self._cell_text(row[3])),
            )
        )
        positive_rows.sort(
            key=lambda row: (
                -self._cell_int(row[8]),
                -self._cell_int(row[10]),
                -self._cell_int(row[9]),
                str(self._cell_text(row[0])),
                str(self._cell_text(row[3])),
            )
        )
        grouped_rows = [header]
        include_empty_summary_sections = not data_rows
        self._append_workhours_section(grouped_rows, "Просадка", negative_rows, style=XLSX_STYLE_NEGATIVE)
        self._append_workhours_section(
            grouped_rows,
            "Нейтрально",
            neutral_rows,
            style=XLSX_STYLE_DEFAULT,
            include_empty=include_empty_summary_sections,
        )
        self._append_workhours_section(
            grouped_rows,
            "Переработка",
            positive_rows,
            style=XLSX_STYLE_POSITIVE,
            include_empty=include_empty_summary_sections,
        )
        return grouped_rows

    def _build_workhours_department_rows(self, rows) -> List[List[object]]:
        result: List[List[object]] = [[
            "Подразделение",
            "Сотрудников",
            "Дней учета",
            "Проблемных дней",
            "Нет выхода",
            "Нет входа",
            "Нет проходов",
            "Замещения",
            "План, мин",
            "Факт, мин",
            "Обед, мин",
            "Итог, мин",
            "Ср. итог/день, мин",
            "Опоздание, мин",
            "Компенсировано опозданий",
        ]]
        grouped: dict[str, dict[str, object]] = defaultdict(
            lambda: {
                "employees": set(),
                "days": 0,
                "planned": 0,
                "worked": 0,
                "lunch": 0,
                "balance": 0,
                "late": 0,
                "compensated": 0,
                "problem_days": 0,
                "missing_exit": 0,
                "missing_entry": 0,
                "no_passes": 0,
                "substitutions": 0,
            }
        )
        for row in rows:
            department = str(getattr(row, "department_name", "") or "Не указано")
            bucket = grouped[department]
            day_type = self._record_day_type(row)
            bucket["employees"].add(str(getattr(row, "employee_user_id", "") or getattr(row, "employee_name", "") or "").strip())
            bucket["days"] += 1
            bucket["planned"] += int(getattr(row, "planned_minutes", 0) or 0)
            bucket["worked"] += int(getattr(row, "worked_minutes", 0) or 0)
            bucket["lunch"] += int(getattr(row, "lunch_minutes", 0) or 0)
            balance = int(getattr(row, "balance_minutes", 0) or 0)
            bucket["balance"] += balance
            if day_type not in {"Обычный", "Замещение"}:
                bucket["problem_days"] += 1
            if day_type == "Нет выхода":
                bucket["missing_exit"] += 1
            elif day_type == "Нет входа":
                bucket["missing_entry"] += 1
            elif day_type == "Нет проходов":
                bucket["no_passes"] += 1
            elif day_type == "Замещение":
                bucket["substitutions"] += 1
            if str(getattr(row, "arrival_status", "") or "") == "late":
                bucket["late"] += int(getattr(row, "arrival_delta_minutes", 0) or 0)
                if bool(getattr(row, "late_compensated", False)):
                    bucket["compensated"] += 1

        body_rows: List[List[object]] = []
        for department, stats in grouped.items():
            balance = int(stats["balance"])
            day_count = max(int(stats["days"]), 1)
            body_rows.append(
                [
                    _styled_cell(department, self._balance_style(balance)),
                    str(len([value for value in stats["employees"] if value])),
                    str(int(stats["days"])),
                    str(int(stats["problem_days"])),
                    str(int(stats["missing_exit"])),
                    str(int(stats["missing_entry"])),
                    str(int(stats["no_passes"])),
                    str(int(stats["substitutions"])),
                    str(int(stats["planned"])),
                    str(int(stats["worked"])),
                    str(int(stats["lunch"])),
                    _styled_cell(self._format_signed_minutes(balance), self._balance_style(balance)),
                    _styled_cell(self._format_signed_minutes(int(round(balance / day_count))), self._balance_style(balance)),
                    self._format_signed_minutes(int(stats["late"])),
                    _styled_cell(
                        str(int(stats["compensated"])),
                        XLSX_STYLE_POSITIVE if int(stats["compensated"]) > 0 else XLSX_STYLE_DEFAULT,
                    ),
                ]
            )
        negative_rows = []
        neutral_rows = []
        positive_rows = []
        for row in body_rows:
            balance = self._cell_int(row[11])
            if balance < 0:
                negative_rows.append(row)
            elif balance > 0:
                positive_rows.append(row)
            else:
                neutral_rows.append(row)
        negative_rows.sort(
            key=lambda row: (
                -self._cell_int(row[3]),
                self._cell_int(row[11]),
                -self._cell_int(row[13]),
                str(self._cell_text(row[0])),
            )
        )
        neutral_rows.sort(
            key=lambda row: (
                -self._cell_int(row[3]),
                -self._cell_int(row[13]),
                str(self._cell_text(row[0])),
            )
        )
        positive_rows.sort(
            key=lambda row: (
                -self._cell_int(row[11]),
                -self._cell_int(row[14]),
                -self._cell_int(row[13]),
                str(self._cell_text(row[0])),
            )
        )
        include_empty_summary_sections = not body_rows
        self._append_workhours_section(result, "Просадка", negative_rows, style=XLSX_STYLE_NEGATIVE)
        self._append_workhours_section(
            result,
            "Нейтрально",
            neutral_rows,
            style=XLSX_STYLE_DEFAULT,
            include_empty=include_empty_summary_sections,
        )
        self._append_workhours_section(
            result,
            "Переработка",
            positive_rows,
            style=XLSX_STYLE_POSITIVE,
            include_empty=include_empty_summary_sections,
        )
        return result

    def _sort_visit_rows(self, rows: List[VisitReportRow], *, primary: str) -> List[VisitReportRow]:
        def metric(row: VisitReportRow) -> int:
            if primary == "departure":
                return abs(int(getattr(row.record, "departure_delta_minutes", 0) or 0))
            return abs(int(getattr(row.record, "arrival_delta_minutes", 0) or 0))

        def event_key(row: VisitReportRow) -> str:
            return str(getattr(row.record, "event_date", "") or "")

        return sorted(
            rows,
            key=lambda row: (
                self._visit_priority(self._row_day_type(row)),
                metric(row),
                event_key(row),
                str(getattr(row.record, "employee_name", "") or ""),
            ),
            reverse=True,
        )

    @staticmethod
    def _filter_visit_rows(
        rows: List[VisitReportRow],
        *,
        arrival_status: str | None = None,
        departure_status: str | None = None,
        ordinary_only: bool = False,
    ) -> List[VisitReportRow]:
        filtered: List[VisitReportRow] = []
        for row in rows:
            if ordinary_only and row.record and ReportService._record_day_type(row.record) != "Обычный":
                continue
            if arrival_status is not None and str(getattr(row.record, "arrival_status", "") or "") != arrival_status:
                continue
            if departure_status is not None and str(getattr(row.record, "departure_status", "") or "") != departure_status:
                continue
            filtered.append(row)
        return filtered

    @classmethod
    def _filter_problem_rows(cls, rows: List[VisitReportRow]) -> List[VisitReportRow]:
        return [row for row in rows if cls._row_day_type(row) != "Обычный"]

    @staticmethod
    def _is_approved_late_notice(row: VisitReportRow) -> bool:
        return row.warned_text == "Да" and row.approval_status_text == "Согласовано"

    def _build_visit_entries(self, rows, case_rows, approval_rows) -> List[VisitReportRow]:
        case_groups = defaultdict(list)
        for case in case_rows:
            employee_user_id = str(getattr(case, "employee_user_id", "") or "").strip()
            event_date = str(getattr(case, "event_date", "") or "").strip()
            if not employee_user_id or not event_date:
                continue
            case_groups[(employee_user_id, event_date)].append(case)

        approval_by_case_id = {approval.case_id: approval for approval, _case in approval_rows}

        entries: List[VisitReportRow] = []
        for record in rows:
            matched_cases = case_groups.get((str(record.employee_user_id or "").strip(), str(record.event_date or "").strip()), [])
            kinds = []
            reasons = []
            approver_names = []
            approval_statuses = []
            approval_comments = []
            warned = False
            matched = False
            for case in matched_cases:
                kinds.append(self._case_kind_label(case))
                source = str(getattr(case, "source", "") or "").strip()
                if source.startswith("late_notice"):
                    warned = True
                if source == "late_notice_matched":
                    matched = True
                reason_text = str(getattr(case, "employee_reason", "") or "").strip()
                if reason_text:
                    reasons.append(reason_text)
                approval = approval_by_case_id.get(int(getattr(case, "id", 0) or 0))
                if approval is not None:
                    approval_statuses.append(self._approval_status_label(approval.status))
                    manager_name = str(getattr(approval, "manager_name", "") or "").strip()
                    if manager_name:
                        approver_names.append(manager_name)
                    comment = str(getattr(approval, "comment", "") or "").strip()
                    if comment:
                        approval_comments.append(comment)
            record_source = str(getattr(record, "source", "") or "").strip()
            if not matched_cases and record_source == "approved_substitution":
                kinds.append("Замещение")
                reasons.append("Согласованное замещение")
            entries.append(
                VisitReportRow(
                    record=record,
                    case_count=len(matched_cases),
                    kinds_text=self._join_unique(kinds) or "-",
                    reason_text=self._join_unique(reasons) or "-",
                    warned_text="Да" if warned else "Нет",
                    matched_text="Да" if matched else "Нет",
                    approval_status_text=self._merge_approval_statuses(approval_statuses),
                    approver_text=self._join_unique(approver_names) or "-",
                    approval_comment_text=self._join_unique(approval_comments) or "-",
                )
            )
        return entries

    def _build_visit_entries_from_cases(self, case_rows, approval_rows) -> List[VisitReportRow]:
        case_groups = defaultdict(list)
        for case in case_rows:
            employee_user_id = str(getattr(case, "employee_user_id", "") or "").strip()
            event_date = str(getattr(case, "event_date", "") or "").strip()
            employee_name = str(getattr(case, "employee_name", "") or "").strip()
            group_key = (employee_user_id or employee_name, event_date)
            if not group_key[1]:
                continue
            case_groups[group_key].append(case)

        approval_by_case_id = {approval.case_id: approval for approval, _case in approval_rows}
        entries: List[VisitReportRow] = []
        for (employee_key, event_date), matched_cases in case_groups.items():
            first_case = matched_cases[0]
            kinds = []
            reasons = []
            approver_names = []
            approval_statuses = []
            approval_comments = []
            warned = False
            matched = False
            for case in matched_cases:
                kinds.append(self._case_kind_label(case))
                source = str(getattr(case, "source", "") or "").strip()
                if source.startswith("late_notice"):
                    warned = True
                if source == "late_notice_matched":
                    matched = True
                reason_text = str(getattr(case, "employee_reason", "") or "").strip()
                if reason_text:
                    reasons.append(reason_text)
                approval = approval_by_case_id.get(int(getattr(case, "id", 0) or 0))
                if approval is not None:
                    approval_statuses.append(self._approval_status_label(approval.status))
                    manager_name = str(getattr(approval, "manager_name", "") or "").strip()
                    if manager_name:
                        approver_names.append(manager_name)
                    comment = str(getattr(approval, "comment", "") or "").strip()
                    if comment:
                        approval_comments.append(comment)

            record = SimpleNamespace(
                id=getattr(first_case, "id", 0),
                employee_name=str(getattr(first_case, "employee_name", "") or employee_key),
                department_name=str(getattr(first_case, "department_name", "") or "Не указано"),
                manager_name=str(getattr(first_case, "manager_name", "") or ""),
                event_date=event_date,
                first_entry_time=str(getattr(first_case, "actual_start", "") or "-"),
                arrival_status="late" if any(str(getattr(case, "case_type", "") or "").strip() == "late" for case in matched_cases) else "",
                arrival_delta_minutes=int(getattr(first_case, "delay_minutes", 0) or 0),
                last_exit_time="-",
                departure_status="",
                departure_delta_minutes=0,
                planned_start=str(getattr(first_case, "planned_start", "") or ""),
                planned_end="",
                total_passes=len(matched_cases),
            )
            entries.append(
                VisitReportRow(
                    record=record,
                    case_count=len(matched_cases),
                    kinds_text=self._join_unique(kinds) or "-",
                    reason_text=self._join_unique(reasons) or "-",
                    warned_text="Да" if warned else "Нет",
                    matched_text="Да" if matched else "Нет",
                    approval_status_text=self._merge_approval_statuses(approval_statuses),
                    approver_text=self._join_unique(approver_names) or "-",
                    approval_comment_text=self._join_unique(approval_comments) or "-",
                )
            )
        return entries

    def _join_unique(self, values: Sequence[str]) -> str:
        seen = set()
        ordered = []
        for value in values:
            text = str(value or "").strip()
            if not text or text in seen:
                continue
            seen.add(text)
            ordered.append(text)
        return "; ".join(ordered)

    @staticmethod
    def _record_day_type(record: object) -> str:
        source = str(getattr(record, "source", "") or "").strip()
        if source == "approved_substitution":
            return "Замещение"
        first_entry = str(getattr(record, "first_entry_time", "") or "").strip()
        last_exit = str(getattr(record, "last_exit_time", "") or "").strip()
        total_passes = int(getattr(record, "total_passes", 0) or 0)
        if first_entry and not last_exit:
            return "Нет выхода"
        if last_exit and not first_entry:
            return "Нет входа"
        if not first_entry and not last_exit and total_passes <= 0:
            return "Нет проходов"
        return "Обычный"

    @classmethod
    def _row_day_type(cls, row: VisitReportRow) -> str:
        return cls._record_day_type(row.record)

    @staticmethod
    def _visit_priority(day_type: str) -> int:
        if day_type == "Нет выхода":
            return 4
        if day_type == "Нет входа":
            return 3
        if day_type == "Нет проходов":
            return 2
        if day_type == "Замещение":
            return 1
        return 0

    @staticmethod
    def _workhours_priority(day_type: str, day_balance: int) -> int:
        if day_type == "Нет выхода":
            return 0
        if day_type == "Нет входа":
            return 1
        if day_type == "Нет проходов":
            return 2
        if day_balance < 0:
            return 3
        if day_balance == 0:
            return 4
        return 5

    @staticmethod
    def _workhours_balance_sort(day_balance: int) -> int:
        if day_balance < 0:
            return day_balance
        if day_balance == 0:
            return 0
        return -day_balance

    @staticmethod
    def _append_workhours_section(
        target_rows: List[List[object]],
        title: str,
        rows: List[List[object]],
        *,
        style: int,
        include_empty: bool = False,
    ) -> None:
        if not rows and not include_empty:
            return
        column_count = len(target_rows[0]) if target_rows else len(rows[0])
        section_row: List[object] = [_styled_cell(title, style)]
        while len(section_row) < column_count:
            section_row.append("")
        target_rows.append(section_row)
        target_rows.extend(rows)

    def _merge_approval_statuses(self, statuses: Sequence[str]) -> str:
        if not statuses:
            return "-"
        normalized = self._join_unique(statuses)
        if "Отклонено" in normalized:
            return "Отклонено"
        if "Ожидает" in normalized:
            return "Ожидает"
        if "Согласовано" in normalized:
            return "Согласовано"
        return normalized

    @staticmethod
    def _status_label(status: str) -> str:
        labels = {
            "early": "Раньше",
            "on_time": "Вовремя",
            "late": "Позже",
        }
        return labels.get(status, status or "-")

    @staticmethod
    def _balance_style(balance: int) -> int:
        if balance > 0:
            return XLSX_STYLE_POSITIVE
        if balance < 0:
            return XLSX_STYLE_NEGATIVE
        return XLSX_STYLE_DEFAULT

    @staticmethod
    def _approval_status_label(status: str) -> str:
        labels = {
            "pending": "Ожидает",
            "approved": "Согласовано",
            "rejected": "Отклонено",
        }
        return labels.get(status, status or "-")

    def _rows_to_text(self, rows: Sequence[Sequence[object]]) -> str:
        return "\n".join(" | ".join(self._cell_text(cell) for cell in row) for row in rows)

    @staticmethod
    def _format_signed_minutes(value: object) -> str:
        try:
            minute_value = int(value)
        except (TypeError, ValueError):
            return str(value)
        if minute_value > 0:
            return f"+{minute_value}"
        return str(minute_value)

    @staticmethod
    def _cell_text(cell: object) -> str:
        if isinstance(cell, dict):
            return str(cell.get("value", ""))
        return str(cell)

    def _cell_int(self, cell: object) -> int:
        text = self._cell_text(cell)
        try:
            return int(float(text))
        except (TypeError, ValueError):
            return 0

    def _write_pdf(self, file_path: Path, title: str, summary_rows: List[List[str]], detail_rows: List[List[str]], extra_rows: List[List[str]] | None = None) -> None:
        writer = SimplePdfWriter()
        lines = self._build_pdf_lines(title, summary_rows, detail_rows, extra_rows or [])
        file_path.write_bytes(writer.build_pdf(title, lines))

    def _build_pdf_lines(self, title: str, summary_rows: List[List[str]], detail_rows: List[List[str]], extra_rows: List[List[str]]) -> List[str]:
        if summary_rows and summary_rows[0][:2] == ["Сотрудник", "Подразделение"]:
            return self._build_late_pdf_lines(title, summary_rows, detail_rows)
        lines: List[str] = [title, "Сформировано автоматически", ""]
        for row in summary_rows[1:]:
            if len(row) >= 2:
                lines.append(f"{row[0]}: {row[1]}")
        if extra_rows:
            lines.extend(["", "Разрез по подразделениям"])
            for row in extra_rows[1:]:
                if len(row) >= 15:
                    lines.append(
                        f"{row[0]}: всего {row[1]}, проблемных {row[2]}, нет выхода {row[3]}, нет проходов {row[4]}, замещений {row[5]}, с опозданием {row[6]}, с причиной {row[7]}, предупреждали {row[8]}, согласованные предупреждения {row[9]}, совпало со СКУД {row[10]}, согласовано {row[11]}, на согласовании {row[12]}, отклонено {row[13]}, ушли позже {row[14]}"
                    )
        for title_label, filtered_rows in [
            ("Проблемные дни", self._filter_problem_detail_rows(detail_rows)),
            ("Опоздавшие", self._filter_detail_rows_by_status(detail_rows, arrival_status="late")),
            ("Согласованные опоздания", self._filter_approved_late_notice_detail_rows(detail_rows)),
            ("Вовремя", self._filter_detail_rows_by_status(detail_rows, arrival_status="on_time")),
            ("Раньше", self._filter_detail_rows_by_status(detail_rows, arrival_status="early")),
            ("Ушли позже", self._filter_detail_rows_by_status(detail_rows, departure_status="late")),
            ("Ушли вовремя", self._filter_detail_rows_by_status(detail_rows, departure_status="on_time")),
            ("Ушли раньше", self._filter_detail_rows_by_status(detail_rows, departure_status="early")),
        ]:
            lines.extend(["", title_label])
            for row in filtered_rows:
                lines.extend(
                    self._wrap_text_block(
                        [
                            f"ID: {row[DETAIL_COL_ID]}",
                            f"Сотрудник: {row[DETAIL_COL_EMPLOYEE]}",
                            f"Подразделение: {row[DETAIL_COL_DEPARTMENT]}",
                            f"Руководитель: {row[DETAIL_COL_MANAGER]}",
                            f"Дата: {row[DETAIL_COL_DATE]}",
                            f"Тип дня: {row[DETAIL_COL_DAY_TYPE]}",
                            f"Приход: {row[DETAIL_COL_ARRIVAL_TIME]} ({row[DETAIL_COL_ARRIVAL_STATUS]})",
                            f"План прихода: {row[DETAIL_COL_PLANNED_START]}",
                            f"Отклонение прихода: {row[DETAIL_COL_ARRIVAL_DELTA]} мин",
                            f"Уход: {row[DETAIL_COL_DEPARTURE_TIME]} ({row[DETAIL_COL_DEPARTURE_STATUS]})",
                            f"План ухода: {row[DETAIL_COL_PLANNED_END]}",
                            f"Отклонение ухода: {row[DETAIL_COL_DEPARTURE_DELTA]} мин",
                            f"Проходов за день: {row[DETAIL_COL_TOTAL_PASSES]}",
                            f"Нарушения: {row[DETAIL_COL_KINDS]}",
                            f"Причина: {row[DETAIL_COL_REASON]}",
                            f"Предупреждал: {row[DETAIL_COL_WARNED]}",
                            f"Сопоставлено со СКУД: {row[DETAIL_COL_MATCHED]}",
                            f"Согласование: {row[DETAIL_COL_APPROVAL_STATUS]}",
                            f"Кто согласовал: {row[DETAIL_COL_APPROVER]}",
                            f"Комментарий: {row[DETAIL_COL_APPROVAL_COMMENT]}",
                            "-" * 72,
                        ]
                    )
                )
        lines.extend(["", "Случаи"])
        for row in detail_rows[1:]:
            if len(row) < 22:
                continue
            lines.extend(
                self._wrap_text_block(
                    [
                        f"ID: {row[DETAIL_COL_ID]}",
                        f"Сотрудник: {row[DETAIL_COL_EMPLOYEE]}",
                        f"Подразделение: {row[DETAIL_COL_DEPARTMENT]}",
                        f"Руководитель: {row[DETAIL_COL_MANAGER]}",
                        f"Дата: {row[DETAIL_COL_DATE]}",
                        f"Тип дня: {row[DETAIL_COL_DAY_TYPE]}",
                        f"Приход: {row[DETAIL_COL_ARRIVAL_TIME]} ({row[DETAIL_COL_ARRIVAL_STATUS]})",
                        f"План прихода: {row[DETAIL_COL_PLANNED_START]}",
                        f"Отклонение прихода: {row[DETAIL_COL_ARRIVAL_DELTA]} мин",
                        f"Уход: {row[DETAIL_COL_DEPARTURE_TIME]} ({row[DETAIL_COL_DEPARTURE_STATUS]})",
                        f"План ухода: {row[DETAIL_COL_PLANNED_END]}",
                        f"Отклонение ухода: {row[DETAIL_COL_DEPARTURE_DELTA]} мин",
                        f"Проходов за день: {row[DETAIL_COL_TOTAL_PASSES]}",
                        f"Нарушения: {row[DETAIL_COL_KINDS]}",
                        f"Причина: {row[DETAIL_COL_REASON]}",
                        f"Предупреждал: {row[DETAIL_COL_WARNED]}",
                        f"Сопоставлено со СКУД: {row[DETAIL_COL_MATCHED]}",
                        f"Согласование: {row[DETAIL_COL_APPROVAL_STATUS]}",
                        f"Кто согласовал: {row[DETAIL_COL_APPROVER]}",
                        f"Комментарий: {row[DETAIL_COL_APPROVAL_COMMENT]}",
                        "-" * 72,
                    ]
                )
            )
        return lines

    def _build_late_pdf_lines(self, title: str, summary_rows: List[List[str]], detail_rows: List[List[str]]) -> List[str]:
        lines: List[str] = [title, "Сформировано автоматически", "", "Сводка по опоздавшим"]
        for row in summary_rows[2:]:
            if len(row) < 7:
                continue
            lines.extend(
                self._wrap_text_block(
                    [
                        f"{row[0]} | {row[1]}",
                        f"Опозданий: {row[2]}, по СКУД: {row[3]} мин, согласовано: {row[4]} мин, несогласовано: {row[5]} мин",
                        f"Случаи: {row[6] or '-'}",
                        "-" * 72,
                    ]
                )
            )
        grouped: dict[str, List[List[str]]] = defaultdict(list)
        for row in detail_rows[1:]:
            if len(row) >= 13:
                grouped[row[0]].append(row)
        for event_date in sorted(grouped):
            lines.extend(["", event_date])
            for row in grouped[event_date]:
                lines.extend(
                    self._wrap_text_block(
                        [
                            f"Сотрудник: {row[1]}",
                            f"Подразделение: {row[2]}",
                            f"Приход: {row[3]}, уход: {row[4]}, план: {row[5]}",
                            f"Опоздание: {row[6]} мин, согласовано: {row[7]} мин, несогласовано: {row[8]} мин",
                            f"Заявка/объяснение: {row[9]}",
                            f"Согласование: {row[10]}, кто: {row[11]}, комментарий: {row[12]}",
                            "-" * 72,
                        ]
                    )
                )
        return lines

    def _filter_detail_rows_by_status(
        self,
        rows: List[List[str]],
        *,
        arrival_status: str | None = None,
        departure_status: str | None = None,
    ) -> List[List[str]]:
        if not rows:
            return []
        filtered: List[List[str]] = [rows[0]]
        for row in rows[1:]:
            if len(row) < 22:
                continue
            if row[DETAIL_COL_DAY_TYPE] != "Обычный":
                continue
            if arrival_status is not None and row[DETAIL_COL_ARRIVAL_STATUS] != self._status_label(arrival_status):
                continue
            if departure_status is not None and row[DETAIL_COL_DEPARTURE_STATUS] != self._status_label(departure_status):
                continue
            filtered.append(row)
        return filtered

    def _filter_problem_detail_rows(self, rows: List[List[str]]) -> List[List[str]]:
        if not rows:
            return []
        filtered: List[List[str]] = [rows[0]]
        for row in rows[1:]:
            if len(row) < 22:
                continue
            if row[DETAIL_COL_DAY_TYPE] == "Обычный":
                continue
            filtered.append(row)
        return filtered

    def _filter_approved_late_notice_detail_rows(self, rows: List[List[str]]) -> List[List[str]]:
        if not rows:
            return []
        filtered: List[List[str]] = [rows[0]]
        for row in rows[1:]:
            if len(row) < 22:
                continue
            if row[DETAIL_COL_DAY_TYPE] != "Обычный":
                continue
            if row[DETAIL_COL_ARRIVAL_STATUS] != self._status_label("late"):
                continue
            if row[DETAIL_COL_WARNED] != "Да":
                continue
            if row[DETAIL_COL_APPROVAL_STATUS] != "Согласовано":
                continue
            filtered.append(row)
        return filtered

    def _wrap_text_block(self, lines: List[str], width: int = 96) -> List[str]:
        wrapped: List[str] = []
        for line in lines:
            wrapped.extend(textwrap.wrap(line, width=width, break_long_words=False, drop_whitespace=False) or [""])
        return wrapped

    def _write_workbook(
        self,
        file_path: Path,
        sheet1_name: str,
        summary_rows: List[List[str]],
        detail_rows: List[List[str]],
        detail_tabs: List[Tuple[str, List[List[str]]]] | None = None,
        extra_rows: List[List[str]] | None = None,
    ) -> None:
        file_path.parent.mkdir(parents=True, exist_ok=True)
        tabs = list(detail_tabs or [])
        sheet_payloads: List[Tuple[str, List[List[str]]]] = []
        if extra_rows:
            sheet_payloads.append(("Разрез", extra_rows))
        sheet_payloads.extend(tabs)
        sheet_payloads.append(("Случаи", detail_rows))
        with zipfile.ZipFile(file_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            sheet_count = 1 + len(sheet_payloads)
            archive.writestr("[Content_Types].xml", self._content_types_xml(sheet_count))
            archive.writestr("_rels/.rels", self._rels_xml())
            sheet_names = [sheet1_name]
            sheet_names.extend([title for title, _rows in sheet_payloads])
            archive.writestr("xl/workbook.xml", self._workbook_xml(sheet_names))
            archive.writestr("xl/_rels/workbook.xml.rels", self._workbook_rels_xml(sheet_count))
            archive.writestr("xl/styles.xml", self._styles_xml())
            archive.writestr("xl/worksheets/sheet1.xml", self._sheet_xml(summary_rows))
            next_sheet = 2
            for _title, tab_rows in sheet_payloads:
                archive.writestr(f"xl/worksheets/sheet{next_sheet}.xml", self._sheet_xml(tab_rows))
                next_sheet += 1

    def _content_types_xml(self, sheet_count: int) -> str:
        overrides = [
            '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
        ]
        for index in range(1, sheet_count + 1):
            overrides.append(
                f'<Override PartName="/xl/worksheets/sheet{index}.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
            )
        overrides.append('<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>')
        return """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  {overrides}
</Types>
""".format(overrides="\n  ".join(overrides))

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

    def _workbook_rels_xml(self, sheet_count: int) -> str:
        relationships = []
        for index in range(1, sheet_count + 1):
            relationships.append(
                f'<Relationship Id="rId{index}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet{index}.xml"/>'
            )
        relationships.append(
            f'<Relationship Id="rId{sheet_count + 1}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>'
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
  <fills count="4">
    <fill><patternFill patternType="none"/></fill>
    <fill><patternFill patternType="gray125"/></fill>
    <fill><patternFill patternType="solid"><fgColor rgb="FFE2F0D9"/><bgColor indexed="64"/></patternFill></fill>
    <fill><patternFill patternType="solid"><fgColor rgb="FFFDE9D9"/><bgColor indexed="64"/></patternFill></fill>
  </fills>
  <borders count="1"><border/></borders>
  <cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>
  <cellXfs count="3">
    <xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>
    <xf numFmtId="0" fontId="0" fillId="2" borderId="0" xfId="0" applyFill="1"/>
    <xf numFmtId="0" fontId="0" fillId="3" borderId="0" xfId="0" applyFill="1"/>
  </cellXfs>
</styleSheet>
"""

    def _sheet_xml(self, rows: List[List[object]]) -> str:
        sheet_rows = []
        for row_index, row in enumerate(rows, start=1):
            cells = []
            for col_index, value in enumerate(row, start=1):
                ref = f"{self._column_letter(col_index)}{row_index}"
                style_id = XLSX_STYLE_DEFAULT
                cell_value = value
                if isinstance(value, dict):
                    cell_value = value.get("value", "")
                    style_id = int(value.get("style", XLSX_STYLE_DEFAULT) or 0)
                style_attr = f' s="{style_id}"' if style_id else ""
                cells.append(
                    f'<c r="{ref}" t="inlineStr"{style_attr}><is><t>{escape(str(cell_value))}</t></is></c>'
                )
            sheet_rows.append(f"<row r=\"{row_index}\">{''.join(cells)}</row>")
        sheet_views = ""
        auto_filter = ""
        cols = ""
        if rows:
            max_cols = max(len(row) for row in rows)
            last_ref = f"{self._column_letter(max_cols)}1"
            auto_filter = f'  <autoFilter ref="A1:{last_ref}"/>\n'
            sheet_views = (
                "  <sheetViews>"
                '<sheetView workbookViewId="0">'
                '<pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" state="frozen"/>'
                "</sheetView>"
                "</sheetViews>\n"
            )
            cols = self._sheet_cols_xml(rows)
        return """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
{sheet_views}{cols}  <sheetData>{rows}</sheetData>
{auto_filter}</worksheet>
""".format(rows="".join(sheet_rows), sheet_views=sheet_views, cols=cols, auto_filter=auto_filter)

    def _sheet_cols_xml(self, rows: List[List[object]]) -> str:
        max_cols = max(len(row) for row in rows)
        widths: List[int] = []
        sample_rows = rows[: min(len(rows), 40)]
        for col_index in range(max_cols):
            column_width = 10
            for row in sample_rows:
                if col_index >= len(row):
                    continue
                text = self._cell_text(row[col_index]).strip()
                column_width = max(column_width, min(len(text) + 2, 40))
            widths.append(column_width)
        cols = "".join(
            f'<col min="{index}" max="{index}" width="{width}" customWidth="1"/>'
            for index, width in enumerate(widths, start=1)
        )
        return f"  <cols>{cols}</cols>\n"

    def _column_letter(self, index: int) -> str:
        result = ""
        while index:
            index, remainder = divmod(index - 1, 26)
            result = chr(65 + remainder) + result
        return result

    def _build_download_url(self, token: str, format: str = "xlsx") -> str:
        settings = get_settings()
        base = settings.max_bot_webhook_url.rstrip("/")
        suffix = "/api/webhooks/max"
        if base.endswith(suffix):
            base = base[: -len(suffix)]
        if format == "pdf":
            return f"{base}/api/reports/{token}/download/pdf"
        return f"{base}/api/reports/{token}/download"
