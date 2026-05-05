from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from app.services.report_service import ReportService


router = APIRouter(tags=["reports"])


@router.get("/reports/{token}/download")
def download_report(token: str):
    service = ReportService()
    path = service.get_report_path(token)
    if path is None:
        raise HTTPException(status_code=404, detail="Report not found")
    return FileResponse(
        path,
        filename=path.name,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
