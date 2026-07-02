from __future__ import annotations

from typing import Optional

from app.repositories.bot_message_cursor_repository import BotMessageCursorRepository


class PersistentBotMessageCursorStore:
    def __init__(self) -> None:
        self.repository = BotMessageCursorRepository()

    def get(self, conversation_key: str) -> Optional[str]:
        return self.repository.get(conversation_key)

    def get_many(self, conversation_keys: list[str]) -> dict[str, str]:
        return self.repository.get_many(conversation_keys)

    def get_chat_id_for_user(self, user_id: str) -> Optional[str]:
        return self.repository.get_chat_id_for_user(user_id)

    def set(self, conversation_key: str, chat_id: str, user_id: str, message_id: str) -> str:
        return self.repository.save(conversation_key, chat_id, user_id, message_id)

    def set_many(self, conversation_keys: list[str], chat_id: str, user_id: str, message_id: str) -> str:
        return self.repository.save_many(conversation_keys, chat_id, user_id, message_id)

    def reset(self, conversation_key: str) -> None:
        self.repository.reset(conversation_key)

    def reset_many(self, conversation_keys: list[str]) -> None:
        self.repository.reset_many(conversation_keys)


bot_message_cursor_store = PersistentBotMessageCursorStore()
