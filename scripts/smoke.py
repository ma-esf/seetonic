"""Upload a one-page PDF to a running service, ask about it and check every citation against the contract.

Usage:
  uv run python scripts/smoke.py <base URL>

Prints PASS and exits 0, or prints FAIL with the first problem (the endpoint that failed, the decision when /ask did not
answer, or the citation field) and exits 1.
"""

import sys

import httpx
import pymupdf

SENTENCE = "The invoice total is 4 812 euros."
QUESTION = "What is the invoice total?"
# The types each citation field may hold. type() is compared, not isinstance(), because True is an int.
FIELDS = {
    "page": (int,), "quote": (str,), "label": (str,), "status": (str,), "boxes": (list,),
    "snippet_url": (str, type(None)),
}
STATUSES = {"verified", "approximate", "unverified"}


def one_page_pdf() -> bytes:
    with pymupdf.open() as doc:
        doc.new_page().insert_text((72, 112), SENTENCE)
        return doc.tobytes()


def _is_box(box) -> bool:
    return type(box) is list and len(box) == 4 and all(type(value) in (int, float) for value in box)


def contract_failure(citations) -> str | None:
    """Return the first way the citations break the contract, naming the field, or None when they keep it."""
    if type(citations) is not list:
        return f"citations is {citations!r}"
    for number, citation in enumerate(citations, start=1):
        if type(citation) is not dict:
            return f"citations: citation {number} is {citation!r}"
        for field, types in FIELDS.items():
            if field not in citation:
                return f"citation {number} has no {field}"
            if type(citation[field]) not in types:
                return f"citation {number}: {field} is {citation[field]!r}"
        if citation["status"] not in STATUSES:
            return f"citation {number}: status is {citation['status']!r}"
        if not all(_is_box(box) for box in citation["boxes"]):
            return f"citation {number}: boxes holds a box that is not [x0, y0, x1, y1]: {citation['boxes']!r}"
        if (citation["status"] == "unverified") != (citation["boxes"] == []):
            return f"citation {number}: status is {citation['status']} but boxes is {citation['boxes']!r}"
    if not any(citation["status"] == "verified" for citation in citations):
        return f"status: none of the {len(citations)} citation(s) is verified"
    return None


def _post(client: httpx.Client, path: str, **kwargs) -> dict:
    response = client.post(path, **kwargs)
    if response.status_code != 200:
        sys.exit(f"FAIL: {path} returned {response.status_code}: {response.text}")
    return response.json()


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    # One request can wait out a cold start and a model call, well past httpx's 5-second default.
    with httpx.Client(base_url=sys.argv[1].rstrip("/"), timeout=120) as client:
        upload = _post(client, "/upload", files={"file": ("smoke.pdf", one_page_pdf(), "application/pdf")})
        reply = _post(client, "/ask", json={"doc_id": upload["doc_id"], "question": QUESTION})
    if reply.get("decision") != "answer":
        # A rejection leaves no citations, and the check below would blame them instead of the routing.
        sys.exit(f"FAIL: /ask did not answer: decision {reply.get('decision')!r}, Jev {reply.get('jev_route')!r}")
    citations = reply.get("citations")
    failure = contract_failure(citations)
    if failure:
        sys.exit(f"FAIL: {failure}")
    verified = sum(citation["status"] == "verified" for citation in citations)
    print(f"PASS: {len(citations)} citation(s), {verified} verified")
