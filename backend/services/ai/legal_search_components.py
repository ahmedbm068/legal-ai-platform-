"""
legal_search_components.py — R5 / R5b refactor

Components that make Legal Search Mode jurisdiction-aware, corpus-restricted,
and capable of lawyer-grade law→facts→assessment reasoning.

  JurisdictionRouter           – resolves jurisdiction; never guesses when case is bound
  LegalDomainClassifier        – multi-signal classifier: civil/succession/PIL with confidence
  LegalApplicabilityMapper     – maps each legal source to case facts (direct/partial/weak/none)
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
    Multi-signal classifier for legal domain (civil / succession / PIL).

    Scoring tiers:
      Tier 1 (strong, weight 3) — unambiguous multi-word phrases unique to a domain
      Tier 2 (medium, weight 2) — single domain-specific nouns/verbs
      Tier 3 (weak, weight 1)   — words that lean toward a domain but appear elsewhere

    Negative rules prevent cross-contamination:
      - Strong succession signals suppress civil score → 0
      - Strong PIL signals reduce civil score by 50 %

    Case metadata signals (matter_type / task_type) add +4 to the matching domain.

    Confidence:
      high   — top_score ≥ 4 AND top_score ≥ 2 × second_score
      medium — top_score ≥ 2 OR case metadata contributed
      low    — otherwise

    Returns a dict compatible with the legacy _infer_case_topic() shape plus
    ``confidence``, ``reason``, and ``needs_counsel_domain_verification``.
    """

    # domain → code-family mapping
    _DOMAIN_TO_FAMILY: Dict[str, str] = {
        "civil": "code_civil",
        "succession": "code_succession",
        "private_international_law": "code_international_prive",
    }

    # Tier weights
    _T1 = 3  # strong / phrase
    _T2 = 2  # medium / single word
    _T3 = 1  # weak / contextual

    _MARKERS: Dict[str, List[tuple]] = {
        "code_civil": [
            # Tier 1
            ("breach of contract", _T1),
            ("service level agreement", _T1),
            ("contractual obligation", _T1),
            ("civil liability", _T1),
            ("obligation contractuelle", _T1),
            ("procedure civile", _T1),
            ("procedure commerciale", _T1),
            ("code des obligations", _T1),
            # Tier 2
            ("contrat", _T2), ("contract", _T2), ("obligation", _T2),
            ("responsabilite", _T2), ("liability", _T2), ("dommage", _T2),
            ("damages", _T2), ("vente", _T2), ("bail", _T2),
            ("termination", _T2), ("invoice", _T2), ("payment", _T2),
            ("sla", _T2), ("indemnite", _T2), ("indemnity", _T2),
            # Tier 3
            ("breach", _T3), ("property", _T3), ("propriete", _T3),
            ("assignation", _T3), ("penalty", _T3),
        ],
        "code_succession": [
            # Tier 1
            ("reserved share", _T1), ("forced heirship", _T1),
            ("succession ab intestat", _T1), ("statut personnel", _T1),
            ("partage de succession", _T1),
            # Tier 2
            ("succession", _T2), ("inheritance", _T2), ("heritage", _T2),
            ("heritier", _T2), ("heir", _T2), ("testament", _T2),
            ("estate", _T2), ("partage", _T2), ("mirath", _T2),
            ("surviving spouse", _T2), ("legataire", _T2), ("legator", _T2),
            # Tier 3
            ("death", _T3), ("deceased", _T3), ("decede", _T3),
            ("will", _T3), ("probate", _T3), ("reserve", _T3),
        ],
        "code_international_prive": [
            # Tier 1
            ("conflit de lois", _T1), ("private international law", _T1),
            ("droit international prive", _T1), ("conflict of laws", _T1),
            ("applicable law", _T1), ("recognition of foreign", _T1),
            ("international jurisdiction", _T1),
            # Tier 2
            ("exequatur", _T2), ("foreign judgment", _T2),
            ("competence internationale", _T2), ("foreign party", _T2),
            ("cross-border", _T2), ("domicile abroad", _T2),
            ("choice of law", _T2), ("forum", _T2),
            # Tier 3
            ("international", _T3), ("foreign", _T3), ("abroad", _T3),
            ("transnational", _T3),
        ],
    }

    # Case matter_type / task_type → domain boost
    _MATTER_TYPE_MAP: Dict[str, str] = {
        "civil": "code_civil", "civil_liability": "code_civil",
        "contract": "code_civil", "contract_dispute": "code_civil",
        "commercial": "code_civil",
        "inheritance": "code_succession", "succession": "code_succession",
        "estate": "code_succession", "family": "code_succession",
        "international": "code_international_prive",
        "cross_border": "code_international_prive",
        "private_international_law": "code_international_prive",
    }

    # ── helpers ──────────────────────────────────────────────────────────────

    def _score_corpus(self, corpus: str, code_scope: List[str]) -> Dict[str, float]:
        scores: Dict[str, float] = {cf: 0.0 for cf in code_scope}
        for cf in code_scope:
            for phrase, weight in self._MARKERS.get(cf, []):
                if phrase in corpus:
                    scores[cf] += weight
        return scores

    def _apply_negative_rules(self, scores: Dict[str, float]) -> Dict[str, float]:
        succ = scores.get("code_succession", 0.0)
        pil = scores.get("code_international_prive", 0.0)
        civil = scores.get("code_civil", 0.0)
        # Strong succession signals suppress civil
        if succ >= 4 and succ > civil:
            scores["code_civil"] = 0.0
        # Strong PIL signals reduce civil by half
        if pil >= 4 and pil > civil:
            scores["code_civil"] = civil * 0.5
        return scores

    # ── public API ────────────────────────────────────────────────────────────

    def classify(
        self,
        *,
        query: str,
        case_focus_terms: List[str],
        internal_results: List[Dict[str, Any]],
        code_scope: List[str],
        country: str = "tunisia",
        case: Any = None,  # Optional[Case] — avoid hard import
    ) -> Dict[str, Any]:
        # Build text corpus
        text_parts = [query.lower(), " ".join(t.lower() for t in case_focus_terms)]
        for item in internal_results[:6]:
            text_parts.append(
                " ".join([
                    str(item.get("filename") or ""),
                    str(item.get("title") or ""),
                    str(item.get("snippet") or ""),
                ]).lower()
            )
        corpus = " ".join(text_parts)

        scores = self._score_corpus(corpus, code_scope)
        scores = self._apply_negative_rules(scores)

        # Case metadata boost
        meta_contributed = False
        if case is not None:
            raw_matter = str(
                getattr(case, "matter_type", None)
                or getattr(case, "task_type", None)
                or ""
            ).lower().replace(" ", "_")
            cf_boost = self._MATTER_TYPE_MAP.get(raw_matter)
            if cf_boost and cf_boost in scores:
                scores[cf_boost] = scores.get(cf_boost, 0.0) + 4.0
                meta_contributed = True

        # Rank
        ranked_pairs = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        ranked_cfs = [cf for cf, s in ranked_pairs if s > 0]
        selected = ranked_cfs[:2] if ranked_cfs else list(code_scope)
        primary = selected[0] if selected else (code_scope[0] if code_scope else "code_civil")

        top_score = scores.get(primary, 0.0)
        second_score = ranked_pairs[1][1] if len(ranked_pairs) > 1 else 0.0

        # Confidence
        if top_score >= 4 and top_score >= 2 * max(second_score, 0.5):
            confidence = "high"
            reason = f"Strong signal: {primary} ({top_score:.0f} pts)"
        elif top_score >= 2 or meta_contributed:
            confidence = "medium"
            reason = (
                f"Moderate signal: {primary} ({top_score:.0f} pts)"
                + (" + case metadata" if meta_contributed else "")
            )
        else:
            confidence = "low"
            reason = (
                f"Weak signal: top score {top_score:.0f} pts. "
                "Domain classification is uncertain — counsel should verify."
            )

        domain = next(
            (d for d, cf in self._DOMAIN_TO_FAMILY.items() if cf == primary),
            "civil",
        )
        needs_verification = confidence == "low"

        logger.info(
            "[legal_search] legal_domain_decision domain=%s confidence=%s reason=%r code_families=%s",
            domain, confidence, reason, selected,
        )

        return {
            "country": country,
            "domain": domain,
            "confidence": confidence,
            "reason": reason,
            "topic": _CODE_SCOPE_LABELS.get(primary, "General Civil Matter"),
            "code_families": selected,
            "scope": code_scope,
            "signals": ranked_cfs,
            "needs_counsel_domain_verification": needs_verification,
        }


