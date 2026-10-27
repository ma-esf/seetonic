import mimetypes

from google.cloud import bigquery, storage

from app import config

bucket = storage.Client(project=config.PROJECT).bucket(config.BUCKET)
bq = bigquery.Client(project=config.PROJECT, location=config.DATA_LOCATION)
PAGES_TABLE = f"{config.PROJECT}.{config.DATASET}.pages"

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
    # Without a content type the client stores text/plain, and a browser would show a PNG as text.
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


def search_pages(doc_id: str, query_vector: list[float], k: int) -> list[tuple[int, float]]:
    """Return up to k of the document's pages nearest the query vector, as (page, cosine similarity), best first."""
    parameters = [
        bigquery.ScalarQueryParameter("doc_id", "STRING", doc_id),
        bigquery.ArrayQueryParameter("query_vector", "FLOAT64", query_vector),
        bigquery.ScalarQueryParameter("k", "INT64", k),
    ]
    job = bq.query(SEARCH_QUERY, job_config=bigquery.QueryJobConfig(query_parameters=parameters))
    return [(row.page, row.similarity) for row in job.result()]
