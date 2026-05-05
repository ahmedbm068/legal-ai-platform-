"""
Generates 8 individual sprint PDF cards — one per week.
Each PDF is a printable, action-oriented sprint guide.
Output: C:/Users/ahmed/Desktop/upgrades pfe/weekly/WEEK_N_*.pdf
"""
from __future__ import annotations

from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT, TA_RIGHT
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
INK       = colors.HexColor("#0F1A2B")
INK_SOFT  = colors.HexColor("#3A4A60")
ACCENT    = colors.HexColor("#0E7C66")
ACCENT_SOFT = colors.HexColor("#E5F4F0")
WARN      = colors.HexColor("#B85A1A")
RULE      = colors.HexColor("#D4DBE3")
PANEL     = colors.HexColor("#F7F9FB")
WHITE     = colors.white
MUTED     = colors.HexColor("#6B7B91")
GREEN     = colors.HexColor("#0E7C66")
AMBER     = colors.HexColor("#D97706")

# ---------------------------------------------------------------------------
# Styles
# ---------------------------------------------------------------------------
styles = getSampleStyleSheet()

H_KICKER = ParagraphStyle("Kicker", parent=styles["Normal"], fontName="Helvetica-Bold",
    fontSize=9, leading=12, textColor=ACCENT, spaceAfter=4, letterSpacing=2)
H1 = ParagraphStyle("H1", parent=styles["Heading1"], fontName="Helvetica-Bold",
    fontSize=22, leading=28, textColor=INK, spaceBefore=8, spaceAfter=8)
H2 = ParagraphStyle("H2", parent=styles["Heading2"], fontName="Helvetica-Bold",
    fontSize=13, leading=17, textColor=INK, spaceBefore=8, spaceAfter=4)
H3 = ParagraphStyle("H3", parent=styles["Heading3"], fontName="Helvetica-Bold",
    fontSize=10, leading=14, textColor=ACCENT, spaceBefore=5, spaceAfter=3)
BODY = ParagraphStyle("Body", parent=styles["BodyText"], fontName="Helvetica",
    fontSize=9.5, leading=13, textColor=INK, spaceAfter=3, alignment=TA_JUSTIFY)
BODY_SOFT = ParagraphStyle("BodySoft", parent=BODY, textColor=INK_SOFT)
BULLET = ParagraphStyle("Bullet", parent=BODY, leftIndent=10, bulletIndent=2, spaceAfter=2)
SMALL = ParagraphStyle("Small", parent=styles["Normal"], fontName="Helvetica",
    fontSize=8, leading=11, textColor=MUTED)
CALLOUT = ParagraphStyle("Callout", parent=BODY, textColor=INK, fontName="Helvetica-Bold",
    backColor=ACCENT_SOFT, borderPadding=8, spaceAfter=6, spaceBefore=6)
WARN_P = ParagraphStyle("WarnP", parent=BODY, fontName="Helvetica-Bold", textColor=WARN)
CENTER = ParagraphStyle("Center", parent=BODY, alignment=TA_CENTER)
CHECK_STYLE = ParagraphStyle("Check", parent=BODY, fontSize=9, leading=13,
    leftIndent=4, spaceAfter=1)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def hr(color=RULE, height=0.5, space=5):
    t = Table([[""]], colWidths=[17*cm], rowHeights=[height])
    t.setStyle(TableStyle([("LINEBELOW", (0,0),(-1,-1), height, color)]))
    return [Spacer(1, space), t, Spacer(1, space)]

def bullets(items):
    return [Paragraph(f"•  {x}", BULLET) for x in items]

def callout(text):
    return Paragraph(f"<b>★  </b>{text}", CALLOUT)

def check_row(text, indent=0):
    pad = "&nbsp;" * (indent * 4)
    return Paragraph(f"{pad}☐  {text}", CHECK_STYLE)

def section_header(text):
    t = Table([[Paragraph(f"<b>{text}</b>",
        ParagraphStyle("sh", parent=BODY, textColor=WHITE, fontName="Helvetica-Bold",
            fontSize=9, alignment=TA_LEFT))]],
        colWidths=[17*cm])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0,0),(-1,-1), INK),
        ("LEFTPADDING", (0,0),(-1,-1), 10),
        ("RIGHTPADDING", (0,0),(-1,-1), 10),
        ("TOPPADDING", (0,0),(-1,-1), 6),
        ("BOTTOMPADDING", (0,0),(-1,-1), 6),
    ]))
    return [t, Spacer(1, 4)]

