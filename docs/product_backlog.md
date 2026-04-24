# Product Backlog

## Epic 1: Trust and Grounding (Priority P0)
Goal: Make legal AI answers reliably grounded and auditable.

- Add citation-fidelity validation gates for core copilot intents.
	- Acceptance: citation fidelity >= 95% on eval suite.
- Add contradiction detection benchmark for case-memory workflows.
	- Acceptance: contradiction detection F1 >= 0.85.
- Add structured fallback reason taxonomy for failed reasoning paths.
	- Acceptance: 100% of fallback responses include machine-readable reason.

## Epic 2: Intent Reliability (Priority P0)
Goal: Reduce parser brittleness and intent misrouting.

- Centralize parser keyword and regex lexicon used by assistant features.
	- Acceptance: no duplicate intent keyword lists across parser/runtime modules.
- Add parser confidence scoring and low-confidence disambiguation pass.
	- Acceptance: low-confidence misroutes reduced by >= 50% vs baseline.
- Build parser regression corpus from real prompts and weak-feedback samples.
	- Acceptance: parser benchmark >= 92% intent accuracy.

## Epic 3: Multimodal Copilot (Priority P1)
Goal: Enable safe, observable image-aware assistant reasoning.

- Add attachment schema and multimodal orchestration stage.
	- Acceptance: multimodal stage appears in execution trace when attachments exist.
- Integrate vision agent with provider availability and feature-flag checks.
	- Acceptance: success and fallback paths both covered by tests.
- Preserve scanned-document fallback path with explicit user-visible reason.
	- Acceptance: fallback reason appears in response metadata.

## Epic 4: High-Reasoning Rollout Controls (Priority P1)
Goal: Convert binary toggle into safe progressive rollout.

- Add tenant allowlist and percentage rollout controls.
	- Acceptance: can target high reasoning by tenant and rollout percentage.
- Add reasoning audit telemetry fields (activated/skipped/winner/fallback/latency).
	- Acceptance: telemetry is present for 100% of high-reasoning attempts.
- Move from advisory gates to enforced gates after stability period.
	- Acceptance: clear go/no-go thresholds documented and automated.

## Epic 5: Feedback and Governance (Priority P0)
Goal: Turn user feedback into legal-risk intelligence.

- Extend feedback schema with root-cause and jurisdiction metadata.
	- Acceptance: downvotes carry structured root-cause data for triage.
- Add weekly triage and escalation workflow.
	- Acceptance: weak intents reviewed weekly with documented actions.
- Add monthly compliance-style report with risk trend lines.
	- Acceptance: report generated automatically and archived.

## Epic 6: Platform Quality and Operations (Priority P1)
Goal: Raise release confidence across backend and frontend.

- Expand automated tests for trust-critical paths.
	- Acceptance: core AI services maintain >= 80% coverage on critical paths.
- Strengthen regression runner with legal-quality gates.
	- Acceptance: release pipeline fails when trust thresholds are breached.
- Improve monitoring and incident playbooks for assistant regressions.
	- Acceptance: alert routing defined for quality and legal-risk degradations.