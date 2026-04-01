# ML Model Workstream

This folder is the execution center for trainable model work.

Objective:
- Build useful legal AI models that improve real product behavior.
- Produce clear, reproducible evidence for final jury report.
- Keep a short model report per model, then merge all reports into the final project report.

## Contents

- `training_master_plan_2026-03-31.md`: end-to-end plan, timeline, milestones.
- `colab_runbook.md`: Colab-first workflow and artifact export rules.
- `notebooks/01_reranker_all_in_one.ipynb`: single local notebook for data prep, split, validation, train, and test.
- `model_report_template.md`: base template for any new model.
- `reports/01_retrieval_reranker_report.md`
- `reports/02_claim_evidence_verifier_report.md`
- `reports/03_obligation_deadline_extractor_report.md`
- `reports/04_contradiction_detector_report.md`
- `reports/05_case_risk_stratification_report.md`

## Model Priority

1. Retrieval reranker (highest immediate product impact)
2. Claim-evidence verifier (trust and safety)
3. Obligation + deadline extractor (actionable legal workflow)
4. Contradiction detector (cross-document risk detection)
5. Case risk stratification (only with strong labels)

## Minimum Evidence Per Model

Each model report must include:
- baseline metric vs trained metric
- 3 qualitative examples (good, bad, edge case)
- practical product impact statement
- known limitations and fallback behavior

## Local Notebook Mode

If you want to run locally instead of Colab, start with:

- `docs/ml/notebooks/01_reranker_all_in_one.ipynb`

Input file location:

- `docs/ml/data/reranker_pairs.csv` or `docs/ml/data/kaggle_raw.csv`

## Final Report Packaging Rule

At final stage, each report contributes:
- one result table
- one key chart (confusion matrix, ranking metric plot, or PR curve)
- one short business impact paragraph
- one reliability paragraph
