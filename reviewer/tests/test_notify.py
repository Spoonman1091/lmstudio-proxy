from datetime import date, datetime

from watch.config import Settings
from watch.models import Entry, Event, Verdict
from watch.notify import (
    FileNotifier,
    Message,
    SmtpNotifier,
    build_notifier,
    format_alert,
    format_digest,
)


def entry(person="kid1", prompt="a risky question", response="an answer"):
    return Entry("r1", datetime(2026, 11, 24, 15, 0), person, prompt, response)


def test_alert_subject_marks_urgent_for_severity_three():
    m = format_alert(entry(), Verdict(True, "self_harm", 3, "stated intent"))
    assert m.subject == "[LM proxy] URGENT: kid1 - self_harm (severity 3)"
    assert "stated intent" in m.body and "a risky question" in m.body and "an answer" in m.body


def test_alert_subject_for_severity_two():
    m = format_alert(entry(), Verdict(True, "drugs_alcohol", 2, "asks where to buy"))
    assert m.subject.startswith("[LM proxy] ALERT: kid1 - drugs_alcohol")


def test_alert_subject_strips_control_characters_from_person():
    m = format_alert(entry(person="Sam\r\nBcc: evil@example.com"), Verdict(True, "other", 2, "r"))
    assert "\n" not in m.subject and "\r" not in m.subject


def test_digest_lists_counts_and_flagged_items():
    events = [
        Event("kid1", "ok", "none", 0, "", "hello", "2026-11-24"),
        Event("kid1", "flagged", "violence_weapons", 1, "curiosity", "how do swords work", "2026-11-24"),
        Event("kid2", "unclassified", "none", 0, "", "???", "2026-11-24"),
    ]
    m = format_digest(date(2026, 11, 24), events)
    assert m.subject == "[LM proxy] Daily summary 2026-11-24"
    assert "kid1: 2 prompts reviewed, 1 flagged" in m.body
    assert "kid2: 1 prompts reviewed, 0 flagged" in m.body
    assert "how do swords work" in m.body
    assert "could not be classified" in m.body.lower()


class FakeSMTP:
    instances = []

    def __init__(self, host, port, timeout=None):
        self.host, self.port, self.calls = host, port, []
        FakeSMTP.instances.append(self)

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def starttls(self, context=None):
        self.calls.append("starttls")

    def login(self, user, password):
        self.calls.append(("login", user))

    def send_message(self, msg):
        self.calls.append(("send", msg["To"], msg["Subject"], msg.get_content()))


def smtp_settings(**kw):
    base = dict(smtp_host="smtp.example.com", smtp_port=587, smtp_user="u", smtp_password="p",
                mail_from="from@example.com", mail_to="to@example.com", smtp_security="starttls")
    return Settings.from_env({}).replace(**{**base, **kw})


def test_smtp_notifier_starttls_login_and_send():
    FakeSMTP.instances.clear()
    n = SmtpNotifier(smtp_settings(), smtp_factory=FakeSMTP, ssl_factory=FakeSMTP)
    n.send(Message("Subj", "Body text"))
    calls = FakeSMTP.instances[0].calls
    assert calls[0] == "starttls" and calls[1] == ("login", "u")
    assert calls[2] == ("send", "to@example.com", "Subj", "Body text\n")


def test_smtp_notifier_uses_ssl_factory_for_ssl_mode():
    used = []

    def ssl_factory(host, port, timeout=None, context=None):
        used.append(("ssl", port))
        return FakeSMTP(host, port, timeout)

    n = SmtpNotifier(smtp_settings(smtp_security="ssl", smtp_port=465),
                     smtp_factory=FakeSMTP, ssl_factory=ssl_factory)
    n.send(Message("S", "B"))
    assert used == [("ssl", 465)]


def test_file_notifier_appends(tmp_path):
    p = tmp_path / "alerts.log"
    n = FileNotifier(p)
    n.send(Message("S1", "B1"))
    n.send(Message("S2", "B2"))
    text = p.read_text()
    assert "S1" in text and "B2" in text


def test_build_notifier_dry_run_when_smtp_incomplete(tmp_path):
    s = Settings.from_env({"DATA_DIR": str(tmp_path)})
    assert isinstance(build_notifier(s), FileNotifier)


def test_build_notifier_smtp_when_configured(tmp_path):
    s = smtp_settings(data_dir=str(tmp_path))
    assert isinstance(build_notifier(s), SmtpNotifier)
