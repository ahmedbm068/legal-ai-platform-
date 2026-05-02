# Supervised Legal Models Runbook

This track adds trainable non-LLM models to the project so the ML part is visible, reproducible, and defensible.

## What It Trains

The trainer builds three small supervised classifiers:

| Model | Input | Output | Why it matters |
|---|---|---|---|
| Document type classifier | Legal document text | `contract`, `invoice`, `legal_letter`, `court_judgment`, `complaint`, `case_memo` | Shows classic text classification with TF-IDF features. |
| Claim-evidence verifier | Claim + evidence snippet | `supported`, `contradicted`, `insufficient` | Shows supervised safety checking beyond prompting. |
| Case risk triage | Case summary | `low`, `medium`, `high` | Shows business-facing prediction from labeled examples. |

Each task compares:

- Multinomial Naive Bayes
- Logistic Regression
- Linear SVM
- Character n-gram Linear SVM

The verifier and risk models also add small hand-built cue features before TF-IDF. This is useful for class discussion because it shows that ML performance depends on representation, not only on the algorithm. The best model is selected by macro F1, then saved as a scikit-learn pipeline.

## Train Locally

From the repository root:

```bash
.\.venv\Scripts\python.exe scripts\train_supervised_legal_models.py
```

Outputs are written to:

```text
docs/ml/models/supervised/
```

Each model folder contains:

- `model.joblib`: trained model artifact
- `metrics.json`: accuracy, macro F1, weighted F1, classification report, confusion matrix
- `predictions.csv`: held-out predictions for error analysis
- `README.md`: short artifact summary

## Run A Prediction

After training, try a saved model:

```bash
.\.venv\Scripts\python.exe scripts\predict_supervised_legal_model.py --model case_risk_triage --text "Urgent hearing tomorrow with missing evidence and unpaid damages."
```

Claim-evidence verifier example:

```bash
.\.venv\Scripts\python.exe scripts\predict_supervised_legal_model.py --model claim_evidence_verifier --claim "The invoice was fully paid." --evidence "The invoice shows outstanding balance due and no payment received."
```

## Add Your Own Data

Replace or extend the seed CSV files:

- `docs/ml/data/supervised/document_type_examples.csv`
- `docs/ml/data/supervised/claim_evidence_examples.csv`
- `docs/ml/data/supervised/case_risk_examples.csv`

Keep the same columns. Add at least 10 to 20 examples per class before presenting final metrics.

## How To Explain It

This is not an LLM fine-tune. It is a classical supervised ML layer:

1. Labeled legal examples are stored in CSV files.
2. Text is converted into TF-IDF numerical features.
3. Several algorithms are trained and compared on a held-out test split.
4. The best model is saved and can be reused by the backend.
5. Metrics and prediction files provide evidence for the report.

For the jury, position this as the "models we can train ourselves" layer that complements the LLM agents:

- LLMs handle reasoning, drafting, and natural language interaction.
- Supervised models handle narrow repeatable predictions with measurable metrics.
- Retrieval models handle grounding and evidence ranking.

## Next Upgrade

After the seed demo works, improve it with:

- real anonymized cases and documents
- double-labeling on a sample of examples
- leakage checks by `case_id`
- class balance reporting
- confidence thresholds before product enforcement
