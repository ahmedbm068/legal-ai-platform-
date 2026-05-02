"""Copilot Retrieval Execution Service — Step 3B extraction.

Contains the RAG / retrieval execution pipeline that was previously embedded
inside CopilotService._answer_with_optional_external_research().

CopilotService._answer_with_optional_external_research() is now a thin
compatibility shim that delegates here, providing pre-resolved context and
callbacks for the complex logic that still lives in CopilotService
(material-breach case analysis, high-reasoning finalization).

Responsibilities:
    - ask_case / ask_document / ask_global RAG execution
    - Query optimization before retrieval
    - External research integration and answer synthesis
    - Source / citation normalization
    - Retrieval-specific fallback handling
    - Confidence and used_fallback propagation

NOT responsible for:
    - Drafting intents
    - Legal search mode (legal_search_mode_service)
    - Trust / verifier pipeline
    - High-reasoning finalization (delegated back via callback)
    - Material-breach case analysis (delegated back via callback)
"""
from __future__ import annotations

import json
import logging
import time
from typing import Any, Callable, Dict, List, Optional

from sqlalchemy.orm import Session

from backend.services.ai import copilot_service_constants as _consts
from backend.services.ai.agents.prompt_optimizer_agent import prompt_optimizer_agent
from backend.services.ai.external_research_service import external_research_service
from backend.services.ai.jurisdiction_context_service import jurisdiction_context_service
from backend.services.ai.llm_gateway import llm_gateway
from backend.services.ai.rag_service import RagService

_logger = logging.getLogger("copilot.retrieval")


