# WARP

## Operating rules
- Use Google Sheets as the runtime source for roles and employee directory data when configured.
- Keep SQLite as a fallback cache and operational store.
- Update docs, scripts, and tests whenever behavior changes.
- Prefer reversible, observable terminal commands.

## Current runtime data flow
1. Resolve role from Google Sheets `Сотрудники` with a short-lived cache on incoming events.
2. If Google Sheets returns a quota or transport error, fall back to the last cached directory and then to local role overrides and local employee directory.
3. Render role-based MAX menus.
4. Display role names in Russian in user-facing interfaces while keeping technical role codes internal.
5. Import SKUD files and create attendance cases. If a MAX file attachment arrives without a direct download URL, rehydrate the source message by `message_id` before rejecting the upload.
6. Save runtime cases and approvals in SQLite.
7. Expose a visible `Старт` button in every role menu; `/start` remains the underlying command.
8. Expose a dedicated `Админ-панель` screen for users with the `admin` role.
9. Expose read-only admin diagnostics for current MAX identity and Google Sheets binding.
10. Let the employee pick a manager from a shortlist before submitting a reason.
11. Send a push notification to the selected manager when an employee submits a reason, with approval actions attached.
12. Restrict SKUD file uploads to the `Служба безопасности` role.
13. Provide substitution draft actions in the bot: list, cancel, and extend.
14. Generate `.xlsx` and `.pdf` reports, including department breakdown reports, and send them to MAX as files with public download URLs as fallback.
15. Bootstrap `Сотрудники` and `Подразделения` in Google Sheets from `staff_catalog.json` and `staff_bindings.json` via `create_google_sheet.py`.
16. Resolve SKUD planned start times and grace windows from Google Sheets `Графики` when an employee has a schedule assigned, and continue from the last cached schedule snapshot if Google Sheets is temporarily unavailable.
17. Assign bootstrap employee schedules to the five-day schedules `ГР003` or `ГР004` automatically from the employee name pattern instead of using `ГР001` for everyone.
18. Send ordinary MAX replies with `send_message` using a fallback recipient chain: try `chat_id` first for incoming message replies, then `user_id` if needed. Use the same fallback pattern for push notifications and proactive messages. Reserve `answer_callback` for inline keyboard callbacks.

## Operational notes
- Google service account path and spreadsheet id are configured in `.env`.
- If Google Sheets is unavailable, the bot must continue with local data.
- Any change in role logic must be covered by tests before deployment.
