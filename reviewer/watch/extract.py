"""Turn a LiteLLM spend-log row into a reviewable Entry."""
from __future__ import annotations

from typing import Any, Mapping

from .models import Entry

TRUNCATION_MARK = "…[truncated]"
RESPONSE_EXCERPT_CHARS = 400
# Open WebUI sends background jobs (titles, tags, follow-up suggestions) that
# start with this marker and embed the whole chat; they are not child input.
BACKGROUND_PREFIX = "### Task:"


def last_user_text(messages: Any) -> str:
    """Text of the most recent user message, or "" when there is none."""
    if not isinstance(messages, list):
        return ""
    for message in reversed(messages):
        if isinstance(message, dict) and message.get("role") == "user":
            return _content_text(message.get("content"))
    return ""


def _content_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = [
            part.get("text", "")
            for part in content
            if isinstance(part, dict) and part.get("type") == "text"
        ]
        return "\n".join(p for p in parts if p)
    return ""


def is_background_task(text: str) -> bool:
    return text.lstrip().startswith(BACKGROUND_PREFIX)


def _truncate(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[:limit] + TRUNCATION_MARK


def _person(row: Mapping[str, Any], request: Mapping[str, Any]) -> str:
    end_user = (row.get("end_user") or "").strip()
    if end_user:
        return end_user
    metadata = request.get("metadata") if isinstance(request.get("metadata"), dict) else {}
    headers = metadata.get("headers") if isinstance(metadata.get("headers"), dict) else {}
    header_name = str(headers.get("x-openwebui-user-name") or "").strip()
    return header_name or (row.get("user") or "unknown")


def _response_excerpt(response: Any) -> str:
    try:
        content = response["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError):
        return ""
    return _truncate(content, RESPONSE_EXCERPT_CHARS) if isinstance(content, str) else ""


def to_entry(row: Mapping[str, Any], max_chars: int) -> Entry | None:
    """Build an Entry, or None when the row is not something a child typed."""
    request = row.get("proxy_server_request")
    if not isinstance(request, dict):
        return None
    text = last_user_text(request.get("messages")).strip()
    if not text or is_background_task(text):
        return None
    return Entry(
        request_id=str(row["request_id"]),
        created_at=row.get("created_at"),
        person=_person(row, request),
        prompt=_truncate(text, max_chars),
        response=_response_excerpt(row.get("response")),
    )
