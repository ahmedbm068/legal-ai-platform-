# Legal Risk Triage Process

## Purpose
Define how copilot quality issues are triaged, escalated, and resolved with legal-risk awareness.

## Inputs
- Weekly feedback report from scripts/generate_feedback_report.py.
- Regression and eval outputs from scripts/run_regression_checks.py and scripts/run_agent_evals.py.
- Manual lawyer comments from user acceptance sessions.

## Root Cause Taxonomy
- unclear_prompt
- wrong_jurisdiction
- missing_evidence
- generic_answer
- wrong_legal_area
- ungrounded
- other

## Weekly Cadence
- Monday: engineering triage of weak intents and downvote root causes.
- Tuesday: rotating lawyer SME review for escalated legal-risk items.
- Wednesday to Thursday: implement and verify fixes.
- Friday: publish short status summary and carry-forward risks.

## Escalation Rules
Escalate same day when any of the following is true:
- Intent up_rate drops below 0.60 over a weekly window.
- A downvote cites wrong jurisdiction or ungrounded legal advice.
- Citation/grounding regression gates fail for production-bound changes.

## SLA Targets
- High risk: mitigation decision within 24 hours.
- Medium risk: fix plan within 3 business days.
- Low risk: backlog for next sprint with owner and ETA.

## Required Ticket Fields
- intent
- risk_level
- root_cause
- jurisdiction
- user_impact
- mitigation_plan
- owner
- due_date

## Interim Ownership Model
- Triage owner: AI engineering lead.
- Legal review owner: rotating lawyer SME (bi-weekly).
- Override owner for high-risk release decisions: product + engineering leadership.

## Exit Criteria for an Escalation
- Regression tests pass.
- Relevant eval prompts pass.
- Triage ticket includes root-cause resolution notes.
- Reviewer confirms residual risk level (low, medium, high).
