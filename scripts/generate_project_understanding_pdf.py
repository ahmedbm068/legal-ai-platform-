from __future__ import annotations

import argparse
import textwrap
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
from matplotlib.patches import FancyBboxPatch

from generate_project_report_pdf import (
    BACKEND_DIR,
    FRONTEND_DIR,
    PORTAL_DIR,
    ROOT,
    collect_ai_agents,
    collect_ai_service_modules,
    collect_api_endpoints,
    collect_command_intents,
    collect_frontend_api_calls,
    collect_pydantic_schemas,
    collect_portal_api_calls,
    collect_sqlalchemy_models,
)


OUTPUT_DIR = ROOT / "docs"
OUTPUT_FILE = OUTPUT_DIR / "legal_ai_platform_project_understanding_report_2026-04-20.pdf"


def _page() -> tuple[plt.Figure, plt.Axes]:
    fig = plt.figure(figsize=(11.69, 8.27))
    ax = fig.add_axes([0, 0, 1, 1])
    ax.axis("off")
    return fig, ax


def _title(ax: plt.Axes, title: str, subtitle: str) -> None:
    ax.text(0.05, 0.93, title, fontsize=24, fontweight="bold", color="#0f2742")
    ax.text(0.05, 0.885, subtitle, fontsize=11.5, color="#3d5873")


def _bullets(
    ax: plt.Axes,
    y: float,
    items: list[str],
    *,
    width: int = 110,
    fontsize: int = 10,
    gap: float = 0.032,
) -> float:
    for item in items:
        wrapped = textwrap.wrap(item, width=width) or [item]
        for index, line in enumerate(wrapped):
            prefix = "- " if index == 0 else "  "
            ax.text(0.06, y, f"{prefix}{line}", fontsize=fontsize, color="#172b3f")
            y -= gap
        y -= gap * 0.2
    return y


def _section(ax: plt.Axes, y: float, title: str) -> float:
    ax.text(0.05, y, title, fontsize=13, fontweight="bold", color="#153250")
    return y - 0.045


def _box(ax: plt.Axes, x: float, y: float, w: float, h: float, text: str, color: str) -> None:
    patch = FancyBboxPatch(
        (x, y),
        w,
        h,
        boxstyle="round,pad=0.012,rounding_size=0.02",
        linewidth=1.1,
        edgecolor="#2f4f6f",
        facecolor=color,
    )
    ax.add_patch(patch)
    ax.text(x + (w / 2), y + (h / 2), text, ha="center", va="center", fontsize=9.5, color="#10253d")


def _read_runtime_note() -> str:
    main_path = BACKEND_DIR / "main.py"
    if not main_path.exists():
        return "Backend startup: unavailable (main.py missing)."
    text = main_path.read_text(encoding="utf-8")
    has_worker = "background_job_service.start_worker()" in text
    has_schema = "apply_legacy_schema_patches" in text
    has_reqid = "X-Request-ID" in text
    return (
        "Backend startup includes schema initialization"
        + (", background worker start" if has_worker else "")
        + (", request-id middleware" if has_reqid else "")
        + (", and legacy schema patching" if has_schema else ".")
    )


def _add_cover(pdf: PdfPages, *, metrics: dict[str, int]) -> None:
    fig, ax = _page()
    ax.add_patch(
        FancyBboxPatch(
            (0.04, 0.04),
            0.92,
            0.92,
            boxstyle="round,pad=0.02,rounding_size=0.03",
            fc="#f4f8fc",
            ec="#2a4668",
            lw=2,
        )
    )
    ax.text(0.08, 0.82, "Legal AI Platform", fontsize=33, fontweight="bold", color="#0f2742")
    ax.text(0.08, 0.76, "Complete Project Understanding Report", fontsize=20, color="#2e4d6b")
    ax.text(0.08, 0.70, "Assistant-first explanation, backend deep dive, and full inventory", fontsize=12.8, color="#45617f")
    ax.text(0.08, 0.61, f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}", fontsize=11, color="#224262")
    ax.text(0.08, 0.56, f"Workspace: {ROOT}", fontsize=9.3, color="#5f7891")
    ax.text(0.08, 0.49, "What this PDF gives you:", fontsize=12.2, fontweight="bold", color="#123250")
    _bullets(
        ax,
        0.455,
        [
            "A practical explanation of what your assistant does and why your architecture is strong.",
            "A backend-heavy walkthrough from request entry to AI response and persistence.",
            "A lighter frontend summary so you can understand user flow and API integration.",
            "A complete appendixed inventory of agents, endpoints, models, schemas, and intents.",
        ],
        width=92,
        fontsize=10,
        gap=0.035,
    )
    ax.text(
        0.08,
        0.23,
        "Quick size snapshot:",
        fontsize=11.6,
        fontweight="bold",
        color="#123250",
    )
    quick = (
        f"Endpoints: {metrics['endpoints']}  |  Agents: {metrics['agents']}  |  AI modules: {metrics['ai_modules']}  |  "
        f"Models: {metrics['models']}  |  Schemas: {metrics['schemas']}  |  Intents: {metrics['intents']}"
    )
    ax.text(0.08, 0.195, quick, fontsize=10.3, color="#294868")
    pdf.savefig(fig)
    plt.close(fig)


