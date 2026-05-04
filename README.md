# Attendance Bot

Проект сейчас состоит из двух частей:

- `create_google_sheet.py` — настройка Google Sheets со справочниками
- `app/` — backend-оболочка бота для MAX на `FastAPI`

## Структура

```text
attendance-bot/
  app/
    api/
    bot/
    integrations/
    schemas/
    services/
  create_google_sheet.py
  .env
  data/
  requirements.txt
```

## Переменные окружения

Файл `.env`:

```env
MAX_BOT_TOKEN=
MAX_BOT_SECRET=
MAX_BOT_WEBHOOK_URL=
APP_HOST=0.0.0.0
APP_PORT=8000
APP_DEBUG=true
DATABASE_URL=sqlite:///./data/attendance_bot.db
```

## Запуск backend на Mac

```bash
cd ~/attendance-bot
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

## Регистрация webhook в MAX

После обновления `MAX_BOT_WEBHOOK_URL` и `MAX_BOT_SECRET`:

```bash
cd ~/attendance-bot
source .venv/bin/activate
python3 scripts/register_max_webhook.py
```

## Полезные URL

- `GET /` — корневой статус
- `GET /api/health` — healthcheck
- `POST /api/webhooks/max` — webhook-заглушка под MAX
- `GET /docs` — Swagger UI

## Пример webhook payload

```json
{
  "event_type": "message",
  "text": "/start",
  "user": {
    "id": "mgr_001",
    "username": "manager.test",
    "full_name": "Тестовый Руководитель"
  },
  "chat": {
    "id": "private_001",
    "type": "private"
  }
}
```

## Пример нажатия кнопки

```json
{
  "event_type": "message",
  "action": "menu.substitutions",
  "text": "Замещения",
  "user": {
    "id": "mgr_001",
    "username": "manager.test",
    "full_name": "Тестовый Руководитель"
  },
  "chat": {
    "id": "private_001",
    "type": "private"
  }
}
```

## Быстрый тест сценария замещения

1. Отправить стартовое сообщение:

```json
{
  "event_type": "message",
  "text": "/start",
  "user": {
    "id": "mgr_001",
    "username": "manager.test",
    "full_name": "Тестовый Руководитель"
  },
  "chat": {
    "id": "private_001",
    "type": "private"
  }
}
```

2. Затем последовательно отправлять в тот же webhook.

Для кнопок лучше отправлять `action`, а для свободного ввода обычный `text`.

- `action=menu.substitutions`, `text=Замещения`
- `action=substitution.create`, `text=Назначить замещение`
- `Петров Петр Сергеевич`
- `Волков Игорь Павлович`
- `action=Отпуск`, `text=Отпуск`
- `2026-07-01`
- `2026-07-14`
- `action=Согласования и отчеты`, `text=Согласования и отчеты`
- `action=common.confirm`, `text=Подтвердить`

## Текущий статус

Уже готово:

- конфиг из `.env`
- каркас `FastAPI`
- постоянная SQLite БД для MVP
- webhook-роут для MAX
- регистрация webhook в MAX на живой tunnel URL
- кнопочное ролевое меню с action-кодами
- заглушка клиента MAX API
- сценарий `Назначить замещение` с пошаговым состоянием в памяти
- кнопочные разделы `Замещения`, `Согласования`, `Отчеты`
- сохранение шагов диалога и черновиков замещений в БД

Следующий этап:

- модели сотрудников, нарушений и согласований
- сценарии `Согласования`, `Отчеты`, `Импорт СКУД`
- импорт СКУД
- маршрутизация согласований и замещений
