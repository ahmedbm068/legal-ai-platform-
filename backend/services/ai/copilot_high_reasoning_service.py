"""CopilotHighReasoningMixin

Extracted from copilot_service.py (R4a refactor).

Contains the 9-method high-reasoning multi-candidate cluster:
  _coerce_unit_score
  _parse_high_reasoning_allowlist
  _stable_rollout_bucket
  _is_high_reasoning_rollout_eligible
  _extract_json_object
  _build_high_reasoning_evidence_block
  _generate_high_reasoning_candidate
  _judge_high_reasoning_candidates
  _finalize_reasoning_payload

Design note: implemented as a mixin (not a standalone service) so that
patch.object(copilot_service_instance, "_generate_high_reasoning_candidate")
in the test suite still intercepts calls made inside _finalize_reasoning_payload.
A delegation-based design would break those tests because patches on the facade
shim would not propagate into the service's own self references.
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
import time
from typing import Any, Dict

from backend.core.config import settings
from backend.services.ai.llm_gateway import llm_gateway

logger = logging.getLogger(__name__)


class CopilotHighReasoningMixin:
    """Mixin providing the high-reasoning multi-candidate pipeline.

    Consumed by CopilotService.  All methods access self.client, self.model,
    self.HIGH_REASONING_STYLES, self.HIGH_REASONING_ELIGIBLE_INTENTS, and
    self._normalize_reasoning_level() which are defined on CopilotService.
    """

    # ── Score helpers ─────────────────────────────────────────────────────────

    @staticmethod
    def _coerce_unit_score(value: Any) -> float:
        try:
            parsed = float(value)
        except (TypeError, ValueError):
            return 0.0
        if parsed > 1.0:
            parsed = parsed / 100.0
        return max(0.0, min(parsed, 1.0))

    # ── Rollout helpers ───────────────────────────────────────────────────────

    @staticmethod
    def _parse_high_reasoning_allowlist(raw_allowlist: str | None) -> set[int]:
        if not raw_allowlist:
            return set()
        values: set[int] = set()
        for token in str(raw_allowlist).replace(";", ",").split(","):
            normalized = token.strip()
            if not normalized:
                continue
            if normalized.isdigit():
                values.add(int(normalized))
        return values

    @staticmethod
    def _stable_rollout_bucket(*, tenant_id: int, salt: str) -> int:
        digest = hashlib.sha256(f"{salt}:{tenant_id}".encode("utf-8")).hexdigest()
        return int(digest[:8], 16) % 100

    def _is_high_reasoning_rollout_eligible(self, *, tenant_id: int | None) -> tuple[bool, str, int | None]:
        allowlist = self._parse_high_reasoning_allowlist(settings.HIGH_REASONING_TENANT_ALLOWLIST)
        rollout_percentage = int(settings.HIGH_REASONING_ROLLOUT_PERCENTAGE or 0)
        rollout_percentage = max(0, min(rollout_percentage, 100))

        if tenant_id is None:
            if rollout_percentage >= 100 and not allowlist:
                return True, "global_full_rollout", None
            return False, "tenant_id_missing", None

        if tenant_id in allowlist:
            return True, "allowlist", None

        if rollout_percentage <= 0:
            return False, "rollout_percentage_zero", None
        if rollout_percentage >= 100:
            return True, "rollout_percentage_full", None

        salt = str(settings.HIGH_REASONING_ROLLOUT_SALT or "legal-ai-high-reasoning-v1").strip() or "legal-ai-high-reasoning-v1"
        bucket = self._stable_rollout_bucket(tenant_id=tenant_id, salt=salt)
        return bucket < rollout_percentage, "rollout_percentage", bucket

    # ── JSON extraction ───────────────────────────────────────────────────────

    @staticmethod
    def _extract_json_object(text: str) -> dict[str, Any]:
        raw = str(text or "").strip()
        if not raw:
            return {}
        cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw, flags=re.IGNORECASE | re.DOTALL).strip()
        try:
            payload = json.loads(cleaned)
            return payload if isinstance(payload, dict) else {}
        except json.JSONDecodeError:
            match = re.search(r"\{.*\}", cleaned, re.DOTALL)
            if not match:
                return {}
            try:
                payload = json.loads(match.group(0))
                return payload if isinstance(payload, dict) else {}
            except json.JSONDecodeError:
                return {}

    # ── Evidence block builder ────────────────────────────────────────────────

    @staticmethod
    def _build_high_reasoning_evidence_block(
        *,
        sources: list[dict[str, Any]],
        citations: list[dict[str, Any]],
    ) -> str:
        lines: list[str] = []
        for citation in citations[:10]:
            label = str(citation.get("label") or "Source").strip()
            snippet = str(citation.get("snippet") or "").strip()
            if label and snippet:
                lines.append(f"- [{label}] {snippet[:260]}")

        if not lines:
            for source in sources[:10]:
                filename = str(source.get("filename") or "Source").strip()
                chunk_index = source.get("chunk_index")
                snippet = str(source.get("snippet") or source.get("chunk_text") or "").strip()
                label = f"{filename} - chunk {chunk_index}" if chunk_index is not None else filename
                if snippet:
                    lines.append(f"- [{label}] {snippet[:260]}")

        return "\n".join(lines)

    # ── LLM candidate generation ──────────────────────────────────────────────

    def _generate_high_reasoning_candidate(
        self,
        *,
        question: str,
        base_answer: str,
        style_name: str,
        style_instruction: str,
        evidence_block: str,
        timeout_seconds: float,
    ) -> str:
        if not self.client:
            return ""

        prompt = f"""
