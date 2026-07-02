from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request

from app.integrations.google_sheets.directory import GoogleSheetsDirectoryService
from app.repositories.employee_directory_repository import EmployeeDirectoryRepository
from app.services.employee_directory_import import EmployeeDirectoryImportService
from app.domain.role_labels import display_role_name


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
    local_rows = repository.list_recent(limit=limit)
    if local_rows:
        return {
            "source": "local_database",
            "items": [
                {
                    "id": row.id,
                    "employee_name": row.employee_name,
                    "employee_user_id": row.employee_user_id,
                    "manager_name": row.manager_name,
                    "manager_user_id": row.manager_user_id,
                    "department_name": row.department_name,
                    "schedule_name": row.schedule_name,
                    "schedule_id": row.schedule_id,
                    "role": row.role,
                    "role_label": display_role_name(row.role),
                    "is_active": row.is_active,
                    "updated_at": row.updated_at.isoformat(),
                }
                for row in local_rows
            ],
        }

    google_directory_service = GoogleSheetsDirectoryService.from_settings()
    google_rows = google_directory_service.list_employees()
    if google_rows:
        rows = google_rows[:limit]
        return {
            "source": "google_sheets",
            "items": [
                {
                    "id": index + 1,
                    "employee_name": row.employee_name,
                    "employee_user_id": row.employee_user_id,
                    "manager_name": row.manager_name,
                    "manager_user_id": row.manager_user_id,
                    "department_name": row.department_name,
                    "schedule_name": row.schedule_name,
                    "schedule_id": row.schedule_id,
                    "role": row.role,
                    "role_label": display_role_name(row.role),
                    "is_active": row.is_active,
                    "updated_at": None,
                }
                for index, row in enumerate(rows)
            ],
        }

    rows = repository.list_recent(limit=limit)
    return {
        "source": "local_database",
        "items": [
            {
                "id": row.id,
                "employee_name": row.employee_name,
                "employee_user_id": row.employee_user_id,
                "manager_name": row.manager_name,
                "manager_user_id": row.manager_user_id,
                "department_name": row.department_name,
                "schedule_name": "",
                "schedule_id": "",
                "role": row.role,
                "role_label": display_role_name(row.role),
                "is_active": row.is_active,
                "updated_at": row.updated_at.isoformat(),
            }
            for row in rows
        ]
    }
