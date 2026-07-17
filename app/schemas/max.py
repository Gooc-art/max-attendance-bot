from __future__ import annotations

from typing import List, Literal, Optional

from pydantic import BaseModel, Field


class MaxUser(BaseModel):
    user_id: int
    first_name: str
    last_name: Optional[str] = None
    username: Optional[str] = None
    is_bot: bool = False
    last_activity_time: Optional[int] = None
    name: Optional[str] = None


class MaxRecipient(BaseModel):
    chat_id: int
    chat_type: str = "dialog"
    user_id: Optional[int] = None


class MaxAttachmentPayload(BaseModel):
    url: Optional[str] = None
    token: Optional[str] = None


class MaxAttachment(BaseModel):
    type: str
    payload: Optional[MaxAttachmentPayload] = None
    filename: Optional[str] = None
    size: Optional[int] = None


class MaxMessageBody(BaseModel):
    mid: str
    seq: int
    text: Optional[str] = None
    attachments: List[MaxAttachment] = Field(default_factory=list)


class MaxMessage(BaseModel):
    recipient: MaxRecipient
    timestamp: int
    body: MaxMessageBody
    sender: MaxUser


class MaxCallback(BaseModel):
    timestamp: int
    callback_id: str
    payload: Optional[str] = None
    user: MaxUser


class MaxUpdate(BaseModel):
    update_type: str
    timestamp: int
    message: Optional[MaxMessage] = None
    callback: Optional[MaxCallback] = None
    user_locale: Optional[str] = None
    chat_id: Optional[int] = None
    user: Optional[MaxUser] = None
    payload: Optional[str] = None


class MaxOutboundButton(BaseModel):
    title: str
    action: str
    emoji: Optional[str] = None
    row: int = 0
    button_type: Literal["callback", "link"] = "callback"
    url: Optional[str] = None


class MaxKeyboardButton(BaseModel):
    type: Literal["callback", "link"] = "callback"
    text: str
    payload: Optional[str] = None
    url: Optional[str] = None
    intent: str = "default"


class MaxInlineKeyboardPayload(BaseModel):
    buttons: List[List[MaxKeyboardButton]]


class MaxInlineKeyboardAttachment(BaseModel):
    type: Literal["inline_keyboard"] = "inline_keyboard"
    payload: MaxInlineKeyboardPayload


class MaxNewMessageLink(BaseModel):
    type: str
    mid: str


class MaxSendMessageBody(BaseModel):
    text: Optional[str] = None
    attachments: List[MaxInlineKeyboardAttachment] = Field(default_factory=list)
    link: Optional[MaxNewMessageLink] = None
    notify: Optional[bool] = True
    format: Optional[str] = None


class MaxCallbackAnswerBody(BaseModel):
    message: Optional[MaxSendMessageBody] = None
    notification: Optional[str] = None


class MaxOutboundMessage(BaseModel):
    text: str
    buttons: List[MaxOutboundButton] = Field(default_factory=list)


class MaxWebhookResponse(BaseModel):
    ok: bool
    role: str
    menu: List[str]
    outbound: MaxOutboundMessage
    active_flow: Optional[str] = None