You are a legal AI assistant generating one grounded candidate answer.

Style profile: {style_name}
Style instruction: {style_instruction}

Rules:
1) Use only evidence listed below.
2) Do not invent facts.
3) If evidence is missing, say so explicitly.
4) Keep legal precision and practical usefulness.
5) Include citation labels inline where relevant, e.g. [filename - chunk X].

Question:
{question}

Existing grounded baseline answer:
{base_answer}

Evidence:
{evidence_block}
""".strip()

        response = self.client.responses.create(
            model=self.model,
            input=prompt,
            timeout=max(1.0, timeout_seconds),
        )
        return llm_gateway.extract_output_text(response).strip()

    # ── LLM judge ────────────────────────────────────────────────────────────

    def _judge_high_reasoning_candidates(
        self,
        *,
        question: str,
        candidates: list[dict[str, Any]],
        evidence_block: str,
        timeout_seconds: float,
    ) -> dict[str, Any]:
        if not self.client:
            return {}

        candidates_block = "\n\n".join(
            f"Candidate {item['index']} ({item['style']}):\n{item['answer']}"
            for item in candidates
        )
        judge_prompt = f"""
You are a legal quality judge. Score each candidate against this rubric from 0 to 1:
- grounding_score
- citation_score
- factual_consistency_score
- legal_usefulness_score
- actionability_score
- clarity_score

Critical ranking rule:
Grounding, factual consistency, and citation quality must dominate fluency/style.

Compute overall_score with priority weighting:
overall_score =
  0.30*grounding_score +
  0.25*factual_consistency_score +
  0.20*citation_score +
  0.10*legal_usefulness_score +
  0.10*actionability_score +
  0.05*clarity_score

Question:
{question}

Evidence:
{evidence_block}

Candidates:
{candidates_block}

