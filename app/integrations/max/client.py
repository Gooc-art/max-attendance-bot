from __future__ import annotations

import json
import time
from dataclasses import dataclass
from itertools import groupby
from pathlib import Path
from typing import Dict, List, Optional
from urllib.parse import urlencode
from urllib.error import HTTPError
from urllib.request import Request, urlopen
import mimetypes
from uuid import uuid4

from app.config import get_settings
from app.schemas.max import (
    MaxCallbackAnswerBody,
    MaxInlineKeyboardAttachment,
    MaxInlineKeyboardPayload,
    MaxKeyboardButton,
    MaxOutboundButton,
    MaxSendMessageBody,
)

INVISIBLE_MESSAGE_TEXT = "\u2060"


@dataclass
class MaxApiClient:
    token: str
    secret: str
    base_url: str
    version: str
    request_timeout_seconds: int = 10

    @classmethod
    def from_settings(cls) -> "MaxApiClient":
        settings = get_settings()
        return cls(
            token=settings.max_bot_token,
            secret=settings.max_bot_secret,
            base_url=settings.max_api_base_url,
            version=settings.max_api_version,
            request_timeout_seconds=settings.max_api_timeout_seconds,
        )

    def is_configured(self) -> bool:
        return bool(self.token)

    def send_text(self, chat_id: str, text: str) -> Dict[str, str]:
        return {
            "chat_id": chat_id,
            "text": text,
            "status": "stub",
        }

    def build_inline_keyboard(self, buttons: List[MaxOutboundButton]) -> List[MaxInlineKeyboardAttachment]:
        if not buttons:
            return []

        keyboard_buttons = []
        sorted_buttons = sorted(enumerate(buttons), key=lambda item: (item[1].row, item[0]))
        for _, group in groupby(sorted_buttons, key=lambda item: item[1].row):
            row_buttons = []
            for _, button in group:
                text = button.title
                if button.emoji:
                    text = f"{button.emoji} {text}"
                row_buttons.append(MaxKeyboardButton(text=text, payload=button.action))
            keyboard_buttons.append(row_buttons)
        return [
            MaxInlineKeyboardAttachment(
                payload=MaxInlineKeyboardPayload(buttons=keyboard_buttons)
            )
        ]

    def build_message_body(
        self,
        text: str,
        buttons: Optional[List[MaxOutboundButton]] = None,
        notify: bool = True,
    ) -> MaxSendMessageBody:
        return MaxSendMessageBody(
            text=text,
            attachments=self.build_inline_keyboard(buttons or []),
            notify=notify,
        )

    def send_message(
        self,
        *,
        chat_id: Optional[int] = None,
        user_id: Optional[int] = None,
        text: str,
        buttons: Optional[List[MaxOutboundButton]] = None,
        notify: bool = True,
    ) -> Dict[str, object]:
        body = self.build_message_body(text=text, buttons=buttons, notify=notify)
        if not self.is_configured():
            return {
                "status": "not_configured",
                "body": body.model_dump(exclude_none=True),
            }
        params = self._recipient_params(chat_id=chat_id, user_id=user_id)
        return self._request(
            "POST",
            "messages",
            params=params,
            body=body.model_dump(exclude_none=True),
        )

    def send_file_message(
        self,
        *,
        chat_id: Optional[int] = None,
        user_id: Optional[int] = None,
        text: str = "",
        file_path: str | Path,
        notify: bool = True,
    ) -> Dict[str, object]:
        path = Path(file_path)
        upload_info = self.upload_file(path)
        attachment = {
            "type": "file",
            "payload": {"token": upload_info["token"]},
            "filename": path.name,
            "size": path.stat().st_size,
        }
        body: Dict[str, object] = {
            "text": text,
            "attachments": [attachment],
            "notify": notify,
        }
        if not self.is_configured():
            return {
                "status": "not_configured",
                "body": body,
            }
        params = self._recipient_params(chat_id=chat_id, user_id=user_id)
        for attempt in range(3):
            try:
                return self._request("POST", "messages", params=params, body=body)
            except RuntimeError as exc:
                if "attachment.not.ready" not in str(exc) or attempt == 2:
                    raise
                time.sleep(1)
        raise RuntimeError("MAX file message retry exhausted")

    def answer_callback(
        self,
        *,
        callback_id: str,
        notification: Optional[str] = None,
        new_text: Optional[str] = None,
        buttons: Optional[List[MaxOutboundButton]] = None,
    ) -> Dict[str, object]:
        answer = MaxCallbackAnswerBody(notification=notification)
        if new_text is not None:
            answer.message = self.build_message_body(text=new_text, buttons=buttons or [])

        if not self.is_configured():
            return {
                "status": "not_configured",
                "callback_id": callback_id,
                "body": answer.model_dump(exclude_none=True),
            }
        return self._request(
            "POST",
            "answers",
            params={"callback_id": callback_id},
            body=answer.model_dump(exclude_none=True),
        )

    def get_message(self, message_id: str) -> Dict[str, object]:
        if not self.is_configured():
            return {"status": "not_configured", "message_id": message_id}
        return self._request(
            "GET",
            f"messages/{message_id}",
            params={},
            body=None,
        )

    def delete_message(self, message_id: str) -> Dict[str, object]:
        if not self.is_configured():
            return {"status": "not_configured", "message_id": message_id}
        return self._request(
            "DELETE",
            "messages",
            params={"message_id": message_id},
            body=None,
        )

    def soft_clear_message(self, message_id: str) -> Dict[str, object]:
        if not self.is_configured():
            return {"status": "not_configured", "message_id": message_id}
        return self._request(
            "PUT",
            "messages",
            params={"message_id": message_id},
            body={
                "text": INVISIBLE_MESSAGE_TEXT,
                "attachments": [],
                "notify": False,
            },
        )

    def edit_message(
        self,
        message_id: str,
        *,
        text: str,
        buttons: Optional[List[MaxOutboundButton]] = None,
        notify: bool = False,
    ) -> Dict[str, object]:
        body = self.build_message_body(text=text, buttons=buttons or [], notify=notify)
        if not self.is_configured():
            return {
                "status": "not_configured",
                "message_id": message_id,
                "body": body.model_dump(exclude_none=True),
            }
        return self._request(
            "PUT",
            "messages",
            params={"message_id": message_id},
            body=body.model_dump(exclude_none=True),
        )

    def register_webhook(self, url: str, update_types: List[str], secret: str) -> Dict[str, object]:
        body = {
            "url": url,
            "update_types": update_types,
            "secret": secret,
        }
        if not self.is_configured():
            return {
                "status": "not_configured",
                "body": body,
            }
        return self._request("POST", "subscriptions", params={}, body=body)

    def get_subscriptions(self) -> Dict[str, object]:
        if not self.is_configured():
            return {"status": "not_configured"}
        return self._request("GET", "subscriptions", params={}, body=None)

    def get_updates(
        self,
        *,
        marker: Optional[str] = None,
        timeout_seconds: Optional[int] = None,
        limit: Optional[int] = None,
    ) -> Dict[str, object]:
        if not self.is_configured():
            return {"status": "not_configured", "updates": []}
        return self._request(
            "GET",
            "updates",
            params={
                "marker": marker,
                "timeout": timeout_seconds,
                "limit": limit,
            },
            body=None,
        )

    def unsubscribe_webhook(self, url: str) -> Dict[str, object]:
        if not self.is_configured():
            return {"status": "not_configured", "url": url}
        return self._request("DELETE", "subscriptions", params={"url": url}, body=None)

    def unsubscribe_all_webhooks(self) -> List[str]:
        subscriptions = self.get_subscriptions().get("subscriptions", [])
        deleted: List[str] = []
        if not isinstance(subscriptions, list):
            return deleted
        for subscription in subscriptions:
            if not isinstance(subscription, dict):
                continue
            url = str(subscription.get("url") or subscription.get("webhook_url") or "").strip()
            if not url:
                continue
            self.unsubscribe_webhook(url)
            deleted.append(url)
        return deleted

    def upload_file(self, file_path: Path) -> Dict[str, object]:
        if not self.is_configured():
            return {"status": "not_configured", "token": ""}

        endpoint = self._get_upload_endpoint("file")
        with file_path.open("rb") as fh:
            upload_result = self._multipart_upload(endpoint["url"], file_path.name, fh.read())
        token = upload_result.get("token") or endpoint.get("token") or ""
        return {"token": token, **upload_result}

    def _request(
        self,
        method: str,
        path: str,
        params: Dict[str, Optional[object]],
        body: Optional[Dict[str, object]] = None,
    ) -> Dict[str, object]:
        query = {
            "v": self.version,
        }
        for key, value in params.items():
            if value is not None:
                query[key] = str(value)

        encoded = json.dumps(body).encode("utf-8") if body is not None else None
        request = Request(
            url="{base}{path}?{query}".format(
                base=self.base_url,
                path=path,
                query=urlencode(query),
            ),
            data=encoded,
            method=method,
            headers={
                "Authorization": self.token,
                "User-Agent": "skud/0.1.0",
            },
        )
        if body is not None:
            request.add_header("Content-Type", "application/json")
        try:
            with urlopen(request, timeout=self.request_timeout_seconds) as response:
                raw = response.read().decode("utf-8")
                if not raw:
                    return {"status": response.status}
                return json.loads(raw)
        except HTTPError as exc:
            raw = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"MAX API {method} {path} failed: HTTP {exc.code} {raw[:500]}") from exc

    def _get_upload_endpoint(self, upload_type: str) -> Dict[str, object]:
        return self._request(
            "POST",
            "uploads",
            params={"type": upload_type},
            body=None,
        )

    def _multipart_upload(self, url: str, filename: str, content: bytes) -> Dict[str, object]:
        boundary = f"----attendancebot{uuid4().hex}"
        content_type = f"multipart/form-data; boundary={boundary}"
        file_part = (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="data"; filename="{filename}"\r\n'
            f"Content-Type: {mimetypes.guess_type(filename)[0] or 'application/octet-stream'}\r\n\r\n"
        ).encode("utf-8") + content + f"\r\n--{boundary}--\r\n".encode("utf-8")

        request = Request(
            url=url,
            data=file_part,
            method="POST",
            headers={
                "Content-Type": content_type,
                "User-Agent": "skud/0.1.0",
            },
        )
        with urlopen(request, timeout=60) as response:
            raw = response.read().decode("utf-8")
            return json.loads(raw) if raw else {"status": response.status}

    def _recipient_params(self, chat_id: Optional[int] = None, user_id: Optional[int] = None) -> Dict[str, Optional[object]]:
        if chat_id is not None:
            return {"chat_id": chat_id}
        if user_id is not None:
            return {"user_id": user_id}
        return {}
