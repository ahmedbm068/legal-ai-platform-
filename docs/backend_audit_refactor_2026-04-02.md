# Backend Audit and Refactor Report (Lawyer Backend)

Date: 2026-04-02
Scope: backend/ API routes, services, AI agents, models, orchestration, permissions

## 1) Full System Audit

### 1.1 Request Lifecycle (Current, Post-Refactor)

1. Frontend sends POST /ai/copilot with user message, mode, workspace context.
2. API layer in backend/api/rag.py forwards to CopilotOrchestrationService.
3. Orchestration pipeline stages:
   - context_resolution (merge client history + persisted case memory)
   - prompt_correction (PromptCorrectionAgent)
   - intent_detection (CommandParsingService)
   - prompt_optimization (PromptOptimizerAgent, only for retrieval-like intents)
   - case_context_enrichment (CaseContextService snapshot)
   - copilot_execution (CopilotService deterministic dispatch)
   - memory_persistence (persist user + assistant exchange in CaseMemoryEntry)
4. CopilotService dispatches by parsed intent to:
   - CRUD/query handlers
   - RAG answer flow via RagService
   - Legal Search mode via LegalSearchModeService
   - domain agents (timeline, reasoning, drafting, booking, comparison)
5. Response is returned with structured_result.pipeline metadata including stage records and case context.

### 1.2 Findings (What Was Wrong / Suboptimal)

High-impact architecture issues identified:
- Orchestration was previously thin and not a real pipeline (memory wrapper only).
- CopilotService did correction/parsing/optimization internally in a monolithic method, causing implicit flow and duplicated responsibilities.
- Case-awareness was fragmented across services; no explicit orchestration stage producing a unified case context snapshot.
- Heavy AI components (embedding/vector pipeline) were instantiated in multiple routers independently, increasing memory and startup/runtime overhead.
- Role checks could drift when enum/string role representations varied in DB/runtime objects.

Medium-impact issues identified:
- API layer mixed endpoint behavior with service construction (harder to test/inject).
- Structured pipeline metadata was not standardized enough for observability.
- Some schema and module structure reflects evolutionary growth rather than clean separation.

### 1.3 Missing Connections

- No explicit typed contract between orchestration stages and execution layer.
- No central reusable "case context" aggregator service for timeline/risk/memory hints.
- No runtime singleton registry for shared AI dependencies.

## 2) Agent System Review (Critical)

### PromptCorrectionAgent
- Role: normalize spelling/grammar while preserving intent and language.
- Input: raw_query, conversation_history.
- Output: corrected_query + changed flag.
- Called in pipeline stage prompt_correction.
- Improvement validity: good for noisy user input; now deterministic and explicit.

### PromptOptimizerAgent
- Role: rewrite query for stronger retrieval/answer quality.
- Input: raw_query + intent + target scope.
- Output: optimized_query + strategy/notes.
- Called in pipeline stage prompt_optimization only for retrieval-oriented intents.
- Improvement validity: useful when bounded by intent; now not duplicated.

### RetrievalAgent
- Role: hybrid lexical + semantic retrieval and reranking.
- Input: tenant scope + question + case/document filters.
- Output: ranked chunks with scores/method.
- Called by RagService and LegalSearchModeService.
- Improvement validity: strong; now benefits from upstream deterministic optimized query.

### VerifierAgent
- Role: grounding check between answer and sources.
- Input: question + answer + source snippets.
- Output: verified status + supported answer + confidence/issues.
- Called by RagService and workflow flows.
- Improvement validity: strong guardrail; should remain mandatory in grounded flows.

### SummarizationAgent
- Role: structured summary synthesis from document + heuristic insights.
- Input: filename + document_text + heuristic_insights.
- Output: structured summary payload.
- Called by SummarizationService.
- Improvement validity: useful; fallback logic already present.

### CaseReasoningAgent
- Role: case-wide reasoning across docs/consultations/voice context.
- Input: case + docs + jurisdiction + optional consult/voice rows.
- Output: narrative, issues, dates, risks, next steps, sources.
- Called by CopilotService and AgentWorkflowService.
- Improvement validity: key for case-level intelligence; now complemented by CaseContextService.

### Additional Agents
- TimelineAgent: extracts timeline events and optional LLM synthesis.
- DraftingAgent: produces client update drafts from grounded summaries.
- BookingAgent: consultation scheduling signal synthesis.
- DocumentComparisonAgent: cross-document mismatch analysis.
- IntakeAgent: transcript-to-intake extraction.