def two_col_block(left_items, right_items):
    """Two column table for backend/frontend split."""
    left = [Paragraph(f"•  {x}",
        ParagraphStyle("lc", parent=BODY, fontSize=9, leading=12)) for x in left_items]
    right = [Paragraph(f"•  {x}",
        ParagraphStyle("rc", parent=BODY, fontSize=9, leading=12)) for x in right_items]
    data = [[left, right]]
    t = Table(data, colWidths=[8.3*cm, 8.7*cm])
    t.setStyle(TableStyle([
        ("VALIGN", (0,0),(-1,-1), "TOP"),
        ("LEFTPADDING", (0,0),(-1,-1), 8),
        ("RIGHTPADDING", (0,0),(-1,-1), 8),
        ("TOPPADDING", (0,0),(-1,-1), 6),
        ("BOTTOMPADDING", (0,0),(-1,-1), 6),
        ("BACKGROUND", (0,0),(0,-1), WHITE),
        ("BACKGROUND", (1,0),(1,-1), PANEL),
        ("LINEBEFORE", (1,0),(1,-1), 0.4, RULE),
        ("BOX", (0,0),(-1,-1), 0.4, RULE),
    ]))
    return t

# ---------------------------------------------------------------------------
# Sprint data
# ---------------------------------------------------------------------------
SPRINTS = [
    dict(
        week_no=1,
        dates="May 4 → May 10, 2026",
        title="Stabilization + Foundations",
        theme="ZERO CRASHES. THREE APPS. ROLE SYSTEM.",
        color="#0F1A2B",
        objective="Achieve zero crashes. Foundation for 3 frontends + role system. Production-shape backend.",
        backend=[
            "Add Role enum to User: lawyer / client / admin (DB migration).",
            "Per-role auth middleware + route scoping decorators.",
            "Audit log table + middleware (every mutating request).",
            "Standardize error envelopes (problem+json) across all routers.",
            "Rate limiter (slowapi) on auth + AI endpoints.",
            "Fix every 500: full click-through QA pass, log every error.",
        ],
        frontend=[
            "Click-through QA on lawyer app: every page, modal, empty state.",
            "Bootstrap client-portal app shell (router, auth, shared theme).",
            "Bootstrap admin app shell (router, auth, theme).",
            "Toast system + global error boundary across all 3 apps.",
        ],
        ai_tasks=[
            "Freeze all prompts — no changes to prompts after this week.",
            "Snapshot current eval scores as numeric baseline.",
            "Add LLM call cost + latency structured logging.",
        ],
        deliverable="3 deployable apps · Role-based login works · Audit log live · Zero 500s.",
        dod=[
            "All 131 tests pass (pytest output screenshot).",
            "Manual QA bug list = 0 open items.",
            "Login as lawyer / client / admin → lands on correct shell.",
            "Audit log records last 24h of activity.",
        ],
        daily_tasks={
            "Mon May 4":  ["DB migration: Role enum + audit_log table", "Per-role middleware skeleton"],
            "Tue May 5":  ["Route scoping decorators for lawyer/client/admin", "Error envelope standardization"],
            "Wed May 6":  ["Rate limiter (slowapi) on auth + AI routes", "Fix open 500 errors — backend"],
            "Thu May 7":  ["QA pass: every lawyer app page + modal", "Fix found bugs immediately"],
            "Fri May 8":  ["Bootstrap client-portal shell", "Bootstrap admin shell"],
            "Sat May 9":  ["Toast system + global error boundary across 3 apps", "Prompt freeze + eval snapshot"],
            "Sun May 10": ["Final QA pass", "Sprint review: write 5 lines in advancement/"],
        },
        focus_tip="Every bug you find and fix today is one less bug the jury sees in July.",
    ),
    dict(
        week_no=2,
        dates="May 11 → May 17, 2026",
        title="Lawyer Workspace v2 + Verifier",
        theme="WOW #1 — VERIFIABLE CITATIONS. TRUST UPGRADE.",
        color="#0E7C66",
        objective="Ship verifiable citations. Make every copilot answer provable and clickable.",
        backend=[
            "POST /copilot/verify — mDeBERTa NLI on (claim, retrieved_chunk).",
            "Citation builder: every LLM sentence → chunk IDs + char offsets.",
            "PDF coordinate index per chunk (page + bbox) for highlighting.",
            "Confidence aggregation per answer (entail × retrieval score).",
        ],
        frontend=[
            "Copilot answer renderer: superscripts [¹][²] → source chips.",
            "Click citation → PDF preview opens at exact page with bbox highlight.",
            "Confidence pill + 'Sources used' collapsible panel on each answer.",
            "Unsupported sentences in amber + hover tooltip explanation.",
        ],
        ai_tasks=[
            "Integrate MoritzLaurer/mDeBERTa-v3-base-xnli (zero-shot, no training needed).",
            "Add verifier as final step in copilot pipeline (after generation).",
            "Eval: precision/recall on 50 hand-labeled answer/claim pairs.",
            "Target: ≥ 80% recall on injected fake claims.",
        ],
        deliverable="Every copilot answer ships with inline citations + verifier badge.",
        dod=[
            "Click [¹] in any answer → PDF opens at correct page with highlight.",
            "Verifier flags ≥ 80% of injected fake claims in the eval set.",
            "Demo scenario #1 ('From email to memo in 90 s') works end-to-end.",
        ],
        daily_tasks={
            "Mon May 11": ["Integrate mDeBERTa (download + test inference locally)", "POST /copilot/verify endpoint skeleton"],
            "Tue May 12": ["Citation builder: sentence → chunk_id + char_offset mapping", "PDF coordinate index per chunk"],
            "Wed May 13": ["Confidence aggregation logic (entail × retrieval)", "Wire verifier into copilot pipeline"],
            "Thu May 14": ["Frontend: superscript renderer [¹][²] linked to chips", "PDF preview: open at page + highlight bbox"],
            "Fri May 15": ["Confidence pill + Sources panel UI", "Amber unsupported sentence highlighting"],
            "Sat May 16": ["Eval harness: run 50 hand-labeled pairs, record metrics", "Fix until ≥ 80% recall"],
            "Sun May 17": ["Demo scenario #1 rehearsal (90 s email-to-memo)", "Sprint review"],
        },
        focus_tip="Citations make your product trustworthy. No other local legal AI has this.",
    ),
    dict(
        week_no=3,
        dates="May 18 → May 24, 2026",
        title="Client Portal v1 + Document Classifier",
        theme="ML #1 — FIRST TRAINED MODEL IN PRODUCTION.",
        color="#5B3A8C",
        objective="Lawyers stop emailing clients. First ML model auto-classifies every upload.",
        backend=[
            "POST /portal/cases — clients see only their own cases (tenant + client_id scope).",
            "POST /portal/documents/upload — multi-file (max 10), auto-classify, attach to case.",
            "GET /portal/cases/{id}/timeline — public-safe events only.",
            "POST /portal/ask — copilot strictly scoped to client's documents.",
            "Email/SMS notification stubs on case status changes.",
        ],
        frontend=[
            "Client app: login, case list, case detail, drag-drop upload (max 10).",
            "Client AI chat: simple single-thread, citations to own docs only.",
            "Mobile-first layout (responsive ≤ 480 px).",
            "Empty states + onboarding flow for first-time clients.",
        ],
        ai_tasks=[
            "Fine-tune CamemBERT classifier (10 classes) with LLM-assisted label generation.",
            "Pipeline: PDF → text → classifier → tag (contract / judgment / summons / ...).",
            "Auto-tag every uploaded doc on upload + backfill existing documents.",
            "Show predicted type + confidence badge in document list.",
        ],
        deliverable="Live client portal · Every uploaded doc auto-classified in <2 s.",
        dod=[
            "Held-out F1 on classifier ≥ 0.85 across top 6 classes (show confusion matrix).",
            "Client uploads PDF → tag appears in lawyer view in <2 s.",
            "Client A cannot see Client B's data (verified with automated test).",
        ],
        daily_tasks={
            "Mon May 18": ["Generate labeled training data (LLM-assisted, 500+ examples)", "Set up CamemBERT fine-tuning pipeline"],
            "Tue May 19": ["Train classifier — run overnight if needed", "Client portal backend: /portal/cases + scope guard"],
            "Wed May 20": ["POST /portal/documents/upload + auto-classify on upload", "GET /portal/cases/{id}/timeline (public-safe filter)"],
            "Thu May 21": ["Client app: login + case list + case detail screens", "Drag-drop upload UI (max 10, progress bar)"],
            "Fri May 22": ["Client AI chat (single-thread, scoped to own docs)", "Mobile-first layout pass (≤ 480 px)"],
            "Sat May 23": ["Classifier eval: F1 per class, confusion matrix, fix weak classes", "Backfill existing documents with classifier"],
            "Sun May 24": ["Isolation test: Client A cannot see Client B data", "Sprint review"],
        },
        focus_tip="The classifier is your most jury-friendly ML demo. Make it fast and visible.",
    ),
    dict(
        week_no=4,
        dates="May 25 → May 31, 2026",
        title="Admin Console + Hybrid RAG",
        theme="ADMIN SPINE. RAG +15% RECALL. MEASURABLE WINS.",
        color="#1A3A6B",
        objective="Admin can run the platform without DB access. Retrieval measurably better.",
        backend=[
            "Admin endpoints: tenants, users, cases, documents — full CRUD + pagination + search.",
            "Bulk actions: export CSV, bulk-archive, role change.",
            "Hybrid retriever: BM25 + dense, weighted score fusion.",
            "Reranker (cross-encoder: bge-reranker-v2-m3) on top-k results.",
            "Audit log viewer endpoint with actor/action/date filters.",
        ],
        frontend=[
            "Admin app: data tables for users / cases / documents (sortable, filterable).",
            "Modal-based CRUD with optimistic UI updates.",
            "Audit log timeline view with actor + diff column.",
            "System health dashboard: counts, AI cost/day, error rate.",
        ],
        ai_tasks=[
            "Retrieval eval: measure recall@5 BEFORE implementing hybrid (baseline).",
            "Implement BM25 + dense fusion, measure recall@5 AFTER.",
            "Implement reranker, measure again — target: +15% over baseline.",
            "Persist retrieval metrics in DB so dashboard shows real numbers.",
        ],
        deliverable="Admin CRUD works · Hybrid + reranker live · Recall@5 improvement charted.",
        dod=[
            "All admin CRUD actions work and are audit-logged.",
            "Hybrid + reranker live in production; recall@5 improvement charted (screenshot).",
            "System health dashboard shows live data.",
        ],
        daily_tasks={
            "Mon May 25": ["Admin: users table (sortable, filterable, role-change modal)", "Measure recall@5 BASELINE (write number down)"],
            "Tue May 26": ["Admin: cases table + document global view", "Implement BM25 retriever + dense fusion"],
            "Wed May 27": ["Admin: audit log timeline view (actor + diff)", "Implement bge-reranker-v2-m3 on top-k"],
            "Thu May 28": ["Admin: system health dashboard (counts + AI cost)", "Measure recall@5 AFTER hybrid + reranker"],
            "Fri May 29": ["Bulk actions: export CSV, bulk-archive, role change", "Persist retrieval metrics to DB"],
            "Sat May 30": ["Audit log viewer endpoint (filters + pagination)", "Wire health dashboard to live DB metrics"],
            "Sun May 31": ["Full admin QA pass — every action, every modal", "Sprint review: chart the recall@5 improvement"],
        },
        focus_tip="The retrieval improvement chart is a slide in your jury deck. Make it clean.",
    ),
    dict(
        week_no=5,
        dates="June 1 → June 7, 2026",
        title="Document Editor + Drafting Agent",
        theme="WOW #2 — NOTION-GRADE EDITOR WITH INLINE AI.",
        color="#0E7C66",
        objective="Lawyers draft legal memos with AI inside a block editor and export to PDF.",
        backend=[
            "Draft documents: persist as JSON block tree + Markdown render endpoint.",
            "Versioning: store last 10 versions per draft, diff endpoint (per-block).",
            "POST /draft/{id}/ai — slash-command invokes drafting agent with case context.",
            "Export: PDF via weasyprint/reportlab + DOCX via python-docx.",
        ],
        frontend=[
            "Block editor (TipTap or Lexical): paragraphs, headings, lists, quote, table.",
            "Slash menu: /summary /clause /rewrite /translate /cite.",
            "⌘K command palette (global) + ⌘/ shortcut help overlay.",
            "Right margin: live citation chips + risk flags from NER.",
            "Track changes mode + version history drawer (last 10 versions + diff).",
        ],
        ai_tasks=[
            "Drafting agent: generates clauses grounded in case docs + legal corpus.",
            "Style adapter: 'plain language for client' vs 'formal for court filing'.",
            "Citation attachment: every AI-generated sentence includes source chunk IDs.",
        ],
        deliverable="Lawyer opens editor, uses /clause, gets AI text + citation, exports PDF.",
        dod=[
            "Slash-AI returns text + citations in < 3 s inside the editor.",
            "Version history shows last 10 versions with visual diff.",
            "Export PDF preserves formatting, headings, and citation markers.",
        ],
        daily_tasks={
            "Mon Jun 1":  ["Set up TipTap/Lexical in the lawyer app", "Draft JSON block schema + backend POST /draft"],
            "Tue Jun 2":  ["Versioning system (store 10 versions, diff endpoint)", "POST /draft/{id}/ai endpoint + drafting agent wiring"],
            "Wed Jun 3":  ["Slash menu (/, /summary, /clause, /rewrite)", "AI response streamed into editor blocks"],
            "Thu Jun 4":  ["Right-margin citation chips + risk flag panel", "Track changes mode UI"],
            "Fri Jun 5":  ["⌘K command palette + ⌘/ shortcut overlay", "Version history drawer with diff view"],
            "Sat Jun 6":  ["Export PDF (weasyprint) + DOCX (python-docx)", "Style adapter (formal vs plain toggle)"],
            "Sun Jun 7":  ["End-to-end: draft memo → AI clause → export PDF", "Sprint review"],
        },
        focus_tip="The editor is the most tangible wow moment. Demo it in 60 seconds: open, type, /clause, export.",
    ),
    dict(
        week_no=6,
        dates="June 8 → June 14, 2026",
        title="Legal NER + Timeline + Deadlines",
        theme="WOW #3 — CASE TIMELINE FROM RAW DOCUMENTS. NOBODY DOES THIS LOCALLY.",
        color="#7C3A0E",
        objective="Drop a case folder, get timeline + deadlines + risk heatmap in one minute.",
        backend=[
            "Run Legal NER on every uploaded doc (PERSON / DATE / MONEY / LAW_REF / DEADLINE).",
            "Persist NER entities in DB with source span + confidence score.",
            "Timeline service: aggregate dated events from NER + manual lawyer entries.",
            "Deadline engine: jurisdiction-aware date math (Tunisian CPC + German BGB rules).",
        ],
        frontend=[
            "Visual case timeline (vertical scroll, filterable by entity type).",
            "Deadlines tab with red highlights for critical days (< 7 days out).",
            "'Risk heatmap' view per case: entity counts + anomaly score.",
            "Calendar integration: deadlines auto-populate the existing calendar view.",
        ],
        ai_tasks=[
            "Fine-tune XLM-R NER on WikiNER-FR + 200 hand-labeled legal sentences.",
            "Target F1 ≥ 0.78 on 5 entity classes (PERSON, DATE, MONEY, LAW_REF, DEADLINE).",
            "Anomaly score per clause via Isolation Forest on clause embeddings.",
            "Per-document insight cards: parties · dates · risks · obligations.",
        ],
        deliverable="Drop 10 docs → timeline appears with deadlines and risk heatmap in <3 s.",
        dod=[
            "NER held-out F1 ≥ 0.78 on 5 entity classes (show per-class metrics).",
            "Demo scenario #2 ('Deadline saved your client') runs end-to-end.",
            "Timeline renders for a case with ≥ 10 docs in < 3 s.",
        ],
        daily_tasks={
            "Mon Jun 8":  ["Fine-tune XLM-R NER (set up training, first run overnight)", "Persist NER entity schema in DB"],
            "Tue Jun 9":  ["Evaluate NER — fix weak entity classes (add more labeled examples)", "Timeline service: aggregate NER dated events"],
            "Wed Jun 10": ["Deadline engine: CPC + BGB jurisdiction rules table", "Timeline frontend: vertical scroll view + entity filters"],
            "Thu Jun 11": ["Deadlines tab: red critical-day highlights + badge counts", "Calendar integration: auto-populate from deadlines"],
            "Fri Jun 12": ["Anomaly detector: Isolation Forest on clause embeddings", "Risk heatmap view per case"],
            "Sat Jun 13": ["Per-document insight cards (parties · dates · risks)", "Performance: timeline renders ≥ 10 docs in < 3 s"],
            "Sun Jun 14": ["Demo scenario #2 rehearsal (deadline saved your client)", "Sprint review + NER metrics screenshot"],
        },
        focus_tip="The timeline is the most visual, most unique thing your product does. Make it beautiful.",
    ),
    dict(
        week_no=7,
        dates="June 15 → June 21, 2026",
        title="Polish, Performance, Demo Engineering",
        theme="PREMIUM FEEL. FAST. DEMOS LOCKED. NO NEW FEATURES.",
        color="#0F1A2B",
        objective="Make it feel premium. Make it fast. Lock and rehearse all 3 demos.",
        backend=[
            "Cache layer (Redis or in-memory LRU) for hot reads (cases, document lists).",
            "Move heavy ingestion (PDF processing, NER, classifier) to Arq/RQ queue.",
            "Add OpenTelemetry traces around the full AI pipeline.",
            "Daily eval harness in CI: regression gate on copilot answer quality.",
        ],
        frontend=[
            "Skeleton loaders on every page (no blank white flashes).",
            "Optimistic UI mutations on all writes (create, archive, update).",
            "Empty-state pass: every empty page has exactly one CTA.",
            "Keyboard shortcut sheet overlay (⌘/).",
            "Polish micro-interactions: toasts, transitions, focus rings, hover states.",
            "Mobile pass on lawyer + client apps (test on 375 px viewport).",
        ],
        ai_tasks=[
            "Lock all 3 demo scenarios — no script changes after today.",
            "Pre-seed demo dataset (realistic Tunisian + German case, docs, timelines).",
            "Record fallback video for each demo (in case live connection fails).",
            "Build one-click 'Reset demo data' admin button.",
        ],
        deliverable="Product feels premium · 3 demos rehearsed + timed · Backup videos exist.",
        dod=[
            "P95 page load < 1.2 s on lawyer app (measure with browser DevTools).",
            "All 3 demo scenarios complete in < 3 minutes each.",
            "Backup videos recorded for all 3 demo scenarios.",
        ],
        daily_tasks={
            "Mon Jun 15": ["Cache layer: Redis/LRU on cases + document list endpoints", "Skeleton loaders on all lawyer app pages"],
            "Tue Jun 16": ["Move ingestion to Arq/RQ queue (PDF → NER → classifier)", "Optimistic mutations on all write operations"],
            "Wed Jun 17": ["OpenTelemetry traces on AI pipeline", "Empty-state pass + one CTA per empty page"],
            "Thu Jun 18": ["Keyboard shortcut overlay + polish micro-interactions", "Mobile pass: 375 px viewport on lawyer + client"],
            "Fri Jun 19": ["Pre-seed demo dataset (Tunisian + German case)", "Lock + rehearse Demo #1 (email → memo, 90 s)"],
            "Sat Jun 20": ["Lock + rehearse Demo #2 (deadline saved client)", "Lock + rehearse Demo #3 (drop folder → timeline)"],
            "Sun Jun 21": ["Record all 3 fallback videos", "One-click 'Reset demo data' button — Sprint review"],
        },
        focus_tip="This week is not about features. It's about making what exists feel like a product worth €500k.",
    ),
    dict(
        week_no=8,
        dates="June 22 → June 28, 2026",
        title="Defense Prep + Documentation",
        theme="SLIDES. REPORT. MOCK DEFENSE. FREEZE. SLEEP.",
        color="#2A1A6B",
        objective="Slides, written report, 2 mock defenses, code freeze June 25.",
        backend=[
            "Code freeze: June 25. Only critical-bug fixes after that date.",
            "Generate API docs: OpenAPI export + annotated screenshots.",
            "Final test pass + coverage report (target ≥ 75% coverage).",
        ],
        frontend=[
            "Final accessibility pass: focus states, alt text, color contrast (WCAG AA).",
            "Final pixel pass on all 5 demo screens (perfect spacing, no overflow).",
        ],
        ai_tasks=[
            "Final eval run: classifier F1 · NER F1 · NLI precision/recall · RAG recall@5.",
            "Build 'Corpus &amp; Models' dashboard inside admin with real metric numbers.",
            "Capture all metric screenshots for jury slide deck.",
        ],
        deliverable="Slides (≤25) + written report + 2 mock defenses + code freeze.",
        dod=[
            "Slide deck (≤ 25 slides) reviewed and approved by supervisor.",
            "PFE written report submitted to supervisor.",
            "2 mock defenses completed (1 with peers, 1 with supervisor).",
            "Sleep ≥ 7h the 3 nights before the real defense.",
        ],
        daily_tasks={
            "Mon Jun 22": ["Slide deck draft: cover, problem, solution, architecture (10 slides)", "Corpus & Models dashboard inside admin"],
            "Tue Jun 23": ["Slide deck: 3 demo walkthroughs + ML metrics slides", "Written report: abstract + intro + architecture chapter"],
            "Wed Jun 24": ["Slide deck: conclusion + jury Q&A prep slides", "Written report: AI/ML chapter + results chapter"],
            "Thu Jun 25": ["CODE FREEZE — no new features after today", "Final test pass + coverage report"],
            "Fri Jun 26": ["Mock defense #1 with peers (full 20 min + Q&A)", "Fix slide issues from mock feedback"],
            "Sat Jun 27": ["Mock defense #2 with supervisor (full 20 min + Q&A)", "Final accessibility + pixel pass"],
            "Sun Jun 28": ["Rest. Prepare clothes. Review slides one last time.", "Sleep ≥ 7h. You're ready."],
        },
        focus_tip="The jury evaluates your ability to explain. Practice out loud, not in your head.",
    ),
]

