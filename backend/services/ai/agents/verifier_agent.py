from __future__ import annotations

import json
import re
from typing import Any

from backend.services.ai.agents.base_agent import BaseAgent, AgentResult
from backend.services.ai.llm_gateway import llm_gateway


WORD_REGEX = re.compile(r"\b\w+\b")


class VerifierAgent(BaseAgent):
    agent_name = "verifier_agent"

    def __init__(self) -> None:
        self.client = llm_gateway.create_client()
        self.model = llm_gateway.default_model

    def verify_answer(
        self,
        *,
        question: str,
        answer: str,
        sources: list[dict[str, Any]],
    ) -> AgentResult:
        normalized_question = (question or "").strip()
        normalized_answer = (answer or "").strip()

        if not normalized_answer:
            return self.result(
                success=False,
                error="Answer text is empty.",
                trace=["Input validation failed: answer text missing."],
            )

        trace = [
            "Starting verification pass.",
            f"Received {len(sources)} source item(s) for grounding check.",
        ]

        heuristic = self._heuristic_verification(
            question=normalized_question,
            answer=normalized_answer,
            sources=sources,
        )
        trace.append("Completed heuristic grounding checks.")

        if self.client and sources:
            llm_result = self._llm_verification(
                question=normalized_question,
                answer=normalized_answer,
                sources=sources,
            )
            if llm_result:
                heuristic.update(llm_result)
                trace.append("Enhanced verification result with LLM review.")
            else:
                trace.append("LLM verification unavailable; kept heuristic verification result.")
        else:
            trace.append("Skipped LLM verification because provider or sources were unavailable.")

        warnings = heuristic.get("issues") or []
        return self.result(
            success=bool(heuristic.get("is_verified")),
            payload=heuristic,
            warnings=warnings,
            error=None if heuristic.get("is_verified") else "Verification agent flagged the answer as weakly grounded.",
            trace=trace,
        )

    def _heuristic_verification(
        self,
        *,
        question: str,
        answer: str,
        sources: list[dict[str, Any]],
    ) -> dict[str, Any]:
        issues: list[str] = []
        snippets = [str(item.get("snippet") or "") for item in sources if item.get("snippet")]
        top_score = max((float(item.get("score", 0.0)) for item in sources), default=0.0)

        if not snippets:
            issues.append("No evidence snippets were available for verification.")

        answer_terms = self._keywords(answer)
        source_terms = set()
        for snippet in snippets:
            source_terms.update(self._keywords(snippet))

        overlap_ratio = (len(answer_terms & source_terms) / len(answer_terms)) if answer_terms else 0.0

        if top_score < 0.35:
            issues.append("Retrieved evidence scored too low for a strong grounded answer.")
        if overlap_ratio < 0.2 and snippets:
            issues.append("Answer wording overlaps weakly with the retrieved evidence.")
        if question:
            question_terms = self._keywords(question)
            if question_terms and len(question_terms & source_terms) == 0:
                issues.append("Evidence does not clearly match the user question.")

        is_verified = not issues
        if not is_verified and snippets:
            supported_excerpt = snippets[0][:240].strip()
            if len(snippets[0]) > 240:
                supported_excerpt += "..."
        else:
            supported_excerpt = answer

        return {
            "is_verified": is_verified,
            "issues": issues,
            "confidence": "high" if is_verified and top_score >= 0.6 else "medium" if snippets else "low",
            "supported_answer": supported_excerpt,
            "verification_method": "heuristic",
        }

    def _llm_verification(
        self,
        *,
        question: str,
        answer: str,
        sources: list[dict[str, Any]],
    ) -> dict[str, Any] | None:
        prompt = f"""
You are the Verifier Agent inside a legal AI platform.

Your only job is to judge whether the answer is adequately supported by the supplied evidence snippets.
Do not invent missing evidence. Be strict.

Return valid JSON only with this exact schema:
{{
  "is_verified": true,
  "confidence": "high",
  "issues": ["string"],
  "supported_answer": "string",
  "verification_method": "llm_verifier_agent"
}}

Rules:
- If the answer contains claims not clearly supported by the snippets, set "is_verified" to false.
- Keep "supported_answer" short and grounded in the snippets.
- "issues" should list the exact grounding problems, if any.

Question:
{question}

Answer:
{answer}

Evidence snippets:
{json.dumps(sources, ensure_ascii=False, indent=2)}
"""

        try:
            response = self.client.responses.create(
                model=self.model,
                input=prompt,
            )
            raw_text = (response.output_text or "").strip()
            if not raw_text:
                return None

            payload = self._extract_json_payload(raw_text)
            if not payload:
                return None

            return {
                "is_verified": bool(payload.get("is_verified")),
                "confidence": str(payload.get("confidence") or "medium").strip(),
                "issues": self._normalize_string_list(payload.get("issues")),
                "supported_answer": str(payload.get("supported_answer") or answer).strip(),
                "verification_method": str(payload.get("verification_method") or "llm_verifier_agent").strip(),
            }
        except Exception:
            return None

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
    def _normalize_string_list(values: Any) -> list[str]:
        if not isinstance(values, list):
            return []
        return [str(value).strip() for value in values if str(value).strip()]

    @staticmethod
    def _keywords(text: str) -> set[str]:
        raw_terms = {term.lower() for term in WORD_REGEX.findall(text or "")}
        stopwords = {
            "the", "and", "for", "with", "that", "this", "from", "have", "has", "into",
            "case", "document", "chunk", "are", "was", "were", "been", "will", "would",
            "shall", "about", "there", "their", "them", "they", "your", "you", "only",
            "using", "used", "than", "then", "when", "what", "which", "where", "while",
            "also", "into", "under", "over", "more", "some", "such", "than", "just",
        }
        return {term for term in raw_terms if len(term) > 2 and term not in stopwords}


verifier_agent = VerifierAgent()
