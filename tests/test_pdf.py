import pymupdf
import pytest

from app.pdf import page_count


def _png() -> bytes:
    return pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 10, 10), False).tobytes("png")


@pytest.mark.parametrize("data", [b"not a pdf", b"", _png()], ids=["text", "empty", "png"])
def test_page_count_rejects_bytes_that_are_not_a_pdf(data):
    with pytest.raises(ValueError):
        page_count(data)
