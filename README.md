# Legal AI Platform

AI-powered legal case management and analysis platform.

## Features

- Case management
- Document management
- Case-centric legal copilot
- Grounded retrieval and evidence display
- AI document classification
- Legal entity extraction
- Voice-ready workflow foundation

## Architecture

The system currently follows a backend-first architecture:

Frontend -> FastAPI Backend -> AI Services

Infrastructure:

- PostgreSQL
- Redis
- MinIO
- Docker

## Backend

Install Python dependencies:

```bash
pip install -r requirements.txt
```

Run the API:

```bash
uvicorn backend.main:app --reload
```

If you use an OpenAI-compatible provider such as OpenRouter, configure these env vars:

```bash
OPENAI_API_KEY=your-provider-key
LLM_BASE_URL=https://openrouter.ai/api/v1
LLM_MODEL=openai/gpt-4o-mini
SUMMARY_AGENT_MODEL=openai/gpt-4o-mini
```

If `LLM_BASE_URL` points to OpenRouter and `TRANSCRIPTION_BASE_URL` is blank, the backend intentionally skips remote speech transcription and falls back to local Whisper.

For faster remote speech transcription while keeping LLM reasoning on OpenRouter, set a dedicated transcription provider:

```bash
TRANSCRIPTION_BASE_URL=https://api.openai.com/v1
TRANSCRIPTION_API_KEY=your-openai-key
TRANSCRIPTION_MODEL=gpt-4o-mini-transcribe
```

For local Whisper fallback, you can keep speech transcription on-device:

```bash
TRANSCRIPTION_REMOTE_ENABLED=true
LOCAL_TRANSCRIPTION_MODEL=openai/whisper-base
TRANSCRIPTION_DEVICE=auto
```

If SMTP delivery is unstable in development, keep portal code fallback enabled so login codes are written to server logs:

```bash
PORTAL_ALLOW_CONSOLE_CODE_FALLBACK=true
```

Swagger:

`http://127.0.0.1:8000/docs`

## Quality Gates

Run backend tests with either command:

```bash
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py"
```

Run frontend build checks:

```bash
npm run build --prefix frontend
npm run build --prefix client-portal
```

Project hardening notes for the jury/demo discussion are documented in [docs/pfe_hardening_notes.md](/c:/Users/ahmed/Desktop/pfe.2/legal-ai-platform/docs/pfe_hardening_notes.md).

## Frontend

The Sprint 2 frontend lives in [frontend/](/c:/Users/ahmed/Desktop/pfe.2/legal-ai-platform/frontend).

Install frontend dependencies after Node.js is available locally:

```bash
cd frontend
npm install
npm run dev
```

Default frontend URL:

`http://127.0.0.1:5173`

## Client Portal

The separate client-facing intake portal lives in [client-portal/](/c:/Users/ahmed/Desktop/pfe.2/legal-ai-platform/client-portal).

Install client portal dependencies after Node.js is available locally:

```bash
cd client-portal
npm install
npm run dev
```

Default client portal URL:

`http://127.0.0.1:5174`

## Full Smoke Test

Run an end-to-end API smoke test (auth, clients, cases, documents, voice, copilot, workflow, and portal auth):

```bash
.\venv\Scripts\python.exe scripts\full_smoke_test.py --port 8021
```

## Agent Evals

Run automatic backend agent quality checks (intent + output-shape assertions) and save reports:

```bash
.\venv\Scripts\python.exe scripts\run_agent_evals.py --base-url http://127.0.0.1:8000
```

What this does:

- Creates a temporary eval user/case
- Uploads synthetic legal PDFs
- Runs prompts from `scripts/evals/default_eval_suite.json`
- Writes JSON + Markdown reports to `advancement/evals/`

If you want to evaluate your own existing case:

```bash
.\venv\Scripts\python.exe scripts\run_agent_evals.py --case-id 11 --email you@example.com --password your-password
```

Fast iteration mode (run a subset):

```bash
.\venv\Scripts\python.exe scripts\run_agent_evals.py --spawn-server --limit 6 --min-pass-rate 0
```

Current default eval suite size: `43` prompts (`scripts/evals/default_eval_suite.json`).

## Regression Checks

Run compile + smoke + eval gates in one command:

```bash
.\venv\Scripts\python.exe scripts\run_regression_checks.py --eval-base-url http://127.0.0.1:8000
```

Optional skips:

```bash
.\venv\Scripts\python.exe scripts\run_regression_checks.py --skip-smoke
```

## Development Defaults

`docker-compose.yml` is configured for fast local development. PostgreSQL, MinIO, and n8n use clearly marked development defaults that should be overridden with environment variables outside local demos. See `.env.example` and [docs/pfe_hardening_notes.md](/c:/Users/ahmed/Desktop/pfe.2/legal-ai-platform/docs/pfe_hardening_notes.md).

## Feedback Loop (Thumbs Up/Down)

The copilot UI now sends per-message feedback to `/ai/feedback` (thumbs up/down).
Use this weekly report command to identify weak intents and tune prompts/agents:

```bash
.\venv\Scripts\python.exe scripts\generate_feedback_report.py --weeks 8
```

Output files are written to:

- `advancement/feedback/feedback_report_<timestamp>.json`
- `advancement/feedback/feedback_report_<timestamp>.md`

## Advancement Auto-Log

On every GitHub push, a workflow auto-creates a markdown file in `advancement/` with what changed in that push.

Manual generation (local):

```bash
python scripts/generate_advancement_log.py --before <old_sha> --after <new_sha> --branch <branch_name>
```
