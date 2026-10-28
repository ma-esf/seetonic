import pymupdf


def page_count(pdf_bytes: bytes) -> int:
    """Raises ValueError, with a message for the user, for a non-PDF, a password-protected PDF or a PDF with no pages."""
    try:
        doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
    except pymupdf.FileDataError as error:
        raise ValueError("The file is not a PDF.") from error
    with doc:
        # pymupdf opens an image as a one-page document even when told the bytes are a PDF.
        if not doc.is_pdf:
            raise ValueError("The file is not a PDF.")
        if doc.needs_pass:
            raise ValueError("The PDF is password-protected.")
        if doc.page_count == 0:
            raise ValueError("The PDF has no pages.")
        return doc.page_count


def _page(doc: pymupdf.Document, page_number: int) -> pymupdf.Page:
    # pymupdf counts negative indexes from the end, so page 0 would be the last page.
    if not 1 <= page_number <= doc.page_count:
        raise ValueError(f"page {page_number} is not in this {doc.page_count}-page PDF")
    return doc[page_number - 1]


def has_text_layer(pdf_bytes: bytes, page_number: int) -> bool:
    """True when the page (1-based) yields any non-whitespace text; false for a scan or an image-only page."""
    with pymupdf.open(stream=pdf_bytes, filetype="pdf") as doc:
        return bool(_page(doc, page_number).get_text().strip())


def render_page(pdf_bytes: bytes, page_number: int, dpi: int) -> tuple[bytes, int, int]:
    """Render one page (1-based) to PNG; returns the PNG bytes, width and height in pixels."""
    with pymupdf.open(stream=pdf_bytes, filetype="pdf") as doc:
        pixmap = _page(doc, page_number).get_pixmap(dpi=dpi)
    return pixmap.tobytes("png"), pixmap.width, pixmap.height


def crop(png: bytes, box: list[float]) -> bytes:
    """Cut a box [x0, y0, x1, y1], in pixels, out of a PNG, rounding outwards.

    Raises ValueError for a box with no area inside the image.
    """
    image = pymupdf.Pixmap(png)
    clip = pymupdf.Rect(box) & pymupdf.Rect(0, 0, image.width, image.height)
    # pymupdf crashes the process, not just the call, when the clip has no area inside the image.
    if clip.is_empty:
        raise ValueError(f"The box {box} has no area inside the {image.width} x {image.height} image.")
    return pymupdf.Pixmap(image, image.width, image.height, clip).tobytes("png")
