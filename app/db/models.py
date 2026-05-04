from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class DialogStateModel(Base):
    __tablename__ = "dialog_states"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    flow: Mapped[str] = mapped_column(String(100), index=True)
    step: Mapped[str] = mapped_column(String(100))
    data_json: Mapped[str] = mapped_column(Text, default="{}")
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class SubstitutionDraftModel(Base):
    __tablename__ = "substitution_drafts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    created_by_user_id: Mapped[str] = mapped_column(String(255), index=True)
    role: Mapped[str] = mapped_column(String(100), index=True)
    target_manager: Mapped[str] = mapped_column(String(255))
    replacement_user: Mapped[str] = mapped_column(String(255))
    reason: Mapped[str] = mapped_column(String(100))
    date_from: Mapped[str] = mapped_column(String(20))
    date_to: Mapped[str] = mapped_column(String(20))
    scope: Mapped[str] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(50), default="draft", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


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
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class ApprovalModel(Base):
    __tablename__ = "approvals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    case_id: Mapped[int] = mapped_column(Integer, index=True)
    manager_user_id: Mapped[str] = mapped_column(String(255), index=True)
    manager_name: Mapped[str] = mapped_column(String(255), index=True)
    status: Mapped[str] = mapped_column(String(50), index=True)
    comment: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class UserRoleOverrideModel(Base):
    __tablename__ = "user_role_overrides"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    role: Mapped[str] = mapped_column(String(100), index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class SkudImportModel(Base):
    __tablename__ = "skud_imports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    filename: Mapped[str] = mapped_column(String(255), index=True)
    created_by_user_id: Mapped[str] = mapped_column(String(255), default="", index=True)
    status: Mapped[str] = mapped_column(String(50), index=True)
    total_rows: Mapped[int] = mapped_column(Integer, default=0)
    created_cases: Mapped[int] = mapped_column(Integer, default=0)
    error_rows: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
