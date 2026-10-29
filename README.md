# Seetonic

Ask a PDF a question and see the evidence highlighted on the page.

## Evaluation

Measured on 2026-10-29 against a local server, with `gemini-embedding-2` for the page and question embeddings and
`gemini-3.8-flash` for the answers. To measure again, start a server and run
`uv run python scripts/evaluate.py http://localhost:8080`. The script asks again when `/ask` answers 502, so an
answer that failed the citation format is not counted.

| Questions | hit@3 | MRR@3 | Verification rate |
|---|---|---|---|
| All (20) | 0.90 | 0.85 | 0.97 (31 of 32) |
| APPLE_Statements.pdf (5) | 1.00 | 0.90 | 0.90 (9 of 10) |
| APPLE_10Q_Q3_2026.pdf (15) | 0.87 | 0.83 | 1.00 (22 of 22) |

- **hit@3:** the share of questions whose labeled page is among the 3 pages `/ask` retrieves.
- **MRR@3:** the mean of 1 / rank of the labeled page, counting 0 when it is not in the top 3. `/ask` returns only
  3 pages, so this is MRR@3, not MRR.
- **Verification rate:** verified citations over all citations. Verified means the code found the quote on the cited
  page. It does not mean the answer is right, and an answer with no citation does not count against it.
- **Labeled set:** 20 question-to-page pairs in `eval/questions.jsonl`, on `eval/pdfs/APPLE_Statements.pdf`
  (3 pages) and `eval/pdfs/APPLE_10Q_Q3_2026.pdf` (32 pages). 7 pairs were written by hand. 13 were drafted by an LLM
  from the 10-Q's page text and checked by the author line by line. The drafting model is not the Gemini model that
  answers.
- **Statements PDF:** it has 3 pages and `/ask` returns 3, so its hit@3 is always 1.00. The 10-Q row is the
  retrieval measure.

Both misses are on the 10-Q. The capital expenditures question (page 8, the cash flow statement) got pages 9, 21
and 20, and the model gave no citation. The corporate bonds question (page 10, the June 2026 table) got pages 11, 12
and 13. Page 11 holds the same table for September 2025, and the model quoted it: 3 verified citations for the
wrong period.
