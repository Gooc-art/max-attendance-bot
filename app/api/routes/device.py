from __future__ import annotations

from typing import Dict

from fastapi import APIRouter
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from app.repositories.user_bot_activity_repository import UserBotActivityRepository


page_router = APIRouter(tags=["device"])
api_router = APIRouter(tags=["device"])


class DeviceRequest(BaseModel):
    user_id: str
    device_platform: str = "unknown"


@page_router.get("/device", response_class=HTMLResponse)
def device_page(user_id: str = "") -> str:
    return """<!doctype html>
<html lang="ru">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Устройство</title>
  <style>
    body { font-family: system-ui, sans-serif; margin: 0; padding: 32px; line-height: 1.4; }
    .box { max-width: 520px; margin: 0 auto; }
    .status { font-size: 20px; font-weight: 700; margin-bottom: 12px; }
  </style>
</head>
<body>
  <main class="box">
    <div class="status" id="status">Определяю устройство...</div>
    <div id="detail"></div>
  </main>
  <script>
    const userId = new URLSearchParams(location.search).get("user_id") || "";
    const ua = navigator.userAgent || "";
    const isIOS = /iPhone|iPad|iPod/i.test(ua) || (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1);
    const platform = /Android/i.test(ua) ? "android" : isIOS ? "ios" : "unknown";
    const label = platform === "android" ? "Android" : platform === "ios" ? "iOS" : "неизвестно";

    fetch("/api/device", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({user_id: userId, device_platform: platform})
    }).then(response => response.json()).then(result => {
      if (!result.ok) throw new Error("not saved");
      document.getElementById("status").textContent = "Устройство: " + label;
      document.getElementById("detail").textContent = "Вернись в MAX и нажми Обновить.";
    }).catch(() => {
      document.getElementById("status").textContent = "Не получилось сохранить устройство";
      document.getElementById("detail").textContent = "Попробуй открыть ссылку еще раз.";
    });
  </script>
</body>
</html>"""


@api_router.post("/device")
def save_device(payload: DeviceRequest) -> Dict[str, object]:
    saved = UserBotActivityRepository().set_device_platform(
        user_id=payload.user_id,
        device_platform=payload.device_platform,
    )
    return {"ok": saved}
