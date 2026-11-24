"""One review pass over new log rows, plus the daily digest."""
from __future__ import annotations

import logging
from dataclasses import dataclass, fields
from datetime import datetime
from typing import Any, Callable, Iterable, Mapping

from .classify import ClassifierUnavailable
from .extract import to_entry
from .models import Entry, Event, Verdict
from .notify import Notifier, format_alert, format_digest
from .store import Store

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ReviewDeps:
    store: Store
    classify: Callable[[Entry], Verdict | None]
    notifier: Notifier
    min_severity: int
    max_chars: int
    max_attempts: int


@dataclass(frozen=True)
class CycleResult:
    reviewed: int = 0
    alerts: int = 0
    flagged: int = 0
    unclassified: int = 0
    skipped: int = 0
    alert_failures: int = 0
    stopped: bool = False

    def plus(self, other: "CycleResult") -> "CycleResult":
        values = {
            f.name: getattr(self, f.name) + getattr(other, f.name)
            if f.name != "stopped" else self.stopped or other.stopped
            for f in fields(self)
        }
        return CycleResult(**values)


def _finish(entry: Entry, deps: ReviewDeps) -> None:
    deps.store.remember_prompt(entry.person, entry.prompt)
    deps.store.mark_processed(entry.request_id)


def _event(entry: Entry, verdict: Verdict | None, status: str, day: str) -> Event:
    return Event(
        person=entry.person,
        status=status,
        category=verdict.category if verdict else "none",
        severity=verdict.severity if verdict else 0,
        reason=verdict.reason if verdict else "",
        prompt=entry.prompt,
        day=day,
    )


def _handle_unparsed(entry: Entry, deps: ReviewDeps, day: str) -> CycleResult:
    if deps.store.bump_attempts(entry.request_id) < deps.max_attempts:
        return CycleResult()
    deps.store.add_event(_event(entry, None, "unclassified", day))
    _finish(entry, deps)
    return CycleResult(unclassified=1)


def _handle_flagged(entry: Entry, verdict: Verdict, deps: ReviewDeps, day: str) -> CycleResult:
    alert = verdict.severity >= deps.min_severity
    if alert:
        try:
            deps.notifier.send(format_alert(entry, verdict))
        except Exception:  # SMTP down etc.: leave the row so it is retried
            logger.exception("Could not deliver alert for request %s", entry.request_id)
            return CycleResult(alert_failures=1)
    deps.store.add_event(_event(entry, verdict, "flagged", day))
    _finish(entry, deps)
    return CycleResult(reviewed=1, flagged=1, alerts=1 if alert else 0)


def _review_row(row: Mapping[str, Any], deps: ReviewDeps, now: datetime) -> CycleResult:
    request_id = str(row["request_id"])
    if deps.store.is_processed(request_id):
        return CycleResult()
    entry = to_entry(row, deps.max_chars)
    if entry is None or deps.store.has_prompt(entry.person, entry.prompt):
        deps.store.mark_processed(request_id)
        return CycleResult(skipped=1)
    day = now.date().isoformat()
    try:
        verdict = deps.classify(entry)
    except ClassifierUnavailable as exc:
        logger.warning("Classifier unavailable, will retry later: %s", exc)
        return CycleResult(stopped=True)
    if verdict is None:
        return _handle_unparsed(entry, deps, day)
    if verdict.flag:
        return _handle_flagged(entry, verdict, deps, day)
    deps.store.add_event(_event(entry, verdict, "ok", day))
    _finish(entry, deps)
    return CycleResult(reviewed=1)


def run_cycle(rows: Iterable[Mapping[str, Any]], deps: ReviewDeps, now: datetime) -> CycleResult:
    total = CycleResult()
    for row in rows:
        delta = _review_row(row, deps, now)
        total = total.plus(delta)
        if delta.stopped:
            break
    return total


def maybe_send_digest(now: datetime, store: Store, notifier: Notifier, digest_hour: int) -> bool:
    """Send the daily summary once, after `digest_hour`. Raises if delivery fails."""
    today = now.date().isoformat()
    if now.hour < digest_hour or store.last_digest_day() == today:
        return False
    pending = store.undigested()
    if not pending:
        store.set_digest_day(today)
        return False
    notifier.send(format_digest(now.date(), [event for _, event in pending]))
    store.mark_digested([event_id for event_id, _ in pending])
    store.set_digest_day(today)
    return True
