from __future__ import annotations

from typing import List

from sqlalchemy import select

from app.db.base import SessionLocal
from app.db.models import AttendanceCaseModel


class AttendanceCaseRepository:
    def create_demo_case(
        self,
        *,
        employee_name: str,
        department_name: str,
        case_type: str,
        status: str,
        event_date: str,
        planned_start: str,
        actual_start: str,
        delay_minutes: int,
        employee_reason: str,
    ) -> int:
        with SessionLocal() as session:
            case = AttendanceCaseModel(
                employee_name=employee_name,
                department_name=department_name,
                case_type=case_type,
                status=status,
                event_date=event_date,
                planned_start=planned_start,
                actual_start=actual_start,
                delay_minutes=delay_minutes,
                employee_reason=employee_reason,
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