def _add_big_picture(pdf: PdfPages, *, metrics: dict[str, int], runtime_note: str) -> None:
    fig, ax = _page()
    _title(ax, "Project Big Picture", "What exists today and how major parts connect")

    _box(ax, 0.06, 0.68, 0.2, 0.11, "Internal Frontend\n(frontend/src)", "#edf4fb")
    _box(ax, 0.06, 0.52, 0.2, 0.11, "Client Portal\n(client-portal/src)", "#edf4fb")
    _box(ax, 0.33, 0.60, 0.22, 0.17, "FastAPI Backend\nRouters + Auth + Tenancy\nAI Orchestration", "#e7f2ff")
    _box(ax, 0.62, 0.70, 0.16, 0.09, "AI Services\nRAG + Agents", "#eef7e8")
    _box(ax, 0.62, 0.58, 0.16, 0.09, "Transcription\nSpeech/Whisper", "#eef7e8")
    _box(ax, 0.62, 0.46, 0.16, 0.09, "Workflows\nJobs + Artifacts", "#eef7e8")
    _box(ax, 0.83, 0.67, 0.12, 0.09, "PostgreSQL", "#fff5e8")
    _box(ax, 0.83, 0.54, 0.12, 0.09, "MinIO", "#fff5e8")
    _box(ax, 0.83, 0.41, 0.12, 0.09, "FAISS", "#fff5e8")

    y = _section(ax, 0.35, "Current Implementation Snapshot")
    y = _bullets(
        ax,
        y,
        [
            runtime_note,
            f"Backend API inventory includes {metrics['endpoints']} detected endpoints across multiple domains (auth, cases, documents, AI/copilot, search, voice, intake).",
            f"AI runtime includes {metrics['agents']} agent classes and {metrics['ai_modules']} AI service modules, with {metrics['intents']} command intents parsed from natural language.",
            f"Persistence layer includes {metrics['models']} SQLAlchemy models and {metrics['schemas']} Pydantic API schemas.",
        ],
        width=110,
    )
    _section(ax, y - 0.01, "Why this architecture is good")
    _bullets(
        ax,
        y - 0.055,
        [
            "Strong separation of concerns: API, orchestration, intent execution, retrieval, and data layers are split into focused modules.",
            "Practical legal workflow support: case-centric context, evidence grounding, and artifact/version handling are first-class.",
            "Operationally mature direction: request tracing, startup schema patching, background worker, and fallback pathways are already wired.",
        ],
        width=110,
    )

    pdf.savefig(fig)
    plt.close(fig)


