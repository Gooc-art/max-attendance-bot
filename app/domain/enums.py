from __future__ import annotations

from enum import Enum


class Role(str, Enum):
    EMPLOYEE = "employee"
    MANAGER = "manager"
    SECURITY = "security"
    HR = "hr"
    ADMIN = "admin"
    TOP_MANAGER = "top_manager"


class DialogFlow(str, Enum):
    SUBSTITUTION = "substitution"
    ATTENDANCE_REASON = "attendance_reason"


class SubstitutionScope(str, Enum):
    APPROVALS = "Только согласования"
    REPORTS = "Только отчеты"
    BOTH = "Согласования и отчеты"


class SubstitutionReason(str, Enum):
    VACATION = "Отпуск"
    SICK_LEAVE = "Больничный"
    BUSINESS_TRIP = "Командировка"
    OTHER = "Иное"


class AttendanceCaseType(str, Enum):
    LATE = "late"
    ABSENT = "absent"


class AttendanceCaseStatus(str, Enum):
    NEW = "new"
    AWAITING_EMPLOYEE_REASON = "awaiting_employee_reason"
    AWAITING_MANAGER_APPROVAL = "awaiting_manager_approval"
    JUSTIFIED = "justified"
    UNJUSTIFIED = "unjustified"
    CLOSED = "closed"


class ApprovalStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class AttendanceReasonCode(str, Enum):
    SICK_LEAVE = "sick_leave"
    BUSINESS_TRIP = "business_trip"
    REMOTE_DAY = "remote_day"
    APPROVED_LATE = "approved_late"
    PERSONAL_REASON = "personal_reason"
    OTHER = "other"
