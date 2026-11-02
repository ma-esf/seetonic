# seetonic

Ask a PDF a question and see the evidence highlighted on the page.

You upload a PDF of up to 50 pages and ask a question about it. Seetonic answers from the pages that best match the
question. For every claim it gives the page, the exact quote and a short label, and highlights the quote on the page
image. Gemini Flash writes the answer, but every quote is verified deterministically, with no LLM call: PyMuPDF
searches the cited page's text layer for it (`app/verify.py`). Each citation's status comes from that check, not from
the model.

Before a question is answered, two models label it: Jev (TypeSafe) and Gemini Flash. Seetonic gives a fixed reply,
without calling the answer model, to a question that is too vague, off topic, or an attempt to change or reveal the
instructions.

## Table of Contents

- [Background](#background)
- [Install](#install)
  - [Dependencies](#dependencies)
- [Usage](#usage)
  - [CLI](#cli)
- [Configuration](#configuration)
- [Deploy](#deploy)
- [Data location](#data-location)
- [Tests](#tests)
- [API](#api)
  - [`POST /upload`](#post-upload)
  - [`POST /ask`](#post-ask)
  - [`GET /files/{path}`](#get-filespath)
- [License](#license)

## Background

The point is answers you can check. An LLM can hallucinate or misquote a citation and still state it with confidence,
so Seetonic marks each citation `unverified` until the text-layer search finds the quote. Each one gets one of three
statuses:

| Status | Meaning |
|---|---|
| `verified` | The quote was found on the cited page's text layer, as whole words and whole numbers. Its boxes come from the PDF. |
| `approximate` | The page has no text layer (a scan), so the box the model gave is shown instead. |
| `unverified` | The quote was not found, or the cited page was not one of the pages the model was given. No box is shown. |

How one PDF goes through the service:

1. **Upload.** The PDF is checked (a real PDF, no password, 1 to 50 pages). Each page is rendered to a PNG at 144 DPI
   and embedded as an image with `gemini-embedding-2`. Nothing is written until every page is rendered and embedded.
   Then the PDF and the page images go to Cloud Storage, and one row per page goes to BigQuery in a single load job.
2. **Label the question.** Jev and Flash each label the question `answer`, `clarify`, `off_topic` or `attack`. Jev's
   label decides, but if Flash says `attack`, or Gemini's safety filter blocks the question, the question is refused.
3. **Retrieve.** The question is embedded as text, and BigQuery `VECTOR_SEARCH` returns the 3 pages nearest to it by
   cosine distance.
4. **Answer.** Flash gets those page images and returns an answer and its citations as JSON.
5. **Verify.** PyMuPDF searches each quote on its page and turns the matches into pixel boxes on the page image. For a
   citation with a box, the first box is cropped out and saved as a snippet image.
6. **Log.** Every question is written to a BigQuery table with the pages, the statuses, the latency and both labels. A
   failed log write is printed to stderr and never costs the user the answer.

Built with FastAPI, PyMuPDF, Gemini on Vertex AI (Agent Platform), Jev on TypeSafe, Cloud Storage, BigQuery and
Cloud Run. The web page in `static/index.html` is plain HTML and JavaScript with no build step.

## Install

```sh
git clone https://github.com/ma-esf/seetonic.git
cd seetonic
uv sync
```

`uv sync` creates `.venv` with the exact versions in `uv.lock`, including pytest.

### Dependencies

- Python 3.12 or later.
- [uv](https://docs.astral.sh/uv/).
- The [Google Cloud CLI](https://cloud.google.com/sdk/docs/install) (`gcloud` and `bq`), logged in to a Google Cloud
  project with billing on.
- A TypeSafe API key for Jev.

The service has no local storage. Even when it runs on your machine, it reads and writes the Cloud Storage bucket and
the BigQuery tables, and it calls Gemini and Jev. So set up the cloud resources once:

1. Create the secret that holds the TypeSafe key. `setup.sh` grants access to it but does not create it, so the key
   never lands in a file:

   ```sh
   printf '%s' "$KEY" | gcloud secrets create typesafe-api-key --data-file=- --project seetonic-demo
   ```

2. Run `setup.sh`. It turns on the APIs, creates the `seetonic-run` service account and its roles, the bucket, the
   BigQuery dataset and the `pages` and `questions` tables. It is safe to run again.

   ```sh
   GOOGLE_CLOUD_PROJECT=seetonic-demo ./setup.sh
   ```

## Usage

Run the service locally on your own Google login:

```sh
gcloud auth application-default login
export GOOGLE_CLOUD_PROJECT=seetonic-demo
export TYPESAFE_API_KEY="$(gcloud secrets versions access latest --secret typesafe-api-key --project "$GOOGLE_CLOUD_PROJECT")"
uv run uvicorn app.main:app --port 8080
```

Open <http://localhost:8080>, upload a PDF, then ask a question. The answer lists each citation with its status, label,
quote and snippet, and shows which label, Jev's or Flash's, decided the question. Click a citation to open its page
beside the answer with the quote boxed; you can zoom and step through the citations there.

Your own account needs the same access the service account has: Vertex AI, the bucket, and the BigQuery dataset.

### CLI

Each script takes the base URL of a running service, local or deployed.

Check the whole path end to end. It builds a one-page PDF, uploads it, asks about it and checks every citation field
against the API contract. It prints `PASS` and exits 0, or prints `FAIL` with the first problem and exits 1:

```sh
uv run python scripts/smoke.py http://localhost:8080
```

Measure retrieval and citations on the labeled set in `eval/questions.jsonl` (20 questions about the two Apple PDFs in
`eval/pdfs/`). It prints one row per question, then hit@3, MRR@3 and the verification rate, overall and per PDF. The
service must run with the default `TOP_K=3`. A busy model (HTTP 502 or a timeout) is retried up to 3 times, a minute
apart:

```sh
uv run python scripts/evaluate.py http://localhost:8080
```

Both scripts upload PDFs and ask questions like a real user, so they write to the bucket and the BigQuery tables.

See which pages retrieval picks for a question, without asking the answer model. It calls Gemini and BigQuery
directly, so it needs the same login and settings as the service:

```sh
uv run python scripts/search.py <doc_id> "What were total liabilities?"
```

It prints one line per page: the page number and its cosine similarity, best first.

## Configuration

Every setting is an environment variable read in `app/config.py`. `deploy.sh` repeats every default, `setup.sh` the
project and storage ones and `scripts/evaluate.py` `TOP_K`, so a change to a default goes there too, and in this table.

| Variable | Default | What it sets |
|---|---|---|
| `GOOGLE_CLOUD_PROJECT` | `seetonic-demo` | The Google Cloud project. |
| `GOOGLE_CLOUD_LOCATION` | `eu` | The Gemini endpoint. `eu` keeps Gemini calls in the EU. |
| `EMBEDDING_MODEL` | `gemini-embedding-2` | The model that embeds page images and questions. |
| `EMBEDDING_SIZE` | `768` | The length of each embedding vector. |
| `FLASH_MODEL` | `gemini-3.8-flash` | The model that labels questions and writes answers. |
| `JEV_MODEL` | `jev-1.13.0` | The Jev model that labels questions. |
| `TYPESAFE_API_KEY` | empty | The TypeSafe key. On Cloud Run it comes from the `typesafe-api-key` secret. |
| `DPI` | `144` | The resolution pages are rendered at. Citation boxes are in pixels at this DPI. |
| `TOP_K` | `3` | How many pages are retrieved and sent to the answer model. |
| `MAX_PAGES` | `50` | The largest PDF accepted, in pages. |
| `DATA_LOCATION` | `europe-north1` | The region of the bucket and the BigQuery dataset. |
| `BUCKET` | `<project>-files` | The Cloud Storage bucket. |
| `DATASET` | `seetonic` | The BigQuery dataset. |
| `QUESTIONS_TABLE` | `questions` | The BigQuery table that logs each question. |

`setup.sh` also reads `DATA_LOCATION`, `BUCKET`, `DATASET` and `QUESTIONS_TABLE`. `deploy.sh` also reads `REGION`
(default `europe-north1`), the Cloud Run region.

## Deploy

After `setup.sh`, deploy to Cloud Run:

```sh
GOOGLE_CLOUD_PROJECT=seetonic-demo ./deploy.sh
```

It builds the image from the `Dockerfile` in Cloud Build, deploys the `seetonic` service and prints its URL. Every run
deploys a new revision. The service runs as `seetonic-run`, keeps one instance running so no request waits for a cold
start, scales up to 2 instances, and takes one request per instance, because PyMuPDF is not thread-safe. That also caps
the service at two requests at once, which caps the rate of model calls. `.gcloudignore` uploads only the
`Dockerfile`, `pyproject.toml`, `uv.lock`, `app/` and `static/`.

Who may call the service is set in IAM, not by the script, so a redeploy keeps it open or closed. Check the deployed
service with `scripts/smoke.py` and its URL.

## Data location

The PDFs, the page images, the snippets, the embeddings and the question log are stored in `DATA_LOCATION`
(`europe-north1` by default). Gemini is called through the `eu` endpoint. TypeSafe names no EU region, so the text of
each question is sent to Jev and may leave the EU. Page content is never sent to Jev.

`/files/` serves only PNGs, so the uploaded PDF itself is never served back.

## Tests

```sh
uv run pytest
```

The tests replace every model and cloud call, so they need no Google login and no TypeSafe key. They cover citation
verification, PDF checks, how `/ask` combines the two labels and logs each question, and the evaluation metrics.

## API

The service has three routes. Everything else serves the web page from `static/`.

### `POST /upload`

Takes a multipart form with one field, `file`, holding the PDF.

```sh
curl -F file=@report.pdf http://localhost:8080/upload
```

```json
{"doc_id": "3f2a…", "pages": 12}
```

Returns 400, with a message in `detail`, for a file that is not a PDF, a password-protected PDF, a PDF with no pages,
or one over `MAX_PAGES`. If a model call fails during the upload, the request fails and nothing is stored.

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
| `answer` | The model's answer, or the fixed reply when the question was refused. |
| `pages` | The retrieved pages and their cosine similarity, best first. Empty when refused. |
| `citations[].status` | `verified`, `approximate` or `unverified`, set by `verify.verify_citation`, not by the model. See [Background](#background). |
| `citations[].boxes` | The quote's place as `[x0, y0, x1, y1]` in pixels on the page image at `DPI`, origin top left. One box per line. Empty when `unverified`. |
| `citations[].snippet_url` | A cropped image of the first box, or `null` when there is no box. |
| `decision` | The label that decided: `answer`, `clarify`, `off_topic`, `attack` or `blocked`. |
| `route` | Flash's label, or `blocked` when the safety filter blocked the question. |
| `jev_route`, `jev_confidence` | Jev's label and its confidence. |

Returns 404 when no pages are stored for `doc_id`, and 502 when Gemini or Jev fails or the answer does not fit the
citation format. A 502 is worth asking again.

### `GET /files/{path}`

Serves a PNG from the bucket: a page image at `/files/<doc_id>/pages/<page>.png`, or a snippet from `snippet_url`.
Any other path returns 404.

## License

UNLICENSED © ma-esf