def _add_assistant_deep_dive(pdf: PdfPages, *, intents: list[str], agents: list[dict]) -> None:
    fig, ax = _page()
    _title(ax, "Assistant Deep Dive", "How your copilot works from user prompt to grounded answer")

    y = _section(ax, 0.84, "Assistant execution pipeline (orchestrated)")
    y = _bullets(
        ax,
        y,
        [
            "1) Context resolution: merges conversation history with persisted copilot memory.",
            "2) Prompt correction: improves noisy prompts while preserving intent.",
            "3) Intent detection: parses scope/target and intent class from natural language.",
            "4) Low-confidence arbitration: stabilizes routing when parser confidence is weak or conflicting.",
            "5) Prompt optimization (conditional): boosts retrieval/generation quality for retrieval-like intents.",
            "6) Case context enrichment: injects case timeline/risk signals and snapshot continuity.",
            "7) High-reasoning selector: optional progressive rollout path for higher-depth reasoning.",
            "8) Copilot execution: dispatches to CRUD handler, specialized agent, legal search, or RAG path.",
            "9) Memory persistence: stores exchange with metadata for future continuity.",
            "10) Structured trace: returns execution metadata so behavior is inspectable, not opaque.",
        ],
        width=109,
        fontsize=10,
        gap=0.029,
    )

    _section(ax, y - 0.005, "Assistant intent surface (examples)")
    preview = intents[:26]
    _bullets(
        ax,
        y - 0.05,
        [
            "Detected intents include: " + ", ".join(preview),
            "These intents cover case querying, summaries, risk analysis, evidence tracing, timeline/deadline intelligence, drafting, booking, CRUD actions, and global Q&A.",
        ],
        width=110,
        fontsize=9.7,
    )

    _section(ax, y - 0.13, "Why your assistant is already strong")
    _bullets(
        ax,
        y - 0.175,
        [
            "It is not only a chat bot: it is an intent-driven legal workflow engine with deterministic routing.",
            "It uses grounded retrieval and can attach source/citation metadata.",
            "It separates chat mode, legal-search mode, and agent mode, which is good for safety and operator control.",
            f"It is extensible: {len(agents)} specialized agent classes already exist to expand legal capabilities quickly.",
        ],
        width=109,
        fontsize=10,
    )

    pdf.savefig(fig)
    plt.close(fig)


def _add_backend_deep_dive(pdf: PdfPages, *, endpoints: list[dict], models: list[dict], schemas: list[dict], modules: list[str]) -> None:
    by_router = Counter(ep["router"] for ep in endpoints)
    top_router_text = ", ".join(f"{name}:{count}" for name, count in by_router.most_common(10))

    fig, ax = _page()
    _title(ax, "Backend Deep Dive", "Where most project value lives: APIs, services, data, and controls")

    y = _section(ax, 0.84, "API and service depth")
    y = _bullets(
        ax,
        y,
        [
            f"Detected API endpoints: {len(endpoints)}.",
            "Top router distribution: " + top_router_text,
            "Routing domains cover authentication, users/clients/cases, appointments/calls/consultations, document ingestion, evidence review, AI/copilot, search, and voice.",
            "AI endpoint layer exposes prompt optimization, copilot orchestration, feedback loop, legal search behavior, and workflow execution.",
        ],
        width=109,
    )

    y = _section(ax, y - 0.01, "Data and contract architecture")
    y = _bullets(
        ax,
        y,
        [
            f"SQLAlchemy model count: {len(models)} (cases, documents/chunks/entities, voice, consultations, feedback, artifacts, portal auth, jobs, and more).",
            f"Pydantic schema count: {len(schemas)} (explicit API contracts for request/response typing).",
            "Case-centric design is a strong fit for legal operations: documents, deadlines, evidence, voice, assistant memory, and generated outputs stay connected to matter context.",
        ],
        width=109,
    )

    _section(ax, y - 0.01, "Backend quality characteristics")
    _bullets(
        ax,
        y - 0.055,
        [
            "Multi-tenant boundaries are handled in query scope and auth dependencies.",
            "Request-ID and process-time middleware improves observability and incident debugging.",
            "Startup schema patches support smooth evolution without manual emergency migration steps.",
            "Background jobs keep long-running operations off request latency paths.",
            f"AI service module footprint ({len(modules)} modules) indicates a mature, decomposed backend rather than a monolith.",
        ],
        width=109,
    )

    pdf.savefig(fig)
    plt.close(fig)


