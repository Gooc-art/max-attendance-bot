from __future__ import annotations

from pathlib import Path

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import declarative_base, sessionmaker

from app.config import get_settings


Base = declarative_base()


def _ensure_sqlite_directory(database_url: str) -> None:
    sqlite_prefix = "sqlite:///"
    if not database_url.startswith(sqlite_prefix):
        return
    db_path = database_url.replace(sqlite_prefix, "", 1)
    if not db_path or db_path == ":memory:":
        return
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)


settings = get_settings()
_ensure_sqlite_directory(settings.database_url)

engine = create_engine(
    settings.database_url,
    future=True,
    connect_args={"check_same_thread": False} if settings.database_url.startswith("sqlite") else {},
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


def init_db() -> None:
    from app.db import models  # noqa: F401

    Base.metadata.create_all(bind=engine)
    _ensure_runtime_schema()


def _ensure_runtime_schema() -> None:
    if not settings.database_url.startswith("sqlite"):
        return

    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    if "runtime_markers" not in tables:
        RuntimeMarkerModel = Base.metadata.tables.get("runtime_markers")
        if RuntimeMarkerModel is not None:
            RuntimeMarkerModel.create(bind=engine, checkfirst=True)
    if "attendance_cases" not in tables:
        return

    existing_columns = {column["name"] for column in inspector.get_columns("attendance_cases")}
    required_columns = {
        "employee_user_id": "ALTER TABLE attendance_cases ADD COLUMN employee_user_id VARCHAR(255) DEFAULT ''",
        "manager_user_id": "ALTER TABLE attendance_cases ADD COLUMN manager_user_id VARCHAR(255) DEFAULT ''",
        "manager_name": "ALTER TABLE attendance_cases ADD COLUMN manager_name VARCHAR(255) DEFAULT ''",
        "source": "ALTER TABLE attendance_cases ADD COLUMN source VARCHAR(50) DEFAULT 'manual'",
        "updated_at": "ALTER TABLE attendance_cases ADD COLUMN updated_at DATETIME",
    }
    skud_import_required_columns = {
        "period_start": "ALTER TABLE skud_imports ADD COLUMN period_start VARCHAR(20) DEFAULT ''",
        "period_end": "ALTER TABLE skud_imports ADD COLUMN period_end VARCHAR(20) DEFAULT ''",
        "unique_employees": "ALTER TABLE skud_imports ADD COLUMN unique_employees INTEGER DEFAULT 0",
        "samples_text": "ALTER TABLE skud_imports ADD COLUMN samples_text TEXT DEFAULT ''",
    }
    substitution_required_columns = {
        "target_user_id": "ALTER TABLE substitution_drafts ADD COLUMN target_user_id VARCHAR(255) DEFAULT ''",
        "replacement_user_id": "ALTER TABLE substitution_drafts ADD COLUMN replacement_user_id VARCHAR(255) DEFAULT ''",
        "departments_json": "ALTER TABLE substitution_drafts ADD COLUMN departments_json TEXT DEFAULT '[]'",
    }
    employee_directory_required_columns = {
        "office": "ALTER TABLE employee_directory ADD COLUMN office VARCHAR(100) DEFAULT ''",
        "schedule_name": "ALTER TABLE employee_directory ADD COLUMN schedule_name VARCHAR(255) DEFAULT ''",
        "schedule_id": "ALTER TABLE employee_directory ADD COLUMN schedule_id VARCHAR(100) DEFAULT ''",
    }
    attendance_day_record_required_columns = {
        "raw_events_json": "ALTER TABLE attendance_day_records ADD COLUMN raw_events_json TEXT DEFAULT '[]'",
        "presence_intervals_json": "ALTER TABLE attendance_day_records ADD COLUMN presence_intervals_json TEXT DEFAULT '[]'",
        "worked_minutes": "ALTER TABLE attendance_day_records ADD COLUMN worked_minutes INTEGER DEFAULT 0",
        "planned_minutes": "ALTER TABLE attendance_day_records ADD COLUMN planned_minutes INTEGER DEFAULT 0",
        "lunch_minutes": "ALTER TABLE attendance_day_records ADD COLUMN lunch_minutes INTEGER DEFAULT 0",
        "balance_minutes": "ALTER TABLE attendance_day_records ADD COLUMN balance_minutes INTEGER DEFAULT 0",
        "late_compensated": "ALTER TABLE attendance_day_records ADD COLUMN late_compensated BOOLEAN DEFAULT 0",
    }
    with engine.begin() as connection:
        for column_name, ddl in required_columns.items():
            if column_name not in existing_columns:
                connection.execute(text(ddl))
        if "attendance_day_records" in tables:
            attendance_day_record_columns = {column["name"] for column in inspector.get_columns("attendance_day_records")}
            for column_name, ddl in attendance_day_record_required_columns.items():
                if column_name not in attendance_day_record_columns:
                    connection.execute(text(ddl))
        if "skud_imports" in tables:
            skud_columns = {column["name"] for column in inspector.get_columns("skud_imports")}
            for column_name, ddl in skud_import_required_columns.items():
                if column_name not in skud_columns:
                    connection.execute(text(ddl))
        if "substitution_drafts" in tables:
            substitution_columns = {column["name"] for column in inspector.get_columns("substitution_drafts")}
            for column_name, ddl in substitution_required_columns.items():
                if column_name not in substitution_columns:
                    connection.execute(text(ddl))
        if "employee_directory" in tables:
            employee_directory_columns = {column["name"] for column in inspector.get_columns("employee_directory")}
            for column_name, ddl in employee_directory_required_columns.items():
                if column_name not in employee_directory_columns:
                    connection.execute(text(ddl))
