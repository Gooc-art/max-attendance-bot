from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request

from app.repositories.skud_import_repository import SkudImportRepository
from app.services.skud_import import SkudImportService


router = APIRouter(tags=["imports"])


@router.post("/imports/skud/csv")
async def import_skud_csv(
    request: Request,
    filename: str = Query(..., description="Имя исходного CSV файла"),
    created_by_user_id: str = Query(default="", description="ID пользователя безопасности"),
) -> dict:
    content = await request.body()
    if not content:
        raise HTTPException(status_code=400, detail="CSV payload is empty")

    service = SkudImportService()
    result = service.import_csv(
        filename=filename,
        content=content,
        created_by_user_id=created_by_user_id,
    )
    return {
        "ok": True,
        "import_id": result.import_id,
        "filename": result.filename,
        "period_start": result.period_start,
        "period_end": result.period_end,
        "unique_employees": result.unique_employees,
        "total_rows": result.total_rows,
        "created_cases": result.created_cases,
        "error_rows": result.error_rows,
        "samples": result.samples,
        "errors": result.errors,
    }


@router.get("/imports/skud")
def list_skud_imports(limit: int = Query(default=20, ge=1, le=100)) -> dict:
    repository = SkudImportRepository()
    rows = repository.list_recent(limit=limit)
    return {
        "items": [
            {
                "id": row.id,
                "filename": row.filename,
                "created_by_user_id": row.created_by_user_id,
                "status": row.status,
                "period_start": row.period_start,
                "period_end": row.period_end,
                "unique_employees": row.unique_employees,
                "total_rows": row.total_rows,
                "created_cases": row.created_cases,
                "error_rows": row.error_rows,
                "samples": row.samples_text.splitlines() if row.samples_text else [],
                "created_at": row.created_at.isoformat(),
            }
            for row in rows
        ]
    }
