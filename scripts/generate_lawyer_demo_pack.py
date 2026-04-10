from __future__ import annotations

import argparse
from pathlib import Path


def escape_pdf_text(value: str) -> str:
    return value.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def build_simple_pdf(text: str) -> bytes:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        lines = ["Empty content."]

    # Keep a compact but readable one-page layout.
    content_parts = [
        "BT",
        "/F1 10 Tf",
        "44 770 Td",
    ]
    for line in lines[:58]:
        content_parts.append(f"({escape_pdf_text(line[:140])}) Tj")
        content_parts.append("0 -12 Td")
    content_parts.append("ET")
    content_stream = ("\n".join(content_parts) + "\n").encode("latin-1", errors="ignore")

    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        f"<< /Length {len(content_stream)} >>\nstream\n".encode("ascii") + content_stream + b"endstream",
    ]

    pdf = b"%PDF-1.4\n"
    offsets: list[int] = [0]
    for index, obj in enumerate(objects, start=1):
        offsets.append(len(pdf))
        pdf += f"{index} 0 obj\n".encode("ascii") + obj + b"\nendobj\n"

    xref_start = len(pdf)
    pdf += f"xref\n0 {len(objects) + 1}\n".encode("ascii")
    pdf += b"0000000000 65535 f \n"
    for offset in offsets[1:]:
        pdf += f"{offset:010d} 00000 n \n".encode("ascii")
    pdf += f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref_start}\n%%EOF".encode("ascii")
    return pdf


