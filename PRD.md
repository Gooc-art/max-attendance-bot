# PRD

## Goal
Build a MAX bot for attendance control that reads employee rights and directory data from Google Sheets, falls back to local SQLite when needed, and routes attendance cases to the correct managers and substitutes.

## Source of truth
- Google Sheets `Сотрудники` is the first runtime source for:
  - role resolution
  - employee directory lookup
  - manager lookup
- The initial spreadsheet population is bootstrapped from `staff_catalog.json` and `staff_bindings.json` via `create_google_sheet.py`.
- During bootstrap, employee schedules are assigned automatically to the five-day schedules `ГР003` or `ГР004` based on the name pattern, so the attendance importer can use weekday schedules without manual per-row edits.
- Local SQLite remains a fallback/cache for imported data and runtime cases.

## Functional scope
- Read user roles from Google Sheets.
- Show role-based MAX menus with Russian display labels for people-facing UI.
- Read employee directory, departments, and managers from Google Sheets.
- Import SKUD reports and create late/absence cases.
- Resolve planned start times and grace windows from Google Sheets `Графики` when an employee has a schedule assigned.
- Support employee reason selection, manager choice from a shortlist, and manager approvals.
- Notify the selected manager immediately when the employee submits a reason.
- Restrict SKUD upload actions to the `Служба безопасности` role.
- Support substitution drafts and future substitution CRUD.
- Support substitution draft actions: list, cancel, and extend.
- Generate downloadable `.xlsx` and `.pdf` reports with public download URLs.
- Send normal MAX replies with `send_message` on incoming message events, and use `answer_callback` for inline keyboard callbacks.

## Constraints
- No manual file edits for runtime permissions.
- No hard dependency on local demo data.
- Google Sheets reads must be cached and fail gracefully to SQLite fallback.

## Success criteria
- Admin users with `admin` role in Google Sheets see admin-only sections.
- Manager and employee menus reflect the spreadsheet without code changes.
- User-facing role names are shown in Russian while internal role codes remain stable.
- SKUD import still works when Google Sheets is unavailable, using local fallback.
