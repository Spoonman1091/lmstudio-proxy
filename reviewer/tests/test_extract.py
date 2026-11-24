from datetime import datetime

from watch.extract import last_user_text, is_background_task, to_entry


def row(messages, user="kid1", end_user="", headers=None, response=None):
    return {
        "request_id": "req-1",
        "created_at": datetime(2026, 11, 24, 15, 0, 0),
        "user": user,
        "end_user": end_user,
        "proxy_server_request": {
            "messages": messages,
            "metadata": {"headers": headers or {}},
        },
        "response": response,
    }


def test_last_user_text_picks_last_user_message():
    msgs = [
        {"role": "system", "content": "be nice"},
        {"role": "user", "content": "first"},
        {"role": "assistant", "content": "reply"},
        {"role": "user", "content": "second"},
    ]
    assert last_user_text(msgs) == "second"


def test_last_user_text_handles_content_parts():
    msgs = [{"role": "user", "content": [
        {"type": "text", "text": "hello"},
        {"type": "image_url", "image_url": {"url": "x"}},
        {"type": "text", "text": "world"},
    ]}]
    assert last_user_text(msgs) == "hello\nworld"


def test_last_user_text_empty_when_no_user_message():
    assert last_user_text([{"role": "assistant", "content": "hi"}]) == ""
    assert last_user_text([]) == ""
    assert last_user_text(None) == ""


def test_background_tasks_detected():
    assert is_background_task("### Task: Generate a concise title for the chat")
    assert is_background_task("  ### Task:\nPredict 3-5 follow ups")
    assert not is_background_task("Can this Mac run macOS 13?")


def test_to_entry_uses_key_alias_for_person():
    e = to_entry(row([{"role": "user", "content": "hi"}]), max_chars=1000)
    assert e.person == "kid1" and e.prompt == "hi" and e.request_id == "req-1"


def test_to_entry_prefers_end_user():
    e = to_entry(row([{"role": "user", "content": "hi"}], user="openwebui", end_user="Alex"), 1000)
    assert e.person == "Alex"


def test_to_entry_falls_back_to_openwebui_header():
    r = row([{"role": "user", "content": "hi"}], user="openwebui",
            headers={"x-openwebui-user-name": "Sam"})
    assert to_entry(r, 1000).person == "Sam"


def test_to_entry_skips_background_and_empty():
    assert to_entry(row([{"role": "user", "content": "### Task: title"}]), 1000) is None
    assert to_entry(row([{"role": "user", "content": "   "}]), 1000) is None
    assert to_entry(row([]), 1000) is None


def test_to_entry_truncates_prompt_and_extracts_response():
    resp = {"choices": [{"message": {"content": "R" * 900}}]}
    e = to_entry(row([{"role": "user", "content": "x" * 5000}], response=resp), max_chars=100)
    assert len(e.prompt) <= 100 + len("…[truncated]")
    assert e.prompt.endswith("…[truncated]")
    assert len(e.response) <= 400 + len("…[truncated]")


def test_to_entry_tolerates_missing_or_bad_response():
    assert to_entry(row([{"role": "user", "content": "hi"}], response=None), 100).response == ""
    assert to_entry(row([{"role": "user", "content": "hi"}], response={"x": 1}), 100).response == ""
