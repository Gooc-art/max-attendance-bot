from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.db.base import SessionLocal
from app.db.models import WeatherUserLocationModel


class WeatherLocationRepository:
    def get(self, user_id: str) -> tuple[str, str, datetime] | None:
        now = datetime.now(UTC).replace(tzinfo=None)
        with SessionLocal() as session:
            row = session.execute(
                select(WeatherUserLocationModel).where(WeatherUserLocationModel.user_id == str(user_id))
            ).scalar_one_or_none()
            if row is None:
                return None
            if row.expires_at <= now:
                session.delete(row)
                session.commit()
                return None
            return row.latitude, row.longitude, row.expires_at

    def save(self, user_id: str, latitude: str, longitude: str, ttl_seconds: int = 86400) -> None:
        expires_at = datetime.now(UTC).replace(tzinfo=None) + timedelta(seconds=ttl_seconds)
        with SessionLocal() as session:
            row = session.execute(
                select(WeatherUserLocationModel).where(WeatherUserLocationModel.user_id == str(user_id))
            ).scalar_one_or_none()
            if row is None:
                session.add(
                    WeatherUserLocationModel(
                        user_id=str(user_id),
                        latitude=str(latitude),
                        longitude=str(longitude),
                        expires_at=expires_at,
                    )
                )
            else:
                row.latitude = str(latitude)
                row.longitude = str(longitude)
                row.expires_at = expires_at
            session.commit()
