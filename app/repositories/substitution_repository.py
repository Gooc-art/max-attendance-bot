from __future__ import annotations

from typing import Dict, List

from sqlalchemy import select

from app.db.base import SessionLocal
from app.db.models import SubstitutionDraftModel


class SubstitutionRepository:
    def create_draft(self, created_by_user_id: str, role: str, data: Dict[str, str]) -> int:
        with SessionLocal() as session:
            draft = SubstitutionDraftModel(
                created_by_user_id=created_by_user_id,
                role=role,
                target_manager=data.get("target_manager", ""),
                replacement_user=data.get("replacement_user", ""),
                reason=data.get("reason", ""),
                date_from=data.get("date_from", ""),
                date_to=data.get("date_to", ""),
                scope=data.get("scope", ""),
                status="draft",
            )
            session.add(draft)
            session.commit()
            session.refresh(draft)
            return int(draft.id)

    def list_drafts_for_user(self, created_by_user_id: str) -> List[SubstitutionDraftModel]:
        with SessionLocal() as session:
            rows = session.execute(
                select(SubstitutionDraftModel)
                .where(SubstitutionDraftModel.created_by_user_id == created_by_user_id)
                .order_by(SubstitutionDraftModel.created_at.desc())
            ).scalars().all()
            return list(rows)

    def get_draft(self, draft_id: int, created_by_user_id: str | None = None) -> SubstitutionDraftModel | None:
        with SessionLocal() as session:
            query = select(SubstitutionDraftModel).where(SubstitutionDraftModel.id == draft_id)
            if created_by_user_id:
                query = query.where(SubstitutionDraftModel.created_by_user_id == created_by_user_id)
            return session.execute(query.limit(1)).scalar_one_or_none()

    def cancel_draft(self, draft_id: int, created_by_user_id: str) -> SubstitutionDraftModel | None:
        with SessionLocal() as session:
            draft = session.execute(
                select(SubstitutionDraftModel)
                .where(SubstitutionDraftModel.id == draft_id)
                .where(SubstitutionDraftModel.created_by_user_id == created_by_user_id)
                .limit(1)
            ).scalar_one_or_none()
            if draft is None:
                return None
            draft.status = "cancelled"
            session.commit()
            session.refresh(draft)
            return draft

    def extend_draft(self, draft_id: int, created_by_user_id: str, new_date_to: str) -> SubstitutionDraftModel | None:
        with SessionLocal() as session:
            draft = session.execute(
                select(SubstitutionDraftModel)
                .where(SubstitutionDraftModel.id == draft_id)
                .where(SubstitutionDraftModel.created_by_user_id == created_by_user_id)
                .limit(1)
            ).scalar_one_or_none()
            if draft is None:
                return None
            draft.date_to = new_date_to
            draft.status = "draft"
            session.commit()
            session.refresh(draft)
            return draft
