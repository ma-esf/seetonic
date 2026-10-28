"""Ask the running server a question and draw each citation's boxes on its page image, as debug/<page>.png.

Usage:
  python scripts/ask_debug.py <doc_id> "<question>"

Expects the server from `uv run uvicorn app.main:app --port 8080`.
"""

import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

import pymupdf

SERVER = "http://localhost:8080"
DEBUG = Path(__file__).resolve().parent.parent / "debug"  # at the repo root, whatever the working directory
COLORS = {"verified": (0, 160, 0), "approximate": (255, 140, 0)}  # an unverified citation has no boxes
LINE = 3  # outline width in pixels


def outline(image: pymupdf.Pixmap, box: list[float], color: tuple[int, int, int]) -> None:
    x0, y0, x1, y1 = (round(value) for value in box)
    for edge in [(x0, y0, x1, y0 + LINE), (x0, y1 - LINE, x1, y1), (x0, y0, x0 + LINE, y1), (x1 - LINE, y0, x1, y1)]:
        image.set_rect(pymupdf.IRect(edge), color)


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    doc_id, question = sys.argv[1], sys.argv[2]
    request = urllib.request.Request(
        f"{SERVER}/ask",
        data=json.dumps({"doc_id": doc_id, "question": question}).encode(),
        headers={"content-type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request) as response:
            reply = json.load(response)
    except urllib.error.HTTPError as error:
        sys.exit(f"{error.code}: {error.read().decode()}")
    print(reply["answer"])

    images = {}
    for citation in reply["citations"]:
        page = citation["page"]
        print(f"page {page}, {citation['status']}: {citation['quote']}")
        if not citation["boxes"]:
            continue
        if page not in images:
            with urllib.request.urlopen(f"{SERVER}/files/{doc_id}/pages/{page}.png") as response:
                images[page] = pymupdf.Pixmap(response.read())
        for box in citation["boxes"]:
            outline(images[page], box, COLORS[citation["status"]])

    # Remove the last run's images, so every file in debug/ belongs to this answer.
    DEBUG.mkdir(exist_ok=True)
    for old in DEBUG.glob("*.png"):
        old.unlink()
    for page, image in images.items():
        image.save(str(DEBUG / f"{page}.png"))
        print(f"wrote debug/{page}.png")
