from __future__ import annotations

import argparse
from pathlib import Path

from generate_lawyer_demo_pack import build_simple_pdf


def demo_documents() -> list[tuple[str, str]]:
    return [
        (
            "01_equipment_maintenance_agreement.pdf",
            """
EQUIPMENT MAINTENANCE AND SERVICE AGREEMENT
Agreement ID: EMSA-MC-BS-2025-018
Effective Date: November 18, 2025
Parties: MedCare Clinics SARL and BioServe Medical Systems SARL
Governing law: Tunisia

1) Scope
BioServe will provide preventive maintenance, emergency repair, calibration,
software updates, and spare-part coordination for five diagnostic imaging units
operated by MedCare in Tunis, Ariana, and Sousse.

2) Service Levels
- Critical equipment downtime response: technician onsite within 6 business hours
- Monthly preventive maintenance visit for each covered site
- Uptime target: 98.5 percent measured monthly across covered units
- Replacement part quotation due within 2 business days after diagnosis
- Incident report due within 24 hours after each critical outage

3) Commercial Terms
- Monthly fixed maintenance fee: 18,750 TND excluding VAT
- Emergency callout included for first 4 calls per month
- Spare parts billed separately after written purchase order
- Payment terms: Net 30 from valid invoice and service report
- MedCare may withhold disputed invoice lines if written reasons are provided
  within 10 calendar days after invoice receipt.

4) Cure and Termination
Material breach may be notified in writing. BioServe has 10 business days to cure
unless patient safety or regulatory compliance requires immediate mitigation.
MedCare may suspend payments for unsupported services, but must pay undisputed
amounts when due.

5) Liability
Direct damages are capped at three months of fees. The cap does not apply to
gross negligence, intentional misconduct, confidentiality breach, or regulatory
penalties caused by BioServe's documented failure.

6) Confidentiality and Patient Data
Service logs may include device IDs and limited operational metadata. BioServe
must not access patient records except where strictly required for diagnostics.
Any unauthorized access must be reported within 24 hours.

7) Dispute Resolution
Senior management negotiation must occur within 7 business days after notice.
If unresolved, the parties will attempt mediation in Tunis before arbitration.
""",
        ),
        (
            "02_internal_incident_report_march_outage.pdf",
            """
INTERNAL INCIDENT REPORT
Report ID: IR-MEDCARE-2026-03-21
Prepared by: MedCare Operations and Compliance
Date: March 22, 2026

Incident Summary
On March 21, 2026, the Ariana clinic MRI unit was unavailable from 08:15 to
17:40. Twenty-three patient appointments were delayed or moved. The incident was
classified as critical because the affected unit supports urgent neurological
diagnostic referrals.

Timeline
- 08:15: Radiology coordinator reported boot failure and calibration error C-417
- 08:28: Helpdesk ticket opened with BioServe
- 09:10: BioServe acknowledged ticket and requested log export
- 11:55: MedCare escalated because no technician was onsite
- 14:30: BioServe technician arrived
- 16:50: Temporary workaround applied
- 17:40: Unit returned to limited operation

Initial Findings
The BioServe response exceeded the 6 business hour onsite response standard.
Preventive maintenance records for February 2026 do not show completion for the
Ariana MRI unit. The unit had generated calibration warnings on March 17 and
March 19 that were not escalated by BioServe.

Business Impact
- 23 patient appointments disrupted
- 9 outsourced scans booked at partner clinic
- Estimated direct outsourcing cost: 8,920 TND
- Potential regulator concern if repeat downtime affects continuity of care
""",
        ),
        (
            "03_client_breach_notice.pdf",
            """
FORMAL NOTICE OF BREACH AND PAYMENT RESERVATION
Reference: NOB-MEDCARE-2026-03-25
Date: March 25, 2026
From: MedCare Clinics SARL
To: BioServe Medical Systems SARL

Subject
Repeated equipment downtime, missing maintenance records, and disputed invoice
items under EMSA-MC-BS-2025-018.

1) Breach Allegations
MedCare records show that BioServe failed to satisfy the critical onsite response
standard for the March 21 Ariana outage. MedCare also has no complete preventive
maintenance report for the Ariana MRI unit for February 2026.

2) Disputed Invoice
MedCare disputes Invoice BS-INV-2026-0317 dated March 17, 2026.
- BioServe claimed amount: 64,380 TND
- MedCare accepted amount pending support: 39,750 TND
- Disputed amount: 24,630 TND
The disputed amount includes unsupported emergency callout fees, replacement
part handling fees, and remote diagnostic charges.

3) Cure Requests
MedCare requests:
- Root cause report by March 30, 2026
- Corrective maintenance plan by April 1, 2026
- Complete February and March service logs by April 1, 2026
- Revised invoice and supporting work orders by April 3, 2026

4) Reservation of Rights
MedCare reserves all contractual and legal remedies, including recovery of direct
outsourcing costs, regulatory response costs, and termination if the breach is
not cured within the contractual cure period.
""",
        ),
        (
            "04_bioserve_response_letter.pdf",
            """
COUNTERPARTY RESPONSE LETTER
Reference: RESP-BIOSERVE-2026-03-28
Date: March 28, 2026
From: BioServe Medical Systems SARL
To: MedCare Clinics SARL

Subject
Response to notice of breach and invoice dispute.

1) Service Response Position
BioServe denies material breach. BioServe states the onsite response clock should
start at 09:10 when its helpdesk accepted the complete ticket, not 08:28 when
MedCare opened the first ticket. BioServe also states traffic disruption around
Ariana delayed technician arrival.

2) Preventive Maintenance Position
BioServe states a February preventive check was performed remotely on February
26, 2026. BioServe admits that the signed service sheet is missing and offers to
reconstruct the log from system telemetry.

3) Invoice Position
BioServe maintains that Invoice BS-INV-2026-0317 is payable in full. However, as
a commercial gesture, BioServe offers a temporary credit note of 6,500 TND if
MedCare pays the undisputed amount by April 5, 2026.

4) Corrective Actions
- Additional senior engineer visit proposed for April 2, 2026
- Remote monitoring thresholds to be recalibrated by April 4, 2026
- Joint review meeting proposed for April 6, 2026 at 10:00

5) Legal Reservation
BioServe reserves its right to claim late payment interest if undisputed amounts
remain unpaid.
""",
        ),
        (
            "05_invoice_and_reconciliation_sheet.pdf",
            """
INVOICE AND RECONCILIATION SHEET
Reference: REC-BS-INV-2026-0317
Prepared by: MedCare Finance
Date: March 29, 2026

Invoice Overview
- Invoice ID: BS-INV-2026-0317
- Invoice date: March 17, 2026
- Claimed total: 64,380 TND excluding VAT
- Accepted pending verification: 39,750 TND
- Disputed amount: 24,630 TND

Accepted Lines
- Monthly fixed maintenance fee for March: 18,750 TND
- Sousse ultrasound preventive visit: 4,800 TND
- Tunis CT calibration visit: 6,200 TND
- Standard consumables and filters: 10,000 TND

Disputed Lines
- Emergency callout fees: 7,500 TND, appears included in monthly allowance
- Remote diagnostic charge: 4,950 TND, no work order attached
- Replacement part handling fee: 6,880 TND, no purchase order approval found
- Priority dispatch uplift: 5,300 TND, not listed in signed rate card

Finance Notes
MedCare sent written dispute reasons within 10 calendar days of receipt. Finance
recommends paying the accepted amount after legal confirms payment language does
not waive breach rights.
""",
        ),
        (
            "06_service_logs_extract.pdf",
            """
SERVICE LOGS EXTRACT
Source: BioServe shared portal and MedCare facility records
Period: February 1 to March 27, 2026

February Preventive Maintenance
- Tunis CT unit: completed February 8, signed by site manager
- Sousse ultrasound unit: completed February 14, signed by biomedical lead
- Ariana MRI unit: no signed preventive maintenance sheet located
- Remote telemetry note for Ariana MRI: February 26, status marked incomplete

March Events
- March 17, 07:52: Ariana MRI warning C-417 generated
- March 19, 18:12: Second C-417 warning generated
- March 21, 08:28: MedCare ticket opened
- March 21, 09:10: BioServe ticket accepted
- March 21, 14:30: BioServe technician onsite
- March 21, 17:40: Limited operation restored
- March 24, 16:05: Calibration stability test failed once, then passed

Log Integrity Concerns
The portal export does not contain a technician signature for the February
Ariana entry. Two March warning events were automatically closed by remote
monitoring without MedCare confirmation.

Potentially Helpful Evidence
The system event timestamps are machine-generated. They may be stronger evidence
than later email narratives if authenticity is preserved.
""",
        ),
        (
            "07_patient_operations_impact_summary.pdf",
            """
PATIENT OPERATIONS IMPACT SUMMARY
Prepared by: MedCare Patient Operations
Date: March 31, 2026

Affected Services
The March 21 outage affected MRI scheduling at the Ariana clinic. Patients with
urgent referrals were prioritized for rerouting to partner clinics.

Impact Figures
- Delayed appointments: 23
- Same-day external referrals: 9
- Cancelled appointments later rebooked: 4
- Patient complaints received by March 29: 7
- Direct external scan costs: 8,920 TND
- Estimated internal overtime cost: 1,480 TND

Customer Communications
Staff used approved disruption scripts. No patient diagnosis details were shared
with BioServe. Two patients requested written explanations for insurance files.

Compliance Notes
No immediate patient injury was reported. Compliance recommends preserving all
ticket records, service logs, patient scheduling records, and external clinic
invoices. If downtime repeats in April, a regulator notification assessment may
be needed.

Evidence Gaps
The summary estimates do not yet include reputational harm or lost future
appointments. Legal should avoid overstating damages until finance support is
complete.
""",
        ),
        (
            "08_internal_legal_memo.pdf",
            """
INTERNAL LEGAL MEMORANDUM
Author: MedCare Legal Department
Date: April 2, 2026
Subject: Preliminary risk assessment for MedCare v BioServe

Key Questions
1) Did BioServe miss the 6 business hour onsite response SLA?
2) Does the missing February service sheet prove preventive maintenance breach?
3) Can MedCare recover outsourcing and compliance costs despite liability cap?
4) Can MedCare withhold disputed invoice lines without triggering late interest?

Preliminary Assessment
MedCare has a credible breach position based on machine timestamps, missing
maintenance documentation, and the March outage chronology. The strongest issue
is service-level performance. The weaker issue is damages because some impact
figures remain estimates.

Counterparty Risks
BioServe will argue that the response clock started only after ticket acceptance
at 09:10. BioServe will also argue that traffic disruption and remote maintenance
records reduce fault. These defenses should be tested against the agreement,
ticket policy, and service logs.

Recommended Strategy
- Pay undisputed amount with express reservation of rights
- Demand complete telemetry and signed service records
- Preserve settlement option with credit note and enhanced monitoring
- Prepare mediation brief if April 6 management negotiation fails

Immediate Deadlines
- April 3, 2026: revised invoice support due
- April 5, 2026: BioServe payment deadline for credit note offer
- April 6, 2026: proposed joint review meeting
""",
        ),
        (
            "09_without_prejudice_settlement_offer.pdf",
            """
WITHOUT PREJUDICE SETTLEMENT PROPOSAL
Reference: WPS-MEDCARE-2026-04-04
Date: April 4, 2026
From: MedCare Clinics SARL
To: BioServe Medical Systems SARL

Commercial Terms Proposed
1) BioServe issues a credit note of 14,000 TND against BS-INV-2026-0317
2) MedCare pays 39,750 TND undisputed amount within 3 business days after credit
note issuance and supporting documents
3) BioServe waives late payment interest for March invoice
4) BioServe provides two months of enhanced monitoring at no additional charge

Operational Commitments
- Senior engineer onsite inspections for Ariana MRI on April 8 and April 22
- Daily remote alert review for all covered units until May 31, 2026
- Incident report template agreed by April 10, 2026
- Monthly preventive maintenance sheets must be signed by MedCare site manager

Escalation
If accepted by April 8, 2026, MedCare will pause termination steps. If rejected,
MedCare reserves the right to proceed with senior management escalation,
mediation, and all contractual remedies.

Legal Reservation
This proposal is made without prejudice and does not waive MedCare's rights.
""",
        ),
        (
            "10_management_call_summary.pdf",
            """
MANAGEMENT CALL SUMMARY
Call date: April 6, 2026
Participants: MedCare CEO, MedCare Legal, BioServe Director, BioServe Service Lead
Prepared by: MedCare Legal

Main Discussion Points
MedCare stated that patient continuity and documentation gaps are the core
concerns. BioServe repeated that it does not accept material breach, but accepted
that the missing February service sheet is a documentation problem.

Agreed Action Items
- BioServe to provide raw telemetry export by April 7, 2026 at 18:00
- MedCare to send external scan invoices by April 8, 2026
- BioServe senior engineer visit scheduled for April 8, 2026 at 09:00
- Both sides to hold settlement call on April 9, 2026 at 15:00

Unresolved Issues
- Start time for SLA response clock remains disputed
- Amount of credit note remains disputed
- Whether payment of undisputed amount affects MedCare remedies remains sensitive

Settlement Signals
BioServe indicated possible flexibility up to 10,000 TND credit if MedCare pays
by April 10. MedCare indicated it may accept enhanced monitoring if documentation
controls become strict and measurable.

Legal Note
Future client communications should separate operational settlement language from
admissions of breach or waiver of rights.
""",
        ),
    ]