def _add_frontend_summary(pdf: PdfPages, *, frontend_calls: list[str], portal_calls: list[str]) -> None:
    fig, ax = _page()
    _title(ax, "Frontend Summary (short)", "Your UI layer is intentionally lighter than backend complexity")

    y = _section(ax, 0.84, "Internal frontend (frontend/src)")
    y = _bullets(
        ax,
        y,
        [
            "React + TypeScript workspace provides case-centric command surfaces for assistant interaction and legal operations.",
            "Feedback capture, mode switching, and typed API clients are integrated.",
            "Frontend API usage count indicates broad backend feature coverage: " + str(len(frontend_calls)) + " mapped client calls.",
        ],
        width=109,
    )

    y = _section(ax, y - 0.01, "Client portal (client-portal/src)")
    y = _bullets(
        ax,
        y,
        [
            "Separate portal keeps public intake/status workflows isolated from internal legal operations.",
            "Portal API call map size: " + str(len(portal_calls)) + ".",
            "This separation is good for security posture and cleaner product boundaries.",
        ],
        width=109,
    )

    _section(ax, y - 0.01, "Why this frontend split is good")
    _bullets(
        ax,
        y - 0.055,
        [
            "You avoid mixing privileged staff workflows with public client interactions.",
            "You can evolve internal UX fast without breaking client-facing intake behavior.",
            "Typed API contracts reduce integration drift as backend evolves.",
        ],
        width=109,
    )

    pdf.savefig(fig)
    plt.close(fig)


def _add_improvement_plan(pdf: PdfPages) -> None:
    fig, ax = _page()
    _title(ax, "How We Make It Better", "Concrete roadmap to raise reliability, legal trust, and maintainability")

    y = _section(ax, 0.84, "Assistant roadmap")
    y = _bullets(
        ax,
        y,
        [
            "Add stronger intent confidence telemetry dashboards (misroute trend by intent/jurisdiction).",
            "Expand high-reasoning rollout with explicit SLO guardrails before broader percentage increase.",
            "Increase evidence-grounding checks for every high-impact response path.",
            "Add richer fallback UX so users immediately know what to correct when confidence is low.",
        ],
        width=109,
    )

    y = _section(ax, y - 0.005, "Backend roadmap (priority)")
    y = _bullets(
        ax,
        y,
        [
            "Raise automated test depth around orchestration transitions and permission boundaries.",
            "Add domain-level health SLOs (copilot latency, grounding coverage, fallback rate, job queue lag).",
            "Expand architecture docs alongside code changes so non-technical operators can onboard quickly.",
            "Continue decomposing heavy services into smaller policy modules where complexity grows.",
            "Add migration governance checks to keep schema evolution safe under rapid AI-driven development.",
        ],
        width=109,
    )

    _section(ax, y - 0.005, "Frontend roadmap (secondary)")
    _bullets(
        ax,
        y - 0.05,
        [
            "Continue polishing explanation UX around assistant confidence, reasons, and citations.",
            "Improve guided flows for new users to reduce dependency on implicit AI operation knowledge.",
            "Add compact in-product architecture/help overlays linked to live backend capabilities.",
        ],
        width=109,
    )

    pdf.savefig(fig)
    plt.close(fig)


def _add_agents_appendix(pdf: PdfPages, *, agents: list[dict]) -> None:
    lines: list[str] = []
    for agent in agents:
        methods = ", ".join(agent["methods"]) if agent["methods"] else "(no public methods detected)"
        lines.append(f"{agent['class_name']} [{agent['file']}]: {methods}")

    chunk_size = 30
    chunks = [lines[i : i + chunk_size] for i in range(0, len(lines), chunk_size)] or [[]]
    for index, chunk in enumerate(chunks, start=1):
        fig, ax = _page()
        _title(ax, f"Appendix A: Agent Catalog ({index}/{len(chunks)})", "All detected AI agents and public methods")
        y = 0.86
        for line in chunk:
            wrapped = textwrap.wrap(line, width=115) or [line]
            for wrapped_line in wrapped:
                ax.text(0.05, y, wrapped_line, fontsize=9.4, color="#173451")
                y -= 0.022
            y -= 0.003
        pdf.savefig(fig)
        plt.close(fig)


