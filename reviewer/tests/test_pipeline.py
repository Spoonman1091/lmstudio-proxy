from datetime import datetime

import pytest

from watch.classify import ClassifierUnavailable
from watch.models import Verdict
from watch.pipeline import ReviewDeps, maybe_send_digest, run_cycle
from watch.store import Store

NOW = datetime(2026, 11, 24, 15, 0)


def make_row(rid, text, user="kid1", end_user=""):
    return {
        "request_id": rid,
        "created_at": NOW,
        "user": user,
        "end_user": end_user,
        "proxy_server_request": {"messages": [{"role": "user", "content": text}], "metadata": {}},
        "response": None,
    }


class Recorder:
    def __init__(self, fail=False):
        self.sent, self.fail = [], fail

    def send(self, message):
        if self.fail:
            raise OSError("smtp down")
        self.sent.append(message)


def deps(tmp_path, classify, notifier=None, min_severity=2, max_attempts=3):
    return ReviewDeps(
        store=Store(tmp_path / "s.db"),
        classify=classify,
        notifier=notifier or Recorder(),
        min_severity=min_severity,
        max_chars=1000,
        max_attempts=max_attempts,
    )


SAFE = Verdict(False, "none", 0, "fine")
SEV2 = Verdict(True, "drugs_alcohol", 2, "asks to buy")
SEV1 = Verdict(True, "violence_weapons", 1, "curious")


def test_safe_prompt_is_recorded_without_alert(tmp_path):
    d = deps(tmp_path, lambda e: SAFE)
    r = run_cycle([make_row("1", "homework help")], d, NOW)
    assert r.reviewed == 1 and r.alerts == 0 and d.notifier.sent == []
    assert d.store.is_processed("1")
    assert d.store.events_for("2026-11-24")[0].status == "ok"


def test_severity_at_or_above_threshold_sends_alert(tmp_path):
    d = deps(tmp_path, lambda e: SEV2)
    r = run_cycle([make_row("1", "where can i buy vodka")], d, NOW)
    assert r.alerts == 1 and len(d.notifier.sent) == 1
    assert "drugs_alcohol" in d.notifier.sent[0].subject


def test_low_severity_is_queued_for_digest_only(tmp_path):
    d = deps(tmp_path, lambda e: SEV1)
    r = run_cycle([make_row("1", "how do swords work")], d, NOW)
    assert r.alerts == 0 and r.flagged == 1 and d.notifier.sent == []
    assert d.store.events_for("2026-11-24")[0].status == "flagged"


def test_background_tasks_are_skipped_but_marked_processed(tmp_path):
    called = []
    d = deps(tmp_path, lambda e: called.append(e) or SAFE)
    r = run_cycle([make_row("1", "### Task: Generate a title")], d, NOW)
    assert r.skipped == 1 and called == [] and d.store.is_processed("1")


def test_already_processed_rows_are_ignored(tmp_path):
    called = []
    d = deps(tmp_path, lambda e: called.append(e) or SAFE)
    d.store.mark_processed("1")
    run_cycle([make_row("1", "hi")], d, NOW)
    assert called == []


def test_repeated_prompt_is_not_reclassified_or_realerted(tmp_path):
    d = deps(tmp_path, lambda e: SEV2)
    run_cycle([make_row("1", "buy vodka"), make_row("2", "Buy  vodka")], d, NOW)
    assert len(d.notifier.sent) == 1
    assert d.store.is_processed("2")


def test_same_prompt_from_different_children_is_reviewed_for_each(tmp_path):
    d = deps(tmp_path, lambda e: SEV2)
    run_cycle([make_row("1", "buy vodka", user="kid1"), make_row("2", "buy vodka", user="kid2")], d, NOW)
    assert len(d.notifier.sent) == 2


def test_classifier_outage_stops_cycle_and_leaves_rows_unprocessed(tmp_path):
    def down(e):
        raise ClassifierUnavailable("lm studio down")
    d = deps(tmp_path, down)
    r = run_cycle([make_row("1", "a"), make_row("2", "b")], d, NOW)
    assert r.stopped and not d.store.is_processed("1") and not d.store.is_processed("2")


def test_unparseable_verdict_retries_then_gives_up(tmp_path):
    d = deps(tmp_path, lambda e: None, max_attempts=2)
    run_cycle([make_row("1", "hello")], d, NOW)
    assert not d.store.is_processed("1")
    r = run_cycle([make_row("1", "hello")], d, NOW)
    assert d.store.is_processed("1") and r.unclassified == 1
    assert d.store.events_for("2026-11-24")[0].status == "unclassified"


def test_failed_email_leaves_row_for_retry_and_records_no_event(tmp_path):
    d = deps(tmp_path, lambda e: SEV2, notifier=Recorder(fail=True))
    r = run_cycle([make_row("1", "buy vodka")], d, NOW)
    assert r.alert_failures == 1 and not d.store.is_processed("1")
    assert d.store.events_for("2026-11-24") == []


def test_end_user_name_is_used_in_alert(tmp_path):
    d = deps(tmp_path, lambda e: SEV2)
    run_cycle([make_row("1", "buy vodka", user="openwebui", end_user="Alex")], d, NOW)
    assert "Alex" in d.notifier.sent[0].subject


def digest_deps(tmp_path):
    return deps(tmp_path, lambda e: SEV1)


def test_digest_sent_once_after_digest_hour(tmp_path):
    d = digest_deps(tmp_path)
    run_cycle([make_row("1", "how do swords work")], d, NOW)
    early = datetime(2026, 11, 24, 18, 0)
    assert maybe_send_digest(early, d.store, d.notifier, digest_hour=20) is False
    late = datetime(2026, 11, 24, 20, 5)
    assert maybe_send_digest(late, d.store, d.notifier, digest_hour=20) is True
    assert maybe_send_digest(late, d.store, d.notifier, digest_hour=20) is False
    assert "Daily summary" in d.notifier.sent[-1].subject


def test_digest_skipped_but_marked_when_no_activity(tmp_path):
    d = digest_deps(tmp_path)
    late = datetime(2026, 11, 24, 21, 0)
    assert maybe_send_digest(late, d.store, d.notifier, digest_hour=20) is False
    assert d.notifier.sent == [] and d.store.last_digest_day() == "2026-11-24"


def test_digest_send_failure_is_retried(tmp_path):
    d = deps(tmp_path, lambda e: SEV1, notifier=Recorder(fail=True))
    run_cycle([make_row("1", "how do swords work")], d, NOW)
    late = datetime(2026, 11, 24, 21, 0)
    with pytest.raises(OSError):
        maybe_send_digest(late, d.store, d.notifier, digest_hour=20)
    assert d.store.last_digest_day() is None
