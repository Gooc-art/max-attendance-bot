from __future__ import annotations

from uuid import uuid4

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.db.base import SessionLocal
from app.db.models import EmployeeDirectoryModel
import app.repositories.employee_directory_repository as employee_directory_repository
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


def test_deactivate_missing_marks_only_absent_active_rows(tmp_path, monkeypatch) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'employee_directory.db'}", future=True)
    Base.metadata.create_all(bind=engine)
    monkeypatch.setattr(
        employee_directory_repository,
        "SessionLocal",
        sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True),
    )
    repo = EmployeeDirectoryRepository()
    keep_id = f"test-keep-{uuid4().hex}"
    missing_id = f"test-missing-{uuid4().hex}"

    repo.upsert_many([
        {"employee_name": "Оставить", "employee_user_id": keep_id, "role": "employee"},
        {"employee_name": "Убрать", "employee_user_id": missing_id, "role": "employee"},
    ])

    assert repo.deactivate_missing({keep_id}) == 1
    assert repo.get_by_user_id(keep_id).is_active is True
    assert repo.get_by_user_id(missing_id).is_active is False
