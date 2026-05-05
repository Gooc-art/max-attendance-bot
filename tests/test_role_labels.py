from __future__ import annotations

import unittest

from app.domain.role_labels import display_role_name


class RoleLabelsTests(unittest.TestCase):
    def test_display_role_name_returns_russian_label(self) -> None:
        self.assertEqual(display_role_name("admin"), "Администратор")
        self.assertEqual(display_role_name("manager"), "Руководитель")
        self.assertEqual(display_role_name("security"), "Служба безопасности")

    def test_display_role_name_preserves_unknown_values(self) -> None:
        self.assertEqual(display_role_name("custom_role"), "custom_role")


if __name__ == "__main__":
    unittest.main()
