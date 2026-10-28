import pytest
from fastapi.testclient import TestClient

from app import config, gemini, pdf, store
from app.gemini import Citation, ModelAnswer
from app.main import app
from scripts.smoke import SENTENCE, one_page_pdf


@pytest.fixture
def logged(monkeypatch) -> list[dict]:
    """Stand in for every model and storage call /ask makes; returns the rows passed to store.log_question."""
    source = one_page_pdf()
    png = pdf.render_page(source, 1, config.DPI)[0]
    answer = ModelAnswer(answer="4 812 euros.", citations=[Citation(page=1, quote=SENTENCE, box_2d=[0, 0, 0, 0])])
    rows = []
    monkeypatch.setattr(gemini, "embed_text", lambda text: [0.0])
    monkeypatch.setattr(gemini, "ask_model", lambda question, pages: answer)
    monkeypatch.setattr(store, "search_pages", lambda doc_id, vector, k: [(1, 0.52)])
    monkeypatch.setattr(store, "load_file", lambda path: source if path.endswith(".pdf") else png)
    monkeypatch.setattr(store, "save_file", lambda path, data: None)
    monkeypatch.setattr(store, "log_question", rows.append)
    return rows


def test_ask_logs_one_row_with_the_pages_and_statuses_it_returns(logged):
    response = TestClient(app).post("/ask", json={"doc_id": "d1", "question": "What is the invoice total?"})
    assert response.status_code == 200
    [row] = logged
    assert row["doc_id"] == "d1"
    assert row["question"] == "What is the invoice total?"
    assert row["pages"] == response.json()["pages"] == [{"page": 1, "score": 0.52}]
    assert row["statuses"] == ["verified"]
    assert isinstance(row["latency_ms"], int) and row["latency_ms"] >= 0
    assert row["embed_model"] == config.EMBEDDING_MODEL
    assert row["answer_model"] == config.FLASH_MODEL
    assert row["ts"]


def test_ask_still_answers_when_logging_fails(logged, monkeypatch, capsys):
    def fail(row):
        raise RuntimeError("no such table")

    monkeypatch.setattr(store, "log_question", fail)
    response = TestClient(app).post("/ask", json={"doc_id": "d1", "question": "What is the invoice total?"})
    assert response.status_code == 200
    assert response.json()["answer"] == "4 812 euros."
    assert "no such table" in capsys.readouterr().err


def test_ask_logs_nothing_for_an_unknown_document(logged, monkeypatch):
    monkeypatch.setattr(store, "search_pages", lambda doc_id, vector, k: [])
    response = TestClient(app).post("/ask", json={"doc_id": "missing", "question": "What is the invoice total?"})
    assert response.status_code == 404
    assert logged == []
