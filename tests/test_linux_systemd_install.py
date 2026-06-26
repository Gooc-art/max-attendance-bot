from pathlib import Path


def test_linux_installer_enables_office_seal_reminder_timers() -> None:
    script = Path("scripts/install_systemd_user_linux.sh").read_text()

    assert "skud-office-seal-reminder-female.timer" in script
    assert "skud-office-seal-reminder-male.timer" in script
    assert "OnCalendar=Mon..Fri *-*-* $hour:$minute:00" in script
    assert "scripts/send_office_seal_reminders.py $gender" in script
    assert "enable --now skud-office-seal-reminder-female.timer skud-office-seal-reminder-male.timer" in script
