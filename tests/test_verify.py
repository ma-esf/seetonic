import pymupdf
import pytest

from app.gemini import Citation
from app.verify import verify_citation

# 144 DPI, the default in app/config.py: 2 pixels per point.
DPI = 144


def _text_page(text: str) -> pymupdf.Page:
    """A US-letter page, which is not square, with the text from x = 72 points and the first baseline at 112."""
    page = pymupdf.open().new_page(width=612, height=792)
    page.insert_text((72, 112), text)
    return page


def _scan_page() -> pymupdf.Page:
    """A US-letter page holding only an image, so it has no text layer."""
    page = pymupdf.open().new_page(width=612, height=792)
    scan = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 100, 100), False)
    scan.clear_with(200)
    page.insert_image(page.rect, pixmap=scan)
    return page


def _line_boxes(page: pymupdf.Page) -> list[list[float]]:
    """Each line's box as the page's text layer gives it, in pixels at 144 DPI, as approx values."""
    lines = [line["bbox"] for block in page.get_text("dict")["blocks"] for line in block["lines"]]
    return [pytest.approx([2 * value for value in bbox], abs=2) for bbox in lines]


def _citation(page: int, quote: str, box_2d: list[int] = [0, 0, 0, 0]) -> Citation:
    return Citation(page=page, quote=quote, label="", box_2d=box_2d)


def test_an_exact_quote_is_verified_with_its_box_in_pixels():
    page = _text_page("Net revenue was 2312")
    result = verify_citation(page, _citation(4, "Net revenue was 2312"), DPI)
    assert result["page"] == 4
    assert result["quote"] == "Net revenue was 2312"
    assert result["status"] == "verified"
    assert result["boxes"] == _line_boxes(page)


@pytest.mark.parametrize("separator", [chr(0x2009), chr(0x202F)], ids=["thin-space", "narrow-no-break-space"])
def test_a_plain_space_in_the_quote_matches_a_thin_separator_in_the_number(separator):
    page = pymupdf.open().new_page(width=612, height=792)
    writer = pymupdf.TextWriter(page.rect)
    writer.append((72, 112), f"Net revenue was 2{separator}312", font=pymupdf.Font("helv"), fontsize=12)
    writer.write_text(page)
    assert separator in page.get_text()

    result = verify_citation(page, _citation(4, "Net revenue was 2 312"), DPI)
    assert result["status"] == "verified"
    assert result["boxes"] == _line_boxes(page)


def test_spaces_and_line_breaks_around_or_inside_the_quote_do_not_stop_the_match():
    page = _text_page("Net revenue was 2312")
    result = verify_citation(page, _citation(4, " Net revenue\nwas  2312 "), DPI)
    assert result["status"] == "verified"
    assert result["boxes"] == _line_boxes(page)


def test_a_quote_matches_a_ligature_in_the_text_layer():
    # Typeset PDFs often store "fi" as one ligature character, U+FB01, while the model reads two letters.
    fi = chr(0xFB01)
    page = pymupdf.open().new_page(width=612, height=792)
    writer = pymupdf.TextWriter(page.rect)
    writer.append((72, 112), f"The {fi}nancial year", font=pymupdf.Font("tiro"), fontsize=12)
    writer.write_text(page)
    assert fi in page.get_text()

    result = verify_citation(page, _citation(4, "The financial year"), DPI)
    assert result["status"] == "verified"
    assert result["boxes"] == _line_boxes(page)


def test_a_word_split_by_a_hyphen_at_a_line_end_is_verified():
    page = _text_page("Net reve-\nnue was 2312")
    result = verify_citation(page, _citation(4, "Net revenue was 2312"), DPI)
    assert result["status"] == "verified"
    assert len(result["boxes"]) == 2


def test_a_quote_in_a_different_case_is_verified():
    page = _text_page("Net revenue was 2312")
    result = verify_citation(page, _citation(4, "NET REVENUE WAS 2312"), DPI)
    assert result["status"] == "verified"
    assert result["boxes"] == _line_boxes(page)


