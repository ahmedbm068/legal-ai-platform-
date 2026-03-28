# Project Audit vs PPT Vision

## Goal

Assess the current repository against the target product described in:

`Case-Centric Legal AI Platform with Multi-Agent Architecture and Trainable Models.pptx`

This audit is based on the repository state inspected on 2026-03-28.

## Executive Summary

The current repository is a solid backend-first prototype for a legal AI platform, but it is not yet the full application described in the presentation.

What already exists:

- Multi-tenant-aware data model for users, tenants, clients, cases, documents, chunks, and entities.
- Authentication and tenant-scoped API behavior.
- Document upload/storage pipeline with MinIO integration.
- Document processing pipeline with extraction, cleanup, PII redaction, chunking, NER, embeddings, and FAISS indexing.
- Hybrid retrieval approach combining lexical search and vector search.
- AI endpoints for document processing, search, question answering, summaries, and a case/document copilot.
- Early case-centric behavior inside `CopilotService`, especially for case summarization, deadline listing, risk listing, and document comparison.

What is still missing relative to the PPT:

- No frontend application.
- No true multi-agent orchestration framework.
- No verifier/proof-first gate that validates every answer before release.
- No trainable ML models wired into the platform.
- No voice intake / anti-spoof flow.
- No production-grade observability, CI/CD, or test suite.
- No legal source ingestion layer for statutes/case law beyond uploaded case documents.

Bottom line:

The repo currently represents **Stage 1.5 to Stage 2** of the PPT vision:

- Strong document intelligence foundation
- Partial case-centric intelligence
- Early grounded copilot
- Not yet a full case-centric multi-agent legal application

## What Already Matches the PPT

### 1. Core platform layer

The repository already includes the backbone of the core platform:

- FastAPI application entrypoint and router composition
- Tenant-aware authentication
- Case, client, user, tenant, and document persistence
- Role-aware foundations
- MinIO-based document storage

This aligns well with the PPT's platform model and core platform layer.

### 2. Document processing layer

This is currently the strongest part of the system.

Implemented capabilities include:

- File download from object storage
- Text extraction
- Text normalization
- PII redaction
- Semantic chunking
- Named entity extraction
- Chunk persistence
- Embedding generation
- FAISS indexing

This matches the PPT's "Document Processing Layer" quite closely.

### 3. Early intelligence layer

The intelligence layer is partially implemented:

- Document summaries
- Document entity retrieval
- Full document analysis endpoint
- Case-level summary synthesis
- Deadline extraction aggregation
- Legal risk aggregation
- Document comparison

This is a strong step toward case-centric reasoning, although the reasoning is still mostly service-based rather than agent-orchestrated.

### 4. RAG grounding

There is already an actual grounding strategy:

- Hybrid lexical + semantic retrieval
- Tenant/case/document scoped retrieval
- Source snippet return values
- Fallback behavior when confidence is low or no evidence is found

This is one of the most important parts of the future system and is already present in an early form.

## Main Gaps vs the PPT

### 1. No real application frontend

The PPT describes a platform. This repository currently exposes only backend APIs and architecture docs.

Missing:

- Lawyer-facing dashboard
- Case workspace UI
- Document review UI
- Copilot chat UI
- Source citation / traceability UI
- Human validation interface

Without a frontend, the repo is a backend prototype rather than the full app shown in the presentation.

### 2. Multi-agent architecture is conceptual, not implemented

The PPT explicitly describes:

- Document Analyzer
- Retrieval Agent
- Case Reasoning Agent
- Drafting Agent
- Verifier Agent
- LangGraph orchestration

Current state:

- `CopilotService` centralizes multiple responsibilities in one Python service.
- `RagService` handles retrieval and answer generation directly.
- No LangGraph or equivalent orchestration exists.
- No agent state graph, agent memory, or routing graph exists.

So the project currently has **agent-like responsibilities**, but not a true multi-agent system.

### 3. Proof-first verification is not yet enforced

The PPT emphasizes:

- No answer before evidence validation
- Contradiction checks
- Refusal when evidence is insufficient
- Explicit verification layer

Current state:

- The RAG layer returns sources and falls back when retrieval confidence is low.
- Prompts instruct the model not to invent facts.
- There is no dedicated verifier pass over generated claims.
- There is no structured contradiction detector.
- There is no mandatory claim-to-source validation pipeline.

This is a major gap because it is central to the academic positioning of the system.

### 4. Trainable ML layer is not implemented

The PPT promises:

- Caller intent classifier
- Voice anti-spoof model
- Case risk forecast model
- Retrieval re-ranker

Current repository status:

- Intent parsing exists, but it appears rule-based / prompt-driven rather than a trainable classifier.
- No anti-spoof pipeline exists.
- No predictive case risk model exists.
- No learned re-ranker exists; retrieval is weighted hybrid search only.

This is one of the biggest feature gaps between the current repo and the final vision.

### 5. External legal knowledge grounding is incomplete

The PPT references verified legal sources, statutes, and case law.

Current repository grounding is primarily based on:

- Uploaded case documents
- Stored chunk metadata

Missing:

- Statute ingestion pipeline
- Case law corpus ingestion
- Legal ontology / knowledge graph
- Cross-document authority hierarchy modeling

That means the system is currently best described as a **case document intelligence platform**, not yet a broader legal knowledge platform.

### 6. DevOps and validation maturity are still early

The PPT mentions:

