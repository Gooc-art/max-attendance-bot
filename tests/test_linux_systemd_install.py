from pathlib import Path


def test_linux_installer_enables_office_seal_reminder_timers() -> None:
    script = Path("scripts/install_systemd_user_linux.sh").read_text()

    assert "skud-office-seal-reminder-female.timer" in script
    assert "skud-office-seal-reminder-male.timer" in script
    assert "OnCalendar=Mon..Fri *-*-* $hour:$minute:00" in script
    assert "scripts/send_office_seal_reminders.py $gender" in script
    assert "enable --now skud-office-seal-reminder-female.timer skud-office-seal-reminder-male.timer" in script


def test_linux_installer_enables_directory_sync_timer() -> None:
    script = Path("scripts/install_systemd_user_linux.sh").read_text()

    assert "skud-directory-sync.timer" in script
    assert "OnUnitActiveSec=6h" in script
    assert "scripts/sync_employee_directory.py" in script
    assert "enable --now skud-directory-sync.timer" in script


def test_linux_installer_uses_polling_not_tunnel_for_bot_events() -> None:
    script = Path("scripts/install_systemd_user_linux.sh").read_text()

    assert "skud-polling.service" in script
    assert "ExecStart=$ROOT_DIR/scripts/run_polling.sh" in script
    assert "systemctl --user enable skud-backend.service skud-polling.service skud-public-url-tunnel.service" in script
    assert "systemctl --user disable skud-tunnel.service || true" in script
    assert "ExecStart=$ROOT_DIR/scripts/run_public_url_tunnel.sh" in script


def test_linux_deploy_restarts_polling_and_public_url_tunnel_and_stops_webhook_tunnel() -> None:
    script = Path("scripts/deploy_local_linux.sh").read_text()

    assert "systemctl --user stop skud-tunnel.service || true" in script
    assert "systemctl --user restart skud-public-url-tunnel.service" in script
    assert "systemctl --user restart skud-polling.service" in script
    assert "scripts/sync_employee_directory.py" in script
    assert "is-active --quiet skud-polling.service" in script
    assert "$PUBLIC_URL/api/health" in script
    assert "SKUD_PUBLIC_URL" not in script
