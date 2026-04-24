# Definition of Done (DoD) for Legal AI Features

A feature is considered done only when all gates in the selected tier are met.

## Tier 1: Developer Done
- Code is committed and peer reviewed.
- Changes follow backend and frontend project structure.
- Observability is included for new behavior (logs or trace metadata).
- API contracts are backward compatible unless a documented breaking change is approved.

## Tier 2: Product Done
- Feature works end to end for expected workflows.
- Error and fallback paths are implemented and user-visible.
- Existing behavior for unaffected intents remains stable.
- Documentation is updated for feature behavior, limits, and fallback conditions.

## Tier 3: Legal AI Done
- Outputs include evidence grounding metadata when applicable.
- Jurisdiction context is preserved for legal reasoning flows.
- Unsafe or weakly grounded outputs degrade safely with explicit fallback messaging.
- Feedback collection includes structured legal-risk metadata (`root_cause`, `legal_domain`, `jurisdiction`) for downvote analysis.

## Tier 4: Release Done
- Regression checks pass (tests, evals, build checks).
- Advisory quality thresholds are reviewed before release:
	- citation fidelity target >= 95%
	- unsupported claim rate target <= 2%
	- weak-intent alert threshold up_rate < 70%
- Feature flag rollout policy is defined (safe default, staged rollout, kill switch).
- Rollback plan is documented for high-risk behavior.

## Governance Cadence (Interim Model)
- Weekly triage owner: AI engineering lead.
- Bi-weekly legal review: rotating lawyer SME until a dedicated reviewer is assigned.
- High-risk escalations: same-day decision by product/engineering leadership.

## Required Evidence Before Merge
- Relevant tests added or updated.
- Traceable change notes in PR description: what changed, why, and fallback behavior.
- Updated docs for user-facing behavior.

## Exemptions
- Any exemption to Tier 3 or Tier 4 requires explicit written approval from engineering lead and product lead.