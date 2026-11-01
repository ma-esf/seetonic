from types import SimpleNamespace

from app import gemini


def test_route_question_labels_a_question_the_safety_filter_blocked(monkeypatch):
    feedback = SimpleNamespace(block_reason="PROHIBITED_CONTENT")
    reply = SimpleNamespace(text=None, prompt_feedback=feedback)
    models = SimpleNamespace(generate_content=lambda **kwargs: reply)
    monkeypatch.setattr(gemini, "client", SimpleNamespace(models=models))
    assert gemini.route_question("A question the safety filter blocks.") == "blocked"
