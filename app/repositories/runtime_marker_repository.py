from __future__ import annotations

from datetime import timedelta

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError

from app.db.base import SessionLocal
from app.db.models import RuntimeMarkerModel, utc_now


class RuntimeMarkerRepository:
    def claim(self, marker_key: str, marker_type: str, lease_seconds: int = 120) -> bool:
        key = str(marker_key or "").strip()
        if not key:
            return True

        now = utc_now()
        expires_at = now + timedelta(seconds=lease_seconds)
        with SessionLocal() as session:
            marker = RuntimeMarkerModel(
                marker_key=key,
                marker_type=marker_type,
                status="processing",
                created_at=now,
                updated_at=now,
                expires_at=expires_at,
            )
            session.add(marker)
            try:
                session.commit()
                return True
            except IntegrityError:
                session.rollback()

            existing = session.execute(
                select(RuntimeMarkerModel).where(RuntimeMarkerModel.marker_key == key).limit(1)
            ).scalar_one_or_none()
            if existing is None or existing.expires_at > now:
                return False

            session.execute(delete(RuntimeMarkerModel).where(RuntimeMarkerModel.marker_key == key))
            session.commit()
            session.add(marker)
            try:
                session.commit()
                return True
            except IntegrityError:
                session.rollback()
                return False

    def complete(self, marker_key: str, ttl_seconds: int = 600) -> None:
        key = str(marker_key or "").strip()
        if not key:
            return

        now = utc_now()
        with SessionLocal() as session:
            marker = session.execute(
                select(RuntimeMarkerModel).where(RuntimeMarkerModel.marker_key == key).limit(1)
            ).scalar_one_or_none()
            if marker is None:
                return
            marker.status = "done"
            marker.updated_at = now
            marker.expires_at = now + timedelta(seconds=ttl_seconds)
            session.commit()

    def release(self, marker_key: str) -> None:
        key = str(marker_key or "").strip()
        if not key:
            return
        with SessionLocal() as session:
            session.execute(delete(RuntimeMarkerModel).where(RuntimeMarkerModel.marker_key == key))
            session.commit()