# ---------------------------------------------------------------------------
# Page chrome per week
# ---------------------------------------------------------------------------
def make_cover_bg(week_color):
    hex_c = week_color
    c = colors.HexColor(hex_c)
    def draw(canvas, doc):
        canvas.saveState()
        w, h = A4
        canvas.setFillColor(c)
        canvas.rect(0, 0, w, h, fill=1, stroke=0)
        canvas.setFillColor(ACCENT if hex_c != "#0E7C66" else colors.HexColor("#0F1A2B"))
        canvas.rect(0, h - 6*cm, w, 0.3*cm, fill=1, stroke=0)
        canvas.restoreState()
    return draw


def make_page_chrome(week_no, title, dates):
    def draw(canvas, doc):
        canvas.saveState()
        w, h = A4
        canvas.setStrokeColor(RULE)
        canvas.setLineWidth(0.4)
        canvas.line(2*cm, h - 1.6*cm, w - 2*cm, h - 1.6*cm)
        canvas.setFont("Helvetica-Bold", 8)
        canvas.setFillColor(ACCENT)
        canvas.drawString(2*cm, h - 1.25*cm, f"LEGAL AI  ·  WEEK {week_no}  ·  {title.upper()}")
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(MUTED)
        canvas.drawRightString(w - 2*cm, h - 1.25*cm, dates)
        canvas.line(2*cm, 1.5*cm, w - 2*cm, 1.5*cm)
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(MUTED)
        canvas.drawString(2*cm, 1.0*cm, "Ahmed  ·  Legal AI Platform  ·  PFE 2026")
        canvas.drawCentredString(w/2, 1.0*cm, f"Sprint {week_no} of 8")
        canvas.drawRightString(w - 2*cm, 1.0*cm, f"Page {doc.page}")
        canvas.restoreState()
    return draw


