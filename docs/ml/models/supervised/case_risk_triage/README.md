# Supervised Model Artifact

Task: `case_risk_triage`

Predict low, medium, or high legal case risk from case facts.

## Best Model

- Algorithm: `multinomial_nb`
- Accuracy: `0.8333`
- Macro F1: `0.8222`
- Weighted F1: `0.8222`

## Files

- `model.joblib`: trained scikit-learn pipeline.
- `metrics.json`: full train/test metrics for every candidate algorithm.
- `predictions.csv`: held-out predictions for error analysis.

Re-run from the repository root:

```bash
.\.venv\Scripts\python.exe scripts\train_supervised_legal_models.py
```
