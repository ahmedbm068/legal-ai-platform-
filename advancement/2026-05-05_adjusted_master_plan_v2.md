# Adjusted Master Plan — May 5 → July 5, 2026
**Trigger:** Week 1 (planned 56h / 7 days) shipped in **~2 hours** with DoD green.
**New baseline velocity:** ~25× the original plan's assumed pace.
**Owner:** Ahmed · Solo build · ~4–6 productive hours / day average
**Horizon:** 2 months to *defense-ready* — not just "feature complete"

---

## 0 · Why this re-plan exists

The original 8-week plan was sized for a part-time student pace. Actual velocity is dramatically higher, so:

1. **Don't stretch the same scope across 8 weeks** — that wastes the runway and produces a thin product.
2. **Don't just race to the end** — finishing in week 3 with no eval harness, no fine-tuned models, no jury-grade polish is exactly how PFE projects lose marks.
3. **Compress the baseline, then build *above* it.** Use the freed time to ship things Harvey-class products have and student PFE projects don't: a real eval harness, fine-tuned components, production-grade observability, a defensible multi-agent verifier, and a full demo runbook.

The plan below has **4 phases over 9 calendar weeks**, each with hard exit criteria. Phase A is the original 8-week plan compressed. Phases B–D are the *excellence* layer.

---

## 1 · Phase Map (one screen)

| Phase | Window | Calendar | Effort | Headline Outcome |
|---|---|---|---|---|
| **A · Core compressed** | May 5 → May 17 | ~2 weeks | ~30–40h | Original 8-week scope shipped + **Big Agent layer surfaced** + product functionally complete |
| **B · Excellence layer** | May 18 → June 7 | 3 weeks | ~50–70h | Eval harness, persisted metrics, multi-tenant scoping audit, citation grounding ≥ 95% |
| **C · Wow / Differentiation** | June 8 → June 21 | 2 weeks | ~40–55h | Proof-first verifier, voice→case timeline, drafting agent, fine-tuned reranker |
| **D · Polish + Defense** | June 22 → July 5 | 2 weeks | ~30–40h | Demo data, jury runbook, slides, screencasts, end-to-end walkthrough rehearsed |

**Total budget:** ~150–200h of focused work over 9 calendar weeks. Buffer of ~20% baked in.

---

## 2 · Phase A — Core Compressed (May 5 → May 17)

Goal: deliver every backlog item from the original 8-week plan, at production quality.

### A0 · Big Agent Registry + Surfacing — *target: today, ~3h*

**Context.** Audit (2026-05-05) found you already have all 5 Harvey/Legora-class "Big Agents" (specialist agents the orchestrator routes to, like the SQL/Forecasting/Visualization agents in the reference architecture). They are **unlabeled** and scattered across 6 files. The orchestrator already routes to them via 6 frozenset intent groups (`LEGAL_ANALYSIS_INTENTS`, `DRAFTING_INTENTS`, `DOCUMENT_REVIEW_INTENTS`, `CLIENT_EXPLANATION_INTENTS`, `EXPLICIT_ANALYSIS_INTENTS`, `OPTIMIZABLE_INTENTS`).

**Existing inventory (do NOT duplicate):**

| Big Agent | Backed by (already exists) | Triggered by intents |
|---|---|---|
| **Research Agent** (Harvey "Assist") | `copilot_legal_search_execution_service` + `external_research_service` + `copilot_high_reasoning_service` | search-mode + `EXPLICIT_ANALYSIS_INTENTS` |
| **Drafting Agent** (Harvey "Draft") | `copilot_drafting_execution_service` + `/draft-documents` route | `DRAFTING_INTENTS` |
| **Review Agent** (Harvey "Vault") | `document_ai_pipeline` + `/cases/{id}/review-table` route | `DOCUMENT_REVIEW_INTENTS` |
| **Workspace Agent** (Legora) | `copilot_memory_service` + `case_context_service` + `case_snapshot_service` | always-on (state, not intent-routed) |
| **Workflow Agent** | `agent_workflow_service` + `legal_workflow_agent_pack` (21-class IRAC pipeline) | `LEGAL_ANALYSIS_INTENTS` + `agent_execution` route |

