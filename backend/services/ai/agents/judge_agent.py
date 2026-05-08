"""Judge agent for the dual-answer deep-reasoning mode.

Receives two candidate answers (A = primary IRAC framing, low temperature;
B = steelman-the-counter-position, higher temperature) plus the retrieved
sources and the original query. Returns a structured verdict:

* ``chosen_candidate`` ∈ {"A", "B", "merge"}
* per-criterion scores in ``[0.0, 1.0]``
* a 1–3 sentence textual ``reasoning``
* the ``final_answer`` text (== chosen candidate, or a merge if "merge")

The judge is intentionally deterministic (``temperature=0.0``) and is given
an explicit rubric. If the LLM cannot produce a valid JSON verdict the
agent falls back to a heuristic that picks the longer candidate, so the
caller always receives a usable answer.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

from backend.services.ai.llm_gateway import llm_gateway


logger = logging.getLogger(__name__)


JUDGE_SCORE_KEYS = (
    "factual_grounding",
    "citation_faithfulness",
    "completeness",
    "legal_precision",
    "language_compliance",
    "refusal_correctness",
)


JUDGE_SYSTEM_PROMPT = """You are an impartial Senior Legal Reviewer judging two candidate answers to the SAME legal question.

Score each candidate on the following criteria (0.0 weakest, 1.0 strongest):
- factual_grounding: are the factual claims supported by the supplied SOURCES?
- citation_faithfulness: do the [cite:doc:N] markers point to sources that actually support the surrounding text?
- completeness: does the answer address every aspect of the question?
- legal_precision: are statute references, terms of art, and legal reasoning correct?
- language_compliance: does the answer use the requested output language consistently?
- refusal_correctness: if the answer refuses or partially refuses, is the refusal justified by the sources (or unjustified, lowering the score)?

Then choose one of: "A", "B", or "merge".
- "A" or "B" — that candidate is clearly better as-is.
- "merge" — neither dominates; combine the best parts. ONLY pick "merge" if neither candidate's overall score is above 0.75 AND the candidates are non-trivially different.

