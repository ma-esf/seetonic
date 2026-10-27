import pymupdf


def render_page(pdf_bytes: bytes, page_number: int, dpi: int) -> tuple[bytes, int, int]:
    """Render one page (1-based) to PNG; returns the PNG bytes, width and height in pixels."""
    with pymupdf.open(stream=pdf_bytes, filetype="pdf") as doc:
        # pymupdf counts negative indexes from the end, so page 0 would render the last page.
        if not 1 <= page_number <= doc.page_count:
            raise ValueError(f"page {page_number} is not in this {doc.page_count}-page PDF")
        pixmap = doc[page_number - 1].get_pixmap(dpi=dpi)
    return pixmap.tobytes("png"), pixmap.width, pixmap.height
