# Model Report - Legal Retrieval Reranker

Model ID: A
Status: Not Started
Priority: High

## 1) Problem and User Value

Problem:
- current ranking can surface less relevant chunks, reducing answer quality.

User value:
- better evidence quality for every copilot answer.

## 2) Task Definition

Input:
- query + candidate chunks

Output:
- relevance score per chunk

Primary metrics:
- nDCG@10
- MRR
- Recall@5/10

## 3) Data Plan

Sources:
- eval prompts
- case documents and chunks
- hard negatives from nearby but irrelevant chunks

## 4) Baseline vs Trained

| Metric | Baseline | Trained | Delta |
|---|---:|---:|---:|
| nDCG@10 |  |  |  |
| MRR |  |  |  |
| Recall@10 |  |  |  |

## 5) Error Analysis

- misses on long legal clauses:
- confusion between similar obligations:
- multilingual query drift:

## 6) Integration Plan

Target file:
- `backend/services/ai/reranker_service.py`

Rollout:
1. shadow mode
2. A/B style comparison
3. full switch if metrics hold

## 7) Decision

Current decision:
- Pending

## 8) Final Report Snippet

To be written after first successful run.
