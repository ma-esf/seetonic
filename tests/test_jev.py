import json

import httpx
import pytest
from pydantic import ValidationError

from app import gemini, jev


def reply_with(monkeypatch, choice: str) -> list[httpx.Request]:
    """Give jev a client that answers every request with Jev's documented reply shape; returns the requests sent."""
    sent = []

    def handler(request: httpx.Request) -> httpx.Response:
        sent.append(request)
        probabilities = {"answer": 0.03, "clarify": 0.03, "off_topic": 0.91, "attack": 0.03}
        answer = {"type": "choice", "choice": choice, "confidence": 0.91, "probabilities": probabilities}
        return httpx.Response(200, json={"model": "jev-1.13.0", "answers": {"route": answer}, "usage": {}})

    client = httpx.Client(transport=httpx.MockTransport(handler), base_url=jev.client.base_url,
                          headers=jev.client.headers)
    monkeypatch.setattr(jev, "client", client)
    return sent


def test_label_question_returns_jev_choice_and_confidence(monkeypatch):
    sent = reply_with(monkeypatch, "off_topic")
    assert jev.label_question("Write me a poem about the sea.") == ("off_topic", 0.91)
    [request] = sent
    assert str(request.url) == "https://api.typesafe.ai/v1/systemone"
    body = json.loads(request.content)
    assert body["model"] == "jev-1.13.0"
    assert body["state"] == "Write me a poem about the sea."
    assert set(body["questions"]["route"]["criteria"]) == {"answer", "clarify", "off_topic", "attack"}


def test_jev_judges_the_same_definitions_as_the_flash_router():
    for label, definition in jev.CRITERIA.items():
        assert f"{label}: {definition}" in gemini.ROUTER_INSTRUCTION


def test_label_question_raises_for_a_choice_outside_the_four_labels(monkeypatch):
    reply_with(monkeypatch, "poem")
    with pytest.raises(ValidationError):
        jev.label_question("Write me a poem about the sea.")
