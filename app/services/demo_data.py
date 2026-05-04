from __future__ import annotations

from sqlalchemy import select

from app.db.base import SessionLocal
from app.db.models import ApprovalModel
from app.domain.enums import ApprovalStatus, AttendanceCaseStatus, AttendanceCaseType
from app.repositories.approval_repository import ApprovalRepository
from app.repositories.attendance_case_repository import AttendanceCaseRepository
from app.repositories.user_role_override_repository import UserRoleOverrideRepository


def ensure_demo_approvals() -> None:
    with SessionLocal() as session:
        existing = session.execute(select(ApprovalModel.id).limit(1)).first()
        if existing:
            return

    case_repo = AttendanceCaseRepository()

    case_id_1 = case_repo.create_case(
        employee_name="Иванов Иван Иванович",
        department_name="Отдел продаж",
        manager_user_id="mgr_001",
        manager_name="Тестовый Руководитель",
        case_type=AttendanceCaseType.LATE.value,
        status=AttendanceCaseStatus.AWAITING_MANAGER_APPROVAL.value,
        event_date="2026-05-04",
        planned_start="08:30",
        actual_start="08:47",
        delay_minutes=17,
        employee_reason="Был у врача, справку предоставлю позже.",
        source="demo",
    )
    case_id_2 = case_repo.create_case(
        employee_name="Петров Петр Сергеевич",
        department_name="Отдел продаж",
        manager_user_id="mgr_001",
        manager_name="Тестовый Руководитель",
        case_type=AttendanceCaseType.ABSENT.value,
        status=AttendanceCaseStatus.AWAITING_MANAGER_APPROVAL.value,
        event_date="2026-05-04",
        planned_start="08:30",
        actual_start="-",
        delay_minutes=0,
        employee_reason="Командировка, жду подтверждение в системе.",
        source="demo",
    )

    approval_repo = ApprovalRepository()
    approval_repo.create(case_id=case_id_1, manager_user_id="mgr_001", manager_name="Тестовый Руководитель")
    approval_repo.create(case_id=case_id_2, manager_user_id="mgr_001", manager_name="Тестовый Руководитель")


def ensure_demo_approvals_for_manager(manager_user_id: str, manager_name: str = "Тестовый Руководитель") -> None:
    approval_repo = ApprovalRepository()
    existing = approval_repo.list_pending_for_manager(manager_user_id)
    if existing:
        return

    case_repo = AttendanceCaseRepository()
    case_id_1 = case_repo.create_case(
        employee_name="Иванов Иван Иванович",
        department_name="Отдел продаж",
        manager_user_id=manager_user_id,
        manager_name=manager_name,
        case_type=AttendanceCaseType.LATE.value,
        status=AttendanceCaseStatus.AWAITING_MANAGER_APPROVAL.value,
        event_date="2026-05-04",
        planned_start="08:30",
        actual_start="08:47",
        delay_minutes=17,
        employee_reason="Был у врача, справку предоставлю позже.",
        source="demo",
    )
    case_id_2 = case_repo.create_case(
        employee_name="Петров Петр Сергеевич",
        department_name="Отдел продаж",
        manager_user_id=manager_user_id,
        manager_name=manager_name,
        case_type=AttendanceCaseType.ABSENT.value,
        status=AttendanceCaseStatus.AWAITING_MANAGER_APPROVAL.value,
        event_date="2026-05-04",
        planned_start="08:30",
        actual_start="-",
        delay_minutes=0,
        employee_reason="Командировка, жду подтверждение в системе.",
        source="demo",
    )
    approval_repo.create(case_id=case_id_1, manager_user_id=manager_user_id, manager_name=manager_name)
    approval_repo.create(case_id=case_id_2, manager_user_id=manager_user_id, manager_name=manager_name)


def ensure_demo_cases_for_employee(employee_user_id: str) -> None:
    case_repo = AttendanceCaseRepository()
    existing = case_repo.list_for_employee_user(employee_user_id)
    if existing:
        return

    manager_user_id = "mgr_001"
    manager_name = "Тестовый Руководитель"
    UserRoleOverrideRepository().set_role(manager_user_id, "manager")

    case_repo.create_case(
        employee_user_id=employee_user_id,
        employee_name="Тестовый Сотрудник",
        department_name="Отдел продаж",
        manager_user_id=manager_user_id,
        manager_name=manager_name,
        case_type=AttendanceCaseType.LATE.value,
        status=AttendanceCaseStatus.AWAITING_EMPLOYEE_REASON.value,
        event_date="2026-05-04",
        planned_start="08:30",
        actual_start="08:44",
        delay_minutes=14,
        employee_reason="",
        source="demo",
    )
    case_repo.create_case(
        employee_user_id=employee_user_id,
        employee_name="Тестовый Сотрудник",
        department_name="Отдел продаж",
        manager_user_id=manager_user_id,
        manager_name=manager_name,
        case_type=AttendanceCaseType.LATE.value,
        status=AttendanceCaseStatus.AWAITING_MANAGER_APPROVAL.value,
        event_date="2026-05-03",
        planned_start="08:30",
        actual_start="08:41",
        delay_minutes=11,
        employee_reason="Командировка",
        source="demo",
    )
