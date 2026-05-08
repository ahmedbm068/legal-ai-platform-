# Legal Practice and Harvey Gap Analysis

Original date: 2026-04-23
Last updated: 2026-05-06

## 0. Update log

- 2026-04-23 — original gap analysis written.
- 2026-05-06 — updated after the Phase A close-out, the engineering hardening
  pass (Alembic, rate limiting, structlog, frontend tests, LLM cost/latency
  baseline) and the design of two new AI-engineering features (multilingual
  answers and dual-answer deep reasoning with a judge agent).

## 1. Why this document exists

This document compares three things:

- how real legal analysis is taught in the legal-practice material from
  `C:\Users\ahmed\Downloads\legal practice (1).pdf`
- how Harvey describes its product and operating model in the transcript
  shared on 2026-04-23
- how the current Legal AI Platform actually works today

The goal is simple: turn the project from a broad legal AI demo into a more
lawyer-realistic product that earns trust.

## 2. What the legal-practice material says lawyers actually do

The legal-practice material is not mainly about firm management. It is about
how legal reasoning works.

Core takeaways:

- A lawyer starts by identifying the exact issue, not by producing an answer
  immediately.
- Facts matter twice: first to understand what happened, then to isolate the
  operative facts that change the result.
- Legal analysis is structured: conclusion, rule, explanation, application,
  counter-analysis.
- Case reading requires: court, procedural posture, parties, facts, legal
  issue, holding, reasoning, dicta, and outcome.
- Good legal work compares the client fact pattern against authority, instead
  of only summarizing authority.
- Legal conclusions should be framed with the correct level of confidence and
  with awareness of missing facts.

What this means for the product:

- The AI should act more like a junior associate preparing a grounded internal
  note.
- The system should separate facts we know, rules we found, application,
  uncertainties, and next steps.
- "Answer quality" in law is not just fluency. It is issue spotting, rule
  accuracy, fact matching, and cautious reasoning.

## 3. What Harvey gets right from the transcript

The Harvey transcript points to five strong product principles.

### A. Trust is the product

- Prestige matters because trust matters.
- Citations were a core investment from day one.
- Lawyers trust systems that show their work.

### B. Intent → context → validation

Harvey describes legal AI as three linked problems:

1. What does the user want?
2. What context do we need?
3. Is this right?

That maps directly to routing, retrieval, and verification — and matches the
current orchestrator stages: command parsing → context loading → execution →
verifier.

### C. Expand then collapse

- Build narrow workflows for high-value legal tasks.
- Then collapse them back into one product surface with good suggestions and
  orchestration.

### D. Process data matters more than generic legal text

- Reading legal documents is not enough.
- The product must encode how lawyers actually do tasks.
- Domain experts define steps; models execute within those steps.

### E. Blank-page avoidance and personalization matter

- Lawyers adopt AI faster when the UI suggests the right starting workflows.
- A pure empty chat box is not enough for real professional use.

## 4. Where the project is already strong (updated 2026-05-06)

Confirmed strengths after the May audit:

- **System breadth.** ~94K LOC across backend, three frontends, infra, tests
  and scripts. Backend alone is ~46K LOC, 137 endpoints, 35 SQLAlchemy models,
  28 mini-agents and 5 declarative big agents.
- **Legal-product direction.** Case-centric workflows, not a generic chatbot.
- **Code-aware legal search.** Already retrieves and scopes by code family.
- **Real orchestration.** A staged graph (memory → correction → parsing →
  optimization → context → execution → verifier → assembly → trace) with
  per-stage logging, not a glorified prompt wrapper.
- **Verifier with three states** (grounded / partial / refused), with an
  explicit `_NEVER_REFUSE_INTENTS` carve-out for drafting flows so the system
  never blocks the lawyer from generating something they explicitly asked
  for.
- **Trust UI loop closed end-to-end.** The verifier verdict is rendered as a
  badge on every assistant message in `ChatMessageBubble.tsx`, including the
  new `trust-refused` state.
- **Observability triad.** `llm_call_log`, `request_audit_log` and
  `copilot_trace` tables. After the May hardening pass, an
  `/admin/llm/baseline` endpoint and a `scripts/llm_cost_latency_baseline.py`
  CLI report P50 / P95 / P99 latency, token totals and USD spend.
- **Schema versioning.** Alembic now configured with a `0001_baseline` no-op
  migration so existing databases can be brought under control without
  disruption.
- **Rate limiting.** Now applied to every previously-unprotected LLM endpoint
  (`/ai/copilot`, `/ai/optimize-prompt`, `/ai/artifacts/versions/*`,
  `/ai/test-llm`, `/ai/translate`, `/draft-documents/{id}/ai-edit`,
  `/draft-documents/{id}/send-email`, export endpoints). LLM-budget DOS by a
  single user is no longer trivial.
