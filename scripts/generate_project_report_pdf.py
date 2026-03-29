from __future__ import annotations

import re
import textwrap
from collections import defaultdict
from datetime import datetime
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch


ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = ROOT / "backend"
FRONTEND_DIR = ROOT / "frontend" / "src"
PORTAL_DIR = ROOT / "client-portal" / "src"
OUTPUT_DIR = ROOT / "docs"
OUTPUT_FILE = OUTPUT_DIR / "legal_ai_platform_full_technical_report_2026-03-29.pdf"


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def collect_api_endpoints() -> tuple[list[dict], dict[str, str]]:
    endpoints: list[dict] = []
    prefixes: dict[str, str] = {}
    api_dir = BACKEND_DIR / "api"

    for path in sorted(api_dir.glob("*.py")):
        if path.name.endswith("_schema.py"):
            continue

        content = read_text(path)
        stem = path.stem
        prefix_match = re.search(r'APIRouter\([\s\S]*?prefix\s*=\s*"([^"]+)"', content)
        prefix = prefix_match.group(1).strip() if prefix_match else ""
        prefixes[stem] = prefix

        for method, route in re.findall(r'@router\.(get|post|put|delete|patch)\(\s*"([^"]+)"', content):
            full_path = f"{prefix.rstrip('/')}/{route.lstrip('/')}" if prefix else route
            full_path = "/" + full_path.strip("/")
            endpoints.append(
                {
                    "router": stem,
                    "method": method.upper(),
                    "route": route,
                    "path": full_path,
                }
            )
    return endpoints, prefixes


def collect_sqlalchemy_models() -> list[dict]:
    models: list[dict] = []
    model_dir = BACKEND_DIR / "models"
    for path in sorted(model_dir.glob("*.py")):
        if path.name == "__init__.py":
            continue

        content = read_text(path)
        class_match = re.search(r"class\s+(\w+)\(Base\):", content)
        table_match = re.search(r'__tablename__\s*=\s*"([^"]+)"', content)
        if not class_match:
            continue

        fields = re.findall(r"^\s{4}(\w+)\s*=\s*Column\(", content, flags=re.MULTILINE)
        relationships = re.findall(r'^\s{4}(\w+)\s*=\s*relationship\("([^"]+)"', content, flags=re.MULTILINE)
        models.append(
            {
                "class_name": class_match.group(1),
                "table": table_match.group(1) if table_match else "n/a",
                "fields": fields,
                "relationships": relationships,
                "file": path.name,
            }
        )
    return models


def collect_pydantic_schemas() -> list[dict]:
    schemas: list[dict] = []
    schema_files = sorted((BACKEND_DIR / "api").glob("*_schema.py"))
    for path in schema_files:
        content = read_text(path)
        classes = re.findall(r"class\s+(\w+)\(BaseModel\):", content)
        for cls in classes:
            schemas.append({"name": cls, "file": path.name})
    return schemas


def collect_ai_agents() -> list[dict]:
    agent_dir = BACKEND_DIR / "services" / "ai" / "agents"
    agents: list[dict] = []

    for path in sorted(agent_dir.glob("*.py")):
        if path.name in {"__init__.py", "base_agent.py"}:
            continue
        content = read_text(path)
        class_match = re.search(r"class\s+(\w+)\((?:BaseAgent|object)?\):", content)
        public_methods = re.findall(r"^\s{4}def\s+([a-zA-Z_]\w*)\(", content, flags=re.MULTILINE)
        public_methods = [m for m in public_methods if not m.startswith("_") and m != "__init__"]
        agents.append(
            {
                "file": path.name,
                "class_name": class_match.group(1) if class_match else path.stem,
                "methods": public_methods,
            }
        )
    return agents


def collect_ai_service_modules() -> list[str]:
    service_dir = BACKEND_DIR / "services" / "ai"
    modules: list[str] = []
    for path in sorted(service_dir.glob("*.py")):
        if path.name == "__init__.py":
            continue
        modules.append(path.name)
    return modules


