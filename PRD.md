# PRD

## Goal
Build a MAX bot for attendance control that reads employee rights and directory data from Google Sheets, falls back to local SQLite when needed, and routes attendance cases to the correct managers and substitutes.

## Source of truth
- Google Sheets `Сотрудники` is the first runtime source for role resolution and employee directory lookup.
- Manager lookup can also use the sheet, but role resolution should use a short-lived cache and fail over to local data when Google Sheets hits a quota or transport error.
- Google Sheets reads are cached briefly; if Sheets returns a quota error, the bot must continue from the last valid cached directory instead of failing the webhook. Schedule reads must follow the same fail-soft behavior so SKUD imports do not break on large files.
- The initial spreadsheet population is bootstrapped from `staff_catalog.json` and `staff_bindings.json` via `create_google_sheet.py`.
- During bootstrap, employee schedules are assigned automatically to the five-day schedules `ГР003` or `ГР004` based on the name pattern, so the attendance importer can use weekday schedules without manual per-row edits.
- A separate staging sheet `DOCX_Связи_ШАБЛОН` is used for leadership and substitution preparation; `docx_leadership_sync.py` reads it back into `Сотрудники`, keeps `Посунько Руслан Юрьевич` as the top of the hierarchy, uses `DOCX_Структура` to infer departments, infers missing department managers from the branch layout, backfills blank department managers across `Сотрудники`, and creates a normalized review sheet.
- Local SQLite remains a fallback/cache for imported data and runtime cases.

## Functional scope
- Read user roles from Google Sheets.
- Show role-based MAX menus with Russian display labels for people-facing UI.
- Read employee directory, departments, and managers from Google Sheets.
- Import SKUD reports, create late/absence cases, and persist daily visit records with first entry, last exit, and arrival/departure status.
- If MAX sends a file attachment without a direct download URL, rehydrate the original message by `message_id` and resolve the file from there before rejecting the upload.
- Resolve planned start times and grace windows from Google Sheets `Графики` when an employee has a schedule assigned.
- Support employee reason selection, manager choice from a shortlist, and manager approvals.
- Notify the selected manager immediately when the employee submits a reason.
- Restrict SKUD upload actions to the `Служба безопасности` role.
- Support substitution drafts and future substitution CRUD.
- Support substitution draft actions: list, cancel, and extend.
- Generate `.xlsx` and `.pdf` reports and send them to MAX as files, with public download URLs as fallback. Queue file delivery in the background so callbacks stay responsive. Reports should include first entry, last exit, arrival/departure status, employee reason, approver, and approval comment for each day record when available. Excel reports should split attendance into status tabs for `Опоздавшие`, `Вовремя`, `Раньше`, `Ушли позже`, `Ушли вовремя`, `Ушли раньше`, plus a full `Случаи` sheet. If daily visit records are temporarily empty, fall back to attendance cases so reports still render useful data. When a new report of the same type is generated for the same user, the previous report files and database rows should be removed automatically.
- Send normal MAX replies with `send_message` using a fallback recipient chain: try `chat_id` first for incoming message replies, then `user_id` if needed. Use the same fallback pattern for push notifications and proactive messages. Use `answer_callback` for inline keyboard callbacks.
- Ignore inline keyboard attachments when routing text/callback buttons; only real file uploads should reach the SKUD importer.

## Constraints
- No manual file edits for runtime permissions.
- No hard dependency on local demo data.
- Google Sheets reads should be fresh for role resolution, may be cached for lower-priority lookups, and must fail gracefully to SQLite fallback.

## Success criteria
- Roles from Google Sheets are shown through compact sectioned menus for every role so the keyboard stays readable on mobile.
- Manager and employee menus reflect the spreadsheet without code changes.
- User-facing role names are shown in Russian while internal role codes remain stable.
- SKUD import still works when Google Sheets is unavailable, using local fallback.
