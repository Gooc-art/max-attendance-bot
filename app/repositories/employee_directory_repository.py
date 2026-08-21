from __future__ import annotations

from typing import Dict, List, Optional

from sqlalchemy import select

from app.db.base import SessionLocal
from app.db.models import EmployeeDirectoryModel
from app.integrations.google_sheets.directory import GoogleSheetsDirectoryService


class EmployeeDirectoryRepository:
    def upsert_many(self, rows: List[Dict[str, str]]) -> int:
        count = 0
        with SessionLocal() as session:
            for data in rows:
                employee_user_id = data.get("employee_user_id", "").strip()
                if not employee_user_id:
                    continue
                row = session.execute(
                    select(EmployeeDirectoryModel).where(EmployeeDirectoryModel.employee_user_id == employee_user_id)
                ).scalar_one_or_none()
                if row is None:
                    row = EmployeeDirectoryModel(employee_user_id=employee_user_id)
                    session.add(row)
                row.employee_name = data.get("employee_name", "").strip()
                row.manager_name = data.get("manager_name", "").strip()
                row.manager_user_id = data.get("manager_user_id", "").strip()
                row.department_name = data.get("department_name", "").strip()
                row.office = data.get("office", "").strip()
                row.schedule_name = data.get("schedule_name", "").strip()
                row.schedule_id = data.get("schedule_id", "").strip()
                row.role = GoogleSheetsDirectoryService.normalize_role_value(data.get("role", "employee"))
                row.is_active = data.get("is_active", "1").strip().lower() in {"1", "true", "yes", "on", "да"}
                count += 1
            session.commit()
        return count

    def deactivate_missing(self, active_user_ids: set[str]) -> int:
        if not active_user_ids:
            return 0
        count = 0
        with SessionLocal() as session:
            rows = session.execute(
                select(EmployeeDirectoryModel).where(EmployeeDirectoryModel.is_active.is_(True))
            ).scalars().all()
            for row in rows:
                if row.employee_user_id not in active_user_ids:
                    row.is_active = False
                    count += 1
            session.commit()
        return count

    def list_recent(self, limit: int = 50) -> List[EmployeeDirectoryModel]:
        with SessionLocal() as session:
            rows = session.execute(
                select(EmployeeDirectoryModel)
                .order_by(EmployeeDirectoryModel.updated_at.desc())
                .limit(limit)
            ).scalars().all()
            return list(rows)

    def get_by_user_id(self, user_id: str) -> Optional[EmployeeDirectoryModel]:
        with SessionLocal() as session:
            return session.execute(
                select(EmployeeDirectoryModel).where(EmployeeDirectoryModel.employee_user_id == user_id).limit(1)
            ).scalar_one_or_none()

    def get_by_employee_name(self, employee_name: str) -> Optional[EmployeeDirectoryModel]:
        with SessionLocal() as session:
            return session.execute(
                select(EmployeeDirectoryModel)
                .where(EmployeeDirectoryModel.employee_name == employee_name)
                .where(EmployeeDirectoryModel.is_active.is_(True))
                .order_by(EmployeeDirectoryModel.updated_at.desc())
                .limit(1)
            ).scalar_one_or_none()

    def get_by_manager_user_id(self, manager_user_id: str) -> List[EmployeeDirectoryModel]:
        with SessionLocal() as session:
            rows = session.execute(
                select(EmployeeDirectoryModel)
                .where(EmployeeDirectoryModel.manager_user_id == manager_user_id)
                .where(EmployeeDirectoryModel.is_active.is_(True))
                .order_by(EmployeeDirectoryModel.employee_name.asc())
            ).scalars().all()
            return list(rows)

    def list_by_department_names(self, department_names: List[str]) -> List[EmployeeDirectoryModel]:
        departments = [name for name in {str(item).strip() for item in department_names} if name]
        if not departments:
            return []
        with SessionLocal() as session:
            rows = session.execute(
                select(EmployeeDirectoryModel)
                .where(EmployeeDirectoryModel.department_name.in_(departments))
                .where(EmployeeDirectoryModel.is_active.is_(True))
                .order_by(EmployeeDirectoryModel.employee_name.asc())
            ).scalars().all()
            return list(rows)
