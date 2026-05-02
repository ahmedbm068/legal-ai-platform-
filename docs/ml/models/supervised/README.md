# Supervised Legal Models Summary

These artifacts are trained from local labeled CSV files with classical ML models.

| Task | Best algorithm | Accuracy | Macro F1 | Rows |
|---|---:|---:|---:|---:|
| document_type_classifier | char_linear_svm | 1.0 | 1.0 | 30 |
| claim_evidence_verifier | char_linear_svm | 1.0 | 1.0 | 30 |
| case_risk_triage | multinomial_nb | 0.8333 | 0.8222 | 30 |

Artifacts are intentionally small so they can be retrained quickly during demos or class discussion.
