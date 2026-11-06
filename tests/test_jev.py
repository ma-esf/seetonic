import base64
import json

import httpx
import pymupdf
import pytest

from app import config, jev


def _png(width: int, height: int) -> bytes:
    return pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, width, height), False).tobytes("png")


def _reply(noul: float, confidence: float) -> dict:
    """A find_quote reply in the shape TypeSafe's docs give, with a box around a table cell."""
    box = {"top": 0.22, "bottom": 0.26, "left": 0.59, "right": 0.69}
    return {
        "model": "jev-1.14.0",
        "answers": {
            "visible": {"type": "noul", "noul": noul},
            "where": {"type": "box", "box": box, "confidence": confidence},
        },
        "usage": {"input_tokens": 4791, "output_tokens": 36},
    }


@pytest.fixture
def typesafe(monkeypatch) -> dict:
    """Answer each request with typesafe["reply"] and keep the request in typesafe["request"]."""
    calls = {}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["request"] = request
        return httpx.Response(calls.get("status", 200), json=calls["reply"])

    client = httpx.Client(base_url="https://api.typesafe.ai", transport=httpx.MockTransport(handler))
    monkeypatch.setattr(jev, "client", client)
    return calls


def test_find_quote_returns_the_box_and_sends_a_page_image_jev_accepts(typesafe):
    typesafe["reply"] = _reply(noul=0.99, confidence=0.95)
    # A US-letter page at 144 DPI, taller than the 1568 pixels Jev accepts.
    edges = jev.find_quote(_png(1224, 1584), "4,718")
    assert edges == jev.Edges(left=0.59, top=0.22, right=0.69, bottom=0.26)

    request = typesafe["request"]
    assert request.url.path == "/v1/systemone"
    assert request.headers["TypeSafe-Danger-Zone-Images"] == "true"
    body = json.loads(request.content)
    assert body["model"] == config.JEV_BOX_MODEL
    assert body["questions"]["visible"]["type"] == "noul"
    assert body["questions"]["where"]["type"] == "box"
    assert all('"4,718"' in question["instructions"] for question in body["questions"].values())
    sent = pymupdf.Pixmap(base64.b64decode(body["assets"]["page-image"]["data_base64"]))
    assert (sent.width, sent.height) == (1212, 1568)


@pytest.mark.parametrize(
    ("noul", "confidence"), [(0.01, 0.95), (0.99, 0.24)], ids=["quote-not-seen", "box-in-doubt"]
)
def test_find_quote_returns_none_when_jev_doubts_the_quote_or_its_box(typesafe, noul, confidence):
    typesafe["reply"] = _reply(noul, confidence)
    assert jev.find_quote(_png(1224, 1584), "4,781") is None


def test_find_quote_raises_when_typesafe_rejects_the_request(typesafe):
    typesafe["status"], typesafe["reply"] = 400, {"detail": {"error_type": "max_tokens_exceeded"}}
    with pytest.raises(httpx.HTTPStatusError):
        jev.find_quote(_png(1224, 1584), "4,718")
