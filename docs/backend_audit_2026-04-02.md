# Backend Audit and Refactor Report (2026-04-02)

## 1. Audit Report

### Request Lifecycle (Before)
1. Frontend called `POST /ai/copilot`.
2. API route in `backend/api/rag.py` directly called `CopilotService.handle_message`.
3. `CopilotService` handled everything in one class:
   - prompt correction
   - intent parsing
   - conversation/workspace scope
   - role checks
   - legal-search mode routing
   - retrieval + external search synthesis
   - case CRUD and appointment actions
   - case reasoning/summarization/drafting
   - response formatting
4. Response returned directly with no persistent cross-request memory.

### Key Problems Found
1. **Overloaded service design**: `CopilotService` mixed orchestration, business actions, retrieval, and formatting.
2. **No persistent case memory**: context continuity depended only on frontend-provided history.
3. **Legal search quality risk**:
   - multilingual keyword corruption in legal-search logic
   - weak domain control in external legal retrieval
4. **Security/role gap**: `/ai/agent-workflow` had no explicit role gate.
5. **Data contract drift risk**: no top-level orchestration contract ensuring deterministic pre/post stages.

### Agent System Review
1. `PromptCorrectionAgent`: useful for typo/intent stabilization; currently called early and correctly.
2. `PromptOptimizerAgent`: useful in retrieval and legal-search query framing; correctly used but previously coupled inside monolith.
3. `RetrievalAgent`: strong hybrid retrieval with reranking; correctly used.
4. `VerifierAgent`: used for grounding in RAG and workflow; useful and correctly placed after generation.
5. `SummarizationAgent`: useful for document intelligence; correctly used through `SummarizationService`.
6. `CaseReasoningAgent`: high-value case-aware synthesis; useful for fallback and risk/timeline workflows.
7. Additional agents (`Timeline`, `Booking`, `Drafting`, `DocumentComparison`, `Intake`): all useful, but orchestration cohesion was fragmented between route/service layers.

## 2. Refactored Architecture

### New Flow (Text Diagram)
1. `POST /ai/copilot` (route)
2. `CopilotOrchestrationService.run` (new single entrypoint)
3. Stage A: resolve context from:
   - persisted case memory (new)
   - request conversation history
4. Stage B: execute domain workflow through `CopilotService`
   - correction -> parse -> mode route -> retrieval/reasoning/actions
5. Stage C: persist new user/assistant exchange into case-aware memory
6. Return normalized response with pipeline metadata in `structured_result.pipeline`

### New Components
1. `CaseMemoryEntry` model (`backend/models/case_memory_entry.py`)
2. `CopilotMemoryService` (`backend/services/ai/copilot_memory_service.py`)
3. `CopilotOrchestrationService` (`backend/services/ai/copilot_orchestration_service.py`)

### Legal Search Refactor
1. Reworked `LegalSearchModeService` with:
   - robust country resolution
   - strict-source pass (official + jurisprudence domains)
   - fallback broad search pass
   - deterministic source normalization/ranking
   - strict output format:
     - `[Legal Source Answer]`
     - `[Answer]`
     - optional `[Fallback Notice]`
2. Removed multilingual corruption issues in Tunisian/German keyword handling.

## 3. Updated Code (Ready to Use)

### New Files
1. `backend/models/case_memory_entry.py`
2. `backend/services/ai/copilot_memory_service.py`
3. `backend/services/ai/copilot_orchestration_service.py`
4. `docs/backend_audit_2026-04-02.md`

### Updated Files
1. `backend/main.py`
   - imports `CaseMemoryEntry` so `Base.metadata.create_all` creates the new table.
2. `backend/api/rag.py`
   - `/ai/copilot` now uses `CopilotOrchestrationService`.
   - `/ai/agent-workflow` now enforces `admin/lawyer` role guard.
3. `backend/services/ai/external_research_service.py`
   - added `allowed_domains` filtering support.
   - normalized domain matching for strict legal-source passes.
4. `backend/services/ai/legal_search_mode_service.py`
   - rewritten with deterministic jurisdiction-aware legal-search pipeline.

## 4. Improvement Summary (Before vs After)

### Before
1. Copilot orchestration and business logic were tightly coupled.
2. No durable case memory between requests.
3. Legal-search multilingual/source logic had reliability issues.
4. Role checks were inconsistent for heavyweight AI workflow endpoints.

### After
1. **Central orchestration**: one professional entrypoint (`CopilotOrchestrationService`).
2. **Persistent case-aware memory**: continuity across prompts even when frontend history is incomplete.
3. **Safer legal retrieval**: source-prioritized, jurisdiction-aware external research with strict formatting.
4. **Improved security posture**: explicit role protection on `/ai/agent-workflow`.
5. **Production-readiness boost**: cleaner layering, stronger contracts, and reduced architectural ambiguity.
