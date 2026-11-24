"""Settings read from the environment."""
from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any, Mapping


def _int(env: Mapping[str, str], key: str, default: int, low: int, high: int) -> int:
    try:
        value = int(env.get(key, default))
    except (TypeError, ValueError):
        return default
    return max(low, min(high, value))


@dataclass(frozen=True)
class Settings:
    db_url: str = ""
    lm_url: str = "http://host.docker.internal:1234/v1"
    model: str = "qwen/qwen3.6-35b-a3b"
    interval_seconds: int = 300
    batch_size: int = 25
    backfill_hours: int = 24
    min_severity: int = 2
    digest_hour: int = 20
    max_chars: int = 4000
    max_attempts: int = 3
    retention_days: int = 30
    data_dir: str = "/data"
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_security: str = "starttls"  # "starttls" | "ssl"
    mail_from: str = ""
    mail_to: str = ""

    @property
    def smtp_configured(self) -> bool:
        return bool(self.smtp_host and self.mail_from and self.mail_to)

    def replace(self, **changes: Any) -> "Settings":
        return replace(self, **changes)

    @classmethod
    def from_env(cls, env: Mapping[str, str]) -> "Settings":
        security = env.get("SMTP_SECURITY", "starttls").strip().lower()
        return cls(
            db_url=env.get("REVIEWER_DB_URL", ""),
            lm_url=env.get("REVIEWER_LM_URL", cls.lm_url).rstrip("/"),
            model=env.get("REVIEWER_MODEL", cls.model),
            interval_seconds=_int(env, "REVIEW_INTERVAL_SECONDS", 300, 30, 86400),
            batch_size=_int(env, "REVIEW_BATCH_SIZE", 25, 1, 500),
            backfill_hours=_int(env, "REVIEW_BACKFILL_HOURS", 24, 0, 720),
            min_severity=_int(env, "ALERT_MIN_SEVERITY", 2, 1, 3),
            digest_hour=_int(env, "DIGEST_HOUR", 20, 0, 23),
            max_chars=_int(env, "MAX_PROMPT_CHARS", 4000, 200, 20000),
            max_attempts=_int(env, "MAX_CLASSIFY_ATTEMPTS", 3, 1, 10),
            retention_days=_int(env, "REVIEWER_RETENTION_DAYS", 30, 1, 365),
            data_dir=env.get("DATA_DIR", cls.data_dir),
            smtp_host=env.get("SMTP_HOST", "").strip(),
            smtp_port=_int(env, "SMTP_PORT", 587, 1, 65535),
            smtp_user=env.get("SMTP_USER", "").strip(),
            smtp_password=env.get("SMTP_PASSWORD", ""),
            smtp_security="ssl" if security == "ssl" else "starttls",
            mail_from=env.get("ALERT_FROM", "").strip(),
            mail_to=env.get("ALERT_TO", "").strip(),
        )
