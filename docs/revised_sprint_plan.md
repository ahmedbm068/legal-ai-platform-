# Revised Sprint Plan

This roadmap reflects the current repository state on 2026-03-28.

## Current Position

The project is currently in **Sprint 1: Backend Stabilization** of the revised plan.

Why:

- the backend foundation already exists
- document intelligence already exists in prototype form
- case-aware AI behavior already exists in partial form
- the project still needs dependency cleanup, infra alignment, and test hardening before frontend and voice work

## Revised Sprint Order

### Sprint 1. Backend Stabilization

Goal:

Make the current backend reliable enough to support frontend and voice features.

Main work:

- fix missing dependencies
- align config and Docker services
- reduce startup fragility
- add `.env.example`
- prepare test strategy

Exit criteria:

- backend installs cleanly in a fresh environment
- required local services are documented and available
- config no longer blocks startup unnecessarily

### Sprint 2. Case Workspace v1

Goal:

Turn the backend into a real application with a visible workflow.

Main work:

- login screen
- case list
- case detail page
- document upload/listing
- summary panels
- copilot chat panel

Exit criteria:

- a user can log in, open a case, upload a document, and view AI outputs in the UI

### Sprint 3. Voice Intake & Interaction v1

Goal:

Introduce voice as a first-class input to the legal workflow.

Main work:

- browser recording or audio upload
- speech-to-text transcription
- transcript persistence
- transcript attached to case
- transcript viewer in the case workspace
- basic extraction from transcripts

Exit criteria:

- a user can add a voice recording to a case and get a saved transcript back inside the app

### Sprint 4. Case-Centric Intelligence

Goal:

Move from document-level outputs to case-level structured reasoning.

Main work:

- timeline generation
- party-role mapping
- obligation extraction
- relation mapping across documents and transcripts
- stronger case summary synthesis

Exit criteria:

- the system can summarize a case using multiple artifacts together, not just one document

### Sprint 5. Semantic Retrieval & RAG Upgrade

Goal:

Improve retrieval quality and broaden evidence coverage.

Main work:

- search across documents and transcripts
- better chunking and metadata filtering
- cleaner source formatting
- retrieval tuning
- optional legal corpus ingestion for statutes and case law

Exit criteria:

- the copilot can answer grounded questions using both case documents and transcripts with visible citations

### Sprint 6. Trust Layer / Proof-First Verification

Goal:

Make outputs safer and more defendable.

Main work:

- explicit refusal rules
- verifier step before final answer release
- contradiction checks
- evidence mapping for claims
- better citation display

Exit criteria:

- the system can refuse weak answers and explain what evidence was or was not found

### Sprint 7. Multi-Agent Legal AI

Goal:

Replace centralized service logic with explicit specialized agent roles.

Main work:

- document analyzer agent
- retrieval agent
- case reasoning agent
- drafting agent
- verifier agent
- orchestration flow and shared state

Exit criteria:

- a complex legal request is handled through a traceable multi-step agent workflow

### Sprint 8. Trainable AI Models

Goal:

Add focused ML components that strengthen the product in measurable ways.

Main work:

- intent classifier
- retrieval reranker
- case risk scoring
- voice anti-spoof if still required and feasible

Exit criteria:

- at least one trainable model is integrated into runtime behavior and evaluated with project metrics

### Sprint 9. Final Productization & Soutenance Preparation

Goal:

Polish the system for demo, reporting, and defense.

Main work:

- bug fixing
- UI polish
- benchmark results
- seeded demo data
- architecture diagrams
- screenshots and defense material
- end-to-end walkthrough preparation

Exit criteria:

- the app is demoable end to end and the technical story matches the implementation

## Recommended Immediate Next Step

Finish Sprint 1, then start Sprint 2 with:

- frontend app scaffold
- authentication flow
- case dashboard
- case detail workspace

That gives the project a visible product surface before voice is added in Sprint 3.
