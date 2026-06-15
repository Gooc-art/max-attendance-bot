from __future__ import annotations

from pathlib import Path


WEBHOOK_SUFFIX = "/api/webhooks/max"


def normalize_webhook_url(value: str) -> str:
    candidate = value.strip()
    if not candidate:
        return ""
    if candidate.endswith(WEBHOOK_SUFFIX):
        return candidate
    return f"{candidate.rstrip('/')}{WEBHOOK_SUFFIX}"


def resolve_webhook_url(*, explicit_url: str = "", env_url: str = "", tunnel_url_file: Path | None = None) -> str:
    normalized_explicit = normalize_webhook_url(explicit_url)
    if normalized_explicit:
        return normalized_explicit

    if tunnel_url_file is not None and tunnel_url_file.exists():
        tunnel_url = normalize_webhook_url(tunnel_url_file.read_text(encoding="utf-8").strip())
        if tunnel_url:
            return tunnel_url

    return normalize_webhook_url(env_url)
