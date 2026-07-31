from __future__ import annotations

from uuid import uuid4

from sqlalchemy import event

from app.db.base import SessionLocal, engine
from app.db.models import AttendanceDayRecordModel
from app.repositories.attendance_day_record_repository import AttendanceDayRecordRepository


def test_upsert_many_loads_existing_records_in_one_lookup() -> None:
    repo = AttendanceDayRecordRepository()
    marker = uuid4().hex
    keys = [f"test-day-{marker}-{index}" for index in range(3)]
    lookup_count = 0

    def count_lookup(_conn, _cursor, statement, _parameters, _context, _executemany):
        nonlocal lookup_count
        if (
            statement.lstrip().upper().startswith("SELECT")
            and "attendance_day_records" in statement
            and "record_key" in statement
        ):
            lookup_count += 1

    event.listen(engine, "before_cursor_execute", count_lookup)
    try:
        count = repo.upsert_many([
            {"record_key": keys[0], "employee_name": "Первый"},
            {"record_key": keys[1], "employee_name": "Второй"},
            {"record_key": keys[2], "employee_name": "Третий"},
        ])
    finally:
        event.remove(engine, "before_cursor_execute", count_lookup)

    assert count == 3
    assert lookup_count == 1

    with SessionLocal() as session:
        rows = session.query(AttendanceDayRecordModel).filter(AttendanceDayRecordModel.record_key.in_(keys)).all()
        for row in rows:
            session.delete(row)
        session.commit()