def collect_command_intents() -> list[str]:
    path = BACKEND_DIR / "services" / "ai" / "command_parsing_service.py"
    content = read_text(path)
    intents = re.findall(r'return\s+"([a-z_]+)"\s*,\s*"(?:high|medium|low)"', content)
    unique = []
    seen = set()
    for intent in intents:
        if intent not in seen:
            seen.add(intent)
            unique.append(intent)
    return unique


def collect_frontend_api_calls() -> list[str]:
    path = FRONTEND_DIR / "lib" / "api.ts"
    content = read_text(path)
    raw = re.findall(r'request<[^>]+>\((`[^`]+`|"[^"]+")', content)
    cleaned = [item.strip('`"') for item in raw]
    return cleaned


def collect_portal_api_calls() -> list[str]:
    path = PORTAL_DIR / "lib" / "api.ts"
    content = read_text(path)
    calls = re.findall(rf'{re.escape("fetch(`${API_BASE_URL}")}([^`]+)`', content)
    return sorted(set([call.strip() for call in calls]))


def read_env_summary() -> dict[str, str]:
    env_path = ROOT / ".env"
    if not env_path.exists():
        return {}

    lines = read_text(env_path).splitlines()
    env: dict[str, str] = {}
    for raw in lines:
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        env[key.strip()] = value.strip()
    return env


def draw_title(ax, title: str, subtitle: str) -> None:
    ax.text(0.05, 0.93, title, fontsize=26, fontweight="bold", color="#0f2742")
    ax.text(0.05, 0.885, subtitle, fontsize=12, color="#3d5873")


def draw_bullets(ax, y: float, items: list[str], *, width: int = 108, fontsize: int = 11, gap: float = 0.035) -> float:
    for item in items:
        wrapped = textwrap.wrap(item, width=width) or [item]
        for idx, line in enumerate(wrapped):
            prefix = "• " if idx == 0 else "  "
            ax.text(0.06, y, f"{prefix}{line}", fontsize=fontsize, color="#172b3f")
            y -= gap
        y -= gap * 0.22
    return y


def draw_box(ax, x: float, y: float, w: float, h: float, text: str, color: str = "#eaf2fb") -> None:
    patch = FancyBboxPatch(
        (x, y),
        w,
        h,
        boxstyle="round,pad=0.012,rounding_size=0.02",
        linewidth=1.2,
        edgecolor="#2f4f6f",
        facecolor=color,
    )
    ax.add_patch(patch)
    ax.text(x + w / 2, y + h / 2, text, ha="center", va="center", fontsize=10, color="#10253d")


def draw_arrow(ax, x1: float, y1: float, x2: float, y2: float) -> None:
    ax.add_patch(FancyArrowPatch((x1, y1), (x2, y2), arrowstyle="->", mutation_scale=12, color="#244564", lw=1.2))


def add_cover_page(pdf: PdfPages) -> None:
    fig = plt.figure(figsize=(11.69, 8.27))
    ax = fig.add_axes([0, 0, 1, 1])
    ax.axis("off")

    ax.add_patch(FancyBboxPatch((0.04, 0.04), 0.92, 0.92, boxstyle="round,pad=0.02,rounding_size=0.03", fc="#f4f8fc", ec="#2a4668", lw=2))
    ax.text(0.08, 0.82, "Legal AI Platform", fontsize=34, fontweight="bold", color="#0f2742")
    ax.text(0.08, 0.76, "Full Technical & Architecture Report", fontsize=21, color="#2e4d6b")
    ax.text(0.08, 0.69, "Backend Deep Dive + AI Stack + Frontend Overview + Diagrams", fontsize=13, color="#45617f")
    ax.text(0.08, 0.58, "Generated from live codebase inspection", fontsize=12, color="#3e5b79")
    ax.text(0.08, 0.54, f"Workspace: {ROOT}", fontsize=10, color="#5f7891")
    ax.text(0.08, 0.49, "Report date: March 29, 2026", fontsize=12, color="#224262")
    ax.text(0.08, 0.44, "Scope: backend APIs, models, AI agents/services, architecture, and selected frontend coverage", fontsize=11, color="#3e5b79")

    pdf.savefig(fig)
    plt.close(fig)


