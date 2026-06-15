from __future__ import annotations

import unittest
from types import SimpleNamespace

from app.bot.router import MaxWebhookRouter
from app.domain.enums import AttendanceCaseStatus


class _DirectoryByUser:
    def __init__(self, name: str = "") -> None:
        self.name = name

    def get_by_user_id(self, user_id: str):
        if not self.name:
            return None
        return SimpleNamespace(employee_name=self.name)


class _CaseRepository:
    def __init__(self, rows_by_user=None, rows_by_name=None, pending_by_user=None, pending_by_name=None) -> None:
        self.rows_by_user = rows_by_user or []
        self.rows_by_name = rows_by_name or []
        self.pending_by_user = pending_by_user or []
        self.pending_by_name = pending_by_name or []
        self.requested_names = []

    def list_for_employee_user(self, user_id: str, limit: int = 20):
        return list(self.rows_by_user)

    def list_for_employee_names(self, employee_names, limit: int = 20):
        self.requested_names = list(employee_names)
        return list(self.rows_by_name)

    def list_pending_reason_for_employee(self, user_id: str, limit: int = 20):
        return list(self.pending_by_user)

    def list_pending_reason_for_employee_names(self, employee_names, limit: int = 20):
        self.requested_names = list(employee_names)
        return list(self.pending_by_name)


class EmployeeCaseLookupTests(unittest.TestCase):
    def _router(self, case_repository: _CaseRepository, employee_name: str) -> MaxWebhookRouter:
        router = MaxWebhookRouter()
        router.case_repository = case_repository
        router.google_directory_service = _DirectoryByUser(employee_name)
        router.employee_directory_repository = _DirectoryByUser("")
        return router

    def test_my_lates_falls_back_to_employee_name_when_user_id_has_no_cases(self) -> None:
        case = SimpleNamespace(
            id=42,
            event_date="2026-06-10",
            case_type="late",
            source="skud_report",
            status=AttendanceCaseStatus.AWAITING_EMPLOYEE_REASON.value,
        )
        repository = _CaseRepository(rows_by_name=[case])
        router = self._router(repository, "Иванов Иван Иванович")

        response = router._employee_cases("employee", "max_001")

        self.assertIn("#42 | 2026-06-10 | Опоздание", response.outbound.text)
        self.assertEqual(repository.requested_names, ["Иванов Иван Иванович"])

    def test_pending_reason_falls_back_to_employee_name_when_user_id_has_no_cases(self) -> None:
        case = SimpleNamespace(id=43, event_date="2026-06-11", case_type="late", source="skud_report")
        repository = _CaseRepository(pending_by_name=[case])
        router = self._router(repository, "Иванов Иван Иванович")

        response = router._employee_pending_reason_cases("employee", "max_001")

        self.assertIn("#43 | 2026-06-11 | Опоздание", response.outbound.text)
        self.assertEqual(repository.requested_names, ["Иванов Иван Иванович"])


if __name__ == "__main__":
    unittest.main()
