"""
legal_search_components.py — R5 refactor

Five lightweight components that make Legal Search Mode jurisdiction-aware
and corpus-restricted without changing the public API or frontend schema.

  JurisdictionRouter           – resolves jurisdiction; never guesses when case is bound
  LegalDomainClassifier        – classifies query into civil/succession/PIL/unknown
  LegalSourceRelevanceFilter   – removes low-overlap sources; sets missing-authority note
  RestrictedLegalCorpusRetriever – policy: disallow broad web fallback when case is bound
  LegalSearchResponseBuilder   – resolves grounding type label
"""
from __future__ import annotations

import logging
import re
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────────────────
# Shared constants
# ──────────────────────────────────────────────────────────────────────────────

MISSING_AUTHORITY_NOTE = (
    "No applicable legal provisions were identified in the selected jurisdiction/domain "
    "corpus. Counsel must verify the governing legal authority before reliance."
)

_CODE_SCOPE_LABELS: Dict[str, str] = {
    "code_civil": "Code Civil",
    "code_succession": "Code de Succession",
    "code_international_prive": "Code International Prive",
}

_DEFAULT_CODE_SCOPE = ["code_civil", "code_succession", "code_international_prive"]


# ──────────────────────────────────────────────────────────────────────────────
# JurisdictionRouter
# ──────────────────────────────────────────────────────────────────────────────

class JurisdictionRouter:
    """
    Resolves the search jurisdiction.

    Rules
    ─────
    • case_id present AND case.jurisdiction_country is set and supported
      → use that country, resolution="case_pinned"
    • case_id present BUT jurisdiction absent/unsupported
      → return (None, "case_jurisdiction_missing")  — caller must short-circuit
    • case_id absent
      → infer from message + history; fallback to "tunisia"
    """

    SUPPORTED: frozenset[str] = frozenset({"tunisia", "germany"})

    def resolve(
        self,
        *,
        case: Any,                          # Optional[Case] — avoid hard import
        case_is_bound: bool,                # True when caller provided case_id
        message: str,
        conversation_history: Optional[List[Dict[str, Any]]],
        normalize_fn: Callable[[str], str], # jurisdiction_context_service.normalize_country
    ) -> Tuple[Optional[str], str]:
        """
        Returns (country_or_None, resolution_method).

        resolution_method: "case_pinned" | "case_jurisdiction_missing"
                         | "inferred" | "fallback_tunisia"
        """
        if case is not None:
            raw = str(getattr(case, "jurisdiction_country", None) or "")
            normalized = normalize_fn(raw)
            if normalized in self.SUPPORTED:
                logger.info(
                    "[legal_search] jurisdiction_selected=%s resolution=case_pinned case_id=%s",
                    normalized,
                    getattr(case, "id", None),
                )
                return normalized, "case_pinned"

        if case_is_bound:
            # Case was requested but jurisdiction is absent or unsupported.
            logger.warning(
                "[legal_search] jurisdiction_selected=None resolution=case_jurisdiction_missing"
                " case_id=%s",
                getattr(case, "id", None) if case else None,
            )
            return None, "case_jurisdiction_missing"

        # No case in scope — infer from free-text.
        corpus = " ".join(
            [message or ""]
            + [str(item.get("content") or "") for item in (conversation_history or [])]
        ).lower()

        _german: frozenset[str] = frozenset(
            {"germany", "deutschland", "german", "grundgesetz", "bgb", "stgb", "gesetz", "§"}
        )
        _tunisian: frozenset[str] = frozenset(
            {"tunisia", "tunisie", "tunisian", "\u062a\u0648\u0646\u0633",
             "code des obligations", "code des contrats"}
        )

        if any(t in corpus for t in _german):
            logger.info("[legal_search] jurisdiction_selected=germany resolution=inferred")
            return "germany", "inferred"
        if any(t in corpus for t in _tunisian):
            logger.info("[legal_search] jurisdiction_selected=tunisia resolution=inferred")
            return "tunisia", "inferred"

        logger.info("[legal_search] jurisdiction_selected=tunisia resolution=fallback_tunisia")
        return "tunisia", "fallback_tunisia"


