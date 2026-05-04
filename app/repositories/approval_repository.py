from __future__ import annotations

from typing import List, Optional, Tuple

from sqlalchemy import select

from app.db.base import SessionLocal
from app.db.models import ApprovalModel, AttendanceCaseModel
from app.domain.enums import ApprovalStatus


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

    def update_status(self, approval_id: int, status: str, comment: str = "") -> Optional[ApprovalModel]:
        with SessionLocal() as session:
            approval = session.get(ApprovalModel, approval_id)
            if approval is None:
                return None
            approval.status = status
            if comment:
                approval.comment = comment
            session.commit()
            session.refresh(approval)
            return approval
