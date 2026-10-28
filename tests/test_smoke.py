import pymupdf
import pytest

from scripts.smoke import SENTENCE, contract_failure, one_page_pdf


def _citation(**fields) -> dict:
    citation = {"page": 1, "quote": "4 812 euros", "status": "verified", "boxes": [[1.0, 2.0, 3.0, 4.0]], "snippet_url": "/files/a.png"}
    return {**citation, **fields}


def test_the_pdf_has_the_sentence_in_its_text_layer():
    with pymupdf.open(stream=one_page_pdf(), filetype="pdf") as doc:
        assert len(doc) == 1
        assert SENTENCE in doc[0].get_text()


def test_citations_that_keep_the_contract_pass():
    unverified = _citation(status="unverified", boxes=[], snippet_url=None)
    approximate = _citation(status="approximate")
    assert contract_failure([_citation(), unverified, approximate]) is None


@pytest.mark.parametrize(
    "citation, field",
    [
        ({key: value for key, value in _citation(box=[[1, 2, 3, 4]]).items() if key != "boxes"}, "boxes"),
        (_citation(page="1"), "page"),
        (_citation(page=True), "page"),
        (_citation(quote=None), "quote"),
        (_citation(status="exact"), "status"),
        (_citation(boxes=[[1, 2, 3]]), "boxes"),
        (_citation(snippet_url=5), "snippet_url"),
        (_citation(status="unverified"), "boxes"),
        (_citation(boxes=[]), "boxes"),
    ],
    ids=[
        "boxes-renamed", "page-string", "page-bool", "quote-null", "unknown-status",
        "box-of-three", "snippet-url-number", "unverified-with-boxes", "verified-without-boxes",
    ],
)
def test_a_broken_citation_fails_and_names_the_field(citation, field):
    failure = contract_failure([citation])
    assert failure is not None
    assert field in failure


@pytest.mark.parametrize("citations", [None, "x", ["x"]], ids=["missing", "string", "citation-string"])
def test_citations_that_are_not_a_list_of_objects_fail_and_name_the_field(citations):
    assert "citations" in contract_failure(citations)


def test_an_answer_with_no_verified_citation_fails():
    approximate = _citation(status="approximate")
    assert "verified" in contract_failure([approximate])
    assert "verified" in contract_failure([])
