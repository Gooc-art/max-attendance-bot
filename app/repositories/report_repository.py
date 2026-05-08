from __future__ import annotations

from pathlib import Path
from typing import List, Optional

from sqlalchemy import delete, select

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

    def list_by_user_and_type(self, user_id: str, report_type: str) -> List[ReportModel]:
        with SessionLocal() as session:
            rows = session.execute(
                select(ReportModel)
                .where(ReportModel.user_id == user_id)
                .where(ReportModel.report_type == report_type)
                .order_by(ReportModel.created_at.desc())
            ).scalars().all()
            return list(rows)

    def delete_by_user_and_type(
        self,
        user_id: str,
        report_type: str,
        exclude_token: str | None = None,
    ) -> List[Path]:
        removed_paths: List[Path] = []
        with SessionLocal() as session:
            query = select(ReportModel).where(ReportModel.user_id == user_id).where(ReportModel.report_type == report_type)
            if exclude_token:
                query = query.where(ReportModel.token != exclude_token)
            rows = session.execute(query).scalars().all()
            for row in rows:
                removed_paths.append(Path(row.file_path))
                removed_paths.append(Path(row.file_path).with_suffix(".pdf"))
            delete_query = delete(ReportModel).where(ReportModel.user_id == user_id).where(ReportModel.report_type == report_type)
            if exclude_token:
                delete_query = delete_query.where(ReportModel.token != exclude_token)
            session.execute(delete_query)
            session.commit()
        return removed_paths