def add_inventory_page(
    pdf: PdfPages,
    endpoints: list[dict],
    models: list[dict],
    schemas: list[dict],
    ai_agents: list[dict],
    ai_modules: list[str],
    frontend_calls: list[str],
) -> None:
    fig = plt.figure(figsize=(11.69, 8.27))
    ax = fig.add_axes([0, 0, 1, 1])
    ax.axis("off")

    draw_title(ax, "System Inventory", "Project footprint extracted from source code")

    endpoint_by_method = defaultdict(int)
    endpoint_by_router = defaultdict(int)
    for ep in endpoints:
        endpoint_by_method[ep["method"]] += 1
        endpoint_by_router[ep["router"]] += 1

    top_routers = sorted(endpoint_by_router.items(), key=lambda x: x[1], reverse=True)[:8]
    method_summary = ", ".join(f"{m}:{c}" for m, c in sorted(endpoint_by_method.items()))

    y = 0.83
    bullets = [
        f"Backend routers scanned: {len(endpoint_by_router)}",
        f"Total API endpoints detected: {len(endpoints)} ({method_summary})",
        "Top endpoint domains: " + ", ".join(f"{name} ({count})" for name, count in top_routers),
        f"SQLAlchemy models: {len(models)}",
        f"Pydantic API schemas: {len(schemas)}",
        f"AI agent files: {len(ai_agents)}",
        f"AI service modules: {len(ai_modules)}",
        f"Frontend API client calls mapped: {len(frontend_calls)}",
    ]
    y = draw_bullets(ax, y, bullets, width=112, fontsize=12, gap=0.042)

    ax.text(0.05, y - 0.02, "Core Technology Stack", fontsize=14, fontweight="bold", color="#133150")
    y -= 0.07
    stack_items = [
        "Backend: FastAPI + SQLAlchemy + Pydantic Settings + JOSE JWT + Passlib",
        "Storage: PostgreSQL (primary), MinIO object storage, FAISS local vector index",
        "AI/NLP: OpenAI-compatible client gateway, Groq/OpenRouter/OpenAI compatibility, SentenceTransformers embeddings + reranker",
        "Transcription: Speechmatics API + local Whisper pipeline fallback",
        "Frontend: React + TypeScript single-page legal copilot desk + separate client portal app",
    ]
    draw_bullets(ax, y, stack_items, width=110, fontsize=11, gap=0.038)

    pdf.savefig(fig)
    plt.close(fig)


