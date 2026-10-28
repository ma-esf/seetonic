import re

import pymupdf

from app.gemini import Citation

# Thousands separators to try between the digits of a number such as "2 312": plain, thin, narrow no-break space.
# A plain space in search_for also matches U+00A0 in the text layer, but a thin separator only matches itself.
SEPARATORS = [" ", chr(0x2009), chr(0x202F)]


def _stands_alone(quote: str, text: str) -> bool:
    """True when the quote is in the text and does not cut a longer word or number short.

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
    result = {"page": citation.page, "quote": citation.quote, "status": "unverified", "boxes": []}
    if page is None:
        return result
    scale = dpi / 72  # PyMuPDF positions are in points, 72 to the inch
    # TEXTFLAGS_SEARCH joins a word hyphenated at a line end and splits a ligature such as U+FB01 into its letters.
    # The default flags keep the ligature, and get_text's also keeps the hyphen.
    text = page.get_text(flags=pymupdf.TEXTFLAGS_SEARCH)
    if not text.strip():
        # A scan has no text to search, so keep the model's box: [ymin, xmin, ymax, xmax] on a 0-1000 scale.
        ymin, xmin, ymax, xmax = citation.box_2d
        width, height = page.rect.width * scale, page.rect.height * scale
        box = pymupdf.Rect(xmin * width / 1000, ymin * height / 1000, xmax * width / 1000, ymax * height / 1000)
        box &= pymupdf.Rect(0, 0, width, height)  # keep only the part on the page image
        if box.is_empty:  # zero size, min after max, or off the page: no place to show
            return result
        return {**result, "status": "approximate", "boxes": [list(box)]}
    # Every run of whitespace, Unicode spaces included, becomes one plain space, in the quote and in the page text.
    quote = " ".join(citation.quote.split())
    # search_for also matches inside a longer word or number.
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
