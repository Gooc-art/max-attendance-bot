from __future__ import annotations

from uuid import uuid4

from app.db.base import SessionLocal
from app.db.models import DialogStateModel, utc_now
from app.domain.dialog_state import UserDialogState
from app.repositories.dialog_state_repository import STALE_STATE_TTL, DialogStateRepository
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


def test_dialog_state_store_drops_stale_memory_state():
    store = PersistentDialogStateStore()
    store.repository = _FakeRepository()
    state = UserDialogState(flow="running_late", step="choose_manager", data={"manager_options": {"1": "A"}})

    store._cache["u-old"] = (utc_now() - STALE_STATE_TTL * 2, state)

    assert store.get("u-old") is None


def test_dialog_state_repository_deletes_stale_db_state():
    user_id = f"dialog-{uuid4().hex}"
    with SessionLocal() as session:
        session.add(
            DialogStateModel(
                user_id=user_id,
                flow="running_late",
                step="choose_manager",
                data_json="{}",
                updated_at=utc_now() - STALE_STATE_TTL * 2,
            )
        )
        session.commit()

    assert DialogStateRepository().get(user_id) is None

    with SessionLocal() as session:
        assert session.query(DialogStateModel).filter(DialogStateModel.user_id == user_id).one_or_none() is None
