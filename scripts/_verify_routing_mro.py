"""Verify MRO + method ownership for CopilotIntentRoutingMixin."""
import sys
sys.path.insert(0, ".")

from backend.services.ai.copilot_service import CopilotService  # noqa: E402

TARGET = [
    "_normalize_role", "_normalize_mode", "_normalize_reasoning_level",
    "_should_use_trust_engine", "_chat_mode_needs_rag",
    "_permission_denied_response", "_agent_mode_required_response",
    "_looks_like_conversational_opening", "_build_chat_greeting_answer",
    "_build_chat_fallback_answer", "_respond_in_chat_mode",
    "_apply_workspace_scope", "_autocorrect_message", "_extract_count_hint",
    "_build_history_context", "_is_follow_up_message", "_apply_conversation_memory",
    "_normalize_allowed_ids", "_validate_scope_permissions",
    "_unsupported_intent_response", "_normalize_lookup_text",
]

mro_names = [c.__name__ for c in CopilotService.__mro__]
assert "CopilotIntentRoutingMixin" in mro_names, "CopilotIntentRoutingMixin not in MRO!"
assert mro_names[1] == "CopilotIntentRoutingMixin", f"Expected as first mixin, got: {mro_names}"

errors = []
for m in TARGET:
    owner = next((cls.__name__ for cls in CopilotService.__mro__ if m in cls.__dict__), None)
    if owner != "CopilotIntentRoutingMixin":
        errors.append(f"  {m} -> {owner}")

if errors:
    print("FAIL - wrong owner:")
    for e in errors:
        print(e)
    sys.exit(1)

print("ALL ASSERTIONS PASS")
print("MRO:", " -> ".join(mro_names))

cs = len(open("backend/services/ai/copilot_service.py", encoding="utf-8").readlines())
rt = len(open("backend/services/ai/copilot_intent_routing_service.py", encoding="utf-8").readlines())
print(f"copilot_service.py:               {cs} lines")
print(f"copilot_intent_routing_service.py: {rt} lines")