# ──────────────────────────────────────────────────────────────────────────────
# LegalDomainClassifier
# ──────────────────────────────────────────────────────────────────────────────

class LegalDomainClassifier:
    """
    Classifies the query into a code-family (civil / succession / PIL).

    Returns a dict whose shape is identical to the legacy _infer_case_topic()
    output so the rest of the service can use it unchanged.
    """

    _DOMAIN_TO_FAMILY: Dict[str, str] = {
        "civil": "code_civil",
        "succession": "code_succession",
        "private_international_law": "code_international_prive",
    }

    _FAMILY_MARKERS: Dict[str, List[str]] = {
        "code_civil": [
            "contrat", "obligation", "responsabilite", "dommage", "vente",
            "bail", "property", "propriete", "procedure civile",
            "procedure commerciale", "breach", "contract", "liability",
            "damages", "termination", "sla", "service level", "invoice",
            "payment",
        ],
        "code_succession": [
            "succession", "inheritance", "heritage", "heritier",
            "testament", "estate", "partage", "mirath", "statut personnel",
        ],
        "code_international_prive": [
            "international prive", "droit international prive",
            "conflit de lois", "competence internationale",
            "recognition of foreign", "foreign judgment",
            "exequatur", "private international",
        ],
    }

    def classify(
        self,
        *,
        query: str,
        case_focus_terms: List[str],
        internal_results: List[Dict[str, Any]],
        code_scope: List[str],
        country: str = "tunisia",
    ) -> Dict[str, Any]:
        # Build text corpus from query + focus terms + top internal chunks.
        text_parts = [query, " ".join(case_focus_terms)]
        for item in internal_results[:6]:
            text_parts.append(
                " ".join([
                    str(item.get("filename") or ""),
                    str(item.get("title") or ""),
                    str(item.get("snippet") or ""),
                ])
            )
        corpus = " ".join(text_parts).lower()

        scores: Dict[str, int] = {cf: 0 for cf in code_scope}
        for cf in code_scope:
            for marker in self._FAMILY_MARKERS.get(cf, []):
                if marker.lower() in corpus:
                    scores[cf] += 1

        ranked = [
            cf for cf, s in sorted(scores.items(), key=lambda x: x[1], reverse=True)
            if s > 0
        ]
        selected = ranked[:2] if ranked else list(code_scope)
        primary = selected[0] if selected else (code_scope[0] if code_scope else "code_civil")

        domain = next(
            (d for d, cf in self._DOMAIN_TO_FAMILY.items() if cf == primary),
            "civil",
        )
        logger.info(
            "[legal_search] legal_domain_selected=%s code_families=%s",
            domain, selected,
        )

        return {
            "country": country,
            "domain": domain,
            "topic": _CODE_SCOPE_LABELS.get(primary, "General Civil Matter"),
            "code_families": selected,
            "scope": code_scope,
            "signals": ranked,
        }


# ──────────────────────────────────────────────────────────────────────────────
# LegalSourceRelevanceFilter
# ──────────────────────────────────────────────────────────────────────────────