def add_architecture_diagram_page(pdf: PdfPages) -> None:
    fig = plt.figure(figsize=(11.69, 8.27))
    ax = fig.add_axes([0, 0, 1, 1])
    ax.axis("off")
    draw_title(ax, "Architecture Diagram", "High-level runtime architecture")

    draw_box(ax, 0.05, 0.69, 0.18, 0.11, "Lawyer Frontend\nReact + TS", "#edf4fb")
    draw_box(ax, 0.05, 0.53, 0.18, 0.11, "Client Portal\nReact + TS", "#edf4fb")
    draw_box(ax, 0.29, 0.61, 0.2, 0.16, "FastAPI Backend\nRouters + Auth + Tenant Scope", "#e7f2ff")
    draw_box(ax, 0.55, 0.7, 0.18, 0.09, "Copilot Service\nIntent Router", "#eef7e8")
    draw_box(ax, 0.55, 0.58, 0.18, 0.09, "RAG Service\nHybrid Retrieval", "#eef7e8")
    draw_box(ax, 0.55, 0.46, 0.18, 0.09, "AI Agents\nReasoning / Timeline /\nDrafting / Verifier / etc.", "#eef7e8")
    draw_box(ax, 0.79, 0.72, 0.16, 0.08, "LLM Gateway\nGroq/OpenAI/OpenRouter", "#fff5e8")
    draw_box(ax, 0.79, 0.60, 0.16, 0.08, "External Research\nTavily/SerpAPI", "#fff5e8")
    draw_box(ax, 0.79, 0.48, 0.16, 0.08, "Speechmatics +\nLocal Whisper", "#fff5e8")
    draw_box(ax, 0.29, 0.39, 0.2, 0.12, "Document AI Pipeline\nExtract -> NER -> Redact -> Chunk", "#e8f4ef")
    draw_box(ax, 0.55, 0.31, 0.18, 0.09, "Vector Store\nFAISS + metadata", "#e8f4ef")
    draw_box(ax, 0.79, 0.31, 0.16, 0.09, "PostgreSQL + MinIO", "#e8f4ef")

    draw_arrow(ax, 0.23, 0.745, 0.29, 0.70)
    draw_arrow(ax, 0.23, 0.585, 0.29, 0.64)
    draw_arrow(ax, 0.49, 0.69, 0.55, 0.74)
    draw_arrow(ax, 0.49, 0.69, 0.55, 0.62)
    draw_arrow(ax, 0.49, 0.66, 0.55, 0.50)
    draw_arrow(ax, 0.73, 0.75, 0.79, 0.76)
    draw_arrow(ax, 0.73, 0.62, 0.79, 0.64)
    draw_arrow(ax, 0.73, 0.50, 0.79, 0.52)
    draw_arrow(ax, 0.49, 0.45, 0.55, 0.35)
    draw_arrow(ax, 0.73, 0.35, 0.79, 0.35)
    draw_arrow(ax, 0.49, 0.43, 0.49, 0.39)

    ax.text(0.05, 0.17, "All user-facing operations are tenant-scoped and flow through authenticated APIs.", fontsize=11, color="#294868")
    ax.text(0.05, 0.13, "AI stack combines deterministic heuristics + LLM enhancement + grounding verification.", fontsize=11, color="#294868")

    pdf.savefig(fig)
    plt.close(fig)


def add_ai_flow_diagram_page(pdf: PdfPages, intents: list[str], ai_agents: list[dict]) -> None:
    fig = plt.figure(figsize=(11.69, 8.27))
    ax = fig.add_axes([0, 0, 1, 1])
    ax.axis("off")
    draw_title(ax, "AI Orchestration Flow", "Copilot intent routing, agent execution, and evidence grounding")

    draw_box(ax, 0.06, 0.72, 0.18, 0.11, "User Prompt\n(case/doc/global)", "#edf4fb")
    draw_box(ax, 0.29, 0.72, 0.2, 0.11, "Command Parsing Service\nintent + target + count", "#eaf2ff")
    draw_box(ax, 0.54, 0.72, 0.2, 0.11, "Copilot Service\nhandler dispatch", "#e7f7eb")
    draw_box(ax, 0.79, 0.72, 0.15, 0.11, "Response\nanswer + metadata + sources", "#f5f8fc")

    draw_box(ax, 0.13, 0.50, 0.24, 0.12, "RAG path:\nRetrievalAgent -> hybrid retrieve\n-> VerifierAgent", "#eef7e8")
    draw_box(ax, 0.43, 0.50, 0.24, 0.12, "Specialized intent agents:\nCaseReasoning, Timeline,\nDocumentComparison, Drafting,\nBooking, PromptOptimizer", "#eef7e8")
    draw_box(ax, 0.73, 0.50, 0.21, 0.12, "Optional external research\n(Tavily / SerpAPI)\nthen synthesis", "#fff5e8")

    draw_box(ax, 0.13, 0.30, 0.24, 0.12, "Workflow endpoint:\nIntake -> Retrieval ->\nReasoning -> Timeline ->\nBooking -> Verifier -> Drafting", "#e8f4ef")
    draw_box(ax, 0.43, 0.30, 0.24, 0.12, "Document intelligence:\nExtract -> NER -> PII redaction\n-> chunk -> embed/index\n-> summarize/insights", "#e8f4ef")
    draw_box(ax, 0.73, 0.30, 0.21, 0.12, "Voice pipeline:\nupload/record -> transcription\nSpeechmatics or local fallback\n-> transcript intake agent", "#e8f4ef")

    draw_arrow(ax, 0.24, 0.775, 0.29, 0.775)
    draw_arrow(ax, 0.49, 0.775, 0.54, 0.775)
    draw_arrow(ax, 0.74, 0.775, 0.79, 0.775)
    draw_arrow(ax, 0.54, 0.72, 0.25, 0.62)
    draw_arrow(ax, 0.64, 0.72, 0.55, 0.62)
    draw_arrow(ax, 0.70, 0.72, 0.83, 0.62)
    draw_arrow(ax, 0.25, 0.50, 0.79, 0.72)
    draw_arrow(ax, 0.55, 0.50, 0.84, 0.72)
    draw_arrow(ax, 0.83, 0.50, 0.86, 0.72)
    draw_arrow(ax, 0.25, 0.50, 0.25, 0.42)
    draw_arrow(ax, 0.55, 0.50, 0.55, 0.42)
    draw_arrow(ax, 0.83, 0.50, 0.83, 0.42)

    ax.text(0.06, 0.20, "Recognized intents", fontsize=12, fontweight="bold", color="#123250")
    ax.text(
        0.06,
        0.16,
        ", ".join(intents[:14]) if intents else "No intents parsed",
        fontsize=9.5,
        color="#2e4d6b",
    )
    ax.text(0.06, 0.12, f"Agent classes detected: {len(ai_agents)}", fontsize=10.5, color="#2e4d6b")

    pdf.savefig(fig)
    plt.close(fig)