def runbook() -> str:
    return """# MedCare v BioServe Demo Pack

This is a realistic synthetic case pack for testing the full legal AI workflow.
All parties and facts are fictional.

## Recommended Case Values

- Client name: MedCare Clinics SARL
- Case title: MedCare v BioServe - Medical Equipment Maintenance Dispute
- Practice area: Commercial Litigation / Healthcare Operations
- Priority: High
- Status: Open
- Jurisdiction: Tunisia

## Upload Order

1. 01_equipment_maintenance_agreement.pdf
2. 02_internal_incident_report_march_outage.pdf
3. 03_client_breach_notice.pdf
4. 04_bioserve_response_letter.pdf
5. 05_invoice_and_reconciliation_sheet.pdf
6. 06_service_logs_extract.pdf
7. 07_patient_operations_impact_summary.pdf
8. 08_internal_legal_memo.pdf
9. 09_without_prejudice_settlement_offer.pdf
10. 10_management_call_summary.pdf

## Demo Prompts

1. Summarize the case in 8 bullets with the main contract, breach, invoice, and healthcare operations issues.
2. Build a strict chronology with dates, deadlines, and source documents.
3. Identify contradictions between MedCare and BioServe positions.
4. What are the strongest and weakest pieces of evidence for MedCare?
5. Extract every deadline and propose calendar reminders.
6. Rank the legal risks from high to low and explain the evidence behind each one.
7. Draft a client-facing update email that preserves MedCare's rights.
8. Draft a without-prejudice negotiation strategy for the April 9 settlement call.
9. What documents are missing or should be requested next?
10. Prepare a partner review memo with recommended next actions.

## Expected Workflow Coverage

- PDF ingestion and text extraction
- Matter classification
- Timeline and deadline extraction
- Contradiction detection
- Evidence strength analysis
- Risk triage
- Settlement and drafting assistance
- Source-grounded RAG answers
"""


