"""
Generates a premium, consulting-grade PDF execution plan for the Legal AI Platform.
Output: C:/Users/ahmed/Desktop/upgrades pfe/PFE_EXECUTION_PLAN_LOCKED.pdf
"""
from __future__ import annotations

from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm, mm
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    KeepTogether,
    NextPageTemplate,
    PageBreak,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)

# ---------------------------------------------------------------------------
# Brand
# ---------------------------------------------------------------------------
INK = colors.HexColor("#0F1A2B")
INK_SOFT = colors.HexColor("#3A4A60")
ACCENT = colors.HexColor("#0E7C66")        # legal/forest
ACCENT_SOFT = colors.HexColor("#E5F4F0")
WARN = colors.HexColor("#B85A1A")
RULE = colors.HexColor("#D4DBE3")
PANEL = colors.HexColor("#F7F9FB")
WHITE = colors.white
MUTED = colors.HexColor("#6B7B91")

# ---------------------------------------------------------------------------
# Styles
# ---------------------------------------------------------------------------
styles = getSampleStyleSheet()

H_TITLE = ParagraphStyle(
    "HTitle", parent=styles["Title"], fontName="Helvetica-Bold",
    fontSize=28, leading=34, textColor=INK, spaceAfter=6,
)
H_SUB = ParagraphStyle(
    "HSub", parent=styles["Normal"], fontName="Helvetica",
    fontSize=12, leading=16, textColor=INK_SOFT, spaceAfter=4,
)
H_KICKER = ParagraphStyle(
    "Kicker", parent=styles["Normal"], fontName="Helvetica-Bold",
    fontSize=9, leading=12, textColor=ACCENT, spaceAfter=4, letterSpacing=2,
)
H1 = ParagraphStyle(
    "H1", parent=styles["Heading1"], fontName="Helvetica-Bold",
    fontSize=20, leading=26, textColor=INK, spaceBefore=10, spaceAfter=10,
)
H2 = ParagraphStyle(
    "H2", parent=styles["Heading2"], fontName="Helvetica-Bold",
    fontSize=14, leading=18, textColor=INK, spaceBefore=8, spaceAfter=6,
)
H3 = ParagraphStyle(
    "H3", parent=styles["Heading3"], fontName="Helvetica-Bold",
    fontSize=11, leading=15, textColor=ACCENT, spaceBefore=6, spaceAfter=3,
)
BODY = ParagraphStyle(
    "Body", parent=styles["BodyText"], fontName="Helvetica",
    fontSize=10, leading=14, textColor=INK, spaceAfter=4, alignment=TA_JUSTIFY,
)
BODY_SOFT = ParagraphStyle(
    "BodySoft", parent=BODY, textColor=INK_SOFT,
)
BULLET = ParagraphStyle(
    "Bullet", parent=BODY, leftIndent=12, bulletIndent=2, spaceAfter=2,
)
SMALL = ParagraphStyle(
    "Small", parent=styles["Normal"], fontName="Helvetica",
    fontSize=8, leading=11, textColor=MUTED,
)
QUOTE = ParagraphStyle(
    "Quote", parent=BODY, fontName="Helvetica-Oblique",
    leftIndent=14, rightIndent=14, textColor=INK_SOFT,
    borderPadding=10, spaceAfter=8, spaceBefore=8,
)
CALLOUT = ParagraphStyle(
    "Callout", parent=BODY, textColor=INK, fontName="Helvetica-Bold",
    backColor=ACCENT_SOFT, borderPadding=10, spaceAfter=8, spaceBefore=8,
)
RULE_TXT = ParagraphStyle(
    "Rule", parent=BODY, fontName="Helvetica-Bold", textColor=WARN,
)
CENTER = ParagraphStyle("Center", parent=BODY, alignment=TA_CENTER)


# ---------------------------------------------------------------------------
# Page chrome
# ---------------------------------------------------------------------------
def _draw_cover_bg(canvas, doc):
    canvas.saveState()
    w, h = A4
    canvas.setFillColor(INK)
    canvas.rect(0, 0, w, h, fill=1, stroke=0)
    # accent ribbon
    canvas.setFillColor(ACCENT)
    canvas.rect(0, h - 8 * cm, w, 0.35 * cm, fill=1, stroke=0)
    canvas.restoreState()


