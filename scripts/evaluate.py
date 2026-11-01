"""Measure retrieval, citations and answers on the labeled set in eval/questions.jsonl: hit@3, MRR@3, the verification
rate and answer accuracy. A question the router rejects counts as not retrieved.

Usage:
  uv run python scripts/evaluate.py <base URL>

Uploads each PDF once, asks every question and prints two Markdown tables: one row per question, then the metrics
for all questions and for each PDF. Then prints each wrong answer with its expected facts. A run writes to the cloud
project like real traffic does.
"""

import json
import re
import sys
import time
from pathlib import Path

import httpx
import pymupdf

ROOT = Path(__file__).resolve().parent.parent  # the PDF paths in the labeled set are relative to the repo root
QUESTIONS = ROOT / "eval" / "questions.jsonl"
RETRIES = 3  # with WAIT_SECONDS, outlasts a busy model (a Vertex 429), which clears within minutes
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


def answer_accuracy(correct: list[bool]) -> float:
    """The share of answers that hold every expected fact."""
    return sum(correct) / len(correct)


def _stands_alone(spelling: str, text: str) -> bool:
    """True when the spelling is in the text and does not cut a longer word or number short: the rule of
    app/verify.py, copied because this script talks to the service over HTTP and imports nothing from app/."""
    before = r"(?<!\w)" if spelling[0].isalnum() else ""
    before += r"(?<!\d[.,])" if spelling[0].isdigit() else ""
    after = r"(?![.,]\d)" if spelling[-1].isdigit() else ""
    after += r"(?!\w)" if spelling[-1].isalnum() else ""
    return re.search(before + re.escape(spelling) + after, text) is not None


def answer_holds(answer: str, expect: list[list[str]]) -> bool:
    """True when every fact has one of its spellings in the answer, ignoring case and line breaks."""
    text = " ".join(answer.split()).lower()
    return all(any(_stands_alone(spelling.lower(), text) for spelling in fact) for fact in expect)


def _post(client: httpx.Client, path: str, **kwargs) -> dict:
    """POST and return the JSON reply. A 502 or a timeout, as when the model is busy, is retried RETRIES times; any other
    failure stops the run."""
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
    correct = [result["correct"] for result in results]
    rate = f"{verification_rate(statuses):.2f} ({statuses.count('verified')} of {len(statuses)})"
    accuracy = f"{answer_accuracy(correct):.2f} ({sum(correct)} of {len(correct)})"
    return f"| {label} ({len(results)}) | {hit_rate(ranks):.2f} | {mrr(ranks):.2f} | {rate} | {accuracy} |"


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
            page_text = doc[pair["page"] - 1].get_text(flags=pymupdf.TEXTFLAGS_SEARCH)  # as app/verify.py reads it
        # A mistyped figure would mark a right answer wrong.
        for fact in pair["expect"]:
            if not answer_holds(page_text, [fact]):
                sys.exit(f"FAIL: no spelling of {fact} is on page {pair['page']}: {pair['question']}")
    results = []
    # Well past one upload of the 32-page 10-Q, so only a hung request runs into it.
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
            correct = answer_holds(reply["answer"], pair["expect"])
            results.append({**pair, "rank": rank, "decision": reply["decision"], "statuses": statuses,
                            "answer": reply["answer"], "correct": correct})

    print("| PDF | Question | Labeled page | Rank | Statuses | Correct |")
    print("|---|---|---|---|---|---|")
    for result in results:
        if result["decision"] != "answer":
            rank = f"rejected ({result['decision']})"
        else:
            rank = "missed" if result["rank"] is None else result["rank"]
        statuses = ", ".join(result["statuses"]) or "none"
        question = result["question"].replace("|", "\\|")  # a bare | would start a new cell
        correct = "yes" if result["correct"] else "no"
        print(f"| {Path(result['pdf']).name} | {question} | {result['page']} | {rank} | {statuses} | {correct} |")
    print()
    print("| Questions | hit@3 | MRR@3 | Verification rate | Answer accuracy |")
    print("|---|---|---|---|---|")
    print(_summary_row("All", results))
    for pdf in uploads:
        print(_summary_row(Path(pdf).name, [result for result in results if result["pdf"] == pdf]))
    # Printing the answer tells a fact that lacks a spelling apart from a wrong answer.
    for result in results:
        if not result["correct"]:
            print(f"\n### Wrong: {result['question']}\n\nExpected: {result['expect']}\n\n{result['answer']}")
