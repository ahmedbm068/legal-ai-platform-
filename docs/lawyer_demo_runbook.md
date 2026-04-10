# Lawyer Demo Runbook (New Case + 8 Documents)

This runbook is designed for a realistic teacher demo focused on the lawyer workflow only.

## 1) Start Services

From project root:

```powershell
# Backend
C:/Users/ahmed/AppData/Local/Programs/Python/Python313/python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload
```

In another terminal:

```powershell
# Frontend app
cd frontend
npm install
npm run dev
```

## 2) Use the Prepared Demo Documents

The generated PDF pack is here:

- docs/test-data/lawyer-demo-pack

Files available:

1. 01_master_service_agreement.pdf
2. 02_notice_of_breach.pdf
3. 03_counterparty_response.pdf
4. 04_kpi_dashboard_extract_q1.pdf
5. 05_invoice_reconciliation_sheet.pdf
6. 06_internal_legal_memo.pdf
7. 07_without_prejudice_settlement_offer.pdf
8. 08_client_call_transcript_summary.pdf

## 3) Create a New Lawyer Case in UI

Recommended demo values:

- Client name: Atlas Retail Group SARL
- Case title: Atlas v Nova Logistics - SLA Breach Q1 2026
- Practice area: Commercial Litigation
- Priority: High
- Status: Open

## 4) Upload More Than 5 Documents

Upload all 8 PDFs from docs/test-data/lawyer-demo-pack in one batch or in two waves.

Suggested order for narrative clarity:

1. MSA contract
2. Breach notice
3. Counterparty response
4. KPI dashboard
5. Invoice reconciliation
6. Internal legal memo
7. Settlement offer
8. Call transcript summary

Wait for all documents to finish processing/indexing before querying Copilot.

## 5) Copilot Prompt Script (Demo Sequence)

Use these prompts in order to show full value:

1. Summarize this case in 8 bullet points with contractual context.
2. Build a strict chronology of events with dates and source documents.
3. Identify top legal and operational risks, ranked high to low.
4. What evidence is strongest for material breach and what is weak?
5. Draft a negotiation strategy for the next 10 days.
6. Give strategic case insights and an action plan for partner review.
7. Propose a without-prejudice settlement structure with fallback options.
8. Draft a concise email to the client explaining current posture.

## 6) Expected Outputs to Showcase

- Cross-document reasoning from contract + notices + KPI + finance docs
- Risk ranking with concrete references
- Strategy and negotiation options
- Insight-style synthesis and next actions
- Client-facing communication draft

## 7) Optional Full Smoke Validation Before Demo

If you want a backend confidence pass before live presentation:

```powershell
C:/Users/ahmed/AppData/Local/Programs/Python/Python313/python.exe scripts/full_smoke_test.py --base-url http://127.0.0.1:8000 --wait-seconds 25
```

## 8) Fast Presentation Flow (6-8 Minutes)

1. Create client and case.
2. Upload all 8 docs.
3. Show processed documents list.
4. Run prompts 1, 3, 6, and 8 (high impact set).
5. Close with action plan and settlement strategy.
