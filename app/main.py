import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

import httpx
import pymupdf
from fastapi import FastAPI, HTTPException, Response, UploadFile
from fastapi.staticfiles import StaticFiles
from google.api_core.exceptions import NotFound
from google.genai.errors import APIError
from pydantic import BaseModel, Field, ValidationError

from app import config, gemini, jev, pdf, store, verify

app = FastAPI()

REFUSAL = "This question cannot be answered."


class Question(BaseModel):
    doc_id: str
    question: str = Field(min_length=1)


@app.post("/upload")
def upload(file: UploadFile) -> dict:
    """Store the PDF, one PNG per page and one row per page. A file that fails a check is rejected before any write."""
    data = file.file.read()
    try:
        pages = pdf.page_count(data)
    except ValueError as error:
        raise HTTPException(400, str(error))
    if pages > config.MAX_PAGES:
        raise HTTPException(400, f"The PDF has {pages} pages. The limit is {config.MAX_PAGES}.")

    doc_id = uuid.uuid4().hex
    # Render and embed every page before the first write, so a failed model call leaves nothing behind.
    pngs, rows = [], []
    for page in range(1, pages + 1):
        png = pdf.render_page(data, page, config.DPI)
        pngs.append(png)
        rows.append({"doc_id": doc_id, "page": page, "embedding": gemini.embed_image(png)})
    store.save_file(f"{doc_id}/source.pdf", data)
    for page, png in enumerate(pngs, start=1):
        store.save_file(f"{doc_id}/pages/{page}.png", png)
    store.insert_pages(rows)
    return {"doc_id": doc_id, "pages": pages}


@app.post("/ask")
def ask(body: Question) -> dict:
    """Answer from the document's top pages, unless Flash blocks the question or either model labels it "attack": then
    give a fixed reply. Both labels are logged and returned either way. Code, not the model, decides each citation's
    status and boxes."""
    start = time.perf_counter()
    try:
        jev_label = jev.label_question(body.question)
        flash_label = gemini.route_question(body.question)
        # A question the safety filter blocked, or either model calls an attack, must not reach the answer model.
        # clarify and off_topic are only shown, so a label one model gets wrong cannot hide the answer.
        if flash_label in ("blocked", "attack"):
            decision = flash_label
        elif jev_label[0] == "attack":
            decision = "attack"
        else:
            decision = "answer"
        # The last three are the log's column names; decision is not logged, as it follows from route and jev_route.
        labels = {"decision": decision, "route": flash_label, "jev_route": jev_label[0], "jev_confidence": jev_label[1]}
        if decision != "answer":
            log_question(body, start, flash_label, jev_label, [], [])
            return {"answer": REFUSAL, "pages": [], "citations": [], **labels}
        vector = gemini.embed_text(body.question)
    except (APIError, ValidationError, httpx.HTTPError):
        raise HTTPException(502, "The model is unavailable. Ask again.")
    scored = store.search_pages(body.doc_id, vector, config.TOP_K)
    if not scored:
        raise HTTPException(404, "No pages are stored for this document.")
    pngs = {page: store.load_file(f"{body.doc_id}/pages/{page}.png") for page, _ in scored}
    try:
        reply = gemini.ask_model(body.question, list(pngs.items()))
    except ValidationError:
        raise HTTPException(502, "The model's answer did not fit the citation format. Ask again.")
    except (APIError, httpx.HTTPError):
        raise HTTPException(502, "The model is unavailable. Ask again.")

    citations = []
    with pymupdf.open(stream=store.load_file(f"{body.doc_id}/source.pdf"), filetype="pdf") as doc:
        for citation in reply.citations:
            page = doc[citation.page - 1] if citation.page in pngs else None
            result = verify.verify_citation(page, citation, config.DPI)
            result["snippet_url"] = None
            if result["boxes"]:
                # Use the first box for the snippet; the page view shows all boxes.
                path = f"{body.doc_id}/snippets/{uuid.uuid4().hex}.png"
                store.save_file(path, pdf.crop(pngs[citation.page], result["boxes"][0]))
                result["snippet_url"] = f"/files/{path}"
            citations.append(result)
    pages = [{"page": page, "score": score} for page, score in scored]
    log_question(body, start, flash_label, jev_label, pages, [citation["status"] for citation in citations])
    return {"answer": reply.answer, "pages": pages, "citations": citations, **labels}


def log_question(
    body: Question, start: float, route: str, jev_label: tuple[str, float], pages: list[dict], statuses: list[str]
) -> None:
    try:
        store.log_question({
            "ts": datetime.now(timezone.utc).isoformat(),
            "doc_id": body.doc_id,
            "question": body.question,
            "pages": pages,
            "statuses": statuses,
            "latency_ms": round((time.perf_counter() - start) * 1000),
            "embed_model": config.EMBEDDING_MODEL,
            "answer_model": config.FLASH_MODEL,
            "route": route,
            "jev_route": jev_label[0],
            "jev_confidence": jev_label[1],
        })
    except Exception as error:
        # Monitoring must never cost the user the answer, but the failure must show in the logs.
        print(f"Logging the question failed: {error!r}", file=sys.stderr)


@app.get("/files/{path:path}")
def files(path: str) -> Response:
    """Serve a page image or a snippet. Only PNGs, so the source PDF is never served."""
    if not path.endswith(".png"):
        raise HTTPException(404, "Not found.")
    try:
        return Response(store.load_file(path), media_type="image/png")
    except NotFound:
        raise HTTPException(404, "Not found.")


# Mounted last: a route declared below this line would be caught by the mount instead.
# static/ is found beside app/ from this file, so app/ must run from the source tree, not from an installed wheel.
app.mount("/", StaticFiles(directory=Path(__file__).parent.parent / "static", html=True), name="static")
