"""
Generate the May 2026 Dashboard Test Pack.

Case: TechVenture SARL v CloudAxis Solutions — SaaS Platform Dispute
Jurisdiction: Tunisia
Dates: April-May 2026 (includes upcoming deadlines in May for dashboard testing)

Run from project root:
    python scripts/generate_may2026_demo_pack.py [--output-dir docs/test-data/may2026-demo-pack] [--overwrite]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Reuse the PDF builder from the existing generator
_scripts_dir = Path(__file__).resolve().parent
sys.path.insert(0, str(_scripts_dir))
from generate_lawyer_demo_pack import build_simple_pdf  # noqa: E402


def demo_documents() -> list[tuple[str, str]]:
    return [
        # ── 00 ── Case upload guide ─────────────────────────────────────────
        (
            "00_case_upload_guide.pdf",
            """
MAY 2026 DASHBOARD TEST PACK — UPLOAD GUIDE
Case: TechVenture SARL v CloudAxis Solutions
Matter type: SaaS Platform Breach and Data Loss Dispute
Jurisdiction: Tunisia (French-law influenced)
Client: TechVenture SARL
Status: Open — High Priority
Created: May 1, 2026

UPLOAD ORDER
1. 01_saas_platform_agreement.pdf
2. 02_incident_report_data_loss.pdf
3. 03_formal_breach_notice.pdf
4. 04_cloudaxis_response.pdf
5. 05_financial_impact_assessment.pdf
6. 06_it_forensics_extract.pdf
7. 07_regulatory_notification_draft.pdf
8. 08_internal_risk_memo.pdf
9. 09_settlement_term_sheet.pdf
10. 10_case_strategy_update.pdf

KEY DATES FOR DASHBOARD TESTING
- May 6, 2026: CloudAxis final response deadline
- May 8, 2026: Data restoration deadline
- May 9, 2026: Executive negotiation call (AI-suggested)
- May 12, 2026: Mediation session in Tunis
- May 15, 2026: TechVenture regulatory filing deadline
- May 20, 2026: Arbitration trigger date if mediation fails
- June 2, 2026: Settlement acceptance deadline

AI DEMO PROMPTS
1. Summarize the case in 8 bullets with contract, breach, data loss, and risk issues.
2. Build a strict chronology from first outage to current status.
3. Identify contradictions between TechVenture and CloudAxis positions.
4. What are the strongest and weakest pieces of evidence for TechVenture?
5. Extract every deadline and create calendar reminders.
6. Rank the legal risks from high to low with evidence basis.
7. Draft a without-prejudice settlement counter-proposal for May 9.
8. What regulatory obligations arise from the confirmed data loss?
9. Prepare a partner review memo with recommended next actions.
10. What documents are still missing that should be requested urgently?
""",
        ),
        # ── 01 ── SaaS Platform Agreement ───────────────────────────────────
        (
            "01_saas_platform_agreement.pdf",
            """
SAAS PLATFORM SERVICES AGREEMENT
Agreement ID: SPSA-TV-CA-2025-011
Effective Date: October 15, 2025
Parties: TechVenture SARL (Customer) and CloudAxis Solutions SARL (Provider)
Governing law: Tunisia

1) Scope of Services
CloudAxis provides TechVenture with a cloud-based enterprise resource planning
platform including financial management, HR, payroll processing, customer data
storage, and business intelligence reporting modules.

2) Service Level Commitments
- Platform availability: 99.7 percent measured monthly (excluding maintenance)
- Planned maintenance window: Sundays 02:00 to 05:00 maximum 4 hours per month
- Incident response P1 (critical): acknowledgment within 30 minutes, resolution
  plan within 2 hours, full resolution within 8 business hours
- Data backup: automated daily incremental, weekly full backup retained 90 days
- Recovery Time Objective (RTO): 4 hours for P1 outages
- Recovery Point Objective (RPO): maximum 24 hours data loss