- **Structured logging.** `backend/core/logging_config.py` wires `structlog`
  at process start; toggle JSON output via `LOG_FORMAT=json`.
- **Frontend tests.** Vitest scaffolded with three component-test files
  (`chatStorage.test.ts`, `SendEmailModal.test.tsx`,
  `AppErrorBoundary.test.tsx`) and a Playwright happy-path
  (`e2e/login-happy-path.spec.ts`).

The problem is no longer "the project is weak". It is "the AI-engineering
rigor (evals, ablations, hallucination measurement) is shallower than the
platform engineering". Sections 8–10 close that.

## 5. Main gaps between real legal work and the current platform

### Gap 1. The product still answers too much like an assistant and not enough like a legal analyst — IN PROGRESS

Current state:

- Legal search retrieves sources and generates grounded answers.
- The system infers case topic and retrieves relevant code articles.
- Legal-search prompting has been updated toward an issue → rule → application
  → uncertainty → next-steps structure.

Still missing:

- A strict, contract-validated lawyer-style reasoning sequence enforced as a
  structured-output schema rather than a prompt-only convention.
- Strong separation between confirmed facts and assumptions, surfaced in the
  UI rather than only in the prose.

Impact: answers are improving but not yet provably structured.

### Gap 2. Citations exist, but trust is still snippet-level — PARTIALLY ADDRESSED

Current state:

- Citations and source metadata are returned and rendered.
- The verifier classifies each answer into grounded / partial / refused.
- `[cite:doc:N]` markers flow end-to-end: prompt → LLM output →
  `citation_insertion_service` parsing → `ChatMessageBubble` rendering.

Still missing:

- Strong article-by-article claim mapping (which sentence in the answer maps
  to which article in which document).
- A final validation step checking that quoted rule statements really match
  the retrieved article text. Today this is rule-based; the labelled eval set
  (Section 8.1) will quantify how often it is right.

### Gap 3. The app is broad, but workflow packs are not lawyer-specific enough — IN PROGRESS

Current state:

- Phase A4 introduced `workflow_blueprint_service.py` with templates: IRAC
  analysis, case brief, risk triage.
- A `/cases/{id}/workflows` endpoint serves these to the frontend.

Still missing:

- Dedicated legal-method workflow packs in the UI for: legal issue memo,
  case-law / code comparison, article applicability review, succession
  entitlement analysis, international private law conflict analysis,
  litigation position memo.
- Each pack should be a one-click action in the workspace, not a free-form
  prompt.

### Gap 4. Legal search is code-aware, but not yet full legal-method aware

Current state:

- Legal search can infer case topic and scope code families.

Still missing:

- Procedural posture awareness.
- Substantive vs procedural law distinction.
- Explicit "missing facts that may change the legal result" surface.
- Dedicated counter-analysis section in the structured output.

### Gap 5. The product has intelligence panels, but trust UX is still underdeveloped — PARTIALLY ADDRESSED

Current state:

- Workspace shows risks, missing info, evidence, timeline.
- The trust badge (grounded / partial / refused) is rendered next to every
  assistant message.

Still missing:

- A dedicated trust drawer per message showing: confidence, legal basis,
  missing facts, contradictions, and verifier reasoning text.
- A lawyer-facing "before you rely on this" checklist tied to each citation.

### Gap 6. Limited encoded process data from practicing lawyers

Current state:

- The platform uses prompts, heuristics, retrieval, and agents.

Still missing:

- Decision trees from real lawyers (notice clauses, chronology comparison,
  dispositive facts, missing-document detection).
- Jurisdiction-specific playbooks from the cabinet.

This is the highest-leverage product-research gap and remains pending.

### Gap 7 (NEW, 2026-05-06). Multilingual answers — DESIGNED, NOT YET BUILT

Tunisian legal practice routinely mixes French, Arabic and English. Today the
system replies in whatever language the model picks — usually echoing the
user's input language. There is no first-class output-language control. See
Section 8 priority 6.

### Gap 8 (NEW, 2026-05-06). Deep reasoning is single-shot — DESIGNED, NOT YET BUILT

The current `reasoning_level=high` setting still produces a single answer.
There is no diversity, no self-consistency, no judge step. For high-stakes
matters, juries (and lawyers) want to see the system actively comparing two
candidate analyses and explaining the choice. See Section 8 priority 7.

### Gap 9 (NEW, 2026-05-06). AI-engineering rigor — UPGRADED INFRASTRUCTURE, METRICS STILL MISSING

After the May hardening pass the *infrastructure* for AI-engineering rigor is
in place (LLM call log table, baseline endpoint, structured logging). What is
still missing are the *measured numbers*: a labelled eval set, recall@k for
retrieval, hallucination rate, refusal calibration precision/recall, prompt
A/B deltas. See Section 8 priority 8.