def _draw_page_chrome(canvas, doc):
    canvas.saveState()
    w, h = A4

    # top accent line
    canvas.setStrokeColor(RULE)
    canvas.setLineWidth(0.4)
    canvas.line(2 * cm, h - 1.6 * cm, w - 2 * cm, h - 1.6 * cm)

    # header
    canvas.setFont("Helvetica-Bold", 8)
    canvas.setFillColor(ACCENT)
    canvas.drawString(2 * cm, h - 1.25 * cm, "LEGAL AI  ·  PFE EXECUTION PLAN")
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(MUTED)
    canvas.drawRightString(w - 2 * cm, h - 1.25 * cm, "LOCKED  ·  NON-NEGOTIABLE")

    # footer
    canvas.setStrokeColor(RULE)
    canvas.line(2 * cm, 1.5 * cm, w - 2 * cm, 1.5 * cm)
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(MUTED)
    canvas.drawString(2 * cm, 1.0 * cm, "Ahmed  ·  Legal AI Platform")
    canvas.drawCentredString(w / 2, 1.0 * cm, "8-Week Plan  ·  May 4 → June 28, 2026")
    canvas.drawRightString(w - 2 * cm, 1.0 * cm, f"Page {doc.page}")
    canvas.restoreState()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def hr(color=RULE, height=0.6, space=6):
    t = Table([[""]], colWidths=[17 * cm], rowHeights=[height])
    t.setStyle(TableStyle([("LINEBELOW", (0, 0), (-1, -1), height, color)]))
    return [Spacer(1, space), t, Spacer(1, space)]


def callout(text):
    return Paragraph(f"<b>★ </b>{text}", CALLOUT)


def rule_para(text):
    return Paragraph(f"⛔  {text}", RULE_TXT)


def bullets(items):
    return [Paragraph(f"•&nbsp;&nbsp;{x}", BULLET) for x in items]


def kv_table(rows, col_widths=(5.5 * cm, 11 * cm)):
    data = []
    for k, v in rows:
        data.append([Paragraph(f"<b>{k}</b>", BODY), Paragraph(v, BODY)])
    t = Table(data, colWidths=list(col_widths))
    t.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("BACKGROUND", (0, 0), (0, -1), PANEL),
        ("BOX", (0, 0), (-1, -1), 0.4, RULE),
        ("INNERGRID", (0, 0), (-1, -1), 0.4, RULE),
    ]))
    return t


def sprint_card(week_no, dates, title, objective, backend, frontend, ai_tasks,
                deliverable, dod):
    head_data = [[
        Paragraph(f"<b>WEEK {week_no}</b>", ParagraphStyle(
            "wk", parent=BODY, textColor=WHITE, fontName="Helvetica-Bold",
            fontSize=11, alignment=TA_CENTER)),
        Paragraph(f"<b>{title}</b>", ParagraphStyle(
            "wt", parent=BODY, textColor=WHITE, fontName="Helvetica-Bold",
            fontSize=12)),
        Paragraph(dates, ParagraphStyle(
            "wd", parent=BODY, textColor=WHITE, fontName="Helvetica",
            fontSize=9, alignment=2)),
    ]]
    head = Table(head_data, colWidths=[2.4 * cm, 10.6 * cm, 4 * cm])
    head.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), ACCENT),
        ("BACKGROUND", (0, 0), (0, 0), INK),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
        ("RIGHTPADDING", (0, 0), (-1, -1), 10),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
    ]))

    def block(lbl, items):
        body = "<br/>".join(f"•  {x}" for x in items) if items else "—"
        return [
            Paragraph(f"<b>{lbl}</b>", ParagraphStyle(
                "lbl", parent=BODY, textColor=ACCENT, fontName="Helvetica-Bold",
                fontSize=9, spaceAfter=2)),
            Paragraph(body, ParagraphStyle(
                "blk", parent=BODY, fontSize=9.5, leading=13)),
            Spacer(1, 4),
        ]

    body_data = [[
        block("OBJECTIVE", [objective])
        + block("BACKEND", backend)
        + block("FRONTEND", frontend)
        + block("AI / ML", ai_tasks),
        block("DELIVERABLE", [deliverable])
        + block("DEFINITION OF DONE", dod),
    ]]
    body = Table(body_data, colWidths=[10 * cm, 7 * cm])
    body.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 12),
        ("RIGHTPADDING", (0, 0), (-1, -1), 12),
        ("TOPPADDING", (0, 0), (-1, -1), 10),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
        ("BACKGROUND", (0, 0), (0, -1), WHITE),
        ("BACKGROUND", (1, 0), (1, -1), PANEL),
        ("LINEBEFORE", (1, 0), (1, -1), 0.4, RULE),
        ("BOX", (0, 0), (-1, -1), 0.4, RULE),
    ]))

    return KeepTogether([head, body, Spacer(1, 12)])


