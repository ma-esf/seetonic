import uuid

from fastapi import FastAPI, HTTPException, UploadFile

from app import config, gemini, pdf, store

app = FastAPI()


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
