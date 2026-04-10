# Provider Prompt Comparison (20260407_001832 UTC)

- Winner: `grok` (Higher prompt pass rate)
- Runs per prompt: `1`
- Temperature: `0.2`

## Summary

| Provider | Model | Passed/Total | Pass Rate | Avg Score | Avg Latency (ms) | P95 Latency (ms) | Errors | Tokens |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| grok | llama-3.3-70b-versatile | 2/6 | 33.33% | 0.597 | 8591.9 | 45126.2 | 0 | 1925 |
| gemini | gemini-2.5-flash | 1/6 | 16.67% | 0.542 | 22179.6 | 93707.7 | 0 | 9982 |

## Sample Outputs

### grok
- [FAIL] summary_brief: `## Summary The commercial contract dispute revolves around a breach of agreement between two parties, XYZ Corporation and ABC Inc. The contract in question was for the supply of goods and services, with XYZ Corporation failing to deliver the agreed-upon quant...`
- [PASS] timeline_extraction: `Here's a timeline of the events based on the provided facts: 1. **2025-01-04**: A contract was signed, marking the beginning of the agreement. 2. **2025-02-11**: A notice of breach was sent, indicating that one party had failed to fulfill their obligations un...`
- [FAIL] client_email: `Subject: Update on Current Project Status Dear [Client], I wanted to take a moment to update you on the current status of our project. Everything is progressing as planned, and we are on track to meet the deadlines we previously discussed. Our team has been w...`
- [FAIL] evidence_gaps: `## Key Gaps The following are the top evidence gaps that may arise in a wrongful termination case: 1. **Lack of Documentation**: Insufficient or missing records of employee performance, disciplinary actions, and termination procedures can hinder the establish...`
- [PASS] risk_matrix: `* Cyber Attack - High - Implement robust firewall and antivirus software, and conduct regular security audits to prevent and detect potential threats. * Natural Disaster - Medium - Develop a business continuity plan, including backup systems and emergency pro...`
- [FAIL] legal_answer: `## Answer Under Tunisian labor law, the general principle is that an employer must provide notice to an employee before terminating their employment contract, except in certain circumstances. The Tunisian Labor Code (Code du Travail) outlines the conditions a...`

### gemini
- [FAIL] summary_brief: `## Case Brief: Commercial Contract Dispute ### Summary This dispute involves **[Client Name/Buyer]** and **[Opposing Party/Seller]** concerning a supply agreement for critical electronic components. [Client Name] alleges that [Opposing Party] breached the con...`
- [FAIL] timeline_extraction: `Here is a timeline of the events: * **2025-01-04:** Contract signed * **2025-02-11:** Notice of breach sent * **2025-03-01:** Payment default occurred * **2025-03-15:** Settlement offer made`
- [FAIL] client_email: `Subject: Quick Update: [Project Name/Your Project] Hi [Client Name], Just wanted to provide a quick update on [Project Name/Your Project]. We've made good progress on [specific task/phase, e.g., the initial design concepts / data analysis / content drafting]...`
- [FAIL] evidence_gaps: `A wrongful termination case hinges on proving that an employer's decision to fire an employee was illegal, discriminatory, retaliatory, or in breach of contract/public policy, rather than for a legitimate business reason. Identifying and addressing evidence g...`
- [PASS] risk_matrix: `Here is a simple risk matrix: * **Risk:** Key team member leaves unexpectedly - **Impact:** Project delays, knowledge loss, increased workload for remaining team - **Mitigation:** Cross-training, documented processes, succession planning, talent retention str...`
- [FAIL] legal_answer: `Under Tunisian labor law, the general principle is that an employer must provide a notice period before terminating an employment contract. However, there are specific circumstances under which an employer *may* be able to terminate an employment contract wit...`
