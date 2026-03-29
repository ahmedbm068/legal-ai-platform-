# Harvey Outperformance Plan

Date: 2026-03-29

## 1) Goal

Build a legal AI platform that can outperform Harvey for our target segment by focusing on:
- stronger trust and explainability
- lower cost per matter
- localized legal workflows
- faster practical deployment in small and mid-size firms

This plan is execution-focused and aligned with the current codebase.

## 2) Agreed Model Stack (Current Decisions)

Based on current runtime configuration:

- Primary reasoning/chat model: `meta-llama/llama-3.3-70b-instruct:free`
- Summary model: `meta-llama/llama-3.3-70b-instruct:free`
- LLM provider route: OpenRouter-compatible via `LLM_BASE_URL=https://openrouter.ai/api/v1`
- Local transcription model: `openai/whisper-tiny`
- Local transcription mode: enabled (`TRANSCRIPTION_REMOTE_ENABLED=false`)
- Retrieval reranker model: `cross-encoder/ms-marco-MiniLM-L-6-v2`

Planned model policy upgrade:
- add task-level routing (not one global model for all tasks)
- keep Llama for reasoning/drafting
- allow optional stronger model for verifier on high-risk outputs
- keep local Whisper fallback for reliability

## 3) What We Will Add (Outperformance Scope)

### A. Trust Layer (Primary Differentiator)

- claim-to-evidence mapping for every legal answer
- page/section-aware citations (not chunk-only)
- explicit refusal when evidence is weak or contradictory
- answer confidence and trace shown in UI
- immutable audit trail for generated outputs

### B. Retrieval and Knowledge Layer

- upgrade retrieval from generic chunk search to legal-aware retrieval
- improve ranking features (recency, source authority, statute/case-law type)
- legal source packs by jurisdiction (start with target jurisdictions)
- external web legal search pipeline (SerpAPI/Tavily) with strict filtering and citations

### C. Multi-Model and Reliability Layer

- model router by task (`retrieval`, `reasoning`, `drafting`, `verification`, `transcription`)
- automatic fallback policies and retry matrix
- latency and cost telemetry per request and per task

### D. Product and Workflow Layer

- workflow packs by legal use case:
  - intake triage
  - deadline extraction
  - contradiction check
  - client-ready drafting
- stronger lawyer UX for evidence review and export
- enterprise controls roadmap (retention, activity logs, role policy expansions)

## 4) External Search Add-On (SerpAPI/Tavily -> Llama)

## Objective

Let lawyers run external legal web search, then synthesize a grounded answer through the Llama API.

## Proposed Architecture

1. User query (optionally case-scoped)  
2. Query rewriting for legal intent  
3. Search provider call:
- Provider A: SerpAPI
- Provider B: Tavily
4. URL filtering:
- trusted legal domains first
- language/jurisdiction filters
- deduplicate results
5. Content fetch + extraction:
- fetch top N pages
- clean text
- keep source metadata (`title`, `url`, `snippet`, `retrieved_at`)
6. Merge with internal retrieval context (optional hybrid mode)  
7. Llama answer generation with strict grounding prompt  
8. Verifier pass  
9. Return answer + source list + confidence + fallback reason

## API Proposal

- New endpoint: `POST /ai/web-ask`
- Request body:
  - `question: str`
  - `provider: "tavily" | "serpapi" | "auto"`
  - `case_id: int | null`
  - `use_internal_docs: bool` (default `true`)
  - `top_k_web: int` (default `5`)
- Response body:
  - `answer`
  - `confidence`
  - `sources` (web + internal)
  - `used_fallback`
  - `fallback_reason`

## Configuration to Add

- `WEB_SEARCH_ENABLED=true`
- `WEB_SEARCH_PROVIDER=auto`
- `SERPAPI_API_KEY=`
- `TAVILY_API_KEY=`
- `WEB_SEARCH_TOP_K=5`
- `WEB_SEARCH_ALLOWED_DOMAINS=` (comma-separated)
- `WEB_SEARCH_TIMEOUT_SECONDS=`

## Security and Legal Guardrails

- do not treat external web text as verified legal advice
- visibly separate "external web sources" vs "internal case evidence"
- require citations for externally grounded claims
- block known low-trust domains by policy
- log source URLs and retrieval timestamps for auditability

## 5) Delivery Plan (Execution)

### Phase 1 (Week 1-2): Evaluation and Safety Baseline

- build eval set for legal Q/A and drafting
- add quality metrics dashboard (groundedness, citation precision, refusal precision)
- add latency and cost metrics

Definition of done:
- repeatable benchmark run with tracked baseline

### Phase 2 (Week 3-4): External Search and Grounding

- implement web search provider abstraction (`SerpAPI`, `Tavily`)
- add `/ai/web-ask` endpoint
- add prompt template for web-grounded legal answering
- return normalized citations and source cards in UI

Definition of done:
- lawyer can ask a question and receive cited answer from trusted external sources

### Phase 3 (Week 5-6): Trust Layer Hardening

- claim-to-evidence map
- contradiction checks
- refusal policy improvements
- audit/event log schema and persistence

Definition of done:
- each answer has auditable trace and clear confidence behavior

### Phase 4 (Week 7-8): Product Moat and Scale

- localized legal workflow templates
- improved role permissions and admin controls
- export package (answer + citations + trace)

Definition of done:
- complete end-to-end lawyer workflow with explainable outputs

## 6) Success Metrics

- grounded answer pass rate >= 90%
- citation precision >= 85%
- unsafe/ungrounded answer rate <= 5%
- p95 response latency <= 8s for standard questions
- cost per resolved lawyer query reduced vs current baseline

## 7) Immediate Build Backlog (Next Coding Tasks)

1. Create `web_search_service.py` with provider interface and two adapters (Tavily, SerpAPI).
2. Add `POST /ai/web-ask` route and schema.
3. Add settings/env entries for web search provider keys and controls.
4. Add source normalization and dedup utilities.
5. Add verifier integration for web-based responses.
6. Add frontend panel/toggle for "Internal + Web" vs "Internal only".
7. Add evaluation script for web-grounded QA.

## 8) Strategic Positioning

We do not need to beat Harvey everywhere.  
We win by being:
- more transparent in legal grounding
- cheaper to deploy and operate
- faster to adapt to local legal workflows
- more practical for day-to-day legal operations in our target market
