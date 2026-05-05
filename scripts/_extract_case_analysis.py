"""One-shot extraction script: builds copilot_case_analysis_service.py."""
import ast

src = open("backend/services/ai/copilot_service.py", encoding="utf-8").read()
lines = src.splitlines()
tree = ast.parse(src)

for node in ast.walk(tree):
    if isinstance(node, ast.ClassDef) and node.name == "CopilotService":
        all_methods = {
            n.name: (n.lineno, n.end_lineno)
            for n in ast.walk(node)
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        break

target = [
    "_result_indicates_insufficient_evidence",
    "_answer_material_breach_clause_question",
    "_build_material_breach_clause_rows",
    "_resolve_case_for_context",
    "_get_case_or_404",
    "_get_case_documents",
    "_get_case_consultation_requests",
    "_get_case_voice_recordings",
    "_safe_load_insights",
    "_ensure_document_summary",
    "_document_summary_unavailable_reason",
    "_run_case_reasoning",
    "_normalize_risk_items",
    "_build_case_document_resume_entry",
    "_to_summary_bullet_sentence",
    "_append_case_summary_bullet",
    "_build_evidence_story_bullets",
    "_build_full_case_document_context",
    "_generate_source_grounded_case_summary_bullets",
    "_build_timeline_summary_bullet",
    "_build_case_summary_bullets",
    "_build_case_overall_overview",
    "_build_case_key_takeaways",
    "_build_contextual_case_next_steps",
    "_wants_case_document_breakdown",
    "_build_case_people_role_lines",
    "_build_case_brief_summary_lines",
    "_extract_concise_summary_text",
    "_to_clean_summary_paragraph",
    "_summarize_document",
    "_summarize_case",
    "_summarize_and_analyze_case_risks",
    "_list_case_deadlines",
    "_parse_timeline_date_value",
    "_normalize_timeline_label",
    "_canonicalize_timeline_label",
    "_build_strict_case_timeline_text",
    "_build_case_timeline",
    "_generate_case_insights",
    "_generate_case_memory",
    "_evaluate_case_evidence",
    "_build_party_evidence_strength_answer",
    "_build_medcare_evidence_strength_answer",
    "_trace_case_evidence",
    "_monitor_deadlines_case",
    "_build_medcare_ranked_legal_risks_answer",
    "_analyze_case_risks",
    "_build_medcare_without_prejudice_strategy",
    "_review_case_booking",
    "_compare_case_documents",
]


def get_full_range(method_name):
    start, end = all_methods[method_name]
    i = start - 2
    while i >= 0:
        stripped = lines[i].strip()
        if stripped.startswith("@"):
            start = i + 1
            i -= 1
        else:
            break
    return start, end


ordered = sorted(target, key=lambda m: all_methods[m][0])

method_chunks = []
for m in ordered:
    full_start, full_end = get_full_range(m)
    chunk_lines = lines[full_start - 1 : full_end]
    # De-indent by 4 spaces (remove class body indent)
    de = []
    for l in chunk_lines:
        if l.startswith("    "):
            de.append(l[4:])
        else:
            de.append(l)
    method_chunks.append("\n".join(de))

mixin_body = "\n\n".join(method_chunks)

header = (
    "from __future__ import annotations\n"
    "\n"
    "import json\n"
    "import logging\n"
    "import re\n"
    "from datetime import datetime\n"
    "from typing import Any, Dict, List, Optional\n"
    "\n"
    "from fastapi import HTTPException, status\n"
    "from sqlalchemy.orm import Session\n"
    "\n"
    "from backend.core.config import settings\n"
    "from backend.models.case import Case\n"
    "from backend.models.consultation_request import ConsultationRequest\n"
    "from backend.models.document import Document\n"
    "from backend.models.voice_recording import VoiceRecording\n"
    "from backend.services.ai.agents.booking_agent import booking_agent\n"
    "from backend.services.ai.agents.case_memory_agent import case_memory_agent\n"
    "from backend.services.ai.agents.case_reasoning_agent import case_reasoning_agent\n"
    "from backend.services.ai.agents.deadline_obligation_agent import deadline_obligation_agent\n"
    "from backend.services.ai.agents.document_comparison_agent import document_comparison_agent\n"
    "from backend.services.ai.agents.evidence_strength_agent import evidence_strength_agent\n"
    "from backend.services.ai.agents.evidence_trace_agent import evidence_trace_agent\n"
    "from backend.services.ai.agents.insight_agent import insight_agent\n"
    "from backend.services.ai.agents.timeline_agent import timeline_agent\n"
    "from backend.services.ai.artifact_versioning_service import artifact_versioning_service\n"
    "from backend.services.ai.jurisdiction_context_service import jurisdiction_context_service\n"
    "from backend.services.ai.llm_gateway import llm_gateway\n"
    "from backend.services.ai.summarization_service import summarization_service\n"
    "from backend.services.calendar_assistant_tool_service import calendar_assistant_tool_service\n"
    "\n"
    "_logger = logging.getLogger(__name__)\n"
    "\n"
    "\n"
    "class CopilotCaseAnalysisMixin:\n"
    '    """Mixin: case reasoning, analysis, risk, timeline, and summary methods.\n'
    "\n"
    "    Extracted from CopilotService (R4).  All methods reference shared state\n"
    "    (self.rag_service, self.model, self.client, class constants) that is\n"
    '    defined on CopilotService and resolved at runtime via MRO.\n'
    '    """\n'
    "\n"
)

# Indent every method line by 4 spaces (they were de-indented from class body)
indented_body = "\n".join("    " + l if l.strip() else l for l in mixin_body.splitlines())

full_content = header + indented_body + "\n"

out_path = "backend/services/ai/copilot_case_analysis_service.py"
with open(out_path, "w", encoding="utf-8") as f:
    f.write(full_content)

total_lines = len(full_content.splitlines())
print(f"Written {out_path}: {total_lines} lines")
print(f"Methods extracted: {len(ordered)}")
for m in ordered:
    s, e = get_full_range(m)
    print(f"  L{s:5d}-{e:5d}  {m}")
