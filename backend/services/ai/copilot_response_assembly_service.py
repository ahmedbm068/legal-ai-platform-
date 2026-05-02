"""Step 3E — Single source of truth for CopilotService response assembly.
Step 4  — Quality & product hardening:
  - Fix #1: Grounding inconsistency (used_fallback always → Partial, never Case-grounded)
  - Fix #2: Legal search source relevance filter
  - Fix #3: ask_case fallback concise structured answer
  - Fix #4: Improved confidence scoring (_compute_confidence)

Centralises:
  1. Final answer formatting
  2. Grounding classification (Case-grounded / Partial / Not grounded)
  3. Confidence normalization (high / medium / low)
  4. Fallback labeling
  5. Source + citation deduplication / relevance filtering
  6. Warning messages
  7. Structured result merging
  8. Mode-specific output shaping
  9. Output contract consistency
"""

from __future__ import annotations

import logging
import re
import time
from typing import Any, Dict, List, Optional

_logger = logging.getLogger("copilot.response")

# ──────────────────────────────────────────────────────────────────────────────
# Grounding / warning constants
# ──────────────────────────────────────────────────────────────────────────────

_GROUNDING_CASE = "Case-grounded"
_GROUNDING_PARTIAL = "Partial"
_GROUNDING_NONE = "Not grounded"

_WARNING_NOT_GROUNDED = (
    "The case file does not contain documents sufficient to ground this response. "
    "Independent legal review is required before reliance."
)
_WARNING_PARTIAL_FALLBACK = (
    "The case file indicates that full document indexing is incomplete. "
    "This response draws on case metadata only and must be verified by counsel before use."
)
_WARNING_PARTIAL = (
    "This response is partially supported by case documents. "
    "Certain assertions require independent verification before reliance in proceedings."
)

# Modes where grounding annotations are meaningful
_GROUNDED_MODES = {"legal_search", "external", "agent", "default"}

# Scope values that indicate case / document context
_CASE_SCOPES = {"case", "document", "case_document"}

# Fallback reasons that indicate doc-indexing fallback (not full grounding)
_INDEXING_FALLBACK_REASONS = {
    "rag_empty_case_context_used",
    "empty_query",
    "no_matching_chunks",
    "chunk_fallback",
}

# Answer phrases that indicate insufficient evidence
_INSUFFICIENT_EVIDENCE_PHRASES = (
    "not enough grounded evidence",
    "insufficient evidence",
    "documents are not yet fully indexed",
    "no matching chunks were found",
    "not yet fully indexed",
)

# ask_case section headings for structured fallback
_ASK_CASE_SECTIONS = (
    "Parties",
    "Contract / Legal relationship",
    "Incident / Trigger event",
    "Dispute / Allegations",
    "Counterparty position",
    "Financial issue",
    "Operational impact",
    "Current posture",
    "Missing facts / Verification needed",
)


