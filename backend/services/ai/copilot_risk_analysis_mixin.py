from __future__ import annotations

import re
from typing import Any, Dict, List, Optional


class CopilotRiskAnalysisMixin:
    @classmethod
    def _expand_risks_from_reasoning(cls, reasoning_payload: Dict[str, Any]) -> List[str]:
        candidates: List[str] = []
        for issue in reasoning_payload.get("main_issues") or []:
            text = str(issue or "").strip()
            lowered = text.lower()
            if not text:
                continue
            if any(token in lowered for token in ["breach", "termination", "dispute", "deadline", "notice", "liability"]):
                candidates.append(text)
        return cls._normalize_risk_items(candidates)

    @classmethod
    def _extract_operational_risks_from_reasoning(cls, reasoning_payload: Dict[str, Any]) -> List[str]:
        candidates: List[str] = []

        for issue in reasoning_payload.get("main_issues") or []:
            text = str(issue or "").strip()
            lowered = text.lower()
            if not text:
                continue
            if any(token in lowered for token in cls.OPERATIONAL_RISK_KEYWORDS):
                candidates.append(text)

        for risk in reasoning_payload.get("legal_risks") or []:
            text = str(risk or "").strip()
            lowered = text.lower()
            if not text:
                continue
            if any(token in lowered for token in cls.OPERATIONAL_RISK_KEYWORDS):
                candidates.append(text)

        return cls._normalize_risk_items(candidates)

    @classmethod
    def _risk_token_set(cls, value: str) -> set[str]:
        tokens = re.findall(r"[a-z0-9]+", str(value or "").lower())
        return {
            token
            for token in tokens
            if len(token) > 2 and token not in cls.RISK_TOKEN_STOPWORDS
        }

    @classmethod
    def _supporting_source_filenames_for_risk(
        cls,
        *,
        risk_text: str,
        sources: List[Dict[str, Any]],
        max_items: int = 3,
    ) -> List[str]:
        risk_tokens = cls._risk_token_set(risk_text)

        fallback: List[str] = []
        scored: List[tuple[int, str]] = []
        for source in sources:
            filename = cls._normalize_text(str(source.get("filename") or ""))
            snippet = cls._normalize_text(str(source.get("snippet") or ""))
            if not filename:
                continue

            if filename not in fallback:
                fallback.append(filename)

            haystack = (filename + " " + snippet).lower()
            overlap = sum(1 for token in risk_tokens if token in haystack)
            if overlap > 0:
                scored.append((overlap, filename))

        ranked_sources: List[str] = []
        for _overlap, filename in sorted(scored, key=lambda item: (-item[0], item[1].lower())):
            if filename not in ranked_sources:
                ranked_sources.append(filename)
            if len(ranked_sources) >= max_items:
                break

        if ranked_sources:
            return ranked_sources[:max_items]
        return fallback[:max_items]

    @classmethod
    def _classify_risk_category(cls, value: str) -> str:
        lowered = str(value or "").lower()
        legal_hits = sum(1 for token in cls.LEGAL_RISK_KEYWORDS if token in lowered)
        operational_hits = sum(1 for token in cls.OPERATIONAL_RISK_KEYWORDS if token in lowered)

        if legal_hits == 0 and operational_hits == 0:
            if any(token in lowered for token in ["evidence", "documentation", "proof", "deadline", "notice"]):
                return "Legal"
            return "Operational"

        if legal_hits >= operational_hits:
            return "Legal"
        return "Operational"

    @classmethod
    def _score_risk_item(cls, *, risk_text: str, category: str) -> tuple[int, str]:
        lowered = str(risk_text or "").lower()
        score = 52

        if any(token in lowered for token in cls.HIGH_SEVERITY_RISK_KEYWORDS):
            score += 28
        if any(token in lowered for token in cls.MEDIUM_SEVERITY_RISK_KEYWORDS):
            score += 14
        if any(token in lowered for token in cls.SUPPORTING_EVIDENCE_RISK_KEYWORDS):
            score += 7

        if category == "Legal" and any(
            token in lowered
            for token in ["breach", "non-compliance", "non compliance", "liability", "termination"]
        ):
            score += 12
        if category == "Operational" and any(
            token in lowered
            for token in ["sla", "kpi", "invoice", "reconciliation", "delivery", "operations"]
        ):
            score += 14

        if category == "Legal":
            score += 4

        score = max(40, min(score, 96))
        if score >= 80:
            return score, "HIGH"
        if score >= 64:
            return score, "MEDIUM"
        return score, "LOW"

    def _build_ranked_case_risks(
        self,
        *,
        reasoning_payload: Dict[str, Any],
        wants_legal: bool,
        wants_operational: bool,
    ) -> List[Dict[str, Any]]:
        legal_candidates = self._normalize_risk_items(reasoning_payload.get("legal_risks") or [])
        for item in self._expand_risks_from_reasoning(reasoning_payload):
            if item not in legal_candidates:
                legal_candidates.append(item)

        operational_candidates = self._extract_operational_risks_from_reasoning(reasoning_payload)

        sources = list(reasoning_payload.get("sources") or [])
        combined_source_text = " ".join(
            [
                self._normalize_text(str(source.get("filename") or ""))
                + " "
                + self._normalize_text(str(source.get("snippet") or ""))
                for source in sources
                if isinstance(source, dict)
            ]
        )

        ranked: List[Dict[str, Any]] = []
        seen: set[str] = set()

        def register(candidate: str, *, forced_category: Optional[str] = None) -> None:
            risk_text = self._normalize_text(candidate).rstrip(".")
            if not risk_text:
                return

            key = risk_text.lower()
            if key in seen:
                return

            category = forced_category or self._classify_risk_category(risk_text)
            if category == "Legal" and not wants_legal:
                return
            if category == "Operational" and not wants_operational:
                return

            score, severity = self._score_risk_item(risk_text=risk_text, category=category)
            supporting_sources = self._supporting_source_filenames_for_risk(
                risk_text=risk_text,
                sources=sources,
                max_items=3,
            )

            ranked.append(
                {
                    "risk": risk_text,
                    "category": category,
                    "score": score,
                    "severity": severity,
                    "sources": supporting_sources,
                }
            )
            seen.add(key)

        if wants_legal:
            for candidate in legal_candidates:
                register(candidate, forced_category="Legal")

        if wants_operational:
            for candidate in operational_candidates:
                register(candidate, forced_category="Operational")

        if wants_operational and not any(item.get("category") == "Operational" for item in ranked):
            for candidate in self._normalize_risk_items(reasoning_payload.get("main_issues") or [])[:4]:
                register(candidate, forced_category="Operational")

        if wants_operational and not any(item.get("category") == "Operational" for item in ranked):
            percentages = self._extract_percentages(combined_source_text, max_items=2)
            amounts = self._extract_currency_amounts(combined_source_text, max_items=2)

            if percentages:
                register(
                    "SLA performance volatility remains unresolved ("
                    + ", ".join(percentages)
                    + "), creating service-continuity and escalation risk",
                    forced_category="Operational",
                )
            else:
                register(
                    "SLA performance stabilization remains unresolved, creating service-continuity and escalation risk",
                    forced_category="Operational",
                )

            if amounts:
                register(
                    "Invoice operations remain unstable while disputed amounts ("
                    + ", ".join(amounts)
                    + ") are unresolved",
                    forced_category="Operational",
                )
            else:
                register(
                    "Invoice reconciliation remains unresolved, creating financial and operational execution risk",
                    forced_category="Operational",
                )

        if wants_legal and not any(item.get("category") == "Legal" for item in ranked):
            register(
                "Evidentiary sufficiency remains uncertain for proving contractual breach and recoverable damages",
                forced_category="Legal",
            )

        ranked.sort(
            key=lambda item: (
                -int(item.get("score") or 0),
                0 if str(item.get("category") or "") == "Legal" else 1,
                str(item.get("risk") or "").lower(),
            )
        )
        return ranked

    @staticmethod
    def _format_ranked_case_risks_answer(
        *,
        case_id: int,
        ranked_entries: List[Dict[str, Any]],
        target_count: int,
        wants_legal: bool,
        wants_operational: bool,
    ) -> str:
        header = f"Detected legal risks for case {case_id} (ranked high to low):"
        if wants_operational and not wants_legal:
            header = f"Detected legal risks for case {case_id} (operational signals, ranked high to low):"
        elif wants_legal and wants_operational:
            header = f"Detected legal risks for case {case_id} (including operational signals, ranked high to low):"

        lines = [header, ""]
        for index, item in enumerate(ranked_entries[:target_count], start=1):
            source_values = item.get("sources") or []
            source_text = ", ".join(source_values[:3]) if source_values else "Case evidence synthesis"
            lines.append(
                f"{index}. {item['severity']} | {item['category']} | {item['risk']} | Sources: {source_text}"
            )

        if len(lines) == 2:
            lines.append("No high-confidence risk signals were extracted from current evidence.")

        return "\n".join(lines).strip()