- CI/CD
- high test coverage
- production monitoring
- operational stability

Current repository observations:

- No tests were found in the repo.
- No GitHub Actions workflow was found.
- No monitoring stack was found.
- No structured logging / telemetry layer was found.

This is expected for a prototype, but it is still an important gap.

## Technical Risks Found During Inspection

### 1. Runtime dependencies appear incomplete

Several imported packages are not listed in `requirements.txt`, including packages used directly by the codebase such as:

- `openai`
- `minio`
- `faiss`
- `numpy`
- `sentence_transformers`
- `pydantic-settings`

This means the backend may fail in a clean environment even if the code itself is logically correct.

### 2. Infrastructure config is only partially aligned with settings

`backend/core/config.py` requires:

- database
- redis
- minio
- openai

But `docker-compose.yml` currently defines only:

- PostgreSQL
- MinIO

Redis is referenced in config but not provisioned in compose.

### 3. The AI stack is instantiated eagerly

`DocumentAIPipeline()` creates `EmbeddingService()`, which creates `SentenceTransformer()` immediately.

This can create startup friction because:

- model download may happen at import/runtime
- app startup may become slow
- environments without ML dependencies may crash early

For a production-grade system, lazy initialization or service isolation would be safer.

### 4. FAISS metadata stores raw embeddings inside JSON

The vector store persists embeddings inside `faiss_metadata.json`.

This is acceptable for a prototype, but it will become problematic for scale because:

- metadata files grow very quickly
- index rebuild cost increases
- concurrent writes become risky

Eventually this should move to a more durable vector storage pattern or at least a proper metadata store.

## Current Maturity by PPT Layer

### Core Platform Layer

Status: **Partially complete**

Implemented:

- tenants
- users
- auth
- case model
- client model
- document model

Missing / immature:

- audit logs
- strong RBAC enforcement coverage
- case history timeline
- admin UX

### Document Processing Layer

Status: **Mostly complete for prototype level**

Implemented:

- extraction
- normalization
- redaction
- chunking
- NER
- embeddings
- indexing

Missing / immature:

- OCR robustness validation
- asynchronous processing jobs
- retry handling
- page-aware citations

### Intelligence Layer

Status: **Partially complete**

Implemented:

- summaries
- entities
- risks
- case aggregation

Missing / immature:

- obligation mapping
- contradiction detection
- timeline reasoning engine
- formal evidence graph

### Agentic AI Layer

Status: **Not yet implemented as described**

Implemented:

- centralized copilot service
- routing by parsed intent

Missing:

- orchestrated specialized agents
- shared agent state
- graph execution
- verifier agent

### Trainable ML Layer

Status: **Not implemented**

Implemented:

- none as trainable deployed models

Missing:

- intent classifier
- anti-spoof model
- outcome/risk model
- learned re-ranker

## Recommended Build Order

If the goal is to actually reach the PPT-quality application, this is the safest order:

### Phase 1. Stabilize the existing backend

- Fix dependency declarations.
- Align `.env`, config, and Docker services.
- Add tests for auth, cases, documents, search, and intelligence endpoints.
- Add structured logging and basic error monitoring.

### Phase 2. Complete the case-centric intelligence model

- Add structured case timeline generation.
- Add obligation extraction and obligation-to-party linking.
- Add contradiction detection across case documents.
- Store structured evidence objects instead of only free-text summaries.

### Phase 3. Implement proof-first verification

- Introduce a verifier step after retrieval and before final answer release.
- Require every generated claim to map to one or more evidence spans.
- Refuse answer generation when evidence is ambiguous or contradictory.
- Standardize citation output format.

### Phase 4. Introduce real multi-agent orchestration

- Split current services into explicit agent roles:
  - document analyzer
  - retrieval agent
  - case reasoner
  - drafting agent
  - verifier agent
- Add orchestration with LangGraph or an equivalent workflow engine.
- Persist agent state and trace execution steps for auditability.

### Phase 5. Build the frontend application

- Case dashboard
- Case workspace
- Document viewer with citations
- Copilot chat with evidence panel
- Human validation / approve-reject flows

### Phase 6. Add trainable ML modules

- Intent classifier
- Retrieval re-ranker
- Case risk scoring model
- Voice security only if voice interaction remains a real project requirement

## What the Project Should Be Called Right Now

Based on the current repository, the most accurate description today is:

**A backend-first, case-aware legal document intelligence platform with RAG-assisted copilot features.**

That description is strong and honest.

The PPT final description becomes accurate only after:

- real multi-agent orchestration
- proof-first verification
- trainable ML integration
- production-grade UI and validation workflows

## Recommended Next Deliverable

The best next milestone is:

**Case Workspace v1**

Scope:

- one frontend app
- one case page
- document list
- document summary panel
- case summary panel
- copilot chat
- source citation side panel

Why this milestone first:

- It turns the backend into a real app.
- It makes the case-centric value visible immediately.
- It creates the right UI surface for later verifier and multi-agent features.

## Final Assessment

You already built the hardest foundation:

- multi-tenant backend structure
- document intelligence pipeline
- hybrid retrieval
- early case-level synthesis

That is real progress.

The main thing missing is not "basic coding"; it is the transition from **prototype services** to **product architecture**:

- frontend experience
- verifier-first trust layer
- agent orchestration
- trainable ML modules

So the project is on the right track, but the presentation currently describes the **target system**, not the **fully implemented repo**.
