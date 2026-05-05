"""Remove the 50 case-analysis methods from copilot_service.py in-place."""
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
    return start, end  # 1-indexed inclusive


# Build set of 1-indexed line numbers to delete
lines_to_delete: set[int] = set()
for m in target:
    full_start, full_end = get_full_range(m)
    for ln in range(full_start, full_end + 1):
        lines_to_delete.add(ln)

print(f"Lines to delete: {len(lines_to_delete)}")

# Keep all other lines; also collapse triple blank lines -> double blank
kept = []
for i, l in enumerate(lines, start=1):
    if i not in lines_to_delete:
        kept.append(l)

# Collapse excessive blank lines (3+ -> 2)
result = []
blank_run = 0
for l in kept:
    if l.strip() == "":
        blank_run += 1
        if blank_run <= 2:
            result.append(l)
    else:
        blank_run = 0
        result.append(l)

new_src = "\n".join(result) + "\n"
with open("backend/services/ai/copilot_service.py", "w", encoding="utf-8") as f:
    f.write(new_src)

orig_lines = len(lines)
new_lines = len(result)
print(f"Original: {orig_lines} lines")
print(f"After deletion: {new_lines} lines")
print(f"Net reduction: {orig_lines - new_lines} lines")
