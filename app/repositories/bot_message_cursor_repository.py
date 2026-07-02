from __future__ import annotations

from typing import Optional

from sqlalchemy import select

from app.db.base import SessionLocal
from app.db.models import BotMessageCursorModel


class BotMessageCursorRepository:
    def get(self, conversation_key: str) -> Optional[str]:
        with SessionLocal() as session:
            model = session.execute(
                select(BotMessageCursorModel).where(BotMessageCursorModel.conversation_key == conversation_key)
            ).scalar_one_or_none()
            if model is None:
                return None
            return model.message_id

    def get_many(self, conversation_keys: list[str]) -> dict[str, str]:
        keys = [str(key or "").strip() for key in conversation_keys if str(key or "").strip()]
        if not keys:
            return {}
        with SessionLocal() as session:
            rows = session.execute(
                select(BotMessageCursorModel).where(BotMessageCursorModel.conversation_key.in_(keys))
            ).scalars().all()
            return {row.conversation_key: row.message_id for row in rows}

    def get_chat_id_for_user(self, user_id: str) -> Optional[str]:
        with SessionLocal() as session:
            model = session.execute(
                select(BotMessageCursorModel)
                .where(BotMessageCursorModel.user_id == str(user_id))
                .where(BotMessageCursorModel.chat_id != "")
                .order_by(BotMessageCursorModel.updated_at.desc())
                .limit(1)
            ).scalar_one_or_none()
            if model is None:
                return None
            return model.chat_id

    def save(self, conversation_key: str, chat_id: str, user_id: str, message_id: str) -> str:
        with SessionLocal() as session:
            model = session.execute(
                select(BotMessageCursorModel).where(BotMessageCursorModel.conversation_key == conversation_key)
            ).scalar_one_or_none()
            if model is None:
                model = BotMessageCursorModel(
                    conversation_key=conversation_key,
                    chat_id=chat_id,
                    user_id=user_id,
                    message_id=message_id,
                )
                session.add(model)
            else:
                model.chat_id = chat_id
                model.user_id = user_id
                model.message_id = message_id
            session.commit()
        return message_id

    def save_many(self, conversation_keys: list[str], chat_id: str, user_id: str, message_id: str) -> str:
        keys = [str(key or "").strip() for key in conversation_keys if str(key or "").strip()]
        if not keys:
            return message_id
        with SessionLocal() as session:
            existing = {
                row.conversation_key: row
                for row in session.execute(
                    select(BotMessageCursorModel).where(BotMessageCursorModel.conversation_key.in_(keys))
                ).scalars().all()
            }
            for key in keys:
                model = existing.get(key)
                if model is None:
                    session.add(
                        BotMessageCursorModel(
                            conversation_key=key,
                            chat_id=chat_id,
                            user_id=user_id,
                            message_id=message_id,
                        )
                    )
                else:
                    model.chat_id = chat_id
                    model.user_id = user_id
                    model.message_id = message_id
            session.commit()
        return message_id

    def reset(self, conversation_key: str) -> None:
        with SessionLocal() as session:
            model = session.execute(
                select(BotMessageCursorModel).where(BotMessageCursorModel.conversation_key == conversation_key)
            ).scalar_one_or_none()
            if model is not None:
                session.delete(model)
                session.commit()

    def reset_many(self, conversation_keys: list[str]) -> None:
        keys = [str(key or "").strip() for key in conversation_keys if str(key or "").strip()]
        if not keys:
            return
        with SessionLocal() as session:
            rows = session.execute(
                select(BotMessageCursorModel).where(BotMessageCursorModel.conversation_key.in_(keys))
            ).scalars().all()
            for row in rows:
                session.delete(row)
            if rows:
                session.commit()
