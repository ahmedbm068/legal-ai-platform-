# PFE Hardening Notes

This project intentionally keeps a fast local-demo setup while documenting the controls expected in a professional legal AI system. These notes turn the main jury/audit questions into explicit engineering decisions.

## 1. Test and Quality Gates

The repository has deterministic backend tests for legal trust, agent contracts, retrieval helpers, calendar sync, feedback reporting, and command parsing.

Recommended commands:

```bash
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py"
npm run build --prefix frontend
npm run build --prefix client-portal
```

`pytest` is included in `requirements.txt` so the common jury/reviewer command works. The tests are also compatible with Python `unittest`, which gives a fallback with no extra test framework behavior.

## 2. Maintainability of Large Modules

Some modules are intentionally large because the project evolved from prototype to integrated platform during PFE delivery:

- `backend/services/ai/copilot_service.py`: legacy orchestration and case-workflow implementation.
- `frontend/src/App.tsx`: preserved classic workspace during the routed workspace rollout.
- `client-portal/src/App.tsx`: client intake, portal auth, status, and upload flows in one deployable portal.

This is not presented as the final architecture. The maintainability plan is:

1. Keep current behavior stable through tests and regression scripts.
2. Move legacy orchestration into smaller use-case services by intent family: summarization, drafting, evidence tracing, calendar, and client updates.
3. Retire the classic monolith UI only after the routed workspace reaches feature parity.
4. Split client portal auth, intake, case status, and document upload into focused components.
5. Use the existing tests as safety rails during each extraction.

This is a controlled technical-debt item rather than hidden complexity.

Refactor started:

- Client portal presentation helpers now live in `client-portal/src/portalPresentation.tsx`.
- Classic workspace storage, chat-session, formatting, and local helper utilities now live in `frontend/src/legacyWorkspaceSupport.ts`.
- Copilot intent, role, chat, and high-reasoning constants now live in `backend/services/ai/copilot_service_constants.py`.

These extractions reduce file size without changing runtime behavior, because the original entry modules still own the same workflow state and call paths.

## 3. AI Artifacts and Reproducibility

The local FAISS index, FAISS metadata, and reranker checkpoint are demo/runtime artifacts. They are useful for offline demonstration, but they should not be treated as source code.

Current stance:

- Tracked artifacts support a self-contained PFE demo.
- `.gitignore` blocks future local FAISS snapshots and model checkpoints from accidental commits.
- The source corpus and scripts remain the reproducibility path.

Professional target:

- Store large model and vector artifacts in object storage or a release registry.
- Keep only metadata manifests in git, including artifact name, version, source corpus, checksum, and rebuild command.
- Rebuild local legal corpora with `scripts/import_legal_codes_corpus.py` when source PDFs change.

## 4. Database Evolution

`backend/database/schema_sync.py` is a pragmatic bootstrap layer for a fast-moving student project. It creates missing tables/columns and gracefully falls back from pgvector to FAISS when the extension is unavailable.

Professional target:

- Introduce Alembic migrations as the source of truth for schema changes.
- Keep `schema_sync.py` only as a local-demo compatibility guard or remove it after migrations are stable.
- Add migration checks to the regression command before release.

## 5. Development Defaults and Secret Management

`docker-compose.yml` uses local development defaults for PostgreSQL, MinIO, and n8n so the jury demo can start quickly. These values are explicitly marked as development defaults.

Professional target:

- Override all secrets through environment variables or a secret manager.
- Rotate `SECRET_KEY`, `PORTAL_SECRET_KEY`, MinIO credentials, database password, SMTP credentials, and webhook secrets outside local demos.
- Keep `.env.example` safe and non-sensitive.

## 6. How To Present This In The Defense

Suggested wording:

> The project is intentionally demo-friendly locally, but the repository documents the production controls: runnable test gates, legal trust validation, tenant scoping, artifact reproducibility, migration plan, and secret override policy. The remaining large modules are known consolidation points with a staged refactor plan, not unexamined design gaps.
