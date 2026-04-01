# Model Report - Obligation and Deadline Extractor

Model ID: C
Status: Not Started
Priority: High

## 1) Problem and User Value

Problem:
- legal operations need obligations and deadlines, not only summaries.

User value:
- practical next steps, deadline monitoring, breach prevention.

## 2) Task Definition

Input:
- legal text segments

Output:
- obligation spans
- deadline/date spans
- notice period spans
- optional penalty spans

Primary metrics:
- span F1
- normalized date accuracy
- obligation completeness rate

## 3) Data Plan

Sources:
- contracts, letters, notices from case docs
- manual span annotations

Label schema:
- OBLIGATION
- DEADLINE
- NOTICE_PERIOD
- PENALTY

## 4) Baseline vs Trained

| Metric | Baseline | Trained | Delta |
|---|---:|---:|---:|
| Span F1 |  |  |  |
| Date Accuracy |  |  |  |
| Completeness |  |  |  |

## 5) Error Analysis

- implicit deadline language:
- nested clauses with multiple obligations:
- ambiguous temporal references:

## 6) Integration Plan

Target files:
- `backend/services/ai/agents/timeline_agent.py`
- `backend/services/ai/agents/case_reasoning_agent.py`

Rollout:
1. assistive extraction only
2. merged with timeline output
3. surfaced in practical next steps

## 7) Decision

Current decision:
- Pending

## 8) Final Report Snippet

To be written after first successful run.