**Tasks (zero new business logic — pure surfacing):**
- [ ] Create `backend/services/ai/big_agents/` with 5 thin wrappers (~50 lines each), each declaring `name`, `tier`, `ui_route`, `mini_agents_used`, `intents_handled`, `description`, `delegates_to`
- [ ] Create `backend/services/ai/big_agents/registry.py` — `BigAgentRegistry.list_all()`, `find_by_intent(intent)`, `find_by_route(path)`
- [ ] Each wrapper auto-registers on import; orchestrator's intent-routing decision logs `big_agent=<name>` into trace
- [ ] Admin endpoint `/admin/big-agents` returns the registry as JSON (catalog)
- [ ] Admin app: new tab `/big-agents` rendering tier · name · UI route · mini-agents used · last-24h call count (placeholder until B2 wires real data)
- [ ] Tests: 5 registry tests (one per agent: round-trip, intent match, mini-agent set non-empty)
- [ ] **Cleanup:** the 4 orchestrator files (`runtime_copilot_orchestrator`, `copilot_orchestrator_runtime`, `copilot_orchestration_service`, `multimodal_copilot_orchestration_service`) — pick the canonical one, mark the others as deprecated shims (full collapse deferred to B3)

**Why it matters for the jury:** answers "which agents do you have?" with one screen instead of a grep. Same shape as the reference architecture diagram.

**Exit criteria:**
- `/admin/big-agents` shows 5 agents with non-empty `mini_agents_used`
- `Ran X tests` is up by ≥ 5; suite green
- No new orchestration paths — every Big Agent delegates to its existing service

### A1 · Lawyer Workspace v2 + Verifier (Wow #1) — *target: today–tomorrow*
Original plan: Week 2.

**Backend**
- [ ] Workspace API: `/cases/{id}/workspace` returns case + documents + transcripts + analyses in one call
- [ ] Verifier service: every `/copilot` answer passes through `VerifierAgent` before stream-out; emits `verification_state ∈ {grounded, partial, refused}`
- [ ] Refusal contract: when `verifier_score < 0.6`, response carries `problem+json` with `type=urn:lai:weak-grounding` instead of a fabricated answer
- [ ] Persist `llm_call_log` table (use the dict from `record_llm_call` already returned)
- [ ] Tests: ≥ 6 new unit tests for verifier branch coverage

**Frontend (lawyer)**
- [ ] Case workspace shell: 3-pane layout (case rail · evidence column · copilot panel)
- [ ] Verification badge component: green/yellow/red on every answer, click expands evidence
- [ ] Citation pills inline in answers; click highlights document chunk
- [ ] Empty-state flows for "no evidence" / "weak grounding"

**Exit criteria**
- Lawyer can open a case, ask a question, and the answer is rendered with **at least one verified citation OR a clearly-marked refusal**. No silent hallucinations possible.
- 5 manual QA scenarios pass: known-grounded · partially-grounded · ungrounded · empty-case · multi-doc.

### A2 · Voice Intake v1 — *target: +1 day*
Original plan: Week 3.

- [ ] `/cases/{id}/voice/upload` (multipart, `audio/webm` and `audio/mp3`)
- [ ] Whisper transcription wired (already partially scaffolded in `ai/`)
- [ ] Transcript persisted; attached to case; timeline entry auto-created
- [ ] Frontend: record-from-browser component + upload dropzone + transcript viewer
- [ ] **Differentiator:** transcript chunks become first-class evidence for copilot citations

**Exit:** voice → transcript → citation in copilot answer, end to end.

### A3 · Case-Centric Intelligence — *target: +1 day*
Original plan: Week 4.

- [ ] Timeline endpoint (auto-generated from doc events + transcripts)
- [ ] Party-role mapping endpoint
- [ ] Obligation extraction endpoint
- [ ] All three exposed in workspace UI as collapsible panels

**Exit:** case page renders timeline + parties + obligations from real artifacts.

### A4 · RAG Upgrade — *target: +1 day*
Original plan: Week 5.

- [ ] Search across documents AND transcripts (single FAISS index, source-typed)
- [ ] Metadata filters: `case_id`, `source_type`, `date_range`
- [ ] Citation snippets with offsets (not just doc title)
- [ ] Optional: ingest one open legal corpus (start with EUR-Lex EN subset, ≤ 5k docs) — defer if blocking

**Exit:** copilot answers cite both documents and transcripts with offsets, gated by case scope.

### A5 · Multi-Agent Orchestration — *target: +1 day*
Original plan: Week 6 + 7 merged.

*Builds on A0 (Big Agent registry).* Focus here is **traceability**, not new agents.

- [ ] Orchestrator records per-step trace into a `copilot_trace` table — each row: `call_id, big_agent, mini_agents_used[], intent, duration_ms, verdict`
- [ ] `/copilot/trace/{call_id}` admin endpoint shows the full reasoning trail (orchestrator decision → big agent → mini agents → verifier)
- [ ] Trace viewer in admin app (extend the existing `/audit` page with a Trace tab)
- [ ] Wire the A0 Big Agent registry's call-count counter to read from `copilot_trace` (replaces the placeholder)
- [ ] Surface `big_agent` field in `/admin/big-agents` last-24h column (real data now)

**Exit:** any complex copilot answer is auditable step-by-step from the admin console; admin can answer "how often did the Drafting agent fire today?" with a number.

