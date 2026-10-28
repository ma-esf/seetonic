import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pymupdf
from fastapi import FastAPI, HTTPException, Response, UploadFile
from fastapi.staticfiles import StaticFiles
from google.api_core.exceptions import NotFound
from google.genai.errors import APIError
from pydantic import BaseModel, Field, ValidationError

from app import config, gemini, pdf, store, verify

app = FastAPI()


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
        png, width, height = pdf.render_page(data, page, config.DPI)
        pngs.append(png)
        rows.append({
            "doc_id": doc_id,
            "page": page,
            "width": width,
            "height": height,
            "has_text": pdf.has_text_layer(data, page),
            "embedding": gemini.embed_image(png),
        })
    store.save_file(f"{doc_id}/source.pdf", data)
    for page, png in enumerate(pngs, start=1):
        store.save_file(f"{doc_id}/pages/{page}.png", png)
    store.insert_pages(rows)
    return {"doc_id": doc_id, "pages": pages}


@app.post("/ask")
def ask(body: Question) -> dict:
    """Answer from the document's top pages. Code, not the model, decides each citation's status and boxes."""
    start = time.perf_counter()
    try:
        vector = gemini.embed_text(body.question)
    except APIError:
        raise HTTPException(502, "The model is unavailable. Ask again.")
    scored = store.search_pages(body.doc_id, vector, config.TOP_K)
    if not scored:
        raise HTTPException(404, "No pages are stored for this document.")
    pngs = {page: store.load_file(f"{body.doc_id}/pages/{page}.png") for page, _ in scored}
    try:
        reply = gemini.ask_model(body.question, list(pngs.items()))
    except ValidationError:
        raise HTTPException(502, "The model's answer did not fit the citation format. Ask again.")
    except APIError:
        raise HTTPException(502, "The model is unavailable. Ask again.")

    citations = []
    with pymupdf.open(stream=store.load_file(f"{body.doc_id}/source.pdf"), filetype="pdf") as doc:
        for citation in reply.citations:
            page = doc[citation.page - 1] if citation.page in pngs else None
            result = verify.verify_citation(page, citation, config.DPI)
            result["snippet_url"] = None
            if result["boxes"]:
                # Only the first box: the first line of the first place where search_for found the quote.
                path = f"{body.doc_id}/snippets/{uuid.uuid4().hex}.png"
                store.save_file(path, pdf.crop(pngs[citation.page], result["boxes"][0]))
                result["snippet_url"] = f"/files/{path}"
            citations.append(result)
    pages = [{"page": page, "score": score} for page, score in scored]
    try:
        store.log_question({
            "ts": datetime.now(timezone.utc).isoformat(),
            "doc_id": body.doc_id,
            "question": body.question,
            "pages": pages,
            "statuses": [citation["status"] for citation in citations],
            "latency_ms": round((time.perf_counter() - start) * 1000),
            "embed_model": config.EMBEDDING_MODEL,
            "answer_model": config.FLASH_MODEL,
        })
    except Exception as error:
        # Monitoring must never cost the user the answer, but the failure must show in the logs.
        print(f"Logging the question failed: {error!r}", file=sys.stderr)
    return {"answer": reply.answer, "pages": pages, "citations": citations}


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
