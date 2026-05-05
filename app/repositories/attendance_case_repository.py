from __future__ import annotations

from typing import List, Optional

from sqlalchemy import select

from app.db.base import SessionLocal
from app.db.models import AttendanceCaseModel
from app.domain.enums import AttendanceCaseStatus


class AttendanceCaseRepository:
    def create_case(
        self,
        *,
        employee_user_id: str = "",
        employee_name: str,
        department_name: str,
        manager_user_id: str = "",
        manager_name: str = "",
        case_type: str,
        status: str,
        event_date: str,
        planned_start: str,
        actual_start: str,
        delay_minutes: int,
        employee_reason: str,
        source: str = "manual",
    ) -> int:
        with SessionLocal() as session:
            case = AttendanceCaseModel(
                employee_user_id=employee_user_id,
                employee_name=employee_name,
                department_name=department_name,
                manager_user_id=manager_user_id,
                manager_name=manager_name,
                case_type=case_type,
                status=status,
                event_date=event_date,
                planned_start=planned_start,
                actual_start=actual_start,
                delay_minutes=delay_minutes,
                employee_reason=employee_reason,
                source=source,
            )
            session.add(case)
            session.commit()
            session.refresh(case)
            return int(case.id)

    def list_recent(self, limit: int = 20) -> List[AttendanceCaseModel]:
        with SessionLocal() as session:
            rows = session.execute(
                select(AttendanceCaseModel)
                .order_by(AttendanceCaseModel.created_at.desc())
                .limit(limit)
            ).scalars().all()
            return list(rows)

    def exists_for_employee(self, employee_name: str) -> bool:
        with SessionLocal() as session:
            row = session.execute(
                select(AttendanceCaseModel.id)
                .where(AttendanceCaseModel.employee_name == employee_name)
                .limit(1)
            ).first()
            return row is not None

    def list_for_employee_user(self, user_id: str, limit: int = 20) -> List[AttendanceCaseModel]:
        with SessionLocal() as session:
            rows = session.execute(
                select(AttendanceCaseModel)
                .where(AttendanceCaseModel.employee_user_id == user_id)
                .order_by(AttendanceCaseModel.created_at.desc())
                .limit(limit)
            ).scalars().all()
            return list(rows)

    def list_pending_reason_for_employee(self, user_id: str, limit: int = 20) -> List[AttendanceCaseModel]:
        with SessionLocal() as session:
            rows = session.execute(
                select(AttendanceCaseModel)
                .where(AttendanceCaseModel.employee_user_id == user_id)
                .where(AttendanceCaseModel.status == AttendanceCaseStatus.AWAITING_EMPLOYEE_REASON.value)
                .order_by(AttendanceCaseModel.created_at.desc())
                .limit(limit)
            ).scalars().all()
            return list(rows)

    def list_for_manager_user(self, manager_user_id: str, limit: int = 20) -> List[AttendanceCaseModel]:
        with SessionLocal() as session:
            rows = session.execute(
                select(AttendanceCaseModel)
                .where(AttendanceCaseModel.manager_user_id == manager_user_id)
                .order_by(AttendanceCaseModel.created_at.desc())
                .limit(limit)
            ).scalars().all()
            return list(rows)

    def list_for_manager_user_by_status(
        self,
        manager_user_id: str,
        statuses: List[str],
        limit: int = 20,
    ) -> List[AttendanceCaseModel]:
        with SessionLocal() as session:
            rows = session.execute(
                select(AttendanceCaseModel)
                .where(AttendanceCaseModel.manager_user_id == manager_user_id)
                .where(AttendanceCaseModel.status.in_(statuses))
                .order_by(AttendanceCaseModel.created_at.desc())
                .limit(limit)
            ).scalars().all()
            return list(rows)

    def list_for_department_name(
        self,
        department_name: str,
        statuses: Optional[List[str]] = None,
        limit: int = 20,
    ) -> List[AttendanceCaseModel]:
        with SessionLocal() as session:
            query = select(AttendanceCaseModel).where(AttendanceCaseModel.department_name == department_name)
            if statuses:
                query = query.where(AttendanceCaseModel.status.in_(statuses))
            rows = session.execute(
                query.order_by(AttendanceCaseModel.created_at.desc()).limit(limit)
            ).scalars().all()
            return list(rows)

    def count_for_manager_user(self, manager_user_id: str, statuses: Optional[List[str]] = None) -> int:
        with SessionLocal() as session:
            query = select(AttendanceCaseModel.id).where(AttendanceCaseModel.manager_user_id == manager_user_id)
            if statuses:
                query = query.where(AttendanceCaseModel.status.in_(statuses))
            return len(session.execute(query).all())

    def get(self, case_id: int) -> Optional[AttendanceCaseModel]:
        with SessionLocal() as session:
            return session.get(AttendanceCaseModel, case_id)

    def update_reason_and_status(self, case_id: int, employee_reason: str, status: str) -> Optional[AttendanceCaseModel]:
        with SessionLocal() as session:
            case = session.get(AttendanceCaseModel, case_id)
            if case is None:
                return None
            case.employee_reason = employee_reason
            case.status = status
            session.commit()
            session.refresh(case)
            return case

    def update_manager(self, case_id: int, manager_user_id: str, manager_name: str) -> Optional[AttendanceCaseModel]:
        with SessionLocal() as session:
            case = session.get(AttendanceCaseModel, case_id)
            if case is None:
                return None
            case.manager_user_id = manager_user_id
            case.manager_name = manager_name
            session.commit()
            session.refresh(case)
            return case

    def update_status(self, case_id: int, status: str) -> Optional[AttendanceCaseModel]:
        with SessionLocal() as session:
            case = session.get(AttendanceCaseModel, case_id)
            if case is None:
                return None
            case.status = status
            session.commit()
            session.refresh(case)
            return case
