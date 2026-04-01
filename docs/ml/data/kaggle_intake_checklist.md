# Kaggle and External Intake Checklist (Reranker Model)

Put one CSV at:

- docs/ml/data/kaggle_raw.csv

The all-in-one notebook splits train/dev/test automatically by query_id when split is missing.

## Fast source shortlist (start here)

Hugging Face legal datasets:

- https://huggingface.co/datasets/coastalcph/lex_glue
- https://huggingface.co/datasets/nguha/legalbench
- https://huggingface.co/datasets/theatticusproject/cuad
- https://huggingface.co/datasets/albertvillanova/legal_contracts

Kaggle legal datasets/search:

- https://www.kaggle.com/datasets?search=legal+qa
- https://www.kaggle.com/datasets/hrithikraj2537/indian-case-law-evaluation-corpus-iclec
- https://www.kaggle.com/datasets?search=contract+clause
- https://www.kaggle.com/datasets?search=case+law

## Exact queries to use when searching

- legal qa passage ranking
- legal retrieval relevance pairs
- contract clause question answer pairs
- case law question answering dataset
- legal ir benchmark

## Required fields after export

Your final CSV must map to:

- query (or question)
- candidate_text (or passage/text/chunk_text)
- label (0/1, or relevance score)

Optional but useful:

- query_id
- source
- case_id
- document_id
- chunk_id
- split (train/dev/test)

## Label mapping rule

- label=1 means candidate directly supports or answers the query
- label=0 means candidate is irrelevant, weak, or contradictory

If a source has graded relevance (for example 0 to 3), map values > 0 to 1.

## How to transform common source formats into reranker pairs

QA style data (question + answer):

1. Set query = question.
2. Set one correct answer as candidate_text with label=1.
3. Add 2 to 5 hard negatives as candidate_text with label=0.

Case law corpora (query not provided):

1. Build query from headnote/issue/title.
2. Use matching paragraph(s) from judgment as positive candidates.
3. Sample candidates from other cases or unrelated sections as negatives.

Clause datasets (contract with clause types):

1. Convert each clause-intent into a query sentence.
2. Matching clause text is label=1.
3. Clauses of other types are label=0.

## Quality gate before training

- every query_id has at least 1 positive and at least 1 negative
- remove exact duplicates for (query, candidate_text)
- keep one primary language per training run
- avoid candidates that are too short to carry legal meaning (for example less than 20 characters)

## Size guidance

- quick pipeline smoke test: 3,000 rows
- first useful model: 8,000 to 30,000 rows
- stronger model: 50,000+ rows

## After adding kaggle_raw.csv

Run:

- docs/ml/notebooks/01_reranker_all_in_one.ipynb

The notebook will:

1. normalize columns
2. validate quality
3. split by query_id
4. generate full prep figures and prep report
5. run baseline
6. train model
7. evaluate dev/test
8. save metrics, prepared data, figures, and model artifacts
