from __future__ import annotations

from datetime import UTC, datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


def utc_now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


class DialogStateModel(Base):
    __tablename__ = "dialog_states"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    flow: Mapped[str] = mapped_column(String(100), index=True)
    step: Mapped[str] = mapped_column(String(100))
    data_json: Mapped[str] = mapped_column(Text, default="{}")
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, onupdate=utc_now)


class BotMessageCursorModel(Base):
    __tablename__ = "bot_message_cursors"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    conversation_key: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    chat_id: Mapped[str] = mapped_column(String(255), default="", index=True)
    user_id: Mapped[str] = mapped_column(String(255), default="", index=True)
    message_id: Mapped[str] = mapped_column(String(255))
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, onupdate=utc_now)


class RuntimeMarkerModel(Base):
    __tablename__ = "runtime_markers"
    __table_args__ = (
        UniqueConstraint("marker_key", name="uq_runtime_markers_marker_key"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    marker_key: Mapped[str] = mapped_column(String(500), unique=True, index=True)
    marker_type: Mapped[str] = mapped_column(String(50), index=True)
    status: Mapped[str] = mapped_column(String(50), default="processing", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, onupdate=utc_now)
    expires_at: Mapped[datetime] = mapped_column(DateTime, index=True)


class SubstitutionDraftModel(Base):
    __tablename__ = "substitution_drafts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    created_by_user_id: Mapped[str] = mapped_column(String(255), index=True)
    role: Mapped[str] = mapped_column(String(100), index=True)
    target_manager: Mapped[str] = mapped_column(String(255))
    target_user_id: Mapped[str] = mapped_column(String(255), default="", index=True)
    replacement_user: Mapped[str] = mapped_column(String(255))
    replacement_user_id: Mapped[str] = mapped_column(String(255), default="", index=True)
    reason: Mapped[str] = mapped_column(String(100))
    date_from: Mapped[str] = mapped_column(String(20))
    date_to: Mapped[str] = mapped_column(String(20))
    scope: Mapped[str] = mapped_column(String(100))
    departments_json: Mapped[str] = mapped_column(Text, default="[]")
    status: Mapped[str] = mapped_column(String(50), default="pending_replacement_approval", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)


class AttendanceCaseModel(Base):
    __tablename__ = "attendance_cases"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    employee_user_id: Mapped[str] = mapped_column(String(255), default="", index=True)
    employee_name: Mapped[str] = mapped_column(String(255), index=True)
    department_name: Mapped[str] = mapped_column(String(255), index=True)
    manager_user_id: Mapped[str] = mapped_column(String(255), default="", index=True)
    manager_name: Mapped[str] = mapped_column(String(255), default="")
    case_type: Mapped[str] = mapped_column(String(50), index=True)
    status: Mapped[str] = mapped_column(String(50), index=True)
    event_date: Mapped[str] = mapped_column(String(20), index=True)
    planned_start: Mapped[str] = mapped_column(String(20))
    actual_start: Mapped[str] = mapped_column(String(20))
    delay_minutes: Mapped[int] = mapped_column(Integer, default=0)
    employee_reason: Mapped[str] = mapped_column(Text, default="")
    source: Mapped[str] = mapped_column(String(50), default="manual", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, onupdate=utc_now)


class AttendanceDayRecordModel(Base):
    __tablename__ = "attendance_day_records"
    __table_args__ = (
        UniqueConstraint("record_key", name="uq_attendance_day_records_record_key"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    record_key: Mapped[str] = mapped_column(String(300), unique=True, index=True)
    employee_user_id: Mapped[str] = mapped_column(String(255), default="", index=True)
    employee_name: Mapped[str] = mapped_column(String(255), index=True)
    department_name: Mapped[str] = mapped_column(String(255), index=True)
    manager_user_id: Mapped[str] = mapped_column(String(255), default="", index=True)
    manager_name: Mapped[str] = mapped_column(String(255), default="")
    schedule_name: Mapped[str] = mapped_column(String(255), default="")
    schedule_id: Mapped[str] = mapped_column(String(255), default="")
    event_date: Mapped[str] = mapped_column(String(20), index=True)
    planned_start: Mapped[str] = mapped_column(String(20), default="")
    planned_end: Mapped[str] = mapped_column(String(20), default="")
    raw_events_json: Mapped[str] = mapped_column(Text, default="[]")
    presence_intervals_json: Mapped[str] = mapped_column(Text, default="[]")
    first_entry_time: Mapped[str] = mapped_column(String(20), default="")
    arrival_status: Mapped[str] = mapped_column(String(20), default="")
    arrival_delta_minutes: Mapped[int] = mapped_column(Integer, default=0)
    last_exit_time: Mapped[str] = mapped_column(String(20), default="")
    departure_status: Mapped[str] = mapped_column(String(20), default="")
    departure_delta_minutes: Mapped[int] = mapped_column(Integer, default=0)
    worked_minutes: Mapped[int] = mapped_column(Integer, default=0)
    planned_minutes: Mapped[int] = mapped_column(Integer, default=0)
    lunch_minutes: Mapped[int] = mapped_column(Integer, default=0)
    balance_minutes: Mapped[int] = mapped_column(Integer, default=0)
    late_compensated: Mapped[bool] = mapped_column(Boolean, default=False)
    total_passes: Mapped[int] = mapped_column(Integer, default=0)
    source: Mapped[str] = mapped_column(String(50), default="skud_report", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, onupdate=utc_now)


class ApprovalModel(Base):
    __tablename__ = "approvals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    case_id: Mapped[int] = mapped_column(Integer, index=True)
    manager_user_id: Mapped[str] = mapped_column(String(255), index=True)
    manager_name: Mapped[str] = mapped_column(String(255), index=True)
    status: Mapped[str] = mapped_column(String(50), index=True)
    comment: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)


class UserRoleOverrideModel(Base):
    __tablename__ = "user_role_overrides"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    role: Mapped[str] = mapped_column(String(100), index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, onupdate=utc_now)


class UserBotActivityModel(Base):
    __tablename__ = "user_bot_activity"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(255), default="")
    role: Mapped[str] = mapped_column(String(100), default="", index=True)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, onupdate=utc_now)
    first_start_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True, default=None)
    last_start_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True, default=None)
    start_count: Mapped[int] = mapped_column(Integer, default=0)
    interaction_count: Mapped[int] = mapped_column(Integer, default=0)
    device_platform: Mapped[str] = mapped_column(String(50), default="")
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, onupdate=utc_now)


