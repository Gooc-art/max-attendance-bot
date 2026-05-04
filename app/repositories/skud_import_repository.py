from __future__ import annotations

from typing import List

from sqlalchemy import select

from app.db.base import SessionLocal
from app.db.models import SkudImportModel


class SkudImportRepository:
    def create(
        self,
        *,
        filename: str,
        created_by_user_id: str,
        status: str,
        period_start: str,
        period_end: str,
        unique_employees: int,
        total_rows: int,
        created_cases: int,
        error_rows: int,
        samples_text: str = "",
    ) -> int:
        with SessionLocal() as session:
            row = SkudImportModel(
                filename=filename,
                created_by_user_id=created_by_user_id,
                status=status,
                period_start=period_start,
                period_end=period_end,
                unique_employees=unique_employees,
                total_rows=total_rows,
                created_cases=created_cases,
                error_rows=error_rows,
                samples_text=samples_text,
            )
            session.add(row)
            session.commit()
            session.refresh(row)
            return int(row.id)

    def list_recent(self, limit: int = 20) -> List[SkudImportModel]:
        with SessionLocal() as session:
            rows = session.execute(
                select(SkudImportModel)
                .order_by(SkudImportModel.created_at.desc())
                .limit(limit)
            ).scalars().all()
            return list(rows)
