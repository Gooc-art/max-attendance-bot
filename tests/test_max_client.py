from __future__ import annotations

import json
import unittest
from unittest.mock import MagicMock, patch

from app.integrations.max.client import MaxApiClient
from app.schemas.max import MaxOutboundButton


class MaxApiClientTests(unittest.TestCase):
    def test_send_message_uses_snake_case_query_names(self) -> None:
        client = MaxApiClient(
            token="token",
            secret="secret",
            base_url="https://platform-api.max.ru/",
            version="1.2.5",
        )

        response = MagicMock()
        response.__enter__.return_value = response
        response.read.return_value = b"{}"
        response.status = 200

        with patch("app.integrations.max.client.urlopen", return_value=response) as mocked:
            client.send_message(chat_id=123, text="hello")

        request = mocked.call_args.args[0]
        self.assertIn("chat_id=123", request.full_url)
        self.assertIn("v=1.2.5", request.full_url)
        self.assertEqual(json.loads(request.data.decode("utf-8"))["text"], "hello")

    def test_answer_callback_uses_snake_case_query_name(self) -> None:
        client = MaxApiClient(
            token="token",
            secret="secret",
            base_url="https://platform-api.max.ru/",
            version="1.2.5",
        )

        response = MagicMock()
        response.__enter__.return_value = response
        response.read.return_value = b"{}"
        response.status = 200

        with patch("app.integrations.max.client.urlopen", return_value=response) as mocked:
            client.answer_callback(callback_id="cb-1", notification="ok")

        request = mocked.call_args.args[0]
        self.assertIn("callback_id=cb-1", request.full_url)

    def test_inline_keyboard_uses_emoji_and_row_grouping(self) -> None:
        client = MaxApiClient(
            token="token",
            secret="secret",
            base_url="https://platform-api.max.ru/",
            version="1.2.5",
        )

        attachments = client.build_inline_keyboard(
            [
                MaxOutboundButton(title="Старт", action="/start", emoji="🏁", row=0),
                MaxOutboundButton(title="Кто я", action="/whoami", emoji="👤", row=0),
                MaxOutboundButton(title="Отчеты", action="reports", emoji="📊", row=1),
            ]
        )

        self.assertEqual(len(attachments), 1)
        rows = attachments[0].payload.buttons
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0][0].text, "🏁 Старт")
        self.assertEqual(rows[0][1].text, "👤 Кто я")
        self.assertEqual(rows[1][0].text, "📊 Отчеты")


if __name__ == "__main__":
    unittest.main()
