from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Dict, List, Optional
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from app.config import get_settings
from app.schemas.max import (
    MaxCallbackAnswerBody,
    MaxInlineKeyboardAttachment,
    MaxInlineKeyboardPayload,
    MaxKeyboardButton,
    MaxOutboundButton,
    MaxSendMessageBody,
)


@dataclass
class MaxApiClient:
    token: str
    secret: str
    base_url: str
    version: str

    @classmethod
    def from_settings(cls) -> "MaxApiClient":
        settings = get_settings()
        return cls(
            token=settings.max_bot_token,
            secret=settings.max_bot_secret,
            base_url=settings.max_api_base_url,
            version=settings.max_api_version,
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

        keyboard_buttons = [
            [MaxKeyboardButton(text=button.title, payload=button.action)]
            for button in buttons
        ]
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
        return self._request(
            "POST",
            "messages",
            params={
                "chatId": chat_id,
                "userId": user_id,
            },
            body=body.model_dump(exclude_none=True),
        )

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
            params={"callbackId": callback_id},
            body=answer.model_dump(exclude_none=True),
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

    def unsubscribe_webhook(self, url: str) -> Dict[str, object]:
        if not self.is_configured():
            return {"status": "not_configured", "url": url}
        return self._request("DELETE", "subscriptions", params={"url": url}, body=None)

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
                "User-Agent": "attendance-bot/0.1.0",
            },
        )
        if body is not None:
            request.add_header("Content-Type", "application/json")
        with urlopen(request, timeout=30) as response:
            raw = response.read().decode("utf-8")
            if not raw:
                return {"status": response.status}
            return json.loads(raw)
