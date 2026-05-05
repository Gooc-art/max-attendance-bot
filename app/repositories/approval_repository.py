from __future__ import annotations

from datetime import datetime, timedelta
from typing import List, Optional, Tuple

from sqlalchemy import select

from app.db.base import SessionLocal
from app.db.models import ApprovalModel, AttendanceCaseModel
from app.domain.enums import ApprovalStatus, AttendanceCaseStatus


class ApprovalRepository:
    def list_pending_for_manager(self, manager_user_id: str) -> List[Tuple[ApprovalModel, AttendanceCaseModel]]:
        with SessionLocal() as session:
            rows = session.execute(
                select(ApprovalModel, AttendanceCaseModel)
                .join(AttendanceCaseModel, AttendanceCaseModel.id == ApprovalModel.case_id)
                .where(ApprovalModel.manager_user_id == manager_user_id)
                .where(ApprovalModel.status == ApprovalStatus.PENDING.value)
                .order_by(ApprovalModel.created_at.desc())
            ).all()
            return list(rows)

    def list_for_manager(
        self,
        manager_user_id: str,
        statuses: Optional[List[str]] = None,
        limit: int = 20,
    ) -> List[Tuple[ApprovalModel, AttendanceCaseModel]]:
        with SessionLocal() as session:
            query = (
                select(ApprovalModel, AttendanceCaseModel)
                .join(AttendanceCaseModel, AttendanceCaseModel.id == ApprovalModel.case_id)
                .where(ApprovalModel.manager_user_id == manager_user_id)
            )
            if statuses:
                query = query.where(ApprovalModel.status.in_(statuses))
            rows = session.execute(query.order_by(ApprovalModel.created_at.desc()).limit(limit)).all()
            return list(rows)

    def list_overdue_for_manager(
        self,
        manager_user_id: str,
        overdue_days: int = 2,
        limit: int = 20,
    ) -> List[Tuple[ApprovalModel, AttendanceCaseModel]]:
        with SessionLocal() as session:
            overdue_before = datetime.utcnow() - timedelta(days=overdue_days)
            rows = session.execute(
                select(ApprovalModel, AttendanceCaseModel)
                .join(AttendanceCaseModel, AttendanceCaseModel.id == ApprovalModel.case_id)
                .where(ApprovalModel.manager_user_id == manager_user_id)
                .where(ApprovalModel.status == ApprovalStatus.PENDING.value)
                .where(ApprovalModel.created_at <= overdue_before)
                .order_by(ApprovalModel.created_at.asc())
                .limit(limit)
            ).all()
            return list(rows)

    def count_pending_for_manager(self, manager_user_id: str) -> int:
        with SessionLocal() as session:
            rows = session.execute(
                select(ApprovalModel.id)
                .where(ApprovalModel.manager_user_id == manager_user_id)
                .where(ApprovalModel.status == ApprovalStatus.PENDING.value)
            ).all()
            return len(rows)

    def get(self, approval_id: int) -> Optional[ApprovalModel]:
        with SessionLocal() as session:
            return session.get(ApprovalModel, approval_id)

    def get_by_case_id(self, case_id: int) -> Optional[ApprovalModel]:
        with SessionLocal() as session:
            return session.execute(
                select(ApprovalModel).where(ApprovalModel.case_id == case_id).limit(1)
            ).scalar_one_or_none()

    def create(
        self,
        *,
        case_id: int,
        manager_user_id: str,
        manager_name: str,
        status: str = ApprovalStatus.PENDING.value,
    ) -> int:
        with SessionLocal() as session:
            row = ApprovalModel(
                case_id=case_id,
                manager_user_id=manager_user_id,
                manager_name=manager_name,
                status=status,
            )
            session.add(row)
            session.commit()
            session.refresh(row)
            return int(row.id)

    def create_if_missing(
        self,
        *,
        case_id: int,
        manager_user_id: str,
        manager_name: str,
        status: str = ApprovalStatus.PENDING.value,
    ) -> Optional[int]:
        with SessionLocal() as session:
            existing = session.execute(
                select(ApprovalModel).where(ApprovalModel.case_id == case_id).limit(1)
            ).scalar_one_or_none()
            if existing is not None:
                existing.manager_user_id = manager_user_id
                existing.manager_name = manager_name
                existing.status = status
                session.commit()
                session.refresh(existing)
                return int(existing.id)
            row = ApprovalModel(
                case_id=case_id,
                manager_user_id=manager_user_id,
                manager_name=manager_name,
                status=status,
            )
            session.add(row)
            session.commit()
            session.refresh(row)
            return int(row.id)

    def update_status(self, approval_id: int, status: str, comment: str = "") -> Optional[ApprovalModel]:
        with SessionLocal() as session:
            approval = session.get(ApprovalModel, approval_id)
            if approval is None:
                return None
            approval.status = status
            if comment:
                approval.comment = comment
            case = session.get(AttendanceCaseModel, approval.case_id)
            if case is not None:
                if status == ApprovalStatus.APPROVED.value:
                    case.status = AttendanceCaseStatus.JUSTIFIED.value
                elif status == ApprovalStatus.REJECTED.value:
                    case.status = AttendanceCaseStatus.UNJUSTIFIED.value
            session.commit()
            session.refresh(approval)
            return approval
