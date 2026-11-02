# seetonic

Ask a PDF a question and see the evidence highlighted on the page.

Visual RAG over PDFs of up to 50 pages, with citations checked in code. Pages are embedded as images. Gemini Flash
answers from the top 3 and cites each claim as page, quote and label. PyMuPDF then searches every quote in the cited
page's text layer and boxes it on the page image. A citation's status comes from that search, never from the model.
Jev (TypeSafe) and Flash route each question first, and vague, off-topic and injection questions get a fixed reply.

Live: <https://seetonic-v77e2oesjq-lz.a.run.app>

## Table of Contents

- [How it works](#how-it-works)
- [Evaluation](#evaluation)
- [Install](#install)
- [Usage](#usage)
- [Tests](#tests)
- [API](#api)
- [Contributing](#contributing)
- [License](#license)

## How it works

One PDF, end to end:

1. **Upload.** Validate (a PDF, no password, 1 to 50 pages), render each page to PNG at 144 DPI, and embed it with
   `gemini-embedding-2` at 768 dimensions. Nothing is written until every page is embedded; then the PDF and PNGs go to
   Cloud Storage and the rows to BigQuery in one load job.
2. **Route.** Jev and Flash each label the question `answer`, `clarify`, `off_topic` or `attack`. Jev's label wins,
   unless Flash says `attack` or Gemini's safety filter blocks the question. Only the question is screened: text in the
   PDF reaches Flash unscreened.
3. **Retrieve.** Embed the question as text and run an exact cosine `VECTOR_SEARCH` over the document's pages, top 3.
4. **Answer.** Flash gets the 3 page images and returns the answer and its citations as JSON.
5. **Verify.** PyMuPDF searches each quote on its page. Matches become pixel boxes, and the first is cropped as a
   snippet.
6. **Log.** Every reply, answered or refused, goes to BigQuery with the pages, statuses, latency and both labels.
   A request that ends in a 404 or 502 writes no row, and a failed log write never fails the request.

Citation statuses:

| Status | Meaning |
|---|---|
| `verified` | The quote is on the cited page's text layer, as whole words and numbers. Boxes come from the PDF. |
| `approximate` | The page has no text layer (a scan), so the model's box is shown. |
| `unverified` | The quote is not on the page, the page was not one the model saw, or a scan's box falls off the page. No box. |

Stack: FastAPI, PyMuPDF, Gemini on Vertex AI, Jev on TypeSafe, Cloud Storage, BigQuery, Cloud Run. The frontend is
one static HTML file with no build step.

Data stays in the EU: storage is in `europe-north1` and Gemini is called through the `eu` endpoint. The exception is
the question text sent to Jev, since TypeSafe names no EU region. Page content never goes to Jev.

## Evaluation

- **Set:** 20 questions in `eval/questions.jsonl`, each labeled with the one page that answers it. 13 were drafted
  from that page's text, so their wording may favour retrieval.
- **Documents:** the 10-Q (`APPLE_10Q_Q3_2026.pdf`, 32 pages, 15 questions) and the statements
  (`APPLE_Statements.pdf`, 3 pages, 5 questions).
- **Run:** once, on 2026-11-01, with `gemini-embedding-2`, `gemini-3.8-flash` and top 3.

Metrics:

- **hit@3:** the share of questions whose labeled page is among the 3 pages retrieved. Also called top-3 retrieval
  accuracy.
- **MRR@3:** the mean of 1 / rank of the labeled page, counting 0 when it is not in the top 3. 1.00 means it always
  ranked first.
- **Verified citations:** citations whose quote was found on the cited page, out of all citations.

| Document | No. of questions | hit@3 | MRR@3 | Verified citations |
|---|---|---|---|---|
| Both | 20 | 0.90 | 0.85 | 26 of 26 |
| 10-Q | 15 | 0.87 | 0.83 | 21 of 21 |
| Statements | 5 | 1.00 | 0.90 | 5 of 5 |

1. **Read retrieval from the 10-Q.** The statements have 3 pages, so their hit@3 is 1.00 by construction.
2. **Both misses are on the 10-Q:**
   1. *Capital expenditures* (page 8): the page never says "capital expenditures", only "Payments for acquisition
      of property, plant and equipment".
   2. *Corporate bonds* (page 10, June 2026): page 11 holds the same table for September 2025 and ranked higher.
      The model cited the retrieved pages: 4 verified quotes, wrong period.
3. **Not measured:** answer correctness, scanned PDFs, and variance (one run of 20 questions).

## Install

```sh
git clone https://github.com/ma-esf/seetonic.git
cd seetonic
uv sync
```

Needs Python 3.12+, [uv](https://docs.astral.sh/uv/), the [Google Cloud CLI](https://cloud.google.com/sdk/docs/install)
and a TypeSafe API key. There is no local storage: a local server still uses Cloud Storage, BigQuery, Gemini and Jev.
`setup.sh` provisions the project, `deploy.sh` deploys to Cloud Run, and every setting is an environment variable in
`app/config.py`.

## Usage

Use the [live service](https://seetonic-v77e2oesjq-lz.a.run.app), or run it locally against a project that `setup.sh`
has provisioned:

```sh
gcloud auth application-default login
export TYPESAFE_API_KEY=...
uv run uvicorn app.main:app --port 8080
```

Scripts in `scripts/`:

- `smoke.py <URL>`: end-to-end check of one upload and one question against the API contract.
- `evaluate.py <URL>`: the [Evaluation](#evaluation) run. Needs `TOP_K=3` on the server.
- `search.py <doc_id> "<question>"`: the pages retrieval picks, without calling the answer model.

`smoke.py` and `evaluate.py` write to the bucket and tables like real traffic.

## Tests

```sh
uv run pytest
```

Every model and cloud call is faked, so no credentials are needed. Covers citation verification, PDF validation,
routing and logging in `/ask`, and the evaluation metrics.

## API

Three routes; everything else serves `static/`.

### `POST /upload`

Multipart, one field `file`.

```sh
curl -F file=@report.pdf http://localhost:8080/upload
```

```json
{"doc_id": "3f2a…", "pages": 12}
```

400 for a non-PDF, a password-protected PDF, an empty PDF or more than `MAX_PAGES` pages.

### `POST /ask`

```sh
curl -H 'Content-Type: application/json' \
  -d '{"doc_id": "3f2a…", "question": "What was net revenue in 2024?"}' \
  http://localhost:8080/ask
```

```json
{
  "answer": "Net revenue was 2 312 million.",
  "pages": [{"page": 4, "score": 0.61}, {"page": 5, "score": 0.48}, {"page": 1, "score": 0.40}],
  "citations": [
    {
      "page": 4,
      "quote": "2 312",
      "label": "Net revenue, year ended December 31, 2024",
      "status": "verified",
      "boxes": [[412.0, 380.5, 455.3, 398.0]],
      "snippet_url": "/files/3f2a…/snippets/9c1e….png"
    }
  ],
  "decision": "answer",
  "route": "answer",
  "jev_route": "answer",
  "jev_confidence": 0.97
}
```

| Field | Meaning |
|---|---|
| `answer` | The answer, or the fixed reply when refused. |
| `pages` | Retrieved pages with cosine similarity, best first. Empty when refused. |
| `citations[].status` | See [How it works](#how-it-works). Set by `verify.verify_citation`, not the model. |
| `citations[].boxes` | `[x0, y0, x1, y1]` in pixels on the page image at `DPI`, origin top left, one per line. Empty when `unverified`. |
| `citations[].snippet_url` | A crop of the first box, or `null`. |
| `decision` | The label that decided: `answer`, `clarify`, `off_topic`, `attack` or `blocked`. |
| `route` | Flash's label, or `blocked` by the safety filter. |
| `jev_route`, `jev_confidence` | Jev's label and confidence. |

404 when `doc_id` has no pages. 502 when Gemini or Jev fails or the answer does not fit the citation format; it is
safe to retry.

### `GET /files/{path}`

A page image at `/files/<doc_id>/pages/<page>.png`, or a snippet from `snippet_url`. Only PNGs are served, never
the source PDF; anything else is 404.

## Contributing

Issues are welcome; pull requests are not expected.

## License

UNLICENSED © ma-esf
