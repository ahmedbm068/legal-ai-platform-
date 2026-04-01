# Bring This Data Now (Model 1 Starter)

Bring one CSV file named either:

- `docs/ml/data/reranker_pairs.csv`
- `docs/ml/data/kaggle_raw.csv`

## Minimum required columns

- `query` (or `question`)
- `candidate_text` (or `passage`, `chunk_text`, `text`)
- `label` (0 or 1)

## Optional columns

- `query_id`
- `split` (`train`, `dev`, `test`)
- `source`
- `case_id`
- `document_id`
- `chunk_id`

If `query_id` is missing, it will be generated automatically.
If `split` is missing, the notebook will create train/dev/test by `query_id`.

## Minimum usable amount (quick start)

- At least `150` unique queries total
- At least `1` positive and `1` negative per query
- Recommended rows: `3000+`

## Better first run target

- `300 to 800` unique train queries
- `80 to 150` unique dev queries
- `80 to 150` unique test queries
- Recommended rows: `8000 to 30000`

## Recommended download order (practical)

1. https://huggingface.co/datasets/coastalcph/lex_glue
2. https://huggingface.co/datasets/nguha/legalbench
3. https://www.kaggle.com/datasets/hrithikraj2537/indian-case-law-evaluation-corpus-iclec
4. https://www.kaggle.com/datasets?search=legal+qa

Start with one source, convert to the required columns, run the notebook once, then add the second source.

## Labeling rules

- `label=1`: passage directly supports or answers the query
- `label=0`: passage is irrelevant, contradictory, or generic/noisy
