# Agent Eval Report (20260413_133344 UTC)

- Base URL: `http://127.0.0.1:8036`
- Case ID: `16`
- Suite: `scripts\evals\default_eval_suite.json`
- Passed: `38/43` (88.4%)

## Results

### summary_case_paragraph_only_01 - FAIL
- Prompt: `Summarize case #16`
- Intent: `summarize_case`
- Confidence: `high`
- Duration: `1892.2 ms`
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
- [PASS] max_answer_chars: chars=1924, max=2800
- Answer preview: `Case #16 resume:

Overall Case Overview:
The case currently contains 2 documents: a contract and a legal letter. Main parties detected include Master Service Agreement between Atlas Retail Group SARL, Nova Logistics Tunisia SARL, and Atlas Retail Group SARL. Termination rights are triggered by material breach, and paym`

### summary_case_paragraph_only_02 - PASS
- Prompt: `Give me a concise case summary for case #16 in paragraph form only.`
- Intent: `summarize_case`
- Confidence: `high`
- Duration: `1047.9 ms`
- [PASS] intent_match: expected summarize_case, got summarize_case
- [PASS] target_type_match: expected case, got case
- [PASS] scope_match: expected case, got case
- [PASS] not_contains:Main Issues:: must not contain 'Main Issues:'
- [PASS] not_contains:Legal Risks:: must not contain 'Legal Risks:'
- [PASS] not_contains:Risk Assessment:: must not contain 'Risk Assessment:'
- Answer preview: `Case #16 resume:

Overall Case Overview:
The case involves a contract and a legal letter, with main issues including termination rights triggered by material breach, payment terms of net 30 from invoice date, and a notice of breach and payment dispute. Nova Logistics Tunisia SARL disputes the material breach characteri`

### summary_case_paragraph_only_03 - PASS
- Prompt: `Make a resume of case #16.`
- Intent: `summarize_case`
- Confidence: `high`
- Duration: `1077.1 ms`
- [PASS] intent_match: expected summarize_case, got summarize_case
- [PASS] target_type_match: expected case, got case
- [PASS] scope_match: expected case, got case
- [PASS] not_contains:Main Issues:: must not contain 'Main Issues:'
- [PASS] not_contains:Key Dates:: must not contain 'Key Dates:'
- Answer preview: `Case #16 resume:

Overall Case Overview:
The case includes a Master Service Agreement and a legal letter, with termination rights triggered by material breach and repeated SLA failure, payment terms of net 30 from invoice date, and Nova disputing material breach characterization. The active counterparties are Master Se`

### summary_case_paragraph_only_04 - PASS
- Prompt: `I need a short recap for case #16.`
- Intent: `summarize_case`
- Confidence: `high`
- Duration: `961.6 ms`
- [PASS] intent_match: expected summarize_case, got summarize_case
- [PASS] target_type_match: expected case, got case
- [PASS] scope_match: expected case, got case
- Answer preview: `Case #16 resume:

Overall Case Overview:
The case involves a contract dispute between Atlas Retail Group SARL and Nova Logistics Tunisia SARL, with issues related to termination rights triggered by material breach, payment terms, and notice of breach and payment dispute. The active counterparties are Master Service Agr`

### summary_case_paragraph_only_05 - PASS
- Prompt: `Provide a practical overview of case #16.`
- Intent: `summarize_case`
- Confidence: `high`
- Duration: `1574.7 ms`
- [PASS] intent_match: expected summarize_case, got summarize_case
- [PASS] target_type_match: expected case, got case
- [PASS] scope_match: expected case, got case
- Answer preview: `Case #16 resume:

Overall Case Overview:
The case involves a contract and a legal letter, with main issues including termination rights triggered by material breach, payment terms of net 30 from invoice date, and a notice of breach and payment dispute. Nova disputes the material breach characterization and proposes cor`

