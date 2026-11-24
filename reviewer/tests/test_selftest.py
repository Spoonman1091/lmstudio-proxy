from watch.notify import Message
from watch.selftest import send_test_message


class Recorder:
    def __init__(self):
        self.sent = []

    def send(self, message: Message) -> None:
        self.sent.append(message)


def test_send_test_message_sends_harmless_message_and_reports_destination():
    r = Recorder()
    text = send_test_message(r, destination="parent@example.com")
    assert len(r.sent) == 1
    assert "test" in r.sent[0].subject.lower()
    assert "parent@example.com" in text
    assert r.sent[0].body == (
        "This is a test from the prompt reviewer. Email delivery works.\n"
    )  # fixed text only: never includes any child content
