# PRD

## Goal
Build a MAX bot for attendance control that reads employee rights and directory data from Google Sheets, falls back to local SQLite when needed, and routes attendance cases to the correct managers and substitutes.

## Source of truth
- Google Sheets `Сотрудники` is the first runtime source for role resolution and employee directory lookup.
- Manager lookup can also use the sheet, but role resolution should use a short-lived cache and fail over to local data when Google Sheets hits a quota or transport error.
- Google Sheets reads are cached briefly and indexed in memory for direct `user_id`, employee, manager, and schedule lookups; if Sheets returns a quota error, the bot must continue from the last valid cached directory instead of failing the webhook. Schedule reads must follow the same fail-soft behavior so SKUD imports do not break on large files.
- Interactive MAX API calls should use a shorter request timeout than file-transfer paths, so button clicks fail fast instead of blocking the whole webhook for a long time.
- MAX webhook registration must recover automatically from localhost.run URL rotation: reuse `run/localhostrun.url`, normalize it to `/api/webhooks/max`, and persist the refreshed webhook URL back into `.env`.
- The initial spreadsheet population is bootstrapped from `staff_catalog.json` and `staff_bindings.json` via `create_google_sheet.py`.
- During bootstrap, employee schedules are assigned automatically to the five-day schedules `ГР003` or `ГР004` based on the name pattern, so the attendance importer can use weekday schedules without manual per-row edits.
- SKUD imports must resolve employees against the sheet directory not only by strict exact full name, but also by safe normalized variants (`ё/е`, trailing punctuation, truncated patronymic) when the candidate is unique.
- A separate staging sheet `DOCX_Связи_ШАБЛОН` is used for leadership and substitution preparation; `docx_leadership_sync.py` reads it back into `Сотрудники`, keeps `Посунько Руслан Юрьевич` as the top of the hierarchy, uses `DOCX_Структура` as a structural reference, applies the explicit department-to-manager map captured from the DOCX review, backfills department managers across `Сотрудники`, also resolves `ID_руководителя` from the manager row inside `Сотрудники`, normalizes department names, rebuilds the `Подразделения` sheet with department managers, marks department heads with the `Руководитель` role, and creates a normalized review sheet.
- Local SQLite remains a fallback/cache for imported data and runtime cases.

