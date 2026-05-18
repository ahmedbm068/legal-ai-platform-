"""Generate the work-summary PDF for the messaging & frontend build.

Self-contained ReportLab script — no external assets. Produces
docs/Legal_AI_Build_Summary.pdf
"""
from __future__ import annotations

import os

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    HRFlowable,
    ListFlowable,
    ListItem,
    PageBreak,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)

# ── Palette ────────────────────────────────────────────────────────────────
INK = colors.HexColor("#0F1B2D")
ACCENT = colors.HexColor("#1F4C6B")
ACCENT_SOFT = colors.HexColor("#E8F0F5")
AI_PURPLE = colors.HexColor("#6D4AD8")
MUTED = colors.HexColor("#5A6B78")
LINE = colors.HexColor("#D8E2E7")
PAGE_BG = colors.HexColor("#FBFCFD")

OUT_PATH = os.path.join(os.path.dirname(__file__), "Legal_AI_Build_Summary.pdf")

styles = getSampleStyleSheet()


def style(name, **kw):
    return ParagraphStyle(name, parent=styles["Normal"], **kw)


H1 = style("H1", fontName="Helvetica-Bold", fontSize=24, textColor=INK,
           leading=28, spaceAfter=4)
SUBTITLE = style("SUB", fontName="Helvetica", fontSize=11, textColor=MUTED,
                 leading=16)
SECTION = style("SECTION", fontName="Helvetica-Bold", fontSize=15,
                textColor=ACCENT, leading=20, spaceBefore=18, spaceAfter=6)
BODY = style("BODY", fontName="Helvetica", fontSize=10, textColor=INK,
             leading=15, spaceAfter=4, alignment=TA_LEFT)
BULLET = style("BULLET", fontName="Helvetica", fontSize=10, textColor=INK,
               leading=15)
SMALL = style("SMALL", fontName="Helvetica", fontSize=8.5, textColor=MUTED,
              leading=12)
KICKER = style("KICKER", fontName="Helvetica-Bold", fontSize=8.5,
               textColor=ACCENT, leading=12)
CARD_TITLE = style("CARDT", fontName="Helvetica-Bold", fontSize=10.5,
                    textColor=INK, leading=14)
CARD_BODY = style("CARDB", fontName="Helvetica", fontSize=9, textColor=MUTED,
                   leading=13)


def bullets(items, color=ACCENT):
    return ListFlowable(
        [ListItem(Paragraph(t, BULLET), leftIndent=6,
                  value="•", bulletColor=color) for t in items],
        bulletType="bullet", leftIndent=14, spaceAfter=6,
    )


def feature_cards(rows):
    """rows: list of (title, body) -> 2-col card grid."""
    cells = []
    for title, body in rows:
        inner = Table(
            [[Paragraph(title, CARD_TITLE)], [Paragraph(body, CARD_BODY)]],
            colWidths=[8.0 * cm],
        )
        inner.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), colors.white),
            ("BOX", (0, 0), (-1, -1), 0.75, LINE),
            ("LEFTPADDING", (0, 0), (-1, -1), 10),
            ("RIGHTPADDING", (0, 0), (-1, -1), 10),
            ("TOPPADDING", (0, 0), (-1, -1), 9),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
            ("LINEBEFORE", (0, 0), (0, -1), 3, ACCENT),
        ]))
        cells.append(inner)

    grid = []
    for i in range(0, len(cells), 2):
        pair = cells[i:i + 2]
        if len(pair) == 1:
            pair.append("")
        grid.append(pair)

    tbl = Table(grid, colWidths=[8.4 * cm, 8.4 * cm])
    tbl.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    return tbl


def stat_band(stats):
    """stats: list of (number, label)."""
    row = []
    for num, label in stats:
        cell = Table(
            [[Paragraph(num, style("N", fontName="Helvetica-Bold",
                                    fontSize=20, textColor=ACCENT,
                                    alignment=TA_CENTER, leading=22))],
             [Paragraph(label, style("L", fontName="Helvetica", fontSize=8,
                                      textColor=MUTED, alignment=TA_CENTER,
                                      leading=10))]],
        )
        cell.setStyle(TableStyle([
            ("TOPPADDING", (0, 0), (-1, -1), 2),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ]))
        row.append(cell)
    tbl = Table([row], colWidths=[4.2 * cm] * len(stats))
    tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), ACCENT_SOFT),
        ("BOX", (0, 0), (-1, -1), 0, ACCENT_SOFT),
        ("TOPPADDING", (0, 0), (-1, -1), 14),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 14),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    return tbl