# ---------------------------------------------------------------------------
# Build story for one week
# ---------------------------------------------------------------------------
def build_week_story(sp):
    s = []
    hex_c = sp["color"]
    txt_c = WHITE

    # ===== COVER =====
    s.append(Spacer(1, 4.5*cm))
    s.append(Paragraph(
        f'<font color="white">SPRINT CARD  ·  WEEK {sp["week_no"]} OF 8</font>',
        ParagraphStyle("ck", parent=H_KICKER,
            textColor=colors.HexColor("#7BD7C2") if hex_c == "#0F1A2B" else WHITE,
            fontSize=10, alignment=TA_CENTER)))
    s.append(Spacer(1, 0.4*cm))
    s.append(Paragraph(
        f'<font color="white">{sp["title"]}</font>',
        ParagraphStyle("ct", parent=H1, textColor=WHITE, fontSize=28, leading=34,
            alignment=TA_CENTER)))
    s.append(Spacer(1, 0.2*cm))
    s.append(Paragraph(
        f'<font color="#B7C4D6">{sp["dates"]}</font>',
        ParagraphStyle("cd", parent=BODY, textColor=colors.HexColor("#B7C4D6"),
            fontSize=13, alignment=TA_CENTER)))
    s.append(Spacer(1, 0.5*cm))
    s.append(Paragraph(
        f'<font color="#7BD7C2"><b>{sp["theme"]}</b></font>',
        ParagraphStyle("th", parent=BODY, textColor=colors.HexColor("#7BD7C2"),
            fontSize=11, alignment=TA_CENTER, leading=16)))
    s.append(Spacer(1, 3*cm))

    # Cover meta table
    cov_data = [
        ["OBJECTIVE", sp["objective"]],
        ["DELIVERABLE", sp["deliverable"]],
    ]
    cov = Table(cov_data, colWidths=[3.5*cm, 12*cm])
    cov.setStyle(TableStyle([
        ("FONTNAME", (0,0),(0,-1), "Helvetica-Bold"),
        ("FONTNAME", (1,0),(1,-1), "Helvetica"),
        ("FONTSIZE", (0,0),(-1,-1), 9),
        ("TEXTCOLOR", (0,0),(0,-1), colors.HexColor("#7BD7C2")),
        ("TEXTCOLOR", (1,0),(1,-1), WHITE),
        ("BOTTOMPADDING", (0,0),(-1,-1), 10),
        ("TOPPADDING", (0,0),(-1,-1), 6),
        ("LINEBELOW", (0,0),(-1,-1), 0.4, colors.HexColor("#2A3A55")),
        ("VALIGN", (0,0),(-1,-1), "TOP"),
    ]))
    s.append(cov)
    s.append(NextPageTemplate("body"))
    s.append(PageBreak())

    # ===== PAGE 2: SPRINT TASKS =====
    s.append(Paragraph(f"WEEK {sp['week_no']} SPRINT TASKS", H_KICKER))
    s.append(Paragraph(sp["title"], H1))
    s += hr()
    s.append(Paragraph(f"<b>Objective:</b> {sp['objective']}", BODY))
    s.append(Spacer(1, 6))

    # Backend + Frontend two-column
    s.append(Paragraph("BACKEND", H3))
    s.append(two_col_block(sp["backend"], sp["frontend"]))
    s.append(Spacer(1, 2))
    s.append(Paragraph("← BACKEND", ParagraphStyle("lbl", parent=SMALL, alignment=TA_LEFT)))

    s.append(Spacer(1, 8))

    # AI/ML section
    s += section_header("AI / ML TASKS")
    for item in sp["ai_tasks"]:
        s.append(Paragraph(f"•  {item}", BULLET))
    s.append(Spacer(1, 8))

    # Definition of Done
    s += section_header("DEFINITION OF DONE — ALL MUST BE GREEN BEFORE WEEK ENDS")
    for item in sp["dod"]:
        s.append(check_row(item))
    s.append(Spacer(1, 10))
    s.append(callout(
        f"You cannot start Week {sp['week_no'] + 1} if any DoD item above is not checked."))

    s.append(PageBreak())

    # ===== PAGE 3: DAILY PLAN =====
    s.append(Paragraph("DAILY EXECUTION PLAN", H_KICKER))
    s.append(Paragraph(f"Week {sp['week_no']} — Day by Day", H1))
    s += hr()

    day_data = [["DAY", "TASK 1 (MORNING)", "TASK 2 (AFTERNOON)"]]
    for day, tasks in sp["daily_tasks"].items():
        t1 = tasks[0] if len(tasks) > 0 else "—"
        t2 = tasks[1] if len(tasks) > 1 else "—"
        bg = ACCENT_SOFT if "Sun" in day else WHITE
        day_data.append([
            Paragraph(f"<b>{day}</b>", ParagraphStyle("d", parent=BODY, fontSize=8.5, textColor=INK)),
            Paragraph(t1, ParagraphStyle("t1", parent=BODY, fontSize=8.5)),
            Paragraph(t2, ParagraphStyle("t2", parent=BODY, fontSize=8.5)),
        ])

    dt = Table(day_data, colWidths=[2.8*cm, 7.1*cm, 7.1*cm])
    row_styles = [
        ("BACKGROUND", (0,0),(-1,0), INK),
        ("TEXTCOLOR", (0,0),(-1,0), WHITE),
        ("FONTNAME", (0,0),(-1,0), "Helvetica-Bold"),
        ("FONTSIZE", (0,0),(-1,0), 8.5),
        ("FONTNAME", (0,1),(-1,-1), "Helvetica"),
        ("FONTSIZE", (0,1),(-1,-1), 8.5),
        ("VALIGN", (0,0),(-1,-1), "TOP"),
        ("BOX", (0,0),(-1,-1), 0.4, RULE),
        ("INNERGRID", (0,0),(-1,-1), 0.3, RULE),
        ("LEFTPADDING", (0,0),(-1,-1), 6),
        ("RIGHTPADDING", (0,0),(-1,-1), 6),
        ("TOPPADDING", (0,0),(-1,-1), 5),
        ("BOTTOMPADDING", (0,0),(-1,-1), 5),
        ("BACKGROUND", (0,-1),(-1,-1), ACCENT_SOFT),  # Sunday row
    ]
    dt.setStyle(TableStyle(row_styles))
    s.append(dt)

    s.append(Spacer(1, 10))

    # Daily work schedule reminder
    s.append(Paragraph("DAILY WORK SCHEDULE (EVERY DAY THIS WEEK)", H3))
    sched = [
        ["09:00–09:15", "Plan", "Open this card. Pick today's 2 tasks. Write them down."],
        ["09:15–11:00", "Deep work #1", "Hardest backend/ML task first. No phone."],
        ["11:15–13:00", "Deep work #2", "Continue or move to second priority."],
        ["14:00–15:30", "Build / ship", "Frontend, integration, lower-cognitive tasks."],
        ["15:30–16:00", "Test pass", "Click-through QA on what you built today."],
        ["16:00–16:30", "Commit + log", "git push. Update SPRINT_LOG.md."],
    ]
    sd = Table([[Paragraph(a, ParagraphStyle("s0", parent=BODY, fontSize=8.5, fontName="Helvetica-Bold")),
                 Paragraph(b, ParagraphStyle("s1", parent=BODY, fontSize=8.5, fontName="Helvetica-Bold")),
                 Paragraph(c, ParagraphStyle("s2", parent=BODY, fontSize=8.5))] for a,b,c in sched],
               colWidths=[2.8*cm, 3*cm, 11.2*cm])
    sd.setStyle(TableStyle([
        ("BOX", (0,0),(-1,-1), 0.4, RULE),
        ("INNERGRID", (0,0),(-1,-1), 0.3, RULE),
        ("LEFTPADDING", (0,0),(-1,-1), 6),
        ("RIGHTPADDING", (0,0),(-1,-1), 6),
        ("TOPPADDING", (0,0),(-1,-1), 4),
        ("BOTTOMPADDING", (0,0),(-1,-1), 4),
        ("VALIGN", (0,0),(-1,-1), "MIDDLE"),
        ("BACKGROUND", (0,0),(0,-1), PANEL),
    ]))
    s.append(sd)
    s.append(Spacer(1, 10))
    s.append(Paragraph(
        f'<b>Focus tip for this week:</b> "{sp["focus_tip"]}"',
        ParagraphStyle("ft", parent=BODY, textColor=ACCENT, fontName="Helvetica-Oblique",
            backColor=ACCENT_SOFT, borderPadding=8)))

    return s


