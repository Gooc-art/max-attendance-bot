from uuid import uuid4

from app.db.base import SessionLocal
from app.db.models import SubstitutionDraftModel
from app.repositories.substitution_repository import SubstitutionRepository


def test_approved_overlap_accepts_dot_dates_from_existing_rows() -> None:
    repo = SubstitutionRepository()
    marker = uuid4().hex
    target = f"Тест Посунько {marker}"

    with SessionLocal() as session:
        draft = SubstitutionDraftModel(
            created_by_user_id=f"creator-{marker}",
            role="top_manager",
            target_manager=target,
            target_user_id=f"target-{marker}",
            replacement_user=f"Тест Кудрявцева {marker}",
            replacement_user_id=f"replacement-{marker}",
            reason="Отпуск",
            date_from="2026.06.25",
            date_to="2026.07.15",
            scope="",
            departments_json='["23. ПО№2"]',
            status="approved",
        )
        session.add(draft)
        session.commit()

    rows = repo.list_approved_overlapping("2026-06-26", "2026-06-26")

    assert any(row.target_manager == target for row in rows)


def test_create_draft_normalizes_dot_dates() -> None:
    repo = SubstitutionRepository()
    marker = uuid4().hex

    draft_id = repo.create_draft(
        created_by_user_id=f"creator-{marker}",
        role="top_manager",
        data={
            "target_manager": f"Тест Посунько {marker}",
            "target_user_id": f"target-{marker}",
            "replacement_user": f"Тест Кудрявцева {marker}",
            "replacement_user_id": f"replacement-{marker}",
            "reason": "Отпуск",
            "date_from": "2026.06.25",
            "date_to": "2026.07.15",
            "departments_json": "[]",
        },
    )

    with SessionLocal() as session:
        draft = session.get(SubstitutionDraftModel, draft_id)

    assert draft is not None
    assert draft.date_from == "2026-06-25"
    assert draft.date_to == "2026-07-15"