class CopilotResponseAssemblyService:
    """Dedicated assembly service (Steps 3E + 4).

    Instantiated once in ``CopilotService.__init__`` and called via the
    compatibility shim that replaces the final ``return {...}`` statement in
    ``CopilotService.handle_message()``.
    """

    # ──────────────────────────────────────────────────────────────────────────
    # Public entry point
    # ──────────────────────────────────────────────────────────────────────────

    def assemble(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """Build and return the fully normalized, quality-hardened response dict.

        Parameters
        ----------
        state:
            Flat dict from ``CopilotService.handle_message()`` containing:
            message, parsed, result, mode, reasoning_level, agent_mode,
            use_trust_engine, intent, action_category, action_status,
            permission_denied, structured_result, steps.
            Optionally: has_case_context, verification_result.
        """
        started = time.perf_counter()

        # ── Unpack state ──────────────────────────────────────────────────────
        message: str = str(state.get("message") or state.get("raw_message") or "")
        parsed: Dict[str, Any] = state.get("parsed") or {}
        result: Dict[str, Any] = dict(state.get("result") or {})
        mode: str = str(state.get("mode") or "default").strip().lower()
        reasoning_level: str = str(state.get("reasoning_level") or "standard")
        agent_mode: bool = bool(state.get("agent_mode"))
        use_trust_engine: bool = bool(state.get("use_trust_engine"))
        intent: str = str(state.get("intent") or parsed.get("intent") or "")
        action_category: str = str(state.get("action_category") or "analysis")
        action_status: str = str(state.get("action_status") or "completed")
        permission_denied: bool = bool(state.get("permission_denied"))
        structured_result: Dict[str, Any] = dict(state.get("structured_result") or {})
        steps: List[str] = list(state.get("steps") or [])
        # Optional quality signals
        has_case_context: bool = bool(state.get("has_case_context"))
        verification_result: Dict[str, Any] = dict(state.get("verification_result") or {})
        # Secondary case-context signals (Step 9) — strengthen has_case_context if omitted by caller
        _case_ctx = state.get("case_context")
        _case_snap = state.get("case_snapshot")
        if not has_case_context:
            has_case_context = bool(
                (_case_ctx and isinstance(_case_ctx, dict))
                or (_case_snap and isinstance(_case_snap, dict))
            )

        _logger.debug(
            "[RESPONSE] response_assembly_start | intent=%s mode=%s agent_mode=%s use_trust_engine=%s",
            intent, mode, agent_mode, use_trust_engine,
        )
        _logger.debug(
            "[RESPONSE] quality_signals | has_case_context=%s "
            "verification_result_present=%s verification_status=%r "
            "confidence_before=%r",
            has_case_context,
            bool(verification_result),
            str(verification_result.get("verification_status") or ""),
            result.get("confidence"),
        )

        used_fallback: bool = bool(result.get("used_fallback"))
        fallback_reason: str = str(result.get("fallback_reason") or "").strip()
        scope: str = str(result.get("scope") or "").strip().lower()
        answer: str = str(result.get("answer") or "")

        # ── R5c-ui: strip metadata sections from case-context fallback answer ──
        # _format_legal_search_output always appends [Trust Status], [Legal
        # Authority Status], and [Fallback Notice] blocks. For the structured
        # case-context path these are internal metadata that should not appear
        # in the user-facing answer — only the 5 structured sections should remain.
        if fallback_reason == "case_context_no_legal_provisions":
            answer = self._strip_legal_metadata_blocks(answer)
            result["answer"] = answer

        # Detect whether this is a doc-indexing fallback (not fully retrieved)
        is_indexing_fallback = (
            used_fallback
            and (
                fallback_reason in _INDEXING_FALLBACK_REASONS
                or any(phrase in answer.lower() for phrase in _INSUFFICIENT_EVIDENCE_PHRASES)
            )
        )

        # ── Fix #3: ask_case concise structured answer ─────────────────────────
        if intent == "ask_case" and is_indexing_fallback and answer.strip():
            answer = self._format_ask_case_concise(answer)
            result["answer"] = answer
            _logger.debug("[RESPONSE] ask_case_summary_mode | intent=%s fallback_reason=%s", intent, fallback_reason)

        # ── 1. Normalize sources + citations ──────────────────────────────────
        raw_sources = self._normalize_sources(result.get("sources"))
        raw_citations = self._normalize_citations(result.get("citations"))

        # ── Fix #2: Legal search source relevance filter ──────────────────────
        if mode in {"legal_search", "external"} or use_trust_engine:
            sources = self._filter_relevant_sources(
                sources=raw_sources,
                answer=answer,
                intent=intent,
                query=message,
            )
            citations = self._filter_relevant_citations(
                citations=raw_citations,
                answer=answer,
                intent=intent,
                query=message,
            )
            if len(sources) < len(raw_sources) or len(citations) < len(raw_citations):
                _logger.debug(
                    "[RESPONSE] source_filtering | mode=%s intent=%s "
                    "sources_before=%s sources_after=%s citations_before=%s citations_after=%s",
                    mode, intent,
                    len(raw_sources), len(sources),
                    len(raw_citations), len(citations),
                )
        else:
            sources = raw_sources
            citations = raw_citations

        sources_count = len(sources)

        # ── Fix #1: Grounding classification (fallback-aware) ─────────────────
        grounding = self._classify_grounding(
            sources_count=sources_count,
            used_fallback=used_fallback,
            is_indexing_fallback=is_indexing_fallback,
            scope=scope,
            mode=mode,
            use_trust_engine=use_trust_engine,
        )
        _logger.debug(
            "[RESPONSE] grounding_decision | intent=%s mode=%s used_fallback=%s "
            "is_indexing_fallback=%s sources_count=%s grounding=%s",
            intent, mode, used_fallback, is_indexing_fallback, sources_count, grounding,
        )

        # ── Fix #4: Improved confidence scoring ───────────────────────────────
        _has_ctx = has_case_context or (sources_count > 0)
        confidence = self._compute_confidence(
            sources_count=sources_count,
            used_fallback=used_fallback,
            verification_result=verification_result,
            has_case_context=_has_ctx,
            existing=result.get("confidence"),
        )
        confidence_reason = self._build_confidence_reason(
            sources_count=sources_count,
            used_fallback=used_fallback,
            is_indexing_fallback=is_indexing_fallback,
            verification_result=verification_result,
            confidence=confidence,
        )
        _logger.debug(
            "[RESPONSE] confidence_decision | intent=%s sources_count=%s "
            "used_fallback=%s has_case_context=%s confidence_after=%s reason=%r",
            intent, sources_count, used_fallback, _has_ctx, confidence, confidence_reason,
        )

        # ── Answer-text insufficient-grounding override ──────────────────────
        # Must run AFTER normal grounding/confidence so it can correct contradictions
        # (e.g. 6 sources exist but the answer itself says "not enough grounded evidence").
        _answer_insufficient = self._answer_indicates_insufficient_grounding(answer)
        if _answer_insufficient:
            _logger.debug(
                "[RESPONSE] answer_insufficient_grounding_override | "
                "old_grounding=%s old_confidence=%s intent=%s mode=%s",
                grounding, confidence, intent, mode,
            )
            # Downgrade grounding — keep Partial if case context exists, else Not grounded
            if grounding == _GROUNDING_CASE:
                grounding = _GROUNDING_PARTIAL if has_case_context else _GROUNDING_NONE
            confidence = "low"
            confidence_reason = (
                "The response itself indicates insufficient grounded evidence. "
                "Source references were found but do not support a reliable legal analysis. "
                "Independent verification of applicable legal authority is required."
            )
            # Downgrade sources count used for insight display (don't hide them, but don't let
            # them inflate grounding signals — keep sources list intact for transparency)

        # ── Warning message ───────────────────────────────────────────────────
        legal_warning = self._build_legal_warning(
            grounding=grounding,
            mode=mode,
            is_indexing_fallback=is_indexing_fallback or _answer_insufficient,
        )

        # ── Legal search: no-sources safety note ─────────────────────────────
        legal_sources_note: Optional[str] = None
        if (mode in {"legal_search", "external"} or use_trust_engine) and (
            sources_count == 0 or _answer_insufficient
        ):
            legal_sources_note = (
                "No applicable legal provisions were identified for this query. "
                "The response is based on available case context only. "
                "Counsel must verify the governing legal authority before reliance."
            )

        # ── AI Insight block ──────────────────────────────────────────────────
        ai_insight = self._build_ai_insight(
            grounding=grounding,
            confidence=confidence,
            confidence_reason=confidence_reason,
            intent=intent,
            mode=mode,
            is_indexing_fallback=is_indexing_fallback,
            sources_count=sources_count,
            used_fallback=used_fallback,
            legal_sources_note=legal_sources_note,
        )

        # ── Structured result — merge all quality signals into it ─────────────
        if grounding and mode in _GROUNDED_MODES:
            structured_result["grounding"] = grounding
            if legal_warning:
                structured_result["legal_warning"] = legal_warning
        structured_result["ai_insight"] = ai_insight
        structured_result["confidence_reason"] = confidence_reason
        if legal_sources_note:
            structured_result["legal_sources_note"] = legal_sources_note

        # ── Build final response (preserving exact existing contract) ──────────
        response: Dict[str, Any] = {
            "message": message,
            "parsed_intent": parsed.get("intent", intent),
            "target_type": parsed.get("target_type"),
            "target_id": parsed.get("target_id"),
            "mode": mode,
            "reasoning_level": reasoning_level,
            "agent_mode": agent_mode,
            "action_category": action_category,
            "action_status": action_status,
            "permission_denied": permission_denied,
            "steps": steps if agent_mode else [],
            "structured_result": structured_result,
        }

        # Spread remaining execution fields (answer, scope, trust_panel, etc.)
        for key, value in result.items():
            if key in {"sources", "citations"}:
                continue  # use our normalized/filtered versions
            if key not in response:
                response[key] = value

        # Inject normalized sources, citations, confidence, grounding, insight
        response["sources"] = sources
        response["citations"] = citations
        response["confidence"] = confidence
        response["confidence_reason"] = confidence_reason
        response["grounding"] = grounding
        response["ai_insight"] = ai_insight
        if legal_warning:
            response["legal_warning"] = legal_warning
        if legal_sources_note:
            response["legal_sources_note"] = legal_sources_note

        # Ensure required baseline fields are always present
        response.setdefault("answer", "")
        response.setdefault("used_fallback", False)
        response.setdefault("fallback_reason", None)
        response.setdefault("scope", "global")

        duration_ms = (time.perf_counter() - started) * 1000.0
        _logger.debug(
            "[RESPONSE] response_assembly_end | intent=%s mode=%s grounding=%s "
            "confidence=%s sources_count=%s used_fallback=%s duration_ms=%.0f",
            intent, mode, grounding, confidence, sources_count, used_fallback, duration_ms,
        )

        return response

    # ──────────────────────────────────────────────────────────────────────────
    # Fix #1 — Grounding classification (fallback-aware)
    # ──────────────────────────────────────────────────────────────────────────

    @staticmethod
    def _classify_grounding(
        *,
        sources_count: int,
        used_fallback: bool,
        is_indexing_fallback: bool,
        scope: str,
        mode: str,
        use_trust_engine: bool,
    ) -> Optional[str]:
        """Return a grounding label following the Step 4 rules.

        Rules (strict priority):
        1. used_fallback=True → never "Case-grounded"; max is "Partial".
        2. sources_count > 0, no fallback, case scope → "Case-grounded".
        3. sources_count > 0, fallback used → "Partial".
        4. sources_count == 0, fallback used → "Not grounded".
        5. Chat mode with no case signal → None.
        """
        # Chat mode without case anchor — grounding not meaningful
        if (
            mode == "default"
            and not use_trust_engine
            and scope not in _CASE_SCOPES
            and sources_count == 0
            and not used_fallback
        ):
            return None

        # Key rule: used_fallback=True → always Partial or worse
        if used_fallback:
            if sources_count > 0:
                return _GROUNDING_PARTIAL
            return _GROUNDING_NONE

        # No fallback path
        if sources_count > 0:
            is_case_scope = scope in _CASE_SCOPES or use_trust_engine
            if is_case_scope:
                return _GROUNDING_CASE
            return _GROUNDING_PARTIAL

        # No sources, no fallback (e.g. CRUD action, permission denied, chat greeting)
        return None

    # ──────────────────────────────────────────────────────────────────────────
    # Fix #4 — Improved confidence scoring
    # ──────────────────────────────────────────────────────────────────────────

    @staticmethod
    def _compute_confidence(
        *,
        sources_count: int,
        used_fallback: bool,
        verification_result: Dict[str, Any],
        has_case_context: bool,
        existing: Any = None,
    ) -> str:
        """Compute a confidence label from execution signals.

        High:
        - sources_count >= 3, no fallback, verifier says "verified" or "partial"
          with no unsupported core claims

        Medium:
        - used_fallback but case_context/snapshot sources exist
        - or sources_count > 0 but verifier is partial

        Low:
        - sources_count == 0
        - or unsupported core claims
        - or no usable case context
        """
        # Never override an explicit "low" from the execution service
        existing_token = str(existing or "").strip().lower()

        # Derive verification status from verification_result
        v_status = str(
            verification_result.get("verification_status")
            or (verification_result.get("global_output_contract") or {}).get("verification_status")
            or existing_token
            or ""
        ).strip().lower()
        has_unsupported_core = bool(verification_result.get("has_unsupported_core_claims"))

        # Low — strongest downgrade signal
        if sources_count == 0 and not has_case_context:
            confidence = "low"
        elif has_unsupported_core:
            confidence = "low"
        elif sources_count == 0 and has_case_context and used_fallback:
            # Context available but no chunks — medium floor
            confidence = "medium"
        elif used_fallback and sources_count > 0:
            confidence = "medium"
        elif sources_count >= 3 and not used_fallback and v_status in {"verified", "partial", ""}:
            confidence = "high"
        elif sources_count > 0 and not used_fallback:
            confidence = "medium"
        else:
            confidence = "low"

        # Respect an explicit low from the execution service — never upgrade it
        if existing_token == "low":
            return "low"
        # Respect explicit high when our logic also says high
        if existing_token == "high" and confidence == "high":
            return "high"
        # Correct contradiction: execution said "high" but signals say low/medium
        if existing_token == "high" and confidence in {"low", "medium"}:
            return confidence

        return confidence

    # ──────────────────────────────────────────────────────────────────────────
    # Fix #2 — Legal search source relevance filter
    # ──────────────────────────────────────────────────────────────────────────

    @classmethod
    def _is_source_relevant_to_answer(
        cls,
        source: Any,
        answer: str,
        intent: str,
        query: str,
    ) -> bool:
        """Return True when a source is relevant to the answer/query.

        Heuristic rules (simple, no LLM):
        1. Source reference / article number is mentioned in the answer.
        2. Source snippet has meaningful keyword overlap with query+answer.
        3. Source filename is explicitly cited in the answer.
        4. Source has a verifier-level "direct" or "partial" support marker.

        Legal-code sources (article refs) are hidden unless they satisfy at
        least one of these rules.
        """
        if not isinstance(source, dict):
            return False

        answer_lower = answer.lower()
        query_lower = query.lower()
        combined_lower = answer_lower + " " + query_lower

        filename = str(source.get("filename") or "").strip()
        snippet = str(source.get("snippet") or "").strip().lower()

        # Rule 4: explicit support marker from verifier
        support = str(source.get("support_level") or source.get("relevance") or "").strip().lower()
        if support in {"direct", "partial"}:
            return True

        # Rule 3: filename mentioned in answer
        if filename and filename.lower() in answer_lower:
            return True

        # Rule 1: article number reference in answer
        # detect patterns like "Article 29", "Art. 51", "article 19"
        article_match = re.search(r"\bart(?:icle)?\.?\s*(\d+)\b", filename, re.IGNORECASE)
        if article_match:
            article_num = article_match.group(1)
            # The article number must appear in the answer text
            if re.search(rf"\bart(?:icle)?\.?\s*{re.escape(article_num)}\b", answer, re.IGNORECASE):
                return True
            # Article not in answer → hide it
            return False

        # Rule 2: keyword overlap (at least 2 meaningful shared words)
        if snippet:
            stop_words = {
                "the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
                "in", "of", "to", "for", "and", "or", "but", "with", "as", "at", "by",
                "on", "from", "that", "this", "it", "its", "not", "no", "if", "any",
                "all", "has", "have", "had", "will", "would", "may", "can", "shall",
                "such", "there", "their", "which", "who", "what", "when", "where",
            }
            snippet_words = {w for w in re.findall(r"\b[a-z]{4,}\b", snippet) if w not in stop_words}
            combined_words = {w for w in re.findall(r"\b[a-z]{4,}\b", combined_lower) if w not in stop_words}
            overlap = snippet_words & combined_words
            if len(overlap) >= 2:
                return True

        # Document / case sources without article reference default to relevant
        # (only legal-code article sources are aggressively filtered)
        doc_id = source.get("document_id")
        case_id = source.get("case_id")
        if doc_id is not None or case_id is not None:
            return True

        return False

    @classmethod
    def _filter_relevant_sources(
        cls,
        *,
        sources: List[Any],
        answer: str,
        intent: str,
        query: str,
    ) -> List[Any]:
        """Return only sources relevant to the answer for legal-search mode."""
        if not sources:
            return sources
        filtered = [s for s in sources if cls._is_source_relevant_to_answer(s, answer, intent, query)]
        return filtered if filtered else []

    @classmethod
    def _filter_relevant_citations(
        cls,
        *,
        citations: List[Any],
        answer: str,
        intent: str,
        query: str,
    ) -> List[Any]:
        """Return only citations relevant to the answer for legal-search mode."""
        if not citations:
            return citations
        filtered = [c for c in citations if cls._is_source_relevant_to_answer(c, answer, intent, query)]
        return filtered if filtered else []

    # ──────────────────────────────────────────────────────────────────────────
    # R5c-ui — strip metadata blocks from case-context legal-search answer
    # ──────────────────────────────────────────────────────────────────────────

    @staticmethod
    def _strip_legal_metadata_blocks(answer: str) -> str:
        """Remove [Trust Status], [Legal Authority Status], and [Fallback Notice]
        blocks from the answer text.

        These blocks are appended by _format_legal_search_output for all Legal
        Search fallback paths.  For the structured case-context path
        (fallback_reason="case_context_no_legal_provisions") they are internal
        metadata that must not appear in the user-facing answer — only the five
        structured sections (Case Risks … Counsel Note) should be visible.

        The method is a pure text transform: it truncates the answer at the first
        line that matches one of the metadata block headers.
        """
        _METADATA_BLOCK_PATTERN = re.compile(
            r"^\[(?:Trust Status|Legal Authority Status|Fallback Notice)\]",
            re.MULTILINE,
        )
        m = _METADATA_BLOCK_PATTERN.search(answer)
        if m:
            answer = answer[: m.start()].rstrip()
        return answer

    # ──────────────────────────────────────────────────────────────────────────
    # Fix #3 — ask_case concise structured answer
    # ──────────────────────────────────────────────────────────────────────────

    @staticmethod
    def _format_ask_case_concise(raw_answer: str) -> str:
        """Reformat a raw context-dump fallback into a concise structured summary.

        Parses the existing answer text and maps facts into the canonical
        ask_case sections.  Does NOT invent facts — only what the raw answer
        contains is used.  Max 1-2 bullets per section.
        """
        text = str(raw_answer or "").strip()
        if not text:
            return raw_answer

        # Strip the long header that says "documents are not yet fully indexed…"
        header_pattern = re.compile(
            r"^Based on the available case context[^:]*:\s*\n+",
            re.IGNORECASE | re.MULTILINE,
        )
        text = header_pattern.sub("", text).strip()

        # Helper: extract content from labelled lines
        def _grab(pattern: str) -> Optional[str]:
            m = re.search(pattern, text, re.IGNORECASE)
            if not m:
                return None
            end = m.end()
            value = text[end:].split("\n")[0].strip(" ;:-")
            return value[:280] if value else None

        # Helper: extract list items after a label
        def _grab_list(label: str, max_items: int = 2) -> List[str]:
            m = re.search(rf"(?i){re.escape(label)}\s*[:;]?\s*(.+?)(?:\n|$)", text)
            if not m:
                return []
            raw = m.group(1).strip()
            parts = [p.strip().strip(";,") for p in re.split(r"\s*[;,]\s*|\s+and\s+", raw) if p.strip()]
            return parts[:max_items]

        parties = _grab_list("Parties", 2)
        overview = _grab(r"Overview\s*[:;]?\s*")
        # Extract case title / meta from inline pipe format "Case: X | Status: Y | Jurisdiction: Z"
        case_title = _grab(r"Case\s*:\s*")
        case_status = _grab(r"Status\s*:\s*")
        case_jurisdiction = _grab(r"Jurisdiction\s*:\s*")
        main_issues = _grab_list("Main issues", 2)
        legal_risks = _grab_list("Legal risks", 2)
        key_dates = _grab_list("Key dates", 2)
        risk_signals = _grab_list("Risk signals", 2)

        # Build sections — law-firm quality, concise
        sections: List[str] = []

        def _add(heading: str, content: Optional[str]) -> None:
            if content and content.strip():
                sections.append(f"**{heading}**\n- {content.strip().rstrip('.')}.")

        def _add_list(heading: str, items: List[str]) -> None:
            clean = [i.strip().rstrip(".") for i in items if i.strip()][:2]
            if clean:
                bullets = "\n".join(f"- {item}." for item in clean)
                sections.append(f"**{heading}**\n{bullets}")

        # ── 1. Parties ────────────────────────────────────────────────────────
        if parties:
            _add_list("Parties", parties)
        elif case_title:
            _add("Parties", case_title)

        # ── 2. Contract / Legal relationship ──────────────────────────────────
        if overview:
            first_sentence = re.split(r"(?<=[.!?])\s+", overview.strip())[0]
            _add("Contract / Legal relationship", first_sentence)

        # ── 3. Incident / Trigger event ───────────────────────────────────────
        trigger = (risk_signals[:1] or main_issues[:1])
        if trigger:
            _add_list("Incident / Trigger event", trigger)

        # ── 4. Dispute / Allegations ──────────────────────────────────────────
        if main_issues:
            _add_list("Dispute / Allegations", main_issues[:2])

        # ── 5. Financial / Legal issue ────────────────────────────────────────
        if legal_risks:
            _add_list("Financial issue", legal_risks[:2])

        # ── 6. Key dates ──────────────────────────────────────────────────────
        if key_dates:
            _add_list("Key dates", key_dates[:2])

        # ── 7. Current posture ────────────────────────────────────────────────
        if case_status:
            _add("Current posture", case_status)
        elif case_jurisdiction:
            _add("Jurisdiction", case_jurisdiction)

        # ── 8. Missing facts / Verification needed ────────────────────────────
        sections.append(
            "**Missing facts / Verification needed**\n"
            "- The case file indicates that full document indexing is not yet complete. "
            "The above facts are derived from case metadata only. "
            "Counsel must verify all material facts before use in proceedings or client communications."
        )

        if not sections:
            # Nothing parsed — return stripped original
            return text

        header = "**Case Summary** *(pending full document indexing — counsel review required)*\n\n"
        return header + "\n\n".join(sections)

    # ──────────────────────────────────────────────────────────────────────────
    # Confidence reason explanation
    # ──────────────────────────────────────────────────────────────────────────

    @staticmethod
    def _build_confidence_reason(
        *,
        sources_count: int,
        used_fallback: bool,
        is_indexing_fallback: bool,
        verification_result: Dict[str, Any],
        confidence: str,
    ) -> str:
        """Return a one-sentence explanation of WHY the confidence level was assigned."""
        v_status = str(
            verification_result.get("verification_status")
            or (verification_result.get("global_output_contract") or {}).get("verification_status")
            or ""
        ).strip().lower()
        has_unsupported = bool(verification_result.get("has_unsupported_core_claims"))

        if confidence == "high":
            if sources_count >= 3:
                return (
                    f"{sources_count} case document sources were matched and verified. "
                    "All principal assertions are directly supported by the case record."
                )
            return "The response is supported by case documents. No fallback was required."

        if confidence == "medium":
            if is_indexing_fallback:
                return (
                    "The case file indicates that full document indexing is not yet complete. "
                    "This response is drawn from case snapshot, risk signals, and timeline metadata. "
                    "Reliability will improve once all documents are processed."
                )
            if used_fallback and sources_count > 0:
                return (
                    f"{sources_count} source(s) were identified; however, a retrieval fallback was triggered. "
                    "The response is partially supported by the case record."
                )
            if v_status == "partial":
                return "Verification yielded partial support. Certain assertions lack direct source backing and require counsel review."
            if sources_count > 0:
                return f"{sources_count} source(s) identified. Document coverage is incomplete for this query."
            return "The response draws on available case context. Full document support is absent for this query."

        # Low
        if has_unsupported:
            return "Principal assertions could not be matched to any document in the case record or cited legal provision."
        if sources_count == 0 and not used_fallback:
            return "No case documents or context sources are available for this query."
        return (
            "No document chunks correspond to this query and no reliable case context was located. "
            "This response must not be relied upon without independent legal verification."
        )

    # ──────────────────────────────────────────────────────────────────────────
    # AI Insight block
    # ──────────────────────────────────────────────────────────────────────────

    @staticmethod
    def _build_ai_insight(
        *,
        grounding: Optional[str],
        confidence: str,
        confidence_reason: str,
        intent: str,
        mode: str,
        is_indexing_fallback: bool,
        sources_count: int,
        used_fallback: bool,
        legal_sources_note: Optional[str],
    ) -> Dict[str, Any]:
        """Build a structured AI Insight block for display in the frontend.

        All fields are additive — the frontend may render or ignore any subset.
        """
        # Grounding type label
        if grounding == _GROUNDING_CASE:
            grounding_type = "Case-grounded"
            grounding_description = (
                f"The response is directly supported by {sources_count} document source(s) from the case record. "
                "No retrieval fallback was required."
            )
        elif grounding == _GROUNDING_PARTIAL:
            if is_indexing_fallback:
                grounding_type = "Fallback (context-based)"
                grounding_description = (
                    "The case file indicates that full document indexing is not yet complete. "
                    "The response draws from case snapshot, risk signals, and timeline metadata."
                )
            else:
                grounding_type = "Partial"
                grounding_description = (
                    f"{sources_count} source(s) were identified; however, a retrieval fallback was triggered. "
                    "Certain assertions may lack direct document support."
                )
        elif grounding == _GROUNDING_NONE:
            grounding_type = "Not grounded"
            grounding_description = (
                "The case record contains no documents applicable to this query. "
                "The response reflects general legal analysis only."
            )
        else:
            grounding_type = "General"
            grounding_description = "Document grounding is not applicable to this response."

        # Lawyer recommendation note
        if confidence == "high" and grounding == _GROUNDING_CASE:
            lawyer_note = (
                "The case record supports this response. "
                "Counsel review is advised prior to use in external communications or proceedings."
            )
        elif confidence == "medium" or grounding == _GROUNDING_PARTIAL:
            lawyer_note = (
                "The case file indicates partial or fallback evidence for this response. "
                "Counsel must review this output before it is relied upon in proceedings or client-facing materials."
            )
        else:
            lawyer_note = (
                "This response is not grounded in the case record. "
                "It must not be relied upon without independent verification by qualified counsel."
            )

        insight: Dict[str, Any] = {
            "grounding_type": grounding_type,
            "grounding_description": grounding_description,
            "confidence_level": confidence,
            "confidence_reason": confidence_reason,
            "lawyer_note": lawyer_note,
            "sources_count": sources_count,
            "used_fallback": used_fallback,
            "mode": mode,
            "intent": intent,
        }
        if legal_sources_note:
            insight["legal_sources_note"] = legal_sources_note
        return insight

    # ──────────────────────────────────────────────────────────────────────────
    # Warning message
    # ──────────────────────────────────────────────────────────────────────────

    @staticmethod
    def _build_legal_warning(
        *,
        grounding: Optional[str],
        mode: str,
        is_indexing_fallback: bool,
    ) -> Optional[str]:
        """Return a legal warning string, or None when not applicable."""
        if grounding is None:
            return None
        if grounding == _GROUNDING_NONE:
            return _WARNING_NOT_GROUNDED
        if grounding == _GROUNDING_PARTIAL:
            if is_indexing_fallback:
                return _WARNING_PARTIAL_FALLBACK
            return _WARNING_PARTIAL
        return None  # Case-grounded — no warning needed

    # ──────────────────────────────────────────────────────────────────────────
    # Answer-text insufficient-grounding detector
    # ──────────────────────────────────────────────────────────────────────────

    # Phrases that the LLM or execution services emit when they cannot produce
    # reliable grounded output.  Case-insensitive substring match.
    _INSUFFICIENT_GROUNDING_PHRASES: tuple[str, ...] = (
        "not enough grounded evidence",
        "insufficient grounded evidence",
        "no reliable legal provisions",
        "could not be confidently identified",
        "not grounded in",
        "unable to identify applicable legal",
        "no applicable legal provisions were identified",
        "no sufficient legal grounding",
        "cannot provide a grounded legal analysis",
        "insufficient evidence to support",
    )

    @classmethod
    def _answer_indicates_insufficient_grounding(cls, answer: str) -> bool:
        """Return True when the answer text itself signals that the LLM could not
        produce a reliably grounded response, regardless of how many source
        records are technically present in the metadata.
        """
        if not answer:
            return False
        lower = answer.lower()
        return any(phrase in lower for phrase in cls._INSUFFICIENT_GROUNDING_PHRASES)

    # ──────────────────────────────────────────────────────────────────────────
    # Source / citation normalization
    # ──────────────────────────────────────────────────────────────────────────

    @staticmethod
    def _normalize_sources(raw: Any) -> List[Any]:
        """Return a deduplicated list of source entries; never raises."""
        if not isinstance(raw, list):
            return []
        seen: set[str] = set()
        out: List[Any] = []
        for item in raw:
            if isinstance(item, dict):
                key = str(item.get("document_id") or item.get("chunk_id") or item.get("text") or item)
            else:
                key = str(item or "")
            if key and key not in seen:
                seen.add(key)
                out.append(item)
        return out

    @staticmethod
    def _normalize_citations(raw: Any) -> List[Any]:
        """Return a deduplicated list of citation entries; never raises."""
        if not isinstance(raw, list):
            return []
        seen: set[str] = set()
        out: List[Any] = []
        for item in raw:
            if isinstance(item, dict):
                key = str(item.get("id") or item.get("label") or item.get("text") or item)
            else:
                key = str(item or "")
            if key and key not in seen:
                seen.add(key)
                out.append(item)
        return out


__all__ = ["CopilotResponseAssemblyService"]
