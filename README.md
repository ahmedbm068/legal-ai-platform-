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
