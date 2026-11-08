"""Every setting, read from the environment with a default, except the two embedding settings, which are fixed here.

deploy.sh repeats the environment defaults, setup.sh repeats the project and storage ones, and scripts/evaluate.py
repeats TOP_K: change them there too.
"""

import os

PROJECT = os.environ.get("GOOGLE_CLOUD_PROJECT", "seetonic-demo")
# The eu endpoint keeps Gemini calls inside the EU.
LOCATION = os.environ.get("GOOGLE_CLOUD_LOCATION", "eu")
# Not read from the environment: stored page vectors only compare with question vectors from the same model and
# size, so changing either means uploading every document again.
EMBEDDING_MODEL = "gemini-embedding-2"
EMBEDDING_SIZE = 768
FLASH_MODEL = os.environ.get("FLASH_MODEL", "gemini-3.8-flash")
JEV_MODEL = os.environ.get("JEV_MODEL", "jev-1.13.0")
# Cloud Run reads it from Secret Manager; empty is enough for the tests.
TYPESAFE_API_KEY = os.environ.get("TYPESAFE_API_KEY", "")
# Page PNGs keep the DPI they were uploaded at: changing it misplaces highlights on documents already uploaded.
DPI = int(os.environ.get("DPI", "144"))
TOP_K = int(os.environ.get("TOP_K", "3"))
# Region of the bucket and the BigQuery dataset. Gemini calls use LOCATION, a multi-region endpoint.
DATA_LOCATION = os.environ.get("DATA_LOCATION", "europe-north1")
BUCKET = os.environ.get("BUCKET", f"{PROJECT}-files")
DATASET = os.environ.get("DATASET", "seetonic")
QUESTIONS_TABLE = os.environ.get("QUESTIONS_TABLE", "questions")
MAX_PAGES = int(os.environ.get("MAX_PAGES", "50"))
