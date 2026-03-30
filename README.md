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

## Advancement Auto-Log

On every GitHub push, a workflow auto-creates a markdown file in `advancement/` with what changed in that push.

Manual generation (local):

```bash
python scripts/generate_advancement_log.py --before <old_sha> --after <new_sha> --branch <branch_name>
```
