from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request

from app.repositories.employee_directory_repository import EmployeeDirectoryRepository
from app.services.employee_directory_import import EmployeeDirectoryImportService


router = APIRouter(tags=["employees"])


@router.post("/employees/directory/csv")
async def import_employee_directory_csv(request: Request) -> dict:
    content = await request.body()
    if not content:
        raise HTTPException(status_code=400, detail="CSV payload is empty")

    service = EmployeeDirectoryImportService()
    result = service.import_csv(content)
    return {
        "ok": True,
        "total_rows": result.total_rows,
        "upserted_rows": result.upserted_rows,
        "errors": result.errors,
    }


@router.get("/employees/directory")
def list_employee_directory(limit: int = Query(default=20, ge=1, le=100)) -> dict:
    repository = EmployeeDirectoryRepository()
    rows = repository.list_recent(limit=limit)
    return {
        "items": [
            {
                "id": row.id,
                "employee_name": row.employee_name,
                "employee_user_id": row.employee_user_id,
                "manager_name": row.manager_name,
                "manager_user_id": row.manager_user_id,
                "department_name": row.department_name,
                "role": row.role,
                "is_active": row.is_active,
                "updated_at": row.updated_at.isoformat(),
            }
            for row in rows
        ]
    }
