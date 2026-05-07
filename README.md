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
GOOGLE_SHEETS_SCHEDULE_RANGE=Графики!A:L
GOOGLE_SHEETS_CACHE_TTL_SECONDS=300
```

Роли из `Сотрудники` бот перечитывает свежим запросом при каждом входящем сообщении, чтобы ручные изменения в Google Sheets применялись сразу. Кэш остается для менее критичных справочников и расписаний.

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

## Загрузка справочника сотрудников в Google Sheets

Скрипт `create_google_sheet.py` умеет не только создавать структуру таблицы, но и заполнять листы `Сотрудники` и `Подразделения` из JSON-файлов:

- `/Users/goocbk.ru/attendance-bot/data/staff_catalog.json`
- `/Users/goocbk.ru/attendance-bot/data/staff_bindings.json`

Запуск:

```bash
cd ~/attendance-bot
source .venv/bin/activate
python3 create_google_sheet.py
```

Скрипт перезапишет данные на листах `Сотрудники` и `Подразделения`, сохранив структуру и справочные листы.
При загрузке он автоматически распределяет сотрудников по пятидневным графикам `ГР003` и `ГР004` по ФИО, а `ГР001` остается как резервный справочный график.

## Полезные URL

- `GET /` — корневой статус
- `GET /api/health` — healthcheck
- `POST /api/webhooks/max` — webhook-заглушка под MAX
- `POST /api/imports/skud/csv?filename=...&created_by_user_id=...` — загрузка CSV выгрузки СКУД
- `GET /api/imports/skud` — история импортов
- `GET /api/reports/{token}/download` — скачивание сгенерированного отчета `.xlsx`
- `GET /api/reports/{token}/download/pdf` — скачивание сгенерированного отчета `.pdf`
- `GET /docs` — страница с ручной проверкой запросов

## Загрузка файла через MAX

Роль `security` может отправить в бот вложение `csv` или `xlsx`.

Бот:

- заберет файл из сообщения и разберет его
- сохранит его в `data/uploads/skud/`
- создаст кейсы через импорт СКУД с учетом графика сотрудника из Google Sheets
- ответит кратким итогом обработки

Обычные ответы в MAX отправляются через `send_message` на входящее сообщение, а `answer_callback` используется для inline-кнопок. Отдельный `send_message` остается и для push-уведомлений, и для обычных текстовых ответов бота.

Отчеты по кнопкам `Недельный отчет`, `Месячный отчет`, `Квартальный отчет` и `Отчеты по подразделениям` теперь отправляются в чат как готовые вложения `.xlsx` и `.pdf`, а не только как ссылки на скачивание.

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

## Быстрый тест сценария причины опоздания

1. Отправить `/start`, затем открыть `Мои опоздания`.
2. Открыть случай со статусом `Ожидает ответа сотрудника`.
3. Нажать `Выбрать руководителя`.
4. Выбрать руководителя из списка.
5. Нажать причину опоздания.

Для кнопок сценария причины:

- `action=employee.reason.start:101`, `text=Выбрать руководителя`
- `action=employee.manager:101:mgr-alt`, `text=Смирнов Сергей Олегович`
- `action=employee.reason:101:personal_reason`, `text=Личная причина`

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
- заглушка клиента MAX
- сценарий `Назначить замещение` с пошаговым состоянием в памяти
- кнопочные разделы `Замещения`, `Согласования`, `Отчеты`
- сохранение шагов диалога и черновиков замещений в БД
- в `Замещения` доступны действия `Отменить` и `Продлить` по конкретному черновику
- demo-согласования с inline-кнопками в MAX
- прод-скрипты для `launchd` и tunnel
- employee-flow: `Мои опоздания`, `Указать причину`, `Мои статусы`
- employee-flow теперь выбирает руководителя из списка до выбора причины
- после выбора причины сотрудником руководитель получает push-уведомление с кнопками согласования
- Загрузка файлов СКУД через бота с записью истории импортов; отправлять файлы может только роль `Служба безопасности`
- экранные отчеты теперь дополняются отправкой `.xlsx` и `.pdf` прямо в чат, включая `Отчет по подразделениям`
- чтение справочника сотрудников и ролей из Google Sheets как первого источника данных
- отображение ролей в интерфейсе по-русски: `Сотрудник`, `Руководитель`, `Служба безопасности`, `HR`, `Администратор`, `Главный руководитель`

Следующий этап:

- расширение Google Sheets до полноценного источника прав и маршрутов согласования
- реальные маршруты руководителей и замещений без demo-данных
- отчеты по периоду и выгрузка файлов