3) Data Protection Obligations
- CloudAxis must not transfer TechVenture data outside Tunisia without written consent
- CloudAxis must notify TechVenture of any data breach within 24 hours of discovery
- All personal data processed under this agreement is subject to Tunisian data
  protection law Act 63-2004 and any subsequent amendments
- CloudAxis must maintain ISO 27001 certification or equivalent throughout the term

4) Commercial Terms
- Monthly subscription fee: 34,500 TND excluding VAT
- Overuse compute charges: 280 TND per additional 100 GB per month
- Professional services: 850 TND per day on request
- Payment terms: Net 30 from valid invoice
- TechVenture may withhold disputed amounts with written reasons within 15 days
  of invoice receipt

5) Business Continuity and Liability
- CloudAxis must maintain a tested disaster recovery plan reviewed annually
- Liability cap: six months of subscription fees for direct damages
- Cap does not apply to data breach, intentional misconduct, or regulatory
  penalties caused by CloudAxis failure
- Force-majeure clause excludes planned infrastructure migrations

6) Termination
- Either party may terminate for material breach with 10 business days written notice
- TechVenture may terminate immediately if a data breach affects customer personal data
- Transition assistance: CloudAxis must provide 60 days of data export support
  at no additional charge after termination notice

7) Dispute Resolution
- Senior management negotiation within 5 business days of written notice
- If unresolved: mediation in Tunis within 20 calendar days
- If mediation fails: binding arbitration under CATO rules
""",
        ),
        # ── 02 ── Incident Report ────────────────────────────────────────────
        (
            "02_incident_report_data_loss.pdf",
            """
CRITICAL INCIDENT REPORT — PLATFORM OUTAGE AND DATA LOSS
Report ID: IR-TECHVENTURE-2026-04-28
Prepared by: TechVenture IT and Operations
Date: April 28, 2026

Incident Classification: P1 CRITICAL — Confirmed Data Loss

Incident Summary
On April 26, 2026 at 14:20, TechVenture's CloudAxis ERP platform became
unavailable. CloudAxis confirmed on April 27 at 09:15 that the outage was caused
by a failed infrastructure migration that was not disclosed to TechVenture in
advance. CloudAxis further confirmed on April 28 at 11:00 that approximately
72 hours of incremental backup data was not recoverable due to a snapshot error
during the migration.

Timeline
- April 26, 14:20: Platform access lost — TechVenture staff report login failure
- April 26, 14:35: P1 ticket opened with CloudAxis helpdesk
- April 26, 15:10: CloudAxis acknowledged ticket, stated investigating
- April 26, 18:45: CloudAxis identified root cause as infrastructure migration
- April 26, 18:45: TechVenture notified for first time about the migration
- April 27, 09:15: CloudAxis confirmed unplanned migration triggered the outage
- April 27, 22:00: Partial platform access restored for read-only operations
- April 28, 11:00: CloudAxis confirmed backup snapshot error causing data loss
- April 28, 14:00: Full platform access restored but data gap confirmed

Data Loss Impact
- Affected period: April 25, 14:00 to April 26, 14:00 (approx. 24 hours of data)
- Modules affected: payroll entries, customer orders, financial postings
- Payroll batch processing for April 25 requires full re-entry
- 847 customer transaction records may need manual reconciliation
- 3 financial postings for April 25 are unrecoverable from CloudAxis backups

SLA Breach Analysis
- Platform was unavailable for approximately 23 hours 40 minutes
- SLA target: 99.7% monthly availability (max downtime ~2.2 hours per month)
- Actual April downtime to date: approximately 24 hours (critical SLA breach)
- P1 resolution SLA of 8 business hours was exceeded by approximately 14 hours
- Data RPO breach: confirmed 24+ hours data loss against 24-hour RPO commitment

