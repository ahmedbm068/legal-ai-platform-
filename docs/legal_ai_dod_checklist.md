# Legal AI DoD Checklist

Use this checklist before releasing any copilot feature.

## Developer Done
- [ ] Code reviewed.
- [ ] Backward compatibility verified.
- [ ] Logs or execution trace updated for new behavior.

## Product Done
- [ ] Happy path and fallback path validated.
- [ ] API schema and frontend types aligned.
- [ ] User-facing behavior documented.

## Legal AI Done
- [ ] Evidence grounding is present where applicable.
- [ ] Jurisdiction context is preserved.
- [ ] Unsafe or weakly grounded output degrades safely.
- [ ] Feedback supports root-cause tagging for downvotes.

## Release Done
- [ ] Regression checks passed.
- [ ] Advisory quality thresholds reviewed.
- [ ] Feature flag and kill switch strategy documented.
- [ ] Rollback steps documented.

## Advisory Quality Thresholds
- Citation fidelity target: >= 95%.
- Unsupported claim rate target: <= 2%.
- Weak intent alert: up_rate < 70%.