## 6. Product direction that fits the target cabinet

Because the cabinet mainly cares about:

- Code civil
- Code de succession
- Code international privé

the best strategy is not to be "AI for all law".

The best strategy is:

- be the most trustworthy Tunisian code-based legal copilot for private
  practice matters
- help the lawyer understand the matter first
- help the lawyer locate the right articles
- help the lawyer test whether those articles actually fit the facts
- help the lawyer see what facts are still missing
- help the lawyer produce a useful internal note or client-facing next step

That is a much sharper and more credible product than "general legal AI".

## 7. Recommended target workflow for legal search

The ideal legal-search flow:

1. Intake the question and case facts.
2. Classify the matter: civil obligation, succession, international private
   law, mixed.
3. Extract the legal issue.
4. Retrieve the most relevant code articles.
5. Build the governing rule from those articles.
6. Compare the rule against known facts in the case.
7. Surface missing facts and alternate interpretations.
8. Produce practical next steps for the lawyer.
9. Offer one-click follow-ups: draft memo, ask for missing documents, compare
   alternative interpretations, prepare client explanation.

This is much closer to both the legal-practice material and Harvey's workflow
philosophy. Steps 1–5 are present today; steps 6–9 are the focus of the next
sprint.

## 8. Concrete roadmap (rewritten 2026-05-06)

Status legend: ✅ done · 🔄 in progress · ⏳ pending · 🆕 newly designed.

### Priority 1. Make every legal answer follow legal method — 🔄

- ✅ Backend legal-search prompts updated toward issue / rule / application /
  uncertainty / next-steps.
- ⏳ Promote the structure from prose to a Pydantic-validated structured
  output so the orchestrator can fail closed when sections are missing.
- ⏳ Render each section as a discrete UI block with its own copy/cite
  affordance.

### Priority 2. Add a trust layer in the UI — 🔄

- ✅ Trust badge (grounded / partial / refused) on every assistant message.
- ✅ `verification_state` plumbed end-to-end:
  `verifier_service` → `runtime_copilot_orchestrator` →
  `RoutedWorkspaceContext` → `ChatMessageBubble`.
- ⏳ Per-message trust drawer with confidence, legal basis, missing facts,
  contradictions, verifier reasoning text.
- ⏳ "Before you rely on this" checklist tied to each citation.

### Priority 3. Build workflow packs instead of only modes — 🔄

- ✅ `workflow_blueprint_service.py` (Phase A4) with IRAC, case brief and
  risk triage templates plus a serving endpoint.
- ⏳ Dedicated UI cards for: civil dispute analysis, succession distribution
  analysis, international private law conflict screening, legal memo from
  case facts, article applicability review.

### Priority 4. Capture cabinet process data — ⏳

Sit with the cabinet and ask:

1. When a new case arrives, what are the first five questions you ask?
2. What makes you decide a case is weak or strong?
3. Which missing documents block legal advice most often?
4. How do you structure an internal legal note?
5. Which articles do you check first for common matter types?

That process data is more valuable than adding more generic AI features. This
remains the highest-leverage pending item.

### Priority 5. Strengthen article-level verification — 🔄

- ✅ `verifier_service` scoring grounded / partial / refused.
- ⏳ Claim-to-article mapping at the sentence level.
- ⏳ Article-text re-fetch and re-validation before final answer.
- ⏳ Lawyer-visible warning when support is partial.

### Priority 6 (NEW 2026-05-06). Multilingual answers — 🆕 designed

User picks French, Arabic or English in the UI; the model replies in that
language regardless of input language and regardless of source-document
language. Citations and statute names stay in their original language so
legal precision is preserved.

Implementation outline (full spec in `docs/PFE_FINAL_PLAN.pdf` §7):

- Add `output_language` and `language_strict` fields to `CopilotRequest`.
- Thread through `CopilotExecutionContext`.
- Inject a target-language directive in `copilot_response_assembly_service`.
- Add a small offline language-detection service for `output_language=auto`.
- Add a `language` column to `copilot_trace` so eval reports can break
  accuracy down per language.
- Frontend: header language picker (persisted to localStorage), RTL layout
  switch when Arabic is selected, "translated answer — citations in original
  language" hint when source language differs from output language.

### Priority 7 (NEW 2026-05-06). Dual-answer deep reasoning + judge agent — 🆕 designed

When the user picks `reasoning_level=deep`, the system produces two
independent candidate answers in parallel and a third "judge" agent picks
the best one and explains why. Textbook self-consistency / LLM-as-judge.

Implementation outline (full spec in `docs/PFE_FINAL_PLAN.pdf` §8):

