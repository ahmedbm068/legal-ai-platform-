# Supervised Model Artifact

Task: `document_type_classifier`

Predict legal document type from document text.

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
