from google import genai
from google.genai import types
from pydantic import BaseModel, Field

from app import config

# Set in code, so neither GOOGLE_GENAI_USE_VERTEXAI nor an API key in the environment
# can move calls off Agent Platform.
client = genai.Client(vertexai=True, project=config.PROJECT, location=config.LOCATION)

INSTRUCTION = (
    'Answer the question using only the page images. Each image follows a label "Page N"; '
    "cite that N as the page. For each claim, copy the exact words from the page as the quote, "
    "and give box_2d around the quote as [ymin, xmin, ymax, xmax] on a 0-1000 scale."
)


class Citation(BaseModel):
    page: int
    quote: str
    box_2d: list[int] = Field(min_length=4, max_length=4)


class ModelAnswer(BaseModel):
    answer: str
    citations: list[Citation]


def _embed(content: types.PartUnion) -> list[float]:
    response = client.models.embed_content(
        model=config.EMBEDDING_MODEL,
        contents=content,
        config=types.EmbedContentConfig(output_dimensionality=config.EMBEDDING_SIZE),
    )
    return response.embeddings[0].values


def embed_image(png: bytes) -> list[float]:
    return _embed(types.Part.from_bytes(data=png, mime_type="image/png"))


def embed_text(text: str) -> list[float]:
    return _embed(text)


def ask_model(question: str, pages: list[tuple[int, bytes]]) -> ModelAnswer:
    """Send each page image after a "Page N" label; raises if the reply does not fit ModelAnswer."""
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
    return ModelAnswer.model_validate_json(response.text)