### A6 · Phase A close — *target: end of May 17*
- [ ] All 151 + new tests green
- [ ] `PROJECT_SO_FAR.md` updated
- [ ] Closeout report `advancement/2026-05-17_phaseA_close.md`

---

## 3 · Phase B — Excellence Layer (May 18 → June 7)

This is what separates a "student finished the plan" project from a "this is shippable" project. None of this was in the original plan.

### B1 · Real Evaluation Harness (5 days)
- [ ] `evals/` framework: JSONL test sets, deterministic seeds, metric runners
- [ ] **Grounding eval:** 100 hand-labeled Q/A pairs, target ≥ 95% citation precision
- [ ] **Refusal eval:** 30 ungrounded questions, target ≥ 95% correct refusal
- [ ] **Latency eval:** P50 / P95 per endpoint, regression-detect on every PR
- [ ] **Cost eval:** $/answer baseline + ceiling alarm
- [ ] CI integration: `make eval` runs the suite; results committed to `advancement/evals/`
- [ ] Baseline numbers locked into `evals/BASELINE.json`

**Exit:** every code change can be measured against the locked baseline. Numbers are jury-defensible.

### B2 · Persisted Observability (2 days)
- [ ] `llm_call_log` table writes from `record_llm_call`
- [ ] `copilot_trace` table writes from orchestrator
- [ ] Admin dashboard tile: 24h cost · P95 latency · refusal rate · per-model usage
- [ ] Export-to-CSV for jury appendix

**Exit:** admin can answer "what did the AI cost this week" and "where did latency spike" from the UI.

### B3 · Security & Multi-Tenant Hardening (3 days)
- [ ] Tenant-scope audit: every query joining a tenant-owned table goes through `apply_tenant_scope`
- [ ] Add `pytest-style` adversarial suite: cross-tenant access attempts must return 404 (never 403, never 500)
- [ ] Rate-limit default: `200/minute` global cap on undecorated routes
- [ ] Prompt-lock surfaced in `/health`; CI fails if drift detected
- [ ] CSRF + secure cookies audit on all 3 frontends
- [ ] OWASP Top-10 self-review checklist committed to `docs/security_review.md`

**Exit:** zero high-severity findings; checklist documented for the jury.

### B4 · UX Hardening (3 days)
- [ ] Loading skeletons everywhere (no spinners on hot paths)
- [ ] Optimistic updates on toast/copilot send
- [ ] Accessibility pass: keyboard nav, ARIA, contrast, screen-reader labels
- [ ] Mobile responsive: client portal must be fully usable on phone

**Exit:** click-through demo can be done on a phone without breaking.

### B5 · Phase B close — *target: end of June 7*
- [ ] Eval baseline numbers green
- [ ] Closeout report `advancement/2026-06-07_phaseB_close.md`

---

## 4 · Phase C — Wow / Differentiation (June 8 → June 21)

Pick **3 of 5** and ship them excellently. Don't dilute. The default 3 are marked ★.

### C1 · Proof-First Verifier 2.0 ★ (4 days)
- Two-pass verification: heuristic overlap → LLM judge for borderline
- Contradiction detection across documents (flag conflicting claims with both citations)
- "Show evidence" panel highlighting exact spans in source PDFs
- *Why it wins:* Harvey shows citations; almost no consumer LLM shows *contradictions*

### C2 · Voice → Case Timeline ★ (3 days)
- Diarization (speaker A / speaker B) on transcripts
- Auto-extract dates, parties, commitments from voice into timeline events
- Hover on timeline event → play the audio snippet that produced it
- *Why it wins:* turns voice intake from a transcription tool into a deposition-prep tool

### C3 · Drafting Agent ★ (3 days)
- "Draft a response letter to [counterparty] addressing claims X, Y" → produces clause-cited draft
- Track-changes UI: every clause has a "why" tooltip with cited evidence
- Export to .docx with comments
- *Why it wins:* concrete demo deliverable the jury can read

### C4 · Trainable Reranker (3 days, *optional*)
- Fine-tune a small cross-encoder (e.g., `ms-marco-MiniLM-L-6-v2`) on hand-labeled retrieval pairs
- A/B against base retrieval in eval harness
- *Why it wins:* gives you "we have a fine-tuned model" — required for an AI-engineering-track PFE
- *Skip if:* eval harness shows base retrieval ≥ 90% recall@5

### C5 · Risk Triage Classifier (3 days, *optional*)
- Few-shot or fine-tuned classifier: "case complexity score 1–5"
- Drives prioritization in case list
- *Why it wins:* second trainable component for the jury

### C6 · Phase C close — *target: end of June 21*
- 3 wow features fully wired, evaluated, and demo-able
- Closeout report `advancement/2026-06-21_phaseC_close.md`

