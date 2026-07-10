from __future__ import annotations

import unittest

from app.bot.buttons import (
    approvals_menu_buttons,
    employee_manager_section_buttons,
    employee_personal_buttons,
    employee_reason_section_buttons,
    hr_reference_buttons,
    main_menu_buttons,
    admin_reports_buttons,
    admin_settings_buttons,
    admin_skud_buttons,
    admin_structure_buttons,
    admin_workflow_buttons,
    manager_reports_buttons,
    security_audit_buttons,
    security_skud_buttons,
    substitutions_menu_buttons,
    top_reports_buttons,
    top_summary_buttons,
)


class CompactRoleMenuTests(unittest.TestCase):
    def test_employee_menu_is_sectioned(self) -> None:
        titles = [button.title for button in main_menu_buttons("employee")]
        self.assertEqual(titles[:2], ["Обо мне", "Опаздываю"])
        self.assertIn("Забыл карточку СКУД", titles)
        self.assertIn("Опоздания", titles)
        self.assertIn("Руководство", titles)
        self.assertNotIn("Статистика", titles)
        self.assertNotIn("Старт", titles)
        self.assertNotIn("Мой кабинет", titles)

    def test_manager_menu_is_sectioned(self) -> None:
        titles = [button.title for button in main_menu_buttons("manager")]
        self.assertEqual(titles[:2], ["Обо мне", "Опаздываю"])
        self.assertIn("Забыл карточку СКУД", titles)
        self.assertIn("Команда", titles)
        self.assertIn("Согласования", titles)
        self.assertNotIn("Отчеты", titles)
        self.assertIn("Замещения", titles)
        self.assertNotIn("Старт", titles)
        self.assertNotIn("Процессы", titles)

    def test_manager_reports_menu_contains_only_reports(self) -> None:
        titles = [button.title for button in manager_reports_buttons()]
        self.assertIn("Загрузить отчет", titles)
        self.assertIn("За период", titles)
        self.assertIn("Недельный", titles)
        self.assertIn("Месячный", titles)
        self.assertIn("Квартал", titles)
        self.assertIn("По отделам", titles)
        self.assertNotIn("Сводка", titles)
        self.assertNotIn("Просроченные", titles)

    def test_approvals_menu_does_not_duplicate_pending_section(self) -> None:
        titles = [button.title for button in approvals_menu_buttons()]
        self.assertIn("Ожидают", titles)
        self.assertIn("Просроченные", titles)
        self.assertIn("История", titles)
        self.assertNotIn("В работе", titles)

    def test_security_menu_is_sectioned(self) -> None:
        titles = [button.title for button in main_menu_buttons("security")]
        self.assertEqual(titles[:2], ["Обо мне", "Опаздываю"])
        self.assertNotIn("Старт", titles)
        self.assertIn("Опаздываю", titles)
        self.assertIn("Забыл карточку СКУД", titles)
        self.assertIn("СКУД", titles)
        self.assertIn("Разбор", titles)

    def test_security_skud_menu_contains_only_import_tools(self) -> None:
        titles = [button.title for button in security_skud_buttons()]
        self.assertIn("Импорт СКУД", titles)
        self.assertIn("История", titles)
        self.assertNotIn("Ошибки", titles)
        self.assertNotIn("Необработанные", titles)

    def test_security_audit_menu_contains_only_review_tools(self) -> None:
        titles = [button.title for button in security_audit_buttons()]
        self.assertIn("Ошибки", titles)
        self.assertIn("Необработанные", titles)
        self.assertNotIn("История", titles)

    def test_hr_menu_is_sectioned(self) -> None:
        buttons = main_menu_buttons("hr")
        titles = [button.title for button in buttons]
        rows_by_title = {button.title: button.row for button in buttons}
        self.assertEqual(titles[:2], ["Обо мне", "Опаздываю"])
        self.assertNotIn("Старт", titles)
        self.assertIn("Опаздываю", titles)
        self.assertIn("Забыл карточку СКУД", titles)
        self.assertIn("Справочники", titles)
        self.assertIn("Процессы", titles)
        self.assertIn("Отчеты", titles)
        self.assertIn("Параметры", titles)
        self.assertNotEqual(rows_by_title["Справочники"], rows_by_title["Процессы"])
        self.assertNotEqual(rows_by_title["Отчеты"], rows_by_title["Параметры"])

    def test_top_menu_is_sectioned(self) -> None:
        buttons = main_menu_buttons("top_manager")
        titles = [button.title for button in buttons]
        self.assertEqual(titles[:2], ["Обо мне", "Аналитика"])
        self.assertNotIn("Старт", titles)
        self.assertIn("Аналитика", titles)
        self.assertNotIn("Забыл карточку СКУД", titles)
        self.assertIn("Согласования", titles)
        self.assertIn("Отчеты", titles)
        self.assertIn("СКУД", titles)
        self.assertIn("Замещения", titles)
        self.assertNotIn("Процессы", titles)

    def test_top_summary_menu_contains_only_analytics_actions(self) -> None:
        titles = [button.title for button in top_summary_buttons()]
        self.assertIn("Сводка", titles)
        self.assertIn("Неявки отделов", titles)
        self.assertIn("Просроченные", titles)
        self.assertIn("По отделам", titles)
        self.assertIn("Входы", titles)
        self.assertNotIn("Мои сотрудники", titles)
        self.assertNotIn("Опоздания", titles)
        self.assertNotIn("Замещения", titles)

    def test_top_reports_menu_contains_only_reports(self) -> None:
        titles = [button.title for button in top_reports_buttons()]
        self.assertIn("За период", titles)
        self.assertIn("Недельный", titles)
        self.assertIn("Месячный", titles)
        self.assertIn("Квартал", titles)
        self.assertIn("По отделам", titles)
        self.assertNotIn("Согласования", titles)

    def test_substitutions_menu_uses_period_and_remove_wording(self) -> None:
        titles = [button.title for button in substitutions_menu_buttons()]
        self.assertIn("На период", titles)
        self.assertIn("Снять замещение", titles)
        self.assertNotIn("Назначить замещение", titles)
        self.assertNotIn("Отменить замещение", titles)

    def test_admin_menu_splits_long_buttons_across_rows(self) -> None:
        buttons = main_menu_buttons("admin")
        rows_by_title = {button.title: button.row for button in buttons}

        self.assertNotEqual(rows_by_title["Структура"], rows_by_title["Процессы"])
        self.assertNotEqual(rows_by_title["Отчеты"], rows_by_title["Параметры"])

    def test_admin_menu_has_no_duplicate_direct_diagnostic_entries(self) -> None:
        titles = [button.title for button in main_menu_buttons("admin")]

        self.assertEqual(titles[:2], ["Обо мне", "Опаздываю"])
        self.assertIn("Забыл карточку СКУД", titles)
        self.assertNotIn("Старт", titles)
        self.assertNotIn("Админ-панель", titles)
        self.assertNotIn("Права доступа", titles)
        self.assertIn("Личное", titles)
        self.assertIn("Отчеты", titles)

    def test_employee_subsections_use_single_back_button(self) -> None:
        for buttons in [employee_personal_buttons(), employee_reason_section_buttons(), employee_manager_section_buttons()]:
            titles = [button.title for button in buttons]
            self.assertIn("Назад", titles)
            self.assertNotIn("Главное меню", titles)

    def test_hr_subsections_use_single_back_button(self) -> None:
        titles = [button.title for button in hr_reference_buttons()]

        self.assertIn("Назад", titles)
        self.assertNotIn("Главное меню", titles)

    def test_admin_subsections_use_single_back_button(self) -> None:
        for buttons in [
            admin_structure_buttons(),
            admin_skud_buttons(),
            admin_workflow_buttons(),
            admin_reports_buttons(),
            admin_settings_buttons(),
        ]:
            titles = [button.title for button in buttons]
            self.assertIn("Назад", titles)
            self.assertNotIn("Админ-панель", titles)
            self.assertNotIn("Главное меню", titles)


if __name__ == "__main__":
    unittest.main()
