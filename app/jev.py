import httpx
from pydantic import BaseModel

from app import config, routing

# Questions go to TypeSafe, which names no EU region, so they may leave the EU.
# timeout=2 limits each connect, read, write and pool wait separately, not the whole call.
client = httpx.Client(
    base_url="https://api.typesafe.ai", headers={"Authorization": f"Bearer {config.TYPESAFE_API_KEY}"}, timeout=2
)


class Choice(BaseModel):
    choice: routing.Label
    confidence: float


class Answers(BaseModel):
    route: Choice


class Reply(BaseModel):
    answers: Answers


def label_question(question: str) -> tuple[str, float]:
    """Return Jev's label and confidence; raises httpx.HTTPError if the call fails and ValidationError if the reply does
    not fit Reply."""
    response = client.post("/v1/systemone", json={
        "model": config.JEV_MODEL,
        "state": question,
        "questions": {"route": {"type": "choice", "instructions": routing.TASK, "criteria": routing.CRITERIA}},
    })
    response.raise_for_status()
    route = Reply.model_validate_json(response.text).answers.route
    return route.choice, route.confidence
