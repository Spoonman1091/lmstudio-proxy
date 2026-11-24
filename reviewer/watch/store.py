"""Small SQLite state: what was reviewed, dedupe hashes, digest queue."""
from __future__ import annotations

import hashlib
import re
import sqlite3
from contextlib import closing
from datetime import datetime
from pathlib import Path

from .models import Event

SCHEMA = """
create table if not exists processed (request_id text primary key, day text not null);
create table if not exists prompts (hash text primary key, day text not null);
create table if not exists attempts (request_id text primary key, n integer not null);
create table if not exists kv (key text primary key, value text not null);
create table if not exists events (
    id integer primary key autoincrement,
    person text, status text, category text, severity integer,
    reason text, prompt text, day text, digested integer not null default 0
);
"""
_EVENT_COLUMNS = "person, status, category, severity, reason, prompt, day"


def _today() -> str:
    return datetime.now().date().isoformat()


def _prompt_hash(person: str, prompt: str) -> str:
    normalised = re.sub(r"\s+", " ", prompt.strip().lower())
    return hashlib.sha256(f"{person}\0{normalised}".encode("utf-8")).hexdigest()


class Store:
    def __init__(self, path: Path) -> None:
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.executescript(SCHEMA)
        self._path.chmod(0o600)

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self._path)

    def _run(self, sql: str, params: tuple = ()) -> list[tuple]:
        with closing(self._connect()) as conn, conn:
            return conn.execute(sql, params).fetchall()

    def is_processed(self, request_id: str) -> bool:
        return bool(self._run("select 1 from processed where request_id=?", (request_id,)))

    def mark_processed(self, request_id: str) -> None:
        self._run("insert or ignore into processed values (?, ?)", (request_id, _today()))

    def has_prompt(self, person: str, prompt: str) -> bool:
        return bool(self._run("select 1 from prompts where hash=?", (_prompt_hash(person, prompt),)))

    def remember_prompt(self, person: str, prompt: str) -> None:
        self._run("insert or ignore into prompts values (?, ?)", (_prompt_hash(person, prompt), _today()))

    def bump_attempts(self, request_id: str) -> int:
        self._run(
            "insert into attempts values (?, 1) on conflict(request_id) do update set n = n + 1",
            (request_id,),
        )
        return self._run("select n from attempts where request_id=?", (request_id,))[0][0]

    def get_cursor(self) -> datetime | None:
        rows = self._run("select value from kv where key='cursor'")
        return datetime.fromisoformat(rows[0][0]) if rows else None

    def set_cursor(self, value: datetime) -> None:
        self._run("insert or replace into kv values ('cursor', ?)", (value.isoformat(),))

    def last_digest_day(self) -> str | None:
        rows = self._run("select value from kv where key='digest_day'")
        return rows[0][0] if rows else None

    def set_digest_day(self, day: str) -> None:
        self._run("insert or replace into kv values ('digest_day', ?)", (day,))

    def add_event(self, event: Event) -> None:
        self._run(
            f"insert into events ({_EVENT_COLUMNS}) values (?, ?, ?, ?, ?, ?, ?)",
            (event.person, event.status, event.category, event.severity,
             event.reason, event.prompt, event.day),
        )

    def events_for(self, day: str) -> list[Event]:
        rows = self._run(f"select {_EVENT_COLUMNS} from events where day=? order by id", (day,))
        return [Event(*row) for row in rows]

    def undigested(self) -> list[tuple[int, Event]]:
        rows = self._run(f"select id, {_EVENT_COLUMNS} from events where digested=0 order by id")
        return [(row[0], Event(*row[1:])) for row in rows]

    def mark_digested(self, ids: list[int]) -> None:
        for event_id in ids:
            self._run("update events set digested=1 where id=?", (event_id,))

    def purge_before(self, day: str) -> None:
        """Forget bookkeeping and stored prompts older than `day` (ISO date)."""
        for table in ("processed", "prompts", "events"):
            self._run(f"delete from {table} where day < ?", (day,))
