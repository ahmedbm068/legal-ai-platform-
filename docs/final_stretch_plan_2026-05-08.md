# Final-stretch plan — from "very strong" to 19.5/20

Date: 2026-05-08
Owner: Ahmed
Defense window: ~4–6 weeks out

## 0. Honest assessment

The platform is already in the top tier of student projects: ~94K LOC,
real orchestrator, verifier with three states, dual-answer + judge agent,
NLI faithfulness, multilingual output, structured-IRAC contract, unified
trust drawer, HyDE+RRF retrieval, contract-validated pipelines, structured
logging, Alembic migrations, rate limiting, frontend test scaffolding.

What separates "great software with AI features" from a 19.5 PFE defense
in front of an AI-savvy jury is **three** things only:

1. **Measured numbers** — every claim about quality must be backed by a
   chart, not a vibe.
2. **At least one model you trained yourself** — proves this is AI
   engineering, not an LLM wrapper.
3. **A defense story that lands** — slides that walk the jury from problem
   to product to numbers to live demo without a stumble.

Everything below targets exactly those three.

---

## 1. Highest-leverage actions (in order)

### Action 1 — Hand-label an eval set (80 tuples, 2 days)

The single biggest gap. Without it, every other AI claim is unfalsified.

**Schema** (`backend/eval/eval_set.jsonl`):

```json
{"id": "eval-001",
 "query": "Quels sont les droits du conjoint survivant en présence de deux enfants ?",
 "language": "fr",
 "expected_intent": "ask_global",
 "expected_matter_type": "succession",
 "expected_articles": ["Art. 85 CSP", "Art. 88 CSP"],
 "expected_grounding": "case-grounded",
 "expected_refuse": false,
 "expected_jurisdiction": "tunisia",
 "notes": "Classic 1/4 share if no will"}
```

