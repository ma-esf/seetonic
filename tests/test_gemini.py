import pytest
from pydantic import ValidationError

from app.gemini import ModelAnswer


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
