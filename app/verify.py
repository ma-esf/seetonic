import re

import pymupdf

from app.gemini import Citation

# Thousands separators to try between the digits of a number such as "2 312": plain, thin, narrow no-break space.
# A plain space in search_for also matches U+00A0 in the text layer, but a thin separator only matches itself.
SEPARATORS = [" ", chr(0x2009), chr(0x202F)]


def _stands_alone(quote: str, text: str) -> bool:
    """True when the quote occurs at least once in the text without cutting a longer word or number short.

    Only an edge that is a letter or digit is checked: "2,312" may not be read from "12,312" or "2,312.5",
    but "$2,312" may follow "US" and "Introduction" may follow "1.".
    """
    before = r"(?<!\w)" if quote[0].isalnum() else ""
    before += r"(?<!\d[.,])" if quote[0].isdigit() else ""
    after = r"(?![.,]\d)" if quote[-1].isdigit() else ""
    after += r"(?!\w)" if quote[-1].isalnum() else ""
    return re.search(before + re.escape(quote) + after, text) is not None


def verify_citation(page: pymupdf.Page | None, citation: Citation, dpi: int) -> dict:
    """Decide the citation's status in code; boxes are [x0, y0, x1, y1] in page-image pixels, origin top left.

    page is the cited page, or None when it was not among the retrieved pages.
    """
    # The label is the model's words and is passed on unchecked; only the quote is checked.
    result = {
        "page": citation.page, "quote": citation.quote, "label": citation.label, "status": "unverified", "boxes": []
    }
    if page is None:
        return result
    scale = dpi / 72  # PyMuPDF positions are in points, 72 to the inch
    # The same flags as search_for below, so both see the same text: a word hyphenated at a line end joined, and a
    # ligature such as U+FB01 split into its letters.
    text = page.get_text(flags=pymupdf.TEXTFLAGS_SEARCH)
    if not text.strip():
        # A scan has no text to search, so keep the model's box.
        return with_model_box(result, page, citation.box_2d, dpi)
    # Every run of whitespace, Unicode spaces included, becomes one plain space, in the quote and in the page text.
    quote = " ".join(citation.quote.split())
    # search_for also matches inside a longer word or number, so check the quote stands alone at least once. The
    # boxes still cover every match: "2,312" also highlights inside "12,312".
    if not quote or not _stands_alone(quote.lower(), " ".join(text.split()).lower()):
        return result
    for separator in SEPARATORS:
        # One rectangle per line, for every place the quote occurs, on the unrotated page.
        rects = page.search_for(re.sub(r"(?<=\d) (?=\d)", separator, quote), flags=pymupdf.TEXTFLAGS_SEARCH)
        if rects:
            break
    # The image shows the page rotated, and text can stick out past the page edge: keep only the part on the image.
    on_page = [(rect * page.rotation_matrix) & page.rect for rect in rects]
    boxes = [list(box * scale) for box in on_page if not box.is_empty]
    if boxes:
        return {**result, "status": "verified", "boxes": boxes}
    return result


def with_model_box(result: dict, page: pymupdf.Page, box_2d: list[int], dpi: int) -> dict:
    """Mark the result approximate with a model's box, [ymin, xmin, ymax, xmax] on a 0-1000 scale, in page-image
    pixels; return it unchanged when no part of the box is on the page image."""
    ymin, xmin, ymax, xmax = box_2d
    width, height = page.rect.width * dpi / 72, page.rect.height * dpi / 72
    box = pymupdf.Rect(xmin * width / 1000, ymin * height / 1000, xmax * width / 1000, ymax * height / 1000)
    box &= pymupdf.Rect(0, 0, width, height)  # keep only the part on the page image
    if box.is_empty:  # zero size, min after max, or off the page: no place to show
        return result
    return {**result, "status": "approximate", "boxes": [list(box)]}
