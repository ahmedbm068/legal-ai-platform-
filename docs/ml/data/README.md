# Reranker Data You Need To Bring

For model 1 (legal retrieval reranker), you can bring one file in either format:

- `docs/ml/data/reranker_pairs.csv`
- `docs/ml/data/kaggle_raw.csv`

The all-in-one notebook can auto-detect common column names and auto-create train/dev/test splits.

## Required columns

- `query` (or `question`)
- `candidate_text` (or `passage`, `chunk_text`, `text`)
- `label` (`1` relevant, `0` not relevant; non-binary relevance will be mapped to binary)

## Optional columns

- `query_id` (if missing, it is auto-generated from query text)
- `split` (`train`, `dev`, `test`; if missing, the notebook auto-splits by `query_id`)
- `source`
- `case_id`
- `document_id`
- `chunk_id`

## Data quality rules

- Each `query_id` should have at least one positive and one negative row.
- Keep positives and negatives hard (similar wording, different meaning).
- Avoid duplicate rows for the same query and candidate.

## Recommended dataset size

- Quick start: 150 to 250 unique queries
- Better first run: 300 to 800 train queries, 80 to 150 dev, 80 to 150 test
- Strong run: 8,000 to 30,000 total rows

Use this template as the reference schema:

- `docs/ml/data/reranker_pairs_template.csv`

If you plan to download from Kaggle first, use this checklist:

- `docs/ml/data/kaggle_intake_checklist.md`