def add_data_model_page(pdf: PdfPages, models: list[dict]) -> None:
    fig = plt.figure(figsize=(11.69, 8.27))
    ax = fig.add_axes([0, 0, 1, 1])
    ax.axis("off")
    draw_title(ax, "Data Model Architecture", "Primary entities and relationships")

    draw_box(ax, 0.08, 0.68, 0.16, 0.09, "Tenant", "#edf4fb")
    draw_box(ax, 0.30, 0.68, 0.16, 0.09, "User", "#edf4fb")
    draw_box(ax, 0.52, 0.68, 0.16, 0.09, "Client", "#edf4fb")
    draw_box(ax, 0.74, 0.68, 0.16, 0.09, "Case", "#edf4fb")

    draw_box(ax, 0.08, 0.51, 0.16, 0.09, "Document", "#e8f4ef")
    draw_box(ax, 0.30, 0.51, 0.16, 0.09, "DocumentChunk", "#e8f4ef")
    draw_box(ax, 0.52, 0.51, 0.16, 0.09, "DocumentEntity", "#e8f4ef")
    draw_box(ax, 0.74, 0.51, 0.16, 0.09, "VoiceRecording", "#e8f4ef")

    draw_box(ax, 0.19, 0.34, 0.2, 0.09, "ConsultationRequest", "#fff5e8")
    draw_box(ax, 0.47, 0.34, 0.2, 0.09, "ClientPortalAccount", "#fff5e8")
    draw_box(ax, 0.75, 0.34, 0.17, 0.09, "PortalLoginCode", "#fff5e8")

    draw_arrow(ax, 0.24, 0.725, 0.30, 0.725)
    draw_arrow(ax, 0.46, 0.725, 0.52, 0.725)
    draw_arrow(ax, 0.68, 0.725, 0.74, 0.725)
    draw_arrow(ax, 0.82, 0.68, 0.16, 0.60)
    draw_arrow(ax, 0.82, 0.68, 0.82, 0.60)
    draw_arrow(ax, 0.16, 0.51, 0.30, 0.56)
    draw_arrow(ax, 0.16, 0.51, 0.52, 0.56)
    draw_arrow(ax, 0.82, 0.51, 0.29, 0.43)
    draw_arrow(ax, 0.82, 0.51, 0.57, 0.43)
    draw_arrow(ax, 0.67, 0.38, 0.75, 0.38)

    top_models = ", ".join([m["class_name"] for m in models[:10]])
    ax.text(0.05, 0.19, "Model inventory (first 10):", fontsize=11, fontweight="bold", color="#183754")
    ax.text(0.05, 0.155, top_models, fontsize=9.5, color="#345773")
    ax.text(0.05, 0.115, "Database-level isolation is driven by tenant_id across operational entities.", fontsize=10.5, color="#345773")

    pdf.savefig(fig)
    plt.close(fig)