def demo_documents() -> list[tuple[str, str]]:
    return [
        (
            "01_master_service_agreement.pdf",
            """
MASTER SERVICE AGREEMENT
Agreement ID: MSA-AR-NL-2026-004
Effective Date: January 12, 2026
Parties: Atlas Retail Group SARL and Nova Logistics Tunisia SARL

1) Scope of Services
Nova provides warehousing, order packing, and last-mile delivery for Atlas ecommerce orders.

2) SLA Targets
- On-time delivery: 96% monthly
- Lost package threshold: 0.8% monthly
- Escalation response time: 4 business hours
- Breach trigger: two consecutive months below SLA target

3) Commercial Terms
- Monthly operations fee: 21,500 TND
- Per delivery fee: 8.70 TND
- Fuel surcharge cap: 4.5%
- Payment terms: Net 30
- Late payment interest: 1.5% per month

4) Termination and Liability
- Initial term: 12 months
- Cure period: 15 days after written notice
- Liability cap: three months of average fees
- No cap for fraud or gross negligence

5) Governing Law and Dispute Resolution
- Governing law: Tunisia
- Escalation: executive negotiation, then mediation, then arbitration
""",
        ),
        (
            "02_notice_of_breach.pdf",
            """
NOTICE OF BREACH AND PAYMENT DISPUTE
Reference: NOB-ATLAS-2026-03-29
Date: March 29, 2026
From: Atlas Retail Group SARL
To: Nova Logistics Tunisia SARL

Subject: Formal notice of repeated SLA breaches and disputed invoice lines.

1) SLA Non-Compliance
- February on-time delivery: 92.4%
- March on-time delivery: 93.1%
- Lost package ratio in March: 1.2%

2) Invoice Dispute
Invoice: INV-NOVA-2026-03
- Claimed amount: 98,420 TND
- Accepted pending verification: 71,960 TND
- Disputed amount: 26,460 TND

3) Cure Deadlines
- Root cause report due: April 3, 2026
- Corrective operations plan due: April 5, 2026
- Revised invoice due: April 6, 2026

4) Reservation of Rights
Atlas reserves contractual and legal remedies if cure is not complete in 15 days.
""",
        ),
        (
            "03_counterparty_response.pdf",
            """
COUNTERPARTY RESPONSE LETTER
Reference: RESP-NOVA-2026-04-02
Date: April 2, 2026
From: Nova Logistics Tunisia SARL
To: Atlas Retail Group SARL

Subject: Response to notice of breach and invoice dispute.

1) SLA Position by Nova
- February on-time delivery: 95.3%
- March on-time delivery: 94.8%
- Nova claims force-majeure weather events were counted incorrectly.

2) Invoice Clarification
Invoice INV-NOVA-2026-03 should remain 98,420 TND.
Nova offers temporary credit note of 8,000 TND pending reconciliation.
Nova requests payment of undisputed amount by April 10, 2026.

3) Corrective Measures
- Additional route planner deployment by April 4
- Weekend dispatch controls by April 6
- Joint KPI review proposed for April 8, 2026

4) Legal Position
Nova denies that termination prerequisites are currently met.
""",
        ),
        (
            "04_kpi_dashboard_extract_q1.pdf",
            """
Q1 OPERATIONS KPI DASHBOARD EXTRACT
Period: January to March 2026
Prepared by: Atlas Operations Audit Unit

Key Metrics by Month
January:
- Orders delivered: 31,240
- On-time delivery: 96.8%
- Lost package ratio: 0.6%

February:
- Orders delivered: 33,110
- On-time delivery: 92.4%
- Lost package ratio: 0.9%

March:
- Orders delivered: 35,880
- On-time delivery: 93.1%
- Lost package ratio: 1.2%

Observed Risks
- Repeated missed SLA targets in two consecutive months
- Elevated complaint volume from key urban zones
- Incomplete proof-of-delivery records in 7.4% of sampled files

Recommended Immediate Actions
- Corrective action plan with weekly KPI checkpoints
- Root-cause analysis by route cluster and carrier team
""",
        ),
        (
            "05_invoice_reconciliation_sheet.pdf",
            """
INVOICE RECONCILIATION SHEET
Reference: REC-INV-NOVA-2026-03
Case linkage: Atlas vs Nova logistics dispute

Invoice Overview
- Invoice ID: INV-NOVA-2026-03
- Invoice date: March 4, 2026
- Claimed total: 98,420 TND
- Atlas accepted amount: 71,960 TND
- Disputed amount: 26,460 TND

Disputed Components
1) Fuel surcharge adjustments above contractual cap
2) Returned parcel handling fees without support logs
3) Weekend delivery uplift entries with duplicate route references

Audit Notes
- 18 line items require documentary support
- 6 line items flagged as likely duplicate charges
- 4 line items appear to exceed negotiated rate card

Deadline
- Revised invoice and support pack requested by April 6, 2026
""",
        ),
        (
            "06_internal_legal_memo.pdf",
            """
INTERNAL LEGAL MEMORANDUM
Author: Atlas Legal Team
Date: April 4, 2026
Subject: Preliminary litigation and negotiation posture

Issue Framing
The case involves potential material breach of service levels and a payment dispute.
Evidence includes contract terms, KPI extracts, and invoice reconciliation records.

Key Legal Questions
- Are termination preconditions satisfied under cure and notice clauses?
- Which damages are recoverable under liability cap language?
- Is mediation mandatory before arbitration trigger?

Risk Assessment
- Medium-to-high risk if Atlas cannot prove metric integrity and causation of losses.
- Counterparty likely to challenge KPI methodology and exclusion criteria.
- Delay in documentation could weaken breach timeline narrative.

Recommended Strategy
- Preserve a settlement window while building arbitration-ready evidence.
- Prioritize chronology clarity and source-grounded damage calculations.
- Align communications to avoid prejudicial statements.
""",
        ),
        (
            "07_without_prejudice_settlement_offer.pdf",
            """
WITHOUT PREJUDICE SETTLEMENT OFFER
Reference: WPS-ATLAS-2026-04-07
Date: April 7, 2026

Commercial Offer Terms
1) Temporary two-month rebate of 0.7 TND per delivered package
2) Fuel surcharge interim cap of 3.8%
3) Credit note issuance for 12,500 TND within 5 business days
4) Weekly executive review for six weeks

Operational Commitments
- Joint performance command center for April and May
- Shared incident dashboard with daily route-level updates
- Corrective plan acceptance criteria tied to SLA recovery threshold

Legal Reservation
This proposal is made without prejudice and does not waive contractual rights.
If terms are not accepted by April 12, Atlas reserves escalation options.
""",
        ),
        (
            "08_client_call_transcript_summary.pdf",
            """
CLIENT CALL TRANSCRIPT SUMMARY
Call date: April 5, 2026
Participants: Atlas CEO, Atlas Legal, Nova Director, Nova Operations Lead

Summary of Positions
- Atlas requests immediate KPI stabilization and invoice correction.
- Nova disputes material breach label and asks for exclusion adjustments.
- Both parties agree to exchange raw delivery logs by April 8.

Action Items
1) Nova to submit corrected route-level KPI methodology note
2) Atlas to provide complaint cohort analysis and churn estimates
3) Joint reconciliation workshop scheduled for April 9, 10:00 AM

Potential Settlement Signals
- Openness to temporary rebates and credit notes
- Agreement in principle on intensified weekly governance cadence

Open Risks
- Disagreement over force-majeure treatment remains unresolved
- Evidence quality on invoice support files still incomplete
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
    parser = argparse.ArgumentParser(description="Generate a realistic lawyer demo PDF pack (8 docs).")
    parser.add_argument(
        "--output-dir",
        default="docs/test-data/lawyer-demo-pack",
        help="Directory where generated PDF files will be written",
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

    print(f"Output directory: {output_dir}")
    print(f"PDF files now available: {total}")
    if written:
        print("Generated files:")
        for item in written:
            print(f"- {item.name}")
    else:
        print("No new files generated (all files already exist).")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
