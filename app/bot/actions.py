from __future__ import annotations


class BotAction:
    START = "/start"
    MAIN_MENU = "menu.main"

    MENU_MY_NOTIFICATIONS = "menu.my_notifications"
    MENU_MY_LATES = "menu.my_lates"
    MENU_SUBMIT_REASON = "menu.submit_reason"
    MENU_MY_STATUSES = "menu.my_statuses"
    MENU_MY_MANAGER = "menu.my_manager"

    MENU_EMPLOYEES = "menu.employees"
    MENU_APPROVALS = "menu.approvals"
    MENU_DEPARTMENT_LATES = "menu.department_lates"
    MENU_DEPARTMENT_ABSENCES = "menu.department_absences"
    MENU_REPORTS = "menu.reports"
    MENU_SUBSTITUTIONS = "menu.substitutions"

    MENU_SECURITY_IMPORT = "menu.security_import"
    MENU_IMPORT_HISTORY = "menu.import_history"
    MENU_MATCH_ERRORS = "menu.match_errors"
    MENU_UNPROCESSED = "menu.unprocessed"

    MENU_STAFF = "menu.staff"
    MENU_DEPARTMENTS = "menu.departments"
    MENU_SCHEDULES = "menu.schedules"
    MENU_EXCEPTIONS = "menu.exceptions"
    MENU_SETTINGS = "menu.settings"
    MENU_ACCESS_RIGHTS = "menu.access_rights"
    MENU_SUMMARY = "menu.summary"
    MENU_DIVISION_REPORTS = "menu.division_reports"
    MENU_OVERDUE_APPROVALS = "menu.overdue_approvals"

    SUBSTITUTION_CREATE = "substitution.create"
    SUBSTITUTION_LIST = "substitution.list"
    SUBSTITUTION_CANCEL = "substitution.cancel"
    SUBSTITUTION_EXTEND = "substitution.extend"

    REPORT_WEEK = "reports.week"
    REPORT_MONTH = "reports.month"
    REPORT_QUARTER = "reports.quarter"

    APPROVALS_NEW = "approvals.new"
    APPROVALS_IN_PROGRESS = "approvals.in_progress"
    APPROVALS_OVERDUE = "approvals.overdue"
    APPROVALS_HISTORY = "approvals.history"
    APPROVAL_OPEN_PREFIX = "approval.open:"
    APPROVAL_APPROVE_PREFIX = "approval.approve:"
    APPROVAL_REJECT_PREFIX = "approval.reject:"
    EMPLOYEE_CASE_OPEN_PREFIX = "employee.case:"
    EMPLOYEE_REASON_PREFIX = "employee.reason:"

    CANCEL = "common.cancel"
    CONFIRM = "common.confirm"