### Redundancy and Consistency Notes
- Previous duplication: correction and optimization could be applied in mixed points.
- Refactor: explicit staged orchestration controls these once and passes pre-parsed/pre-optimized context into execution.

## 3) Refactored Architecture

### 3.1 New Orchestration Design

Single entrypoint remains CopilotOrchestrationService but now with explicit stage contracts and deterministic stage records.

Text flow diagram:

Input request
-> Context resolution (history merge)
-> Prompt correction
-> Intent detection
-> Prompt optimization (conditional)
-> Case context enrichment (timeline/risk/memory snapshot)
-> Copilot execution dispatch
-> Memory persistence
-> Structured response formatting (pipeline metadata)

### 3.2 Data Contracts

Added typed contracts in backend/services/ai/copilot_pipeline_contracts.py:
- CopilotPipelineRequest
- PipelineStageRecord
- CopilotExecutionContext

This enables predictable orchestration metadata and easier testing/telemetry.

## 4) Data and Model Consistency Assessment

Current model strengths:
- Case-centric relations exist (Case -> Document/Voice/Consultation).
- Memory entity exists (CaseMemoryEntry) for conversational persistence.
- Artifact versioning supports generated legal drafting and iterative revisions.

Remaining model opportunities:
- Formal case-level AI snapshot table (optional future enhancement) could persist derived timeline/risk/context at case granularity.
- Some string-based statuses across models can be incrementally tightened with enums.

Implemented now:
- CaseContextService to compute case-centric snapshot from existing relational data without schema-breaking migration.

## 5) Service Layer Review and Refactor

Implemented service-level improvements:
- Added backend/services/ai/runtime_services.py to centralize heavy AI singleton dependencies:
  - shared_document_pipeline
  - rag_service
  - copilot_service
  - copilot_orchestration_service
  - agent_workflow_service
- Routers now consume shared runtime dependencies instead of duplicating expensive model/pipeline construction.

## 6) Auth and Role Logic Review

Implemented:
- Hardened backend/core/permissions.py role normalization to avoid enum/string mismatch bugs in require_roles and admin checks.

## 7) API Design Review

Observed:
- /ai endpoint family now has a clearer orchestration contract via structured_result.pipeline metadata.
- Response format remains frontend-compatible while adding richer pipeline observability fields.

## 8) Performance and Scalability

Implemented:
- Reduced repeated heavy initialization by sharing DocumentAIPipeline and dependent services across routers.
- Deterministic orchestration reduces redundant LLM calls for correction/optimization in mixed flows.

## 9) Code Quality Improvements

Implemented:
- Added explicit orchestration contracts and stage records.
- Reduced hidden cross-layer behavior.
- Improved separation between orchestration and execution.

## 10) Intelligence Upgrade Status

Implemented now:
- Case-aware orchestration stage with CaseContextService.
- Persistent conversation memory integration remains active and explicit.
- Stage metadata exposes risk/timeline/memory signals for downstream UI/agent usage.

Near-term recommended next step:
- Add a dedicated case_context_snapshots table for persisted longitudinal analytics and multi-session retrieval.

## 11) Updated Code (Full Files in Workspace)

Refactor files produced/updated (full files, production-ready in repo):
- backend/services/ai/copilot_pipeline_contracts.py
- backend/services/ai/copilot_orchestration_service.py
- backend/services/ai/copilot_service.py
- backend/services/ai/case_context_service.py
- backend/services/ai/runtime_services.py
- backend/api/rag.py
- backend/api/document_router.py
- backend/api/intelligence.py
- backend/api/public.py
- backend/api/client_portal.py
- backend/core/permissions.py

## 12) Before vs After Summary

Before:
- Thin orchestration wrapper, monolithic implicit copilot flow.
- Redundant or opaque correction/optimization behavior.
- Fragmented case awareness and repeated heavy service construction.
- Role checks sensitive to runtime enum/string representation differences.

After:
- Deterministic, staged orchestration with explicit data contracts and stage metadata.
- Pre-parsed and pre-optimized execution path supported in CopilotService.
- Case-context enrichment stage for timeline/risk/memory awareness.
- Shared runtime singleton services reduce overhead and improve consistency.
- Permission checks hardened for consistent role enforcement.
