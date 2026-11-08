import pymupdf


def page_count(pdf_bytes: bytes) -> int:
    """Raises ValueError, with a message for the user, for a non-PDF, a password-protected PDF or a PDF with no pages."""
    try:
        doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
    except pymupdf.FileDataError as error:
        raise ValueError("The file cannot be read as a PDF.") from error
    with doc:
        # pymupdf opens an image as a one-page document even when told the bytes are a PDF.
        if not doc.is_pdf:
            raise ValueError("The file format is not PDF.")
        if doc.needs_pass:
            raise ValueError("The PDF is password-protected.")
        if doc.page_count == 0:
            raise ValueError("The PDF has no pages.")
        return doc.page_count


def render_page(pdf_bytes: bytes, page_number: int, dpi: int) -> bytes:
    """Render one page (1-based) to PNG."""
    with pymupdf.open(stream=pdf_bytes, filetype="pdf") as doc:
        # pymupdf counts negative indexes from the end, so page 0 would be the last page.
        if not 1 <= page_number <= doc.page_count:
            raise ValueError(f"page {page_number} is not in this {doc.page_count}-page PDF")
        return doc[page_number - 1].get_pixmap(dpi=dpi).tobytes("png")
