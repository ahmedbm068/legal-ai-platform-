# Eval Snapshot — Day 6 (2026-05-09)

**Sprint:** Week 1 · Day 6
**Snapshot type:** Baseline freeze (live run not executed — backend not running at snapshot time)
**Suite:** `scripts/evals/default_eval_suite.json`
**Last live run:** 2026-04-13 13:40 UTC (report: `agent_eval_report_20260413_134039`)

---

## Baseline Metrics (last live run)

| Metric | Value |
|---|---|
| Case ID | 15 |
| Total assertions | 5 |
| Passed | 1 |
| Failed | 4 |
| **Pass rate** | **20.0%** |
| Avg duration | ~258 ms |

---

## Failure Analysis

### 1 · `summary_case_paragraph_only_01` — FAIL
- Root cause: Summarizer returns `Case #15 resume:` preamble before content; doesn't emit `Document 1 (` / `Document 2 (` citation tokens
- Secondary: still emits `Recommended Next Steps:` (forbidden substring)
- Fix target: summarization_prompt → enforce `Document N (filename)` citation format, remove next-steps section

### 2 · `summary_case_paragraph_only_06` — FAIL
- Same citation format failure as above
- Model outputs flat bullet summary instead of per-document paragraphs

### 3 · `risk_only_01` — FAIL
- Expected substring: `Detected legal risks for case` — model uses `Top legal risks for case` instead
- Intent matched correctly; formatting mismatch only

### 4 · `risk_only_02_single` — FAIL (details from prior report)
- Similar formatting prefix mismatch

### Passing
- `summary_case_paragraph_only_02` — PASS (no strict substring checks, only forbidden checks)

---

## Prompt Freeze State (as of this snapshot)

| File | Version | SHA256 (first 16) | Status |
|---|---|---|---|
| `chronology_prompt.md` | 1.0.0 | `66D1C54C208E6A1F…` | frozen |
| `summarization_prompt.md` | 1.0.0 | `27626F08AAE09F5A…` | frozen |

Lock file: `backend/services/ai/agents/PROMPT_LOCK.json`

---

## Action Items Before Next Eval

1. **Fix citation format** — summarization_prompt must produce `Document 1 (filename.pdf)` tokens. Add explicit example line.
2. **Remove next-steps trigger** — ensure `Recommended Next Steps:` never appears; the forbidden check is now in eval.
3. **Align risk prefix** — either update eval assertion to accept `Top legal risks` OR update prompt to use `Detected legal risks for case`.
4. **Target:** ≥ 80% pass rate before any prompt version bump (per PROMPT_LOCK policy).

---

## How to Run Next Eval

```bash
cd legal-ai-platform
python scripts/run_agent_evals.py \
  --case-id 15 \
  --email admin@example.com \
  --password <password> \
  --output-dir advancement/evals
```

Or with server spawn:
```bash
python scripts/run_agent_evals.py --spawn-server --case-id 15 --email ...
```
