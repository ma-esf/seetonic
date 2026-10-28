"""Every setting, read from the environment with a default.

deploy.sh and setup.sh repeat these defaults: change them there too.
"""

import os

PROJECT = os.environ.get("GOOGLE_CLOUD_PROJECT", "seetonic-demo")
LOCATION = os.environ.get("GOOGLE_CLOUD_LOCATION", "global")
EMBEDDING_MODEL = os.environ.get("EMBEDDING_MODEL", "gemini-embedding-2")
FLASH_MODEL = os.environ.get("FLASH_MODEL", "gemini-3.8-flash")
DPI = int(os.environ.get("DPI", "144"))
TOP_K = int(os.environ.get("TOP_K", "3"))
EMBEDDING_SIZE = int(os.environ.get("EMBEDDING_SIZE", "768"))
# Model calls use global, which a bucket or a dataset rejects as a location.
DATA_LOCATION = os.environ.get("DATA_LOCATION", "europe-north1")
BUCKET = os.environ.get("BUCKET", f"{PROJECT}-files")
DATASET = os.environ.get("DATASET", "seetonic")
QUESTIONS_TABLE = os.environ.get("QUESTIONS_TABLE", "questions")
MAX_PAGES = int(os.environ.get("MAX_PAGES", "50"))
