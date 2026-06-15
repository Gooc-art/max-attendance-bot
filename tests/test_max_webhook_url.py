from pathlib import Path

from app.services.max_webhook_url import normalize_webhook_url, resolve_webhook_url


def test_normalize_webhook_url_appends_suffix_for_public_base() -> None:
    assert normalize_webhook_url("https://demo.lhr.life") == "https://demo.lhr.life/api/webhooks/max"


def test_normalize_webhook_url_preserves_existing_webhook_path() -> None:
    assert normalize_webhook_url("https://demo.lhr.life/api/webhooks/max") == "https://demo.lhr.life/api/webhooks/max"


def test_resolve_webhook_url_prefers_explicit_url() -> None:
    tunnel_file = Path("/tmp/unused-localhostrun.url")
    assert (
        resolve_webhook_url(
            explicit_url="https://explicit.lhr.life",
            env_url="https://env.lhr.life/api/webhooks/max",
            tunnel_url_file=tunnel_file,
        )
        == "https://explicit.lhr.life/api/webhooks/max"
    )


def test_resolve_webhook_url_uses_tunnel_file_before_env(tmp_path: Path) -> None:
    tunnel_file = tmp_path / "localhostrun.url"
    tunnel_file.write_text("https://tunnel.lhr.life\n", encoding="utf-8")

    assert (
        resolve_webhook_url(
            env_url="https://env.lhr.life/api/webhooks/max",
            tunnel_url_file=tunnel_file,
        )
        == "https://tunnel.lhr.life/api/webhooks/max"
    )


def test_resolve_webhook_url_falls_back_to_env() -> None:
    assert (
        resolve_webhook_url(
            env_url="https://env.lhr.life",
            tunnel_url_file=Path("/tmp/missing-localhostrun.url"),
        )
        == "https://env.lhr.life/api/webhooks/max"
    )
