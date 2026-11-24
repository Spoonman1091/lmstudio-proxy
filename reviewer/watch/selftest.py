"""`python -m watch.selftest`: send one harmless test message to verify delivery."""
from __future__ import annotations

import os
import sys

from .config import Settings
from .notify import Message, Notifier, SUBJECT_PREFIX, build_notifier


def send_test_message(notifier: Notifier, destination: str) -> str:
    notifier.send(
        Message(
            f"{SUBJECT_PREFIX} Test message",
            "This is a test from the prompt reviewer. Email delivery works.\n",
        )
    )
    return f"Test message sent to {destination}"


def main() -> int:
    settings = Settings.from_env(os.environ)
    if not settings.smtp_configured:
        sys.stderr.write(
            "SMTP is not configured: set SMTP_HOST, ALERT_FROM and ALERT_TO in .env, "
            "then recreate the reviewer container.\n"
        )
        return 2
    sys.stdout.write(send_test_message(build_notifier(settings), settings.mail_to) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
