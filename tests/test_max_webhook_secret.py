from __future__ import annotations

import unittest
from unittest.mock import patch

from fastapi import HTTPException

from app.api.routes import max_webhook
from app.schemas.max import MaxOutboundButton, MaxOutboundMessage, MaxUpdate


class MaxWebhookSecretTests(unittest.TestCase):
    def test_missing_secret_header_is_accepted(self) -> None:
        payload = MaxUpdate(update_type="bot_started", timestamp=1)
        response_model = max_webhook.MaxWebhookResponse(
            ok=True,
            role="admin",
            menu=["Старт"],
            outbound=MaxOutboundMessage(text="Главное меню готово.", buttons=[]),
            active_flow=None,
        )

        with patch.object(max_webhook.webhook_router, "handle_event", return_value=response_model) as handle_event:
            response = max_webhook.receive_max_webhook(payload, x_max_bot_api_secret="")

        self.assertEqual(response, response_model)
        handle_event.assert_called_once_with(payload)

    def test_explicit_wrong_secret_header_is_rejected(self) -> None:
        payload = MaxUpdate(update_type="bot_started", timestamp=1)

        with self.assertRaises(HTTPException) as ctx:
            max_webhook.receive_max_webhook(payload, x_max_bot_api_secret="wrong-secret")

        self.assertEqual(ctx.exception.status_code, 403)


if __name__ == "__main__":
    unittest.main()
