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

    def test_set_device_platform_creates_or_updates_user_activity(self) -> None:
        repo = UserBotActivityRepository()
        user_id = f"test-device-user-{uuid4().hex}"

        self.assertTrue(repo.set_device_platform(user_id=user_id, device_platform="ios"))

        row = repo.get_by_user_id(user_id)
        self.assertIsNotNone(row)
        assert row is not None
        self.assertEqual(row.device_platform, "ios")

    def test_count_by_device_platform_groups_unknown_values(self) -> None:
        repo = UserBotActivityRepository()
        android_user = f"test-device-android-{uuid4().hex}"
        ios_user = f"test-device-ios-{uuid4().hex}"
        unknown_user = f"test-device-unknown-{uuid4().hex}"

        repo.set_device_platform(user_id=android_user, device_platform="android")
        repo.set_device_platform(user_id=ios_user, device_platform="ios")
        repo.set_device_platform(user_id=unknown_user, device_platform="desktop")

        counts = repo.count_by_device_platform()

        self.assertGreaterEqual(counts["android"], 1)
        self.assertGreaterEqual(counts["ios"], 1)
        self.assertGreaterEqual(counts["unknown"], 1)


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

    def count_by_device_platform(self):
        return {"android": 8, "ios": 3, "unknown": 10}

    def list_recent_seen(self, limit: int = 10):
        return [
            SimpleNamespace(
                user_id="u1",
                display_name="Иван Иванов",
                role="manager",
                last_seen_at=None,
                device_platform="android",
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
        self.assertIn("Android: 1", response.outbound.text)
        self.assertIn("Иван Иванов | Начальник отдела | Android |", response.outbound.text)
        self.assertEqual(router.user_bot_activity_repository.touched[0]["started"], False)

    def test_manager_can_open_device_report(self) -> None:
        router = MaxWebhookRouter()
        router.user_bot_activity_repository = _FakeUserBotActivityRepository()

        response = router._device_report("manager")

        self.assertIn("Устройства пользователей", response.outbound.text)
        self.assertIn("Android: 8", response.outbound.text)
        self.assertIn("iOS: 3", response.outbound.text)
        self.assertIn("Неизвестно: 10", response.outbound.text)
        self.assertIn("Определили устройство: 11", response.outbound.text)
        self.assertIn("Всего пользователей: 21", response.outbound.text)


if __name__ == "__main__":
    unittest.main()
