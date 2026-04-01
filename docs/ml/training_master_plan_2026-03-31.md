# Trainable Models Master Plan

Date: 2026-03-31
Mode: Colab-first, product-impact-first

## 1) Strategic Goal

Build trainable models that lawyers can feel in daily workflow, not only models that look good in a demo.

Primary value goals:
- improve evidence relevance
- reduce unsupported claims
- detect legal obligations and deadlines reliably
- surface contradictions across case documents

## 2) Scope and Priority

### Model A - Legal Retrieval Reranker

Purpose:
- rank evidence chunks better than generic pretrained reranker.

Expected product gain:
- better grounding quality in all AI responses.

Target metrics:
- nDCG@10
- MRR
- Recall@k

Integration target:
- `backend/services/ai/reranker_service.py`

### Model B - Claim-Evidence Verifier

Purpose:
- classify claim-snippet pair as `supported`, `contradicted`, or `insufficient`.

Expected product gain:
- stronger refusal behavior and safer answers.

Target metrics:
- contradiction recall
- refusal precision
- macro F1

Integration target:
- `backend/services/ai/agents/verifier_agent.py`

### Model C - Obligation + Deadline Extractor

Purpose:
- extract obligations, due dates, notice periods, and penalties from legal text.

Expected product gain:
- stronger timeline and practical next steps.

Target metrics:
- span F1 (entities)
- normalized date accuracy
- obligation completeness rate

Integration targets:
- `backend/services/ai/agents/timeline_agent.py`
- `backend/services/ai/agents/case_reasoning_agent.py`

### Model D - Cross-Document Contradiction Detector

Purpose:
- detect conflicts across documents (date, amount, clause, party obligations).

Expected product gain:
- earlier legal risk flagging in document comparison.

Target metrics:
- contradiction precision/recall/F1

Integration target:
- `backend/services/ai/agents/document_comparison_agent.py`

### Model E - Case Risk Stratification (Conditional)

Purpose:
- predict case risk level and risk category.

Condition to proceed:
- only if historical label quality is acceptable.

Target metrics:
- AUROC
- macro F1
- calibration error

Integration target:
- `backend/services/ai/agents/case_reasoning_agent.py`

## 3) Data Plan

## 3.1 Data Sources

- existing eval prompts and outcomes
- internal copilot chat logs (anonymized)
- document chunks and metadata
- consultation/intake fields
- document insights fields

## 3.2 Labeling Rules

- define labeling guideline before annotation
- double-label 10% sample for agreement
- measure inter-annotator agreement (Cohen kappa for classification tasks)
- resolve disagreements with one adjudication pass

## 3.3 Data Splits

- train: 70%
- validation: 15%
- test: 15%

Rules:
- split by case_id to avoid leakage
- keep hard examples in validation and test sets

## 4) Colab-First Delivery Framework

For each model, produce these artifacts:
- `metrics.json`
- `predictions.csv`
- `error_analysis.csv`
- `figure_main.png`
- `report.md`

Storage recommendation:
- save under Google Drive project folder and mirror final report files into this repo under `docs/ml/reports/`.

## 5) 8-Week Execution Timeline

## Week 1 - Foundation

Deliverables:
- finalized label guidelines
- dataset extraction scripts (or notebooks)
- baseline eval protocol for all models

Exit criteria:
- at least one clean dataset for Model A and Model B

## Week 2 - Model A (Reranker)

Deliverables:
- baseline reranker metrics
- trained reranker metrics
- integration dry-run in local pipeline
- Model A mini report updated

Exit criteria:
- measurable improvement over current reranker baseline

## Week 3 - Model B (Verifier)

Deliverables:
- claim-evidence dataset v1
- trained verifier model v1
- threshold policy for refusal
- Model B mini report updated

Exit criteria:
- contradiction recall above agreed threshold

## Week 4 - Model C (Obligation + Deadline)

Deliverables:
- annotated extraction dataset
- trained extraction model v1
- date normalization pipeline
- Model C mini report updated

Exit criteria:
- stable span F1 and date accuracy

## Week 5 - Model D (Contradiction Detector)

Deliverables:
- contradiction pair dataset
- trained contradiction model v1
- integration simulation for compare-doc agent
- Model D mini report updated

Exit criteria:
- useful contradiction precision and recall

## Week 6 - Integration and Product Validation

Deliverables:
- integrated A/B/C/D in backend logic (with safe fallback)
- before/after benchmark run
- latency impact analysis

Exit criteria:
- no critical regression in smoke + eval flows

## Week 7 - Model E Decision + Optional Build

If labels are strong:
- train Model E and report impact.

If labels are weak:
- skip training and document reason with transparent evidence.

## Week 8 - Reporting and Defense Packaging

Deliverables:
- all model mini reports finalized
- one summary matrix for final jury report
- charts and evidence pack ready for PDF

## 6) Quality Gates Per Model

Use this gate pattern:
1. Data quality gate: label consistency and leakage checks pass.
2. Metric gate: trained model beats baseline by agreed margin.
3. Product gate: at least 3 practical examples show user value.
4. Reliability gate: fallback behavior defined and tested.

## 7) Start Now - First 24 Hours

1. Set up Drive folder and one Colab notebook per model.
2. Build dataset extraction notebook for Model A and Model B.
3. Run baseline for Model A and save first metrics table.
4. Fill report files for Model A and B with initial baseline numbers.
5. Prepare annotation sheet template for Model C and D.

## 8) Final Report Merge Strategy

At project end, merge each model report into one chapter:
- problem and motivation
- model and data
- baseline vs trained results
- error analysis
- product impact
- limitations and next steps

This keeps your final report consistent, practical, and evidence-driven.