def add_backend_ai_page(
    pdf: PdfPages,
    ai_modules: list[str],
    ai_agents: list[dict],
    intents: list[str],
    env: dict[str, str],
) -> None:
    fig = plt.figure(figsize=(11.69, 8.27))
    ax = fig.add_axes([0, 0, 1, 1])
    ax.axis("off")
    draw_title(ax, "Backend AI Runtime", "Capabilities implemented in services and agents")

    configured_provider = env.get("LLM_BASE_URL") or "configured at runtime"
    llm_model = env.get("LLM_MODEL") or "from settings/default"
    summary_model = env.get("SUMMARY_AGENT_MODEL") or "inherits LLM model"
    local_transcription_model = env.get("LOCAL_TRANSCRIPTION_MODEL") or "openai/whisper-tiny (default)"
    reranker_model = env.get("RERANKER_MODEL") or "cross-encoder/ms-marco-MiniLM-L-6-v2 (default)"

    key_stack = [
        f"LLM gateway supports OpenAI-compatible providers (current base URL: {configured_provider}).",
        f"Primary generation model: {llm_model}; summary model: {summary_model}.",
        "Copilot path combines intent parsing, targeted handlers, RAG, verifier checks, and optional external web research.",
        "Hybrid retrieval = lexical BM25 + semantic vector search + cross-encoder reranking.",
        "Document intelligence pipeline: extraction, cleaning, NER, PII redaction, chunking, embedding, indexing, summarization.",
        f"Transcription supports Speechmatics first, then robust local fallback ({local_transcription_model}).",
        f"Reranker model: {reranker_model}.",
    ]

    y = 0.83
    y = draw_bullets(ax, y, key_stack, width=106, fontsize=11, gap=0.038)
    ax.text(0.05, y - 0.02, "Detected AI service modules", fontsize=12.5, fontweight="bold", color="#153250")
    y -= 0.06
    y = draw_bullets(ax, y, [", ".join(ai_modules)], width=118, fontsize=9.6, gap=0.032)

    ax.text(0.05, y - 0.02, "Detected copilot intents", fontsize=12.5, fontweight="bold", color="#153250")
    y -= 0.06
    intent_text = ", ".join(intents) if intents else "n/a"
    y = draw_bullets(ax, y, [intent_text], width=116, fontsize=9.8, gap=0.032)

    ax.text(0.05, y - 0.02, f"Agent count: {len(ai_agents)}", fontsize=11, color="#254969")

    pdf.savefig(fig)
    plt.close(fig)


def add_frontend_page(pdf: PdfPages, frontend_calls: list[str], portal_calls: list[str]) -> None:
    fig = plt.figure(figsize=(11.69, 8.27))
    ax = fig.add_axes([0, 0, 1, 1])
    ax.axis("off")
    draw_title(ax, "Frontend Coverage", "Main workspace UI + client portal")

    bullets = [
        "Primary app is a one-page legal command center with sidebar, top runtime controls, copilot center, and contextual side panels.",
        "Integrated workspace tabs include workflow, intake, intelligence, and evidence surfaces.",
        "Dark mode is implemented through CSS custom properties and persisted in localStorage.",
        "Copilot composer supports scoped prompts, retrieval depth, external research toggle, and deep workflow trigger.",
        "Upload/record UX supports PDF evidence and voice-note ingestion with transcript display and intake generation.",
        "Client portal is separated from internal workspace and enforces client-safe feature boundaries.",
        "Client portal authentication includes password policy + email-based six-digit verification code flow.",
    ]
    y = 0.83
    y = draw_bullets(ax, y, bullets, width=108, fontsize=11, gap=0.037)

    ax.text(0.05, y - 0.02, "Main app API usage (frontend/src/lib/api.ts)", fontsize=12.5, fontweight="bold", color="#133050")
    y -= 0.06
    y = draw_bullets(ax, y, [", ".join(frontend_calls[:18])], width=116, fontsize=9.4, gap=0.031)

    ax.text(0.05, y - 0.02, "Client portal API usage", fontsize=12.5, fontweight="bold", color="#133050")
    y -= 0.06
    draw_bullets(ax, y, [", ".join(portal_calls[:12])], width=116, fontsize=9.6, gap=0.031)

    pdf.savefig(fig)
    plt.close(fig)


