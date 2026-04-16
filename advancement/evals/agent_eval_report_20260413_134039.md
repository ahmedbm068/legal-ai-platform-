# Agent Eval Report (20260413_134039 UTC)

- Base URL: `http://127.0.0.1:8043`
- Case ID: `15`
- Suite: `scripts\evals\default_eval_suite.json`
- Passed: `1/5` (20.0%)

## Results

### summary_case_paragraph_only_01 - FAIL
- Prompt: `Summarize case #15`
- Intent: `summarize_case`
- Confidence: `medium`
- Duration: `618.4 ms`
- [PASS] intent_match: expected summarize_case, got summarize_case
- [PASS] target_type_match: expected case, got case
- [PASS] scope_match: expected case, got case
- [FAIL] contains:Document 1 (: must contain 'Document 1 ('
- [FAIL] contains:Document 2 (: must contain 'Document 2 ('
- [PASS] not_contains:Main Issues:: must not contain 'Main Issues:'
- [PASS] not_contains:Key Dates:: must not contain 'Key Dates:'
- [PASS] not_contains:Legal Risks:: must not contain 'Legal Risks:'
- [PASS] not_contains:Risk Assessment:: must not contain 'Risk Assessment:'
- [FAIL] not_contains:Recommended Next Steps:: must not contain 'Recommended Next Steps:'
- [PASS] not_contains:Practical Next Steps:: must not contain 'Practical Next Steps:'
- [PASS] max_answer_chars: chars=1973, max=2800
- Answer preview: `Case #15 resume:

Overall Case Overview:
Case 15 - Eval Case 1410 The case currently contains 2 document(s). Detected document types: contract, legal_letter. Main parties detected: Master Service Agreement between Atlas Retail Group SARL, Nova Logistics Tunisia SARL, Atlas Retail Group SARL, Atlas, Nova. The active cou`

### summary_case_paragraph_only_06 - FAIL
- Prompt: `Summarize all documents in case #15 with one paragraph per document.`
- Intent: `summarize_case`
- Confidence: `medium`
- Duration: `100.0 ms`
- [PASS] intent_match: expected summarize_case, got summarize_case
- [PASS] target_type_match: expected case, got case
- [PASS] scope_match: expected case, got case
- [FAIL] contains:Document 1 (: must contain 'Document 1 ('
- [FAIL] contains:Document 2 (: must contain 'Document 2 ('
- Answer preview: `Case #15 summary:

- Case posture: Case 15 - Eval Case 1410 The case currently contains 2 document(s). Detected document types: contract, legal_letter. Main parties detected: Master Service Agreement between Atlas Retail Group SARL, Nova Logistics Tunisia SARL, Atlas Retail Group SARL, Atlas, Nova.`

### risk_only_01 - FAIL
- Prompt: `Analyze risks for case #15.`
- Intent: `analyze_risks_case`
- Confidence: `medium`
- Duration: `97.9 ms`
- [PASS] intent_match: expected analyze_risks_case, got analyze_risks_case
- [PASS] target_type_match: expected case, got case
- [PASS] scope_match: expected case, got case
- [FAIL] contains:Detected legal risks for case: must contain 'Detected legal risks for case'
- Answer preview: `Top legal risks for case 15 (ranked high to low):

1. HIGH | Legal | Nova disputes material breach characterization and proposes corrective steps | Sources: eval_notice.pdf, eval_contract.pdf
2. HIGH | Legal | Termination rights are triggered by material breach and repeated SLA failure | Sources: eval_notice.pdf, eval_`

### risk_only_02_single - FAIL
- Prompt: `Give me only one risk for case #15.`
- Intent: `analyze_risks_case`
- Confidence: `medium`
- Duration: `87.8 ms`
- [PASS] intent_match: expected analyze_risks_case, got analyze_risks_case
- [PASS] target_type_match: expected case, got case
- [PASS] scope_match: expected case, got case
- [FAIL] contains:Detected legal risks for case: must contain 'Detected legal risks for case'
- [PASS] max_bullets: bullets=0, max=1
- Answer preview: `Top legal risks for case 15 (ranked high to low):

1. HIGH | Legal | Nova disputes material breach characterization and proposes corrective steps | Sources: eval_notice.pdf, eval_contract.pdf`

### deadlines_01 - PASS
- Prompt: `List deadlines for case #15.`
- Intent: `list_deadlines_case`
- Confidence: `high`
- Duration: `26.8 ms`
- [PASS] intent_match: expected list_deadlines_case, got list_deadlines_case
- [PASS] target_type_match: expected case, got case
- [PASS] scope_match: expected case, got case
- [PASS] contains:Detected: must contain 'Detected'
- Answer preview: `Detected deadlines and time-related obligations for case 15:

Deadlines / Due Dates:
- April 3, 2026 (Corrective action report due) - eval_notice.pdf

Notice Periods:
- March 29, 2026 (Notice date) - eval_notice.pdf`