# ---------------------------------------------------------------------------
# Build content
# ---------------------------------------------------------------------------
def build_story():
    s = []

    # ===== COVER =====
    s.append(Spacer(1, 5.5 * cm))
    s.append(Paragraph(
        '<font color="#7BD7C2">PFE  ·  EXECUTION PLAN  ·  LOCKED</font>',
        ParagraphStyle("ck", parent=H_KICKER, textColor=colors.HexColor("#7BD7C2"),
                       fontSize=10, alignment=TA_CENTER)))
    s.append(Spacer(1, 0.3 * cm))
    s.append(Paragraph(
        '<font color="white">Legal AI Platform</font>',
        ParagraphStyle("ct", parent=H_TITLE, textColor=WHITE, fontSize=36,
                       leading=42, alignment=TA_CENTER)))
    s.append(Spacer(1, 0.3 * cm))
    s.append(Paragraph(
        '<font color="#B7C4D6">From PFE to startup-grade product · 8 weeks · No deviation</font>',
        ParagraphStyle("cs", parent=H_SUB, textColor=colors.HexColor("#B7C4D6"),
                       fontSize=14, alignment=TA_CENTER)))
    s.append(Spacer(1, 4 * cm))

    # cover meta
    cov_data = [
        ["OWNER", "Ahmed"],
        ["WINDOW", "May 4, 2026  →  June 28, 2026"],
        ["DEFENSE", "July 2026  ·  Tunisia"],
        ["RULE", "This plan is final. No edits. No additions. No reshuffling."],
    ]
    cov = Table(cov_data, colWidths=[3.5 * cm, 12 * cm])
    cov.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("FONTNAME", (1, 0), (1, -1), "Helvetica"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("TEXTCOLOR", (0, 0), (0, -1), colors.HexColor("#7BD7C2")),
        ("TEXTCOLOR", (1, 0), (1, -1), WHITE),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("LINEBELOW", (0, 0), (-1, -1), 0.4, colors.HexColor("#2A3A55")),
    ]))
    s.append(cov)

    s.append(NextPageTemplate("body"))
    s.append(PageBreak())

    # ===== 1. EXECUTIVE OVERVIEW =====
    s.append(Paragraph("EXECUTIVE OVERVIEW", H_KICKER))
    s.append(Paragraph("Vision, outcome, and positioning", H1))
    s += hr()

    s.append(Paragraph("Vision", H2))
    s.append(Paragraph(
        "Build the first <b>Legal AI platform native to the Francophone &amp; "
        "North-African legal market</b> — case-centric, multi-agent, grounded in "
        "real legal corpora — with three production-grade interfaces "
        "(Lawyer · Client · Admin). Win the PFE jury in July, then turn this "
        "into a real SaaS company.", BODY))

    s.append(Paragraph("Final outcome (June 28, 2026)", H2))
    s += bullets([
        "Lawyer workspace: case-centric AI copilot with grounded answers, verifiable citations, drafting editor, and ML-powered document intelligence.",
        "Client portal: multi-document upload, AI Q&amp;A on their own documents, real-time case tracking — minimal, premium, mobile-friendly.",
        "Admin console: full CRUD over tenants, users, cases, documents; observability; audit log. No AI surface.",
        "ML layer: 3 trained/integrated models — Document Classifier, Legal NER, NLI Verifier — visible inside the product.",
        "Demo pack: 3 rehearsed jury scenarios + slide deck + backup video.",
    ])

    s.append(Paragraph("Positioning vs Harvey / Legora", H2))
    pos_data = [
        ["", "Harvey", "Legora", "This product"],
        ["Market", "US / UK Big Law", "EU mid-market", "Francophone + North Africa"],
        ["Languages", "EN", "EN + EU", "FR · AR · EN · DE (native)"],
        ["Local law", "Common law", "EU statutes", "Code Civil / CPC / JORT"],
        ["Price band", "Enterprise ($$$)", "Mid ($$)", "Accessible ($)"],
        ["Moat", "Data + brand", "EU compliance", "Local corpus + multilingual ML (FR/AR/EN/DE)"],
    ]
    pt = Table(pos_data, colWidths=[3 * cm, 3.6 * cm, 3.6 * cm, 4.4 * cm])
    pt.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), INK),
        ("TEXTCOLOR", (0, 0), (-1, 0), WHITE),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTNAME", (0, 1), (0, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("BACKGROUND", (3, 1), (3, -1), ACCENT_SOFT),
        ("BOX", (0, 0), (-1, -1), 0.4, RULE),
        ("INNERGRID", (0, 0), (-1, -1), 0.3, RULE),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    s.append(pt)

    s.append(Spacer(1, 8))
    s.append(callout(
        "Strategic anchor — \"I don't compete with Harvey on intelligence. "
        "I compete on data, language, and jurisdiction they will never have.\""))

    s.append(PageBreak())

    # ===== 2. ARCHITECTURE =====
    s.append(Paragraph("GLOBAL ARCHITECTURE", H_KICKER))
    s.append(Paragraph("Final form (target state, June 28)", H1))
    s += hr()

    s.append(Paragraph("Layered system", H2))
    s.append(Paragraph(
        "Three frontends share one FastAPI backend. The AI layer is split into "
        "deterministic <b>ML models</b> (trust) and <b>LLM agents</b> (fluency). "
        "Every claim returned to the user is grounded in retrieved chunks and "
        "verified by the NLI guardrail.", BODY))

    arch_rows = [
        ("Lawyer App (React + TS)",
         "Case workspace · Documents · Editor · Copilot rail · Calendar · Tasks · Analytics."),
        ("Client App (React + TS)",
         "Upload · Ask AI on my docs · Case tracking · Notifications · Mobile-first."),
        ("Admin App (React + TS)",
         "CRUD: tenants, users, cases, documents · Audit log · Health dashboard · Exports. No AI."),
        ("API Gateway (FastAPI)",
         "Auth (JWT + roles: lawyer / client / admin) · Multi-tenant scoping · Rate limit · Audit middleware."),
        ("Domain services",
         "Cases · Documents · Voice · Image batches · Calendar · Drafts · Notifications · Billing-ready."),
        ("AI orchestrator",
         "Intent routing · Multi-agent (research / draft / explain / verify) · Confidence + citation builder."),
        ("ML layer",
         "1) Document Classifier (CamemBERT)  ·  2) Legal NER (XLM-R)  ·  3) NLI Verifier (mDeBERTa zero-shot)."),
        ("RAG layer",
         "Chunking · Embeddings (sentence-camembert / e5) · FAISS · Hybrid (BM25 + dense) · Reranker."),
        ("Storage",
         "PostgreSQL (relational) · FAISS (vectors) · Object store (PDFs / audio / images)."),
        ("Observability",
         "OpenTelemetry traces · Structured logs · Latency + cost dashboards · Daily eval harness."),
    ]
    s.append(kv_table(arch_rows))

    s.append(Spacer(1, 6))
    s.append(callout(
        "Single-tenant DB schema today, multi-tenant scoping enforced at every "
        "query. Admin console is the only surface that crosses tenant lines."))

    s.append(PageBreak())

    # ===== 3. SPRINT PLAN =====
    s.append(Paragraph("8-WEEK SPRINT PLAN", H_KICKER))
    s.append(Paragraph("The only roadmap that exists", H1))
    s += hr()
    s.append(Paragraph(
        "Each sprint is one calendar week, Monday → Sunday. Sprint reviews on "
        "Sunday evening. <b>You cannot start sprint N+1 if sprint N's "
        "Definition of Done is not green.</b>", BODY_SOFT))
    s.append(Spacer(1, 8))

    sprints = [
        dict(
            week_no=1, dates="May 4 → May 10",
            title="Stabilization + Foundations",
            objective="Zero crashes. Foundation for 3 frontends + role system. Production-shape backend.",
            backend=[
                "Add Role enum to User: lawyer / client / admin (migration).",
                "Per-role auth middleware + route scoping decorators.",
                "Audit log table + middleware capturing every mutating request.",
                "Standardize error envelopes (problem+json) across all routers.",
                "Rate limiter (slowapi) on auth + AI endpoints.",
                "Fix every 500: full click-through QA pass, log every error.",
            ],
            frontend=[
                "Click-through QA on lawyer app: every page, every modal, every empty state.",
                "Bootstrap client-portal app shell (router, auth, theme tokens shared with lawyer app).",
                "Bootstrap admin app shell (router, auth, theme).",
                "Toast system + global error boundary across all 3 apps.",
            ],
            ai_tasks=[
                "Freeze prompts. Snapshot current eval scores as baseline.",
                "Add LLM call cost + latency logging.",
            ],
            deliverable="3 deployable apps, role-based login, audit log, zero 500s.",
            dod=[
                "All 131 tests pass.",
                "Manual QA bug list = 0 open.",
                "Logging in as lawyer / client / admin lands on the right shell.",
                "Audit log records last 24h of activity.",
            ],
        ),
        dict(
            week_no=2, dates="May 11 → May 17",
            title="Lawyer Workspace v2 + Verifier (Wow #1)",
            objective="Ship verifiable citations. This is the single biggest trust upgrade.",
            backend=[
                "POST /copilot/verify — runs mDeBERTa NLI on (claim, retrieved_chunk).",
                "Citation builder: every LLM sentence → list of supporting chunk IDs + char offsets.",
                "PDF coordinate index per chunk (page + bbox) so frontend can highlight.",
                "Confidence aggregation per answer (entail × retrieval score).",
            ],
            frontend=[
                "Copilot answer renderer: numbered superscripts [¹] [²] linked to source chips.",
                "Click citation → opens PDF preview at exact page with bbox highlight.",
                "Confidence pill + 'Sources used' panel on every answer.",
                "Unsupported sentences highlighted in amber with hover explanation.",
            ],
            ai_tasks=[
                "Integrate `MoritzLaurer/mDeBERTa-v3-base-xnli...` (zero-shot, no training).",
                "Add 'verifier' as last step in copilot pipeline.",
                "Eval: precision/recall of unsupported-claim detection on 50 hand-labeled answers.",
            ],
            deliverable="Every copilot answer ships with inline citations + verifier badge.",
            dod=[
                "Click [¹] in any answer → PDF opens at correct page with highlight.",
                "Verifier flags ≥ 80% of injected fake claims in the eval set.",
                "Demo scenario #1 (\"From email to memo in 90 s\") works end-to-end.",
            ],
        ),
        dict(
            week_no=3, dates="May 18 → May 24",
            title="Client Portal v1 + Document Classifier (ML #1)",
            objective="Lawyers stop emailing clients. Clients self-serve. First trained model in production.",
            backend=[
                "POST /portal/cases — clients see only their own cases (tenant + client_id scope).",
                "POST /portal/documents/upload — multi-file (max 10), auto-classify, attach to case.",
                "GET /portal/cases/{id}/timeline — public-safe events only.",
                "POST /portal/ask — copilot scoped to client's documents only.",
                "Email/SMS notification stubs on case status changes.",
            ],
            frontend=[
                "Client app: login, case list, case detail, upload (drag-drop, max 10).",
                "Client AI chat: simple, single-thread, citations to their own docs only.",
                "Mobile-first layout (responsive ≤ 480 px).",
                "Empty states + onboarding for first-time clients.",
            ],
            ai_tasks=[
                "Fine-tune CamemBERT classifier (10 classes) using LLM-assisted labeling.",
                "Pipeline: PDF → text → classifier → tag (contract / judgment / summons / ...).",
                "Auto-tag every uploaded document on upload + backfill existing.",
                "Show predicted type + confidence in document list (badge).",
            ],
            deliverable="Live client portal + every uploaded doc auto-classified.",
            dod=[
                "Held-out F1 on classifier ≥ 0.85 across top 6 classes.",
                "Client uploads PDF → tag appears in <2 s in lawyer view.",
                "Client cannot see another client's data (verified test).",
            ],
        ),
        dict(
            week_no=4, dates="May 25 → May 31",
            title="Admin Console + Hybrid RAG",
            objective="Ship the admin spine. Make retrieval measurably better.",
            backend=[
                "Admin endpoints: tenants, users, cases, documents — full CRUD with pagination + search.",
                "Bulk actions (export CSV, bulk-archive, role change).",
                "Hybrid retriever: BM25 + dense, weighted fusion.",
                "Reranker (cross-encoder, e.g. bge-reranker-v2-m3) on top-k.",
                "Audit log viewer endpoint with filters.",
            ],
            frontend=[
                "Admin app: tables for users / cases / documents (sortable, filterable).",
                "Modal-based CRUD with optimistic updates.",
                "Audit log timeline view with actor + diff.",
                "System health dashboard (counts, AI cost, error rate).",
            ],
            ai_tasks=[
                "Retrieval eval: recall@5 before/after hybrid + reranker (target +15%).",
                "Persist retrieval metrics in DB for the dashboard.",
            ],
            deliverable="Admin can run the platform without DB access. RAG measurably better.",
            dod=[
                "All CRUD actions work + are audit-logged.",
                "Hybrid + reranker live; recall@5 improvement charted.",
                "Health dashboard live data.",
            ],
        ),
        dict(
            week_no=5, dates="June 1 → June 7",
            title="Document Editor + Drafting Agent (Wow #2)",
            objective="Notion-grade editor with inline AI. This is what lawyers fall in love with.",
            backend=[
                "Draft documents: store as JSON tree + Markdown render.",
                "Versioning + diff endpoint (per-block diff).",
                "POST /draft/{id}/ai — slash-command AI invoking drafting agent with citations.",
                "Export to PDF + DOCX.",
            ],
            frontend=[
                "Block editor (TipTap or Lexical): paragraphs, headings, lists, quote, table.",
                "Slash menu: /summary /clause /rewrite /translate /cite.",
                "⌘K command palette (global) + ⌘/ shortcut help.",
                "Right-margin: live citation chips + risk flags from NER.",
                "Track changes + version history viewer.",
            ],
            ai_tasks=[
                "Drafting agent: clause generation grounded in case docs + corpus.",
                "Style adapter: 'plain language for client' vs 'formal for filing'.",
            ],
            deliverable="Lawyer drafts a legal memo with AI in the editor and exports a PDF.",
            dod=[
                "Slash-AI returns text + citations live in the editor.",
                "Version history shows last 10 versions with diff.",
                "Export PDF preserves formatting and citations.",
            ],
        ),
        dict(
            week_no=6, dates="June 8 → June 14",
            title="Legal NER + Timeline + Deadlines (Wow #3)",
            objective="Auto-build a case timeline from raw documents. Nobody does this locally.",
            backend=[
                "Run Legal NER on every uploaded doc (PERSON / DATE / MONEY / LAW_REF / DEADLINE).",
                "Persist entities in DB with source span + confidence.",
                "Timeline service: aggregate dated events from NER + manual entries.",
                "Deadline engine: jurisdiction-aware date math (Tunisian CPC rules table).",
            ],
            frontend=[
                "Visual case timeline (vertical, filterable by entity type).",
                "Deadlines tab with critical-day highlights.",
                "'Risk heatmap' view per case (counts by entity / risk).",
                "Calendar integration: deadlines auto-populate calendar.",
            ],
            ai_tasks=[
                "Fine-tune XLM-R NER on WikiNER-FR + 200 hand-labeled legal sentences.",
                "Anomaly score per clause via Isolation Forest on embeddings.",
                "Per-document insight cards: parties · dates · risks · obligations.",
            ],
            deliverable="Drop a case folder → see timeline, deadlines, risks in one minute.",
            dod=[
                "NER held-out F1 ≥ 0.78 on 5 entity classes.",
                "Demo scenario #2 (\"Deadline saved your client\") runs end-to-end.",
                "Timeline renders for a case with ≥ 10 docs in < 3 s.",
            ],
        ),
        dict(
            week_no=7, dates="June 15 → June 21",
            title="Polish, Performance, Demo Engineering",
            objective="Make it feel premium. Make it fast. Lock the demos.",
            backend=[
                "Cache layer (Redis or in-memory) for hot reads.",
                "Move heavy ingestion to a queue (Arq / RQ).",
                "Add OpenTelemetry traces around AI pipeline.",
                "Daily eval harness in CI (regression on copilot answers).",
            ],
            frontend=[
                "Skeleton loaders everywhere. Optimistic mutations.",
                "Empty-state pass on every page (one CTA each).",
                "Keyboard shortcut sheet (⌘ /).",
                "Polish micro-interactions: toasts, transitions, focus states.",
                "Mobile pass on lawyer + client apps.",
            ],
            ai_tasks=[
                "Lock the 3 demo scenarios. Pre-seed the demo dataset.",
                "Record fallback video of each demo (in case live fails).",
                "One-click 'Reset demo data' admin button.",
            ],
            deliverable="Product feels premium. Demos rehearsed. Backups in place.",
            dod=[
                "P95 page load < 1.2 s on lawyer app.",
                "All 3 demo scenarios run < 3 minutes each.",
                "Backup videos recorded for all 3 scenarios.",
            ],
        ),
        dict(
            week_no=8, dates="June 22 → June 28",
            title="Defense Prep + Documentation",
            objective="Slides, mock soutenance, written report, freeze.",
            backend=[
                "Code freeze on June 25. Only critical-bug fixes after that.",
                "Generate API docs (OpenAPI export + screenshots).",
                "Final test pass + coverage report.",
            ],
            frontend=[
                "Final accessibility pass (focus, alt text, contrast).",
                "Final pixel pass on demo screens.",
            ],
            ai_tasks=[
                "Final eval run: classifier F1 · NER F1 · NLI precision/recall · RAG recall@5.",
                "Build the 'Corpus &amp; Models' dashboard inside admin (real numbers).",
            ],
            deliverable="Slides, written report, mock defense done.",
            dod=[
                "Slide deck (≤ 25 slides) reviewed by supervisor.",
                "PFE written report submitted.",
                "2 mock defenses completed with peers + supervisor.",
                "Sleep ≥ 7h the 3 nights before the real defense.",
            ],
        ),
    ]

    for sp in sprints:
        s.append(sprint_card(**sp))

    s.append(PageBreak())

    # ===== 4. INTERFACES =====
    s.append(Paragraph("INTERFACES", H_KICKER))
    s.append(Paragraph("Lawyer · Client · Admin", H1))
    s += hr()

    # Lawyer
    s.append(Paragraph("Lawyer interface (advanced, AI-first)", H2))
    s += bullets([
        "<b>Inbox</b> — AI-prioritized actions (contracts to review, deadlines, client replies).",
        "<b>Cases</b> — portfolio + matter detail (Overview · Documents · Editor · Timeline · Calendar · Assistant · Tasks).",
        "<b>Documents</b> — queue, preview modal, archive view + restore, filters, AI auto-tags.",
        "<b>Editor</b> — block-based drafting with slash AI, citations, versioning, export.",
        "<b>Research</b> — cross-case + corpus search with hybrid RAG.",
        "<b>Calendar</b> — hearings + auto-computed deadlines.",
        "<b>Analytics</b> — billable time, AI usage, doc volume.",
        "<b>Settings</b> — profile, team, integrations, billing-ready.",
        "<b>Always-on right rail copilot</b> — context-aware to current case.",
    ])

    # Client
    s.append(Paragraph("Client interface (simple, AI-assisted)", H2))
    s += bullets([
        "<b>Login + onboarding</b> — magic link or email/password.",
        "<b>My cases</b> — read-only status, lawyer name, next step, deadline.",
        "<b>Upload documents</b> — drag-drop multi-file (max 10), auto-classification.",
        "<b>Ask AI about my documents</b> — simple chat, citations to client's own docs.",
        "<b>Messages</b> — channel with assigned lawyer (file-friendly).",
        "<b>Notifications</b> — email + in-app on status / deadline.",
        "<b>Mobile-first</b> — same UX on phone and desktop.",
    ])

    # Admin
    s.append(Paragraph("Admin console (CRUD-only, no AI surface)", H2))
    s += bullets([
        "<b>Tenants</b> — list, create, suspend, plan.",
        "<b>Users</b> — list, search, role change, impersonate (audited), reset password.",
        "<b>Cases</b> — full table, filters, force-archive, transfer ownership.",
        "<b>Documents</b> — global view, integrity checks, retention policy enforcement.",
        "<b>Audit log</b> — who/what/when, filterable, exportable.",
        "<b>System health</b> — error rate, AI cost, latency, queue depth.",
        "<b>Exports</b> — CSV/JSON exports per entity.",
        "<b>Feature flags</b> — toggle experiments per tenant.",
    ])

    s.append(Spacer(1, 6))
    s.append(callout(
        "Design language is shared across all 3 apps (same tokens, same components). "
        "What changes is information density and feature surface — not look-and-feel."))

    s.append(PageBreak())

    # ===== 5. AI ROADMAP =====
    s.append(Paragraph("AI ROADMAP", H_KICKER))
    s.append(Paragraph("ML + Agents — what ships, in what order", H1))
    s += hr()

    ai_rows = [
        ("RAG v2 (Week 4)",
         "Hybrid BM25 + dense + cross-encoder reranker. Target +15% recall@5."),
        ("NLI Verifier (Week 2)",
         "mDeBERTa zero-shot. Flags every unsupported sentence. Powers verifiable citations."),
        ("Document Classifier (Week 3)",
         "Fine-tuned CamemBERT, 10 classes. Auto-tags every upload."),
        ("Legal NER (Week 6)",
         "Fine-tuned XLM-R: PERSON, DATE, MONEY, LAW_REF, DEADLINE. Powers timeline + risk view."),
        ("Drafting agent (Week 5)",
         "Clause + memo generator grounded in case docs + corpus. Style adapter (formal vs plain)."),
        ("Multi-agent orchestration",
         "Existing intent router + new chain: Research → Draft → Verifier (visible 'reasoning trace')."),
        ("Anomaly detector (Week 6)",
         "Isolation Forest on clause embeddings. Drives the risk heatmap."),
        ("Eval harness",
         "Daily regression in CI: classifier F1 · NER F1 · NLI P/R · RAG recall@5 · LLM accuracy."),
    ]
    s.append(kv_table(ai_rows))

    s.append(Spacer(1, 6))
    s.append(callout(
        "Every AI feature shipped in this plan is measurable. Each gets a "
        "screenshot of its metric on the jury slide deck."))

    s.append(PageBreak())

    # ===== 6. STRICT EXECUTION RULES =====
    s.append(Paragraph("STRICT EXECUTION RULES", H_KICKER))
    s.append(Paragraph("Read this every Monday morning", H1))
    s += hr()

    rules = [
        "This plan is locked. You will not edit it. You will not reorder sprints.",
        "No new feature outside this document is allowed. Write the idea in /ideas-parking.md and forget it until July.",
        "You cannot start sprint N+1 if sprint N's Definition of Done is not green.",
        "If a sprint slips by > 2 days, cut scope inside that sprint — never push other sprints.",
        "No refactor for elegance. Code quality work is post-July.",
        "No new pages, no new agents, no new models beyond the 3 listed.",
        "If you want to change the plan, you must wait 24h. Then you still don't change it.",
        "Each Sunday 21:00 → 30-min self-review: what shipped, what didn't, why.",
        "If something is not in the demo or on a slide, it does not get built before July.",
        "Sleep ≥ 7h. Tired engineers ship bugs the jury will see.",
    ]
    for r in rules:
        s.append(rule_para(r))

    s.append(Spacer(1, 8))
    s.append(callout(
        "The single biggest risk to this project is not technical. It is you "
        "deciding to change the plan in week 3. Pre-commit now: you won't."))

    s.append(PageBreak())

    # ===== 7. DAILY WORK SYSTEM =====
    s.append(Paragraph("DAILY WORK SYSTEM", H_KICKER))
    s.append(Paragraph("Six hours that ship the future", H1))
    s += hr()

    sched = [
        ("09:00 – 09:15", "Plan", "Open Sprint card. Pick the 3 outcomes for today. Write them down."),
        ("09:15 – 11:00", "Deep work #1", "Hardest task first. No phone. No Slack. No email."),
        ("11:00 – 11:15", "Break", "Walk. Water. Look at something not a screen."),
        ("11:15 – 13:00", "Deep work #2", "Continue the hardest task or move to second priority."),
        ("13:00 – 14:00", "Lunch", "Real food. Off the computer."),
        ("14:00 – 15:30", "Build / ship", "Frontend, polish, integration. Lower-cognitive-load tasks."),
        ("15:30 – 16:00", "Test pass", "Click-through QA on what you shipped today."),
        ("16:00 – 16:30", "Commit + push + log", "git push. Update LABELING_LOG.md / SPRINT_LOG.md."),
        ("Sun 21:00", "Sprint review", "30 min: shipped vs DoD. Write 5 lines in advancement/."),
    ]
    sched_data = [["TIME", "BLOCK", "WHAT"]] + [[a, b, c] for a, b, c in sched]
    st = Table(sched_data, colWidths=[3.2 * cm, 3.2 * cm, 10.6 * cm])
    st.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), INK),
        ("TEXTCOLOR", (0, 0), (-1, 0), WHITE),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("FONTNAME", (0, 1), (1, -1), "Helvetica-Bold"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("BOX", (0, 0), (-1, -1), 0.4, RULE),
        ("INNERGRID", (0, 0), (-1, -1), 0.3, RULE),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("BACKGROUND", (0, 9), (-1, 9), ACCENT_SOFT),
    ]))
    s.append(st)

    s.append(Paragraph("Focus levers", H2))
    s += bullets([
        "<b>One sprint at a time.</b> Sprint card is the only thing on screen at 09:00.",
        "<b>One task at a time.</b> Open issues = 1. Always.",
        "<b>Shipping over polishing.</b> A merged PR &gt; a perfect branch.",
        "<b>Visible progress.</b> Update the sprint log every single day.",
        "<b>Energy hygiene.</b> Sleep, sun, food, water. Non-negotiable.",
    ])

    s.append(PageBreak())

    # ===== 8. MILESTONES & METRICS =====
    s.append(Paragraph("MILESTONES &amp; METRICS", H_KICKER))
    s.append(Paragraph("How you know you're winning", H1))
    s += hr()

    m_data = [
        ["Milestone", "By", "Metric"],
        ["Stabilization done", "May 10", "0 open 500s · 100% tests pass"],
        ["Verifier live", "May 17", "≥ 80% recall on injected fake claims"],
        ["Client portal live", "May 24", "Real client uploads + classifies in <2 s"],
        ["Admin + hybrid RAG", "May 31", "Recall@5 +15% vs baseline"],
        ["Editor + drafting", "June 7", "Memo generated + exported as PDF"],
        ["Timeline + deadlines", "June 14", "NER F1 ≥ 0.78 · timeline renders <3 s"],
        ["Demo-ready", "June 21", "3 demos < 3 min each · backup videos"],
        ["Defense-ready", "June 28", "Slides + report + 2 mock defenses"],
    ]
    mt = Table(m_data, colWidths=[5.6 * cm, 2.8 * cm, 8.6 * cm])
    mt.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), INK),
        ("TEXTCOLOR", (0, 0), (-1, 0), WHITE),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("FONTNAME", (0, 1), (0, -1), "Helvetica-Bold"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("BOX", (0, 0), (-1, -1), 0.4, RULE),
        ("INNERGRID", (0, 0), (-1, -1), 0.3, RULE),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    s.append(mt)

    s.append(Spacer(1, 12))
    s.append(callout(
        "If you fail one milestone, you cut scope inside that sprint. You do "
        "not push the next milestone. Ever."))

    s.append(PageBreak())

    # ===== 9. CLOSING =====
    s.append(Paragraph("CONTRACT WITH YOURSELF", H_KICKER))
    s.append(Paragraph("Sign this. Read it on hard days.", H1))
    s += hr()

    s.append(Paragraph(
        "I, Ahmed, commit to this plan from May 4 to June 28, 2026. I will "
        "follow the sprint order without changes. I will ship a 17/20+ PFE in "
        "July. I will treat this project as the first version of a real "
        "company. I will not let perfectionism stop me from shipping. I will "
        "sleep, train, eat well. I will measure progress weekly. I will sign "
        "below.", BODY))

    s.append(Spacer(1, 30))
    sig = Table([
        ["Signed", "_____________________________"],
        ["Date", "_____________________________"],
        ["Defense target", "July 2026"],
    ], colWidths=[3.5 * cm, 8 * cm])
    sig.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 14),
        ("TEXTCOLOR", (0, 0), (0, -1), ACCENT),
    ]))
    s.append(sig)

    s.append(Spacer(1, 24))
    s.append(Paragraph(
        '<i>"I don\'t compete with Harvey on intelligence. I compete on data, '
        'language, and jurisdiction they will never have."</i>',
        ParagraphStyle("end", parent=QUOTE, alignment=TA_CENTER, fontSize=12,
                       textColor=ACCENT)))

    return s


