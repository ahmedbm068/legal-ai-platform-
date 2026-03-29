# Agent Test Runbook (Fast)

## 1) Create one case
Example title: `Atlas vs Nova Logistics - SLA Dispute`

## 2) Upload docs (same case)
1. `01_master_service_agreement_pdf_ready.md` (exported as PDF)
2. `02_notice_of_breach_and_payment_dispute_pdf_ready.md` (exported as PDF)
3. `03_counterparty_response_pdf_ready.md` (exported as PDF)

## 3) Upload voice
- Record yourself reading `04_voice_intake_script_for_transcription.txt` or upload an audio file of it.
- Wait for transcription status `completed`.
- Click `Create intake request`.

## 4) Copilot prompts to test each agent
- `Summarize case #<CASE_ID>`
- `List deadlines for case #<CASE_ID>`
- `Analyze risks for case #<CASE_ID>`
- `Build timeline for case #<CASE_ID>`
- `Review booking for case #<CASE_ID>`
- `Compare documents in case #<CASE_ID>`
- `Draft client email for case #<CASE_ID>`
- `Optimize prompt: draft a negotiation email for case #<CASE_ID>`
- `What external legal trends might affect warehouse SLA disputes in Tunisia for case #<CASE_ID>`

## 5) What success looks like
- Sources appear in Evidence tab.
- At least one answer includes external web references (when external research is enabled).
- Workflow tab produces stage traces and verified summary.
- Intake tab shows extracted client + urgency + schedule from transcript.
- Intelligence tab shows type, entities, summary, and redacted preview.

