from __future__ import annotations

from app.domain.dialog_state import UserDialogState
from app.services.dialog_state import PersistentDialogStateStore


class _FakeRepository:
    def __init__(self):
        self.states = {}

    def get(self, user_id: str):
        return self.states.get(user_id)

    def save(self, user_id: str, state: UserDialogState):
        self.states[user_id] = state
        return state

    def reset(self, user_id: str):
        self.states.pop(user_id, None)


def test_dialog_state_store_serves_hot_state_from_memory():
    store = PersistentDialogStateStore()
    store.repository = _FakeRepository()

    state = UserDialogState(flow="running_late", step="choose_manager", data={"manager_options": {"1": "A"}})
    store.set("u1", state)
    state.data["manager_options"]["1"] = "mutated"

    cached = store.get("u1")

    assert cached is not None
    assert cached.data["manager_options"]["1"] == "A"

    store.reset("u1")

    assert store.get("u1") is None