Preliminary Business Impact
- Payroll team: 14 hours of manual re-entry work estimated
- Finance team: 3 unrecoverable postings require manual reconstruction
- Customer operations: 847 transaction records require reconciliation
- IT overtime: 31 hours of emergency response time logged
- Estimated internal response cost: 28,400 TND
""",
        ),
        # ── 03 ── Formal Breach Notice ──────────────────────────────────────
        (
            "03_formal_breach_notice.pdf",
            """
FORMAL NOTICE OF MATERIAL BREACH AND DATA PROTECTION VIOLATION
Reference: NOB-TV-2026-04-30
Date: April 30, 2026
From: TechVenture SARL
To: CloudAxis Solutions SARL

Subject: Material breach of SPSA-TV-CA-2025-011 — SLA failure, undisclosed
infrastructure migration, and confirmed data loss.

1) Breach Allegations

A) Undisclosed Infrastructure Migration
CloudAxis performed an infrastructure migration on April 26, 2026 without
providing TechVenture advance written notice as required under the business
continuity provisions of the agreement. This constitutes a material breach of
the transparency and planned maintenance obligations.

B) SLA Availability Breach
Platform unavailability of 23 hours 40 minutes in April 2026 represents a
critical and material breach of the 99.7% monthly availability commitment.
The contracted maximum monthly downtime is approximately 2.2 hours.

C) P1 Response SLA Breach
CloudAxis exceeded the 8 business hour P1 resolution commitment by approximately
14 hours. No escalation to a senior engineer occurred within the contractual
response escalation window.

D) Data Loss — RPO Breach
CloudAxis confirmed that approximately 24 hours of incremental backup data is
unrecoverable. This directly breaches the 24-hour RPO commitment and the data
backup obligations under the agreement.

E) Late Data Breach Notification
CloudAxis first confirmed data loss on April 28, 2026 — more than 24 hours after
the incident began. The contractual notification obligation requires notification
within 24 hours of discovery. TechVenture may have regulatory reporting obligations
as a result of this delay.

2) Cure Demands
TechVenture demands the following by May 6, 2026:
- Full written root cause analysis with technical remediation plan
- Complete restoration of all recoverable data with verification report
- Confirmation of ISO 27001 certification status
- Updated disaster recovery plan and test results dated within 90 days
- Revised and corrected April invoice removing SLA credit obligations

3) Financial Reservation
TechVenture reserves the right to withhold the disputed April invoice pending
resolution and to recover all documented internal response costs, payroll
re-entry costs, customer reconciliation costs, and any regulatory filing costs.
Estimated direct costs currently stand at 28,400 TND with further amounts pending.

4) Regulatory Notification Notice
Given the confirmed data loss affecting customer transaction data, TechVenture's
compliance team is assessing whether regulatory notification is required under
Tunisian data protection law. CloudAxis must not destroy any logs, backups, or
infrastructure records related to the April 26 incident pending this assessment.

5) Reservation of Rights
TechVenture reserves all contractual rights including termination if cure is not
completed by May 6, 2026. This notice does not waive any rights or remedies.

Deadline for CloudAxis full response: May 6, 2026 at 17:00 Tunis time.
""",
        ),
        # ── 04 ── CloudAxis Response ────────────────────────────────────────
        (
            "04_cloudaxis_response.pdf",
            """
RESPONSE TO NOTICE OF BREACH — CLOUDAXIS SOLUTIONS
Reference: RESP-CA-2026-05-02
Date: May 2, 2026
From: CloudAxis Solutions SARL
To: TechVenture SARL

Subject: Response to formal breach notice NOB-TV-2026-04-30.

1) Infrastructure Migration Position
CloudAxis acknowledges that TechVenture was not given advance written notice of
the April 26 migration. CloudAxis states this was an emergency security patch
migration required to address a zero-day vulnerability discovered on April 25.
CloudAxis claims force-majeure cyber-threat provisions may apply and requests
further discussion of the applicability of the planned maintenance clause.