---

## 5 · Phase D — Polish + Defense (June 22 → July 5)

### D1 · Demo Asset Production (4 days)
- [ ] Seeded demo tenant with 3 cases, ~12 documents, 4 voice transcripts
- [ ] Demo accounts: lawyer / client / admin (passwords in `lawyer_demo_runbook.md`)
- [ ] One scripted "happy path" walkthrough (≤ 8 min)
- [ ] One "edge case" walkthrough (refusal + contradiction detection, ≤ 4 min)
- [ ] 2 screencasts (1080p, no audio fluff)

### D2 · Documentation Pack (4 days)
- [ ] Updated architecture diagram (Mermaid + PNG export)
- [ ] Updated `JURY_PROJECT_REPORT.md` with final numbers from eval harness
- [ ] One-page "what is novel here" memo for jury
- [ ] Per-agent capability matrix (input / output / training status / metric)
- [ ] Threat model diagram

### D3 · Defense Rehearsal (3 days)
- [ ] Slide deck (≤ 25 slides)
- [ ] Q&A bank: 30 expected jury questions with crisp answers
- [ ] Two full timed rehearsals
- [ ] Backup: pre-recorded screencast in case live demo fails

### D4 · Final freeze — *target: July 5*
- [ ] Tag `v1.0-defense`
- [ ] Lock prompts (`PROMPT_LOCK.json`)
- [ ] Lock evals (`evals/BASELINE.json`)
- [ ] Closeout report `advancement/2026-07-05_defense_ready.md`

---

## 6 · Daily Cadence (operating rules)

1. **Start each session** by reading the next unchecked checkbox in the current phase. Don't pick.
2. **End each session** by checking off what's done + writing 3 lines into `advancement/daily_log.md`.
3. **Never skip a phase exit criterion.** If you can't satisfy it, you don't move on — you fix it.
4. **Run `make test` before every commit.** 151 → only goes up.
5. **Run `make eval` before every Phase boundary.** Numbers only go up after Phase B.
6. **No refactor for elegance.** This rule from the original plan stays.
7. **One Wow feature shipped > three half-shipped.** Refuse the temptation in Phase C.

---

## 7 · Risk Register

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Phase A finishes too fast → temptation to skip B | High | Critical | Phase B is non-negotiable; eval harness is the jury's first question |
| Voice quality blocks A2 | Medium | Medium | Whisper-medium fallback; drop diarization to Phase C if needed |
| Fine-tuning blocked by data scarcity | Medium | Low | Reranker (C4) and risk classifier (C5) are both optional; skip if eval doesn't justify |
| Scope creep in Phase C | High | High | Hard-cap at 3 features; the other 2 are explicitly out-of-scope |
| Last-week panic in D | Medium | High | All demo assets must be drafted by June 25; week of June 29 = rehearsal only |

---

## 8 · What "perfect" means for this PFE

A defense-ready legal AI platform is one where the jury cannot ask a question that the project doesn't already answer with **a number, a screen, or a doc**:

- "How accurate is the AI?" → eval harness numbers (Phase B1)
- "What does it cost?" → admin cost dashboard (Phase B2)
- "What if the AI is wrong?" → refusal contract + verifier (Phase A1, C1)
- "What's novel?" → contradiction detection or voice→timeline (Phase C)
- "Is it secure?" → security review doc + adversarial test suite (Phase B3)
- "Can we see it work?" → seeded demo + screencast (Phase D1)
- "Can it scale?" → multi-tenant scoping + rate limits (Phase B3)
- "Did you train any models?" → reranker or risk classifier (Phase C4 or C5)

Every box above maps to a deliverable in this plan. **That is what 2 months at your velocity buys.**

---

## 9 · Today's next 4 hours

You have ~4 more hours today. New order — surface what you already have *before* building more on top:

1. **Hour 1:** Phase **A0** — Big Agent layer: 5 wrappers + registry + tests + tag the canonical orchestrator (~50 LOC × 5 + registry ≈ 350 LOC, all glue)
2. **Hour 2:** Phase A0 finish — `/admin/big-agents` endpoint + admin tab; orchestrator emits `big_agent=` in trace
3. **Hour 3:** Phase **A1** backend — `/cases/{id}/workspace` endpoint + verifier integration into copilot stream + 6 unit tests + `verification_state` contract
4. **Hour 4:** Phase A1 frontend — 3-pane layout + verification badge component + citation pills

Stop at A0 exit criterion before starting A1. Stop at A1 exit criterion before tomorrow's A2.

*Key rule reaffirmed: zero new agents this week. A0 is naming + registry, not invention.*

— Plan locked: 2026-05-05
— Adjusted with Big Agent layer: 2026-05-05
