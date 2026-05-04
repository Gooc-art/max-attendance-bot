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
4. Import SKUD files and create attendance cases.
5. Save runtime cases and approvals in SQLite.
6. Expose a visible `Старт` button in every role menu; `/start` remains the underlying command.
7. Expose a dedicated `Админ-панель` screen for users with the `admin` role.
8. Expose read-only admin diagnostics for current MAX identity and Google Sheets binding.

## Operational notes
- Google service account path and spreadsheet id are configured in `.env`.
- If Google Sheets is unavailable, the bot must continue with local data.
- Any change in role logic must be covered by tests before deployment.
