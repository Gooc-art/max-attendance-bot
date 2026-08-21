from __future__ import annotations

from dataclasses import dataclass

from app.integrations.google_sheets.directory import GoogleSheetsDirectoryService
from app.repositories.employee_directory_repository import EmployeeDirectoryRepository


@dataclass(frozen=True)
class EmployeeDirectorySyncResult:
    configured: bool
    fetched_rows: int
    upserted_rows: int


class EmployeeDirectorySyncService:
    def __init__(
        self,
        *,
        directory_service: GoogleSheetsDirectoryService | None = None,
        repository: EmployeeDirectoryRepository | None = None,
    ) -> None:
        self.directory_service = directory_service or GoogleSheetsDirectoryService.from_settings()
        self.repository = repository or EmployeeDirectoryRepository()

    def sync(self, *, refresh: bool = True) -> EmployeeDirectorySyncResult:
        if not self.directory_service.is_configured():
            return EmployeeDirectorySyncResult(configured=False, fetched_rows=0, upserted_rows=0)

        records = self.directory_service.list_employees(refresh=refresh)
        names_by_user_id = {
            record.employee_user_id: record.employee_name
            for record in records
            if record.employee_user_id and record.employee_name
        }
        rows = [
            {
                "employee_name": record.employee_name,
                "employee_user_id": record.employee_user_id,
                "manager_name": names_by_user_id.get(record.manager_user_id, record.manager_name),
                "manager_user_id": record.manager_user_id,
                "department_name": record.department_name,
                "office": record.office,
                "schedule_name": record.schedule_name,
                "schedule_id": record.schedule_id,
                "role": GoogleSheetsDirectoryService.normalize_role_value(record.role),
                "is_active": "1" if record.is_active else "0",
            }
            for record in records
            if record.employee_user_id
        ]
        return EmployeeDirectorySyncResult(
            configured=True,
            fetched_rows=len(records),
            upserted_rows=self.repository.upsert_many(rows) if rows else 0,
        )
