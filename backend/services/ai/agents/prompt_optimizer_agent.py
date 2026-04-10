from __future__ import annotations

import json
import re
from typing import Any

from backend.services.ai.agents.agent_output_formatter import AgentOutputFormatter
from backend.services.ai.agents.base_agent import BaseAgent, AgentResult
from backend.services.ai.llm_gateway import llm_gateway


class PromptOptimizerAgent(BaseAgent):
    agent_name = "prompt_optimizer_agent"
    SPELLING_FIXES = {
        "eksternal": "external",
        "externel": "external",
        "trasncript": "transcript",
        "comparision": "comparison",
        "sumarize": "summarize",
    }

    def __init__(self) -> None:
        self.client = llm_gateway.create_client()
        self.model = llm_gateway.default_model

    def optimize_query(
        self,
        *,
        raw_query: str,
        intent: str | None = None,
        target_type: str | None = None,
        target_id: int | None = None,
        allow_llm: bool = False,
    ) -> AgentResult:
        cleaned_query = self._normalize_text(raw_query)
        if not cleaned_query:
            return self.result(
                success=False,
                error="Prompt text is empty.",
                trace=["Prompt optimizer skipped because query text was empty."],
            )

        heuristic = self._heuristic_optimize(
            raw_query=cleaned_query,
            intent=intent,
            target_type=target_type,
            target_id=target_id,
        )
        trace = [
            "Built heuristic optimized prompt.",
        ]

        if self.client and allow_llm:
            llm_payload = self._generate_llm_optimization(
                raw_query=cleaned_query,
                intent=intent,
                target_type=target_type,
                target_id=target_id,
                heuristic_payload=heuristic,
            )
            if llm_payload:
                heuristic.update(llm_payload)
                heuristic["used_llm"] = True
                trace.append("Enhanced prompt optimization with LLM synthesis.")
            else:
                heuristic["used_llm"] = False
                trace.append("LLM optimization unavailable; kept heuristic optimization.")
        else:
            heuristic["used_llm"] = False
            if allow_llm:
                trace.append("No LLM client configured; kept heuristic optimization.")
            else:
                trace.append("Skipped LLM prompt optimization; kept heuristic optimization.")

        warnings: list[str] = []
        if heuristic.get("optimized_query") == cleaned_query:
            warnings.append("Prompt optimizer produced minimal changes.")

        return self.result(
            success=True,
            payload=heuristic,
            warnings=warnings,
            trace=trace,
        )

    def _heuristic_optimize(
        self,
        *,
        raw_query: str,
        intent: str | None,
        target_type: str | None,
        target_id: int | None,
    ) -> dict[str, Any]:
        normalized = self._normalize_text(raw_query)
        for wrong, fixed in self.SPELLING_FIXES.items():
            normalized = re.sub(rf"\b{re.escape(wrong)}\b", fixed, normalized, flags=re.IGNORECASE)
        normalized = normalized.replace("\n", " ").strip()
        normalized = " ".join(normalized.split())
        normalized = normalized.rstrip(" .,:;!?-")

        optimized_query = normalized
        if target_type == "case" and target_id is not None:
            optimized_query = f"For case #{target_id}, {normalized}"
        elif target_type == "document" and target_id is not None:
            optimized_query = f"For document #{target_id}, {normalized}"

        if intent == "optimize_prompt":
            optimized_query = (
                f"{optimized_query}. "
                "Use concise legal language, cite evidence where available, and provide practical next steps."
            )
        elif intent and intent.startswith("ask_"):
            optimized_query = f"{optimized_query}. Include a short evidence-grounded conclusion."

        return {
            "optimized_query": optimized_query,
            "strategy": "heuristic",
            "notes": "Normalized wording, corrected common typos, and added explicit legal task framing.",
        }

    def _generate_llm_optimization(
        self,
        *,
        raw_query: str,
        intent: str | None,
        target_type: str | None,
        target_id: int | None,
        heuristic_payload: dict[str, Any],
    ) -> dict[str, Any] | None:
        prompt = f"""
You are the Prompt Optimizer Agent in a legal AI platform.

Rewrite the user query into a better prompt for retrieval and answer generation.
Preserve user intent. Do not change language unless necessary.
Do not add legal facts that are not requested.

    {AgentOutputFormatter.build_quality_guidance(task="optimize a legal prompt for better retrieval and answer generation", structured_json=True)}

Return valid JSON only:
{{
  "optimized_query": "string",
  "notes": "string"
}}

Context:
- intent: {intent or "unknown"}
- target_type: {target_type or "global"}
- target_id: {target_id if target_id is not None else "none"}

Heuristic baseline:
{json.dumps(heuristic_payload, ensure_ascii=False, indent=2)}

User query:
{raw_query}
"""
        try:
            response = self.client.responses.create(model=self.model, input=prompt)
            raw_text = llm_gateway.extract_output_text(response).strip()
            if not raw_text:
                return None

            payload = self._extract_json_payload(raw_text)
            if not payload:
                return None

            optimized_query = self._normalize_text(payload.get("optimized_query"))
            if not optimized_query:
                return None

            return {
                "optimized_query": optimized_query,
                "strategy": "llm",
                "notes": self._normalize_text(payload.get("notes")) or "LLM optimized prompt for legal retrieval.",
            }
        except Exception:
            return None

    @staticmethod
    def _extract_json_payload(raw_text: str) -> dict[str, Any] | None:
        return AgentOutputFormatter.extract_json_payload(raw_text)

    @staticmethod
    def _normalize_text(value: Any) -> str:
        return AgentOutputFormatter.normalize_text(value)


prompt_optimizer_agent = PromptOptimizerAgent()