2) SLA Availability Position
CloudAxis accepts that platform availability in April fell below the 99.7% SLA
target. CloudAxis proposes to apply a service credit equivalent to 15% of the
monthly subscription fee per the SLA credit schedule in the agreement.
CloudAxis disputes that the outage constitutes a material breach warranting
termination, noting the agreement requires a pattern of two consecutive months
below target before termination rights are triggered.

3) P1 Response Position
CloudAxis denies a formal P1 breach. CloudAxis states that internal escalation
occurred within 4 hours of ticket acceptance but that the communication was not
externally visible. CloudAxis offers to review ticket escalation protocols.

4) Data Loss Position
CloudAxis confirms data loss of approximately 18 hours of incremental data
(not 24 hours as TechVenture claims). CloudAxis states that backup restoration
recovered some of the April 25 payroll records. A full reconciliation report
will be provided by May 8, 2026.

5) Data Breach Notification Position
CloudAxis disputes that its April 28 notification was outside the 24-hour window.
CloudAxis states the clock began when data loss was confirmed, not when the
outage began. CloudAxis has engaged external legal counsel on this point.

6) Commercial Proposal
CloudAxis offers the following to resolve the dispute without escalation:
- Service credit of 15% of April subscription (5,175 TND) applied to May invoice
- Waiver of May overuse compute charges estimated at 2,100 TND
- Complimentary professional services day (850 TND value) for data reconciliation
- Commitment to provide disaster recovery plan update by May 12, 2026

CloudAxis requests that TechVenture hold the May 9 executive call before
deciding on termination to explore a structured resolution path.

Deadline for TechVenture response to this proposal: May 6, 2026 at 17:00.
""",
        ),
        # ── 05 ── Financial Impact Assessment ───────────────────────────────
        (
            "05_financial_impact_assessment.pdf",
            """
FINANCIAL IMPACT ASSESSMENT — CLOUDAXIS INCIDENT
Reference: FIA-TV-2026-05-01
Prepared by: TechVenture Finance and Operations
Date: May 1, 2026

Purpose
This assessment documents the quantifiable direct costs incurred by TechVenture
as a result of the CloudAxis platform outage and data loss of April 26-28, 2026.

Direct Internal Costs
Payroll team emergency re-entry and reconciliation work:
- 14 hours senior payroll specialist at 120 TND/hour = 1,680 TND
- 8 hours junior payroll coordinator at 75 TND/hour = 600 TND
- Subtotal payroll recovery: 2,280 TND

Finance team unrecoverable posting reconstruction:
- 6 hours senior financial controller at 140 TND/hour = 840 TND
- 4 hours financial analyst at 95 TND/hour = 380 TND
- Subtotal finance recovery: 1,220 TND

Customer operations reconciliation:
- 847 transaction records at estimated 12 minutes per record
- 3 operations staff at 85 TND/hour = 8,470 TND estimated
- Subtotal customer operations: 8,470 TND

IT emergency response and overtime:
- 31 hours IT team at blended rate of 110 TND/hour = 3,410 TND
- External IT consultant emergency call: 4,800 TND
- Subtotal IT response: 8,210 TND

Legal and compliance review:
- 6 hours in-house counsel at 180 TND/hour = 1,080 TND
- External legal review estimated: 6,000 TND
- Subtotal legal: 7,080 TND

Total Direct Internal Costs to Date: 27,260 TND

Disputed Invoice Items
- April subscription invoice: 34,500 TND base
- TechVenture position: April subscription should be reduced by at least 30%
  given the severity and duration of the SLA breach (estimated credit: 10,350 TND)
- CloudAxis counter-proposal credit: 5,175 TND (15%)
- Difference: 5,175 TND remains disputed

Potential Future Costs
- Regulatory filing costs (data protection assessment): estimated 3,500-8,000 TND
- Possible external audit of CloudAxis security controls: estimated 15,000 TND
- Customer compensation claims for delayed orders: not yet quantified
- Reputational harm and lost business: not yet quantified

