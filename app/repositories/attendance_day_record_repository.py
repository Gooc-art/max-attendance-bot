from __future__ import annotations

from typing import Dict, List, Optional

from sqlalchemy import select

from app.db.base import SessionLocal
from app.db.models import AttendanceDayRecordModel


class AttendanceDayRecordRepository:
    @staticmethod
    def _apply_period(query, *, date_from: str = "", date_to: str = ""):
        if date_from:
            query = query.where(AttendanceDayRecordModel.event_date >= date_from)
        if date_to:
            query = query.where(AttendanceDayRecordModel.event_date <= date_to)
        return query

    def upsert_many(self, rows: List[Dict[str, object]]) -> int:
        count = 0
        keyed_rows = []
        record_keys: set[str] = set()
        for data in rows:
            record_key = str(data.get("record_key", "")).strip()
            if not record_key:
                continue
            keyed_rows.append((record_key, data))
            record_keys.add(record_key)

        if not keyed_rows:
            return 0

        with SessionLocal() as session:
            existing_by_key = {
                row.record_key: row
                for row in session.execute(
                    select(AttendanceDayRecordModel).where(AttendanceDayRecordModel.record_key.in_(record_keys))
                ).scalars()
            }
            for record_key, data in keyed_rows:
                row = existing_by_key.get(record_key)
                if row is None:
                    row = AttendanceDayRecordModel(record_key=record_key)
                    session.add(row)
                    existing_by_key[record_key] = row
                row.employee_user_id = str(data.get("employee_user_id", "")).strip()
                row.employee_name = str(data.get("employee_name", "")).strip()
                row.department_name = str(data.get("department_name", "")).strip()
                row.manager_user_id = str(data.get("manager_user_id", "")).strip()
                row.manager_name = str(data.get("manager_name", "")).strip()
                row.schedule_name = str(data.get("schedule_name", "")).strip()
                row.schedule_id = str(data.get("schedule_id", "")).strip()
                row.event_date = str(data.get("event_date", "")).strip()
                row.planned_start = str(data.get("planned_start", "")).strip()
                row.planned_end = str(data.get("planned_end", "")).strip()
                row.raw_events_json = str(data.get("raw_events_json", "[]")).strip() or "[]"
                row.presence_intervals_json = str(data.get("presence_intervals_json", "[]")).strip() or "[]"
                row.first_entry_time = str(data.get("first_entry_time", "")).strip()
                row.arrival_status = str(data.get("arrival_status", "")).strip()
                row.arrival_delta_minutes = int(data.get("arrival_delta_minutes", 0) or 0)
                row.last_exit_time = str(data.get("last_exit_time", "")).strip()
                row.departure_status = str(data.get("departure_status", "")).strip()
                row.departure_delta_minutes = int(data.get("departure_delta_minutes", 0) or 0)
                row.worked_minutes = int(data.get("worked_minutes", 0) or 0)
                row.planned_minutes = int(data.get("planned_minutes", 0) or 0)
                row.lunch_minutes = int(data.get("lunch_minutes", 0) or 0)
                row.balance_minutes = int(data.get("balance_minutes", 0) or 0)
                row.late_compensated = bool(data.get("late_compensated", False))
                row.total_passes = int(data.get("total_passes", 0) or 0)
                row.source = str(data.get("source", "skud_report")).strip() or "skud_report"
                count += 1
            session.commit()
        return count

    def list_all(self, limit: int = 5000, date_from: str = "", date_to: str = "") -> List[AttendanceDayRecordModel]:
        with SessionLocal() as session:
            query = self._apply_period(select(AttendanceDayRecordModel), date_from=date_from, date_to=date_to)
            rows = session.execute(
                query.order_by(AttendanceDayRecordModel.event_date.desc(), AttendanceDayRecordModel.employee_name.asc())
                .limit(limit)
            ).scalars().all()
            return list(rows)

    def list_for_manager_user(
        self,
        manager_user_id: str,
        limit: int = 500,
        date_from: str = "",
        date_to: str = "",
    ) -> List[AttendanceDayRecordModel]:
        with SessionLocal() as session:
            query = self._apply_period(
                select(AttendanceDayRecordModel).where(AttendanceDayRecordModel.manager_user_id == manager_user_id),
                date_from=date_from,
                date_to=date_to,
            )
            rows = session.execute(
                query.order_by(AttendanceDayRecordModel.event_date.desc(), AttendanceDayRecordModel.employee_name.asc())
                .limit(limit)
            ).scalars().all()
            return list(rows)

    def list_for_department_names(
        self,
        department_names: List[str],
        limit: int = 500,
        date_from: str = "",
        date_to: str = "",
    ) -> List[AttendanceDayRecordModel]:
        departments = [name for name in {str(item).strip() for item in department_names} if name]
        if not departments:
            return []
        with SessionLocal() as session:
            query = self._apply_period(
                select(AttendanceDayRecordModel).where(AttendanceDayRecordModel.department_name.in_(departments)),
                date_from=date_from,
                date_to=date_to,
            )
            rows = session.execute(
                query.order_by(AttendanceDayRecordModel.event_date.desc(), AttendanceDayRecordModel.employee_name.asc())
                .limit(limit)
            ).scalars().all()
            return list(rows)

    def list_for_employee_user(self, user_id: str, limit: int = 200) -> List[AttendanceDayRecordModel]:
        with SessionLocal() as session:
            rows = session.execute(
                select(AttendanceDayRecordModel)
                .where(AttendanceDayRecordModel.employee_user_id == user_id)
                .order_by(AttendanceDayRecordModel.event_date.desc())
                .limit(limit)
            ).scalars().all()
            return list(rows)

    def get_by_record_key(self, record_key: str) -> Optional[AttendanceDayRecordModel]:
        with SessionLocal() as session:
            return session.execute(
                select(AttendanceDayRecordModel).where(AttendanceDayRecordModel.record_key == record_key).limit(1)
            ).scalar_one_or_none()
