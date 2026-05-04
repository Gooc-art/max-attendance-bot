from __future__ import annotations

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
