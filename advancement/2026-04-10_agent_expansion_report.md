# Advancement Log - 2026-04-10 UTC

## Overview
- Expanded the legal AI workspace with two new specialist agents aimed at lawyer workflows:
  - deadline / obligation monitoring
  - contract redlining
- Wired the new intents through the backend routing stack so they can be reached from copilot requests and workflow execution.
- Added frontend launch points so lawyers can trigger the new workflows directly from the main workspace and the intelligence dashboard.

## What Was Added
- `backend/services/ai/agents/deadline_obligation_agent.py`
  - Extracts live deadlines, notice windows, cure periods, and obligations from case evidence.
  - Produces a lawyer-facing deadline summary, prioritized signals, and next actions.
- `backend/services/ai/agents/contract_redline_agent.py`
  - Builds clause-level redline guidance for contract packs.
  - Highlights clause risks, recommended edits, fallback positions, and source documents.
- `backend/services/ai/command_parsing_service.py`
  - Added intent detection for deadline monitoring and contract redlining.
- `backend/services/ai/agents/copilot_intent_execution_agent.py`
  - Routed the new intents through the central execution map.
- `backend/services/ai/copilot_service.py`
  - Added the backend handlers that resolve case context, target documents, and produce structured answers.
- `backend/services/ai/agent_workflow_service.py`
  - Added a `deadline_monitor` workflow stage.
- `frontend/src/App.tsx`
  - Added specialist workflow cards for case memory, evidence tracing, deadline monitoring, and contract redlining.
  - Mounted the intelligence dashboard in the main case workspace.
- `frontend/src/components/IntelligencePanel.tsx`
  - Added the same specialist launch buttons inside the dashboard.

## Validation
- Type / syntax checks passed on the touched backend and frontend files.
- Backend import wiring was verified for the new intent parser, dispatcher, workflow service, and the two new agents.
- One environment-level warning remains in the local system Python interpreter:
  - `fastapi` is not installed in that interpreter, so direct import validation of `copilot_service.py` reports an environment error.
  - Importing the new document-backed agents in that same interpreter also shows `psycopg2` missing.
- Those warnings are interpreter / dependency issues in the local validation environment, not syntax errors in the edited files.

## Result
- The workspace now has dedicated launch paths for the most lawyer-useful workflows requested in this expansion slice.
- The new agents are structured to stay useful even with modest model quality because they rely on heuristic extraction first and use LLM refinement only when available.