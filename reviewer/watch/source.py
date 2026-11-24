"""Read new chat requests from LiteLLM's Postgres log table (read-only role)."""
from __future__ import annotations

from datetime import datetime
from typing import Any

QUERY = """
select request_id, created_at, "user", end_user, proxy_server_request, response
from "LiteLLM_SpendLogs"
where created_at > %s and proxy_server_request is not null
order by created_at asc
limit %s
"""


def fetch_rows(db_url: str, since: datetime, limit: int) -> list[dict[str, Any]]:
    import psycopg  # imported lazily so unit tests need no database driver
    from psycopg.rows import dict_row

    with psycopg.connect(db_url, row_factory=dict_row, connect_timeout=10) as conn:
        conn.read_only = True
        return list(conn.execute(QUERY, (since, limit)).fetchall())
