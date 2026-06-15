from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from app.config import get_settings


router = APIRouter(tags=["office-seal"])


@router.get("/office-seal/photos/{filename}")
def download_office_seal_photo(filename: str):
    safe_name = Path(filename).name
    if safe_name != filename:
        raise HTTPException(status_code=404, detail="Photo not found")
    path = Path(get_settings().office_seal_photo_dir) / safe_name
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail="Photo not found")
    return FileResponse(path)