class EmployeeDirectoryModel(Base):
    __tablename__ = "employee_directory"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    employee_name: Mapped[str] = mapped_column(String(255), index=True)
    employee_user_id: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    manager_name: Mapped[str] = mapped_column(String(255), default="")
    manager_user_id: Mapped[str] = mapped_column(String(255), default="", index=True)
    department_name: Mapped[str] = mapped_column(String(255), default="", index=True)
    office: Mapped[str] = mapped_column(String(100), default="")
    schedule_name: Mapped[str] = mapped_column(String(255), default="")
    schedule_id: Mapped[str] = mapped_column(String(100), default="", index=True)
    role: Mapped[str] = mapped_column(String(100), default="employee", index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, onupdate=utc_now)


class SkudImportModel(Base):
    __tablename__ = "skud_imports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    filename: Mapped[str] = mapped_column(String(255), index=True)
    created_by_user_id: Mapped[str] = mapped_column(String(255), default="", index=True)
    status: Mapped[str] = mapped_column(String(50), index=True)
    period_start: Mapped[str] = mapped_column(String(20), default="")
    period_end: Mapped[str] = mapped_column(String(20), default="")
    unique_employees: Mapped[int] = mapped_column(Integer, default=0)
    total_rows: Mapped[int] = mapped_column(Integer, default=0)
    created_cases: Mapped[int] = mapped_column(Integer, default=0)
    error_rows: Mapped[int] = mapped_column(Integer, default=0)
    samples_text: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)


class ReportModel(Base):
    __tablename__ = "reports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    token: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    report_type: Mapped[str] = mapped_column(String(50), index=True)
    user_id: Mapped[str] = mapped_column(String(255), index=True)
    role: Mapped[str] = mapped_column(String(100), index=True)
    title: Mapped[str] = mapped_column(String(255))
    period_start: Mapped[str] = mapped_column(String(20), default="")
    period_end: Mapped[str] = mapped_column(String(20), default="")
    file_name: Mapped[str] = mapped_column(String(255))
    file_path: Mapped[str] = mapped_column(String(500))
    summary_text: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(50), default="ready", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