# ──────────────────────────────────────────────────────────────────────────────
# LegalApplicabilityMapper
# ──────────────────────────────────────────────────────────────────────────────

class LegalApplicabilityMapper:
    """
    Heuristic law-to-facts mapper.

    For each legal source, produces:
      source_reference     – article / title reference label
      rule_summary         – first 140 chars of the snippet (plain-language rule)
      matching_case_facts  – focus terms that appear in the source text
      missing_facts        – top query tokens absent from the source text
      assessment           – short cautious sentence about applicability
      applicability        – "direct" | "partial" | "weak" | "none"

    Applicability thresholds (heuristic):
      direct  — kw_overlap ≥ 0.28 AND (focus_hits ≥ 2 OR source is official)
      partial — kw_overlap ≥ 0.12 OR focus_hits ≥ 1
      weak    — kw_overlap ≥ 0.04
      none    — below all thresholds (excluded from legal reasoning)
    """

    _ASSESSMENT_TEMPLATES: Dict[str, str] = {
        "direct": (
            "The cited provision appears directly applicable to the identified issue. "
            "Verify article wording and full factual record before reliance."
        ),
        "partial": (
            "The cited provision is relevant but its applicability depends on "
            "facts not yet confirmed. Counsel must verify before drawing conclusions."
        ),
        "weak": (
            "The cited provision has only a generic connection to the query. "
            "It should not be relied upon without identifying a stronger legal basis."
        ),
        "none": (
            "The cited provision does not appear applicable to the current matter."
        ),
    }

    # ── helpers ──────────────────────────────────────────────────────────────

    @staticmethod
    def _kw_overlap(query: str, text: str) -> float:
        q_tokens = set(re.findall(r"\w{3,}", query.lower()))
        t_tokens = set(re.findall(r"\w{3,}", text.lower()))
        return len(q_tokens & t_tokens) / max(len(q_tokens), 1)

    @staticmethod
    def _focus_hits(focus_terms: List[str], text: str) -> float:
        low = text.lower()
        return sum(1.0 for t in focus_terms[:12] if len(t) >= 4 and t.lower() in low)

    @staticmethod
    def _matching_facts(focus_terms: List[str], text: str) -> List[str]:
        low = text.lower()
        return [t for t in focus_terms[:12] if len(t) >= 4 and t.lower() in low]

    @staticmethod
    def _missing_facts(query: str, text: str, max_items: int = 5) -> List[str]:
        q_tokens = [t for t in re.findall(r"\w{4,}", query.lower()) if len(t) >= 4]
        t_tokens = set(re.findall(r"\w{3,}", text.lower()))
        return [t for t in q_tokens if t not in t_tokens][:max_items]

    # ── public API ────────────────────────────────────────────────────────────

    def map(
        self,
        *,
        query: str,
        legal_sources: List[Dict[str, Any]],
        case_focus_terms: List[str],
    ) -> List[Dict[str, Any]]:
        """
        Returns a list of applicability dicts, one per source.
        Sources with applicability=="none" are included so callers know why
        a source was excluded.
        """
        results: List[Dict[str, Any]] = []
        for src in legal_sources[:10]:
            results.append(
                self._assess_one(
                    source=src,
                    query=query,
                    case_focus_terms=case_focus_terms,
                )
            )
        direct_count = sum(1 for r in results if r["applicability"] == "direct")
        partial_count = sum(1 for r in results if r["applicability"] == "partial")
        logger.info(
            "[legal_search] applicability_mapping_count=%d direct=%d partial=%d",
            len(results), direct_count, partial_count,
        )
        return results

    def _assess_one(
        self,
        *,
        source: Dict[str, Any],
        query: str,
        case_focus_terms: List[str],
    ) -> Dict[str, Any]:
        text = " ".join([
            str(source.get("title") or ""),
            str(source.get("snippet") or ""),
            str(source.get("reference") or ""),
        ])
        is_official = str(source.get("source_type") or "") == "official"
        kw = self._kw_overlap(query, text)
        fb = self._focus_hits(case_focus_terms, text)

        if kw >= 0.28 and (fb >= 2.0 or is_official):
            applicability = "direct"
        elif kw >= 0.12 or fb >= 1.0:
            applicability = "partial"
        elif kw >= 0.04:
            applicability = "weak"
        else:
            applicability = "none"

        reference = str(source.get("reference") or source.get("title") or "Legal source").strip()
        snippet = str(source.get("snippet") or "").strip()
        rule_summary = snippet[:140].rstrip() + ("…" if len(snippet) > 140 else "")

        return {
            "source_reference": reference,
            "rule_summary": rule_summary or reference,
            "matching_case_facts": self._matching_facts(case_focus_terms, text),
            "missing_facts": self._missing_facts(query, text),
            "assessment": self._ASSESSMENT_TEMPLATES[applicability],
            "applicability": applicability,
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