Summary
Confirmed direct costs: 27,260 TND
Disputed invoice credit balance: minimum 5,175 TND additional due to TechVenture
Total minimum financial exposure for CloudAxis: 32,435 TND
Maximum exposure if regulatory and customer claims crystallize: unclear
""",
        ),
        # ── 06 ── IT Forensics Extract ──────────────────────────────────────
        (
            "06_it_forensics_extract.pdf",
            """
IT FORENSICS EXTRACT — CLOUDAXIS INCIDENT ANALYSIS
Reference: ITFE-TV-2026-05-02
Prepared by: TechVenture IT Security and External Consultant
Date: May 2, 2026

Purpose
This extract documents technical findings from TechVenture's review of available
logs, API exports, and CloudAxis-provided incident documentation.

Key Technical Findings

1) Migration Scheduling Evidence
CloudAxis internal change management records (shared on request) show the
infrastructure migration was scheduled in CloudAxis's internal system on April 24,
2026 — one day before the claimed zero-day vulnerability discovery date.
This is inconsistent with CloudAxis's claim that it was an emergency response.

2) Backup Snapshot Gap
CloudAxis provided backup log exports showing:
- Last successful full backup: April 20, 2026 at 02:15
- Last successful incremental backup: April 25, 2026 at 02:15
- Snapshot creation for migration: April 26, 2026 at 11:30
- Snapshot marked as failed: April 26, 2026 at 14:15
- First recovery attempt: April 27, 2026 at 06:00
The data gap is confirmed as April 25 14:00 to April 26 14:20 (approximately
24 hours 20 minutes) not 18 hours as CloudAxis claims.

3) P1 Escalation Log Discrepancy
CloudAxis claims internal P1 escalation occurred at 18:45 on April 26.
TechVenture ticket portal shows no external escalation update was posted until
April 27 at 06:00. The SLA clock for P1 resolution commenced at 14:35 on April 26
when TechVenture opened the ticket. Resolution at April 27 09:15 = 18 hours 40 minutes.
The 8 business hour P1 SLA was materially exceeded regardless of internal escalation.

4) Data Classification of Lost Records
- April 25 payroll batch: contains personal data of 214 employees
  (names, salary data, bank account references)
- This data is personal data under Act 63-2004
- Loss of this data likely triggers a regulatory notification obligation
- CloudAxis's 28 April notification was 26 hours after confirmed discovery

5) ISO 27001 Certificate Status
CloudAxis's publicly available ISO 27001 certificate expired on March 3, 2026.
No renewal certificate has been provided. The agreement requires active
certification throughout the contract term. This is an independent contractual breach.

Evidence Quality Assessment
- Machine-generated timestamps from CloudAxis backup logs are strong evidence
- Internal CloudAxis change management records contradict the force-majeure defense
- The certificate expiry is documented and not disputed
- Data classification of lost payroll records is clear and well-supported

Gaps Remaining
- CloudAxis has not provided the full migration run-book or approval chain
- The zero-day vulnerability claim has not been independently verified
- Customer transaction reconciliation is not yet complete
""",
        ),
        # ── 07 ── Regulatory Notification Draft ─────────────────────────────
        (
            "07_regulatory_notification_draft.pdf",
            """
DRAFT REGULATORY NOTIFICATION — CONFIDENTIAL LEGAL DOCUMENT
Reference: RND-TV-2026-05-03-DRAFT
Prepared by: TechVenture Legal and Compliance
Date: May 3, 2026
Status: DRAFT — awaiting legal sign-off before submission

Regulatory Body: National Data Protection Authority (INPDP), Tunisia
Subject: Notification of personal data incident — CloudAxis platform outage
Filing Deadline: May 15, 2026 (72 hours from confirmed notification on May 2)

