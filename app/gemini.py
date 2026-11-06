from typing import Literal

from google import genai
from google.genai import types
from pydantic import BaseModel, Field

from app import config, routing

# Set in code, so neither GOOGLE_GENAI_USE_VERTEXAI nor an API key in the environment
# can move calls off Agent Platform. The timeout is in ms: 60 s per call keeps /ask's three Gemini calls inside
# Cloud Run's 300 s request timeout.
client = genai.Client(
    vertexai=True, project=config.PROJECT, location=config.LOCATION, http_options=types.HttpOptions(timeout=60_000)
)

INSTRUCTION = (
    "Answer the question using only the page images. If nothing on the pages relates to the question, say so and "
    "give no citations. If the question is loosely worded, answer its most likely meaning from the pages. Each "
    'image follows a label "Page N"; cite that N as the page. For each claim, copy the exact words from the page as '
    "the quote, "
    "as one continuous run of text in the order the page reads, with nothing left out; from a table, quote one cell "
    "per citation, never text joined from several cells, and prefer the numbers a claim rests on, without the $. "
    "Every claim in the answer, each list item included, needs its own citation. Give each citation a short label "
    'that says what the quote is, such as "Net revenue, year ended December 31, 2024". Give box_2d around the quote '
    "as [ymin, xmin, ymax, xmax] on a 0-1000 scale."
)

ROUTER_INSTRUCTION = routing.TASK + " " + " ".join(f"{label}: {text}" for label, text in routing.CRITERIA.items())


class Route(BaseModel):
    label: routing.Label


class Citation(BaseModel):
    page: int
    quote: str
    label: str
    box_2d: list[int] = Field(min_length=4, max_length=4)


class ModelAnswer(BaseModel):
    answer: str
    citations: list[Citation]


def _embed(content: str | types.Part) -> list[float]:
    response = client.models.embed_content(
        model=config.EMBEDDING_MODEL,
        contents=content,
        config=types.EmbedContentConfig(output_dimensionality=config.EMBEDDING_SIZE),
    )
    if not response.embeddings or response.embeddings[0].values is None:
        raise ValueError("Embedding response did not contain embedding values")
    return response.embeddings[0].values


def embed_image(png: bytes) -> list[float]:
    return _embed(types.Part.from_bytes(data=png, mime_type="image/png"))


def embed_text(text: str) -> list[float]:
    return _embed(text)


def route_question(question: str) -> routing.Label | Literal["blocked"]:
    """Return the question's label, judged from its text alone, or "blocked" when the safety filter blocked it; raises
    ValidationError if the reply is empty or does not fit Route."""
    response = client.models.generate_content(
        model=config.FLASH_MODEL,
        contents=question,
        config=types.GenerateContentConfig(
            system_instruction=ROUTER_INSTRUCTION,
            response_mime_type="application/json",
            response_schema=Route,
        ),
    )
    if response.prompt_feedback and response.prompt_feedback.block_reason:
        return "blocked"
    return Route.model_validate_json(response.text or "").label


def ask_model(question: str, pages: list[tuple[int, bytes]]) -> ModelAnswer:
    """Answer the question from the page images, each sent after a "Page N" label the model cites; raises
    ValidationError if the reply is empty or does not fit ModelAnswer."""
    contents = []
    for page_number, png in pages:
        contents += [f"Page {page_number}", types.Part.from_bytes(data=png, mime_type="image/png")]
    response = client.models.generate_content(
        model=config.FLASH_MODEL,
        contents=contents + [question],
        config=types.GenerateContentConfig(
            system_instruction=INSTRUCTION,
            response_mime_type="application/json",
            response_schema=ModelAnswer,
        ),
    )
    return ModelAnswer.model_validate_json(response.text or "")
