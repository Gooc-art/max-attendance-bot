# WARP

## Operating rules
- Use Google Sheets as the runtime source for roles and employee directory data when configured.
- Keep SQLite as a fallback cache and operational store.
- Update docs, scripts, and tests whenever behavior changes.
- Prefer reversible, observable terminal commands.

## Current runtime data flow
1. Resolve role from Google Sheets `Сотрудники`.
2. Fallback to local role overrides and local employee directory.
3. Render role-based MAX menus.
4. Display role names in Russian in user-facing interfaces while keeping technical role codes internal.
5. Import SKUD files and create attendance cases.
6. Save runtime cases and approvals in SQLite.
7. Expose a visible `Старт` button in every role menu; `/start` remains the underlying command.
8. Expose a dedicated `Админ-панель` screen for users with the `admin` role.
9. Expose read-only admin diagnostics for current MAX identity and Google Sheets binding.
10. Let the employee pick a manager from a shortlist before submitting a reason.
11. Send a push notification to the selected manager when an employee submits a reason, with approval actions attached.
12. Restrict SKUD file uploads to the `Служба безопасности` role.
13. Provide substitution draft actions in the bot: list, cancel, and extend.
14. Generate downloadable `.xlsx` reports, including department breakdown reports, and return a public download URL in report responses.

## Operational notes
- Google service account path and spreadsheet id are configured in `.env`.
- If Google Sheets is unavailable, the bot must continue with local data.
- Any change in role logic must be covered by tests before deployment.