Note: This is a DRAFT document and has NOT been filed. Final version requires
legal team approval. Deadline is May 15, 2026.

Incident Summary
TechVenture SARL notifies the INPDP of an incident affecting personal data
processed through the CloudAxis ERP platform. The incident occurred on April 26,
2026 and was confirmed on April 28, 2026.

Nature of the Incident
An infrastructure migration performed by TechVenture's SaaS provider CloudAxis
Solutions SARL without advance notice caused a platform outage and resulted in
the confirmed loss of approximately 24 hours of incremental backup data.

Categories of Affected Personal Data
- Payroll records for 214 employees (names, identification numbers, salary data,
  bank account references) for April 25, 2026
- Customer transaction records for 847 transactions (business entity data,
  order data, payment reference data)

Note: TechVenture does not believe consumer personal data in the strict sense
is affected. Legal counsel is confirming whether Act 63-2004 reporting thresholds
are triggered for business-to-business transaction data.

Likely Consequences
- Temporary inaccessibility to payroll data creating payroll processing delays
- Potential for incomplete financial records for April 25
- Reputational and operational risk if customers are affected by incomplete orders

Measures Taken by TechVenture
- Formal breach notice sent to CloudAxis on April 30, 2026
- Incident documented and preserved for regulatory purposes
- Data reconstruction underway with CloudAxis and internal teams
- Legal review of regulatory obligations commenced May 1, 2026

Measures Requested from CloudAxis
- Full technical root cause analysis by May 6, 2026
- Confirmation of data recovery status by May 8, 2026
- ISO 27001 certification status confirmation
- Commitment on future notification procedures

Filing Decision
Legal team to confirm by May 10, 2026 whether formal notification to INPDP is
required. Deadline for any required regulatory filing: May 15, 2026.
""",
        ),
        # ── 08 ── Internal Risk Memo ─────────────────────────────────────────
        (
            "08_internal_risk_memo.pdf",
            """
INTERNAL RISK MEMORANDUM — CONFIDENTIAL
Author: TechVenture Legal Department
Date: May 3, 2026
Subject: Risk assessment and strategy — TechVenture v CloudAxis

Classification: Attorney-Client Privileged — Do Not Distribute

KEY DATES REQUIRING IMMEDIATE ACTION
- May 6, 2026: CloudAxis deadline for root cause analysis and data restoration plan
- May 8, 2026: CloudAxis data restoration verification deadline
- May 9, 2026: Executive negotiation call — AI-suggested, confirm attendance
- May 10, 2026: Internal decision on regulatory filing
- May 12, 2026: Mediation session in Tunis (if proceeding)
- May 15, 2026: Regulatory notification filing deadline (if required)
- May 20, 2026: Arbitration trigger date if mediation fails or does not occur

Legal Risk Assessment

RISK 1 — CLOUDAXIS FORCE MAJEURE DEFENSE (HIGH RISK)
CloudAxis may argue the migration was an emergency response to a zero-day
vulnerability, activating force-majeure cyber-threat provisions. However, IT
forensics evidence shows the migration was pre-scheduled on April 24, one day
before the alleged vulnerability discovery. This strongly undermines the defense.
TechVenture should request the vulnerability disclosure report and compare dates.
Strength of TechVenture position on this issue: HIGH.

RISK 2 — DATA LOSS QUANTUM DISPUTE (MEDIUM RISK)
CloudAxis claims only 18 hours of data loss. IT forensics confirms 24+ hours.
Backup logs are the strongest evidence. CloudAxis may contest the methodology.
Request full backup infrastructure logs before May 8 data restoration deadline.
Strength of TechVenture position on this issue: MEDIUM-HIGH.

RISK 3 — REGULATORY EXPOSURE (HIGH RISK)
Payroll data for 214 employees is personal data under Act 63-2004. The filing
deadline of May 15 is non-negotiable once the obligation is confirmed.
Failure to file if required could expose TechVenture to regulatory penalties.
Priority: get external regulatory counsel opinion by May 6.

