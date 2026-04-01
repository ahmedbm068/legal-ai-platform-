# Model Report - Claim-Evidence Verifier

Model ID: B
Status: Not Started
Priority: High

## 1) Problem and User Value

Problem:
- answer-level checks can miss unsupported individual claims.

User value:
- safer legal outputs, clearer refusal when evidence is weak.

## 2) Task Definition

Input:
- claim text + evidence snippet

Output classes:
- supported
- contradicted
- insufficient

Primary metrics:
- contradiction recall
- refusal precision
- macro F1

## 3) Data Plan

Sources:
- generated claims from assistant outputs
- evidence snippets from retrieval
- manual label pass for tri-class supervision

## 4) Baseline vs Trained

| Metric | Baseline | Trained | Delta |
|---|---:|---:|---:|
| Macro F1 |  |  |  |
| Contradiction Recall |  |  |  |
| Refusal Precision |  |  |  |

## 5) Error Analysis

- false support on vague claims:
- false contradiction with partial overlap:
- insufficient vs contradicted confusion:

## 6) Integration Plan

Target file:
- `backend/services/ai/agents/verifier_agent.py`

Rollout:
1. log-only mode
2. threshold tuning
3. enforce policy in production responses

## 7) Decision

Current decision:
- Pending

## 8) Final Report Snippet

To be written after first successful run.
