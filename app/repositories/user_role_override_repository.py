from __future__ import annotations

from typing import List, Optional

from sqlalchemy import select

from app.db.base import SessionLocal
from app.db.models import UserRoleOverrideModel


class UserRoleOverrideRepository:
    def get_role(self, user_id: str) -> Optional[str]:
        with SessionLocal() as session:
            row = session.execute(
                select(UserRoleOverrideModel).where(UserRoleOverrideModel.user_id == user_id)
            ).scalar_one_or_none()
            return row.role if row else None

    def set_role(self, user_id: str, role: str) -> str:
        with SessionLocal() as session:
            row = session.execute(
                select(UserRoleOverrideModel).where(UserRoleOverrideModel.user_id == user_id)
            ).scalar_one_or_none()
            if row is None:
                row = UserRoleOverrideModel(user_id=user_id, role=role)
                session.add(row)
            else:
                row.role = role
            session.commit()
            return role

    def list_all(self, limit: int = 50) -> List[UserRoleOverrideModel]:
        with SessionLocal() as session:
            rows = session.execute(
                select(UserRoleOverrideModel)
                .order_by(UserRoleOverrideModel.updated_at.desc())
                .limit(limit)
            ).scalars().all()
            return list(rows)