- Two candidates run via `asyncio.gather`: A is conservative
  (low-temperature, primary IRAC framing); B is exploratory
  (higher-temperature, "steelman the opposing position" framing).
- New file `backend/services/ai/agents/judge_agent.py`. Inputs: original
  query, candidate A, candidate B, retrieved sources. Output: structured
  JSON with `chosen_candidate` ∈ {A, B, merge}, per-criterion scores
  (grounding, citation faithfulness, completeness, legal precision,
  language compliance, refusal correctness), and a `final_answer`.
- Persist the full judge JSON into `copilot_trace.judge_payload`.
- Frontend: reasoning-mode selector (Quick · Standard · Deep), expandable
  "show candidates and judge reasoning" disclosure, latency-warning pill.
- Cost cap: tenant-level `DEEP_REASONING_DAILY_BUDGET_USD` enforced in the
  orchestrator.
- Eval upgrade: report A-alone accuracy, B-alone accuracy, judge-chosen
  accuracy, and oracle accuracy (always pick the better of A/B). If
  judge-chosen meaningfully beats either alone, the slide is built.

### Priority 8 (NEW 2026-05-06). Real AI-engineering metrics — ⏳

These are the numbers a competent jury will ask for.

- ⏳ Hand-label 50–100 (query, expected_intent, expected_citations) tuples.
- ⏳ Run weekly. Track intent accuracy, citation coverage, hallucination
  rate. Put a chart in the slides.
- ⏳ RAG ablation: measure recall@5 on the eval set with and without the
  reranker.
- ⏳ Refusal calibration: sample 50 verifier outputs, label each, report
  precision/recall of `refused`.
- ⏳ Prompt A/B: ship one measured before/after change ("matter
  classification accuracy 72% → 81%").
- ✅ Cost / latency baseline infrastructure (`/admin/llm/baseline` and
  `scripts/llm_cost_latency_baseline.py`); ⏳ wire `persist_llm_call()` into
  the actual gateway call sites so the table fills with real data.

### Priority 9 (NEW 2026-05-06). Operational hardening — mostly ✅

- ✅ Alembic migrations scaffolded (`alembic.ini`, `alembic/env.py`,
  `alembic/versions/0001_baseline.py`, `alembic/README.md`).
- ✅ `.gitignore` blocks `.env`; `.env.example` in place.
- ⏳ Rotate the historical API keys and scrub `.env` from git history with
  `git filter-repo --path .env --invert-paths` (only the user can do this).
- ✅ Rate limiting on every LLM endpoint.
- ✅ Structured logging via `structlog`.
- ✅ Tightened `except Exception` handlers in `rag.py` and `intelligence.py`.
- ✅ Vitest + Playwright frontend test scaffolding.

## 9. What "perfect" should mean for this project (refined 2026-05-06)

For this project, "perfect" should not mean:

- the biggest number of AI agents
- the flashiest interface
- the longest answer

It should mean:

- a lawyer can trust the flow
- the answer is grounded in the right code family
- the system distinguishes law from assumptions
- missing facts are surfaced clearly
- the AI helps unblock the next legal step
- **the right number is shown next to every claim of quality**: hallucination
  rate on a labelled set, recall@5 of retrieval, refusal precision, cost per
  intent, P95 latency. Without those numbers, the AI-engineering side of the
  defense is weaker than it has to be.

That is the right standard.

## 10. Best next build sequence (re-prioritized 2026-05-06)

In order of ROI:

1. **Hand-label the eval set (50–100 tuples) and wire it into the regression
   harness.** Single highest-impact deliverable for the AI-engineering story.
2. **Wire `persist_llm_call()` into the LLM gateway** so the existing baseline
   endpoint reports real numbers in the slides.
3. **Rotate the leaked keys and scrub git history.** Non-negotiable
   pre-defense action.
4. **Ship multilingual answers** (priority 6). High demo impact, modest
   engineering cost.
5. **Ship dual-answer deep reasoning + judge agent** (priority 7). Strongest
   single AI-engineering feature on the roadmap.
6. **Trust drawer per message + claim-to-article mapping** (priorities 2 & 5).
   Closes the trust UX loop the gap analysis identified in April.
7. **Workflow packs in the UI** (priority 3). Once trust UX is solid, the
   workflow packs become much more useful.
8. **Cabinet process-data interview** (priority 4). Without this, no amount
   of engineering will make the system feel like real legal practice.
9. **Workflow refinement: counter-analysis and missing-fact extraction as
   structured outputs** (priority 1).
10. **Refactor of `copilot_case_analysis_service.py`** into IRAC, deadline,
    and party-triage use-case services. Long-term maintainability win.

If executed in this order, the platform clears every concrete gap identified
on 2026-04-23 and adds the AI-engineering numbers and features that turn the
project from "very strong software with AI features" into "credible AI
engineering work".
