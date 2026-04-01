# Colab Runbook for Trainable Models

## 1) Notebook Setup Standard

At top of each notebook:
- set random seeds
- print environment details (python version, torch version, GPU info)
- define artifact output path in Google Drive

Recommended sections:
1. Config
2. Data load
3. Baseline
4. Training
5. Evaluation
6. Error analysis
7. Export artifacts

## 2) Reproducibility Rules

- lock random seed for all training runs
- save train/val/test split indexes
- version dataset with date stamp
- store model config and hyperparameters in JSON

## 3) Required Export Artifacts

For each run, export:
- `run_config.json`
- `metrics.json`
- `predictions.csv`
- `errors_top_cases.csv`
- `figure_main.png`

Optional:
- confusion matrix image
- PR curve image
- calibration plot image

## 4) Report Snippet Generation

At notebook end, auto-generate a markdown snippet that can be pasted into model report file:
- baseline metrics
- trained metrics
- delta summary
- 3 failure examples

## 5) Naming Convention

Use:
- `model_name_dataset_version_run_id`

Examples:
- `reranker_v1_2026-04-01_run01`
- `verifier_v1_2026-04-03_run02`

## 6) Practical Colab Tips

- use small pilot subsets first to validate pipeline
- only run full training after metrics and logging are confirmed
- save checkpoints every epoch (or every fixed step)
- keep one `best.pt` and one `last.pt`

## 7) Export Back to Repo

After each successful run:
1. update corresponding file in `docs/ml/reports/`
2. add metric table and one chart
3. add short interpretation paragraph
4. list integration decision (go/no-go)