def generate_pack(output_dir: Path, overwrite: bool) -> list[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []

    guide_pdf_path = output_dir / "00_case_upload_guide.pdf"
    if overwrite or not guide_pdf_path.exists():
        guide_pdf_path.write_bytes(build_simple_pdf(runbook()))
        written.append(guide_pdf_path)

    for filename, body in demo_documents():
        target = output_dir / filename
        if target.exists() and not overwrite:
            continue
        target.write_bytes(build_simple_pdf(body))
        written.append(target)

    return written


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate a realistic MedCare legal demo PDF pack.")
    parser.add_argument(
        "--output-dir",
        default="docs/medcare-bioserve-demo-pack",
        help="Directory where generated files will be written",
    )
    parser.add_argument("--overwrite", action="store_true", help="Overwrite existing files")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    if not output_dir.is_absolute():
        output_dir = Path(__file__).resolve().parents[1] / output_dir

    written = generate_pack(output_dir=output_dir, overwrite=args.overwrite)
    pdf_count = len(list(output_dir.glob("*.pdf")))

    print(f"Output directory: {output_dir}")
    print(f"PDF files now available: {pdf_count}")
    if written:
        print("Generated files:")
        for item in written:
            print(f"- {item.name}")
    else:
        print("No new files generated (all files already exist).")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
