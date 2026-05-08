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
from app.services.simple_pdf import SimplePdfWriter


SAFE_USER_RE = re.compile(r"[^A-Za-z0-9._-]+")


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
    approval_status_text: str
    approver_text: str
    approval_comment_text: str


class ReportService:
    def __init__(self) -> None:
        self.logger = logging.getLogger(__name__)
        self.visit_repository = AttendanceDayRecordRepository()
        self.case_repository = AttendanceCaseRepository()
        self.approval_repository = ApprovalRepository()
        self.report_repository = ReportRepository()
        self.reports_dir = BASE_DIR / "data" / "reports"
        self.reports_dir.mkdir(parents=True, exist_ok=True)

    def generate_manager_report(self, *, user_id: str, role: str, period: str) -> ReportArtifact:
        rows = self.visit_repository.list_for_manager_user(user_id, limit=500)
        case_rows = self.case_repository.list_for_manager_user(user_id, limit=500)
        approval_rows = self.approval_repository.list_for_manager_user(user_id, limit=500)
        period_start, period_end = self._resolve_period_range(period)
        filtered = self._filter_cases_by_period(rows, period_start, period_end)
        entries = self._build_visit_entries(filtered, case_rows, approval_rows)
        if not entries and case_rows:
            entries = self._build_visit_entries_from_cases(case_rows, approval_rows)
        title = self._build_title(period)
        summary_rows = self._build_visit_summary_rows(entries, title, period_start, period_end)
        detail_tabs = self._build_visit_status_tabs(entries)
        detail_rows = self._build_visit_detail_rows(entries)
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

    def generate_division_report(self, *, user_id: str, role: str, period: str) -> ReportArtifact:
        if role in {"admin", "top_manager"}:
            rows = self.visit_repository.list_all(limit=5000)
            case_rows = self.case_repository.list_all(limit=5000)
            approval_rows = self.approval_repository.list_all(limit=5000)
        else:
            rows = self.visit_repository.list_for_manager_user(user_id, limit=500)
            case_rows = self.case_repository.list_for_manager_user(user_id, limit=500)
            approval_rows = self.approval_repository.list_for_manager_user(user_id, limit=500)
        period_start, period_end = self._resolve_period_range(period)
        filtered = self._filter_cases_by_period(rows, period_start, period_end)
        title = "Отчет по подразделениям"
        entries = self._build_visit_entries(filtered, case_rows, approval_rows)
        if not entries and case_rows:
            entries = self._build_visit_entries_from_cases(case_rows, approval_rows)
        summary_rows, department_rows = self._build_division_summary_rows(entries, title, period_start, period_end)
        detail_tabs = self._build_visit_status_tabs(entries)
        detail_rows = self._build_visit_detail_rows(entries)
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
            detail_tabs=detail_tabs,
            summary_text=summary_text,
            filename_prefix=f"division_{period}",
            period_start=period_start,
            period_end=period_end,
            sheet1_name="Подразделения",
            extra_rows=department_rows,
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
            return False
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
        arrival_early = sum(1 for row in rows if row.record.arrival_status == "early")
        arrival_on_time = sum(1 for row in rows if row.record.arrival_status == "on_time")
        arrival_late = sum(1 for row in rows if row.record.arrival_status == "late")
        departure_early = sum(1 for row in rows if row.record.departure_status == "early")
        departure_on_time = sum(1 for row in rows if row.record.departure_status == "on_time")
        departure_late = sum(1 for row in rows if row.record.departure_status == "late")
        with_reason = sum(1 for row in rows if row.reason_text != "-")
        approved = sum(1 for row in rows if row.approval_status_text == "Согласовано")
        pending = sum(1 for row in rows if row.approval_status_text == "Ожидает")
        rejected = sum(1 for row in rows if row.approval_status_text == "Отклонено")
        return [
            ["Параметр", "Значение"],
            ["Название", title],
            ["Период с", period_start.isoformat()],
            ["Период по", period_end.isoformat()],
            ["Всего дней учета", str(total)],
            ["Пришли раньше", str(arrival_early)],
            ["Пришли вовремя", str(arrival_on_time)],
            ["Пришли с опозданием", str(arrival_late)],
            ["Ушли раньше", str(departure_early)],
            ["Ушли вовремя", str(departure_on_time)],
            ["Ушли позже", str(departure_late)],
            ["Дней с причиной", str(with_reason)],
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
            "С опозданием",
            "С причиной",
            "Согласовано",
            "На согласовании",
            "Отклонено",
            "Ушли позже",
        ]]
        for department_name in sorted(grouped.keys()):
            department_cases = grouped[department_name]
            department_rows.append(
                [
                    department_name,
                    str(len(department_cases)),
                    str(sum(1 for case in department_cases if case.record.arrival_status == "late")),
                    str(sum(1 for case in department_cases if case.reason_text != "-")),
                    str(sum(1 for case in department_cases if case.approval_status_text == "Согласовано")),
                    str(sum(1 for case in department_cases if case.approval_status_text == "Ожидает")),
                    str(sum(1 for case in department_cases if case.approval_status_text == "Отклонено")),
                    str(sum(1 for case in department_cases if case.record.departure_status == "late")),
                ]
            )

        return summary_rows, department_rows

    def _build_visit_detail_rows(self, rows) -> List[List[str]]:
        detail_rows = [
            [
                "ID",
                "Сотрудник",
                "Подразделение",
                "Руководитель",
                "Дата",
                "Приход",
                "Статус прихода",
                "План прихода",
                "Отклонение прихода, мин",
                "Уход",
                "Статус ухода",
                "План ухода",
                "Отклонение ухода, мин",
                "Количество проходов",
                "Нарушения",
                "Причина",
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
                    row.record.first_entry_time or "-",
                    self._status_label(row.record.arrival_status),
                    row.record.planned_start or "-",
                    str(row.record.arrival_delta_minutes),
                    row.record.last_exit_time or "-",
                    self._status_label(row.record.departure_status),
                    row.record.planned_end or "-",
                    str(row.record.departure_delta_minutes),
                    str(row.record.total_passes),
                    row.kinds_text,
                    row.reason_text,
                    row.approval_status_text,
                    row.approver_text,
                    row.approval_comment_text,
                ]
            )
        return detail_rows

    def _build_visit_status_tabs(self, rows: List[VisitReportRow]) -> List[Tuple[str, List[List[str]]]]:
        tabs: List[Tuple[str, List[List[str]]]] = []
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
            filtered = self._filter_visit_rows(rows, arrival_status=status)
            tabs.append((title, self._build_visit_detail_rows(filtered)))
        for title, status in departure_tabs:
            filtered = self._filter_visit_rows(rows, departure_status=status)
            tabs.append((title, self._build_visit_detail_rows(filtered)))
        return tabs

    @staticmethod
    def _filter_visit_rows(
        rows: List[VisitReportRow],
        *,
        arrival_status: str | None = None,
        departure_status: str | None = None,
    ) -> List[VisitReportRow]:
        filtered: List[VisitReportRow] = []
        for row in rows:
            if arrival_status is not None and str(getattr(row.record, "arrival_status", "") or "") != arrival_status:
                continue
            if departure_status is not None and str(getattr(row.record, "departure_status", "") or "") != departure_status:
                continue
            filtered.append(row)
        return filtered

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
            for case in matched_cases:
                case_type = str(getattr(case, "case_type", "") or "").strip()
                if case_type == "late":
                    kinds.append("Опоздание")
                elif case_type == "absent":
                    kinds.append("Неявка")
                else:
                    kinds.append(case_type or "Нарушение")
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
            entries.append(
                VisitReportRow(
                    record=record,
                    case_count=len(matched_cases),
                    kinds_text=self._join_unique(kinds) or "-",
                    reason_text=self._join_unique(reasons) or "-",
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
            for case in matched_cases:
                case_type = str(getattr(case, "case_type", "") or "").strip()
                if case_type == "late":
                    kinds.append("Опоздание")
                elif case_type == "absent":
                    kinds.append("Неявка")
                else:
                    kinds.append(case_type or "Нарушение")
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
                last_exit_time="",
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
    def _approval_status_label(status: str) -> str:
        labels = {
            "pending": "Ожидает",
            "approved": "Согласовано",
            "rejected": "Отклонено",
        }
        return labels.get(status, status or "-")

    def _rows_to_text(self, rows: Sequence[Sequence[str]]) -> str:
        return "\n".join(" | ".join(cell for cell in row) for row in rows)

    def _write_pdf(self, file_path: Path, title: str, summary_rows: List[List[str]], detail_rows: List[List[str]], extra_rows: List[List[str]] | None = None) -> None:
        writer = SimplePdfWriter()
        lines = self._build_pdf_lines(title, summary_rows, detail_rows, extra_rows or [])
        file_path.write_bytes(writer.build_pdf(title, lines))

    def _build_pdf_lines(self, title: str, summary_rows: List[List[str]], detail_rows: List[List[str]], extra_rows: List[List[str]]) -> List[str]:
        lines: List[str] = [title, "Сформировано автоматически", ""]
        for row in summary_rows[1:]:
            if len(row) >= 2:
                lines.append(f"{row[0]}: {row[1]}")
        if extra_rows:
            lines.extend(["", "Разрез по подразделениям"])
            for row in extra_rows[1:]:
                if len(row) >= 8:
                    lines.append(
                        f"{row[0]}: всего {row[1]}, с опозданием {row[2]}, с причиной {row[3]}, согласовано {row[4]}, на согласовании {row[5]}, отклонено {row[6]}, ушли позже {row[7]}"
                    )
        for title_label, filtered_rows in [
            ("Опоздавшие", self._filter_detail_rows_by_status(detail_rows, arrival_status="late")),
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
                            f"ID: {row[0]}",
                            f"Сотрудник: {row[1]}",
                            f"Подразделение: {row[2]}",
                            f"Руководитель: {row[3]}",
                            f"Дата: {row[4]}",
                            f"Приход: {row[5]} ({row[6]})",
                            f"План прихода: {row[7]}",
                            f"Отклонение прихода: {row[8]} мин",
                            f"Уход: {row[9]} ({row[10]})",
                            f"План ухода: {row[11]}",
                            f"Отклонение ухода: {row[12]} мин",
                            f"Проходов за день: {row[13]}",
                            f"Нарушения: {row[14]}",
                            f"Причина: {row[15]}",
                            f"Согласование: {row[16]}",
                            f"Кто согласовал: {row[17]}",
                            f"Комментарий: {row[18]}",
                            "-" * 72,
                        ]
                    )
                )
        lines.extend(["", "Случаи"])
        for row in detail_rows[1:]:
            if len(row) < 19:
                continue
            lines.extend(
                self._wrap_text_block(
                    [
                        f"ID: {row[0]}",
                        f"Сотрудник: {row[1]}",
                        f"Подразделение: {row[2]}",
                        f"Руководитель: {row[3]}",
                        f"Дата: {row[4]}",
                        f"Приход: {row[5]} ({row[6]})",
                        f"План прихода: {row[7]}",
                        f"Отклонение прихода: {row[8]} мин",
                        f"Уход: {row[9]} ({row[10]})",
                        f"План ухода: {row[11]}",
                        f"Отклонение ухода: {row[12]} мин",
                        f"Проходов за день: {row[13]}",
                        f"Нарушения: {row[14]}",
                        f"Причина: {row[15]}",
                        f"Согласование: {row[16]}",
                        f"Кто согласовал: {row[17]}",
                        f"Комментарий: {row[18]}",
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
            if len(row) < 19:
                continue
            if arrival_status is not None and row[6] != self._status_label(arrival_status):
                continue
            if departure_status is not None and row[10] != self._status_label(departure_status):
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

    def _build_download_url(self, token: str, format: str = "xlsx") -> str:
        settings = get_settings()
        base = settings.max_bot_webhook_url.rstrip("/")
        suffix = "/api/webhooks/max"
        if base.endswith(suffix):
            base = base[: -len(suffix)]
        if format == "pdf":
            return f"{base}/api/reports/{token}/download/pdf"
        return f"{base}/api/reports/{token}/download"
