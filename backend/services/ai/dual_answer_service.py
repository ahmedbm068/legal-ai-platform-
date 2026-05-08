"""Dual-answer deep-reasoning service.

Wraps the judge agent to provide a self-consistency / LLM-as-judge layer
on top of an already-grounded answer:

1. Takes ``Candidate A`` from the orchestrator (the standard answer,
   produced by the existing IRAC / grounded pipeline).
2. Generates ``Candidate B`` using a deliberately different prompt
   framing — *steelman the counter-position*, higher temperature — over
   the same retrieved sources, so disagreements are diagnostic.
3. Calls the judge agent (deterministic, ``temperature=0.0``) which
   scores both on a six-criterion rubric and picks the better answer
   (or merges).

This is the textbook self-consistency pattern (Wang et al. 2022) plus
LLM-as-judge (Zheng et al. 2023). On a labelled eval it lets you report
*A-alone accuracy*, *B-alone accuracy*, *judge-chosen accuracy*, and
*oracle accuracy* (always pick the better of A/B) — the four numbers
that prove a self-consistency layer is worth the extra LLM calls.

The service mutates the response dict in place, attaching:

* ``response['answer']`` — replaced with the judge's chosen final.
* ``response['judge']`` — judge verdict payload.
* ``response['candidates']`` — both candidates' text + persona.
* ``response['reasoning_mode']`` — set to ``"deep"`` for the trace.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Mapping, Sequence

from backend.services.ai.agents.judge_agent import judge_agent
from backend.services.ai.llm_gateway import llm_gateway


logger = logging.getLogger(__name__)


STEELMAN_SYSTEM_PROMPT = """You are a senior litigator preparing the OPPOSING-COUNSEL view of a legal question.

Your job is NOT to disagree for the sake of disagreeing. Your job is to:
- Read the same retrieved sources.
- Identify the strongest plausible alternative interpretation, edge case, or counter-argument the user should be aware of.
- If the alternative interpretation is weak, say so plainly — do not manufacture a disagreement.

Constraints:
- Cite the same retrieved sources using [cite:doc:N] markers when supporting a claim.
- Reply in the SAME language as the question.
- Use ~2/3 the length of a standard answer; this is a complement to the primary answer, not a replacement.
- If you reach the same conclusion as the standard analysis, state explicitly "Aligned with standard analysis" and explain why no meaningful counter-position exists.
"""


class DualAnswerService:
    """Generate a second candidate and run the judge agent."""

    async def enhance(
        self,
        *,
        query: str,
        candidate_a: str,
        sources: Sequence[Mapping[str, Any] | str],
        output_language: str | None = None,
    ) -> dict[str, Any]:
        """Async entry point — produces Candidate B in parallel-ready form
        and judges. Returns a payload ready to merge into the response dict.
        """

        candidate_b = await asyncio.to_thread(
            self._generate_steelman,
            query=query,
            sources=sources,
            output_language=output_language,
        )

        verdict = await asyncio.to_thread(
            judge_agent.judge,
            query=query,
            candidate_a=candidate_a,
            candidate_b=candidate_b,
            sources=sources,
            output_language=output_language,
        )

        return {
            "candidates": [
                {"id": "A", "persona": "primary", "text": candidate_a},
                {"id": "B", "persona": "steelman", "text": candidate_b},
            ],
            "judge": verdict.to_dict(),
            "final_answer": verdict.final_answer or candidate_a,
        }

    def enhance_sync(
        self,
        *,
        query: str,
        candidate_a: str,
        sources: Sequence[Mapping[str, Any] | str],
        output_language: str | None = None,
    ) -> dict[str, Any]:
        """Synchronous wrapper — runs the steelman + judge calls in parallel
        threads. Use this from a sync FastAPI handler."""

        async def _run() -> dict[str, Any]:
            return await self.enhance(
                query=query,
                candidate_a=candidate_a,
                sources=sources,
                output_language=output_language,
            )

        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # Called from inside an event loop (rare for sync FastAPI).
                # Schedule and wait via run_coroutine_threadsafe.
                future = asyncio.run_coroutine_threadsafe(_run(), loop)
                return future.result()
        except RuntimeError:
            pass
        return asyncio.run(_run())

    def apply_to_response(
        self,
        response: dict[str, Any],
        *,
        query: str,
        output_language: str | None = None,
    ) -> None:
        """Mutate ``response`` to enable deep-reasoning mode.

        No-op if ``response['answer']`` is empty or sources are missing —
        deep reasoning over no sources would amplify hallucinations rather
        than catch them.
        """

        candidate_a = str(response.get("answer") or "").strip()
        if not candidate_a:
            response["judge"] = {
                "skipped_reason": "empty_initial_answer",
            }
            return

        sources = response.get("sources") if isinstance(response.get("sources"), list) else []
        if not sources:
            response["judge"] = {
                "skipped_reason": "no_sources",
            }
            return

        try:
            payload = self.enhance_sync(
                query=query,
                candidate_a=candidate_a,
                sources=sources,
                output_language=output_language,
            )
        except Exception as exc:  # noqa: BLE001 — never break the user response
            logger.warning("dual_answer_enhancement_failed err=%s", exc, exc_info=True)
            response["judge"] = {"skipped_reason": "enhancement_error"}
            return

        response["candidates"] = payload["candidates"]
        response["judge"] = payload["judge"]
        response["reasoning_mode"] = "deep"
        # Replace top-level answer with the judge's choice. Mirror onto
        # ``message`` if it duplicates the answer (UI surfaces both).
        new_answer = str(payload["final_answer"] or candidate_a)
        if response.get("message") == candidate_a:
            response["message"] = new_answer
        response["answer"] = new_answer

    # ──────────────────────────────────────────────────────────────────────
    # Candidate B generator — "steelman the counter-position"
    # ──────────────────────────────────────────────────────────────────────

    def _generate_steelman(
        self,
        *,
        query: str,
        sources: Sequence[Mapping[str, Any] | str],
        output_language: str | None,
    ) -> str:
        client = llm_gateway.create_client()
        if client is None:
            return ""
        source_section = _format_sources(sources)
        lang_hint = (
            f"\nRespond in: {output_language}." if output_language and output_language != "auto" else ""
        )
        user_message = (
            f"QUESTION:\n{query}\n{lang_hint}\n\n"
            f"RETRIEVED SOURCES:\n{source_section}\n\n"
            "Provide the steelman counter-position per the system instructions."
        )
        try:
            completion = client.chat.completions.create(
                model=llm_gateway.resolve_model("text") or llm_gateway.default_model,
                messages=[
                    {"role": "system", "content": STEELMAN_SYSTEM_PROMPT},
                    {"role": "user", "content": user_message},
                ],
                temperature=0.7,
                max_tokens=900,
            )
            return llm_gateway.extract_output_text(completion).strip()
        except Exception as exc:  # noqa: BLE001
            logger.warning("steelman_generation_failed err=%s", exc, exc_info=True)
            return ""


def _format_sources(sources: Sequence[Mapping[str, Any] | str]) -> str:
    blocks: list[str] = []
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
            continue
        text = str(text).strip()
        if not text:
            continue
        if len(text) > 600:
            text = text[:600] + "…"
        blocks.append(f"[doc:{i}] {text}")
    return "\n\n".join(blocks) if blocks else "(no sources retrieved)"


dual_answer_service = DualAnswerService()


__all__ = [
    "DualAnswerService",
    "dual_answer_service",
]
