# Model Report - Cross-Document Contradiction Detector

Model ID: D
Status: Not Started
Priority: Medium-High

## 1) Problem and User Value

Problem:
- case documents can conflict on dates, amounts, obligations, and facts.

User value:
- earlier detection of legal risk and inconsistency.

## 2) Task Definition

Input:
- pair of evidence statements (or grouped case facts)

Output classes:
- contradiction
- neutral
- support

Primary metrics:
- contradiction precision
- contradiction recall
- macro F1

## 3) Data Plan

Sources:
- document pair mining from same case
- manually labeled contradiction pairs
- synthetic hard negatives from similar statements

## 4) Baseline vs Trained

| Metric | Baseline | Trained | Delta |
|---|---:|---:|---:|
| Macro F1 |  |  |  |
| Contradiction Precision |  |  |  |
| Contradiction Recall |  |  |  |

## 5) Error Analysis

- false contradictions on context shift:
- missed contradictions with numerical formats:
- clause-level contradiction not captured at sentence level:

## 6) Integration Plan

Target file:
- `backend/services/ai/agents/document_comparison_agent.py`

Rollout:
1. warning-only mode
2. threshold tuning with legal review
3. integrated contradiction section in comparison output

## 7) Decision

Current decision:
- Pending

## 8) Final Report Snippet

To be written after first successful run.
