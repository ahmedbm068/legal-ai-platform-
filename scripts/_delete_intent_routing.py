"""Delete the 21 routing/intent methods from copilot_service.py."""
import ast

SRC_PATH = "backend/services/ai/copilot_service.py"

TARGET = [
    "_normalize_role",
    "_normalize_mode",
    "_normalize_reasoning_level",
    "_should_use_trust_engine",
    "_chat_mode_needs_rag",
    "_permission_denied_response",
    "_agent_mode_required_response",
    "_looks_like_conversational_opening",
    "_build_chat_greeting_answer",
    "_build_chat_fallback_answer",
    "_respond_in_chat_mode",
    "_apply_workspace_scope",
    "_autocorrect_message",
    "_extract_count_hint",
    "_build_history_context",
    "_is_follow_up_message",
    "_apply_conversation_memory",
    "_normalize_allowed_ids",
    "_validate_scope_permissions",
    "_unsupported_intent_response",
    "_normalize_lookup_text",
]

src = open(SRC_PATH, encoding="utf-8").read()
lines = src.splitlines()
tree = ast.parse(src)

method_ranges: dict[str, tuple[int, int]] = {}
for node in ast.walk(tree):
    if isinstance(node, ast.ClassDef) and node.name == "CopilotService":
        for n in ast.walk(node):
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
                method_ranges[n.name] = (n.lineno, n.end_lineno)
        break


def full_range(name: str) -> tuple[int, int]:
    start, end = method_ranges[name]
    i = start - 2
    while i >= 0:
        stripped = lines[i].strip()
        if stripped.startswith("@"):
            start = i + 1
            i -= 1
        else:
            break
    return start, end


lines_to_delete: set[int] = set()
for name in TARGET:
    s, e = full_range(name)
    for ln in range(s, e + 1):
        lines_to_delete.add(ln)

print(f"Lines to delete: {len(lines_to_delete)}")

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
with open(SRC_PATH, "w", encoding="utf-8") as f:
    f.write(new_src)

print(f"Original: {len(lines)} lines")
print(f"After deletion: {len(result)} lines")
print(f"Net reduction: {len(lines) - len(result)} lines")
