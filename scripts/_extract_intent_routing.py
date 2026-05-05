"""
Extract routing/intent cluster from copilot_service.py into CopilotIntentRoutingMixin.

Methods extracted (21):
  _normalize_role, _normalize_mode, _normalize_reasoning_level,
  _should_use_trust_engine, _chat_mode_needs_rag,
  _permission_denied_response, _agent_mode_required_response,
  _looks_like_conversational_opening, _build_chat_greeting_answer,
  _build_chat_fallback_answer, _respond_in_chat_mode,
  _apply_workspace_scope, _autocorrect_message, _extract_count_hint,
  _build_history_context, _is_follow_up_message, _apply_conversation_memory,
  _normalize_allowed_ids, _validate_scope_permissions,
  _unsupported_intent_response, _normalize_lookup_text
"""
import ast
import re

SRC_PATH = "backend/services/ai/copilot_service.py"
DST_PATH = "backend/services/ai/copilot_intent_routing_service.py"

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

# Collect method ranges inside CopilotService
method_ranges: dict[str, tuple[int, int]] = {}
for node in ast.walk(tree):
    if isinstance(node, ast.ClassDef) and node.name == "CopilotService":
        for n in ast.walk(node):
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
                method_ranges[n.name] = (n.lineno, n.end_lineno)
        break


def full_range(name: str) -> tuple[int, int]:
    """Extend start backwards to include decorator lines."""
    start, end = method_ranges[name]
    i = start - 2  # 0-indexed line before the def
    while i >= 0:
        stripped = lines[i].strip()
        if stripped.startswith("@"):
            start = i + 1  # 1-indexed
            i -= 1
        else:
            break
    return start, end


# Build the method blocks (4-space indent = class body level)
blocks: list[tuple[str, list[str]]] = []
for name in TARGET:
    s, e = full_range(name)
    block_lines = lines[s - 1 : e]  # 0-indexed slice
    blocks.append((name, block_lines))

# Helper: de-indent 4 spaces (class body) and re-indent 4 spaces (same – mixin body)
# Since both source and destination use 4-space class-body indentation, the lines
# are already correct: we just need to keep them as-is.

# ---------- Substitutions needed for @staticmethod refs to CopilotService ----------
# _looks_like_conversational_opening, _build_chat_greeting_answer are staticmethods
# that will live in the new mixin class.  References using "CopilotService." in static
# methods must be updated to "CopilotIntentRoutingMixin." so the mixin stays standalone.
# Class-level pattern constants (CHAT_GREETING_PATTERN, CHAT_THANKS_PATTERN) are imported
# directly from copilot_service_constants.

STATIC_REF_SUBS = [
    (
        "CopilotService._looks_like_conversational_opening",
        "CopilotIntentRoutingMixin._looks_like_conversational_opening",
    ),
    (
        "CopilotService._build_chat_greeting_answer",
        "CopilotIntentRoutingMixin._build_chat_greeting_answer",
    ),
    (
        "CopilotService.CHAT_GREETING_PATTERN",
        "copilot_constants.CHAT_GREETING_PATTERN",
    ),
    (
        "CopilotService.CHAT_THANKS_PATTERN",
        "copilot_constants.CHAT_THANKS_PATTERN",
    ),
]


def apply_subs(text: str) -> str:
    for old, new in STATIC_REF_SUBS:
        text = text.replace(old, new)
    return text


HEADER = '''\
# pyright: reportAttributeAccessIssue=false, reportGeneralTypeIssues=false
from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional

from backend.services.ai import copilot_service_constants as copilot_constants
from backend.services.ai.agents.prompt_correction_agent import prompt_correction_agent
from backend.services.ai.llm_gateway import llm_gateway

logger = logging.getLogger(__name__)


class CopilotIntentRoutingMixin:
    """Intent classification and routing logic extracted from CopilotService.

    Provides:
      - input normalization (_normalize_role, _normalize_mode, _normalize_reasoning_level)
      - mode-routing decisions (_should_use_trust_engine, _chat_mode_needs_rag)
      - scope/permission gating (_apply_workspace_scope, _validate_scope_permissions)
      - conversation-memory routing (_apply_conversation_memory, _build_history_context)
      - chat-mode responses (_respond_in_chat_mode, _build_chat_greeting_answer, ...)
      - guard responses (_permission_denied_response, _agent_mode_required_response, ...)
    """
'''

output_lines: list[str] = [HEADER]

for name, block in blocks:
    raw_block = "\n".join(block)
    patched_block = apply_subs(raw_block)
    output_lines.append(patched_block)
    output_lines.append("")   # blank line between methods

output_lines.append("")  # trailing newline

final_text = "\n".join(output_lines) + "\n"

with open(DST_PATH, "w", encoding="utf-8") as f:
    f.write(final_text)

total_lines = len(final_text.splitlines())
print(f"Written {DST_PATH}: {total_lines} lines")
print(f"Methods extracted: {len(TARGET)}")
for name in TARGET:
    s, e = full_range(name)
    print(f"  L{s:4d}-{e:4d}  {name}")
