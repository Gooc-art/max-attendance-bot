from __future__ import annotations

import json
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
                target_user_id=data.get("target_user_id", created_by_user_id),
                replacement_user=data.get("replacement_user", ""),
                replacement_user_id=data.get("replacement_user_id", ""),
                reason=data.get("reason", ""),
                date_from=data.get("date_from", ""),
                date_to=data.get("date_to", ""),
                scope=data.get("scope", ""),
                departments_json=data.get("departments_json", "[]"),
                status="pending_replacement_approval",
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

    def get_draft_for_replacement(self, draft_id: int, replacement_user_id: str) -> SubstitutionDraftModel | None:
        with SessionLocal() as session:
            return session.execute(
                select(SubstitutionDraftModel)
                .where(SubstitutionDraftModel.id == draft_id)
                .where(SubstitutionDraftModel.replacement_user_id == replacement_user_id)
                .limit(1)
            ).scalar_one_or_none()

    def list_pending_for_replacement(self, replacement_user_id: str) -> List[SubstitutionDraftModel]:
        with SessionLocal() as session:
            rows = session.execute(
                select(SubstitutionDraftModel)
                .where(SubstitutionDraftModel.replacement_user_id == replacement_user_id)
                .where(SubstitutionDraftModel.status == "pending_replacement_approval")
                .order_by(SubstitutionDraftModel.created_at.desc())
            ).scalars().all()
            return list(rows)

    def list_approved_overlapping(self, date_from: str, date_to: str) -> List[SubstitutionDraftModel]:
        with SessionLocal() as session:
            rows = session.execute(
                select(SubstitutionDraftModel)
                .where(SubstitutionDraftModel.status == "approved")
                .where(SubstitutionDraftModel.date_from <= date_to)
                .where(SubstitutionDraftModel.date_to >= date_from)
                .order_by(SubstitutionDraftModel.created_at.desc())
            ).scalars().all()
            return list(rows)

    def list_active_department_curations(
        self,
        replacement_user_id: str,
        event_date: str,
    ) -> List[SubstitutionDraftModel]:
        if not replacement_user_id or not event_date:
            return []
        with SessionLocal() as session:
            rows = session.execute(
                select(SubstitutionDraftModel)
                .where(SubstitutionDraftModel.replacement_user_id == replacement_user_id)
                .where(SubstitutionDraftModel.status == "approved")
                .where(SubstitutionDraftModel.date_from <= event_date)
                .where(SubstitutionDraftModel.date_to >= event_date)
                .order_by(SubstitutionDraftModel.created_at.desc())
            ).scalars().all()
            return [row for row in rows if self.departments_for_draft(row)]

    @staticmethod
    def departments_for_draft(draft: SubstitutionDraftModel) -> List[str]:
        raw = str(getattr(draft, "departments_json", "") or "").strip()
        if not raw:
            return []
        try:
            value = json.loads(raw)
        except json.JSONDecodeError:
            return []
        if not isinstance(value, list):
            return []
        return [str(item).strip() for item in value if str(item).strip()]

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
            draft.status = "pending_replacement_approval"
            session.commit()
            session.refresh(draft)
            return draft

    def approve_draft(self, draft_id: int, replacement_user_id: str) -> SubstitutionDraftModel | None:
        with SessionLocal() as session:
            draft = session.execute(
                select(SubstitutionDraftModel)
                .where(SubstitutionDraftModel.id == draft_id)
                .where(SubstitutionDraftModel.replacement_user_id == replacement_user_id)
                .limit(1)
            ).scalar_one_or_none()
            if draft is None:
                return None
            draft.status = "approved"
            session.commit()
            session.refresh(draft)
            return draft

    def reject_draft(self, draft_id: int, replacement_user_id: str) -> SubstitutionDraftModel | None:
        with SessionLocal() as session:
            draft = session.execute(
                select(SubstitutionDraftModel)
                .where(SubstitutionDraftModel.id == draft_id)
                .where(SubstitutionDraftModel.replacement_user_id == replacement_user_id)
                .limit(1)
            ).scalar_one_or_none()
            if draft is None:
                return None
            draft.status = "rejected"
            session.commit()
            session.refresh(draft)
            return draft