def add_security_ops_page(pdf: PdfPages, env: dict[str, str]) -> None:
    fig = plt.figure(figsize=(11.69, 8.27))
    ax = fig.add_axes([0, 0, 1, 1])
    ax.axis("off")
    draw_title(ax, "Security, Reliability & Operations", "Cross-cutting controls implemented in code")

    secret_presence = {
        "GROQ_API_KEY": bool(env.get("GROQ_API_KEY")),
        "OPENAI_API_KEY": bool(env.get("OPENAI_API_KEY")),
        "TAVILY_API_KEY": bool(env.get("TAVILY_API_KEY")),
        "SERPAPI_API_KEY": bool(env.get("SERPAPI_API_KEY")),
        "SPEECHMATICS_API_KEY": bool(env.get("SPEECHMATICS_API_KEY")),
    }

    bullets = [
        "JWT authentication for staff and dedicated token type for client portal accounts.",
        "Rate limiter service protects staff login, portal login-code issuance, and code verification endpoints.",
        "Upload guardrails enforce content type and size limits for documents and voice inputs.",
        "Tenant-scoped queries are applied across API routes to isolate workspace data.",
        "Storage service sanitizes object names and ensures bucket readiness in MinIO.",
        "Request middleware injects request IDs and processing-time headers for traceability.",
        "Transcription path handles provider HTML/error anomalies and falls back to local inference.",
        "Schema patcher applies legacy DB compatibility updates on startup.",
    ]
    y = 0.83
    y = draw_bullets(ax, y, bullets, width=108, fontsize=11, gap=0.038)

    ax.text(0.05, y - 0.02, "Provider key presence (.env, values redacted)", fontsize=12.5, fontweight="bold", color="#153250")
    y -= 0.06
    key_lines = [f"{name}: {'present' if present else 'not set'}" for name, present in secret_presence.items()]
    draw_bullets(ax, y, key_lines, width=90, fontsize=11, gap=0.038)

    pdf.savefig(fig)
    plt.close(fig)


def add_endpoint_appendix(pdf: PdfPages, endpoints: list[dict]) -> None:
    sorted_eps = sorted(endpoints, key=lambda item: (item["router"], item["path"], item["method"]))
    lines = [f"[{ep['router']}] {ep['method']:<6} {ep['path']}" for ep in sorted_eps]
    chunk_size = 35
    chunks = [lines[i : i + chunk_size] for i in range(0, len(lines), chunk_size)]

    for page_index, chunk in enumerate(chunks, start=1):
        fig = plt.figure(figsize=(11.69, 8.27))
        ax = fig.add_axes([0, 0, 1, 1])
        ax.axis("off")
        draw_title(ax, f"Appendix A: Endpoint Catalog ({page_index}/{len(chunks)})", "All detected API routes")
        y = 0.86
        for line in chunk:
            wrapped = textwrap.wrap(line, width=122) or [line]
            for wline in wrapped:
                ax.text(0.05, y, wline, fontsize=9.3, family="monospace", color="#1d3552")
                y -= 0.022
            y -= 0.003
        pdf.savefig(fig)
        plt.close(fig)


