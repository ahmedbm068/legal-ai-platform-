# Project So Far - Legal AI Platform

Generated: 2026-04-06

## 1) Executive Snapshot

Legal AI Platform is currently a full-stack legal workflow system with:
- A FastAPI backend for legal case operations, AI orchestration, retrieval, voice, and public intake.
- An internal staff workspace frontend (lawyers, admins, assistants).
- A separate client portal frontend for public intake and status checks.
- Infrastructure services for PostgreSQL, Redis, and MinIO.

The codebase has moved beyond prototype stage. It now supports end-to-end legal workflows including case management, document intelligence, grounded copilot interactions, voice intake, and consultation pipelines.

## 2) Repository Layout

Top-level areas:
- `backend/`: API, core business logic, AI services, database models.
- `frontend/`: Internal legal workspace (React + TypeScript + Vite).
- `client-portal/`: Public client intake portal (React + TypeScript + Vite).
- `docs/`: Audits, plans, reports, architecture notes, ML artifacts.
- `scripts/`: Smoke tests, evaluation harness, regression checks, reporting utilities.
- `advancement/`: Generated progress logs and reports (evals and feedback).

## 3) Technology Stack

Backend:
- Python 3 ecosystem with FastAPI and Uvicorn.
- SQLAlchemy ORM + PostgreSQL.
- Redis integration for runtime support.
- MinIO object storage.
- AI dependencies include OpenAI SDK, sentence-transformers, FAISS CPU, NumPy, PyPDF.

Frontend:
- React 18 + TypeScript + Vite in both `frontend/` and `client-portal/`.
- Shared design focus on chat-centric legal workflows and intake UX.

Infrastructure (`docker-compose.yml`):
- `postgres` (PostgreSQL 15), mapped `5433:5432`.
- `redis` (Redis 7), mapped `6379:6379`.
- `minio` (MinIO), mapped `9000:9000` and console `9001:9001`.

## 4) Backend Architecture and Runtime Flow

### FastAPI Application Wiring

The backend entrypoint (`backend/main.py`) does the following:
- Configures CORS with explicit origin list plus local network regex allowance.
- Initializes and patches database schema at startup.
- Registers all API routers.
- Adds request timing and request-id middleware.
- Starts background worker service.
- Optionally prewarms local transcription pipeline.

Registered routers:
- Auth: `backend/api/auth.py`
- Client portal auth/session: `backend/api/client_portal.py`
- Users: `backend/api/users.py`
- Clients: `backend/api/clients.py`
- Cases: `backend/api/cases.py`
- Consultations: `backend/api/consultations.py`
- Public intake/status: `backend/api/public.py`
- Prompt library: `backend/api/prompt_library.py`
- Documents and uploads: `backend/api/document_router.py`
- Evidence reviews: `backend/api/evidence_reviews.py`
- RAG and copilot endpoints: `backend/api/rag.py`
- Intelligence endpoints: `backend/api/intelligence.py`
- Legal search: `backend/api/search.py`
- Voice endpoints: `backend/api/voice.py`

### Copilot and Agent Pipeline

Based on current backend audit docs and service layout, copilot behavior follows a staged orchestration pattern:
1. Context resolution (history + memory)
2. Prompt correction
3. Intent detection
4. Conditional prompt optimization
5. Case context enrichment
6. Copilot execution/dispatch
7. Memory persistence and structured stage metadata

Key orchestration and runtime files:
- `backend/services/ai/copilot_orchestration_service.py`
- `backend/services/ai/copilot_pipeline_contracts.py`
- `backend/services/ai/copilot_service.py`
- `backend/services/ai/case_context_service.py`
- `backend/services/ai/runtime_services.py`

## 5) AI and Intelligence Capabilities

### Core AI Services

`backend/services/ai/` currently includes:
- Document AI pipeline
- OCR and text cleaning
- PII redaction
- Chunking, embeddings, and vector store support
- Hybrid retrieval and reranking
- Legal search mode
- Case context and case snapshot logic
- Voice transcription and transcript intake extraction
- Artifact versioning and workflow services

### Agent Layer