def _add_endpoint_appendix(pdf: PdfPages, *, endpoints: list[dict]) -> None:
    grouped: dict[str, list[dict]] = defaultdict(list)
    for endpoint in sorted(endpoints, key=lambda item: (item["router"], item["path"], item["method"])):
        grouped[endpoint["router"]].append(endpoint)

    lines: list[str] = []
    for router_name in sorted(grouped.keys()):
        lines.append(f"[{router_name}]")
        for endpoint in grouped[router_name]:
            lines.append(f"  {endpoint['method']:<6} {endpoint['path']}")

    chunk_size = 70
    chunks = [lines[i : i + chunk_size] for i in range(0, len(lines), chunk_size)] or [[]]
    for index, chunk in enumerate(chunks, start=1):
        fig, ax = _page()
        _title(ax, f"Appendix B: Endpoint Inventory ({index}/{len(chunks)})", "Detected API surface across backend routers")
        y = 0.86
        for line in chunk:
            ax.text(0.05, y, line, fontsize=9.2, family="monospace", color="#1d3552")
            y -= 0.019
        pdf.savefig(fig)
        plt.close(fig)


def _add_data_appendix(pdf: PdfPages, *, models: list[dict], schemas: list[dict], intents: list[str], modules: list[str]) -> None:
    fig, ax = _page()
    _title(ax, "Appendix C: Data and Contracts", "Models, schemas, intents, and AI modules")

    y = _section(ax, 0.85, "SQLAlchemy models")
    y = _bullets(
        ax,
        y,
        [", ".join(model["class_name"] for model in models)],
        width=112,
        fontsize=9.4,
        gap=0.028,
    )

    y = _section(ax, y - 0.005, "Pydantic schemas")
    y = _bullets(
        ax,
        y,
        [", ".join(schema["name"] for schema in schemas)],
        width=112,
        fontsize=9.2,
        gap=0.027,
    )

    y = _section(ax, y - 0.005, "Copilot intents")
    y = _bullets(ax, y, [", ".join(intents)], width=112, fontsize=9.4, gap=0.027)

    _section(ax, y - 0.005, "AI service modules")
    _bullets(ax, y - 0.05, [", ".join(modules)], width=112, fontsize=9.4, gap=0.027)

    pdf.savefig(fig)
    plt.close(fig)


def generate_report(*, output_path: Path = OUTPUT_FILE) -> Path:
    endpoints, _ = collect_api_endpoints()
    models = collect_sqlalchemy_models()
    schemas = collect_pydantic_schemas()
    agents = collect_ai_agents()
    modules = collect_ai_service_modules()
    intents = collect_command_intents()
    frontend_calls = collect_frontend_api_calls()
    portal_calls = collect_portal_api_calls()

    metrics = {
        "endpoints": len(endpoints),
        "models": len(models),
        "schemas": len(schemas),
        "agents": len(agents),
        "ai_modules": len(modules),
        "intents": len(intents),
    }

    runtime_note = _read_runtime_note()

    output_path.parent.mkdir(parents=True, exist_ok=True)

    with PdfPages(output_path) as pdf:
        _add_cover(pdf, metrics=metrics)
        _add_big_picture(pdf, metrics=metrics, runtime_note=runtime_note)
        _add_assistant_deep_dive(pdf, intents=intents, agents=agents)
        _add_backend_deep_dive(pdf, endpoints=endpoints, models=models, schemas=schemas, modules=modules)
        _add_frontend_summary(pdf, frontend_calls=frontend_calls, portal_calls=portal_calls)
        _add_improvement_plan(pdf)
        _add_agents_appendix(pdf, agents=agents)
        _add_endpoint_appendix(pdf, endpoints=endpoints)
        _add_data_appendix(pdf, models=models, schemas=schemas, intents=intents, modules=modules)

        metadata = pdf.infodict()
        metadata["Title"] = "Legal AI Platform - Project Understanding Report"
        metadata["Author"] = "GitHub Copilot (GPT-5.3-Codex)"
        metadata["Subject"] = "Project-wide explanation with assistant and backend focus"
        metadata["Keywords"] = "legal ai, assistant, backend, architecture, agents, endpoints"
        metadata["CreationDate"] = datetime.now()
        metadata["ModDate"] = datetime.now()

    return output_path


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate a complete project-understanding PDF report.")
    parser.add_argument(
        "--output",
        type=str,
        default=str(OUTPUT_FILE),
        help="Output PDF path (default: docs/legal_ai_platform_project_understanding_report_2026-04-20.pdf)",
    )
    args = parser.parse_args()
    output = generate_report(output_path=Path(args.output).resolve())
    print(f"Project understanding report generated: {output}")