class CopilotRetrievalExecutionService:
    """RAG / retrieval execution extracted from CopilotService (Step 3B).

    Instantiated once inside CopilotService.__init__() and stored as
    self.retrieval_execution_service.
    """

    def __init__(
        self,
        *,
        rag_service: RagService,
        client: Any,
        model: str,
    ) -> None:
        self.rag_service = rag_service
        self.client = client
        self.model = model

    # ──────────────────────────────────────────────────────────────────────────
    # Public entry point
    # ──────────────────────────────────────────────────────────────────────────

    def execute(
        self,
        *,
        db: Session,
        tenant_id: int,
        user_id: Optional[int] = None,
        question: str,
        top_k: int,
        case_id: Optional[int],
        document_id: Optional[int],
        use_external_research: bool,
        reasoning_level: str,
        intent: str | None,
        target_type: str | None,
        target_id: int | None,
        already_optimized: bool = False,
        # ── pre-resolved context (provided by CopilotService shim) ───────────
        jurisdiction_context: Dict[str, Any] | None = None,
        # ── prefetched graph context for grounded case fallback ───────────────
        case_context: Dict[str, Any] | None = None,
        case_snapshot: Dict[str, Any] | None = None,
        # ── callbacks for logic that still lives in CopilotService ───────────
        material_breach_handler: Callable[..., Dict[str, Any]] | None = None,
        finalize_reasoning_fn: Callable[..., Dict[str, Any]] | None = None,
    ) -> Dict[str, Any]:
        """Execute the RAG retrieval pipeline and return a normalised result dict.

        Behaviour is identical to the original
        CopilotService._answer_with_optional_external_research(), with added
        debug logging, safe type coercions, and a grounded case-context fallback
        for ask_case when the vector index returns zero results.

        Args:
            db: SQLAlchemy session.
            tenant_id: Tenant identifier.
            user_id: Optional user id (forwarded to RAG trust layer).
            question: User query (may already be optimized if already_optimized=True).
            top_k: Max retrieval results.
            case_id: Resolved case scope (or None for global).
            document_id: Resolved document scope (or None).
            use_external_research: Whether to augment with external web search.
            reasoning_level: One of "low" / "medium" / "high".
            intent: Parsed intent string (e.g. "ask_case").
            target_type: "case" | "document" | None.
            target_id: Numeric target identifier or None.
            already_optimized: Skip internal query optimisation if True.
            jurisdiction_context: Pre-resolved jurisdiction dict (from shim).
            case_context: Prefetched case-context from the graph orchestrator.
            case_snapshot: Persisted case snapshot from the graph orchestrator.
            material_breach_handler: Callable that runs the clause-ranking
                analysis.  When None the path is silently skipped.
            finalize_reasoning_fn: Callable that applies high-reasoning
                multi-answer selection.  When None the payload is returned as-is.
        """
        _t0 = time.monotonic()

        # ── Safe type coercions ───────────────────────────────────────────────
        # If the parsed command delivers case_id as a string (e.g. "29"), coerce
        # it to int so the RAG / DB filters work correctly.
        safe_case_id: Optional[int] = None
        if case_id is not None:
            try:
                safe_case_id = int(case_id)
            except (TypeError, ValueError):
                _logger.warning(
                    "[RETRIEVAL] case_id coercion failed | raw_value=%r — treating as None",
                    case_id,
                )
        safe_document_id: Optional[int] = None
        if document_id is not None:
            try:
                safe_document_id = int(document_id)
            except (TypeError, ValueError):
                _logger.warning(
                    "[RETRIEVAL] document_id coercion failed | raw_value=%r — treating as None",
                    document_id,
                )
        safe_top_k = max(1, int(top_k or 5))

        _logger.debug(
            "[RETRIEVAL] retrieval_execution_start | intent=%s case_id=%s document_id=%s "
            "top_k=%s use_external=%s already_optimized=%s",
            intent, safe_case_id, safe_document_id, safe_top_k,
            use_external_research, already_optimized,
        )

        normalized_question = str(question or "").strip()
        if not normalized_question:
            result: Dict[str, Any] = {
                "answer": "I could not find enough detail in the request to run retrieval.",
                "used_fallback": True,
                "fallback_reason": "empty_query",
                "confidence": "low",
                "scope": "global",
                "sources": [],
                "jurisdiction": jurisdiction_context,
            }
            _logger.debug(
                "[RETRIEVAL] retrieval_execution_end | path=empty_query "
                "used_fallback=True confidence=low duration_ms=%.1f",
                (time.monotonic() - _t0) * 1000,
            )
            return result

        jurisdiction_prompt_block = (
            jurisdiction_context_service.get_prompt_block(jurisdiction_context.get("country_code"))
            if jurisdiction_context
            else ""
        )

        # ── Material breach clause special path ───────────────────────────────
        if safe_case_id is not None and self._looks_like_material_breach_clause_question(normalized_question):
            if material_breach_handler is not None:
                result = material_breach_handler(
                    db=db,
                    tenant_id=tenant_id,
                    case_id=safe_case_id,
                    question=normalized_question,
                    jurisdiction_context=jurisdiction_context,
                )
                _logger.debug(
                    "[RETRIEVAL] retrieval_execution_end | path=material_breach "
                    "used_fallback=%s confidence=%s duration_ms=%.1f",
                    result.get("used_fallback"), result.get("confidence"),
                    (time.monotonic() - _t0) * 1000,
                )
                return result

        # ── Query optimisation ────────────────────────────────────────────────
        optimized_question = (
            normalized_question
            if already_optimized
            else self._optimize_prompt_for_query(
                question=normalized_question,
                intent=intent,
                target_type=target_type,
                target_id=safe_case_id or safe_document_id,
                allow_llm=False,
            )
        )
        # Guard: optimizer must not return empty or noise
        if not optimized_question or self._is_prompt_noise(optimized_question):
            _logger.debug(
                "[RETRIEVAL] optimizer returned empty/noise — reverting to normalized question",
            )
            optimized_question = normalized_question

        # ── Pre-RAG debug log ─────────────────────────────────────────────────
        _logger.debug(
            "[RETRIEVAL] rag_call_start | query_preview=%.80r case_id=%s document_id=%s "
            "top_k=%s intent=%s use_external=%s",
            optimized_question, safe_case_id, safe_document_id,
            safe_top_k, intent, use_external_research,
        )

        # ── Core RAG call ─────────────────────────────────────────────────────
        base_result = self.rag_service.answer_question(
            db=db,
            tenant_id=tenant_id,
            user_id=user_id,
            question=optimized_question,
            top_k=safe_top_k,
            case_id=safe_case_id,
            document_id=safe_document_id,
        )

        # ── Post-RAG debug log ────────────────────────────────────────────────
        raw_sources = base_result.get("sources") or []
        raw_citations = base_result.get("citations") or []
        _logger.debug(
            "[RETRIEVAL] rag_call_end | raw_sources_count=%s normalized_sources_count=%s "
            "answer_empty=%s used_fallback=%s confidence=%s fallback_reason=%r",
            len(raw_sources),
            len(raw_sources),
            not bool(str(base_result.get("answer") or "").strip()),
            base_result.get("used_fallback"),
            base_result.get("confidence"),
            base_result.get("fallback_reason"),
        )

        # ── Grounded case-context fallback ────────────────────────────────────
        # When the vector index returns zero sources for ask_case, attempt to
        # build a grounded answer from the graph-prefetched case_context /
        # case_snapshot so the user sees real case facts instead of a generic
        # "not enough evidence" message.  We never invent facts — only what the
        # context explicitly provides is used.
        if (
            intent == "ask_case"
            and safe_case_id is not None
            and not raw_sources
            and bool(base_result.get("used_fallback"))
        ):
            ctx_answer, ctx_sources = self._build_case_context_grounded_answer(
                question=normalized_question,
                case_id=safe_case_id,
                case_context=case_context,
                case_snapshot=case_snapshot,
            )
            if ctx_answer:
                _logger.debug(
                    "[RETRIEVAL] case_context_fallback_used | case_id=%s ctx_sources=%s",
                    safe_case_id, len(ctx_sources),
                )
                base_result = {
                    **base_result,
                    "answer": ctx_answer,
                    "used_fallback": True,
                    "fallback_reason": "rag_empty_case_context_used",
                    "confidence": "medium",
                    "sources": ctx_sources,
                    "citations": self._context_sources_to_citations(ctx_sources),
                }
                raw_sources = ctx_sources

        if not use_external_research:
            payload = {**base_result, "jurisdiction": jurisdiction_context}
            result = self._maybe_finalize(
                payload, reasoning_level, intent, normalized_question, tenant_id, finalize_reasoning_fn,
            )
            _logger.debug(
                "[RETRIEVAL] retrieval_execution_end | path=internal_only "
                "sources_count=%s used_fallback=%s confidence=%s duration_ms=%.1f",
                len(result.get("sources") or []), result.get("used_fallback"),
                result.get("confidence"), (time.monotonic() - _t0) * 1000,
            )
            return result

        # ── External research augmentation ────────────────────────────────────
        research = external_research_service.search(
            query=optimized_question,
            max_results=max(3, min(safe_top_k, 8)),
        )
        if not research.get("used_external"):
            payload = {**base_result, "jurisdiction": jurisdiction_context}
            result = self._maybe_finalize(
                payload, reasoning_level, intent, normalized_question, tenant_id, finalize_reasoning_fn,
            )
            _logger.debug(
                "[RETRIEVAL] retrieval_execution_end | path=no_external "
                "sources_count=%s used_fallback=%s confidence=%s duration_ms=%.1f",
                len(result.get("sources") or []), result.get("used_fallback"),
                result.get("confidence"), (time.monotonic() - _t0) * 1000,
            )
            return result

        external_results: List[Dict[str, Any]] = research.get("results") or []
        if not external_results:
            payload = {**base_result, "jurisdiction": jurisdiction_context}
            result = self._maybe_finalize(
                payload, reasoning_level, intent, normalized_question, tenant_id, finalize_reasoning_fn,
            )
            _logger.debug(
                "[RETRIEVAL] retrieval_execution_end | path=no_external_results "
                "sources_count=%s duration_ms=%.1f",
                len(result.get("sources") or []), (time.monotonic() - _t0) * 1000,
            )
            return result

        # ── Synthesise with external research ────────────────────────────────
        synthesized_answer = self._synthesize_answer_with_external_research(
            question=question,
            internal_answer=base_result.get("answer", ""),
            internal_sources=raw_sources,
            external_results=external_results,
            jurisdiction_prompt_block=jurisdiction_prompt_block,
        )
        if self._is_prompt_noise(synthesized_answer):
            synthesized_answer = base_result.get("answer", "")

        merged_sources = list(raw_sources)
        merged_sources.extend(self._external_results_to_sources(external_results))
        merged_citations = list(raw_citations)
        merged_citations.extend(self._external_results_to_citations(external_results))

        payload = {
            "answer": synthesized_answer or base_result.get("answer", ""),
            "used_fallback": bool(base_result.get("used_fallback")),
            "fallback_reason": base_result.get("fallback_reason"),
            "confidence": base_result.get("confidence", "medium"),
            "scope": base_result.get("scope", "global"),
            "sources": merged_sources[:20],
            "citations": merged_citations[:12],
            "cache": base_result.get("cache", {"hit": False, "backend": "none"}),
            "jurisdiction": jurisdiction_context,
        }
        result = self._maybe_finalize(
            payload, reasoning_level, intent, normalized_question, tenant_id, finalize_reasoning_fn,
        )
        _logger.debug(
            "[RETRIEVAL] retrieval_execution_end | path=with_external "
            "sources_count=%s used_fallback=%s confidence=%s duration_ms=%.1f",
            len(result.get("sources") or []), result.get("used_fallback"),
            result.get("confidence"), (time.monotonic() - _t0) * 1000,
        )
        return result

    # ──────────────────────────────────────────────────────────────────────────
    # Internal helpers
    # ──────────────────────────────────────────────────────────────────────────

    @staticmethod
    def _maybe_finalize(
        payload: Dict[str, Any],
        reasoning_level: str,
        intent: str | None,
        question: str,
        tenant_id: int | None,
        finalize_fn: Callable[..., Dict[str, Any]] | None,
    ) -> Dict[str, Any]:
        """Apply high-reasoning finalization if a callback was provided."""
        if finalize_fn is not None:
            return finalize_fn(
                payload=payload,
                reasoning_level=reasoning_level,
                intent=intent,
                question=question,
                tenant_id=tenant_id,
            )
        return payload

    def _synthesize_answer_with_external_research(
        self,
        *,
        question: str,
        internal_answer: str,
        internal_sources: List[Dict[str, Any]],
        external_results: List[Dict[str, Any]],
        jurisdiction_prompt_block: str,
    ) -> str:
        """LLM synthesis of internal + external evidence.  Falls back to
        concatenated summary when no LLM client is available."""
        if not self.client:
            return self._build_fallback_external_answer(
                internal_answer=internal_answer,
                external_results=external_results,
            )

        compact_internal_sources = internal_sources[:6]
        compact_external = external_results[:6]

        prompt = f"""
You are a legal AI copilot.
Synthesize one practical answer to the user's question using:
1) internal case/document evidence
2) external web research snippets

Rules:
- Prioritize internal evidence when there is conflict.
- Do not invent facts.
- Keep the answer concise and professional.
- End with a short "Web references" line listing up to 3 URLs.
- Respect the jurisdiction guardrails when applicable.

Jurisdiction context:
{jurisdiction_prompt_block or "No specific jurisdiction scope was provided."}

Question:
{question}

Internal grounded answer:
{internal_answer}

Internal sources (JSON):
{json.dumps(compact_internal_sources, ensure_ascii=False)}

External research snippets (JSON):
{json.dumps(compact_external, ensure_ascii=False)}
"""
        try:
            response = self.client.responses.create(
                model=self.model,
                input=prompt,
            )
            output = llm_gateway.extract_output_text(response).strip()
            if output:
                return output
        except Exception:
            pass

        return self._build_fallback_external_answer(
            internal_answer=internal_answer,
            external_results=external_results,
        )

    @staticmethod
    def _external_results_to_sources(
        external_results: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        sources: List[Dict[str, Any]] = []
        for item in external_results:
            title = str(item.get("title") or item.get("domain") or "Web Research").strip()
            url = str(item.get("url") or "").strip()
            snippet = str(item.get("snippet") or "").strip()
            source_text = snippet
            if url:
                source_text = f"{source_text} (source: {url})".strip()
            sources.append(
                {
                    "chunk_id": None,
                    "document_id": None,
                    "case_id": None,
                    "filename": title[:120] or "Web Research",
                    "chunk_index": None,
                    "score": 0.35,
                    "snippet": source_text[:300],
                }
            )
        return sources

    @staticmethod
    def _external_results_to_citations(
        external_results: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        citations: List[Dict[str, Any]] = []
        for item in external_results[:6]:
            title = str(item.get("title") or item.get("domain") or "Web Research").strip()
            snippet = str(item.get("snippet") or "").strip()
            url = str(item.get("url") or "").strip()
            citations.append(
                {
                    "label": title[:120] or "Web Research",
                    "document_id": None,
                    "case_id": None,
                    "snippet": snippet[:280],
                    "url": url or None,
                }
            )
        return citations

    @staticmethod
    def _build_fallback_external_answer(
        *,
        internal_answer: str,
        external_results: List[Dict[str, Any]],
    ) -> str:
        lines = [internal_answer.strip() or "No internal answer was generated."]
        lines.append("")
        lines.append("External web findings:")
        for item in external_results[:5]:
            title = str(item.get("title") or item.get("domain") or "Web Result").strip()
            snippet = str(item.get("snippet") or "").strip()
            url = str(item.get("url") or "").strip()
            combined = f"- {title}: {snippet}"
            if url:
                combined += f" ({url})"
            lines.append(combined[:360])
        return "\n".join(lines).strip()

    @staticmethod
    def _looks_like_material_breach_clause_question(question: str) -> bool:
        lowered = str(question or "").lower()
        if not lowered:
            return False
        if any(kw in lowered for kw in _consts.MATERIAL_BREACH_QUERY_KEYWORDS):
            return True
        if "clause" in lowered and any(
            token in lowered for token in ["breach", "termination", "notice", "cure", "invoice", "sla"]
        ):
            return True
        return False

    @staticmethod
    def _optimize_prompt_for_query(
        *,
        question: str,
        intent: str | None,
        target_type: str | None,
        target_id: int | None,
        allow_llm: bool = False,
    ) -> str:
        optimized = prompt_optimizer_agent.optimize_query(
            raw_query=question,
            intent=intent,
            target_type=target_type,
            target_id=target_id,
            allow_llm=allow_llm,
        )
        candidate = optimized.payload.get("optimized_query") if optimized.success else ""
        return str(candidate or question).strip()

    @staticmethod
    def _build_case_context_grounded_answer(
        *,
        question: str,
        case_id: int,
        case_context: Dict[str, Any] | None,
        case_snapshot: Dict[str, Any] | None,
    ) -> tuple[str, List[Dict[str, Any]]]:
        """Build a grounded answer from prefetched case context when RAG returns
        zero chunks.  Uses only what the context explicitly provides — no
        invented facts.

        Returns (answer_text, synthesized_sources).  Both are empty when no
        usable context is available.

        Actual output structures:
        - case_context: {scope, case: {id,title,status,jurisdiction_country,...},
            timeline: [{event_type, label, timestamp}],
            risk_signals: [str], memory: {...}}
        - case_snapshot: {case, facts, reasoning: {overview, narrative_summary,
            document_summaries: [str], main_issues: [str], key_dates: [{label,value}],
            legal_risks: [str], sources: [{filename,snippet,document_id,case_id,...}],
            parties: [str], recommended_next_steps: [str]},
            citations: [{label,snippet,...}], summary_text: str, version, refreshed_at}
        """
        lines: List[str] = []
        sources: List[Dict[str, Any]] = []

        # ── Debug: log what keys are actually present ──────────────────────
        _logger.debug(
            "[RETRIEVAL] fallback_context_keys=%s fallback_snapshot_keys=%s "
            "fallback_snapshot_reasoning_keys=%s",
            sorted(case_context.keys()) if isinstance(case_context, dict) else "None",
            sorted(case_snapshot.keys()) if isinstance(case_snapshot, dict) else "None",
            sorted((case_snapshot.get("reasoning") or {}).keys())
            if isinstance(case_snapshot, dict) else "None",
        )

        # ── Pull basic case metadata from case_context ─────────────────────
        if isinstance(case_context, dict):
            case_data = case_context.get("case")
            if isinstance(case_data, dict):
                title = str(case_data.get("title") or "").strip()
                status = str(case_data.get("status") or "").strip()
                jurisdiction = str(case_data.get("jurisdiction_country") or "").strip()
                if title:
                    meta_parts = [f"Case: {title}"]
                    if status:
                        meta_parts.append(f"Status: {status}")
                    if jurisdiction:
                        meta_parts.append(f"Jurisdiction: {jurisdiction}")
                    lines.append(" | ".join(meta_parts))

            # risk_signals from CaseContextService are plain strings
            risk_signals_raw: list = case_context.get("risk_signals") or []
            if isinstance(risk_signals_raw, list):
                risk_texts = [str(r).strip() for r in risk_signals_raw[:6] if r and str(r).strip()]
                if risk_texts:
                    lines.append("Risk signals: " + "; ".join(risk_texts))

            # timeline entries: {event_type, label, timestamp}
            timeline_raw: list = case_context.get("timeline") or []
            if isinstance(timeline_raw, list):
                events = []
                for e in timeline_raw[:6]:
                    if not isinstance(e, dict):
                        continue
                    label = str(e.get("label") or "").strip()
                    evt_type = str(e.get("event_type") or "").strip()
                    ts = str(e.get("timestamp") or "").strip()[:10]  # date part only
                    if label:
                        events.append(f"{label} ({evt_type})" + (f" [{ts}]" if ts else ""))
                if events:
                    lines.append("Timeline: " + "; ".join(events))

        # ── Pull rich intelligence from case_snapshot.reasoning ────────────
        if isinstance(case_snapshot, dict):
            # Top-level summary_text is a short human-readable string
            snap_summary = str(case_snapshot.get("summary_text") or "").strip()

            reasoning: Dict[str, Any] = case_snapshot.get("reasoning") or {}
            if not isinstance(reasoning, dict):
                reasoning = {}

            overview = str(reasoning.get("overview") or reasoning.get("narrative_summary") or snap_summary or "").strip()
            if overview:
                lines.append(f"Overview: {overview[:600]}")
                sources.append({
                    "chunk_id": None,
                    "document_id": None,
                    "case_id": case_id,
                    "filename": "Case analysis overview",
                    "chunk_index": None,
                    "score": 0.60,
                    "snippet": overview[:300],
                })

            # document_summaries: list of strings like "filename.pdf: summary text"
            doc_summaries_raw: list = reasoning.get("document_summaries") or []
            if isinstance(doc_summaries_raw, list):
                existing_text = "\n".join(lines)
                for ds in doc_summaries_raw[:10]:
                    ds_text = str(ds or "").strip()
                    if not ds_text or ds_text in existing_text:
                        continue
                    # Try to parse "filename: summary" format
                    if ": " in ds_text:
                        ds_name, ds_body = ds_text.split(": ", 1)
                        ds_name = ds_name.strip()
                        ds_body = ds_body.strip()
                    else:
                        ds_name = "Document"
                        ds_body = ds_text
                    lines.append(f"'{ds_name}': {ds_body[:400]}")
                    sources.append({
                        "chunk_id": None,
                        "document_id": None,
                        "case_id": case_id,
                        "filename": ds_name[:120] or "Case document",
                        "chunk_index": None,
                        "score": 0.55,
                        "snippet": ds_body[:300],
                    })

            # main_issues: list of strings
            main_issues_raw: list = reasoning.get("main_issues") or []
            if isinstance(main_issues_raw, list):
                issues = [str(i).strip() for i in main_issues_raw[:5] if i and str(i).strip()]
                if issues:
                    lines.append("Main issues: " + "; ".join(issues))

            # key_dates: [{label, value}]
            key_dates_raw: list = reasoning.get("key_dates") or []
            if isinstance(key_dates_raw, list):
                dates = []
                for kd in key_dates_raw[:5]:
                    if not isinstance(kd, dict):
                        continue
                    lbl = str(kd.get("label") or "").strip()
                    val = str(kd.get("value") or "").strip()
                    if lbl and val:
                        dates.append(f"{lbl}: {val}")
                if dates:
                    lines.append("Key dates: " + "; ".join(dates))

            # legal_risks: list of strings
            legal_risks_raw: list = reasoning.get("legal_risks") or []
            if isinstance(legal_risks_raw, list):
                risks = [str(r).strip() for r in legal_risks_raw[:5] if r and str(r).strip()]
                if risks:
                    lines.append("Legal risks: " + "; ".join(risks))

            # sources from reasoning: [{filename, snippet, document_id, case_id}]
            snap_sources_raw: list = reasoning.get("sources") or []
            if isinstance(snap_sources_raw, list):
                existing_filenames = {str(s.get("filename") or "").strip() for s in sources}
                for s in snap_sources_raw[:8]:
                    if not isinstance(s, dict):
                        continue
                    fname = str(s.get("filename") or "").strip()
                    snippet = str(s.get("snippet") or "").strip()
                    if not snippet:
                        continue
                    if fname in existing_filenames:
                        continue
                    sources.append({
                        "chunk_id": s.get("chunk_id"),
                        "document_id": s.get("document_id"),
                        "case_id": s.get("case_id") or case_id,
                        "filename": fname or "Case document",
                        "chunk_index": s.get("chunk_index"),
                        "score": float(s.get("score") or 0.50),
                        "snippet": snippet[:300],
                    })
                    existing_filenames.add(fname)

            # parties
            parties_raw: list = reasoning.get("parties") or []
            if isinstance(parties_raw, list):
                parties = [str(p).strip() for p in parties_raw[:4] if p and str(p).strip()]
                if parties:
                    lines.append("Parties: " + ", ".join(parties))

            # citations as fallback source pool (if reasoning.sources was empty)
            if not sources:
                citations_raw: list = case_snapshot.get("citations") or []
                if isinstance(citations_raw, list):
                    for cit in citations_raw[:6]:
                        if not isinstance(cit, dict):
                            continue
                        label = str(cit.get("label") or "").strip()
                        snippet = str(cit.get("snippet") or "").strip()
                        if snippet:
                            sources.append({
                                "chunk_id": None,
                                "document_id": cit.get("document_id"),
                                "case_id": cit.get("case_id") or case_id,
                                "filename": label or "Case document",
                                "chunk_index": None,
                                "score": 0.45,
                                "snippet": snippet[:300],
                            })

        _logger.debug(
            "[RETRIEVAL] fallback_content_probe | document_summaries_count=%s "
            "context_sources_count=%s fallback_lines_count=%s",
            sum(1 for s in sources if "Document" in str(s.get("filename") or "")),
            len(sources),
            len(lines),
        )

        if not lines:
            return "", []

        header = (
            "Based on the available case context (documents are not yet fully indexed "
            "or no matching chunks were found for your query):\n\n"
        )
        return header + "\n".join(lines), sources[:12]

    @staticmethod
    def _context_sources_to_citations(sources: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        return [
            {
                "label": str(s.get("filename") or "Case document").strip()[:120],
                "document_id": s.get("document_id"),
                "case_id": s.get("case_id"),
                "snippet": str(s.get("snippet") or "").strip()[:280],
                "url": None,
            }
            for s in sources[:8]
        ]

    @staticmethod
    def _is_prompt_noise(text: str) -> bool:
        """Inline port of CopilotService._looks_like_prompt_template_noise.
        Kept as a private copy to avoid a circular import.
        """
        candidate = str(text or "").strip().lower()
        if not candidate:
            return False
        noisy_fragments = (
            "<case_id>",
            "<document_id>",
            "optimize prompt:",
            "what success looks like",
            "email for case #<",
            "sources appea",
            "pdf_ready.md",
            "` - `",
        )
        if any(fragment in candidate for fragment in noisy_fragments):
            return True
        if "email for case #" in candidate and "optimize prompt" in candidate:
            return True
        return False


# Module-level singleton — wired to real dependencies by CopilotService.__init__()
# and also available for tests that want to construct it independently.
__all__ = ["CopilotRetrievalExecutionService"]
