from __future__ import annotations

from datetime import date
from types import SimpleNamespace
from uuid import uuid4

from app.db.base import SessionLocal
from app.db.models import ApprovalModel, AttendanceCaseModel
from app.domain.enums import ApprovalStatus, AttendanceCaseStatus, AttendanceCaseType
from app.repositories.approval_repository import ApprovalRepository
from app.repositories.attendance_case_repository import AttendanceCaseRepository
from app.services.report_service import ReportService


def _late_day_record(*, marker: str, employee_user_id: str):
    return SimpleNamespace(
        id=1,
        employee_user_id=employee_user_id,
        employee_name=f"Тест Согласование {marker}",
        department_name="Отдел тестирования",
        manager_name="Тест Руководитель",
        event_date="2026-05-04",
        planned_start="08:30",
        planned_end="17:15",
        first_entry_time="08:47",
        arrival_status="late",
        arrival_delta_minutes=17,
        last_exit_time="17:20",
        departure_status="late",
        departure_delta_minutes=5,
        worked_minutes=455,
        planned_minutes=435,
        lunch_minutes=60,
        balance_minutes=20,
        late_compensated=False,
        total_passes=8,
        source="skud_report",
    )


def _cleanup(case_id: int, approval_id: int | None = None) -> None:
    with SessionLocal() as session:
        if approval_id is not None:
            approval = session.get(ApprovalModel, approval_id)
            if approval is not None:
                session.delete(approval)
        case = session.get(AttendanceCaseModel, case_id)
        if case is not None:
            session.delete(case)
        session.commit()


def test_approved_case_status_and_approval_fields_reach_report_export() -> None:
    marker = uuid4().hex
    employee_user_id = f"emp-{marker}"
    case_repo = AttendanceCaseRepository()
    approval_repo = ApprovalRepository()
    case_id = case_repo.create_case(
        employee_user_id=employee_user_id,
        employee_name=f"Тест Согласование {marker}",
        department_name="Отдел тестирования",
        manager_user_id=f"mgr-{marker}",
        manager_name="Тест Руководитель",
        case_type=AttendanceCaseType.LATE.value,
        status=AttendanceCaseStatus.AWAITING_MANAGER_APPROVAL.value,
        event_date="2026-05-04",
        planned_start="08:30",
        actual_start="08:47",
        delay_minutes=17,
        employee_reason="Пробки",
        source="manual",
    )
    approval_id = approval_repo.create(
        case_id=case_id,
        manager_user_id=f"mgr-{marker}",
        manager_name="Тест Руководитель",
    )

    try:
        approval_repo.update_status(approval_id, ApprovalStatus.APPROVED.value)

        case = case_repo.get(case_id)
        approval_rows = approval_repo.list_for_manager_user(
            f"mgr-{marker}",
            date_from="2026-05-04",
            date_to="2026-05-04",
        )
        service = ReportService()
        entries = service._build_visit_entries(
            [_late_day_record(marker=marker, employee_user_id=employee_user_id)],
            [case],
            approval_rows,
        )
        _summary_rows, detail_rows, _tabs = service._build_late_report_rows(
            entries,
            "Тестовый отчет",
            date(2026, 5, 4),
            date(2026, 5, 4),
        )

        assert case.status == AttendanceCaseStatus.JUSTIFIED.value
        assert detail_rows[1][7] == "17"
        assert detail_rows[1][8] == "0"
        assert detail_rows[1][9] == "Опоздание"
        assert detail_rows[1][10] == "Согласовано"
        assert detail_rows[1][11] == "Тест Руководитель"
    finally:
        _cleanup(case_id, approval_id)


def test_rejected_case_status_comment_and_approval_fields_reach_report_export() -> None:
    marker = uuid4().hex
    employee_user_id = f"emp-{marker}"
    case_repo = AttendanceCaseRepository()
    approval_repo = ApprovalRepository()
    case_id = case_repo.create_case(
        employee_user_id=employee_user_id,
        employee_name=f"Тест Отказ {marker}",
        department_name="Отдел тестирования",
        manager_user_id=f"mgr-{marker}",
        manager_name="Тест Руководитель",
        case_type=AttendanceCaseType.LATE.value,
        status=AttendanceCaseStatus.AWAITING_MANAGER_APPROVAL.value,
        event_date="2026-05-04",
        planned_start="08:30",
        actual_start="08:47",
        delay_minutes=17,
        employee_reason="Пробки",
        source="manual",
    )
    approval_id = approval_repo.create(
        case_id=case_id,
        manager_user_id=f"mgr-{marker}",
        manager_name="Тест Руководитель",
    )

    try:
        approval_repo.update_status(approval_id, ApprovalStatus.REJECTED.value, comment="Нет подтверждения")

        case = case_repo.get(case_id)
        approval_rows = approval_repo.list_for_manager_user(
            f"mgr-{marker}",
            date_from="2026-05-04",
            date_to="2026-05-04",
        )
        service = ReportService()
        entries = service._build_visit_entries(
            [_late_day_record(marker=marker, employee_user_id=employee_user_id)],
            [case],
            approval_rows,
        )
        _summary_rows, detail_rows, _tabs = service._build_late_report_rows(
            entries,
            "Тестовый отчет",
            date(2026, 5, 4),
            date(2026, 5, 4),
        )

        assert case.status == AttendanceCaseStatus.UNJUSTIFIED.value
        assert detail_rows[1][7] == "0"
        assert detail_rows[1][8] == "17"
        assert detail_rows[1][10] == "Отклонено"
        assert detail_rows[1][11] == "Тест Руководитель"
        assert detail_rows[1][12] == "Нет подтверждения"
    finally:
        _cleanup(case_id, approval_id)
