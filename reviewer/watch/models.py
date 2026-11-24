"""Immutable value objects shared across the reviewer."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class Entry:
    """One child prompt (plus a short excerpt of the model's reply) to review."""

    request_id: str
    created_at: datetime | None
    person: str
    prompt: str
    response: str


@dataclass(frozen=True)
class Verdict:
    """Classifier decision for one entry."""

    flag: bool
    category: str
    severity: int  # 0 = not flagged, 1 = mild, 2 = concerning, 3 = urgent
    reason: str


@dataclass(frozen=True)
class Event:
    """A reviewed prompt as stored for the daily digest."""

    person: str
    status: str  # "ok" | "flagged" | "unclassified"
    category: str
    severity: int
    reason: str
    prompt: str
    day: str  # ISO date the review happened
