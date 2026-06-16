# WARP

## Operating rules
- Use Google Sheets as the runtime source for roles and employee directory data when configured.
- Keep SQLite as a fallback cache and operational store.
- Update docs, scripts, and tests whenever behavior changes.
- Prefer reversible, observable terminal commands.
- Use `~/skud` as the canonical project path; keep `~/attendance-bot` only as a compatibility symlink during migration.

## Current runtime data flow
1. Resolve role from Google Sheets `Сотрудники` with a short-lived cached and indexed lookup on incoming events.
2. If Google Sheets returns a quota or transport error, fall back to the last cached directory and then to local role overrides and local employee directory.
3. Render role-based MAX menus.
4. Display role names in Russian in user-facing interfaces while keeping technical role codes internal; `manager` is shown as `Начальник отдела`.
5. Import SKUD files, create attendance cases, and persist daily visit records with first entry, last exit, and arrival/departure status. If a MAX file attachment arrives without a direct download URL, rehydrate the source message by `message_id` before rejecting the upload.
6. Save runtime cases and approvals in SQLite.
7. Keep `/start` as the underlying command, but do not force a redundant visible `Старт` button in compact employee and manager menus.
8. Expose compact sectioned menus for every role, not only `admin`, so the keyboard fits comfortably on mobile.
9. Lay out inline buttons adaptively: long labels should move to dedicated rows instead of sharing cramped two-column rows.
10. Compute button width from the real rendered label, including emoji prefixes, so mobile row layout stays conservative and buttons do not overflow the MAX viewport.
11. Expose read-only admin diagnostics for current MAX identity and Google Sheets binding.
12. Keep the employee cabinet compact: main menu sections should be `Статистика`, `Опоздания`, and `Руководство`, without a redundant `Старт` button.
13. Let the employee use a `Забыл чип` flow: choose a manager, enter arrival time manually, and send the case to approval.
14. Let the employee use an `Опаздываю` flow: choose a manager, choose `Сегодня` or `Завтра`, then choose a reason. For true late reasons ask for `Опаздываю с`; for `Другое`, collect a free-text reason first; for planned absence use `Буду отсутствовать`, ask period start/end and a free-text reason, then send the notice to approval. Managers use the same `Опаздываю` flow from the main menu, but approvals are routed to top managers.
15. Let the employee shorten an already submitted absence period through the case card with `Выйду раньше`: ask for a new end date, update the reason text, and reopen manager approval for the change.
16. Keep the manager cabinet compact: main menu sections should be `Опаздываю`, `Команда`, `Согласования`, `Отчеты`, and `Замещения`, without duplicated entry points like repeated `Сводка`, `Просроченные согласования`, or `Замещения`.
17. Keep the top-manager cabinet compact too: main menu sections should be `Аналитика`, `Согласования`, `Отчеты`, and `Замещения`, without a separate duplicated `Процессы` section.
18. Present substitution actions in compact user language for managers and top managers: `На период`, `Снять замещение`, and `Продлить`.
19. Model substitutions as a request from the manager/top manager being replaced: the initiator requests a period, picks who will replace them, chooses departments for temporary curation, and the selected replacement employee must explicitly approve or reject it.
20. Approved department curation extends the replacement user's manager views for the covered period: team, approvals, case lists, and reports include the curated departments.
20.1. Active approved substitutions also replace the substituted manager in employee manager-pick flows for covered departments, including `Опаздываю`: employees should choose the replacement, not the absent manager, while the substitution is active.
21. Manager push notifications for reasons and attendance notices should expose a compact `Открыть` button, not a direct `Согласовать` action in the push itself. After approval or rejection, notify the requester with the decision and approver name; if the case has no requester MAX ID, resolve it from the employee directory by name, and if MAX rejects delivery by `user_id`, retry through the saved dialog `chat_id`.
22. Keep the security cabinet compact: main menu sections should be `СКУД` and `Разбор`; `История` belongs only to `СКУД`, while review queues belong only to `Разбор`.
23. Placeholder review screens inside security `Разбор` should return only to `Разбор` with `Назад`, without duplicate shortcuts into `СКУД`.
24. During SKUD import, try to match same-day `late_notice` cases by employee and date; if a match exists, update that case with factual arrival time instead of creating a duplicate late case.
25. Send a push notification to the selected manager when an employee submits a reason, with approval actions attached.
26. Restrict SKUD file uploads to the `Руководитель`, `Служба безопасности`, `Администратор`, and `Главный руководитель` roles.
27. Provide substitution draft actions in the bot: list, cancel, and extend.
28. Generate `.xlsx` and `.pdf` reports, including department breakdown reports, and send them to MAX as files with public download URLs as fallback. Button clicks for reports must answer immediately with a short `отчет формируется` message; actual generation and file delivery should continue in the background so callbacks stay responsive. Deliver report artifacts independently: if MAX rejects the PDF, Excel still has to be sent. Report rows should show first entry, last exit, arrival/departure status, employee reason, approver, and approval comment when present. Excel reports should split attendance into status tabs for `Опоздавшие`, `Согласованные опоздания`, `Вовремя`, `Раньше`, `Ушли позже`, `Ушли вовремя`, `Ушли раньше`, plus a full `Случаи` sheet. If daily visit records are empty, fall back to attendance cases so the report still contains data instead of rendering blank. When a new report of the same type is generated for the same user, delete the previous report files and database rows automatically.
29. Bootstrap `Сотрудники` and `Подразделения` in Google Sheets from `staff_catalog.json` and `staff_bindings.json` via `create_google_sheet.py`.
30. Resolve SKUD planned start times, planned end times, lunch policy, and planned work minutes from Google Sheets `Графики` when an employee has a schedule assigned, and continue from the last cached schedule snapshot if Google Sheets is temporarily unavailable.
31. During SKUD import, match employee names against the directory with safe normalization fallbacks: tolerate `ё/е`, trailing punctuation, and truncated patronymics only when they resolve to a single unambiguous employee.
32. Assign bootstrap employee schedules to the five-day schedules `ГР003` or `ГР004` automatically from the employee name pattern instead of using `ГР001` for everyone.
33. Send ordinary MAX replies with `send_message` using a fallback recipient chain: try `chat_id` first for incoming message replies, then `user_id` if needed. Before each new visible reply to a command or inline-button click, clear the previous bot message in that dialog by deleting it through MAX `DELETE /messages`; if delete is rejected, fall back to editing it to an invisible placeholder and removing buttons. Use the same fallback pattern for push notifications and proactive messages. Reserve `answer_callback` for lightweight inline callback acknowledgements only.
33.1. If MAX sends an inline callback without a real `chat_id`, do not send a fresh `send_message` through an old stored chat id, because MAX may reject it with `403`; render through embedded `answer_callback` instead. Clean-chat deletion applies to ordinary events and callbacks that include a usable `chat_id`.
34. For navigation callbacks like `Главное меню`, accept common aliases (`menu.main`, `menu_main`, `main_menu`, `/start`, `Главное меню`) and answer them with a fresh visible message after deleting the previous bot message. Acknowledge the callback separately so the bot stays responsive even when the client does not render inline message edits reliably.
35. Ignore inline keyboard attachments when routing button clicks; only real file uploads should be handed to the SKUD importer.
36. While importing SKUD, overlay approved substitutions onto the covered date range as synthetic day records with zero passes, so the replaced employee is reflected in reports as absent by substitution rather than silently missing.
37. Track SKUD attendance for regular employees, managers, and HR, but skip `top_manager` when building day records and violations.
38. Accept webhook requests without `X-Max-Bot-Api-Secret` for compatibility if MAX omits the header, but reject requests that carry an explicit wrong secret.
39. Keep `DOCX_Связи_ШАБЛОН` as a staging sheet for leadership data; `docx_leadership_sync.py` updates `Сотрудники` from filled manager fields, applies the explicit department-to-manager map provided from the DOCX hierarchy review, backfills department managers across `Сотрудники`, resolves `ID_руководителя` from the manager row in the same sheet, normalizes department names, rebuilds `Подразделения` with department heads, marks department managers with the `Начальник отдела` role, resolves the hierarchy as `Посунько Руслан Юрьевич -> direct deputies -> departments -> employees` using `DOCX_Структура` only as a structural reference, and writes a normalized review sheet `DOCX_Связи_НОРМА`.
40. Keep webhook observability enabled in backend logs: record timing for total webhook handling, role resolution, Google Sheets fetches, dialog-state access, and MAX outbound delivery steps so production slowness can be localized without changing bot behavior.
41. Keep Google Sheets cache longer for runtime role and schedule lookups, and use shorter timeouts for interactive MAX API calls so callback latency stays bounded during network issues.
42. Build a `Трудочасы` report tab from SKUD daily records with planned minutes, worked minutes, lunch deduction, daily balance, weekly balance, and late-compensation flags.
43. Keep MAX webhook self-healing on tunnel rotation: reuse the base URL from `run/localhostrun.url`, normalize it to `/api/webhooks/max`, persist it back into `.env`, and do not clear the last known URL file during tunnel reconnects.
44. Track aggregate bot activity per `user_id` so top-manager `Аналитика -> Входы` can show everyone who has interacted with the bot, separate `/start` launch counters, and the latest recorded activity without parsing raw logs.
45. Accept both raw `Отчет по проходам` SKUD uploads and summary `О сотруднике ...` Excel exports; the latter must produce daily rows and late/absence cases from aggregated day columns instead of falling back to generic CSV-case parsing.
46. When summary SKUD exports have zero or missing aggregate lateness/early-leave minutes, infer arrival and departure status from `Начало дня` / `Конец дня` against the employee schedule so obviously late arrivals do not land in the `Вовремя` sheet.
47. Production code sync must never overwrite runtime state: exclude `.env`, `data/`, `logs/`, and `run/` from deploy rsync so imports, reports, and SQLite state survive code updates.
48. Report workhours sheets should include a separate department breakdown tab and color-code surplus hours in green and deficits in red to make underworked teams and employees visible at a glance.
49. Workhours sheets should be grouped into manager-readable sections: `Просадка`, `Нейтрально`, `Переработка`; negative rows go first, positive rows go into the final block and sort from the largest surplus downward.
50. When schedule rows do not provide explicit planned minutes, infer them from the planned start/end and lunch settings; sort report tabs by descending deviation or balance so the biggest issues stay at the top.
51. For standard split five-day schedules, keep fixed normative day lengths even on fallback parsing: `ГР003 / Девушки` = `429` minutes, `ГР004 / Парни` = `480` minutes.
52. Classify arrival as `late` from the first minute over plan: any positive arrival delta belongs in `Опоздавшие`, only exact zero remains `Вовремя`.
53. In summary `О сотруднике ...` SKUD exports, treat `23:59` and similar "нет выхода" sentinels as a missing exit mark and therefore an absence/progul day, not as overtime.
54. Management reports must separate `Проблемные дни` from ordinary status tabs: missing exits, missing entries, and no-pass days should not inflate `Вовремя`, `Опоздавшие`, or normal departure counters.
55. Manager-facing Excel sheets should be readable without manual cleanup: include `Тип дня`, freeze the header row, add auto-filters, and size columns to content.
56. Weekly late compensation should rely on positive overwork from ordinary days only; missing-pass or incomplete days must not wipe out an otherwise compensated late arrival.
57. Report menus for management roles should support a custom period flow: `За период` and `По отделам` must ask for start and end dates before queueing background report generation.
58. Employee personal case screens should resolve cases by `employee_user_id` first, then fall back to the employee name from the Google Sheets/local directory so imported cases without a MAX ID still appear under `Мои опоздания`, `Объяснить`, `Мои статусы`, and `Статистика`.
59. Office sealing is currently a simple reminder flow for employees with filled `Кабинет`: girls at 17:10, men at 17:55 via `scripts/send_office_seal_reminders.py`. The reminder button is `Спасибо за напоминание`; pressing it only returns `Принято, спасибо.` and does not write to `Журнал`.

## Operational notes
- Google service account path and spreadsheet id are configured in `.env`.
- If Google Sheets is unavailable, the bot must continue with local data.
- Any change in role logic must be covered by tests before deployment.
- Linux production deployment uses a GitHub Actions self-hosted runner labeled `skud-prod`; the runner executes `scripts/deploy_local_linux.sh` locally, preserving `.env`, `data/`, `logs/`, and `run/`, then restarts user-systemd services `skud-backend.service` and `skud-tunnel.service`.
