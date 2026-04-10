# Provider Prompt Comparison (20260407_002226 UTC)

- Winner: `grok` (Higher prompt pass rate)
- Runs per prompt: `1`
- Temperature: `0.2`

## Summary

| Provider | Model | Passed/Total | Pass Rate | Avg Score | Avg Latency (ms) | P95 Latency (ms) | Errors | Tokens |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| grok | llama-3.3-70b-versatile | 6/6 | 100.00% | 1.000 | 8446.3 | 44624.8 | 0 | 1906 |
| gemini | gemini-2.5-flash | 3/6 | 50.00% | 0.764 | 21573.5 | 90863.3 | 0 | 8715 |

## Sample Outputs

### grok
- [PASS] summary_brief: `## Summary The commercial contract dispute revolves around a breach of agreement between two parties, XYZ Corporation and ABC Inc. The contract in question was for the supply of goods, with XYZ Corporation acting as the supplier and ABC Inc. as the buyer. The...`
- [PASS] timeline_extraction: `Here's a timeline of the events based on the provided facts: 1. **2025-01-04**: A contract was signed, marking the beginning of the agreement. 2. **2025-02-11**: A notice of breach was sent, indicating that one party had failed to fulfill their obligations un...`
- [PASS] client_email: `Subject: Project Update and Progress Dear [Client], I wanted to take a moment to update you on the current status of our project. We have made significant progress over the past week and are on track to meet our deadlines. Our team has been working diligently...`
- [PASS] evidence_gaps: `## Key Gaps The following are the top evidence gaps that may arise in a wrongful termination case: 1. **Lack of Documentation**: Insufficient or missing records of employee performance, disciplinary actions, and termination procedures. 2. **Inconsistent Appli...`
- [PASS] risk_matrix: `* Cyber Attack - High - Implement robust firewall systems and regular security updates to prevent breaches. * Natural Disaster - Medium - Develop a business continuity plan and maintain backup systems in a secure, off-site location. * Supply Chain Disruption...`
- [PASS] legal_answer: `## Answer Under Tunisian labor law, the general principle is that an employer must provide notice to an employee before terminating their employment contract. The notice period varies depending on the length of service and the type of contract. However, there...`

### gemini
- [FAIL] summary_brief: `Here is a concise case brief: **Summary** Our client, Acme Corp, entered into a supply agreement with Beta Solutions for critical manufacturing components. Beta Solutions delivered the components significantly late, and a substantial portion were non-conformi...`
- [FAIL] timeline_extraction: `Here is a timeline of the events: * **2025-01-04:** Contract signed * **2025-02-11:** Notice of breach sent * **2025-03-01:** Payment default occurred * **2025-03-15:** Settlement offer made`
- [FAIL] client_email: `Subject: [Project Name] - Quick Status Update Hi [Client Name], Hope you're having a good week. Just a quick update on the [Project Name] project. We've made good progress on [mention a specific recent task or phase, e.g., the initial design concepts / data a...`
- [PASS] evidence_gaps: `A wrongful termination case hinges on proving that an employer's decision to terminate an employee was illegal (e.g., discriminatory, retaliatory, or in breach of contract/public policy) rather than for a legitimate business reason. Evidence gaps often arise...`
- [PASS] risk_matrix: `Here is a simple risk matrix: * **Risk:** Data breach due to cyberattack - **Impact:** Loss of customer trust, regulatory fines, financial loss - **Mitigation:** Implement strong encryption, multi-factor authentication, regular security audits, employee train...`
- [PASS] legal_answer: `Under Tunisian labor law, the general principle for the termination of an indefinite-term employment contract is that a notice period is required. However, there are specific circumstances where an employer *may* be able to terminate an employee without provi...`