### summary_case_paragraph_only_06 - FAIL
- Prompt: `Summarize all documents in case #16 with one paragraph per document.`
- Intent: `summarize_case`
- Confidence: `high`
- Duration: `5002.3 ms`
- [PASS] intent_match: expected summarize_case, got summarize_case
- [PASS] target_type_match: expected case, got case
- [PASS] scope_match: expected case, got case
- [FAIL] contains:Document 1 (: must contain 'Document 1 ('
- [FAIL] contains:Document 2 (: must contain 'Document 2 ('
- Answer preview: `Case #16 summary:

- Case posture: The case involves a contract dispute between Atlas Retail Group SARL and Nova Logistics Tunisia SARL, with issues related to termination rights, payment terms, and breach characterization. Nova disputes the material breach characterization and proposes corrective steps.`

### summary_case_paragraph_only_07 - PASS
- Prompt: `Case #16 summary only, no bullets.`
- Intent: `summarize_case`
- Confidence: `high`
- Duration: `11250.1 ms`
- [PASS] intent_match: expected summarize_case, got summarize_case
- [PASS] target_type_match: expected case, got case
- [PASS] scope_match: expected case, got case
- [PASS] not_contains:Main Issues:: must not contain 'Main Issues:'
- [PASS] not_contains:Risk Assessment:: must not contain 'Risk Assessment:'
- [PASS] not_contains:Recommended Next Steps:: must not contain 'Recommended Next Steps:'
- Answer preview: `Case #16 summary:

- Case posture: The case involves a contract and a legal letter, with Nova disputing the characterization of a material breach and proposing corrective steps, while the contract terms indicate termination rights triggered by material breach and repeated SLA failure, with payment terms set at net 30 f`

### summary_case_paragraph_only_08 - PASS
- Prompt: `brief synopsis for case #16`
- Intent: `summarize_case`
- Confidence: `high`
- Duration: `12106.0 ms`
- [PASS] intent_match: expected summarize_case, got summarize_case
- [PASS] target_type_match: expected case, got case
- [PASS] scope_match: expected case, got case
- Answer preview: `Case #16 resume:

Overall Case Overview:
The case involves a Master Service Agreement between Atlas Retail Group SARL and Nova Logistics Tunisia SARL, with detected issues including termination rights triggered by material breach, payment terms of net 30 from invoice date, and a notice of breach and payment dispute. No`

### summary_case_paragraph_only_09_no_risks - PASS
- Prompt: `Summarize case #16. Summary only, no risks and no dates.`
- Intent: `summarize_case`
- Confidence: `high`
- Duration: `11080.5 ms`
- [PASS] intent_match: expected summarize_case, got summarize_case
- [PASS] target_type_match: expected case, got case
- [PASS] scope_match: expected case, got case
- [PASS] not_contains:Main Issues:: must not contain 'Main Issues:'
- [PASS] not_contains:Legal Risks:: must not contain 'Legal Risks:'
- [PASS] not_contains:Risk Assessment:: must not contain 'Risk Assessment:'
- [PASS] not_contains:Key Dates:: must not contain 'Key Dates:'
- Answer preview: `Case #16 resume:

Overall Case Overview:
The case involves a Master Service Agreement between Atlas Retail Group SARL and Nova Logistics Tunisia SARL, with a dispute over termination rights and payment terms. Nova disputes the characterization of material breach and proposes corrective steps. The active counterparties `

### summary_plus_risks_01 - PASS
- Prompt: `For case #16, provide a concise summary and identify potential risks, citing relevant evidence and practical next steps.`
- Intent: `summarize_and_analyze_risks_case`
- Confidence: `high`
- Duration: `12063.5 ms`
- [PASS] intent_match: expected summarize_and_analyze_risks_case, got summarize_and_analyze_risks_case
- [PASS] target_type_match: expected case, got case
- [PASS] scope_match: expected case, got case
- [PASS] contains:Summary:: must contain 'Summary:'
- [PASS] contains:Risk Assessment:: must contain 'Risk Assessment:'
- [PASS] contains:Practical Next Steps:: must contain 'Practical Next Steps:'
- [PASS] not_contains:<CASE_ID>: must not contain '<CASE_ID>'
- [PASS] not_contains:What success looks like: must not contain 'What success looks like'
- [PASS] not_contains:Optimize prompt:: must not contain 'Optimize prompt:'
- [PASS] not_contains:Sources appea: must not contain 'Sources appea'
- [PASS] not_contains:email for case #<: must not contain 'email for case #<'
- Answer preview: `Case #16 summary and risk assessment:

Summary:
The case involves a Master Service Agreement between Atlas Retail Group SARL and Nova Logistics Tunisia SARL, with a dispute over termination terms and payment obligations. Nova Logistics Tunisia SARL disputes the material breach characterization and proposes corrective s`

### summary_plus_risks_02 - PASS
- Prompt: `Summarize case #16 and then analyze the legal risks.`
- Intent: `summarize_and_analyze_risks_case`
- Confidence: `high`
- Duration: `11264.8 ms`
- [PASS] intent_match: expected summarize_and_analyze_risks_case, got summarize_and_analyze_risks_case
- [PASS] target_type_match: expected case, got case
- [PASS] scope_match: expected case, got case
- [PASS] contains:Summary:: must contain 'Summary:'
- [PASS] contains:Risk Assessment:: must contain 'Risk Assessment:'
- Answer preview: `Case #16 summary and risk assessment:

Summary:
The case includes a contract and a legal letter, with main issues centered on termination rights triggered by material breach, payment terms, and notice of breach. Nova Logistics Tunisia SARL disputes the material breach characterization and proposes corrective steps.

Ev`

### summary_plus_risks_03 - PASS
- Prompt: `I want summary plus risk review for case #16.`
- Intent: `summarize_and_analyze_risks_case`
- Confidence: `high`
- Duration: `11244.8 ms`
- [PASS] intent_match: expected summarize_and_analyze_risks_case, got summarize_and_analyze_risks_case
- [PASS] target_type_match: expected case, got case
- [PASS] scope_match: expected case, got case
- Answer preview: `Case #16 summary and risk assessment:

Summary:
The case involves a contract dispute between Atlas Retail Group SARL and Nova Logistics Tunisia SARL, with issues related to termination terms, payment obligations, and breach characterization. The contract includes termination rights triggered by material breach and repe`

### summary_plus_risks_04 - PASS
- Prompt: `Case #16: concise brief + risk assessment + next legal steps.`
- Intent: `summarize_and_analyze_risks_case`
- Confidence: `high`
- Duration: `12267.2 ms`
- [PASS] intent_match: expected summarize_and_analyze_risks_case, got summarize_and_analyze_risks_case
- [PASS] target_type_match: expected case, got case
- [PASS] scope_match: expected case, got case
- [PASS] contains:Risk Assessment:: must contain 'Risk Assessment:'
- Answer preview: `Case #16 summary and risk assessment:

Summary:
The case involves a contract dispute between Atlas Retail Group SARL and Nova Logistics Tunisia SARL, with issues related to termination terms, payment terms, and breach characterization. Nova disputes the material breach characterization and proposes corrective steps.

E`

### summary_plus_risks_05 - PASS
- Prompt: `For case #16, summarize and detect dangers.`
- Intent: `summarize_and_analyze_risks_case`
- Confidence: `high`
- Duration: `11284.1 ms`
- [PASS] intent_match: expected summarize_and_analyze_risks_case, got summarize_and_analyze_risks_case
- [PASS] target_type_match: expected case, got case
- [PASS] scope_match: expected case, got case
- Answer preview: `Case #16 summary and risk assessment:

Summary:
The case includes a contract and a legal letter, with main issues centered around termination rights triggered by material breach, payment terms, and notice of breach and payment dispute, while Nova Logistics Tunisia SARL disputes the material breach characterization.

Ev`

### summary_plus_risks_06 - PASS
- Prompt: `Please provide a short case summary and risk mapping for case #16.`
- Intent: `summarize_and_analyze_risks_case`
- Confidence: `high`
- Duration: `11185.0 ms`
- [PASS] intent_match: expected summarize_and_analyze_risks_case, got summarize_and_analyze_risks_case
- [PASS] target_type_match: expected case, got case
- [PASS] scope_match: expected case, got case
- Answer preview: `Case #16 summary and risk assessment:

Summary:
The parties are engaged in a dispute over termination terms, with Nova Logistics Tunisia SARL disputing the characterization of a material breach and proposing corrective steps. The contract has a net 30 payment term from the invoice date, and termination rights are trigg`

### risk_only_01 - FAIL
- Prompt: `Analyze risks for case #16.`
- Intent: `analyze_risks_case`
- Confidence: `high`
- Duration: `12394.9 ms`
- [PASS] intent_match: expected analyze_risks_case, got analyze_risks_case
- [PASS] target_type_match: expected case, got case
- [PASS] scope_match: expected case, got case
- [FAIL] contains:Detected legal risks for case: must contain 'Detected legal risks for case'
- Answer preview: `Top legal risks for case 16 (ranked high to low):

1. HIGH | Legal | Nova disputes material breach characterization and proposes corrective steps | Sources: eval_notice.pdf, eval_contract.pdf
2. HIGH | Legal | Termination rights are triggered by material breach and repeated SLA failure | Sources: eval_notice.pdf, eval_`

### risk_only_02_single - FAIL
- Prompt: `Give me only one risk for case #16.`
- Intent: `analyze_risks_case`
- Confidence: `high`
- Duration: `11002.0 ms`
- [PASS] intent_match: expected analyze_risks_case, got analyze_risks_case
- [PASS] target_type_match: expected case, got case
- [PASS] scope_match: expected case, got case
- [FAIL] contains:Detected legal risks for case: must contain 'Detected legal risks for case'
- [PASS] max_bullets: bullets=0, max=1
- Answer preview: `Top legal risks for case 16 (ranked high to low):

1. HIGH | Legal | Nova disputes material breach characterization and proposes corrective steps | Sources: eval_notice.pdf, eval_contract.pdf`

### risk_only_03_three - PASS
- Prompt: `Top 3 risks for case #16.`
- Intent: `analyze_risks_case`
- Confidence: `high`
- Duration: `11215.9 ms`
- [PASS] intent_match: expected analyze_risks_case, got analyze_risks_case
- [PASS] target_type_match: expected case, got case
- [PASS] scope_match: expected case, got case
- [PASS] max_bullets: bullets=0, max=3
- Answer preview: `Top legal risks for case 16 (ranked high to low):

1. HIGH | Legal | Nova disputes material breach characterization and proposes corrective steps | Sources: eval_notice.pdf, eval_contract.pdf
2. HIGH | Legal | Termination rights are triggered by material breach and repeated SLA failure | Sources: eval_notice.pdf, eval_`

### risk_only_04 - PASS
- Prompt: `What is the biggest legal exposure in case #16?`
- Intent: `analyze_risks_case`
- Confidence: `high`
- Duration: `12116.3 ms`
- [PASS] intent_match: expected analyze_risks_case, got analyze_risks_case
- [PASS] target_type_match: expected case, got case
- [PASS] scope_match: expected case, got case
- Answer preview: `Top legal risks for case 16 (ranked high to low):

1. HIGH | Legal | Nova disputes material breach characterization and proposes corrective steps | Sources: eval_notice.pdf, eval_contract.pdf
2. HIGH | Legal | Termination rights are triggered by material breach and repeated SLA failure | Sources: eval_notice.pdf, eval_`

### risk_only_05 - PASS
- Prompt: `List 2 risks for case #16`
- Intent: `analyze_risks_case`
- Confidence: `high`
- Duration: `11057.5 ms`
- [PASS] intent_match: expected analyze_risks_case, got analyze_risks_case
- [PASS] target_type_match: expected case, got case
- [PASS] scope_match: expected case, got case
- [PASS] max_bullets: bullets=0, max=2
- Answer preview: `Top legal risks for case 16 (ranked high to low):

1. HIGH | Legal | Nova disputes material breach characterization and proposes corrective steps | Sources: eval_notice.pdf, eval_contract.pdf
2. HIGH | Legal | Termination rights are triggered by material breach and repeated SLA failure | Sources: eval_notice.pdf, eval_`

### deadlines_01 - FAIL
- Prompt: `List deadlines for case #16.`
- Intent: `list_deadlines_case`
- Confidence: `low`
- Duration: `4974.4 ms`
- [PASS] intent_match: expected list_deadlines_case, got list_deadlines_case
- [PASS] target_type_match: expected case, got case
- [PASS] scope_match: expected case, got case
- [FAIL] contains:Detected: must contain 'Detected'
- Answer preview: `I could not find enough evidence in the indexed documents.`

### deadlines_02 - PASS
- Prompt: `Top 2 deadlines for case #16`
- Intent: `list_deadlines_case`
- Confidence: `low`
- Duration: `24.1 ms`
- [PASS] intent_match: expected list_deadlines_case, got list_deadlines_case
- [PASS] target_type_match: expected case, got case
- [PASS] scope_match: expected case, got case
- [PASS] max_bullets: bullets=0, max=2
- Answer preview: `I could not find enough evidence in the indexed documents.`

### deadlines_03 - PASS
- Prompt: `Any due dates and notice periods in case #16?`
- Intent: `list_deadlines_case`
- Confidence: `low`
- Duration: `24.7 ms`
- [PASS] intent_match: expected list_deadlines_case, got list_deadlines_case
- [PASS] target_type_match: expected case, got case
- [PASS] scope_match: expected case, got case
- Answer preview: `I could not find enough evidence in the indexed documents.`

### deadlines_04 - PASS
- Prompt: `Show me 3 deadlines in case #16`
- Intent: `list_deadlines_case`
- Confidence: `low`
- Duration: `28.6 ms`
- [PASS] intent_match: expected list_deadlines_case, got list_deadlines_case
- [PASS] target_type_match: expected case, got case
- [PASS] scope_match: expected case, got case
- [PASS] max_bullets: bullets=0, max=3
- Answer preview: `I could not find enough evidence in the indexed documents.`

### deadlines_05 - PASS
- Prompt: `Deadline audit for case #16`
- Intent: `list_deadlines_case`
- Confidence: `low`
- Duration: `32.3 ms`
- [PASS] intent_match: expected list_deadlines_case, got list_deadlines_case
- [PASS] target_type_match: expected case, got case
- [PASS] scope_match: expected case, got case
- Answer preview: `I could not find enough evidence in the indexed documents.`

### timeline_01 - PASS
- Prompt: `Build timeline for case #16.`
- Intent: `build_timeline_case`
- Confidence: `medium`
- Duration: `29.2 ms`
- [PASS] intent_match: expected build_timeline_case, got build_timeline_case
- [PASS] target_type_match: expected case, got case
- [PASS] scope_match: expected case, got case
- [PASS] min_confidence: expected >= medium, got medium
- Answer preview: `Case #16 strict chronology (Eval Case 6884):

Dated Events:
None`

### timeline_02 - PASS
- Prompt: `Chronology of events in case #16`
- Intent: `build_timeline_case`
- Confidence: `medium`
- Duration: `29.8 ms`
- [PASS] intent_match: expected build_timeline_case, got build_timeline_case
- [PASS] target_type_match: expected case, got case
- [PASS] scope_match: expected case, got case
- Answer preview: `Case #16 strict chronology (Eval Case 6884):

Dated Events:
None`

### timeline_03 - PASS
- Prompt: `Create a chronological sequence for case #16.`
- Intent: `build_timeline_case`
- Confidence: `medium`
- Duration: `24.5 ms`
- [PASS] intent_match: expected build_timeline_case, got build_timeline_case
- [PASS] target_type_match: expected case, got case
- [PASS] scope_match: expected case, got case
- Answer preview: `Case #16 strict chronology (Eval Case 6884):

Dated Events:
None`

### timeline_04 - PASS
- Prompt: `case #16 timeline please`
- Intent: `build_timeline_case`
- Confidence: `medium`
- Duration: `21.8 ms`
- [PASS] intent_match: expected build_timeline_case, got build_timeline_case
- [PASS] target_type_match: expected case, got case
- [PASS] scope_match: expected case, got case
- Answer preview: `Case #16 strict chronology (Eval Case 6884):

Dated Events:
None`

### draft_email_01 - PASS
- Prompt: `Draft client email for case #16.`
- Intent: `draft_client_email_case`
- Confidence: `high`
- Duration: `12535.2 ms`
- [PASS] intent_match: expected draft_client_email_case, got draft_client_email_case
- [PASS] target_type_match: expected case, got case
- [PASS] scope_match: expected case, got case
- [PASS] contains:Subject:: must contain 'Subject:'
- Answer preview: `Subject: Update on Eval Case 6884

Dear Client,

We are currently reviewing the Master Service Agreement and legal letter related to your case, Eval Case 6884, in the jurisdiction of Tunisia. The main issues in this case involve termination rights, payment terms, and breach disputes between Atlas Retail Group SARL and `

### draft_email_02 - PASS
- Prompt: `Prepare a client update email for case #16`
- Intent: `draft_client_email_case`
- Confidence: `high`
- Duration: `17316.8 ms`
- [PASS] intent_match: expected draft_client_email_case, got draft_client_email_case
- [PASS] target_type_match: expected case, got case
- [PASS] scope_match: expected case, got case
- Answer preview: `Subject: Update on Eval Case 6884

Dear Client,

We are reviewing the contract and legal letter between Atlas Retail Group SARL and Nova Logistics Tunisia SARL, focusing on termination rights, payment terms, and dispute resolution under Tunisian law. The core dispute revolves around the termination term, where terminat`

### draft_email_03 - PASS
- Prompt: `Write a concise negotiation update mail for case #16.`
- Intent: `draft_client_email_case`
- Confidence: `high`
- Duration: `17554.2 ms`
- [PASS] intent_match: expected draft_client_email_case, got draft_client_email_case
- [PASS] target_type_match: expected case, got case
- [PASS] scope_match: expected case, got case
- Answer preview: `Subject: Update on Eval Case 6884

Dear Client,

We are reviewing the documents related to your case, including a contract and a legal letter, which indicate potential legal risks under Tunisian law. The core dispute focuses on termination terms and payment conditions. Our team is assessing the contractual baseline, ob`

### compare_docs_01 - PASS
- Prompt: `Compare documents in case #16.`
- Intent: `compare_case_documents`
- Confidence: `high`
- Duration: `5821.1 ms`
- [PASS] intent_match: expected compare_case_documents, got compare_case_documents
- [PASS] target_type_match: expected case, got case
- [PASS] scope_match: expected case, got case
- [PASS] min_confidence: expected >= medium, got high
- Answer preview: `Comparison overview for case 16:
- eval_contract.pdf: type=contract, dates=0, risks=3, summary=Overview:
This document is a contract or contract-related record. The main named parties are Master Service Agreement between Atlas Retail Group SARL, Nova Logistics Tunisia SARL. The document includes termination or notice-r`

### compare_docs_02 - PASS
- Prompt: `Find contradictions across documents in case #16.`
- Intent: `compare_case_documents`
- Confidence: `high`
- Duration: `4977.8 ms`
- [PASS] intent_match: expected compare_case_documents, got compare_case_documents
- [PASS] target_type_match: expected case, got case
- [PASS] scope_match: expected case, got case
- Answer preview: `Comparison overview for case 16:
- eval_contract.pdf: type=contract, dates=0, risks=3, summary=Overview:
This document is a contract or contract-related record. The main named parties are Master Service Agreement between Atlas Retail Group SARL, Nova Logistics Tunisia SARL. The document includes termination or notice-r`

### compare_docs_03 - PASS
- Prompt: `Document comparison for case #16`
- Intent: `compare_case_documents`
- Confidence: `high`
- Duration: `5925.2 ms`
- [PASS] intent_match: expected compare_case_documents, got compare_case_documents
- [PASS] target_type_match: expected case, got case
- [PASS] scope_match: expected case, got case
- Answer preview: `Comparison overview for case 16:
- eval_contract.pdf: type=contract, dates=0, risks=3, summary=Overview:
This document is a contract or contract-related record. The main named parties are Master Service Agreement between Atlas Retail Group SARL, Nova Logistics Tunisia SARL. The document includes termination or notice-r`

### booking_review_01 - PASS
- Prompt: `Review booking status for case #16.`
- Intent: `review_booking_case`
- Confidence: `low`
- Duration: `20.0 ms`
- [PASS] intent_match: expected review_booking_case, got review_booking_case
- [PASS] target_type_match: expected case, got case
- [PASS] scope_match: expected case, got case
- Answer preview: `No consultation booking details are available for this case yet.`

### booking_review_02 - PASS
- Prompt: `Do we have any consultation request for case #16?`
- Intent: `review_booking_case`
- Confidence: `low`
- Duration: `19.1 ms`
- [PASS] intent_match: expected review_booking_case, got review_booking_case
- [PASS] target_type_match: expected case, got case
- [PASS] scope_match: expected case, got case
- Answer preview: `No consultation booking details are available for this case yet.`

### optimize_prompt_01 - PASS
- Prompt: `Optimize prompt: draft a client update about payment dispute for case #16`
- Intent: `optimize_prompt`
- Confidence: `high`
- Duration: `1736.4 ms`
- [PASS] intent_match: expected optimize_prompt, got optimize_prompt
- [PASS] target_type_match: expected case, got case
- [PASS] scope_match: expected global, got global
- [PASS] contains:Optimized prompt:: must contain 'Optimized prompt:'
- Answer preview: `Optimized prompt: For case #16, draft a client update regarding the payment dispute, including relevant case details and proposed next steps.

Notes: Added case #16 reference for context, and specified the inclusion of case details and next steps to enhance the response.`

### ask_case_01 - PASS
- Prompt: `What is the payment structure in case #16?`
- Intent: `ask_case`
- Confidence: `low`
- Duration: `70.1 ms`
- [PASS] intent_match: expected ask_case, got ask_case
- [PASS] target_type_match: expected case, got case
- [PASS] scope_match: expected case, got case
- [PASS] not_contains:<CASE_ID>: must not contain '<CASE_ID>'
- [PASS] not_contains:What success looks like: must not contain 'What success looks like'
- [PASS] not_contains:Optimize prompt:: must not contain 'Optimize prompt:'
- Answer preview: `I could not find enough evidence in the indexed documents.`

### ask_case_02 - PASS
- Prompt: `What evidence supports a breach argument in case #16?`
- Intent: `ask_case`
- Confidence: `low`
- Duration: `67.2 ms`
- [PASS] intent_match: expected ask_case, got ask_case
- [PASS] target_type_match: expected case, got case
- [PASS] scope_match: expected case, got case
- Answer preview: `I could not find enough evidence in the indexed documents.`

### ask_case_03 - PASS
- Prompt: `Can you explain this case #16 in plain legal terms?`
- Intent: `ask_case`
- Confidence: `low`
- Duration: `62.7 ms`
- [PASS] intent_match: expected ask_case, got ask_case
- [PASS] target_type_match: expected case, got case
- [PASS] scope_match: expected case, got case
- Answer preview: `I could not find enough evidence in the indexed documents.`

### memory_followup_01 - PASS
- Prompt: `Analyze risks for case #16`
- Intent: `analyze_risks_case`
- Confidence: `high`
- Duration: `10145.2 ms`
- [PASS] intent_match: expected analyze_risks_case, got analyze_risks_case
- [PASS] target_type_match: expected case, got case
- [PASS] scope_match: expected case, got case
- Answer preview: `Top legal risks for case 16 (ranked high to low):

1. HIGH | Legal | Nova disputes material breach characterization and proposes corrective steps | Sources: eval_notice.pdf, eval_contract.pdf
2. HIGH | Legal | Termination rights are triggered by material breach and repeated SLA failure | Sources: eval_notice.pdf, eval_`

### memory_followup_02 - PASS
- Prompt: `just one`
- Intent: `analyze_risks_case`
- Confidence: `high`
- Duration: `11109.7 ms`
- [PASS] intent_match: expected analyze_risks_case, got analyze_risks_case
- [PASS] scope_match: expected case, got case
- [PASS] max_bullets: bullets=0, max=1
- Answer preview: `Top legal risks for case 16 (ranked high to low):

1. HIGH | Legal | Nova disputes material breach characterization and proposes corrective steps | Sources: eval_notice.pdf, eval_contract.pdf`