Output STRICT JSON with exactly these keys and no extra text:
{
  "chosen_candidate": "A" | "B" | "merge",
  "scores_a": { "factual_grounding": 0.0, "citation_faithfulness": 0.0, "completeness": 0.0, "legal_precision": 0.0, "language_compliance": 0.0, "refusal_correctness": 0.0 },
  "scores_b": { ... same keys ... },
  "reasoning": "1-3 sentence explanation",
  "merge_answer": "if chosen_candidate is 'merge', the merged answer text; else empty string"
}
"""


@dataclass
class JudgeVerdict:
    chosen_candidate: str  # "A" | "B" | "merge"
    final_answer: str
    reasoning: str
    scores_a: dict[str, float] = field(default_factory=dict)
    scores_b: dict[str, float] = field(default_factory=dict)
    used_fallback: bool = False
    fallback_reason: str | None = None

    @property
    def overall_a(self) -> float:
        return _mean(self.scores_a.values())

    @property
    def overall_b(self) -> float:
        return _mean(self.scores_b.values())

    def to_dict(self) -> dict[str, Any]:
        return {
            "chosen": self.chosen_candidate,
            "reasoning": self.reasoning,
            "scores": {
                "A": {k: round(float(v), 4) for k, v in self.scores_a.items()},
                "B": {k: round(float(v), 4) for k, v in self.scores_b.items()},
                "overall_a": round(self.overall_a, 4),
                "overall_b": round(self.overall_b, 4),
            },
            "used_fallback": self.used_fallback,
            "fallback_reason": self.fallback_reason,
        }


class JudgeAgent:
    agent_name = "judge_agent"

    def judge(
        self,
        *,
        query: str,
        candidate_a: str,
        candidate_b: str,
        sources: Sequence[Mapping[str, Any] | str] | None = None,
        output_language: str | None = None,
    ) -> JudgeVerdict:
        clean_a = (candidate_a or "").strip()
        clean_b = (candidate_b or "").strip()
        if not clean_a and not clean_b:
            return JudgeVerdict(
                chosen_candidate="A",
                final_answer="",
                reasoning="Both candidates empty.",
                used_fallback=True,
                fallback_reason="empty_candidates",
            )
        if not clean_a:
            return JudgeVerdict(
                chosen_candidate="B",
                final_answer=clean_b,
                reasoning="Candidate A empty; defaulted to B.",
                used_fallback=True,
                fallback_reason="empty_a",
            )
        if not clean_b:
            return JudgeVerdict(
                chosen_candidate="A",
                final_answer=clean_a,
                reasoning="Candidate B empty; defaulted to A.",
                used_fallback=True,
                fallback_reason="empty_b",
            )

        client = llm_gateway.create_client()
        if client is None:
            return self._heuristic_fallback(
                clean_a, clean_b, reason="llm_gateway_unavailable"
            )

        user_payload = _build_user_payload(
            query=query,
            candidate_a=clean_a,
            candidate_b=clean_b,
            sources=sources or [],
            output_language=output_language,
        )

        try:
            completion = client.chat.completions.create(
                model=llm_gateway.resolve_model("text") or llm_gateway.default_model,
                messages=[
                    {"role": "system", "content": JUDGE_SYSTEM_PROMPT},
                    {"role": "user", "content": user_payload},
                ],
                temperature=0.0,
                max_tokens=1200,
            )
            raw = llm_gateway.extract_output_text(completion).strip()
        except Exception as exc:  # noqa: BLE001
            logger.warning("judge_llm_call_failed err=%s", exc, exc_info=True)
            return self._heuristic_fallback(clean_a, clean_b, reason="llm_call_failed")

        parsed = _parse_judge_json(raw)
        if parsed is None:
            return self._heuristic_fallback(clean_a, clean_b, reason="invalid_judge_json")

        chosen = str(parsed.get("chosen_candidate") or "A").strip().upper()
        if chosen not in {"A", "B", "MERGE"}:
            chosen = "A"
        chosen = chosen.lower() if chosen == "MERGE" else chosen  # "merge" lowercase
        if chosen == "MERGE":
            chosen = "merge"

        scores_a = _coerce_scores(parsed.get("scores_a"))
        scores_b = _coerce_scores(parsed.get("scores_b"))
        reasoning = str(parsed.get("reasoning") or "").strip() or "(no reasoning provided)"

        if chosen == "merge":
            final = str(parsed.get("merge_answer") or "").strip()
            if not final:
                # Judge said merge but did not supply a merged answer — fall back
                # to the higher-scoring candidate.
                final = clean_a if _mean(scores_a.values()) >= _mean(scores_b.values()) else clean_b
                chosen = "A" if final is clean_a else "B"
        elif chosen == "A":
            final = clean_a
        else:
            final = clean_b

        return JudgeVerdict(
            chosen_candidate=chosen,
            final_answer=final,
            reasoning=reasoning,
            scores_a=scores_a,
            scores_b=scores_b,
        )

    def _heuristic_fallback(self, a: str, b: str, *, reason: str) -> JudgeVerdict:
        # Without an LLM, prefer the longer / more detailed candidate as a
        # rough proxy for completeness. Document the fallback explicitly.
        chosen = "A" if len(a) >= len(b) else "B"
        return JudgeVerdict(
            chosen_candidate=chosen,
            final_answer=a if chosen == "A" else b,
            reasoning=f"Heuristic fallback ({reason}); picked {chosen} by length.",
            used_fallback=True,
            fallback_reason=reason,
        )


# ──────────────────────────────────────────────────────────────────────────
# Pure helpers
# ──────────────────────────────────────────────────────────────────────────


def _build_user_payload(
    *,
    query: str,
    candidate_a: str,
    candidate_b: str,
    sources: Sequence[Mapping[str, Any] | str],
    output_language: str | None,
) -> str:
    source_blocks: list[str] = []
    for i, src in enumerate(sources):
        if isinstance(src, Mapping):
            text = (
                src.get("snippet")
                or src.get("chunk_text")
                or src.get("text")
                or ""
            )
        elif isinstance(src, str):
            text = src
        else:
            text = ""
        text = str(text).strip()
        if not text:
            continue
        if len(text) > 600:
            text = text[:600] + "…"
        source_blocks.append(f"[doc:{i}] {text}")

    source_section = "\n\n".join(source_blocks) if source_blocks else "(no sources retrieved)"
    lang_line = (
        f"\nRequested output language: {output_language}" if output_language else ""
    )
    return (
        f"QUESTION:\n{query}\n{lang_line}\n\n"
        f"SOURCES:\n{source_section}\n\n"
        f"CANDIDATE A (primary IRAC, conservative):\n{candidate_a}\n\n"
        f"CANDIDATE B (steelman, exploratory):\n{candidate_b}\n\n"
        "Return STRICT JSON per the system instructions."
    )


_JSON_FENCE_RE = re.compile(r"```(?:json)?\s*(\{[\s\S]*\})\s*```", re.IGNORECASE)


def _parse_judge_json(text: str) -> dict[str, Any] | None:
    if not text:
        return None
    candidates: list[str] = []
    fenced = _JSON_FENCE_RE.search(text)
    if fenced:
        candidates.append(fenced.group(1))
    candidates.append(text)
    # First-brace-to-last-brace fallback for models that prepend prose.
    first = text.find("{")
    last = text.rfind("}")
    if 0 <= first < last:
        candidates.append(text[first : last + 1])
    for c in candidates:
        try:
            obj = json.loads(c)
        except (json.JSONDecodeError, TypeError, ValueError):
            continue
        if isinstance(obj, dict):
            return obj
    return None


def _coerce_scores(raw: Any) -> dict[str, float]:
    out: dict[str, float] = {}
    if not isinstance(raw, Mapping):
        return out
    for key in JUDGE_SCORE_KEYS:
        v = raw.get(key)
        try:
            f = float(v)
        except (TypeError, ValueError):
            f = 0.0
        out[key] = max(0.0, min(1.0, f))
    return out


def _mean(values: Any) -> float:
    vals = list(values)
    if not vals:
        return 0.0
    return sum(float(v) for v in vals) / len(vals)


judge_agent = JudgeAgent()


__all__ = [
    "JUDGE_SCORE_KEYS",
    "JudgeVerdict",
    "JudgeAgent",
    "judge_agent",
]
