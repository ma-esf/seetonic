"""Measure retrieval and citations on the labeled set in eval/questions.jsonl: hit@3, MRR@3 and the verification rate.
A question the router rejects counts as not retrieved.

Usage:
  uv run python scripts/evaluate.py <base URL>

Uploads each PDF once, asks every question and prints two Markdown tables: one row per question, then the metrics
for all questions and for each PDF. A run writes to the cloud project like real traffic does.
"""

import json
import sys
import time
from pathlib import Path

import httpx
import pymupdf

ROOT = Path(__file__).resolve().parent.parent  # the PDF paths in the labeled set are relative to the repo root
QUESTIONS = ROOT / "eval" / "questions.jsonl"
RETRIES = 3  # Each retry waits WAIT_SECONDS; request time is additional.
WAIT_SECONDS = 60
TOP_K = 3  # the metrics are @3, so the server must keep its default TOP_K


def retrieved_pages(reply: dict, page_count: int) -> list[int]:
    """The page numbers an /ask reply retrieved, best first, or none for a rejected question. Stops the run unless an
    answered reply has min(TOP_K, page_count) of them, since the metrics are @3."""
    if reply["decision"] != "answer":
        return []
    pages = [page["page"] for page in reply["pages"]]
    if len(pages) != min(TOP_K, page_count):
        sys.exit(f"FAIL: /ask returned {len(pages)} of {page_count} pages; run the server with TOP_K={TOP_K}")
    return pages


def rank_of(pages: list[int], labeled: int) -> int | None:
    """The labeled page's position among the retrieved pages, counting from 1, or None when it was not retrieved."""
    return pages.index(labeled) + 1 if labeled in pages else None


def hit_rate(ranks: list[int | None]) -> float:
    """The share of questions whose labeled page was retrieved. /ask returns the top 3, so this is hit@3."""
    return sum(rank is not None for rank in ranks) / len(ranks)


def mrr(ranks: list[int | None]) -> float:
    """The mean of 1 / rank, counting 0 for a labeled page that was not retrieved. Only 3 come back, so this is MRR@3."""
    return sum(1 / rank for rank in ranks if rank is not None) / len(ranks)


def verification_rate(statuses: list[str]) -> float:
    """Verified citations over all citations, across every answer. With no citations, nothing was verified."""
    return statuses.count("verified") / len(statuses) if statuses else 0.0


def _post(client: httpx.Client, path: str, **kwargs) -> dict:
    """POST and return the JSON reply. A 502 or a timeout is retried RETRIES times; any other failure stops the run.

    A 502 is a Gemini or Jev failure, or a model reply that did not fit its format, so such an answer is asked again
    and never counted.
    """
    for attempt in range(1 + RETRIES):
        if attempt:
            time.sleep(WAIT_SECONDS)
        try:
            response = client.post(path, **kwargs)
        except httpx.TimeoutException:
            failure = f"{path} timed out"
            continue
        if response.status_code == 200:
            return response.json()
        failure = f"{path} returned {response.status_code}: {response.text}"
        if response.status_code != 502:
            break
    sys.exit(f"FAIL: {failure}")


def _summary_row(label: str, results: list[dict]) -> str:
    ranks = [result["rank"] for result in results]
    statuses = [status for result in results for status in result["statuses"]]
    rate = f"{verification_rate(statuses):.2f} ({statuses.count('verified')} of {len(statuses)})"
    return f"| {label} ({len(results)}) | {hit_rate(ranks):.2f} | {mrr(ranks):.2f} | {rate} |"


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    pairs = [json.loads(line) for line in QUESTIONS.read_text().splitlines() if line.strip()]
    if not pairs:
        sys.exit(f"FAIL: {QUESTIONS} holds no questions")
    # A label past the last page could never be retrieved and would count as a retrieval miss.
    for pair in pairs:
        with pymupdf.open(ROOT / pair["pdf"]) as doc:
            if not 1 <= pair["page"] <= doc.page_count:
                sys.exit(f"FAIL: {pair['pdf']} has no page {pair['page']}: {pair['question']}")
    results = []
    with httpx.Client(base_url=sys.argv[1].rstrip("/"), timeout=120) as client:
        uploads = {}
        for pdf in dict.fromkeys(pair["pdf"] for pair in pairs):
            file = (Path(pdf).name, (ROOT / pdf).read_bytes(), "application/pdf")
            uploads[pdf] = _post(client, "/upload", files={"file": file})
        for pair in pairs:
            upload = uploads[pair["pdf"]]
            reply = _post(client, "/ask", json={"doc_id": upload["doc_id"], "question": pair["question"]})
            rank = rank_of(retrieved_pages(reply, upload["pages"]), pair["page"])
            statuses = [citation["status"] for citation in reply["citations"]]
            results.append({**pair, "rank": rank, "decision": reply["decision"], "statuses": statuses})

    print("| PDF | Question | Labeled page | Rank | Statuses |")
    print("|---|---|---|---|---|")
    for result in results:
        if result["decision"] != "answer":
            rank = f"rejected ({result['decision']})"
        else:
            rank = "missed" if result["rank"] is None else result["rank"]
        statuses = ", ".join(result["statuses"]) or "none"
        question = result["question"].replace("|", "\\|")  # a bare | would start a new cell
        print(f"| {Path(result['pdf']).name} | {question} | {result['page']} | {rank} | {statuses} |")
    print()
    print("| Questions | hit@3 | MRR@3 | Verification rate |")
    print("|---|---|---|---|")
    print(_summary_row("All", results))
    for pdf in uploads:
        print(_summary_row(Path(pdf).name, [result for result in results if result["pdf"] == pdf]))
