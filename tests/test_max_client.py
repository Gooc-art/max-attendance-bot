from __future__ import annotations

import json
import unittest
from unittest.mock import MagicMock, patch

from app.integrations.max.client import MaxApiClient


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


if __name__ == "__main__":
    unittest.main()
