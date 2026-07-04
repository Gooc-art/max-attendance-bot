from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from io import BytesIO
from urllib.error import HTTPError
from unittest.mock import MagicMock, patch

from app.integrations.max.client import INVISIBLE_MESSAGE_TEXT, MaxApiClient
from app.bot.buttons import attendance_reason_buttons, reports_menu_buttons, running_late_reason_buttons
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
        self.assertNotIn("user_id=", request.full_url)
        self.assertEqual(json.loads(request.data.decode("utf-8"))["text"], "hello")

    def test_send_message_prefers_chat_id_over_user_id(self) -> None:
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
            client.send_message(chat_id=123, user_id=456, text="hello")

        request = mocked.call_args.args[0]
        self.assertIn("chat_id=123", request.full_url)
        self.assertNotIn("user_id=456", request.full_url)

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

    def test_request_includes_max_http_error_body(self) -> None:
        client = MaxApiClient(
            token="token",
            secret="secret",
            base_url="https://platform-api.max.ru/",
            version="1.2.5",
        )
        error = HTTPError(
            url="https://platform-api.max.ru/answers",
            code=403,
            msg="Forbidden",
            hdrs={},
            fp=BytesIO(b'{"message":"callback expired"}'),
        )

        with patch("app.integrations.max.client.urlopen", side_effect=error):
            with self.assertRaisesRegex(RuntimeError, "HTTP 403"):
                client.answer_callback(callback_id="cb-1", notification="ok")

    def test_delete_message_uses_delete_endpoint(self) -> None:
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
            client.delete_message("mid-42")

        request = mocked.call_args.args[0]
        self.assertEqual(request.method, "DELETE")
        self.assertIn("https://platform-api.max.ru/messages?", request.full_url)
        self.assertIn("message_id=mid-42", request.full_url)
        self.assertIsNone(request.data)

    def test_soft_clear_message_uses_edit_endpoint(self) -> None:
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
            client.soft_clear_message("mid-42")

        request = mocked.call_args.args[0]
        self.assertEqual(request.method, "PUT")
        self.assertIn("https://platform-api.max.ru/messages?", request.full_url)
        self.assertIn("message_id=mid-42", request.full_url)
        body = json.loads(request.data.decode("utf-8"))
        self.assertEqual(body["text"], INVISIBLE_MESSAGE_TEXT)
        self.assertEqual(body["attachments"], [])
        self.assertEqual(body["notify"], False)

    def test_edit_message_updates_text_and_buttons(self) -> None:
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
            client.edit_message(
                "mid-42",
                text="ready",
                buttons=[MaxOutboundButton(title="Старт", action="/start")],
            )

        request = mocked.call_args.args[0]
        self.assertEqual(request.method, "PUT")
        self.assertIn("https://platform-api.max.ru/messages?", request.full_url)
        self.assertIn("message_id=mid-42", request.full_url)
        body = json.loads(request.data.decode("utf-8"))
        self.assertEqual(body["text"], "ready")
        self.assertEqual(body["attachments"][0]["type"], "inline_keyboard")
        self.assertEqual(body["notify"], False)

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
                MaxOutboundButton(title="Обо мне", action="/whoami", emoji="👤", row=0),
                MaxOutboundButton(title="Отчеты", action="reports", emoji="📊", row=1),
            ]
        )

        self.assertEqual(len(attachments), 1)
        rows = attachments[0].payload.buttons
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0][0].text, "🏁 Старт")
        self.assertEqual(rows[0][1].text, "👤 Обо мне")
        self.assertEqual(rows[1][0].text, "📊 Отчеты")

    def test_attendance_reason_buttons_stack_long_labels_vertically(self) -> None:
        buttons = attendance_reason_buttons(101)
        rows_by_title = {button.title: button.row for button in buttons}

        self.assertNotEqual(rows_by_title["Больничный"], rows_by_title["Командировка"])
        self.assertNotEqual(rows_by_title["Удаленка"], rows_by_title["Согласовано"])
        self.assertGreater(rows_by_title["Главное меню"], rows_by_title["Другое"])

    def test_running_late_reason_buttons_stack_vertically(self) -> None:
        buttons = running_late_reason_buttons()
        rows = [button.row for button in buttons if button.title != "Главное меню"]

        self.assertEqual(len(rows), len(set(rows)))

    def test_running_late_reason_buttons_use_only_late_reasons(self) -> None:
        titles = [button.title for button in running_late_reason_buttons()]

        self.assertIn("Указать причину", titles)
        self.assertNotIn("Буду отсутствовать", titles)
        self.assertNotIn("Согласовано", titles)
        self.assertNotIn("Личная причина", titles)
        self.assertNotIn("Другое", titles)
        self.assertNotIn("Отпуск", titles)
        self.assertNotIn("Больничный", titles)
        self.assertNotIn("Командировка", titles)
        self.assertNotIn("Удаленка", titles)

    def test_reports_menu_puts_long_titles_on_separate_rows(self) -> None:
        buttons = reports_menu_buttons()
        rows_by_title = {button.title: button.row for button in buttons}

        self.assertNotEqual(rows_by_title["За период"], rows_by_title["Недельный"])
        self.assertNotEqual(rows_by_title["Недельный"], rows_by_title["Квартал"])

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
        self.assertIn("chat_id=123", request.full_url)
        self.assertNotIn("user_id=", request.full_url)

    def test_send_file_message_retries_when_attachment_is_not_ready(self) -> None:
        client = MaxApiClient(
            token="token",
            secret="secret",
            base_url="https://platform-api.max.ru/",
            version="1.2.5",
        )

        with tempfile.NamedTemporaryFile(suffix=".pdf") as tmp:
            tmp.write(b"report")
            tmp.flush()
            with patch.object(client, "upload_file", return_value={"token": "file-token"}) as upload_file:
                with patch.object(
                    client,
                    "_request",
                    side_effect=[RuntimeError('MAX API POST messages failed: HTTP 400 {"code":"attachment.not.ready"}'), {"ok": True}],
                ) as request:
                    with patch("app.integrations.max.client.time.sleep") as sleep:
                        result = client.send_file_message(chat_id=123, text="report", file_path=tmp.name)

        self.assertEqual(result, {"ok": True})
        upload_file.assert_called_once()
        self.assertEqual(request.call_count, 2)
        sleep.assert_called_once_with(1)


if __name__ == "__main__":
    unittest.main()
