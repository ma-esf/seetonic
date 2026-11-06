import pymupdf
import pytest

from app.pdf import page_count, shrink_to_fit


def _png() -> bytes:
    return pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 10, 10), False).tobytes("png")


@pytest.mark.parametrize("data", [b"not a pdf", b"", _png()], ids=["text", "empty", "png"])
def test_page_count_rejects_bytes_that_are_not_a_pdf(data):
    with pytest.raises(ValueError):
        page_count(data)


def test_shrink_to_fit_scales_the_longest_side_down_and_keeps_the_shape():
    letter = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 1224, 1584), False).tobytes("png")
    shrunk = pymupdf.Pixmap(shrink_to_fit(letter, 1568))
    assert (shrunk.width, shrunk.height) == (1212, 1568)


def test_shrink_to_fit_keeps_an_image_that_already_fits():
    png = _png()
    assert shrink_to_fit(png, 1568) is png
