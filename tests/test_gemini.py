from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app import gemini


def test_route_question_labels_a_question_the_safety_filter_blocked(monkeypatch):
    feedback = SimpleNamespace(block_reason="PROHIBITED_CONTENT")
    reply = SimpleNamespace(text=None, prompt_feedback=feedback)
    models = SimpleNamespace(generate_content=lambda **kwargs: reply)
    monkeypatch.setattr(gemini, "client", SimpleNamespace(models=models))
    assert gemini.route_question("A question the safety filter blocks.") == "blocked"


def _check_client(monkeypatch, text: str | None) -> dict:
    """Answer generate_content with the text; returns the keyword arguments of the call."""
    sent = {}

    def generate_content(**kwargs):
        sent.update(kwargs)
        return SimpleNamespace(text=text)

    monkeypatch.setattr(gemini, "client", SimpleNamespace(models=SimpleNamespace(generate_content=generate_content)))
    return sent


def test_find_quote_returns_the_box_and_sends_only_the_page_image_and_the_quote(monkeypatch):
    sent = _check_client(monkeypatch, '{"present": true, "box_2d": [220, 590, 260, 690]}')
    assert gemini.find_quote(b"png bytes", "4,718") == [220, 590, 260, 690]
    image, quote = sent["contents"]
    assert image.inline_data.data == b"png bytes"
    assert quote == 'Quote: "4,718"'
    assert sent["config"].system_instruction == gemini.CHECK_INSTRUCTION
    assert sent["config"].http_options.timeout == gemini.CHECK_TIMEOUT_MS


def test_find_quote_returns_none_when_the_page_does_not_show_the_quote(monkeypatch):
    _check_client(monkeypatch, '{"present": false, "box_2d": [0, 0, 0, 0]}')
    assert gemini.find_quote(b"png bytes", "4,781") is None


def test_find_quote_raises_on_an_empty_reply(monkeypatch):
    _check_client(monkeypatch, None)
    with pytest.raises(ValidationError):
        gemini.find_quote(b"png bytes", "4,718")
