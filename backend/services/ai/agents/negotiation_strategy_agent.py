from __future__ import annotations

import json
import re
from typing import Any

from backend.services.ai.agents.agent_output_formatter import AgentOutputFormatter
from backend.services.ai.agents.base_agent import BaseAgent, AgentResult
from backend.services.ai.external_research_service import external_research_service
from backend.services.ai.llm_gateway import llm_gateway


class NegotiationStrategyAgent(BaseAgent):
    agent_name = "negotiation_strategy_agent"

    def __init__(self) -> None:
        self.client = llm_gateway.create_client()
        self.model = llm_gateway.default_model

    def draft_strategy(
        self,
        *,
        objective: str,
        horizon_days: int | None,
        case_context: str | None = None,
        use_external_research: bool = False,
    ) -> AgentResult:
        objective_text = self._normalize_text(objective) or "Reach a practical settlement or commercial resolution."
        requested_horizon_days = self._normalize_horizon_days(horizon_days)
        wants_timeline = requested_horizon_days is not None
        external_results = self._collect_external_research(objective=objective_text, use_external_research=use_external_research)

        heuristic_payload = self._build_heuristic_payload(
            objective=objective_text,
            horizon_days=requested_horizon_days,
            case_context=case_context,
            external_results=external_results,
            include_timeline=wants_timeline,
        )
        trace = [
            "Starting negotiation strategy drafting.",
            "Built heuristic negotiation strategy payload.",
        ]

        if self.client:
            llm_payload = self._generate_llm_strategy(heuristic_payload=heuristic_payload)
            if llm_payload:
                heuristic_payload.update(llm_payload)
                if not wants_timeline:
                    heuristic_payload["day_by_day_plan"] = []
                heuristic_payload["used_llm"] = True
                trace.append("Enhanced negotiation strategy payload with LLM synthesis.")
            else:
                heuristic_payload["used_llm"] = False
                trace.append("LLM synthesis unavailable; kept heuristic negotiation strategy payload.")
        else:
            heuristic_payload["used_llm"] = False
            trace.append("No LLM client configured; kept heuristic negotiation strategy payload.")

        if not wants_timeline:
            heuristic_payload["day_by_day_plan"] = []

        warnings: list[str] = []
        if not heuristic_payload.get("strategy_summary"):
            warnings.append("Negotiation strategy was generated from a generic fallback frame.")
        if use_external_research and external_results and not heuristic_payload.get("web_references"):
            warnings.append("External research was requested, but no usable web references were extracted.")

        return self.result(success=True, payload=heuristic_payload, warnings=warnings, trace=trace)

    def _build_heuristic_payload(
        self,
        *,
        objective: str,
        horizon_days: int | None,
        case_context: str | None,
        external_results: list[dict[str, Any]],
        include_timeline: bool,
    ) -> dict[str, Any]:
        objective_lower = objective.lower()
        is_settlement_request = any(
            token in objective_lower
            for token in [
                "without prejudice",
                "without-prejudice",
                "settlement",
                "term sheet",
                "offer",
                "counteroffer",
                "fallback",
                "proposal",
            ]
        )

        opening_position = self._build_opening_position(objective=objective)
        target_outcome = self._build_target_outcome(objective=objective)
        if is_settlement_request:
            strategy_summary = "Use a without-prejudice settlement package: open with the main ask, preserve rights, and keep a smaller fallback ready."
            opening_position = (
                f"Open with a without-prejudice proposal tied to the objective: {objective}. State the commercial ask, keep liability language reserved, and set a response deadline."
            )
            target_outcome = (
                "Secure a written commercial resolution that preserves legal rights, avoids admissions, and leaves room for a controlled fallback if the first offer is resisted."
            )
            red_lines = [
                "Do not admit liability or waive rights in the first offer.",
                "Do not trade away final settlement leverage before the counterparty responds.",
                "Do not let without-prejudice language become a vague open-ended discussion.",
            ]
            concessions = [
                "Offer a staged concession ladder: primary ask, then a narrower commercial fallback.",
                "Trade timing, payment sequencing, or process commitments before trading the core amount.",
                "Use a short decision window to keep pressure on the response.",
            ]
            fallback_options = [
                "Shift to a narrower without-prejudice package with reduced commercial terms and a firmer expiry date.",
                "Offer a split solution: partial immediate concession now, remainder only after performance or payment milestones.",
                "Prepare a final fallback with a clear walk-away line and an escalation-ready dispute brief.",
            ]
        else:
            red_lines = [
                "Do not concede liability wording before the facts, contract baseline, and commercial options are aligned.",
                "Do not give away final settlement leverage in the first contact.",
            ]
            concessions = [
                "Offer structured follow-up and a short decision window.",
                "Trade timing or process concessions before you trade money or admissions.",
            ]
            fallback_options = [
                "Move to a narrower without-prejudice exchange if the counterparty resists the main ask.",
                "Escalate to a second-tier proposal with tighter deadlines and a clear walk-away line.",
            ]
        day_by_day_plan = self._build_day_by_day_plan(horizon_days=horizon_days) if include_timeline else []
        web_references = self._build_web_references(external_results)

        return {
            "objective": objective,
            "horizon_days": horizon_days,
            "strategy_summary": strategy_summary if is_settlement_request else (
                f"Use the requested window to clarify objectives, anchor on evidence, control concessions, and preserve a credible fallback."
            ),
            "opening_position": opening_position,
            "target_outcome": target_outcome,
            "red_lines": red_lines,
            "concessions": concessions,
            "fallback_options": fallback_options,
            "day_by_day_plan": day_by_day_plan,
            "closing_position": "End the period with a written recap, a defined response deadline, and a prepared escalation path.",
            "web_references": web_references,
            "case_context": self._normalize_text(case_context),
            "confidence": "medium",
        }

    @staticmethod
    def _normalize_horizon_days(horizon_days: int | None) -> int | None:
        if horizon_days is None:
            return None
        try:
            normalized = int(horizon_days)
        except (TypeError, ValueError):
            return None
        return max(1, min(normalized, 30))

    def _generate_llm_strategy(self, *, heuristic_payload: dict[str, Any]) -> dict[str, Any] | None:
        prompt = f"""
You are the Negotiation Strategy Agent inside a legal AI platform.

Draft a clearer, more practical negotiation strategy using the supplied objective and time horizon.
{AgentOutputFormatter.build_quality_guidance(task="draft a negotiation strategy with a day-by-day plan", structured_json=True)}

Return valid JSON only with this exact schema:
{{
  "strategy_summary": "string",
  "opening_position": "string",
  "target_outcome": "string",
  "red_lines": ["string"],
  "concessions": ["string"],
  "fallback_options": ["string"],
  "day_by_day_plan": ["string"],
  "closing_position": "string",
    "web_references": ["string"],
  "confidence": "high"
}}

Rules:
- Be concrete and structured.
- Avoid generic negotiation advice.
- Keep the answer practical for the next few days or weeks.
- If the input is general, write a commercial legal negotiation plan that still reads as usable.
- Do not invent facts, parties, or case-specific evidence.

Context:
{json.dumps(heuristic_payload, ensure_ascii=False, indent=2)}
"""
        try:
            response = self.client.responses.create(model=self.model, input=prompt)
            raw_text = (response.output_text or "").strip()
            if not raw_text:
                return None

            payload = self._extract_json_payload(raw_text)
            if not payload:
                return None

            summary = self._normalize_text(payload.get("strategy_summary"))
            opening_position = self._normalize_text(payload.get("opening_position"))
            target_outcome = self._normalize_text(payload.get("target_outcome"))
            red_lines = self._normalize_string_list(payload.get("red_lines"), limit=5)
            concessions = self._normalize_string_list(payload.get("concessions"), limit=5)
            fallback_options = self._normalize_string_list(payload.get("fallback_options"), limit=5)
            day_by_day_plan = self._normalize_string_list(payload.get("day_by_day_plan"), limit=10)
            closing_position = self._normalize_text(payload.get("closing_position"))
            web_references = self._normalize_string_list(payload.get("web_references"), limit=5)
            confidence = self._normalize_text(payload.get("confidence")) or "medium"

            if not summary and not opening_position and not day_by_day_plan:
                return None

            return {
                "strategy_summary": summary or heuristic_payload.get("strategy_summary"),
                "opening_position": opening_position or heuristic_payload.get("opening_position"),
                "target_outcome": target_outcome or heuristic_payload.get("target_outcome"),
                "red_lines": red_lines or heuristic_payload.get("red_lines") or [],
                "concessions": concessions or heuristic_payload.get("concessions") or [],
                "fallback_options": fallback_options or heuristic_payload.get("fallback_options") or [],
                "day_by_day_plan": day_by_day_plan or heuristic_payload.get("day_by_day_plan") or [],
                "closing_position": closing_position or heuristic_payload.get("closing_position"),
                "web_references": web_references or heuristic_payload.get("web_references") or [],
                "confidence": confidence,
            }
        except Exception:
            return None

    def _collect_external_research(self, *, objective: str, use_external_research: bool) -> list[dict[str, Any]]:
        if not use_external_research:
            return []

        research = external_research_service.search(
            query=f"{objective} negotiation strategy settlement planning legal guidance",
            max_results=5,
        )
        if not research.get("used_external"):
            return []

        results = research.get("results") or []
        collected: list[dict[str, Any]] = []
        for item in results[:5]:
            title = self._normalize_text(item.get("title") or item.get("domain") or "Web Result")
            url = self._normalize_text(item.get("url"))
            snippet = self._normalize_text(item.get("snippet"))
            if not (title or url or snippet):
                continue
            collected.append({"title": title, "url": url, "snippet": snippet})
        return collected

    @staticmethod
    def _build_opening_position(*, objective: str) -> str:
        return f"Open with a firm but collaborative position that keeps the objective in view: {objective}."

    @staticmethod
    def _build_target_outcome(*, objective: str) -> str:
        return f"Target a written resolution that advances the objective while preserving escalation rights if the counterpart stalls."

    @staticmethod
    def _build_web_references(external_results: list[dict[str, Any]]) -> list[str]:
        references: list[str] = []
        for item in external_results[:3]:
            title = str(item.get("title") or "Web Result").strip()
            url = str(item.get("url") or "").strip()
            snippet = str(item.get("snippet") or "").strip()
            reference = title
            if url:
                reference += f" ({url})"
            elif snippet:
                reference += f": {snippet[:120]}"
            references.append(reference)
        return references

    @staticmethod
    def _build_day_by_day_plan(*, horizon_days: int) -> list[str]:
        if horizon_days <= 7:
            return [
                "Day 1: define goals, red lines, and the walk-away point.",
                "Day 2: organize the evidence or business rationale into a short opening note.",
                "Day 3: send the first proposal and set a reply deadline.",
                "Day 4: review the reaction and prepare the concession ladder.",
                "Day 5: narrow options, confirm what is negotiable, and what is not.",
                "Day 6: escalate to a fallback proposal if needed.",
                "Day 7: close with a written recap and the next deadline.",
            ]

        first_block = [
            "Days 1-2: define the objective, evidence base, and the negotiation team position.",
            "Days 3-4: open with the strongest factual and commercial position.",
            "Days 5-6: test the counterparty's priorities and identify tradeable issues.",
            "Days 7-8: narrow the gap with controlled concessions.",
            "Days 9-10: table a fallback without-prejudice proposal.",
            "Days 11-12: pause to reassess leverage and deadline pressure.",
            "Days 13-14: escalate only if needed, using the prepared fallback.",
            f"Day {horizon_days}: issue a final recap and confirm the next step or walk-away line.",
        ]
        if horizon_days <= 15:
            return first_block

        return first_block + [
            "Use any remaining time to repeat the fallback cycle only if fresh leverage appears.",
        ]

    @staticmethod
    def _extract_json_payload(raw_text: str) -> dict[str, Any] | None:
        candidate = raw_text.strip()
        if candidate.startswith("```"):
            candidate = candidate.strip("`")
            candidate = candidate.replace("json", "", 1).strip()
        try:
            payload = json.loads(candidate)
            return payload if isinstance(payload, dict) else None
        except json.JSONDecodeError:
            start = candidate.find("{")
            end = candidate.rfind("}")
            if start == -1 or end == -1 or end <= start:
                return None
            try:
                payload = json.loads(candidate[start : end + 1])
                return payload if isinstance(payload, dict) else None
            except json.JSONDecodeError:
                return None

    @staticmethod
    def _normalize_text(value: Any) -> str:
        return str(value or "").strip()

    @classmethod
    def _normalize_string_list(cls, values: Any, *, limit: int) -> list[str]:
        if not isinstance(values, list):
            return []

        normalized: list[str] = []
        for item in values:
            cleaned = cls._normalize_text(item).rstrip(".")
            if not cleaned:
                continue
            if cleaned not in normalized:
                normalized.append(cleaned)
            if len(normalized) >= limit:
                break
        return normalized


negotiation_strategy_agent = NegotiationStrategyAgent()