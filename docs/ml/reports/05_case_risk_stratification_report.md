# Model Report - Case Risk Stratification

Model ID: E
Status: Not Started
Priority: Conditional

## 1) Problem and User Value

Problem:
- teams need triage and prioritization across multiple active cases.

User value:
- better focus on high-risk matters and faster intervention.

## 2) Task Definition

Input:
- structured case signals (document traits, extracted risks, timeline stress signals, consultation urgency)

Output:
- risk level (low/medium/high)
- risk category labels

Primary metrics:
- AUROC
- macro F1
- calibration error

## 3) Data Plan

Proceed only if:
- historical labels are available and reliable.

If labels are weak:
- mark as deferred and document rationale.

## 4) Baseline vs Trained

| Metric | Baseline | Trained | Delta |
|---|---:|---:|---:|
| AUROC |  |  |  |
| Macro F1 |  |  |  |
| Calibration Error |  |  |  |

## 5) Error Analysis

- overconfidence on sparse cases:
- class imbalance drift:
- weak label consistency:

## 6) Integration Plan

Target file:
- `backend/services/ai/agents/case_reasoning_agent.py`

Rollout:
1. internal score only
2. human-reviewed recommendations
3. optional client-facing risk band

## 7) Decision

Current decision:
- Pending (data quality gate required)

## 8) Final Report Snippet

To be written after first successful run.
