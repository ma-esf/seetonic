"""Every setting, read from the environment with a default."""

import os

PROJECT = os.environ.get("GOOGLE_CLOUD_PROJECT", "seetonic-demo")
LOCATION = os.environ.get("GOOGLE_CLOUD_LOCATION", "global")
EMBEDDING_MODEL = os.environ.get("EMBEDDING_MODEL", "gemini-embedding-2")
FLASH_MODEL = os.environ.get("FLASH_MODEL", "gemini-3.8-flash")
DPI = int(os.environ.get("DPI", "144"))
TOP_K = int(os.environ.get("TOP_K", "3"))
EMBEDDING_SIZE = int(os.environ.get("EMBEDDING_SIZE", "768"))
