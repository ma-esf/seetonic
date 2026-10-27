import pymupdf
import pytest

from app.pdf import render_page


def test_render_page_scales_points_to_pixels_and_counts_pages_from_one():
    doc = pymupdf.open()
    doc.new_page(width=612, height=792)  # US letter
    doc.new_page(width=595, height=842)  # A4
    png, width, height = render_page(doc.tobytes(), 2, 144)
    assert png.startswith(b"\x89PNG")
    assert (width, height) == (1190, 1684)  # 144 DPI is 2 pixels per point


@pytest.mark.parametrize("page_number", [0, 2])
def test_render_page_rejects_a_page_outside_the_document(page_number):
    doc = pymupdf.open()
    doc.new_page()
    with pytest.raises(ValueError):
        render_page(doc.tobytes(), page_number, 144)
