import pymupdf
import pytest

from app.pdf import crop, has_text_layer, page_count, render_page


def test_page_count_counts_every_page():
    doc = pymupdf.open()
    for _ in range(3):
        doc.new_page()
    assert page_count(doc.tobytes()) == 3


def _png() -> bytes:
    return pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 10, 10), False).tobytes("png")


@pytest.mark.parametrize("data", [b"not a pdf", b"", _png()], ids=["text", "empty", "png"])
def test_page_count_rejects_bytes_that_are_not_a_pdf(data):
    with pytest.raises(ValueError):
        page_count(data)


def test_page_count_rejects_a_password_protected_pdf():
    doc = pymupdf.open()
    doc.new_page()
    encrypted = doc.tobytes(encryption=pymupdf.PDF_ENCRYPT_AES_256, user_pw="user", owner_pw="owner")
    with pytest.raises(ValueError, match="password"):
        page_count(encrypted)


def test_page_count_rejects_a_pdf_with_no_pages():
    # pymupdf refuses to save a document with no pages, so this one is written by hand.
    empty = (
        b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
        b"2 0 obj<</Type/Pages/Kids[]/Count 0>>endobj\ntrailer<</Root 1 0 R>>\n%%EOF"
    )
    with pytest.raises(ValueError, match="no pages"):
        page_count(empty)


def test_has_text_layer_is_true_for_a_text_page_and_false_for_an_image_only_page():
    doc = pymupdf.open()
    doc.new_page().insert_text((72, 72), "Net revenue 2024")
    scan = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 100, 100), False)
    scan.clear_with(200)
    doc.new_page().insert_image(pymupdf.Rect(72, 72, 300, 300), pixmap=scan)
    pdf_bytes = doc.tobytes()
    assert has_text_layer(pdf_bytes, 1) is True
    assert has_text_layer(pdf_bytes, 2) is False


def test_has_text_layer_is_false_for_a_page_with_only_whitespace():
    doc = pymupdf.open()
    doc.new_page().insert_text((72, 72), "   ")
    assert has_text_layer(doc.tobytes(), 1) is False


@pytest.mark.parametrize("page_number", [0, 2])
def test_has_text_layer_rejects_a_page_outside_the_document(page_number):
    doc = pymupdf.open()
    doc.new_page()
    with pytest.raises(ValueError):
        has_text_layer(doc.tobytes(), page_number)


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


def test_crop_cuts_the_box_out_of_a_png():
    image = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 100, 50), False)
    image.clear_with(255)
    image.set_rect(pymupdf.IRect(10, 5, 40, 25), (0, 0, 0))
    snippet = pymupdf.Pixmap(crop(image.tobytes("png"), [10, 5, 40, 25]))
    assert (snippet.width, snippet.height) == (30, 20)
    assert snippet.pixel(0, 0) == snippet.pixel(29, 19) == (0, 0, 0)


@pytest.mark.parametrize(
    "box", [[0, 0, 0, 0], [40, 25, 10, 5], [200, 200, 300, 300]], ids=["empty", "inverted", "outside"]
)
def test_crop_rejects_a_box_with_no_area_inside_the_image(box):
    image = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 100, 50), False)
    with pytest.raises(ValueError):
        crop(image.tobytes("png"), box)