# ---------------------------------------------------------------------------
# Build one weekly PDF
# ---------------------------------------------------------------------------
def build_week(sp: dict, out_dir: Path):
    safe_title = sp["title"].replace(" ", "_").replace("/", "-").replace("+", "and")
    filename = f"WEEK_{sp['week_no']:02d}_{safe_title}.pdf"
    out_path = out_dir / filename

    doc = BaseDocTemplate(
        str(out_path), pagesize=A4,
        leftMargin=2*cm, rightMargin=2*cm,
        topMargin=2*cm, bottomMargin=2*cm,
        title=f"Legal AI · Week {sp['week_no']} · {sp['title']}",
        author="Ahmed", subject="Weekly sprint card",
    )
    cover_frame = Frame(0, 0, A4[0], A4[1], id="cover",
        leftPadding=2*cm, rightPadding=2*cm, topPadding=0, bottomPadding=0)
    body_frame = Frame(2*cm, 1.8*cm, A4[0] - 4*cm, A4[1] - 4*cm, id="body")

    doc.addPageTemplates([
        PageTemplate(id="cover", frames=[cover_frame],
            onPage=make_cover_bg(sp["color"])),
        PageTemplate(id="body", frames=[body_frame],
            onPage=make_page_chrome(sp["week_no"], sp["title"], sp["dates"])),
    ])
    doc.build(build_week_story(sp))
    print(f"  OK  ->  {out_path.name}")
    return out_path


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    out_dir = Path(r"C:/Users/ahmed/Desktop/upgrades pfe/weekly")
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"\nGenerating 8 weekly sprint PDFs → {out_dir}\n")
    for sp in SPRINTS:
        build_week(sp, out_dir)

    print(f"\nDone. {len(SPRINTS)} PDFs in {out_dir}")
