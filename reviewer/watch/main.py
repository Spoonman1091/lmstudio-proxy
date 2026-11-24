"""Entry point: review new prompts every few minutes, alert, send a daily digest."""
from __future__ import annotations

import logging
import os
import signal
import sys
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .classify import classify
from .config import Settings
from .notify import build_notifier
from .pipeline import ReviewDeps, maybe_send_digest, run_cycle
from .source import fetch_rows
from .store import Store
from .transport import post_json

logger = logging.getLogger("watch")
CURSOR_OVERLAP = timedelta(minutes=5)  # re-read a little; processed-ids dedupe it


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _review_once(settings: Settings, deps: ReviewDeps, store: Store) -> None:
    cursor = store.get_cursor() or _utcnow() - timedelta(hours=settings.backfill_hours)
    rows = fetch_rows(settings.db_url, cursor - CURSOR_OVERLAP, settings.batch_size)
    result = run_cycle(rows, deps, datetime.now())
    if rows and not result.stopped and result.alert_failures == 0:
        store.set_cursor(max(row["created_at"] for row in rows))
    if rows:
        logger.info("Cycle: %s", result)


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    settings = Settings.from_env(os.environ)
    if not settings.db_url:
        logger.error("REVIEWER_DB_URL is not set")
        return 2
    store = Store(Path(settings.data_dir) / "state.db")
    notifier = build_notifier(settings)
    if not settings.smtp_configured:
        logger.warning("SMTP not configured: DRY RUN, alerts are written to %s/alerts.log", settings.data_dir)
    deps = ReviewDeps(
        store=store,
        classify=lambda entry: classify(entry, settings.model, settings.lm_url, post_json),
        notifier=notifier,
        min_severity=settings.min_severity,
        max_chars=settings.max_chars,
        max_attempts=settings.max_attempts,
    )
    stop = threading.Event()
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, lambda *_: stop.set())
    logger.info("Reviewer started: model=%s interval=%ss min_severity=%s",
                settings.model, settings.interval_seconds, settings.min_severity)
    while not stop.is_set():
        try:
            _review_once(settings, deps, store)
            maybe_send_digest(datetime.now(), store, notifier, settings.digest_hour)
            store.purge_before((datetime.now() - timedelta(days=settings.retention_days)).date().isoformat())
        except Exception:
            logger.exception("Review cycle failed; will retry")
        stop.wait(settings.interval_seconds)
    return 0


if __name__ == "__main__":
    sys.exit(main())