class LegalSourceRelevanceFilter:
    """
    Post-retrieval filter: removes sources with weak keyword overlap.

    A source is **kept** when ANY of these is true:
      • ≥8 % of query tokens appear in the source text  (kw_overlap ≥ MIN_KW)
      • ≥1 case focus term (len≥4) appears in the source (focus_hits ≥ MIN_FOCUS)
      • the source's article reference appears verbatim in the answer text

    If no sources survive → exposes ``MISSING_AUTHORITY_NOTE``.
    """

    MIN_KW: float = 0.08
    MIN_FOCUS: float = 1.0
    MISSING_AUTHORITY_NOTE: str = MISSING_AUTHORITY_NOTE

    # ── helpers ──────────────────────────────────────────────────────────────

    @staticmethod
    def _kw_overlap(query: str, text: str) -> float:
        q_tokens = set(re.findall(r"\w+", query.lower()))
        t_tokens = set(re.findall(r"\w+", text.lower()))
        return len(q_tokens & t_tokens) / max(len(q_tokens), 1)

    @staticmethod
    def _focus_hits(focus_terms: List[str], text: str) -> float:
        low = text.lower()
        return sum(1.2 for t in focus_terms[:12] if len(t) >= 4 and t.lower() in low)

    # ── public API ────────────────────────────────────────────────────────────

    def filter(
        self,
        *,
        query: str,
        sources: List[Dict[str, Any]],
        answer_text: str = "",
        case_focus_terms: Optional[List[str]] = None,
    ) -> Tuple[List[Dict[str, Any]], Optional[str]]:
        """
        Returns ``(kept_sources, legal_sources_note_or_None)``.
        """
        raw_count = len(sources)
        if not sources:
            logger.info(
                "[legal_search] raw_legal_sources_count=0 relevant_legal_sources_count=0"
                " legal_sources_note_present=True",
            )
            return [], self.MISSING_AUTHORITY_NOTE

        focus_terms: List[str] = case_focus_terms or []
        low_answer = answer_text.lower()
        kept: List[Dict[str, Any]] = []

        for src in sources:
            text = " ".join([
                str(src.get("title") or ""),
                str(src.get("snippet") or ""),
                str(src.get("reference") or ""),
            ])
            kw = self._kw_overlap(query, text)
            fb = self._focus_hits(focus_terms, text)
            ref = str(src.get("reference") or "").strip().lower()
            ref_in_answer = bool(ref and low_answer and ref in low_answer)

            if kw >= self.MIN_KW or fb >= self.MIN_FOCUS or ref_in_answer:
                kept.append(src)

        note: Optional[str] = None if kept else self.MISSING_AUTHORITY_NOTE
        logger.info(
            "[legal_search] raw_legal_sources_count=%d relevant_legal_sources_count=%d"
            " legal_sources_note_present=%s",
            raw_count, len(kept), str(not bool(kept)),
        )
        return kept, note


# ──────────────────────────────────────────────────────────────────────────────
# RestrictedLegalCorpusRetriever
# ──────────────────────────────────────────────────────────────────────────────

class RestrictedLegalCorpusRetriever:
    """
    Policy helper: decides whether an unrestricted broad-web fallback search
    is allowed for the current request.

    Rule: when a case is bound (``case_bound=True``) the broad unrestricted
    fallback is **disabled** — only jurisdiction-official domains are queried.
    """

    def should_allow_broad_fallback(self, *, case_bound: bool) -> bool:
        allowed = not case_bound
        logger.info(
            "[legal_search] corpus_filter_applied=%s case_bound=%s broad_fallback_allowed=%s",
            str(case_bound), str(case_bound), str(allowed),
        )
        return allowed

    def max_external_queries(self, *, case_bound: bool) -> int:
        """Fewer external queries when case is bound to reduce noise."""
        return 3 if case_bound else 5


# ──────────────────────────────────────────────────────────────────────────────
# LegalSearchResponseBuilder
# ──────────────────────────────────────────────────────────────────────────────

class LegalSearchResponseBuilder:
    """
    Resolves the grounding-type label used in trust/confidence displays.

    Never returns "Legal-grounded" when a legal_sources_note is present
    (i.e. when no reliable provisions were found).
    """

    MISSING_AUTHORITY_NOTE: str = MISSING_AUTHORITY_NOTE

    @staticmethod
    def resolve_grounding_type(
        *,
        legal_sources: List[Dict[str, Any]],
        legal_sources_note: Optional[str],
    ) -> str:
        if legal_sources_note:
            return "Partial"
        if not legal_sources:
            return "Not grounded"
        if any(str(s.get("source_type")) == "official" for s in legal_sources):
            return "Legal-grounded"
        return "Partial"