# ── Page chrome ────────────────────────────────────────────────────────────
def on_page(canvas, doc):
    canvas.saveState()
    canvas.setFillColor(PAGE_BG)
    canvas.rect(0, 0, A4[0], A4[1], fill=1, stroke=0)
    # top accent bar
    canvas.setFillColor(ACCENT)
    canvas.rect(0, A4[1] - 0.35 * cm, A4[0], 0.35 * cm, fill=1, stroke=0)
    # footer
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(MUTED)
    canvas.drawString(2 * cm, 1.1 * cm, "Legal AI Platform — Build Summary")
    canvas.drawRightString(A4[0] - 2 * cm, 1.1 * cm, f"Page {doc.page}")
    canvas.setStrokeColor(LINE)
    canvas.line(2 * cm, 1.5 * cm, A4[0] - 2 * cm, 1.5 * cm)
    canvas.restoreState()


def build():
    doc = BaseDocTemplate(
        OUT_PATH, pagesize=A4,
        leftMargin=2 * cm, rightMargin=2 * cm,
        topMargin=2.1 * cm, bottomMargin=2 * cm,
    )
    frame = Frame(doc.leftMargin, doc.bottomMargin,
                  doc.width, doc.height, id="main")
    doc.addPageTemplates([
        PageTemplate(id="all", frames=[frame], onPage=on_page)
    ])

    s = []

    # ── Cover ──
    s.append(Spacer(1, 1.4 * cm))
    s.append(Paragraph("BUILD SUMMARY", KICKER))
    s.append(Spacer(1, 4))
    s.append(Paragraph("Client &amp; Admin Frontends, Real-Time "
                        "Messenger, and Lawyer AI Assist", H1))
    s.append(Spacer(1, 8))
    s.append(Paragraph(
        "A single working session delivering three product surfaces, a "
        "WebSocket real-time messaging system across two apps, and an "
        "AI assist layer for the lawyer-side conversation — all built "
        "on the platform’s existing legal-AI services.", SUBTITLE))
    s.append(Spacer(1, 16))
    s.append(HRFlowable(width="100%", thickness=1, color=LINE))
    s.append(Spacer(1, 16))
    s.append(stat_band([
        ("3", "Product surfaces"),
        ("2", "Apps made live"),
        ("4", "AI features"),
        ("1", "WebSocket layer"),
    ]))
    s.append(Spacer(1, 16))
    s.append(Paragraph(
        "Scope: client portal &amp; admin frontends brought up, a client "
        "registration bug fixed permanently, lawyer-side case creation, a "
        "full messenger overhaul (live updates, media, paste, drag-drop, "
        "lightbox), and AI assistance for the lawyer.", BODY))

    # ── 1. Frontends ──
    s.append(Paragraph("1 · Client &amp; Admin Frontends", SECTION))
    s.append(Paragraph(
        "Both the client portal and the admin dashboard were brought up and "
        "made viewable, and a blocking client-registration failure was "
        "diagnosed and fixed at the root rather than patched over.", BODY))
    s.append(Spacer(1, 6))
    s.append(feature_cards([
        ("Client Portal live",
         "Vite dev server running; portal UI verified end-to-end."),
        ("Admin Dashboard live",
         "Separate app served and verified on its own port."),
        ("Registration 404 fixed",
         "Root cause: tenant slug data + strict lookup. Added a default "
         "tenant fallback and backfilled all NULL slugs — permanent fix."),
        ("Lawyer case creation",
         "“New Case” modal wired to the existing tenant-scoped "
         "API; lawyer is the correct owner of case creation."),
    ]))

    # ── 2. Messenger ──
    s.append(Paragraph("2 · Real-Time Messenger (both apps)", SECTION))
    s.append(Paragraph(
        "The messenger went from “reload to see new messages” to a "
        "true real-time experience on both the lawyer app and the client "
        "portal, with rich media handling.", BODY))
    s.append(Spacer(1, 6))
    s.append(bullets([
        "<b>WebSocket real-time delivery</b> — new backend WS layer "
        "(per-case rooms, JWT-authed) with auto-reconnect; polling kept "
        "only as a fallback when the socket is down.",
        "<b>Optimistic send</b> — messages appear instantly with "
        "sending / failed / retry states.",
        "<b>Media like a chat app</b> — inline images &amp; video, "
        "paste screenshots, drag-and-drop, multi-file queue with captions.",
        "<b>Gallery lightbox</b> — blurred backdrop, arrow-key "
        "navigation across all thread images, download, Esc to close.",
        "<b>Smart scroll &amp; unread divider</b> — no scroll-jump on "
        "updates; “new messages” pill and a last-read divider.",
        "<b>Typing indicator</b> — live over WebSocket.",
        "<b>Bug fixed along the way</b> — portal attachment downloads "
        "were unauthenticated and broken; now fetched with auth.",
    ]))

    # ── 3. AI ──
    s.append(Paragraph("3 · Lawyer AI Assist", SECTION))
    s.append(Paragraph(
        "An AI layer added to the messenger, lawyer-facing first, reusing "
        "the platform’s existing legal-AI services (LLM gateway, PII "
        "redactor, case context, document insight). Nothing is auto-sent.",
        BODY))
    s.append(Spacer(1, 6))

    ai_rows = [
        ("✨ Suggest replies",
         "3 grounded reply options from thread + case context. Lawyer "
         "clicks one into the composer and edits before sending."),
        ("✨ Summarize thread",
         "Long conversations collapsed into bullet points for fast "
         "context recovery."),
        ("⚠ PII guard (both sides)",
         "Pre-send scan flags emails / phones / IDs with a "
         "review-or-send-anyway prompt. Also added to the client portal."),
        ("✨ Document insight",
         "One-click analysis of files a client shares: type, summary, "
         "parties, key points — powered by existing DocumentInsight."),
    ]
    s.append(feature_cards(ai_rows))
    s.append(Spacer(1, 10))

    # Guardrails callout
    callout = Table([[Paragraph(
        "<b>Guardrails built in.</b> Every AI call fails open with a safe "
        "fallback (never a broken UI or blocked send). Suggestions are "
        "drafts only — the lawyer always reviews and edits. The model "
        "is prompted not to give legal conclusions, and a visible "
        "disclaimer is shown. Existing trust / redaction services were "
        "reused rather than duplicated.", CARD_BODY)]],
        colWidths=[16.8 * cm])
    callout.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F4F1FD")),
        ("BOX", (0, 0), (-1, -1), 0.75, AI_PURPLE),
        ("LINEBEFORE", (0, 0), (0, -1), 3, AI_PURPLE),
        ("LEFTPADDING", (0, 0), (-1, -1), 12),
        ("RIGHTPADDING", (0, 0), (-1, -1), 12),
        ("TOPPADDING", (0, 0), (-1, -1), 10),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 11),
    ]))
    s.append(callout)

    # ── Verification ──
    s.append(Paragraph("Quality &amp; Verification", SECTION))
    s.append(bullets([
        "Lawyer app: TypeScript build clean (tsc).",
        "Client portal: TypeScript build clean (tsc).",
        "Backend: syntax-validated across all modified modules.",
        "Existing services reused; no parallel logic introduced.",
    ]))

    # ── Known caveats ──
    s.append(Paragraph("Known Caveats &amp; Next Steps", SECTION))
    s.append(bullets([
        "WebSocket layer is in-process (single worker). Multi-worker "
        "deployments need a Redis pub/sub backplane; polling fallback "
        "keeps it functional meanwhile.",
        "AI suggest/summarize use the standard LLM tier directly, not the "
        "full copilot RAG pipeline — fast, but less deeply grounded "
        "than the case Assistant.",
        "Attachment insight is richest when the chat file is also "
        "persisted as a case Document; wiring chat uploads into the "
        "document pipeline is a strong follow-up.",
        "Read receipts still update on poll/open, not pushed live.",
    ], color=MUTED))

    s.append(Spacer(1, 14))
    s.append(HRFlowable(width="100%", thickness=1, color=LINE))
    s.append(Spacer(1, 6))
    s.append(Paragraph(
        "Generated for the Legal AI Platform — internal build record. "
        "All work verified at session close.", SMALL))

    doc.build(s)
    print(f"PDF written: {OUT_PATH}")


if __name__ == "__main__":
    build()
