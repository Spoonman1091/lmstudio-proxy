from datetime import date

from watch.config import Settings
from watch.models import Event
from watch.store import Store


def test_defaults_and_dry_run_when_smtp_missing():
    s = Settings.from_env({})
    assert s.min_severity == 2 and s.digest_hour == 20 and not s.smtp_configured


def test_invalid_and_out_of_range_numbers_fall_back_or_clamp():
    s = Settings.from_env({"ALERT_MIN_SEVERITY": "9", "DIGEST_HOUR": "abc", "SMTP_PORT": "0"})
    assert s.min_severity == 3 and s.digest_hour == 20 and s.smtp_port == 1


def test_smtp_security_only_allows_ssl_or_starttls():
    assert Settings.from_env({"SMTP_SECURITY": "none"}).smtp_security == "starttls"
    assert Settings.from_env({"SMTP_SECURITY": "SSL"}).smtp_security == "ssl"


def test_smtp_configured_needs_host_sender_and_recipient():
    env = {"SMTP_HOST": "h", "ALERT_FROM": "a@x", "ALERT_TO": "b@x"}
    assert Settings.from_env(env).smtp_configured
    assert not Settings.from_env({**env, "ALERT_TO": ""}).smtp_configured


def test_purge_removes_old_rows_only(tmp_path):
    s = Store(tmp_path / "s.db")
    s.add_event(Event("kid1", "ok", "none", 0, "", "old", "2026-01-01"))
    s.add_event(Event("kid1", "ok", "none", 0, "", "new", "2026-11-24"))
    s.purge_before("2026-06-01")
    assert s.events_for("2026-01-01") == []
    assert len(s.events_for("2026-11-24")) == 1
    assert date.fromisoformat("2026-11-24")
