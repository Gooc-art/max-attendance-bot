from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.polling import (
    extract_response_marker,
    extract_update_marker,
    extract_update_payload,
    extract_updates,
    handle_polled_update,
)


def test_extract_updates_accepts_common_response_shapes() -> None:
    assert extract_updates({"updates": [{"id": 1}], "marker": "m2"}) == [{"id": 1}]
    assert extract_updates({"items": [{"id": 2}]}) == [{"id": 2}]
    assert extract_updates({"updates": ["bad", {"id": 3}]}) == [{"id": 3}]


def test_extract_marker_helpers() -> None:
    assert extract_response_marker({"next_marker": "m3"}) == "m3"
    assert extract_update_marker({"update_id": 42}) == "42"
    assert extract_update_payload({"update": {"update_type": "bot_started"}}) == {"update_type": "bot_started"}


def test_handle_polled_update_uses_existing_router_and_dedup() -> None:
    router = MagicMock()
    router.incoming_dedup_key.return_value = "in:key"
    markers = MagicMock()
    markers.claim.return_value = True
    raw = {
        "marker": "m1",
        "update": {
            "update_type": "bot_started",
            "timestamp": 1,
            "user": {"user_id": 123, "first_name": "Test"},
        },
    }

    assert handle_polled_update(router, markers, raw) is True

    router.handle_event.assert_called_once()
    markers.claim.assert_called_once_with("in:key", "incoming", lease_seconds=120)
    markers.complete.assert_called_once_with("in:key", ttl_seconds=600)


def test_handle_polled_update_keeps_marker_on_router_failure() -> None:
    router = MagicMock()
    router.incoming_dedup_key.return_value = "in:key"
    router.handle_event.side_effect = RuntimeError("boom")
    markers = MagicMock()
    markers.claim.return_value = True
    raw = {
        "marker": "m1",
        "update": {
            "update_type": "bot_started",
            "timestamp": 1,
            "user": {"user_id": 123, "first_name": "Test"},
        },
    }

    assert handle_polled_update(router, markers, raw) is False
    markers.release.assert_called_once_with("in:key")
    markers.complete.assert_not_called()


def test_run_polling_uses_fast_callback_router(monkeypatch) -> None:
    from app import polling

    client = MagicMock()
    client.get_updates.side_effect = KeyboardInterrupt
    router_cls = MagicMock()
    settings = SimpleNamespace(
        app_debug=False,
        polling_marker_file="run/test.marker",
        polling_timeout_seconds=1,
        polling_limit=100,
        polling_idle_sleep_seconds=1,
        polling_error_sleep_seconds=1,
    )

    monkeypatch.setattr(polling, "get_settings", lambda: settings)
    monkeypatch.setattr(polling, "init_db", lambda: None)
    monkeypatch.setattr(polling.MaxApiClient, "from_settings", lambda: client)
    monkeypatch.setattr(polling, "MaxWebhookRouter", router_cls)
    monkeypatch.setattr(polling, "RuntimeMarkerRepository", MagicMock)
    monkeypatch.setattr(polling, "load_marker", lambda path: "")

    with pytest.raises(KeyboardInterrupt):
        polling.run_polling()

    router_cls.assert_called_once_with(async_callback_outbound=False, async_user_activity=True)
    client.unsubscribe_all_webhooks.assert_called_once()
    assert client.request_timeout_seconds == 6
