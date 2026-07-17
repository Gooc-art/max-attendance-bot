from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from sqlalchemy import and_, func, or_, select

from app.db.base import SessionLocal
from app.db.models import UserBotActivityModel, utc_now


class UserBotActivityRepository:
    DEVICE_PLATFORMS = {"android", "ios", "unknown"}

    def touch(self, *, user_id: str, display_name: str, role: str, started: bool) -> Optional[UserBotActivityModel]:
        normalized_user_id = str(user_id or "").strip()
        if not normalized_user_id:
            return None

        now = utc_now()
        normalized_name = str(display_name or "").strip()
        normalized_role = str(role or "").strip()

        with SessionLocal() as session:
            row = session.execute(
                select(UserBotActivityModel).where(UserBotActivityModel.user_id == normalized_user_id).limit(1)
            ).scalar_one_or_none()
            if row is None:
                row = UserBotActivityModel(
                    user_id=normalized_user_id,
                    first_seen_at=now,
                    last_seen_at=now,
                )
                session.add(row)

            row.last_seen_at = now
            row.interaction_count = int(row.interaction_count or 0) + 1
            if normalized_name:
                row.display_name = normalized_name
            if normalized_role:
                row.role = normalized_role

            if started:
                if row.first_start_at is None:
                    row.first_start_at = now
                row.last_start_at = now
                row.start_count = int(row.start_count or 0) + 1

            session.commit()
            return None

    def set_device_platform(self, *, user_id: str, device_platform: str) -> bool:
        normalized_user_id = str(user_id or "").strip()
        if not normalized_user_id:
            return False

        platform = str(device_platform or "").strip().lower()
        if platform not in self.DEVICE_PLATFORMS:
            platform = "unknown"

        now = utc_now()
        with SessionLocal() as session:
            row = session.execute(
                select(UserBotActivityModel).where(UserBotActivityModel.user_id == normalized_user_id).limit(1)
            ).scalar_one_or_none()
            if row is None:
                row = UserBotActivityModel(
                    user_id=normalized_user_id,
                    first_seen_at=now,
                    last_seen_at=now,
                )
                session.add(row)

            row.device_platform = platform
            row.last_seen_at = now
            session.commit()
            return True

    def get_by_user_id(self, user_id: str) -> Optional[UserBotActivityModel]:
        with SessionLocal() as session:
            return session.execute(
                select(UserBotActivityModel).where(UserBotActivityModel.user_id == str(user_id or "").strip()).limit(1)
            ).scalar_one_or_none()

    def count_started_total(self) -> int:
        with SessionLocal() as session:
            return int(
                session.execute(
                    select(func.count()).select_from(UserBotActivityModel).where(UserBotActivityModel.first_start_at.is_not(None))
                ).scalar_one()
                or 0
            )

    def count_seen_total(self) -> int:
        with SessionLocal() as session:
            return int(
                session.execute(
                    select(func.count()).select_from(UserBotActivityModel)
                ).scalar_one()
                or 0
            )

    def count_by_device_platform(self) -> dict[str, int]:
        with SessionLocal() as session:
            rows = session.execute(
                select(UserBotActivityModel.device_platform, func.count())
                .select_from(UserBotActivityModel)
                .where(
                    and_(
                        UserBotActivityModel.user_id.not_like("test-%"),
                        or_(
                            UserBotActivityModel.interaction_count > 0,
                            UserBotActivityModel.device_platform.in_(("android", "ios")),
                        ),
                    )
                )
                .group_by(UserBotActivityModel.device_platform)
            ).all()
        counts = {"android": 0, "ios": 0, "unknown": 0}
        for platform, total in rows:
            key = str(platform or "").strip().lower()
            if key not in {"android", "ios"}:
                key = "unknown"
            counts[key] += int(total or 0)
        return counts

    def count_started_since(self, dt: datetime) -> int:
        with SessionLocal() as session:
            return int(
                session.execute(
                    select(func.count()).select_from(UserBotActivityModel).where(UserBotActivityModel.last_start_at >= dt)
                ).scalar_one()
                or 0
            )

    def count_active_since(self, dt: datetime) -> int:
        with SessionLocal() as session:
            return int(
                session.execute(
                    select(func.count()).select_from(UserBotActivityModel).where(UserBotActivityModel.last_seen_at >= dt)
                ).scalar_one()
                or 0
            )

    def list_recent_seen(self, limit: int = 10) -> List[UserBotActivityModel]:
        with SessionLocal() as session:
            rows = session.execute(
                select(UserBotActivityModel)
                .order_by(UserBotActivityModel.last_seen_at.desc(), UserBotActivityModel.last_start_at.desc())
                .limit(limit)
            ).scalars().all()
            return list(rows)

    def list_recent_started(self, limit: int = 10) -> List[UserBotActivityModel]:
        with SessionLocal() as session:
            rows = session.execute(
                select(UserBotActivityModel)
                .where(UserBotActivityModel.last_start_at.is_not(None))
                .order_by(UserBotActivityModel.last_start_at.desc(), UserBotActivityModel.last_seen_at.desc())
                .limit(limit)
            ).scalars().all()
            return list(rows)