# ---------------------------------------------------------------------------
# Build PDF
# ---------------------------------------------------------------------------
def build(out_path: Path):
    doc = BaseDocTemplate(
        str(out_path), pagesize=A4,
        leftMargin=2 * cm, rightMargin=2 * cm,
        topMargin=2 * cm, bottomMargin=2 * cm,
        title="Legal AI · PFE Execution Plan (LOCKED)",
        author="Ahmed", subject="8-week execution plan",
    )
    cover_frame = Frame(0, 0, A4[0], A4[1], id="cover",
                        leftPadding=2 * cm, rightPadding=2 * cm,
                        topPadding=0, bottomPadding=0)
    body_frame = Frame(2 * cm, 1.8 * cm, A4[0] - 4 * cm, A4[1] - 4 * cm,
                       id="body")
    doc.addPageTemplates([
        PageTemplate(id="cover", frames=[cover_frame], onPage=_draw_cover_bg),
        PageTemplate(id="body", frames=[body_frame], onPage=_draw_page_chrome),
    ])
    doc.build(build_story())
    print(f"OK  ->  {out_path}")


if __name__ == "__main__":
    out = Path(r"C:/Users/ahmed/Desktop/upgrades pfe/PFE_EXECUTION_PLAN_LOCKED.pdf")
    out.parent.mkdir(parents=True, exist_ok=True)
    build(out)
