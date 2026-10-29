import httpx
import pytest

from scripts import evaluate

TIMEOUT = "timeout"


def _server(replies: list[int | str]) -> tuple[httpx.Client, list[httpx.Request]]:
    """A client whose server answers with these status codes, or times out, in turn, and the requests it was sent."""
    sent = []

    def answer(request: httpx.Request) -> httpx.Response:
        sent.append(request)
        reply = replies[len(sent) - 1]
        if reply == TIMEOUT:
            raise httpx.ReadTimeout("timed out", request=request)
        return httpx.Response(reply, json={"ok": True})

    return httpx.Client(base_url="http://test", transport=httpx.MockTransport(answer)), sent


@pytest.fixture(autouse=True)
def no_wait(monkeypatch):
    monkeypatch.setattr(evaluate.time, "sleep", lambda seconds: None)


@pytest.mark.parametrize("busy", [502, TIMEOUT])
def test_a_busy_model_is_asked_again(busy):
    client, sent = _server([busy, busy, 200])
    assert evaluate._post(client, "/ask") == {"ok": True}
    assert len(sent) == 3


@pytest.mark.parametrize("busy", [502, TIMEOUT])
def test_the_run_stops_when_the_model_stays_busy(busy):
    client, sent = _server([busy] * (1 + evaluate.RETRIES))
    with pytest.raises(SystemExit, match="/ask"):
        evaluate._post(client, "/ask")
    assert len(sent) == 1 + evaluate.RETRIES


def _reply(*pages: int) -> dict:
    return {"pages": [{"page": page, "score": 0.5} for page in pages]}


def test_the_retrieved_pages_are_read_best_first():
    assert evaluate.retrieved_pages(_reply(9, 2, 5), page_count=32) == [9, 2, 5]


def test_a_document_shorter_than_top_k_returns_all_its_pages():
    assert evaluate.retrieved_pages(_reply(2, 1), page_count=2) == [2, 1]


@pytest.mark.parametrize("pages", [(9, 2, 5, 1), (9, 2)], ids=["more-than-3", "fewer-than-3"])
def test_a_server_with_another_top_k_stops_the_run(pages):
    with pytest.raises(SystemExit, match="TOP_K"):
        evaluate.retrieved_pages(_reply(*pages), page_count=32)


def test_any_other_failure_stops_the_run_at_once():
    client, sent = _server([404])
    with pytest.raises(SystemExit, match="404"):
        evaluate._post(client, "/ask")
    assert len(sent) == 1
