from __future__ import annotations

from typing import List, Optional

from sqlalchemy import select

from app.db.base import SessionLocal
from app.db.models import AttendanceCaseModel
from app.domain.enums import AttendanceCaseStatus


class AttendanceCaseRepository:
    @staticmethod
    def _apply_period(query, *, date_from: str = "", date_to: str = ""):
        if date_from:
            query = query.where(AttendanceCaseModel.event_date >= date_from)
        if date_to:
            query = query.where(AttendanceCaseModel.event_date <= date_to)
        return query

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

    def list_all(self, limit: int = 5000, date_from: str = "", date_to: str = "") -> List[AttendanceCaseModel]:
        with SessionLocal() as session:
            query = self._apply_period(select(AttendanceCaseModel), date_from=date_from, date_to=date_to)
            rows = session.execute(
                query.order_by(AttendanceCaseModel.created_at.desc())
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

    def list_for_employee_names(self, employee_names: List[str], limit: int = 20) -> List[AttendanceCaseModel]:
        names = [name for name in {str(item).strip() for item in employee_names} if name]
        if not names:
            return []
        with SessionLocal() as session:
            rows = session.execute(
                select(AttendanceCaseModel)
                .where(AttendanceCaseModel.employee_name.in_(names))
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

    def list_pending_reason_for_employee_names(self, employee_names: List[str], limit: int = 20) -> List[AttendanceCaseModel]:
        names = [name for name in {str(item).strip() for item in employee_names} if name]
        if not names:
            return []
        with SessionLocal() as session:
            rows = session.execute(
                select(AttendanceCaseModel)
                .where(AttendanceCaseModel.employee_name.in_(names))
                .where(AttendanceCaseModel.status == AttendanceCaseStatus.AWAITING_EMPLOYEE_REASON.value)
                .order_by(AttendanceCaseModel.created_at.desc())
                .limit(limit)
            ).scalars().all()
            return list(rows)

    def list_for_manager_user(
        self,
        manager_user_id: str,
        limit: int = 20,
        date_from: str = "",
        date_to: str = "",
    ) -> List[AttendanceCaseModel]:
        with SessionLocal() as session:
            query = self._apply_period(
                select(AttendanceCaseModel).where(AttendanceCaseModel.manager_user_id == manager_user_id),
                date_from=date_from,
                date_to=date_to,
            )
            rows = session.execute(
                query.order_by(AttendanceCaseModel.created_at.desc())
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

    def list_for_department_names(
        self,
        department_names: List[str],
        statuses: Optional[List[str]] = None,
        limit: int = 500,
        date_from: str = "",
        date_to: str = "",
    ) -> List[AttendanceCaseModel]:
        departments = [name for name in {str(item).strip() for item in department_names} if name]
        if not departments:
            return []
        with SessionLocal() as session:
            query = self._apply_period(
                select(AttendanceCaseModel).where(AttendanceCaseModel.department_name.in_(departments)),
                date_from=date_from,
                date_to=date_to,
            )
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

    def find_matching_late_notice(
        self,
        *,
        employee_user_id: str,
        event_date: str,
        actual_start: str,
        max_diff_minutes: int = 120,
    ) -> Optional[AttendanceCaseModel]:
        if not employee_user_id or not event_date or not actual_start:
            return None

        def to_minutes(value: str) -> Optional[int]:
            try:
                hh, mm = str(value or "").split(":", 1)
                return int(hh) * 60 + int(mm)
            except Exception:
                return None

        actual_minutes = to_minutes(actual_start)
        with SessionLocal() as session:
            rows = session.execute(
                select(AttendanceCaseModel)
                .where(AttendanceCaseModel.employee_user_id == employee_user_id)
                .where(AttendanceCaseModel.event_date == event_date)
                .where(AttendanceCaseModel.source == "late_notice")
                .order_by(AttendanceCaseModel.created_at.desc())
            ).scalars().all()

            if actual_minutes is None:
                return rows[0] if rows else None

            best_row: Optional[AttendanceCaseModel] = None
            best_diff: Optional[int] = None
            for row in rows:
                row_minutes = to_minutes(row.actual_start)
                if row_minutes is None:
                    continue
                diff = abs(actual_minutes - row_minutes)
                if diff > max_diff_minutes:
                    continue
                if best_diff is None or diff < best_diff:
                    best_diff = diff
                    best_row = row
            return best_row or (rows[0] if rows else None)

    def update_skud_match(
        self,
        case_id: int,
        *,
        planned_start: str,
        actual_start: str,
        delay_minutes: int,
    ) -> Optional[AttendanceCaseModel]:
        with SessionLocal() as session:
            case = session.get(AttendanceCaseModel, case_id)
            if case is None:
                return None
            case.planned_start = planned_start
            case.actual_start = actual_start
            case.delay_minutes = delay_minutes
            if case.source == "late_notice":
                case.source = "late_notice_matched"
            session.commit()
            session.refresh(case)
            return case
