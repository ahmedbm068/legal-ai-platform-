# Reranker Data Preparation Report

Generated UTC: 2026-03-31T20:13:12.207233+00:00
Data file: C:\Users\ahmed\Desktop\pfe.2\legal-ai-platform\docs\ml\data\reranker_pairs.csv

## Core Stats
- rows_total: 12
- queries_total: 4
- positive_rate_overall: 0.333333
- avg_candidates_per_query: 3.0
- avg_positives_per_query: 1.0
- duplicate_query_candidate: 0
- duplicate_query_id_candidate: 0
- duplicate_full_rows: 0

## Split Summary
```
split  rows  queries  positives  negatives  positive_rate
  dev     3        1          1          2         0.3333
 test     3        1          1          2         0.3333
train     6        2          2          4         0.3333
```

## Missing/Empty Key Fields
```
        column  missing_or_empty_rows
      query_id                      0
         query                      0
candidate_text                      0
         label                      0
         split                      0
        source                      0
```

## Figures
- docs/ml/outputs/figures/prep_01_rows_per_split.png
- docs/ml/outputs/figures/prep_02_label_distribution.png
- docs/ml/outputs/figures/prep_03_positive_rate_per_split.png
- docs/ml/outputs/figures/prep_04_query_length_words.png
- docs/ml/outputs/figures/prep_05_candidate_length_words.png
- docs/ml/outputs/figures/prep_06_candidates_per_query.png
- docs/ml/outputs/figures/prep_07_positives_per_query.png
- docs/ml/outputs/figures/prep_08_top_sources.png
- docs/ml/outputs/figures/prep_09_missing_values.png
- docs/ml/outputs/figures/prep_10_duplicate_diagnostics.png
- docs/ml/outputs/figures/prep_11_split_label_composition.png