**Distribution** (target 80, minimum 50):
- 30 succession (cabinet's main domain)
- 20 civil obligation
- 15 international private law
- 10 mixed / edge cases
- 5 deliberately impossible (verifier should refuse)

**How to build**:
- Take 30 cases from the cabinet's archive → distill 1 query each
- Use `scripts/synthetic_eval_generator.py` (already drafted) to produce 50
  more synthetic, then hand-correct
- Write a single `scripts/run_eval_harness.py` that runs the set every
  night and emits a CSV with: intent_accuracy, matter_type_accuracy,
  citation_coverage@5, hallucination_rate, refusal_precision, P95 latency,
  cost_usd_per_query

**Slide deliverable:** one chart showing the metric trend across 4 weekly
runs, plus an A/B chart showing each feature flag's contribution.

### Action 2 — Train ONE model end-to-end

You only need one trained model to convert "LLM wrapper" into "AI
engineering". Two is better. Three is showing off. Pick from:

| # | Model | Base | Data | Hardware | Slide-ready outcome |
|---|---|---|---|---|---|
| **A** | **Cross-encoder reranker** | `cross-encoder/ms-marco-MiniLM-L-6-v2` | 5–10K synthetic (query, passage, label) pairs from your corpus, labeled with GPT-4 + cleanup | Colab free GPU, 3–5 hrs | NDCG@5 0.62 → 0.78 |
| **B** | **Matter-type classifier** (civil / succession / IPL / penal / mixed) | `distilbert-base-multilingual-cased` or `camembert-base` | 800–1200 labels (mostly synth + 200 cabinet) | Laptop CPU, 30 min | Accuracy 65% rule → 85%+ |
| C | Tunisian legal NER (article refs, parties, jurisdictions, dates) | `Davlan/bert-base-multilingual-cased-ner-hrl` | ~600 labelled spans | Colab free GPU, 2 hrs | F1 chart per entity |
| D | Refusal classifier (replaces rule-based verifier) | LogisticRegression / XGBoost | 200 hand-labeled (sources_count, confidence, NLI, etc.) | Laptop, minutes | Refusal precision 0.71 → 0.89 |

**Recommendation: train A (reranker) — biggest visible quality bump and
plugs into the existing `reranker_service` slot with a one-line model
swap. If you have time, add B (classifier) — replaces the rule-based
matter-type detection with a measured win.**

The training notebook lives in `notebooks/train_legal_reranker.ipynb`.
Model artifact goes to `backend/models_local/legal_reranker_v1/` and is
loaded by `reranker_service` when `RERANKER_MODEL=local:legal_reranker_v1`.

### Action 3 — Wire the eval harness into CI for one feature

Pick one feature flag (recommend `LAI_ENABLE_HYDE_RRF`) and ship a script
that runs the eval set with the flag ON and OFF, prints the diff. This is
the chart that closes the AI-engineering case.

```text
                  recall@5   hallucination   refusal_precision
baseline          0.61       18%             0.71
+ HyDE+RRF        0.74       15%             0.71
+ trained reranker 0.81       12%             0.71
+ NLI faithfulness 0.81       7%              0.71
+ refusal classifier 0.81     7%              0.89
```

That table is your defense.

### Action 4 — Rotate keys + scrub git history

Non-negotiable before defense. The `.env` was committed in early sprints.

```bash
git filter-repo --path .env --invert-paths
# rotate OPENAI_API_KEY, GROQ_API_KEY, TAVILY_API_KEY, SMTP_PASSWORD
# force-push ONLY after coordinating; do NOT do this the night before
```

### Action 5 — Cabinet process-data interview (one afternoon)

Five questions only. Record answers. Convert into ONE workflow pack the
jury can see live:

1. When a new case arrives, what are the first five questions you ask?
2. What makes you decide a case is weak vs strong?
3. Which missing documents block legal advice most often?
4. How do you structure an internal legal note?
5. Which articles do you check first for common matter types?

The deliverable is a JSON in `backend/data/cabinet_playbook.json` and
**one clickable workflow card** in the UI ("Succession entitlement
analysis", say). Then the jury sees you didn't just guess — you talked
to a real lawyer.

---

## 2. New features that elevate to 19.5

Pick 2–3, not all of them. Optimize for visible-in-demo + unique-vs-Harvey.

### A. Tunisian succession entitlement calculator (HIGH ROI)

The cabinet's bread and butter. Take family situation (spouse, N children
of each gender, parents, siblings) + estate value → output entitlement
percentages with article citations. Pure Python rules engine on top of
Code de Statut Personnel articles 85–152. Renders as a clickable workflow
card.

Why it matters: NO competitor has this for Tunisian law. Specificity beats
breadth. The cabinet will use it day 1.

Effort: 2 days. File: `backend/services/legal/succession_calculator.py`
+ frontend card in `WorkflowPacksPanel`.

### B. "Show your work" reasoning trace panel (MEDIUM ROI)

You already log every stage in `copilot_trace`. Surface it. A sliding side
panel that visualizes:

```
query → intent (88% conf, classifier)
      → retrieval (HyDE: 3 queries, RRF pool 47 → top 5)
      → reranker scores (0.91, 0.84, 0.82, 0.71, 0.69)
      → IRAC sections (5/5 validated)
      → verifier (grounded, NLI 0.91)
```

Why it matters: visual proof of "trust is the product". The jury sees the
whole pipeline in one panel, on a real query, in real time. This is what
Harvey calls "show your work" and you'd ship it before they do for
Tunisian law.

Effort: 1.5 days. New `frontend/src/components/ReasoningTracePanel.tsx`.
The data is already in `response.execution_trace`.

### C. Lawyer review queue + label feedback loop (MEDIUM ROI)

Every "partial" or "refused" answer goes to a queue page. The lawyer
clicks "this refusal was correct" / "this answer was wrong" / "this
citation didn't match the article". Labels are written to `eval_labels`
table and weekly the eval harness picks them up.

Why it matters: closes the loop between product use and AI improvement.
A jury question will be "how does this get better over time?" — this is
the answer.

Effort: 1.5 days. New page `frontend/src/pages/LawyerReviewQueuePage.tsx`
+ table `eval_labels`.

### D. Article freshness + revision tracker (LOW EFFORT, HIGH PERCEIVED RIGOR)

Each retrieved article gets a "last revised: 2018-04-12" badge. If the
article was revised after the cabinet's case incident date, show a
warning chip. Comes free if you have the law-source metadata.

Effort: 0.5 day. Field in `legal_corpus` schema + UI badge.

### E. Citation drift detector (HIGH PERCEIVED INTELLIGENCE)

When the answer cites "Art. 85 CSP" but the retrieved snippet for that
citation is actually from "Art. 87 CSP", flag it as a citation drift.
Pure regex + lookup, no LLM. Lives inside `verifier_service`.

Why it matters: catches real hallucinations the NLI service might miss.
Easy to demo with a deliberately-fluffed query.

Effort: 0.5 day. Adds one method to `verifier_service.py`.

### F. Local-first / privacy mode toggle (HIGH PERCEIVED PROFESSIONALISM)

A toggle that runs the whole pipeline against a local model (Ollama with
qwen2.5:7b or llama-3.1-8b). Quality drops, latency spikes, but the
cabinet's confidential matter never leaves the laptop. Shipped via the
existing `LLM_BASE_URL` plumbing.

Why it matters: privacy is the #1 lawyer concern. A toggle they can flip
is a defense-day win.

Effort: 1 day (mostly testing).

---

## 3. The defense story (the slides)

Eight slides. No more. The flow that wins:

1. **Problem** — Tunisian lawyers spend X hours/week on tasks an AI can do.
   One concrete scenario from the cabinet.
2. **Why generic legal AI fails for Tunisia** — language mix
   (FR/AR/EN), code-civil-family vs Anglo-Saxon training data,
   hallucination risk on statute references.
3. **Architecture** — the diagram you already have, simplified to 7 boxes:
   intent → retrieval → reasoning → IRAC → verifier → judge → trust.
4. **The AI engineering** — feature ablation table from Action 3 above.
   Numbers, not words.
5. **The trained model** — your reranker (or classifier). Before/after
   chart with axis labels and a confusion matrix.
6. **Trust as the product** — screenshot of the trust drawer with
   verifier reason + judge candidates + citation checklist.
7. **Live demo** — 90-second timed walkthrough of one query end-to-end:
   ask in Arabic → IRAC structured answer in Arabic → trust drawer →
   succession calculator follow-up.
8. **What's next** — cabinet rollout, eval set growth to 500 tuples,
   second trained model.

A jury that sees those 8 slides walks out saying "this person is an AI
engineer, not a chatbot integrator". That is the entire 19.5 path.

---

## 4. Order of operations (4-week plan)

| Week | Focus | Deliverable |
|---|---|---|
| **W1 (now)** | Eval set + key rotation | `eval_set.jsonl` (80 rows), `run_eval_harness.py`, keys rotated, .env scrubbed |
| **W2** | Trained reranker | Notebook + `legal_reranker_v1` artifact, A/B chart vs base |
| **W3** | One killer feature (recommend succession calculator) + cabinet interview | Workflow card live in UI, `cabinet_playbook.json` committed |
| **W4** | Slides + live-demo dress rehearsal + buffer | 8 slides, demo runbook, recording of the 90-second demo as a fallback |

Hard "no" list — don't touch any of these in the final 4 weeks:
- Big refactors of `copilot_case_analysis_service.py`
- A second trained model (do it after the defense)
- Mobile UI polish
- Anything that introduces a new dependency

---

## 5. What "perfect" looks like on defense day

- Six measured numbers in a single chart, with axis labels and a date.
- One reranker / classifier you trained, with a confusion matrix.
- One Tunisian-specific feature (succession calculator) the jury can
  click during the demo.
- One screenshot of the trust drawer in Arabic with RTL.
- One paragraph in the slides on the eval methodology — "we hand-labeled
  80 tuples drawn from cabinet archives + synthetic generation, run
  weekly, this is the metric history".
- Zero hallucinated bugs in the live demo. Practice it ten times.

If those six things are true on defense day, the project is at 19.5+.
The remaining 0.5 is jury chemistry — which is not in your code.
