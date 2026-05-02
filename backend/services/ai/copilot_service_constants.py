from __future__ import annotations

import re


READ_ONLY_ROLES = {"admin", "lawyer", "assistant", "client"}
CASE_WRITE_ROLES = {"admin", "lawyer"}

CLIENT_ALLOWED_INTENTS = {
    "list_cases",
    "list_case_documents",
    "list_case_appointments",
    "summarize_case",
    "summarize_document",
    "summarize_and_analyze_risks_case",
    "analyze_risks_case",
    "list_deadlines_case",
    "monitor_deadlines_case",
    "build_timeline_case",
    "generate_case_insights",
    "generate_case_memory",
    "evaluate_case_evidence",
    "trace_case_evidence",
    "compare_case_documents",
    "review_booking_case",
    "draft_negotiation_strategy",
    "draft_partner_strategy_note_case",
    "draft_contract_redline_case",
    "draft_client_email_case",
    "draft_internal_email_case",
    "ask_case",
    "ask_document",
    "ask_global",
    "summarize_global",
}

CHAT_ASSISTANT_INTENTS = {"ask_global", "summarize_global"}
CHAT_GREETING_PATTERN = re.compile(
    r"^(?:hi|hello|hey|good\s+morning|good\s+afternoon|good\s+evening|salam|salem|bonjour|bonsoir|yo)\b",
    re.IGNORECASE,
)
CHAT_THANKS_PATTERN = re.compile(
    r"\b(?:thanks?|thank\s+you|thx|much\s+appreciated)\b",
    re.IGNORECASE,
)

CRUD_INTENTS = {
    "create_case",
    "create_client",
    "create_prompt_library_entry",
    "update_case",
    "update_client",
    "delete_case",
    "delete_client",
    "update_case_appointment",
    "delete_case_appointment",
    "update_prompt_library_entry",
    "delete_prompt_library_entry",
    "create_case_appointment",
    "update_case_status",
    "request_document_upload",
    "request_audio_upload",
}

ACTION_CATEGORY_BY_INTENT = {
    "create_case": "crud",
    "create_client": "crud",
    "create_prompt_library_entry": "crud",
    "update_case": "crud",
    "update_client": "crud",
    "delete_case": "crud",
    "delete_client": "crud",
    "update_case_appointment": "crud",
    "delete_case_appointment": "crud",
    "update_prompt_library_entry": "crud",
    "delete_prompt_library_entry": "crud",
    "list_cases": "query",
    "list_clients": "query",
    "list_prompt_library": "query",
    "list_case_documents": "query",
    "list_case_appointments": "query",
    "request_document_upload": "crud",
    "request_audio_upload": "crud",
    "create_case_appointment": "crud",
    "update_case_status": "crud",
    "optimize_prompt": "analysis",
    "summarize_case": "analysis",
    "summarize_document": "analysis",
    "summarize_and_analyze_risks_case": "analysis",
    "analyze_risks_case": "analysis",
    "list_deadlines_case": "analysis",
    "build_timeline_case": "analysis",
    "generate_case_insights": "analysis",
    "generate_case_memory": "analysis",
    "evaluate_case_evidence": "analysis",
    "monitor_deadlines_case": "analysis",
    "compare_case_documents": "analysis",
    "review_booking_case": "analysis",
    "trace_case_evidence": "analysis",
    "draft_negotiation_strategy": "analysis",
    "draft_partner_strategy_note_case": "analysis",
    "draft_contract_redline_case": "analysis",
    "draft_client_email_case": "analysis",
    "draft_internal_email_case": "analysis",
    "ask_case": "query",
    "ask_document": "query",
    "ask_global": "query",
    "summarize_global": "analysis",
}

MATERIAL_BREACH_QUERY_KEYWORDS = (
    "material breach",
    "breach position",
    "strongest clause",
    "strongest clauses",
    "supporting clauses",
    "support a material breach",
    "supporting a material breach",
    "clause supports breach",
    "clauses support breach",
)

LEGAL_SEARCH_ELIGIBLE_INTENTS = {
    "ask_document",
    "ask_case",
    "ask_global",
    "summarize_global",
    "summarize_case",
    "summarize_document",
    "summarize_and_analyze_risks_case",
    "analyze_risks_case",
    "list_deadlines_case",
    "build_timeline_case",
    "compare_case_documents",
    "monitor_deadlines_case",
}

NUMBER_WORDS = {
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
    "eleven": 11,
    "twelve": 12,
}

FOLLOW_UP_COUNT_PATTERN = re.compile(
    r"\b(?:just|only|exactly|give\s+me|show\s+me|list)?\s*(\d{1,2}|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve)\b",
    re.IGNORECASE,
)
FOLLOW_UP_HINT_PATTERN = re.compile(
    r"\b(just|only|same|again|i meant|shorter|one)\b",
    re.IGNORECASE,
)

SUMMARY_STOP_HEADERS = (
    "main issues:",
    "key dates:",
    "legal risks:",
    "recommended next steps:",
    "risk assessment:",
    "practical next steps:",
    "deadlines:",
    "notice periods:",
    "other time references:",
    "evidence basis:",
)

HIGH_REASONING_ELIGIBLE_INTENTS = {
    "ask_document",
    "ask_case",
    "ask_global",
    "summarize_global",
}
HIGH_REASONING_STYLES = (
    (
        "strict_factual_legal",
        "Use a strict factual legal tone. Prioritize legal facts, direct citations, and explicit uncertainty statements when evidence is missing.",
    ),
    (
        "risk_focused",
        "Prioritize legal and operational risk identification. Emphasize exposure, uncertainty, and risk severity with citation-backed justification.",
    ),
    (
        "strategic_actionable",
        "Prioritize practical legal strategy and next actions. Recommend concrete steps anchored in cited evidence and avoid uncited assumptions.",
    ),
)