Return JSON only with this schema:
{{
  "winner_index": 0,
  "decision_reason": "...",
  "scores": [
    {{
      "index": 0,
      "grounding_score": 0.0,
      "citation_score": 0.0,
      "factual_consistency_score": 0.0,
      "legal_usefulness_score": 0.0,
      "actionability_score": 0.0,
      "clarity_score": 0.0,
      "overall_score": 0.0,
      "decision_reason": "..."
    }}
  ]
}}
""".strip()

        response = self.client.responses.create(
            model=self.model,
            input=judge_prompt,
            timeout=max(1.0, timeout_seconds),
        )
        return self._extract_json_object(llm_gateway.extract_output_text(response))

    # ── Main entry point ──────────────────────────────────────────────────────

    def _finalize_reasoning_payload(
        self,
        *,
        payload: Dict[str, Any],
        reasoning_level: str,
        intent: str | None,
        question: str,
        tenant_id: int | None = None,
    ) -> Dict[str, Any]:
        normalized_level = self._normalize_reasoning_level(reasoning_level)
        if normalized_level != "high":
            return payload

        fallback_payload = dict(payload)
        if not settings.ENABLE_HIGH_REASONING_MULTI_ANSWER:
            fallback_payload["reasoning_result"] = {
                "reasoning_level": "high",
                "activated": False,
                "winner_reason": "high_reasoning_disabled",
                "candidates": [],
            }
            return fallback_payload

        rollout_eligible, rollout_reason, rollout_bucket = self._is_high_reasoning_rollout_eligible(tenant_id=tenant_id)
        if not rollout_eligible:
            fallback_payload["reasoning_result"] = {
                "reasoning_level": "high",
                "activated": False,
                "winner_reason": "high_reasoning_rollout_denied",
                "rollout_reason": rollout_reason,
                "rollout_bucket": rollout_bucket,
                "candidates": [],
            }
            return fallback_payload

        if str(intent or "") not in self.HIGH_REASONING_ELIGIBLE_INTENTS:
            fallback_payload["reasoning_result"] = {
                "reasoning_level": "high",
                "activated": False,
                "winner_reason": "intent_not_eligible",
                "candidates": [],
            }
            return fallback_payload

        start = time.perf_counter()
        timeout_ms = max(1000, int(settings.HIGH_REASONING_TIMEOUT_MS or 12000))
        max_candidates = max(2, min(int(settings.HIGH_REASONING_MAX_CANDIDATES or 3), 3))
        sources = payload.get("sources") if isinstance(payload.get("sources"), list) else []
        citations = payload.get("citations") if isinstance(payload.get("citations"), list) else []
        evidence_block = self._build_high_reasoning_evidence_block(sources=sources, citations=citations)
        base_answer = str(payload.get("answer") or "").strip()

        if not base_answer or not evidence_block or not self.client:
            fallback_payload["reasoning_result"] = {
                "reasoning_level": "high",
                "activated": False,
                "winner_reason": "insufficient_evidence_or_provider",
                "candidates": [],
            }
            return fallback_payload

        try:
            candidates: list[dict[str, Any]] = []
            for index, (style_name, style_instruction) in enumerate(self.HIGH_REASONING_STYLES[:max_candidates]):
                elapsed_ms = int((time.perf_counter() - start) * 1000)
                remaining_ms = timeout_ms - elapsed_ms
                if remaining_ms <= 350:
                    raise TimeoutError("high_reasoning_timeout")

                candidate_answer = self._generate_high_reasoning_candidate(
                    question=question,
                    base_answer=base_answer,
                    style_name=style_name,
                    style_instruction=style_instruction,
                    evidence_block=evidence_block,
                    timeout_seconds=remaining_ms / 1000.0,
                )
                if not candidate_answer:
                    raise RuntimeError("high_reasoning_candidate_empty")

                candidates.append(
                    {
                        "index": index,
                        "style": style_name,
                        "answer": candidate_answer,
                    }
                )

            elapsed_ms = int((time.perf_counter() - start) * 1000)
            remaining_ms = timeout_ms - elapsed_ms
            if remaining_ms <= 350:
                raise TimeoutError("high_reasoning_timeout")

            judge_payload = self._judge_high_reasoning_candidates(
                question=question,
                candidates=candidates,
                evidence_block=evidence_block,
                timeout_seconds=remaining_ms / 1000.0,
            )

            score_by_index: dict[int, dict[str, Any]] = {}
            for item in (judge_payload.get("scores") if isinstance(judge_payload, dict) else []) or []:
                if not isinstance(item, dict):
                    continue
                try:
                    idx = int(item.get("index"))
                except (TypeError, ValueError):
                    continue
                grounding = self._coerce_unit_score(item.get("grounding_score"))
                citation = self._coerce_unit_score(item.get("citation_score"))
                factual = self._coerce_unit_score(item.get("factual_consistency_score"))
                legal_usefulness = self._coerce_unit_score(item.get("legal_usefulness_score"))
                actionability = self._coerce_unit_score(item.get("actionability_score"))
                clarity = self._coerce_unit_score(item.get("clarity_score"))
                weighted_overall = (
                    0.30 * grounding
                    + 0.25 * factual
                    + 0.20 * citation
                    + 0.10 * legal_usefulness
                    + 0.10 * actionability
                    + 0.05 * clarity
                )
                score_by_index[idx] = {
                    "grounding_score": grounding,
                    "citation_score": citation,
                    "factual_consistency_score": factual,
                    "legal_usefulness_score": legal_usefulness,
                    "actionability_score": actionability,
                    "clarity_score": clarity,
                    "overall_score": max(
                        weighted_overall,
                        self._coerce_unit_score(item.get("overall_score")),
                    ),
                    "decision_reason": str(item.get("decision_reason") or "").strip(),
                }

            ranked_candidates: list[dict[str, Any]] = []
            for item in candidates:
                score = score_by_index.get(item["index"]) or {
                    "grounding_score": 0.0,
                    "citation_score": 0.0,
                    "factual_consistency_score": 0.0,
                    "legal_usefulness_score": 0.0,
                    "actionability_score": 0.0,
                    "clarity_score": 0.0,
                    "overall_score": 0.0,
                    "decision_reason": "Judge score unavailable.",
                }
                ranked_candidates.append(
                    {
                        "index": item["index"],
                        "style": item["style"],
                        "answer": item["answer"],
                        "score": score,
                    }
                )

            ranked_candidates.sort(key=lambda candidate: float(candidate["score"].get("overall_score", 0.0)), reverse=True)
            if not ranked_candidates:
                raise RuntimeError("high_reasoning_no_candidates")

            winner = ranked_candidates[0]
            second_best = ranked_candidates[1] if len(ranked_candidates) > 1 and settings.HIGH_REASONING_SHOW_TOP_2 else None
            winner_reason = str(judge_payload.get("decision_reason") or winner["score"].get("decision_reason") or "").strip()

            response_payload = dict(payload)
            response_payload["answer"] = winner["answer"]
            response_payload["reasoning_result"] = {
                "reasoning_level": "high",
                "activated": True,
                "winner_index": int(winner["index"]),
                "second_best_index": int(second_best["index"]) if second_best else None,
                "winner_reason": winner_reason,
                "candidates": [
                    {
                        "rank": rank,
                        "style": candidate["style"],
                        "answer": candidate["answer"],
                        "score": candidate["score"],
                    }
                    for rank, candidate in enumerate(ranked_candidates, start=1)
                ],
            }

            if settings.HIGH_REASONING_LOG_SCORES:
                logger.info(
                    "high_reasoning_success intent=%s winner=%s second=%s latency_ms=%s scores=%s",
                    intent,
                    winner["index"],
                    second_best["index"] if second_best else None,
                    int((time.perf_counter() - start) * 1000),
                    [round(float(candidate["score"].get("overall_score", 0.0)), 4) for candidate in ranked_candidates],
                )

            return response_payload
        except Exception as exc:
            degraded = dict(payload)
            degraded["used_fallback"] = True
            degraded["fallback_reason"] = "high_reasoning_timeout_or_error"
            degraded["reasoning_result"] = {
                "reasoning_level": "high",
                "activated": False,
                "winner_reason": f"high_reasoning_failed: {exc}",
                "candidates": [],
            }
            if settings.HIGH_REASONING_LOG_SCORES:
                logger.warning("high_reasoning_fallback intent=%s reason=%s", intent, exc)
            return degraded
