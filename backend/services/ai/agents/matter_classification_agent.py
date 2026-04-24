from __future__ import annotations

import re
from typing import Any

from backend.services.ai.agents.base_agent import BaseAgent, AgentResult


class MatterClassificationAgent(BaseAgent):
    agent_name = "matter_classification_agent"

    MATTER_MARKERS: dict[str, tuple[str, ...]] = {
        "civil obligation": (
            "civil obligation",
            "obligation",
            "contract",
            "breach",
            "liability",
            "payment terms",
            "notice clause",
            "damages",
        ),
        "succession": (
            "succession",
            "inheritance",
            "heritage",
            "heir",
            "testament",
            "estate",
            "statut personnel",
        ),
        "international private law": (
            "international private law",
            "droit international prive",
            "international prive",
            "conflit de lois",
            "conflict of laws",
            "exequatur",
            "foreign judgment",
            "cross-border",
        ),
        "document review": (
            "document review",
            "review document",
            "compare documents",
            "clause extraction",
            "scan clauses",
        ),
        "litigation position memo": (
            "litigation position",
            "position memo",
            "pleading",
            "argument map",
            "contentious",
        ),
        "article applicability review": (
            "article applicability",
            "which article applies",
            "applicable article",
            "article review",
        ),
    }

    TASK_MARKERS: dict[str, tuple[str, ...]] = {
        "drafting": (
            "draft",
            "prepare memo",
            "write memo",
            "write email",
            "prepare email",
            "redline",
            "rewrite",
        ),
        "research": (
            "find sources",
            "research",
            "retrieve",
            "search",
            "which article",
            "locate article",
            "jurisprudence",
        ),
        "explanation": (
            "explain",
            "client explanation",
            "plain language",
            "simplify",
            "explain to client",
            "client-ready",
        ),
    }

    PROCEDURAL_MARKERS = (
        "deadline",
        "filing",
        "jurisdiction",
        "competence",
        "admissibility",
        "appeal",
        "service of process",
        "exequatur",
        "procedure",
    )
    SUBSTANTIVE_MARKERS = (
        "obligation",
        "liability",
        "inheritance",
        "succession",
        "rights",
        "breach",
        "damages",
        "ownership",
        "testament",
    )
    URGENCY_MARKERS = (
        "urgent",
        "asap",
        "immediately",
        "today",
        "tomorrow",
        "deadline",
        "expires",
        "time-sensitive",
    )
    CRITICAL_URGENCY_MARKERS = (
        "court hearing",
        "hearing today",
        "injunction",
        "seizure",
        "freeze order",
        "execution imminent",
    )
    HIGH_SENSITIVITY_MARKERS = (
        "confidential",
        "privileged",
        "minor",
        "child",
        "family dispute",
        "estate",
        "sensitive",
        "reputation",
    )

    SUBTOPIC_HINTS: dict[str, tuple[str, ...]] = {
        "contractual breach and obligations": (
            "contract",
            "breach",
            "payment",
            "notice",
            "damages",
        ),
        "succession shares and testament scope": (
            "succession",
            "inheritance",
            "testament",
            "heir",
            "estate",
        ),
        "cross-border conflict of laws and recognition": (
            "international private law",
            "conflit de lois",
            "exequatur",
            "foreign judgment",
            "cross-border",
        ),
        "document consistency and clause analysis": (
            "document review",
            "compare documents",
            "clause",
            "extract",
        ),
        "litigation theory and position framing": (
            "litigation",
            "position memo",
            "pleading",
            "argument",
        ),
        "article applicability to factual pattern": (
            "article applicability",
            "which article applies",
            "applicable article",
            "article review",
        ),
    }

    def classify_matter(
        self,
        *,
        user_prompt: str,
        case_context: dict[str, Any] | None,
        available_document_summaries: list[str] | None,
    ) -> AgentResult:
        prompt = str(user_prompt or "").strip()
        if not prompt:
            return self.result(
                success=False,
                error="User prompt is empty; classification cannot run.",
                trace=["Classification failed: user prompt was empty."],
            )

        context = case_context if isinstance(case_context, dict) else {}
        summaries = [str(item or "").strip() for item in (available_document_summaries or []) if str(item or "").strip()]

        combined_text = self._build_combined_text(prompt=prompt, case_context=context, summaries=summaries)
        matter_type, matter_scores = self._classify_matter_type(combined_text=combined_text)
        task_type = self._classify_task_type(combined_text=combined_text)
        legal_dimension = self._classify_legal_dimension(combined_text=combined_text)
        likely_code_family = self._likely_code_family(matter_type=matter_type)
        urgency_sensitivity = self._classify_urgency_sensitivity(combined_text=combined_text)
        subtopic = self._infer_subtopic(combined_text=combined_text, matter_type=matter_type)
        confidence = self._estimate_confidence(matter_scores=matter_scores, matter_type=matter_type)

        ambiguity_note = ""
        if matter_type == "mixed private law matter":
            ambiguity_note = "Matter appears mixed or ambiguous; classification should be confirmed during legal review."

        trace = [
            "Classified legal matter before reasoning stage.",
            f"matter_type={matter_type}; task_type={task_type}; legal_dimension={legal_dimension}.",
        ]

        return self.result(
            success=True,
            payload={
                "matter_type": matter_type,
                "subtopic": subtopic,
                "likely_code_family": likely_code_family,
                "urgency_sensitivity": urgency_sensitivity,
                "task_type": task_type,
                "legal_dimension": legal_dimension,
                "confidence": confidence,
                "ambiguity_note": ambiguity_note,
            },
            warnings=[ambiguity_note] if ambiguity_note else [],
            trace=trace,
        )

    @staticmethod
    def _build_combined_text(*, prompt: str, case_context: dict[str, Any], summaries: list[str]) -> str:
        case_payload = case_context.get("case") if isinstance(case_context.get("case"), dict) else {}
        context_bits = [
            prompt,
            str(case_payload.get("title") or ""),
            str(case_payload.get("jurisdiction_country") or ""),
            " ".join(str(item or "") for item in (case_context.get("risk_signals") or [])),
            " ".join(summaries[:12]),
        ]
        merged = " ".join(part for part in context_bits if str(part).strip())
        return re.sub(r"\s+", " ", merged).strip().lower()

    def _classify_matter_type(self, *, combined_text: str) -> tuple[str, dict[str, int]]:
        scores: dict[str, int] = {}
        for matter, markers in self.MATTER_MARKERS.items():
            score = 0
            for marker in markers:
                if marker in combined_text:
                    score += 1
            scores[matter] = score

        private_law_hits = [
            scores.get("civil obligation", 0) > 0,
            scores.get("succession", 0) > 0,
            scores.get("international private law", 0) > 0,
        ]
        if sum(1 for hit in private_law_hits if hit) >= 2:
            return "mixed private law matter", scores

        ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)
        best_label, best_score = ranked[0]
        if best_score <= 0:
            return "mixed private law matter", scores
        return best_label, scores

    def _classify_task_type(self, *, combined_text: str) -> str:
        for task_type, markers in self.TASK_MARKERS.items():
            if any(marker in combined_text for marker in markers):
                return task_type
        return "analysis"

    def _classify_legal_dimension(self, *, combined_text: str) -> str:
        procedural_hits = sum(1 for marker in self.PROCEDURAL_MARKERS if marker in combined_text)
        substantive_hits = sum(1 for marker in self.SUBSTANTIVE_MARKERS if marker in combined_text)
        if procedural_hits > 0 and substantive_hits > 0:
            return "mixed"
        if procedural_hits > 0:
            return "procedural"
        return "substantive"

    @staticmethod
    def _likely_code_family(*, matter_type: str) -> str:
        mapping = {
            "civil obligation": "code_civil",
            "succession": "code_succession",
            "international private law": "code_international_prive",
            "mixed private law matter": "mixed_or_ambiguous",
            "document review": "context_dependent",
            "drafting": "context_dependent",
            "client explanation": "context_dependent",
            "litigation position memo": "context_dependent",
            "article applicability review": "context_dependent",
        }
        return mapping.get(matter_type, "mixed_or_ambiguous")

    def _classify_urgency_sensitivity(self, *, combined_text: str) -> dict[str, str]:
        urgency = "normal"
        if any(marker in combined_text for marker in self.CRITICAL_URGENCY_MARKERS):
            urgency = "critical"
        elif any(marker in combined_text for marker in self.URGENCY_MARKERS):
            urgency = "high"

        sensitivity = "standard"
        if any(marker in combined_text for marker in self.HIGH_SENSITIVITY_MARKERS):
            sensitivity = "high"

        return {
            "urgency": urgency,
            "sensitivity": sensitivity,
        }

    def _infer_subtopic(self, *, combined_text: str, matter_type: str) -> str:
        for subtopic, markers in self.SUBTOPIC_HINTS.items():
            if any(marker in combined_text for marker in markers):
                return subtopic

        fallback = {
            "civil obligation": "general civil obligation analysis",
            "succession": "general succession entitlement analysis",
            "international private law": "general conflict-of-laws analysis",
            "mixed private law matter": "mixed private law classification pending clarification",
            "document review": "general document review",
            "litigation position memo": "litigation position framing",
            "article applicability review": "article applicability assessment",
        }
        return fallback.get(matter_type, "legal matter classification requires additional context")

    @staticmethod
    def _estimate_confidence(*, matter_scores: dict[str, int], matter_type: str) -> str:
        if matter_type == "mixed private law matter":
            return "low"

        ranked = sorted(matter_scores.values(), reverse=True)
        best = ranked[0] if ranked else 0
        second = ranked[1] if len(ranked) > 1 else 0
        if best >= 3 and best >= second + 2:
            return "high"
        if best >= 1:
            return "medium"
        return "low"


matter_classification_agent = MatterClassificationAgent()
