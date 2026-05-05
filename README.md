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
GOOGLE_SERVICE_ACCOUNT_FILE=/Users/goocbk.ru/secure/attendance-max-bot-service-account.json
GOOGLE_SHEETS_SPREADSHEET_ID=1tg5umqy7-72LMLEaXu6n29OvGDSpkOE_adw_7PxsP54
GOOGLE_SHEETS_EMPLOYEE_RANGE=Сотрудники!A:Q
GOOGLE_SHEETS_CACHE_TTL_SECONDS=300
```

## Запуск backend на Mac

```bash
cd ~/attendance-bot
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8001
```

## Прод-режим на Mac mini

Проект рассчитан на два `launchd`-сервиса:

- `com.gooc.attendancebot.backend` — backend на `uvicorn`
- `com.gooc.attendancebot.tunnel` — tunnel в `localhost.run` с автоперерегистрацией webhook

Установка:

```bash
cd ~/attendance-bot
chmod +x scripts/*.sh
./scripts/install_launchd.sh
```

Проверка:

```bash
launchctl list | grep attendancebot
tail -f ~/attendance-bot/logs/backend.stderr.log
tail -f ~/attendance-bot/logs/localhostrun.log
cat ~/attendance-bot/run/localhostrun.url
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
- `POST /api/imports/skud/csv?filename=...&created_by_user_id=...` — импорт CSV выгрузки СКУД
- `GET /api/imports/skud` — история импортов
- `GET /docs` — Swagger UI

## Загрузка файла через MAX

Роль `security` может отправить в бот вложение `csv` или `xlsx`.

Бот:

- скачает файл из attachment `payload.url`
- сохранит его в `data/uploads/skud/`
- создаст кейсы через импорт СКУД
- ответит кратким итогом обработки

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
- inline-кнопки с emoji-иконками и группировкой по рядам; MAX не поддерживает картинки внутри самой кнопки
- видимая кнопка `Старт` для всех ролей
- отдельная `Админ-панель` для роли `admin`
- read-only админ-диагностика: `Кто я`, `Моя строка`, `Проверить привязку`
- заглушка клиента MAX API
- сценарий `Назначить замещение` с пошаговым состоянием в памяти
- кнопочные разделы `Замещения`, `Согласования`, `Отчеты`
- сохранение шагов диалога и черновиков замещений в БД
- demo-согласования с inline-кнопками в MAX
- прод-скрипты для `launchd` и tunnel
- employee-flow: `Мои опоздания`, `Указать причину`, `Мои статусы`
- после выбора причины сотрудником руководитель получает push-уведомление с кнопками согласования
- CSV-импорт СКУД через API с записью истории импортов; загрузка файлов доступна только роли `Служба безопасности`
- чтение справочника сотрудников и ролей из Google Sheets как первого источника данных
- отображение ролей в интерфейсе по-русски: `Сотрудник`, `Руководитель`, `Служба безопасности`, `HR`, `Администратор`, `Главный руководитель`

Следующий этап:

- расширение Google Sheets до полноценного источника прав и маршрутов согласования
- реальные маршруты руководителей и замещений без demo-данных
- отчеты по периоду и выгрузка файлов
