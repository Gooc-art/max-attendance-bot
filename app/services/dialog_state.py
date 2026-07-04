from __future__ import annotations

import copy
import logging
import queue
import threading
from typing import Optional

from app.domain.dialog_state import UserDialogState
from app.repositories.dialog_state_repository import DialogStateRepository


class PersistentDialogStateStore:
    def __init__(self) -> None:
        self.repository = DialogStateRepository()
        self._cache: dict[str, Optional[UserDialogState]] = {}
        self._lock = threading.Lock()
        self._writes: queue.Queue[tuple[str, str, Optional[UserDialogState]]] = queue.Queue()
        self._logger = logging.getLogger(__name__)
        threading.Thread(target=self._write_worker, daemon=True).start()

    def get(self, user_id: str) -> Optional[UserDialogState]:
        user_id = str(user_id or "").strip()
        with self._lock:
            if user_id in self._cache:
                return self._copy_state(self._cache[user_id])
        state = self.repository.get(user_id)
        with self._lock:
            self._cache[user_id] = self._copy_state(state)
        return self._copy_state(state)

    def set(self, user_id: str, state: UserDialogState) -> UserDialogState:
        user_id = str(user_id or "").strip()
        snapshot = self._copy_state(state)
        with self._lock:
            self._cache[user_id] = self._copy_state(snapshot)
        self._writes.put(("set", user_id, snapshot))
        return state

    def reset(self, user_id: str) -> None:
        user_id = str(user_id or "").strip()
        with self._lock:
            self._cache[user_id] = None
        self._writes.put(("reset", user_id, None))

    @staticmethod
    def _copy_state(state: Optional[UserDialogState]) -> Optional[UserDialogState]:
        if state is None:
            return None
        return UserDialogState(flow=state.flow, step=state.step, data=copy.deepcopy(state.data))

    def _write_worker(self) -> None:
        while True:
            action, user_id, state = self._writes.get()
            try:
                if action == "set" and state is not None:
                    self.repository.save(user_id, state)
                elif action == "reset":
                    self.repository.reset(user_id)
            except Exception:
                self._logger.exception("Dialog state background write failed action=%s user_id=%s", action, user_id)
            finally:
                self._writes.task_done()


dialog_state_store = PersistentDialogStateStore()
