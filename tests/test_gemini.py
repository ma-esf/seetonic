from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app import gemini
from app.gemini import ModelAnswer


def reply_without_text(monkeypatch, block_reason):
    feedback = SimpleNamespace(block_reason=block_reason)
    reply = SimpleNamespace(text=None, prompt_feedback=feedback)
    models = SimpleNamespace(generate_content=lambda **kwargs: reply)
    monkeypatch.setattr(gemini, "client", SimpleNamespace(models=models))


def test_route_question_labels_a_question_the_safety_filter_blocked(monkeypatch):
    reply_without_text(monkeypatch, "PROHIBITED_CONTENT")
    assert gemini.route_question("A question the safety filter blocks.") == "blocked"


def test_route_question_raises_for_an_empty_reply_the_safety_filter_did_not_block(monkeypatch):
    reply_without_text(monkeypatch, None)
    with pytest.raises(ValidationError):
        gemini.route_question("What were total net sales?")


def test_model_answer_parses_a_well_formed_answer():
    answer = ModelAnswer.model_validate_json(
        '{"answer": "x", "citations": [{"page": 3, "quote": "q", "box_2d": [1, 2, 3, 4]}]}'
    )
    assert answer.citations[0].page == 3
    assert answer.citations[0].box_2d == [1, 2, 3, 4]


def test_model_answer_rejects_a_page_that_is_not_an_integer():
    with pytest.raises(ValidationError):
        ModelAnswer.model_validate_json(
            '{"answer": "x", "citations": [{"page": "three", "quote": "q", "box_2d": [1, 2, 3, 4]}]}'
        )


def test_model_answer_rejects_a_box_without_four_numbers():
    with pytest.raises(ValidationError):
        ModelAnswer.model_validate_json(
            '{"answer": "x", "citations": [{"page": 3, "quote": "q", "box_2d": [1, 2, 3]}]}'
        )