RISK 4 — ISO 27001 CERTIFICATE BREACH (LOW COMPLEXITY, HIGH VALUE)
The expired certificate is independently documented, easy to prove, and directly
breaches the agreement. This is TechVenture's strongest standalone breach claim.
CloudAxis cannot easily dispute the expiry date from the public certificate record.
This breach alone may support termination rights regardless of the SLA debate.

RISK 5 — CLOUDAXIS TERMINATION DEFENSE (MEDIUM RISK)
CloudAxis will argue that termination requires two consecutive months below SLA
rather than a single month. The agreement is ambiguous. However, the combination
of SLA breach, data loss, late notification, and certificate expiry may collectively
satisfy the material breach threshold even for a single incident.
Legal counsel to confirm interpretation before the May 9 call.

RECOMMENDED STRATEGY
Short term (before May 9 call):
- Obtain full backup logs and zero-day vulnerability evidence from CloudAxis
- Confirm regulatory filing obligation
- Prepare settlement counter-proposal with minimum acceptance criteria
- Preserve all evidence — do not communicate data breach liability admissions

Medium term (May 9-15):
- Use May 9 call to assess CloudAxis's real settlement intent
- If settlement not achievable, confirm mediation for May 12
- File regulatory notification if confirmed required by May 15

Long term (May 15+):
- If mediation fails: prepare arbitration brief
- Consider platform migration to reduce operational dependency
- Document all business impact to strengthen damages claim

Minimum Settlement Terms (legal recommendation)
- Full service credit for April: 34,500 TND (100% of monthly fee)
- Recovery of confirmed direct costs: 27,260 TND
- ISO 27001 renewal within 30 days with certificate provided to TechVenture
- Enhanced SLA with penalty mechanism for any future P1 breach
- 90-day extension option with 60-day notice for migration at no extra cost
- Total minimum: 61,760 TND + enhanced contractual protections
""",
        ),
        # ── 09 ── Settlement Term Sheet ──────────────────────────────────────
        (
            "09_settlement_term_sheet.pdf",
            """
WITHOUT PREJUDICE SETTLEMENT TERM SHEET
Reference: WPTS-TV-2026-05-04
Date: May 4, 2026
Prepared by: TechVenture Legal for internal review
Status: DRAFT — not yet sent to CloudAxis

Context
This term sheet sets out TechVenture's proposed minimum resolution framework
to be presented at the May 9, 2026 executive call. It is prepared on a
without-prejudice basis and reflects the minimum terms TechVenture would accept
to avoid escalation to mediation and arbitration.

Proposed Resolution Terms

Financial Terms
1) CloudAxis to provide full credit for April subscription: 34,500 TND
2) CloudAxis to pay TechVenture's confirmed direct costs: 27,260 TND
3) CloudAxis to waive May overuse compute charges: estimated 2,100 TND
4) CloudAxis to provide complimentary professional services for data reconciliation:
   10 days at no charge (estimated value 8,500 TND)
Total financial resolution: minimum 63,760 TND equivalent

Operational Terms
5) CloudAxis to renew and provide ISO 27001 certificate within 21 days
6) CloudAxis to provide updated and tested disaster recovery plan within 30 days
7) CloudAxis to implement advance 5-day written notice for all future migrations
8) CloudAxis to provide TechVenture read-only access to its incident management
   portal for 12 months

Contractual Protections
9) Contract extension at current pricing for 18 months (TechVenture option)
10) Enhanced SLA credit schedule: P1 breaches trigger 25% of monthly fee credit
11) Immediate termination right if data loss above 2 hours RPO occurs again
12) Mutual preservation of data breach regulatory defense coordination

Acceptance Deadline
TechVenture requires CloudAxis acceptance in writing by May 20, 2026.
If not accepted by May 20, TechVenture will proceed to arbitration.

