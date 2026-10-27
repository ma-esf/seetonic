"""Print a document's top pages for a question: page number and cosine similarity, best first.

Usage:
  python scripts/search.py <doc_id> "<question>"
"""

import sys

from app import config, gemini, store

if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    doc_id, question = sys.argv[1], sys.argv[2]
    results = store.search_pages(doc_id, gemini.embed_text(question), config.TOP_K)
    if not results:
        sys.exit(f"No pages stored for doc_id {doc_id}.")
    for page, similarity in results:
        print(f"{page} {similarity:.2f}")