def test_a_quote_spanning_two_lines_gets_one_box_per_line():
    page = _text_page("Net revenue\nwas 2312")
    result = verify_citation(page, _citation(4, "Net revenue was 2312"), DPI)
    assert result["status"] == "verified"
    assert result["boxes"] == _line_boxes(page)
    assert len(result["boxes"]) == 2


def test_a_quote_on_a_page_rotated_a_quarter_turn_gets_its_box_on_the_rotated_image():
    page = _text_page("Net revenue was 2312")
    [(x0, y0, x1, y1)] = [line["bbox"] for block in page.get_text("dict")["blocks"] for line in block["lines"]]
    page.set_rotation(90)
    result = verify_citation(page, _citation(4, "Net revenue was 2312"), DPI)
    # Turned 90 degrees clockwise, the point (x, y) of the 612 x 792 page lands at (792 - y, x) on the image.
    assert result["boxes"] == [pytest.approx([2 * (792 - y1), 2 * x0, 2 * (792 - y0), 2 * x1], abs=2)]


def test_a_quote_not_on_the_page_is_unverified_with_no_boxes():
    page = _text_page("Net revenue was 2312")
    result = verify_citation(page, _citation(4, "Net revenue was 2900"), DPI)
    assert result["status"] == "unverified"
    assert result["boxes"] == []


@pytest.mark.parametrize(
    "quote", ["Net revenue was 12", "2,312 total"], ids=["cut-at-the-end", "cut-at-the-start"]
)
def test_a_quote_that_stops_inside_a_number_is_unverified_with_no_boxes(quote):
    page = _text_page("Net revenue was 12,312 total")
    result = verify_citation(page, _citation(4, quote), DPI)
    assert result["status"] == "unverified"
    assert result["boxes"] == []


@pytest.mark.parametrize(
    ("text", "quote"),
    [("Price US$2,312 net", "$2,312"), ("1.Introduction", "Introduction")],
    ids=["symbol-first", "after-a-section-number"],
)
def test_a_quote_whose_edge_is_not_a_letter_or_digit_is_verified(text, quote):
    page = _text_page(text)
    result = verify_citation(page, _citation(4, quote), DPI)
    assert result["status"] == "verified"


def test_a_quote_of_only_spaces_is_unverified_with_no_boxes():
    page = _text_page("Net revenue was 2312")
    result = verify_citation(page, _citation(4, "   "), DPI)
    assert result["status"] == "unverified"
    assert result["boxes"] == []


def test_a_page_with_no_text_layer_is_approximate_with_the_model_box_in_pixels():
    result = verify_citation(_scan_page(), _citation(9, "Net revenue was 2312", [100, 200, 150, 400]), DPI)
    assert result["status"] == "approximate"
    # The page image is 1224 x 1584 pixels; box_2d is [ymin, xmin, ymax, xmax] on a 0-1000 scale.
    assert result["boxes"] == [pytest.approx([244.8, 158.4, 489.6, 237.6], abs=2)]


@pytest.mark.parametrize(
    "box_2d",
    [[0, 0, 0, 0], [150, 400, 100, 200], [1100, 1100, 1200, 1200]],
    ids=["empty", "min-after-max", "off-the-page"],
)
def test_a_model_box_with_no_area_on_the_page_image_is_unverified_with_no_boxes(box_2d):
    result = verify_citation(_scan_page(), _citation(9, "Net revenue was 2312", box_2d), DPI)
    assert result["status"] == "unverified"
    assert result["boxes"] == []


def test_a_citation_to_a_page_that_was_not_retrieved_is_unverified_with_no_boxes():
    result = verify_citation(None, _citation(11, "Net revenue was 2312"), DPI)
    assert result == {"page": 11, "quote": "Net revenue was 2312", "label": "", "status": "unverified", "boxes": []}
