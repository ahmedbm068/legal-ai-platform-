# Agent Eval Report (20260330_152359 UTC)

- Base URL: `http://127.0.0.1:8031`
- Case ID: `16`
- Suite: `scripts\evals\default_eval_suite.json`
- Passed: `6/6` (100.0%)

## Results

### summary_case_paragraph_only_01 - PASS
- Prompt: `Summarize case #16`
- Intent: `summarize_case`
- Confidence: `high`
- Duration: `988.8 ms`
- [PASS] intent_match: expected summarize_case, got summarize_case
- [PASS] target_type_match: expected case, got case
- [PASS] scope_match: expected case, got case
- [PASS] contains:Document 1 (: must contain 'Document 1 ('
- [PASS] contains:Document 2 (: must contain 'Document 2 ('
- [PASS] not_contains:Main Issues:: must not contain 'Main Issues:'
- [PASS] not_contains:Key Dates:: must not contain 'Key Dates:'
- [PASS] not_contains:Legal Risks:: must not contain 'Legal Risks:'
- [PASS] not_contains:Risk Assessment:: must not contain 'Risk Assessment:'
- [PASS] not_contains:Recommended Next Steps:: must not contain 'Recommended Next Steps:'
- [PASS] not_contains:Practical Next Steps:: must not contain 'Practical Next Steps:'
- [PASS] max_answer_chars: chars=727, max=2800
- Answer preview: `Case 16 (Eval Case 6884) currently includes 2 document(s). The file set mainly includes contract, legal_letter. The main parties across these documents are Master Service Agreement between Atlas Retail Group SARL, Nova Logistics Tunisia SARL, Atlas Retail Group SARL

Document 1 (eval_contract.pdf): This document is a c`

### summary_case_paragraph_only_02 - PASS
- Prompt: `Give me a concise case summary for case #16 in paragraph form only.`
- Intent: `summarize_case`
- Confidence: `high`
- Duration: `95.7 ms`
- [PASS] intent_match: expected summarize_case, got summarize_case
- [PASS] target_type_match: expected case, got case
- [PASS] scope_match: expected case, got case
- [PASS] not_contains:Main Issues:: must not contain 'Main Issues:'
- [PASS] not_contains:Legal Risks:: must not contain 'Legal Risks:'
- [PASS] not_contains:Risk Assessment:: must not contain 'Risk Assessment:'
- Answer preview: `Case 16 (Eval Case 6884) currently includes 2 document(s). The file set mainly includes contract, legal_letter. The main parties across these documents are Master Service Agreement between Atlas Retail Group SARL, Nova Logistics Tunisia SARL, Atlas Retail Group SARL

Document 1 (eval_contract.pdf): This document is a c`

### summary_case_paragraph_only_03 - PASS
- Prompt: `Make a resume of case #16.`
- Intent: `summarize_case`
- Confidence: `high`
- Duration: `145.5 ms`
- [PASS] intent_match: expected summarize_case, got summarize_case
- [PASS] target_type_match: expected case, got case
- [PASS] scope_match: expected case, got case
- [PASS] not_contains:Main Issues:: must not contain 'Main Issues:'
- [PASS] not_contains:Key Dates:: must not contain 'Key Dates:'
- Answer preview: `Case 16 (Eval Case 6884) currently includes 2 document(s). The file set mainly includes contract, legal_letter. The main parties across these documents are Master Service Agreement between Atlas Retail Group SARL, Nova Logistics Tunisia SARL, Atlas Retail Group SARL

Document 1 (eval_contract.pdf): This document is a c`

### summary_case_paragraph_only_04 - PASS
- Prompt: `I need a short recap for case #16.`
- Intent: `summarize_case`
- Confidence: `high`
- Duration: `97.5 ms`
- [PASS] intent_match: expected summarize_case, got summarize_case
- [PASS] target_type_match: expected case, got case
- [PASS] scope_match: expected case, got case
- Answer preview: `Case 16 (Eval Case 6884) currently includes 2 document(s). The file set mainly includes contract, legal_letter. The main parties across these documents are Master Service Agreement between Atlas Retail Group SARL, Nova Logistics Tunisia SARL, Atlas Retail Group SARL

Document 1 (eval_contract.pdf): This document is a c`

### summary_case_paragraph_only_05 - PASS
- Prompt: `Provide a practical overview of case #16.`
- Intent: `summarize_case`
- Confidence: `high`
- Duration: `102.6 ms`
- [PASS] intent_match: expected summarize_case, got summarize_case
- [PASS] target_type_match: expected case, got case
- [PASS] scope_match: expected case, got case
- Answer preview: `Case 16 (Eval Case 6884) currently includes 2 document(s). The file set mainly includes contract, legal_letter. The main parties across these documents are Master Service Agreement between Atlas Retail Group SARL, Nova Logistics Tunisia SARL, Atlas Retail Group SARL

Document 1 (eval_contract.pdf): This document is a c`

### summary_case_paragraph_only_06 - PASS
- Prompt: `Summarize all documents in case #16 with one paragraph per document.`
- Intent: `summarize_case`
- Confidence: `high`
- Duration: `97.8 ms`
- [PASS] intent_match: expected summarize_case, got summarize_case
- [PASS] target_type_match: expected case, got case
- [PASS] scope_match: expected case, got case
- [PASS] contains:Document 1 (: must contain 'Document 1 ('
- [PASS] contains:Document 2 (: must contain 'Document 2 ('
- Answer preview: `Case 16 (Eval Case 6884) currently includes 2 document(s). The file set mainly includes contract, legal_letter. The main parties across these documents are Master Service Agreement between Atlas Retail Group SARL, Nova Logistics Tunisia SARL, Atlas Retail Group SARL

Document 1 (eval_contract.pdf): This document is a c`
