"""Alert and digest messages, and ways to deliver them."""
from __future__ import annotations

import re
import smtplib
import ssl
from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime
from email.message import EmailMessage
from pathlib import Path
from typing import Any, Callable, Protocol, Sequence

from .config import Settings
from .models import Entry, Event, Verdict

SUBJECT_PREFIX = "[LM proxy]"
SMTP_TIMEOUT_SECONDS = 30
_CONTROL_CHARS = re.compile(r"[\x00-\x1f\x7f]+")
FOOTER = (
    "\n--\nAutomated review by a local AI model. It can be wrong in both directions: "
    "treat this as a prompt for a conversation, not as proof."
)


@dataclass(frozen=True)
class Message:
    subject: str
    body: str


class Notifier(Protocol):
    def send(self, message: Message) -> None: ...


def _one_line(text: str) -> str:
    return _CONTROL_CHARS.sub(" ", text).strip()


def format_alert(entry: Entry, verdict: Verdict) -> Message:
    level = "URGENT" if verdict.severity >= 3 else "ALERT"
    subject = (
        f"{SUBJECT_PREFIX} {level}: {_one_line(entry.person)} - "
        f"{verdict.category} (severity {verdict.severity})"
    )
    when = entry.created_at.strftime("%Y-%m-%d %H:%M UTC") if entry.created_at else "unknown"
    lines = [
        f"Child:    {entry.person}",
        f"When:     {when}",
        f"Category: {verdict.category}",
        f"Severity: {verdict.severity} of 3",
        f"Why:      {verdict.reason}",
        "",
        "What they typed:",
        entry.prompt,
    ]
    if entry.response:
        lines += ["", "Start of the assistant's reply:", entry.response]
    return Message(subject, "\n".join(lines) + "\n" + FOOTER)


def format_digest(day: date, events: Sequence[Event]) -> Message:
    reviewed = Counter(e.person for e in events)
    flagged = Counter(e.person for e in events if e.status == "flagged")
    lines = [f"Activity summary for {day.isoformat()}", ""]
    lines += [
        f"{person}: {reviewed[person]} prompts reviewed, {flagged[person]} flagged"
        for person in sorted(reviewed)
    ]
    flagged_events = [e for e in events if e.status == "flagged"]
    if flagged_events:
        lines += ["", "Flagged items:"]
        for e in flagged_events:
            snippet = _one_line(e.prompt)[:300]
            lines.append(f"- {e.person} [{e.category}, severity {e.severity}] {e.reason}\n  \"{snippet}\"")
    unclassified = sum(1 for e in events if e.status == "unclassified")
    if unclassified:
        lines += ["", f"{unclassified} prompt(s) could not be classified and were not reviewed."]
    return Message(f"{SUBJECT_PREFIX} Daily summary {day.isoformat()}", "\n".join(lines) + "\n" + FOOTER)


class SmtpNotifier:
    """Sends mail over TLS (STARTTLS on 587 or implicit SSL on 465)."""

    def __init__(
        self,
        settings: Settings,
        smtp_factory: Callable[..., Any] = smtplib.SMTP,
        ssl_factory: Callable[..., Any] = smtplib.SMTP_SSL,
    ) -> None:
        self._s = settings
        self._smtp_factory = smtp_factory
        self._ssl_factory = ssl_factory

    def send(self, message: Message) -> None:
        mail = EmailMessage()
        mail["From"] = self._s.mail_from
        mail["To"] = self._s.mail_to
        mail["Subject"] = _one_line(message.subject)
        mail.set_content(message.body)
        context = ssl.create_default_context()
        if self._s.smtp_security == "ssl":
            with self._ssl_factory(
                self._s.smtp_host, self._s.smtp_port, timeout=SMTP_TIMEOUT_SECONDS, context=context
            ) as server:
                self._deliver(server, mail)
        else:
            with self._smtp_factory(
                self._s.smtp_host, self._s.smtp_port, timeout=SMTP_TIMEOUT_SECONDS
            ) as server:
                server.starttls(context=context)
                self._deliver(server, mail)

    def _deliver(self, server: Any, mail: EmailMessage) -> None:
        if self._s.smtp_user:
            server.login(self._s.smtp_user, self._s.smtp_password)
        server.send_message(mail)


class FileNotifier:
    """Dry-run delivery: appends messages to a local file."""

    def __init__(self, path: Path) -> None:
        self._path = Path(path)

    def send(self, message: Message) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().isoformat(timespec="seconds")
        with self._path.open("a", encoding="utf-8") as handle:
            handle.write(f"=== {stamp}\n{message.subject}\n\n{message.body}\n\n")


def build_notifier(settings: Settings) -> Notifier:
    if settings.smtp_configured:
        return SmtpNotifier(settings)
    return FileNotifier(Path(settings.data_dir) / "alerts.log")
