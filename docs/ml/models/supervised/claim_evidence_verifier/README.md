# Supervised Model Artifact

Task: `claim_evidence_verifier`

Classify whether an evidence snippet supports, contradicts, or is insufficient for a claim.

## Best Model

- Algorithm: `char_linear_svm`
- Accuracy: `1.0`
- Macro F1: `1.0`
- Weighted F1: `1.0`

## Files

- `model.joblib`: trained scikit-learn pipeline.
- `metrics.json`: full train/test metrics for every candidate algorithm.
- `predictions.csv`: held-out predictions for error analysis.

Re-run from the repository root:

```bash
.\.venv\Scripts\python.exe scripts\train_supervised_legal_models.py
```
