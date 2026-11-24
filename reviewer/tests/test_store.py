from datetime import datetime

from watch.models import Event
from watch.store import Store


def test_processed_roundtrip(tmp_path):
    s = Store(tmp_path / "s.db")
    assert not s.is_processed("a")
    s.mark_processed("a")
    assert s.is_processed("a")
    assert Store(tmp_path / "s.db").is_processed("a")  # persisted


def test_cursor_roundtrip(tmp_path):
    s = Store(tmp_path / "s.db")
    assert s.get_cursor() is None
    t = datetime(2026, 11, 24, 15, 30, 1, 123456)
    s.set_cursor(t)
    assert s.get_cursor() == t


def test_prompt_dedupe_is_per_person_and_case_insensitive(tmp_path):
    s = Store(tmp_path / "s.db")
    assert not s.has_prompt("kid1", "Hello  World")
    s.remember_prompt("kid1", "Hello  World")
    assert s.has_prompt("kid1", "hello world")
    assert not s.has_prompt("kid2", "hello world")


def test_attempts_increment(tmp_path):
    s = Store(tmp_path / "s.db")
    assert s.bump_attempts("r") == 1
    assert s.bump_attempts("r") == 2


def test_events_by_day(tmp_path):
    s = Store(tmp_path / "s.db")
    e1 = Event("kid1", "ok", "none", 0, "", "hi", "2026-11-24")
    e2 = Event("kid1", "flagged", "self_harm", 3, "r", "p", "2026-11-25")
    s.add_event(e1)
    s.add_event(e2)
    assert s.events_for("2026-11-24") == [e1]
    assert s.events_for("2026-11-25") == [e2]


def test_digest_marker(tmp_path):
    s = Store(tmp_path / "s.db")
    assert s.last_digest_day() is None
    s.set_digest_day("2026-11-24")
    assert s.last_digest_day() == "2026-11-24"
