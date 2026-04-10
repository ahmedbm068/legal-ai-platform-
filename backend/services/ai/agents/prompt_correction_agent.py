from __future__ import annotations

import json
import re
from typing import Any, Iterable

from backend.services.ai.agents.agent_output_formatter import AgentOutputFormatter
from backend.services.ai.agents.base_agent import BaseAgent, AgentResult
from backend.services.ai.llm_gateway import llm_gateway


class PromptCorrectionAgent(BaseAgent):
    agent_name = "prompt_correction_agent"
    SPELLING_FIXES = {
        "sumarize": "summarize",
        "summmarize": "summarize",
        "summarise": "summarize",
        "eksternal": "external",
        "externel": "external",
        "lojacally": "logically",
        "egsemple": "example",
        "eksample": "example",
        "caze": "case",
        "texte": "text",
        "trnascript": "transcript",
    }

    def __init__(self) -> None:
        self.client = llm_gateway.create_client()
        self.model = llm_gateway.default_model

    def correct_query(
        self,
        *,
        raw_query: str,
        conversation_history: Iterable[dict[str, Any]] | None = None,
        allow_llm: bool = False,
    ) -> AgentResult:
        original = self._normalize_text(raw_query)
        if not original:
            return self.result(
                success=False,
                error="Prompt text is empty.",
                trace=["Prompt correction skipped because input text was empty."],
            )

        heuristic = self._heuristic_correct(original)
        trace = ["Applied heuristic correction pass."]

        if self.client and allow_llm:
            llm_correction = self._llm_correct(original=original, heuristic=heuristic, conversation_history=conversation_history or [])
            if llm_correction:
                corrected = llm_correction
                trace.append("Applied LLM semantic correction.")
            else:
                corrected = heuristic
                trace.append("LLM semantic correction unavailable; kept heuristic correction.")
        else:
            corrected = heuristic
            if allow_llm:
                trace.append("No LLM client configured; kept heuristic correction.")
            else:
                trace.append("Skipped LLM semantic correction; kept heuristic correction.")

        changed = corrected != original
        return self.result(
            success=True,
            payload={
                "corrected_query": corrected,
                "changed": changed,
            },
            trace=trace,
            warnings=[] if changed else ["Prompt correction did not change the message."],
        )

    def _heuristic_correct(self, text: str) -> str:
        corrected = text
        for wrong, fixed in self.SPELLING_FIXES.items():
            corrected = re.sub(rf"\b{re.escape(wrong)}\b", fixed, corrected, flags=re.IGNORECASE)
        corrected = corrected.replace("\n", " ")
        corrected = re.sub(r"\s+", " ", corrected).strip()
        return corrected

    def _llm_correct(
        self,
        *,
        original: str,
        heuristic: str,
        conversation_history: Iterable[dict[str, Any]],
    ) -> str | None:
        compact_history = []
        for item in list(conversation_history)[-8:]:
            role = str(item.get("role") or "").strip()
            content = self._normalize_text(item.get("content"))
            if role in {"user", "assistant"} and content:
                compact_history.append({"role": role, "content": content[:220]})

        prompt = f"""
You are a multilingual semantic prompt-correction agent for a legal AI copilot.

Task:
- Correct spelling and grammar mistakes.
- Keep the same language as the original prompt.
- Preserve user intent exactly.
- Keep legal terms, case ids, document ids, and named entities unchanged.
- Keep it concise.

{AgentOutputFormatter.build_quality_guidance(task="correct a legal prompt without changing its intent", structured_json=True)}

Return JSON only:
{{
  "corrected_query": "string"
}}

Conversation context (JSON):
{json.dumps(compact_history, ensure_ascii=False)}

Original prompt:
{original}

Heuristic correction:
{heuristic}
"""
        try:
            response = self.client.responses.create(model=self.model, input=prompt)
            raw_text = llm_gateway.extract_output_text(response).strip()
            payload = self._extract_json(raw_text)
            if not payload:
                return None
            corrected = self._normalize_text(payload.get("corrected_query"))
            return corrected or None
        except Exception:
            return None

    @staticmethod
    def _extract_json(raw_text: str) -> dict[str, Any] | None:
        return AgentOutputFormatter.extract_json_payload(raw_text)

    @staticmethod
    def _normalize_text(value: Any) -> str:
        return AgentOutputFormatter.normalize_text(value)


prompt_correction_agent = PromptCorrectionAgent()
