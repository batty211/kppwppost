from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

from .errors import ValidationError


@dataclass(frozen=True)
class Config:
    wp_url: str
    wp_username: str
    wp_application_password: str
    timeout_seconds: float = 30
    verify_ssl: bool = True


def load_config(batch_root: Path | None = None) -> Config:
    load_dotenv()
    if batch_root:
        load_dotenv(batch_root / ".env", override=True)
    required = {
        "WP_URL": os.getenv("WP_URL", "").strip(),
        "WP_USERNAME": os.getenv("WP_USERNAME", "").strip(),
        "WP_APPLICATION_PASSWORD": os.getenv(
            "WP_APPLICATION_PASSWORD", ""
        ).strip(),
    }
    missing = [key for key, value in required.items() if not value]
    if missing:
        raise ValidationError(f"Missing environment variables: {', '.join(missing)}")
    verify_value = os.getenv("WP_VERIFY_SSL", "true").strip().lower()
    if verify_value not in {"true", "false"}:
        raise ValidationError("WP_VERIFY_SSL must be true or false")
    try:
        timeout = float(os.getenv("WP_TIMEOUT_SECONDS", "30"))
    except ValueError as exc:
        raise ValidationError("WP_TIMEOUT_SECONDS must be a number") from exc
    return Config(
        wp_url=required["WP_URL"],
        wp_username=required["WP_USERNAME"],
        wp_application_password=required["WP_APPLICATION_PASSWORD"],
        timeout_seconds=timeout,
        verify_ssl=verify_value == "true",
    )

