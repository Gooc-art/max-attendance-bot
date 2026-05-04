from __future__ import annotations

from typing import Optional

from app.domain.dialog_state import UserDialogState
from app.repositories.dialog_state_repository import DialogStateRepository


class PersistentDialogStateStore:
    def __init__(self) -> None:
        self.repository = DialogStateRepository()

    def get(self, user_id: str) -> Optional[UserDialogState]:
        return self.repository.get(user_id)

    def set(self, user_id: str, state: UserDialogState) -> UserDialogState:
        return self.repository.save(user_id, state)

    def reset(self, user_id: str) -> None:
        self.repository.reset(user_id)


dialog_state_store = PersistentDialogStateStore()
