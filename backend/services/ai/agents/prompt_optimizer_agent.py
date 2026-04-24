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
    TASK_HINTS: dict[str, tuple[str, ...]] = {
        "risk_analysis": ("risk", "risks", "exposure", "liability", "mitigation"),
        "timeline": ("timeline", "chronology", "chronological", "sequence", "milestone"),
        "deadlines": ("deadline", "deadlines", "due date", "notice period", "cure period"),
        "drafting": ("draft", "email", "letter", "memo", "message"),
        "comparison": ("compare", "comparison", "difference", "vs", "versus"),
        "negotiation": ("negot", "settlement", "proposal", "fallback", "terms"),
        "summary": ("summary", "summarize", "overview", "brief"),
    }
    TASK_OUTPUT_FORMAT: dict[str, list[str]] = {
        "risk_analysis": [
            "Top legal and operational risks (ranked high to low).",
            "Evidence anchor for each risk (document or case fact).",
            "Mitigation options with practical next steps.",
        ],
        "timeline": [
            "Chronological timeline with explicit dates.",
            "Source anchor per timeline item.",
            "Immediate follow-up actions for the next 7 days.",
        ],
        "deadlines": [
            "Upcoming deadlines and legal windows.",
            "Business impact if each date is missed.",
            "Action checklist with owner and priority.",
        ],
        "drafting": [
            "Professional final draft text.",
            "Tone: concise, clear, legally precise.",
            "Short rationale bullets after the draft.",
        ],
        "comparison": [
            "Key similarities and differences.",
            "Legal or commercial impact of each difference.",
            "Recommendation on next action.",
        ],
        "negotiation": [
            "Primary position, fallback position, and walk-away line.",
            "Structured terms package (commercial + legal).",
            "Negotiation sequence for the next call/meeting.",
        ],
        "summary": [
            "Executive summary in plain legal language.",
            "Critical facts, uncertainties, and open questions.",
            "Recommended actions with clear priority.",
        ],
        "general": [
            "Short answer first.",
            "Evidence-grounded reasoning.",
            "Concrete next steps.",
        ],
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

        optimized_query = self._normalize_text(heuristic.get("optimized_query"))
        heuristic["optimized_query"] = optimized_query
        heuristic["unchanged"] = optimized_query == cleaned_query
        heuristic["applied_improvements"] = [
            self._normalize_text(item)
            for item in (heuristic.get("applied_improvements") or [])
            if self._normalize_text(item)
        ][:8]

        warnings: list[str] = []
        if heuristic.get("unchanged"):
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
        original_normalized = self._normalize_text(raw_query)
        normalized = original_normalized
        for wrong, fixed in self.SPELLING_FIXES.items():
            normalized = re.sub(rf"\b{re.escape(wrong)}\b", fixed, normalized, flags=re.IGNORECASE)
        normalized = normalized.replace("\n", " ").strip()
        normalized = " ".join(normalized.split())
        normalized = normalized.rstrip(" .,:;!?-")

        task_type = self._detect_task_type(normalized)
        language_hint = self._detect_language_hint(normalized)
        scope_text = self._build_scope_text(target_type=target_type, target_id=target_id)

        requirements = [
            "Ground key points in available workspace evidence and avoid invented facts.",
            "Flag uncertainty explicitly when evidence is missing.",
            "Keep the response practical and action-oriented.",
        ]
        if intent == "optimize_prompt" or (intent and intent.startswith("ask_")):
            requirements.append("Use concise professional legal language.")
        if language_hint != "english":
            requirements.append(f"Respond in {language_hint} unless the user asks for another language.")

        output_format = self.TASK_OUTPUT_FORMAT.get(task_type, self.TASK_OUTPUT_FORMAT["general"])

        sections: list[str] = [
            f"Objective: {normalized}.",
            f"Scope: {scope_text}",
            "Requirements:",
            *[f"- {item}" for item in requirements],
            "Output format:",
            *[f"- {item}" for item in output_format],
        ]
        optimized_query = "\n".join(sections).strip()

        spelling_changed = normalized != original_normalized
        applied_improvements = [
            "Added explicit objective and output structure.",
            "Added evidence-grounding and uncertainty rules.",
            f"Tailored output format for {task_type.replace('_', ' ')} tasks.",
        ]
        if scope_text != "current workspace context":
            applied_improvements.append("Bound the prompt to the active case/document scope.")
        if language_hint != "english":
            applied_improvements.append(f"Preserved language preference ({language_hint}).")
        if spelling_changed:
            applied_improvements.append("Corrected common prompt typos.")

        return {
            "optimized_query": optimized_query,
            "strategy": "heuristic",
            "notes": "Reframed the prompt into a task-structured legal instruction with evidence and output constraints.",
            "applied_improvements": applied_improvements,
            "unchanged": optimized_query == original_normalized,
        }

    def _detect_task_type(self, query: str) -> str:
        lowered = query.lower()
        for task_type, hints in self.TASK_HINTS.items():
            if any(hint in lowered for hint in hints):
                return task_type
        return "general"

    @staticmethod
    def _build_scope_text(*, target_type: str | None, target_id: int | None) -> str:
        if target_type == "case" and target_id is not None:
            return f"case #{target_id}"
        if target_type == "document" and target_id is not None:
            return f"document #{target_id}"
        return "current workspace context"

    @staticmethod
    def _detect_language_hint(query: str) -> str:
        if re.search(r"[\u0600-\u06FF]", query):
            return "arabic"

        lowered = query.lower()
        german_hints = (" und ", " bitte ", "vertrag", "haftung", "frist", "recht")
        if any(hint in lowered for hint in german_hints):
            return "german"

        return "english"

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
    "notes": "string",
    "applied_improvements": ["string"]
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

            llm_improvements = [
                self._normalize_text(item)
                for item in (payload.get("applied_improvements") or [])
                if self._normalize_text(item)
            ]

            return {
                "optimized_query": optimized_query,
                "strategy": "llm",
                "notes": self._normalize_text(payload.get("notes")) or "LLM optimized prompt for legal retrieval.",
                "applied_improvements": llm_improvements,
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