This document is prepared without prejudice and does not constitute an admission
of any limitation on TechVenture's rights or remedies.
""",
        ),
        # ── 10 ── Case Strategy Update ──────────────────────────────────────
        (
            "10_case_strategy_update.pdf",
            """
CASE STRATEGY UPDATE — TECHVENTURE V CLOUDAXIS
Reference: CSU-TV-2026-05-04
Date: May 4, 2026
Author: TechVenture Legal Team
Status: Current as of May 4, 2026

Executive Summary
TechVenture has a strong multi-ground breach case against CloudAxis. The strongest
elements are the confirmed data loss, expired ISO 27001 certificate, and the IT
forensics evidence that contradicts CloudAxis's force-majeure defense. The case
is at a critical point: the May 6 deadline for CloudAxis's root cause analysis and
the May 9 executive call will determine whether the dispute resolves commercially
or escalates to formal proceedings.

Current Positions

TechVenture position: Multi-ground material breach supporting termination and
full recovery of documented costs. Strong evidence base on availability breach,
data loss, certificate expiry, and migration notice failure.

CloudAxis position: Disputes material breach characterization, claims
force-majeure cyber-threat defense, accepts limited SLA credit only, disputes
data loss quantum, challenges notification timeline.

Evidence Strength Assessment
- IT forensics backup log evidence: STRONG (machine-generated timestamps)
- ISO 27001 certificate expiry: VERY STRONG (independently verifiable)
- Migration pre-scheduling evidence: STRONG (CloudAxis's own records)
- Financial impact assessment: MEDIUM (internal estimates, needs third-party support)
- Regulatory notification obligation: MEDIUM (Act 63-2004 analysis pending)

Critical Upcoming Actions and Deadlines
- May 6, 2026: CloudAxis response deadline — evaluate adequacy of cure
- May 8, 2026: Confirm data restoration status
- May 9, 2026: Executive negotiation call — present settlement term sheet
- May 10, 2026: Internal decision on regulatory notification
- May 12, 2026: Mediation session if May 9 call unsuccessful
- May 15, 2026: Regulatory filing deadline if confirmed required
- May 20, 2026: Arbitration trigger if mediation fails

Recommended Next Actions
1) URGENT: Obtain external regulatory counsel opinion by May 6
2) URGENT: Review CloudAxis root cause analysis when received on May 6
3) Confirm attendance for May 9 executive call
4) Finalize settlement term sheet for May 9 presentation
5) Book mediation center in Tunis for May 12 as contingency
6) Preserve all forensics evidence in write-once secure storage
7) Brief TechVenture CEO on settlement authority limits before May 9

Risk Rating: HIGH
Case Priority: HIGH
Next review date: May 6, 2026 (after CloudAxis deadline)
""",
        ),
    ]


def generate_pack(output_dir: Path, overwrite: bool) -> list[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []

    for filename, body in demo_documents():
        target = output_dir / filename
        if target.exists() and not overwrite:
            continue
        target.write_bytes(build_simple_pdf(body))
        written.append(target)

    return written


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate May 2026 dashboard test pack PDFs (10 docs)."
    )
    parser.add_argument(
        "--output-dir",
        default="docs/test-data/may2026-demo-pack",
        help="Directory where PDFs will be written (default: docs/test-data/may2026-demo-pack)",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite existing PDF files",
    )
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    if not output_dir.is_absolute():
        output_dir = Path(__file__).resolve().parents[1] / output_dir

    written = generate_pack(output_dir=output_dir, overwrite=args.overwrite)
    total = len(list(output_dir.glob("*.pdf")))

    print(f"Output directory : {output_dir}")
    print(f"PDF files total  : {total}")
    if written:
        print("Generated:")
        for item in written:
            print(f"  {item.name}")
    else:
        print("No new files written (all exist — use --overwrite to regenerate).")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
