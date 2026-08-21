from __future__ import annotations

from uuid import uuid4

from app.db.base import SessionLocal
from app.db.models import EmployeeDirectoryModel
from app.repositories.employee_directory_repository import EmployeeDirectoryRepository


def test_upsert_many_normalizes_role() -> None:
    repo = EmployeeDirectoryRepository()
    user_id = f"test-user-{uuid4().hex}"

    try:
        repo.upsert_many([
            {
                "employee_name": "Тестовый Зам",
                "employee_user_id": user_id,
                "role": "зам.руководителя",
            }
        ])

        row = repo.get_by_user_id(user_id)
        assert row is not None
        assert row.role == "manager"
    finally:
        with SessionLocal() as session:
            row = session.query(EmployeeDirectoryModel).filter(EmployeeDirectoryModel.employee_user_id == user_id).one_or_none()
            if row is not None:
                session.delete(row)
                session.commit()
