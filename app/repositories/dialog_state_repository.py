from __future__ import annotations

import json
from datetime import timedelta
from typing import Optional

from sqlalchemy import select

from app.db.base import SessionLocal
from app.db.models import DialogStateModel, utc_now
from app.domain.dialog_state import UserDialogState

STALE_STATE_TTL = timedelta(hours=24)


class DialogStateRepository:
    def get(self, user_id: str) -> Optional[UserDialogState]:
        with SessionLocal() as session:
            model = session.execute(
                select(DialogStateModel).where(DialogStateModel.user_id == user_id)
            ).scalar_one_or_none()
            if not model:
                return None
            if model.updated_at and utc_now() - model.updated_at > STALE_STATE_TTL:
                session.delete(model)
                session.commit()
                return None
            return UserDialogState(
                flow=model.flow,
                step=model.step,
                data=json.loads(model.data_json or "{}"),
            )

    def save(self, user_id: str, state: UserDialogState) -> UserDialogState:
        payload = json.dumps(state.data, ensure_ascii=False)
        with SessionLocal() as session:
            model = session.execute(
                select(DialogStateModel).where(DialogStateModel.user_id == user_id)
            ).scalar_one_or_none()
            if model is None:
                model = DialogStateModel(
                    user_id=user_id,
                    flow=state.flow,
                    step=state.step,
                    data_json=payload,
                )
                session.add(model)
            else:
                model.flow = state.flow
                model.step = state.step
                model.data_json = payload
            session.commit()
        return state

    def reset(self, user_id: str) -> None:
        with SessionLocal() as session:
            model = session.execute(
                select(DialogStateModel).where(DialogStateModel.user_id == user_id)
            ).scalar_one_or_none()
            if model is not None:
                session.delete(model)
                session.commit()
