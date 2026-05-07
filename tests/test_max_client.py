from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
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

    def test_send_file_message_requests_upload_and_sends_file_attachment(self) -> None:
        client = MaxApiClient(
            token="token",
            secret="secret",
            base_url="https://platform-api.max.ru/",
            version="1.2.5",
        )

        with tempfile.NamedTemporaryFile(suffix=".xlsx") as tmp:
            tmp.write(b"report")
            tmp.flush()
            with patch.object(client, "_get_upload_endpoint", return_value={"url": "https://upload.example", "token": "upload-token"}) as get_upload:
                with patch.object(client, "_multipart_upload", return_value={"token": "file-token"}) as multipart_upload:
                    response = MagicMock()
                    response.__enter__.return_value = response
                    response.read.return_value = b"{}"
                    response.status = 200

                    with patch("app.integrations.max.client.urlopen", return_value=response) as mocked:
                        with patch("pathlib.Path.stat") as stat_mock:
                            stat_mock.return_value.st_size = 123
                            client.send_file_message(chat_id=123, text="report", file_path=tmp.name)

        get_upload.assert_called_once_with("file")
        multipart_upload.assert_called_once()
        request = mocked.call_args.args[0]
        body = json.loads(request.data.decode("utf-8"))
        self.assertEqual(body["attachments"][0]["type"], "file")
        self.assertEqual(body["attachments"][0]["payload"]["token"], "file-token")
        self.assertEqual(body["attachments"][0]["filename"], Path(tmp.name).name)
        self.assertEqual(body["attachments"][0]["size"], 123)


if __name__ == "__main__":
    unittest.main()
