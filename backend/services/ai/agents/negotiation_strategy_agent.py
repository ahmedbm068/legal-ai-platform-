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
        case_context: dict[str, Any] | None = None,
        case_snapshot: dict[str, Any] | None = None,
        use_external_research: bool = False,
    ) -> AgentResult:
        objective_text = self._normalize_text(objective) or "Reach a practical settlement or commercial resolution."
        requested_horizon_days = self._normalize_horizon_days(horizon_days)
        wants_timeline = requested_horizon_days is not None
        case_brief = self._build_case_brief(case_context=case_context, case_snapshot=case_snapshot)
        external_results = self._collect_external_research(objective=objective_text, use_external_research=use_external_research)

        heuristic_payload = self._build_heuristic_payload(
            objective=objective_text,
            horizon_days=requested_horizon_days,
            case_brief=case_brief,
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
        case_brief: dict[str, Any],
        external_results: list[dict[str, Any]],
        include_timeline: bool,
    ) -> dict[str, Any]:
        objective_lower = objective.lower()
        case_focus = self._select_case_focus(case_brief)
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

        opening_position = self._build_opening_position(objective=objective, case_focus=case_focus)
        target_outcome = self._build_target_outcome(objective=objective, case_focus=case_focus)
        if is_settlement_request:
            strategy_summary = self._build_strategy_summary(
                objective=objective,
                horizon_days=horizon_days,
                case_focus=case_focus,
                settlement=True,
            )
            opening_position = (
                f"Open with a without-prejudice proposal tied to the objective and the live case record{f' around {case_focus}' if case_focus else ''}. State the commercial ask, keep liability language reserved, and set a response deadline."
            )
            target_outcome = (
                f"Secure a written commercial resolution{f' on {case_focus}' if case_focus else ''} that preserves legal rights, avoids admissions, and leaves room for a controlled fallback if the first offer is resisted."
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
            strategy_summary = self._build_strategy_summary(
                objective=objective,
                horizon_days=horizon_days,
                case_focus=case_focus,
                settlement=False,
            )
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
        day_by_day_plan = self._build_day_by_day_plan(horizon_days=horizon_days, case_brief=case_brief) if include_timeline else []
        case_basis = self._build_case_basis(case_brief=case_brief)
        web_references = self._build_web_references(external_results)

        return {
            "objective": objective,
            "horizon_days": horizon_days,
            "strategy_summary": strategy_summary,
            "opening_position": opening_position,
            "target_outcome": target_outcome,
            "red_lines": red_lines,
            "concessions": concessions,
            "fallback_options": fallback_options,
            "day_by_day_plan": day_by_day_plan,
            "case_basis": case_basis,
            "closing_position": self._build_closing_position(case_focus=case_focus),
            "web_references": web_references,
            "case_context": self._format_case_context(case_brief=case_brief),
            "case_brief": case_brief,
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

                Draft a clearer, more practical negotiation strategy using the supplied objective, time horizon, and case brief.
{AgentOutputFormatter.build_quality_guidance(task="draft a negotiation strategy with a day-by-day plan", structured_json=True)}

Return valid JSON only with this exact schema:
{{
  "strategy_summary": "string",
                    "case_basis": ["string"],
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
    - If case facts are present, reuse them directly in the strategy and do not paraphrase them into boilerplate.
    - Prefer the case title, parties, issues, dates, or risks when available.
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
            case_basis = self._normalize_string_list(payload.get("case_basis"), limit=5)
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
                "case_basis": case_basis or heuristic_payload.get("case_basis") or [],
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
    def _build_opening_position(*, objective: str, case_focus: str | None) -> str:
        if case_focus:
            return (
                f"Open with a firm but collaborative position that keeps the objective in view and references the live case issue: {case_focus}."
            )
        return f"Open with a firm but collaborative position that keeps the objective in view: {objective}."

    @staticmethod
    def _build_target_outcome(*, objective: str, case_focus: str | None) -> str:
        if case_focus:
            return (
                f"Target a written resolution on {case_focus} that advances the objective while preserving escalation rights if the counterpart stalls."
            )
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
    def _build_closing_position(*, case_focus: str | None) -> str:
        if case_focus:
            return f"End the period with a written recap on {case_focus}, a defined response deadline, and a prepared escalation path."
        return "End the period with a written recap, a defined response deadline, and a prepared escalation path."

    @staticmethod
    def _build_strategy_summary(
        *,
        objective: str,
        horizon_days: int | None,
        case_focus: str | None,
        settlement: bool,
    ) -> str:
        if case_focus:
            if settlement:
                return (
                    f"Use the requested {horizon_days or 'next'}-day window to move the live case issue '{case_focus}' into a written without-prejudice resolution, anchoring every concession to the case record."
                )
            return (
                f"Use the requested {horizon_days or 'next'}-day window to clarify objectives around '{case_focus}', anchor on the case record, control concessions, and preserve a credible fallback."
            )
        if settlement:
            return "Use a without-prejudice settlement package: open with the main ask, preserve rights, and keep a smaller fallback ready."
        return "Use the requested window to clarify objectives, anchor on evidence, control concessions, and preserve a credible fallback."

    @staticmethod
    def _build_case_basis(*, case_brief: dict[str, Any]) -> list[str]:
        basis: list[str] = []
        case_title = case_brief.get("case_title")
        if case_title:
            basis.append(f"Case: {case_title}")

        summary_text = case_brief.get("summary_text")
        if summary_text:
            basis.append(f"Snapshot: {summary_text}")

        parties = case_brief.get("parties") or []
        if parties:
            basis.append("Parties: " + ", ".join(parties[:4]))

        main_issues = case_brief.get("main_issues") or []
        if main_issues:
            basis.append("Main issues: " + ", ".join(main_issues[:3]))

        key_dates = case_brief.get("key_dates") or []
        if key_dates:
            basis.append("Key dates: " + "; ".join(key_dates[:3]))

        risk_signals = case_brief.get("risk_signals") or []
        if risk_signals:
            basis.append("Risk signals: " + "; ".join(risk_signals[:3]))

        latest_intents = case_brief.get("latest_intents") or []
        if latest_intents:
            basis.append("Recent case memory: " + ", ".join(latest_intents[:3]))

        return basis[:5]

    @staticmethod
    def _format_case_context(*, case_brief: dict[str, Any]) -> str:
        parts: list[str] = []
        case_title = case_brief.get("case_title")
        if case_title:
            parts.append(f"Case: {case_title}")
        main_issues = case_brief.get("main_issues") or []
        if main_issues:
            parts.append(f"Issue: {main_issues[0]}")
        summary_text = case_brief.get("summary_text")
        if summary_text:
            parts.append(f"Snapshot: {summary_text}")
        key_dates = case_brief.get("key_dates") or []
        if key_dates:
            parts.append(f"Key date: {key_dates[0]}")
        risk_signals = case_brief.get("risk_signals") or []
        if risk_signals:
            parts.append(f"Risk: {risk_signals[0]}")
        return " | ".join(parts)

    @staticmethod
    def _select_case_focus(case_brief: dict[str, Any]) -> str | None:
        main_issues = case_brief.get("main_issues") or []
        for item in main_issues:
            text = str(item or "").strip()
            if text:
                return text

        summary_text = str(case_brief.get("summary_text") or "").strip()
        if summary_text:
            return summary_text

        case_title = str(case_brief.get("case_title") or "").strip()
        if case_title:
            return case_title
        return None

    @classmethod
    def _build_case_brief(
        cls,
        *,
        case_context: dict[str, Any] | None,
        case_snapshot: dict[str, Any] | None,
    ) -> dict[str, Any]:
        context = case_context if isinstance(case_context, dict) else {}
        snapshot = case_snapshot if isinstance(case_snapshot, dict) else {}
        context_case = context.get("case") if isinstance(context.get("case"), dict) else {}
        snapshot_case = snapshot.get("case") if isinstance(snapshot.get("case"), dict) else {}
        reasoning = snapshot.get("reasoning") if isinstance(snapshot.get("reasoning"), dict) else {}
        memory = context.get("memory") if isinstance(context.get("memory"), dict) else {}

        return {
            "case_title": cls._normalize_text(snapshot_case.get("title") or context_case.get("title")),
            "case_status": cls._normalize_text(snapshot_case.get("status") or context_case.get("status")),
            "jurisdiction_country": cls._normalize_text(
                snapshot_case.get("jurisdiction_country") or context_case.get("jurisdiction_country")
            ),
            "document_count": int(context_case.get("document_count") or snapshot.get("facts", {}).get("document_count") or 0),
            "summary_text": cls._normalize_text(snapshot.get("summary_text") or reasoning.get("narrative_summary") or reasoning.get("overview")),
            "parties": cls._normalize_string_list(reasoning.get("parties") or [], limit=6),
            "main_issues": cls._normalize_string_list(reasoning.get("main_issues") or [], limit=6),
            "key_dates": cls._format_case_key_dates(reasoning.get("key_dates") or [], limit=4),
            "legal_risks": cls._normalize_string_list(reasoning.get("legal_risks") or [], limit=6),
            "recommended_next_steps": cls._normalize_string_list(reasoning.get("recommended_next_steps") or [], limit=5),
            "risk_signals": cls._normalize_string_list(context.get("risk_signals") or [], limit=6),
            "latest_intents": cls._normalize_string_list(memory.get("latest_intents") or [], limit=5),
        }

    @staticmethod
    def _format_case_key_dates(values: Any, *, limit: int) -> list[str]:
        if not isinstance(values, list):
            return []

        formatted: list[str] = []
        for item in values:
            if not isinstance(item, dict):
                continue
            label = str(item.get("label") or "").strip()
            value = str(item.get("value") or "").strip()
            if not (label or value):
                continue
            if label and value:
                formatted.append(f"{label}: {value}")
            else:
                formatted.append(label or value)
            if len(formatted) >= limit:
                break
        return formatted

    @staticmethod
    def _build_day_by_day_plan(*, horizon_days: int, case_brief: dict[str, Any]) -> list[str]:
        case_focus = NegotiationStrategyAgent._select_case_focus(case_brief)
        focus_clause = f" around {case_focus}" if case_focus else ""
        if horizon_days <= 7:
            return [
                f"Day 1: define goals, red lines, and the walk-away point{focus_clause}.",
                f"Day 2: organize the evidence or business rationale into a short opening note{focus_clause}.",
                f"Day 3: send the first proposal and set a reply deadline tied to the case record{focus_clause}.",
                "Day 4: review the reaction and prepare the concession ladder.",
                "Day 5: narrow options, confirm what is negotiable, and what is not.",
                "Day 6: escalate to a fallback proposal if needed.",
                "Day 7: close with a written recap and the next deadline.",
            ]

        if horizon_days <= 10:
            return [
                f"Days 1-2: define the objective, evidence base, and negotiation position{focus_clause}.",
                f"Days 3-4: open with the strongest factual and commercial position{focus_clause}.",
                f"Days 5-6: test the counterparty's priorities and identify the tradeable issues.",
                f"Days 7-8: narrow the gap with controlled concessions that do not weaken the core position.",
                f"Days 9-10: table a fallback without-prejudice proposal and lock in a written recap.",
            ]

        first_block = [
            f"Days 1-2: define the objective, evidence base, and the negotiation team position{focus_clause}.",
            f"Days 3-4: open with the strongest factual and commercial position{focus_clause}.",
            f"Days 5-6: test the counterparty's priorities and identify tradeable issues.",
            f"Days 7-8: narrow the gap with controlled concessions.",
            f"Days 9-10: table a fallback without-prejudice proposal.",
            f"Days 11-12: pause to reassess leverage and deadline pressure against the current case record.",
            f"Days 13-14: escalate only if needed, using the prepared fallback.",
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