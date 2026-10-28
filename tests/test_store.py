import pytest

from app import config, store


class _FakeBigQuery:
    """Returns the row errors it was given, the way insert_rows_json reports a rejected row."""

    def __init__(self, errors: list[dict]):
        self.errors = errors
        self.calls = []
        self.options = {}

    def insert_rows_json(self, table: str, rows: list[dict], **options) -> list[dict]:
        self.calls.append((table, rows))
        self.options = options
        return self.errors


def test_log_question_writes_one_row_to_the_questions_table(monkeypatch):
    fake = _FakeBigQuery([])
    monkeypatch.setattr(store, "bq", fake)
    store.log_question({"question": "q"})
    assert fake.calls == [(f"{config.PROJECT}.{config.DATASET}.{config.QUESTIONS_TABLE}", [{"question": "q"}])]


def test_log_question_gives_up_well_before_the_cloud_run_request_timeout(monkeypatch):
    # Retries stop at the retry timeout, but the last attempt can still run for the request timeout.
    fake = _FakeBigQuery([])
    monkeypatch.setattr(store, "bq", fake)
    store.log_question({"question": "q"})
    assert fake.options["retry"].timeout + fake.options["timeout"] <= 10


def test_log_question_raises_when_bigquery_returns_row_errors(monkeypatch):
    monkeypatch.setattr(store, "bq", _FakeBigQuery([{"index": 0, "errors": [{"reason": "invalid"}]}]))
    with pytest.raises(RuntimeError, match="invalid"):
        store.log_question({"question": "q"})
