# Phase A — Closeout Report

**Date:** 2026-05-17
**Plan:** `advancement/2026-05-05_adjusted_master_plan_v2.md`
**Branch state at close:** all green, **233 tests** in ~5s

---

## 1. Scope delivered

Six sub-phases (A0–A6), one cohesive shipment:

| Sub-phase | Title | Tests added | Status |
|---|---|---|---|
| A0 | Big Agent registry | +10 | ✅ |
| A1 | Workspace v2 + Verifier | +13 | ✅ |
| A2 | Drafting v2 + Citations | +14 | ✅ |
| A3 | Review Table v2 | +13 | ✅ |
| A4 | Workflow Blueprints | +16 | ✅ |
| A5 | Multi-agent Orchestration / Trace | +16 | ✅ |
| A6 | Phase A close | — | ✅ |
| **Total** | | **+82** | **233 / 233** |

Baseline at start of Phase A: **151** tests. Final: **233**. Net delta: **+82 tests, 0 regressions**.

---

## 2. New backend surfaces

### Services (pure, stateless, dataclass-based)
- `backend/services/ai/big_agents/` — base + 5 descriptors + registry singleton
- `backend/services/ai/verifier_service.py`
- `backend/services/ai/drafting_outline_service.py`
- `backend/services/ai/citation_insertion_service.py`
- `backend/services/ai/document_review_table_service.py`
- `backend/services/ai/workflow_blueprint_service.py`
- `backend/services/ai/copilot_trace_service.py`

### Models
- `backend/models/copilot_trace.py` (`copilot_traces` table)

### Endpoints added
- `GET  /admin/big-agents` (now with real `last_24h_call_count`)
- `GET  /admin/copilot/traces`
- `GET  /admin/copilot/trace/{call_id}`
- `GET  /cases/{id}/workspace`
- `GET  /cases/{id}/review-table`
- `GET  /cases/{id}/workflows`
- `GET  /cases/{id}/workflows/{blueprint_id}`
- `POST /ai/draft/outline`
- `POST /ai/draft/insert-citation`
- `POST /ai/draft/resolve-markers`

### Schema additions
- `CopilotResponse.verification` (grounded / partial / refused)
- `DraftOutlineRequest`, `CitationInsertionRequest`, `CitationInsertionBulkRequest`

### Refusal contract
- `urn:lai:weak-grounding` problem+json (`422`) on insufficient evidence — drafting / explanation / summarize intents are exempted from refusal by design.

---

## 3. New admin frontend surfaces

- `/big-agents` — catalog page with intents, mini-agents, UI route, last-24h call count
- `/audit` (renamed **Audit & Trace**) — two tabs:
  - **HTTP Audit** (existing)
  - **Copilot Trace** — verdict-filterable list + full reasoning-trail detail panel (intent → big agent → mini-agent chips → ordered pipeline stages with status badges)

---

## 4. Architectural patterns established

Every Phase A service follows the same shape — this is now the project's house style:

1. Pure module — no DB / LLM / IO inside the service layer.
2. Frozen dataclasses with `to_dict()` for serialization.
3. Module-level singleton (`xxx_service = XxxService()`).
4. Defensive readers (`Mapping[str, Any]`, JSON-or-dict tolerance).
5. Endpoint layer is responsible for tenant scoping, DB access, and error envelopes.
6. Tests use `unittest.TestCase` + plain stubs. No `TestClient`, no DB fixtures.

`copilot_trace_service.record()` is the canonical example of the "best-effort sidecar" pattern: the orchestrator's main response path must never fail because tracing failed.

---

## 5. Jury defense surface (what this unlocks)

- **"What does Vault do?"** → live `/cases/{id}/review-table` demo.
- **"What does Harvey Workflows do?"** → live `/cases/{id}/workflows` catalog with availability per case.
- **"How does the AI ground its answers?"** → verifier taxonomy + 422 problem+json contract.
- **"Show me what the AI actually did on call X."** → `/admin/copilot/trace/{call_id}` reasoning trail in the Trace tab.
- **"How often did the Drafting agent fire today?"** → `last_24h_call_count` on `/admin/big-agents`.

---

## 6. Deprecation hygiene

- 2 orchestrator shims (`backend/services/ai/case_orchestrator.py`-style re-exports) tagged `DEPRECATED` in their docstrings. Full removal scheduled for Phase B3.
- 1 empty orchestrator file remains pending cleanup.
- Big-Agents admin `last_24h_call_count` placeholder (Phase A0) was replaced with real data in A5.

---

## 7. Out of scope, intentionally

- **Workflow execution v2.** A4 ships the *catalog* surface only. Actual step-by-step execution for the 4 new blueprints (irac_analysis, risk_triage, contract_redline_pack, client_call_recap) is deferred — the existing `agent_workflow_service.run_case_workflow` already covers `case_brief_pack`.
- **Custom orchestrator model.** Per the plan, the future trained-in-house orchestrator model is being developed outside this repo and will be wired in later.
- **Lawyer-frontend wire-up.** A1–A4 endpoints are exercised through tests only; the lawyer workspace UI consuming them is queued for the next phase.

---

## 8. Health snapshot at close

- Tests: **233 / 233 passing**, ~5s runtime.
- New services: **7**, all with dedicated test files.
- Lint / type errors across all touched files: **0**.
- Schema migration risk: low — only one new table (`copilot_traces`) registered via `Base.metadata.create_all`.

---

## 9. Recommended next phase

**Phase B — Eval & Observability.** Build a golden-set eval harness over the orchestrator that emits grounded% / refusal-rate / partial%. Phase A made these metrics *measurable*; Phase B makes them *reportable*.
