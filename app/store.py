import mimetypes

from google.cloud import bigquery, storage

from app import config

bucket = storage.Client(project=config.PROJECT).bucket(config.BUCKET)
bq = bigquery.Client(project=config.PROJECT, location=config.DATA_LOCATION)
PAGES_TABLE = f"{config.PROJECT}.{config.DATASET}.pages"
QUESTIONS_TABLE = f"{config.PROJECT}.{config.DATASET}.{config.QUESTIONS_TABLE}"

# Exact search: with no vector index, VECTOR_SEARCH compares the query with every row the doc_id pre-filter returns.
SEARCH_QUERY = f"""
SELECT base.page, 1 - distance AS similarity
FROM VECTOR_SEARCH(
  (SELECT * FROM `{PAGES_TABLE}` WHERE doc_id = @doc_id),
  'embedding',
  (SELECT @query_vector AS embedding),
  top_k => @k,
  distance_type => 'COSINE'
)
ORDER BY distance
"""


def save_file(path: str, data: bytes) -> None:
    # upload_from_string would otherwise label every object text/plain.
    bucket.blob(path).upload_from_string(data, content_type=mimetypes.guess_type(path)[0])


def load_file(path: str) -> bytes:
    return bucket.blob(path).download_as_bytes()


def insert_pages(rows: list[dict]) -> None:
    # A load job, not a streaming insert: it writes all rows or none, so the table never holds half a document.
    # setup.sh owns the schema: the load uses the table's own schema and never creates the table.
    job_config = bigquery.LoadJobConfig(
        autodetect=False, create_disposition=bigquery.CreateDisposition.CREATE_NEVER
    )
    bq.load_table_from_json(rows, PAGES_TABLE, job_config=job_config).result()


def log_question(row: dict) -> None:
    # A streaming insert: a load job per question would use up the daily load-job quota. The 5 s retry deadline
    # plus the 5 s request timeout cap this near 10 s; the default retry runs 600 s, past Cloud Run's 300 s timeout.
    errors = bq.insert_rows_json(QUESTIONS_TABLE, [row], retry=bigquery.DEFAULT_RETRY.with_timeout(5), timeout=5)
    # Row-level insertion errors are returned rather than raised; API and transport failures can still raise.
    if errors:
        raise RuntimeError(f"BigQuery rejected the question row: {errors}")


def search_pages(doc_id: str, query_vector: list[float], k: int) -> list[tuple[int, float]]:
    """Return up to k of the document's pages nearest the query vector, as (page, cosine similarity), best first."""
    parameters = [
        bigquery.ScalarQueryParameter("doc_id", "STRING", doc_id),
        bigquery.ArrayQueryParameter("query_vector", "FLOAT64", query_vector),
        bigquery.ScalarQueryParameter("k", "INT64", k),
    ]
    job = bq.query(SEARCH_QUERY, job_config=bigquery.QueryJobConfig(query_parameters=parameters))
    return [(row.page, row.similarity) for row in job.result()]
