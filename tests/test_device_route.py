from __future__ import annotations

from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.router import api_router
from app.db.base import init_db
from app.repositories.user_bot_activity_repository import UserBotActivityRepository


def test_device_route_saves_platform() -> None:
    init_db()
    app = FastAPI()
    app.include_router(api_router)
    client = TestClient(app)
    user_id = f"test-device-route-{uuid4().hex}"

    response = client.post("/api/device", json={"user_id": user_id, "device_platform": "android"})

    assert response.status_code == 200
    assert response.json() == {"ok": True}
    row = UserBotActivityRepository().get_by_user_id(user_id)
    assert row is not None
    assert row.device_platform == "android"


def test_device_page_detects_ipados_desktop_user_agent() -> None:
    app = FastAPI()
    app.include_router(api_router)
    client = TestClient(app)

    response = client.get("/device?user_id=123")

    assert response.status_code == 200
    assert 'navigator.platform === "MacIntel"' in response.text
    assert "navigator.maxTouchPoints > 1" in response.text