Implemented agent modules in `backend/services/ai/agents/`:
- Prompt correction agent
- Prompt optimizer agent
- Retrieval agent
- Verifier agent
- Summarization agent
- Case reasoning agent
- Timeline agent
- Drafting agent
- Booking agent
- Intake agent
- Document comparison agent
- Vision analysis agent

### Current quality direction

Recent backend work strengthened:
- Drafted client-update email quality (clear structure, plain language constraints, stronger fallback behavior).
- Case summarization output shape (structured summary, evidence, key points, dates, next steps, explicit fallback signaling).

## 6) Data Model and Persistence

The domain model spans legal and AI workflow entities, including:
- Tenants and users
- Clients and cases
- Documents, chunks, entities
- Voice recordings
- Consultation requests
- Case memory entries and case context snapshots
- Image document batches and assets
- Evidence analysis reviews
- Prompt library entries
- Generated artifact versions
- Background jobs
- Copilot feedback records

Startup schema initialization and legacy patching are automated in backend startup lifecycle.

## 7) Internal Workspace Frontend (frontend/)

The internal app has evolved to a chat-first legal workstation with:
- Authentication and workspace shell.
- Client/case navigation.
- Case-aware chat sessions and history.
- Document upload, voice upload, and recording.
- Scanned-photo/image batch ingestion with OCR/authenticity paths.
- Evidence review queue interactions.
- Prompt library actions.
- Mode switching (chat, agent, legal search, external).

Recent UX changes already applied:
- Right-side panel removed to keep focus on chat center.
- Collapsible left sidebar with icon-only collapsed state.
- Added Bibliotheque tab with global filtering and search.
- Restored lawyer startup client/case chooser gate.
- Empty-chat state simplified to centered search/composer focus.

Operational reliability improvement:
- Image batch polling was tightened to avoid repetitive full context reload storms.
- Poll loop now checks lightweight batch status and only refreshes full context when status changes/completes, with stalled-cycle cap.

## 8) Client Portal Frontend (client-portal/)

Public portal supports:
- Consultation submission.
- Voice note upload or browser recording.
- Supporting document upload.
- Scheduling preference capture.
- Public reference generation and status lookup.

This portal is intentionally separated from internal legal operations and admin/staff-only tooling.

## 9) Tooling, QA, and Reporting

Key scripts under `scripts/`:
- `full_smoke_test.py`: End-to-end API smoke path.
- `run_agent_evals.py`: Agent quality evaluation suite execution.
- `run_regression_checks.py`: Combined compile/smoke/eval gate.
- `generate_feedback_report.py`: Feedback analytics from thumbs up/down data.
- `generate_advancement_log.py`: Push-level advancement log generation.
- `generate_project_report_pdf.py`: Reporting utility.

Quality and traceability assets:
- Eval reports: `advancement/evals/`
- Feedback reports: `advancement/feedback/`
- Push advancement logs: `advancement/`

## 10) Environment and Configuration Notes

Key backend runtime variables (from README and current setup pattern):
- `OPENAI_API_KEY`
- `LLM_BASE_URL`
- `LLM_MODEL`
- `SUMMARY_AGENT_MODEL`
- `TRANSCRIPTION_BASE_URL`
- `TRANSCRIPTION_API_KEY`
- `TRANSCRIPTION_MODEL`
- `TRANSCRIPTION_REMOTE_ENABLED`
- `LOCAL_TRANSCRIPTION_MODEL`
- `TRANSCRIPTION_DEVICE`
- `PORTAL_ALLOW_CONSOLE_CODE_FALLBACK`

Behavioral note:
- If LLM uses OpenRouter-compatible endpoint and transcription base URL is blank, backend can skip remote speech transcription and fallback to local Whisper path.

## 11) Sprint and Roadmap State

From project docs, the system has passed early backend-only stage and already contains:
- Internal workspace functionality.
- Public intake portal.
- Voice/transcription workflow.
- Explicit AI agent modules and staged orchestration.

Ongoing strategic goals still visible in docs/backlog:
- Stronger multi-agent orchestration and verification-first trust layer.
- Case-level reasoning depth over mixed evidence.
- Higher test maturity and production hardening.
- Additional model quality improvements and benchmark discipline.

## 12) What Was Recently Improved (Latest Development Cycle)

