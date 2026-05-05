from __future__ import annotations

from typing import List, Optional

from sqlalchemy import select

from app.db.base import SessionLocal
from app.db.models import ReportModel


class ReportRepository:
    def create(
        self,
        *,
        token: str,
        report_type: str,
        user_id: str,
        role: str,
        title: str,
        period_start: str,
        period_end: str,
        file_name: str,
        file_path: str,
        summary_text: str,
        status: str = "ready",
    ) -> int:
        with SessionLocal() as session:
            row = ReportModel(
                token=token,
                report_type=report_type,
                user_id=user_id,
                role=role,
                title=title,
                period_start=period_start,
                period_end=period_end,
                file_name=file_name,
                file_path=file_path,
                summary_text=summary_text,
                status=status,
            )
            session.add(row)
            session.commit()
            session.refresh(row)
            return int(row.id)

    def get_by_token(self, token: str) -> Optional[ReportModel]:
        with SessionLocal() as session:
            return session.execute(
                select(ReportModel).where(ReportModel.token == token).limit(1)
            ).scalar_one_or_none()

    def list_recent(self, limit: int = 20) -> List[ReportModel]:
        with SessionLocal() as session:
            rows = session.execute(
                select(ReportModel)
                .order_by(ReportModel.created_at.desc())
                .limit(limit)
            ).scalars().all()
            return list(rows)
