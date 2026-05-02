from __future__ import annotations

import difflib
from typing import Any

from backend.core.config import settings
from backend.services.ai.llm_gateway import llm_gateway


class EditorAIService:
    def propose_edit(
        self,
        *,
        selected_text: str,
        instruction: str,
        full_document_context: str,
        citations: list[dict[str, Any]],
        citation_mode: str = "suggest",
    ) -> dict[str, Any]:
        selected = selected_text.strip()
        instruction_clean = instruction.strip()
        citation_labels = ", ".join(str(item.get("label") or item.get("filename") or "source") for item in citations[:5])

        client = llm_gateway.create_client("standard")
        if client:
            prompt = f"""You are editing a legal draft. Return only the replacement text.

Instruction: {instruction_clean}
Citation mode: {citation_mode}
Available citation anchors: {citation_labels or "none"}

Selected text:
{selected}

Document context:
{full_document_context[:12000]}

Rules:
- Do not invent facts.
- Preserve legal meaning unless the instruction explicitly asks for tone.
- If citations are useful, include short bracket references like [source: filename].
"""
            try:
                response = client.responses.create(
                    model=llm_gateway.resolve_model("standard"),
                    input=prompt,
                    temperature=0.2,
                    max_output_tokens=1200,
                )
                proposed = (response.output_text or "").strip()
                if proposed:
                    return self._build_response(selected, proposed, instruction_clean, citations)
            except Exception:
                pass

        proposed = self._fallback_rewrite(selected, instruction_clean)
        return self._build_response(selected, proposed, instruction_clean, citations)

    def _fallback_rewrite(self, selected: str, instruction: str) -> str:
        lowered = instruction.lower()
        text = " ".join(selected.split())
        if "formal" in lowered:
            return f"It is respectfully noted that {text[0].lower() + text[1:] if len(text) > 1 else text}"
        if "simpl" in lowered or "client" in lowered:
            return text.replace("shall", "will").replace("herein", "in this document")
        if "aggressive" in lowered:
            return f"We maintain that {text[0].lower() + text[1:] if len(text) > 1 else text}"
        if "diplomatic" in lowered:
            return f"We propose to address this constructively while preserving our client's position: {text}"
        if "short" in lowered or "concise" in lowered:
            return text[: max(120, int(len(text) * 0.65))].rstrip(" ,;") + ("." if text else "")
        if "expand" in lowered or "reason" in lowered:
            return f"{text}\n\nThis point should be read in light of the available case record, applicable obligations, and any source evidence confirmed by counsel."
        return text

    def _build_response(self, original: str, proposed: str, instruction: str, citations: list[dict[str, Any]]) -> dict[str, Any]:
        diff = list(difflib.unified_diff(
            original.splitlines(),
            proposed.splitlines(),
            fromfile="current",
            tofile="proposed",
            lineterm="",
        ))
        return {
            "proposed_text": proposed,
            "explanation": f"Proposed edit based on instruction: {instruction}",
            "confidence": "medium",
            "citations_used": citations[:5],
            "diff": {"format": "unified", "lines": diff},
        }


editor_ai_service = EditorAIService()