### Phase A — closed 2026-05-17 (master plan v2)

Six sub-phases shipped in a single sprint, all green at 233/233 tests:

- **A0 — Big Agent registry.** 5 declarative specialist descriptors (research / drafting / review / workspace / workflow) under `backend/services/ai/big_agents/`. Orchestrator emits `big_agent` on `intent_detection`. `/admin/big-agents` exposes the catalog.
- **A1 — Workspace v2 + Verifier.** Pure `verifier_service` enforces the grounded / partial / refused taxonomy; `/ai/copilot` returns `urn:lai:weak-grounding` problem+json on refusal. New `GET /cases/{id}/workspace` aggregates case + timeline + risk_signals + memory + big_agents.
- **A2 — Drafting v2 + Citations.** `drafting_outline_service` (5 intent templates) + `citation_insertion_service` (`[cite:doc:N]`, `[cite:source:N]`, `[cite:N]` markers). 3 endpoints: `POST /ai/draft/outline`, `/ai/draft/insert-citation`, `/ai/draft/resolve-markers`.
- **A3 — Review Table v2.** `document_review_table_service` projects cached `insights_json` into a Vault-style document × question matrix with `evidence_strength` per cell. `GET /cases/{id}/review-table?questions=...`. No LLM per cell — instant render.
- **A4 — Workflow Blueprints.** `workflow_blueprint_service` exposes 5 Harvey-style blueprints (case_brief_pack, irac_analysis, risk_triage, contract_redline_pack, client_call_recap) with prerequisite checks. `GET /cases/{id}/workflows[/{blueprint_id}]`.
- **A5 — Multi-agent traceability.** `copilot_traces` table persists every orchestrator run (call_id, big_agent, mini_agents_used, intent, duration_ms, verdict). Admin endpoints `/admin/copilot/traces` + `/admin/copilot/trace/{call_id}`. `/admin/big-agents` `last_24h_call_count` is now real data. Admin `/audit` page extended with a Trace tab + reasoning-trail detail panel.

Earlier cycle improvements still in place:

- Major internal workspace redesign to modern, simpler, chat-focused UX.
- Collapsible sidebar behavior and icon-based compact navigation.
- Bibliotheque library browsing view for uploaded assets.
- Cleaner no-chat empty state (centered search/composer).
- Better generated email drafting quality through prompt and fallback improvements.
- Better case summarization quality and output structure.
- Polling-loop fix that mitigates repeated case-context request bursts.

## 13) Current Risks and Gaps

Main remaining risks:
- Need broader automated test coverage (unit/integration/end-to-end).
- Need continued hardening of trust/verification constraints in all answer modes.
- Need sustained evaluation benchmarks and acceptance thresholds across intents.
- Need additional production observability and runbook hardening for deployment operations.

## 14) Practical Runbook

Backend:
1. `pip install -r requirements.txt`
2. `uvicorn backend.main:app --reload`
3. Open Swagger at `http://127.0.0.1:8000/docs`

Frontend internal app:
1. `cd frontend`
2. `npm install`
3. `npm run dev`

Client portal:
1. `cd client-portal`
2. `npm install`
3. `npm run dev`

Docker services:
1. `docker compose up -d`

Regression and quality commands:
- `python scripts/full_smoke_test.py --port 8021`
- `python scripts/run_agent_evals.py --base-url http://127.0.0.1:8000`
- `python scripts/run_regression_checks.py --eval-base-url http://127.0.0.1:8000`
- `python scripts/generate_feedback_report.py --weeks 8`

## 15) Source Documents Used for This Snapshot

Primary repository sources consulted for this file:
- `README.md`
- `backend/main.py`
- `requirements.txt`
- `docker-compose.yml`
- `docs/current_project_report_2026-03-28.md`
- `docs/revised_sprint_plan.md`
- `docs/product_backlog.md`
- `docs/backend_audit_refactor_2026-04-02.md`
- Current code change set in backend AI services and frontend workspace files.

---

If you want, this can be expanded next into a jury-ready version with:
- architecture diagrams,
- endpoint matrix,
- ER/data model diagram,
- and a milestone timeline with commit-level evidence.
