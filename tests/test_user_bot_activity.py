from __future__ import annotations

import unittest
from uuid import uuid4
from types import SimpleNamespace
from unittest.mock import MagicMock

from app.bot.router import MaxWebhookRouter
from app.repositories.user_bot_activity_repository import UserBotActivityRepository
from app.schemas.max import MaxMessage, MaxMessageBody, MaxRecipient, MaxUpdate, MaxUser


class UserBotActivityRepositoryTests(unittest.TestCase):
    def test_touch_updates_start_and_interaction_counters(self) -> None:
        repo = UserBotActivityRepository()
        user_id = f"test-bot-activity-user-{uuid4().hex}"

        repo.touch(user_id=user_id, display_name="Test User", role="top_manager", started=True)
        repo.touch(user_id=user_id, display_name="Test User", role="top_manager", started=False)

        row = repo.get_by_user_id(user_id)

        self.assertIsNotNone(row)
        assert row is not None
        self.assertEqual(row.display_name, "Test User")
        self.assertEqual(row.role, "top_manager")
        self.assertEqual(row.start_count, 1)
        self.assertGreaterEqual(row.interaction_count, 2)
        self.assertIsNotNone(row.first_start_at)
        self.assertIsNotNone(row.last_start_at)


class _FakeRoleResolver:
    def resolve_role(self, user_id: str, chat_id: str) -> str:
        return "top_manager"


class _FakeUserBotActivityRepository:
    def __init__(self) -> None:
        self.touched = []

    def touch(self, *, user_id: str, display_name: str, role: str, started: bool):
        self.touched.append(
            {"user_id": user_id, "display_name": display_name, "role": role, "started": started}
        )
        return None

    def count_seen_total(self) -> int:
        return 21

    def count_started_total(self) -> int:
        return 12

    def count_started_since(self, dt) -> int:
        return 5

    def count_active_since(self, dt) -> int:
        return 9

    def list_recent_seen(self, limit: int = 10):
        return [
            SimpleNamespace(
                user_id="u1",
                display_name="Иван Иванов",
                role="manager",
                last_seen_at=None,
            ),
        ]

    def list_recent_started(self, limit: int = 10):
        return [
            SimpleNamespace(
                user_id="u1",
                display_name="Иван Иванов",
                role="manager",
                last_start_at=None,
            ),
        ]


class _FakeEmployeeDirectoryRepository:
    def get_by_user_id(self, user_id: str):
        return None


class TopBotActivityRouteTests(unittest.TestCase):
    def test_top_manager_can_open_bot_activity_screen(self) -> None:
        router = MaxWebhookRouter()
        router.max_client = MagicMock()
        router.max_client.is_configured.return_value = False
        router.role_resolver = _FakeRoleResolver()
        router.user_bot_activity_repository = _FakeUserBotActivityRepository()
        router.employee_directory_repository = _FakeEmployeeDirectoryRepository()

        payload = MaxUpdate(
            update_type="message_created",
            timestamp=1,
            message=MaxMessage(
                recipient=MaxRecipient(chat_id=987, chat_type="dialog", user_id=203302812),
                timestamp=1,
                body=MaxMessageBody(mid="m1", seq=1, text="Входы"),
                sender=MaxUser(user_id=203302812, first_name="Test", last_name="Top"),
            ),
        )

        response = router.handle_event(payload)

        self.assertIn("Входы в бот", response.outbound.text)
        self.assertIn("Вообще были в боте: 21", response.outbound.text)
        self.assertIn("Запускали бот всего: 12", response.outbound.text)
        self.assertEqual(router.user_bot_activity_repository.touched[0]["started"], False)


if __name__ == "__main__":
    unittest.main()
