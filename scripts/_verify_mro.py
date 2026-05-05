"""Quick MRO + method-ownership verification for CopilotCaseAnalysisMixin."""
import sys
sys.path.insert(0, ".")

from backend.services.ai.copilot_service import CopilotService  # noqa: E402

TARGET = [
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

mro_names = [c.__name__ for c in CopilotService.__mro__]
assert "CopilotCaseAnalysisMixin" in mro_names, "CopilotCaseAnalysisMixin not in MRO!"
idx_case = mro_names.index("CopilotCaseAnalysisMixin")
idx_high = mro_names.index("CopilotHighReasoningMixin")
assert idx_case < idx_high, f"MRO order wrong: {mro_names}"

errors = []
for m in TARGET:
    owner = next((cls.__name__ for cls in CopilotService.__mro__ if m in cls.__dict__), None)
    if owner != "CopilotCaseAnalysisMixin":
        errors.append(f"  {m} -> {owner}")

if errors:
    print("FAIL - wrong owner for:")
    for e in errors:
        print(e)
    sys.exit(1)

print("ALL ASSERTIONS PASS")
print("MRO:", " -> ".join(mro_names))

cs = len(open("backend/services/ai/copilot_service.py", encoding="utf-8").readlines())
mx = len(open("backend/services/ai/copilot_case_analysis_service.py", encoding="utf-8").readlines())
print(f"copilot_service.py: {cs} lines")
print(f"copilot_case_analysis_service.py: {mx} lines")
