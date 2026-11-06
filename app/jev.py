import base64

import httpx
from pydantic import BaseModel

from app import config, pdf, routing

# Questions, and page images for find_quote, go to TypeSafe, which names no EU region, so they may leave the EU.
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


# Jev rejects, never resizes, an image with a side over 1568 pixels.
MAX_SIDE = 1568
# On the eval PDFs, real quotes scored noul 0.84 or more and fake ones 0.03 or less; the one box on the wrong cell had
# confidence 0.24 and every right one 0.62 or more.
MIN_NOUL = 0.5
MIN_BOX = 0.5


class Noul(BaseModel):
    noul: float


class Edges(BaseModel):
    left: float
    top: float
    right: float
    bottom: float


class Box(BaseModel):
    box: Edges
    confidence: float


class QuoteAnswers(BaseModel):
    visible: Noul
    where: Box


class QuoteReply(BaseModel):
    answers: QuoteAnswers


def find_quote(png: bytes, quote: str) -> Edges | None:
    """Ask Jev whether the page image shows the quote, and where. Return the box as fractions of the image's width and
    height, or None when Jev doubts the quote is there or doubts its box. Raises like label_question."""
    image = base64.b64encode(pdf.shrink_to_fit(png, MAX_SIDE)).decode()
    response = client.post(
        "/v1/systemone",
        headers={"TypeSafe-Danger-Zone-Images": "true"},
        # A page image takes longer to send and to read than a question.
        timeout=10,
        json={
            "model": config.JEV_BOX_MODEL,
            "state": {"page": "page-image"},
            "assets": {"page-image": {"type": "image", "format": "png", "data_base64": image}},
            "questions": {
                "visible": {"type": "noul", "instructions": f'Does `page` show the exact text "{quote}"?'},
                "where": {"type": "box", "instructions": f'the text "{quote}" in `page`'},
            },
        },
    )
    response.raise_for_status()
    answers = QuoteReply.model_validate_json(response.text).answers
    if answers.visible.noul < MIN_NOUL or answers.where.confidence < MIN_BOX:
        return None
    return answers.where.box