## Functional scope
- Read user roles from Google Sheets.
- Show role-based MAX menus with Russian display labels for people-facing UI.
- Read employee directory, departments, and managers from Google Sheets.
- Import SKUD reports, create late/absence cases, and persist daily visit records with first entry, last exit, and arrival/departure status.
- Support both raw SKUD pass logs (`Отчет по проходам`) and per-employee summary reports (`О сотруднике ...`) where lateness, absence, and day start/end are already aggregated by date.
- When a summary SKUD report contains inconsistent aggregate minutes, derive arrival/departure status from the factual `Начало дня` / `Конец дня` clock values and the employee schedule instead of defaulting to `on_time`.
- Treat any positive arrival delta as late: even `+1 minute` must be classified as `late`, not `on_time`.
- In summary SKUD reports, treat `23:59` or equivalent "no exit" sentinel values in the end-of-day field as a missing evening mark: record the day as an absence/progul rather than as overtime.
- In Excel reports, add a dedicated department-level workhours breakdown and highlight workhour deficits in red and surpluses in green inside the `Трудочасы` views.
- In workhours views, group rows into readable manager blocks: `Просадка`, `Нейтрально`, `Переработка`, with sorting inside each block by the largest deviation first.
- For the standard five-day schedules, enforce normative daily minutes: `429` for `Девушки` (`ГР003`) and `480` for `Парни` (`ГР004`) even when the importer has to reconstruct planned minutes from the schedule identity.
- If `planned_minutes_per_day` is absent in the schedule, infer planned minutes from start/end and lunch, and sort report tabs by descending deviation or balance so the largest outliers appear first.
- Treat incomplete SKUD days as a separate managerial category in reports: missing exit, missing entry, and no-pass days must not be mixed into ordinary `early/on_time/late` status tabs.
- Management reports must show closed totals: separate summary lines for problem days, missing exits, missing entries, no-pass days, and substitutions so the headline counts explain all attendance rows.
- Make the Excel output readable for managers without external tooling: add a `Тип дня` column, freeze the header row, enable auto-filter, and size columns to content.
- Add a report-period dialog for management roles: instead of relying only on fixed week/month/quarter presets, let the bot ask for `date_from` and `date_to` and build both ordinary and division reports for that exact range.
- If MAX sends a file attachment without a direct download URL, rehydrate the original message by `message_id` and resolve the file from there before rejecting the upload.
- Resolve planned start times and grace windows from Google Sheets `Графики` when an employee has a schedule assigned.
- Resolve planned end times, lunch policy, lunch minutes, and planned work minutes from Google Sheets `Графики` when available, with backward-compatible fallback to schedule names and comments.
- Support employee reason selection for imported cases, manager choice from a shortlist, and manager approvals.
- Support a dedicated employee `Забыл чип` scenario: choose a manager, enter the real arrival time manually, and route the case to manager approval.
- Support a dedicated employee `Опаздываю` scenario: choose a manager, then choose the reason. For late reasons request the time from which the employee is late (`Опаздываю с`); for `Другое`, accept a free-text reason before asking that time. For planned absence use one `Буду отсутствовать` reason, request period start/end and a free-text reason. Route the notice to manager approval and persist true late notices for later SKUD matching. Managers also have `Опаздываю` in the main menu; their notices are routed to `Главный руководитель` / `top_manager` approvers.
- Let the employee shorten a previously submitted absence period through the case card: request a new end date, update the period, and reopen manager approval for the change.
- Manager push notifications for new reasons and attendance notices should open the approval card first instead of exposing direct `approve` from the push itself.
- After a manager/top-manager approves or rejects a request, notify the requesting employee or manager with the decision and approver name. If an older case has no requester MAX ID, resolve it from the employee directory by name; if MAX rejects delivery by `user_id`, retry through the saved dialog `chat_id`.
- On SKUD import, match a same-day `late_notice` case by employee and date, update it with the factual arrival time, and avoid creating a duplicate late case when a match exists.
- Notify the selected manager immediately when the employee submits a reason.
- Restrict SKUD upload actions to the `Руководитель`, `Служба безопасности`, `Администратор`, and `Главный руководитель` roles.
- Support substitution drafts and future substitution CRUD.
- Support substitution draft actions: list, cancel, and extend.
- Keep the manager cabinet compact: main entry points should be `Опаздываю`, `Команда`, `Согласования`, `Отчеты`, and `Замещения`, without duplicated navigation into the same function.
- Keep the top-manager cabinet compact too: main entry points should be `Аналитика`, `Согласования`, `Отчеты`, and `Замещения`, without a duplicated `Процессы` section.
- Expose top-manager bot-entry analytics inside `Аналитика`: show how many unique users have interacted with the bot at all, separate `/start` launch counters, and the latest recorded activity.
- Present substitution actions for managers and top managers in compact user-facing language as `На период`, `Снять замещение`, and `Продлить`.
- Model substitution as a request initiated by the employee being replaced: the manager or top manager selects who will replace them for a period, selects departments to hand over for curation, and the selected replacement employee must explicitly approve or reject that request.
- Approved department curation must extend the replacement user's manager views for the covered period: team, approvals, case lists, and reports include the curated departments.
- During SKUD import, treat approved substitutions as justified absence days: add daily attendance rows for the replaced employee even when there were no passes, so reports account for that absence without creating a normal violation.
- During SKUD import, track attendance for employees, managers, and HR, but exclude `top_manager` from daily attendance rows and violation generation.
- Generate `.xlsx` and `.pdf` reports and send them to MAX as files, with public download URLs as fallback. On button click, answer immediately that the report is being generated, then build the report and send the files in the background so callbacks stay responsive. File delivery must be best-effort per artifact: a rejected PDF must not block Excel delivery. Reports should include first entry, last exit, arrival/departure status, employee reason, approver, and approval comment for each day record when available. Excel reports should split attendance into status tabs for `Опоздавшие`, `Согласованные опоздания`, `Вовремя`, `Раньше`, `Ушли позже`, `Ушли вовремя`, `Ушли раньше`, plus a full `Случаи` sheet. If daily visit records are temporarily empty, fall back to attendance cases so reports still render useful data. When a new report of the same type is generated for the same user, the previous report files and database rows should be removed automatically.
- Generate a separate Excel tab `Трудочасы` from daily SKUD records, including day type, planned minutes, worked minutes, lunch deduction, daily balance, weekly balance, and whether late arrivals were compensated by weekly overwork. Compensation should be based on positive weekly overwork, not erased by unrelated missing-pass days.
- Keep MAX dialogs clean: before sending a new visible reply for any incoming command or inline-button click, clear the previous bot message in that dialog by editing it to an invisible placeholder and removing buttons, then send the next screen with `send_message`. Use a fallback recipient chain: try `chat_id` first for incoming message replies, then `user_id` if needed. Use the same fallback pattern for push notifications and proactive messages. Reserve `answer_callback` for lightweight callback acknowledgements without editing the old message.
- Accept webhook requests without `X-Max-Bot-Api-Secret` for compatibility if MAX omits the header, but reject requests that carry an explicit wrong secret.
- Support office sealing confirmation: employees with a filled `Кабинет` can press `Кабинет опломбирован` only on configured workday evening window; the bot immediately writes `Дата`, `Время`, `ID_сотрудника`, `Кабинет`, and a backward-compatible empty `Ссылка_на_фото` to Google Sheets `Журнал`, prevents duplicate same-day entries by office, notifies other employees sharing the same office after the first successful seal, gives employees a `Мой кабинет` status screen, sends employee reminders at 18:00 and 21:30, supports temporary office exceptions through `Исключения_кабинетов`, and lets managers request `/статус` summaries grouped by office.
- For navigation callbacks like `Главное меню`, accept common aliases (`menu.main`, `menu_main`, `main_menu`, `/start`, `Главное меню`) and answer them with a fresh visible message after deleting the previous bot message. Acknowledge the callback separately so menu navigation stays responsive even when the client does not render inline message edits reliably.
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
