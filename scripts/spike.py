"""Spike: one page and one question through both model calls, and page ranks for the Plan B check.

Usage:
  python scripts/spike.py <pdf> <page> "<question>"
  python scripts/spike.py --rank <questions.jsonl>
"""

import json
import math
import sys
from pathlib import Path

import pymupdf

from app import config
from app.gemini import ask_model, client, embed_image, embed_text
from app.pdf import render_page


def cosine(a: list[float], b: list[float]) -> float:
    return math.sumprod(a, b) / (math.hypot(*a) * math.hypot(*b))


def one_page(pdf_path: str, page_number: int, question: str) -> None:
    # Read from the client, not config, so this shows where calls really go.
    api = client._api_client
    print(f"Agent Platform: {client.vertexai}, project {api.project}, location {api.location}")
    png, width, height = render_page(Path(pdf_path).read_bytes(), page_number, config.DPI)
    print(f"Page {page_number}: {width} x {height} px")
    page_vector, question_vector = embed_image(png), embed_text(question)
    for name, vector in [("page image", page_vector), ("question", question_vector)]:
        print(f"{name} embedding: length {len(vector)}, norm {math.hypot(*vector):.4f}")
    print(f"similarity: {cosine(page_vector, question_vector):.4f}")
    print(ask_model(question, [(page_number, png)]).model_dump_json(indent=2))


def rank(questions_path: str) -> None:
    root = Path(questions_path).parent.parent  # the file sits in <root>/eval/, and its pdf paths are relative to <root>
    page_vectors = {}
    for line in Path(questions_path).read_text().splitlines():
        item = json.loads(line)
        pdf = root / item["pdf"]
        if pdf not in page_vectors:
            data = pdf.read_bytes()
            with pymupdf.open(stream=data, filetype="pdf") as doc:
                page_count = doc.page_count
            page_vectors[pdf] = [embed_image(render_page(data, n, config.DPI)[0]) for n in range(1, page_count + 1)]
        question_vector = embed_text(item["question"])
        scores = [cosine(question_vector, vector) for vector in page_vectors[pdf]]
        ranked = sorted(range(1, len(scores) + 1), key=lambda n: scores[n - 1], reverse=True)
        print(f"page {item['page']}: rank {ranked.index(item['page']) + 1} of {len(ranked)}, top 3 {ranked[:3]} - {item['question']}")


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--rank":
        rank(sys.argv[2])
    elif len(sys.argv) == 4:
        one_page(sys.argv[1], int(sys.argv[2]), sys.argv[3])
    else:
        sys.exit(__doc__)
