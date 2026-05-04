from __future__ import annotations

from app.domain.enums import ApprovalStatus, AttendanceCaseStatus, AttendanceCaseType
from app.repositories.approval_repository import ApprovalRepository
from app.repositories.attendance_case_repository import AttendanceCaseRepository
from app.db.base import SessionLocal
from app.db.models import ApprovalModel
from sqlalchemy import select


def ensure_demo_approvals() -> None:
    with SessionLocal() as session:
        existing = session.execute(select(ApprovalModel.id).limit(1)).first()
        if existing:
            return

    case_repo = AttendanceCaseRepository()
    approval_repo = ApprovalRepository()

    case_id_1 = case_repo.create_demo_case(
        employee_name="Иванов Иван Иванович",
        department_name="Отдел продаж",
        case_type=AttendanceCaseType.LATE.value,
        status=AttendanceCaseStatus.AWAITING_MANAGER_APPROVAL.value,
        event_date="2026-05-04",
        planned_start="08:30",
        actual_start="08:47",
        delay_minutes=17,
        employee_reason="Был у врача, справку предоставлю позже.",
    )
    case_id_2 = case_repo.create_demo_case(
        employee_name="Петров Петр Сергеевич",
        department_name="Отдел продаж",
        case_type=AttendanceCaseType.ABSENT.value,
        status=AttendanceCaseStatus.AWAITING_MANAGER_APPROVAL.value,
        event_date="2026-05-04",
        planned_start="08:30",
        actual_start="-",
        delay_minutes=0,
        employee_reason="Командировка, жду подтверждение в системе.",
    )

    with SessionLocal() as session:
        session.add_all(
            [
                ApprovalModel(
                    case_id=case_id_1,
                    manager_user_id="mgr_001",
                    manager_name="Тестовый Руководитель",
                    status=ApprovalStatus.PENDING.value,
                ),
                ApprovalModel(
                    case_id=case_id_2,
                    manager_user_id="mgr_001",
                    manager_name="Тестовый Руководитель",
                    status=ApprovalStatus.PENDING.value,
                ),
            ]
        )
        session.commit()


def ensure_demo_approvals_for_manager(manager_user_id: str, manager_name: str = "Тестовый Руководитель") -> None:
    approval_repo = ApprovalRepository()
    existing = approval_repo.list_pending_for_manager(manager_user_id)
    if existing:
        return

    case_repo = AttendanceCaseRepository()
    case_id_1 = case_repo.create_demo_case(
        employee_name="Иванов Иван Иванович",
        department_name="Отдел продаж",
        case_type=AttendanceCaseType.LATE.value,
        status=AttendanceCaseStatus.AWAITING_MANAGER_APPROVAL.value,
        event_date="2026-05-04",
        planned_start="08:30",
        actual_start="08:47",
        delay_minutes=17,
        employee_reason="Был у врача, справку предоставлю позже.",
    )
    case_id_2 = case_repo.create_demo_case(
        employee_name="Петров Петр Сергеевич",
        department_name="Отдел продаж",
        case_type=AttendanceCaseType.ABSENT.value,
        status=AttendanceCaseStatus.AWAITING_MANAGER_APPROVAL.value,
        event_date="2026-05-04",
        planned_start="08:30",
        actual_start="-",
        delay_minutes=0,
        employee_reason="Командировка, жду подтверждение в системе.",
    )

    with SessionLocal() as session:
        session.add_all(
            [
                ApprovalModel(
                    case_id=case_id_1,
                    manager_user_id=manager_user_id,
                    manager_name=manager_name,
                    status=ApprovalStatus.PENDING.value,
                ),
                ApprovalModel(
                    case_id=case_id_2,
                    manager_user_id=manager_user_id,
                    manager_name=manager_name,
                    status=ApprovalStatus.PENDING.value,
                ),
            ]
        )
        session.commit()