def add_model_schema_appendix(pdf: PdfPages, models: list[dict], schemas: list[dict], agents: list[dict]) -> None:
    fig = plt.figure(figsize=(11.69, 8.27))
    ax = fig.add_axes([0, 0, 1, 1])
    ax.axis("off")
    draw_title(ax, "Appendix B: Backend Model Inventory", "SQLAlchemy entities with key fields")

    y = 0.86
    for model in models:
        field_preview = ", ".join(model["fields"][:8])
        line = f"{model['class_name']} ({model['table']}): {field_preview}"
        wrapped = textwrap.wrap(line, width=118) or [line]
        for wline in wrapped:
            ax.text(0.05, y, wline, fontsize=9.5, color="#173451")
            y -= 0.024
        y -= 0.006
        if y < 0.08:
            break
    pdf.savefig(fig)
    plt.close(fig)

    schema_lines = [f"{item['name']} [{item['file']}]" for item in schemas]
    chunk_size = 45
    chunks = [schema_lines[i : i + chunk_size] for i in range(0, len(schema_lines), chunk_size)]
    for page_index, chunk in enumerate(chunks, start=1):
        fig = plt.figure(figsize=(11.69, 8.27))
        ax = fig.add_axes([0, 0, 1, 1])
        ax.axis("off")
        draw_title(
            ax,
            f"Appendix C: API Schema Classes ({page_index}/{len(chunks)})",
            "Pydantic request/response contract classes",
        )
        y = 0.86
        for line in chunk:
            ax.text(0.05, y, line, fontsize=10, color="#173451")
            y -= 0.0195
        pdf.savefig(fig)
        plt.close(fig)

    agent_lines = []
    for agent in agents:
        methods = ", ".join(agent["methods"]) if agent["methods"] else "no public methods found"
        agent_lines.append(f"{agent['class_name']} ({agent['file']}): {methods}")

    fig = plt.figure(figsize=(11.69, 8.27))
    ax = fig.add_axes([0, 0, 1, 1])
    ax.axis("off")
    draw_title(ax, "Appendix D: AI Agent Catalog", "Detected agent classes and public methods")
    y = 0.86
    for line in agent_lines:
        wrapped = textwrap.wrap(line, width=116) or [line]
        for wline in wrapped:
            ax.text(0.05, y, wline, fontsize=9.6, color="#173451")
            y -= 0.023
        y -= 0.004
    pdf.savefig(fig)
    plt.close(fig)


def generate_report() -> Path:
    endpoints, _ = collect_api_endpoints()
    models = collect_sqlalchemy_models()
    schemas = collect_pydantic_schemas()
    ai_agents = collect_ai_agents()
    ai_modules = collect_ai_service_modules()
    intents = collect_command_intents()
    frontend_calls = collect_frontend_api_calls()
    portal_calls = collect_portal_api_calls()
    env = read_env_summary()

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    with PdfPages(OUTPUT_FILE) as pdf:
        add_cover_page(pdf)
        add_inventory_page(pdf, endpoints, models, schemas, ai_agents, ai_modules, frontend_calls)
        add_architecture_diagram_page(pdf)
        add_ai_flow_diagram_page(pdf, intents, ai_agents)
        add_data_model_page(pdf, models)
        add_backend_ai_page(pdf, ai_modules, ai_agents, intents, env)
        add_frontend_page(pdf, frontend_calls, portal_calls)
        add_security_ops_page(pdf, env)
        add_endpoint_appendix(pdf, endpoints)
        add_model_schema_appendix(pdf, models, schemas, ai_agents)

        metadata = pdf.infodict()
        metadata["Title"] = "Legal AI Platform - Full Technical Report"
        metadata["Author"] = "Codex Report Generator"
        metadata["Subject"] = "Architecture, AI stack, backend, frontend"
        metadata["Keywords"] = "legal ai, fastapi, rag, architecture, agents"
        metadata["CreationDate"] = datetime.now()
        metadata["ModDate"] = datetime.now()

    return OUTPUT_FILE


if __name__ == "__main__":
    report_path = generate_report()
    print(f"Report generated: {report_path}")
