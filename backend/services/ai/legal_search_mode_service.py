from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from sqlalchemy.orm import Session

from backend.core.config import settings
from backend.services.cache_service import cache_service
from backend.models.case import Case
from backend.models.document import Document
from backend.services.ai.agents.case_reasoning_agent import case_reasoning_agent
from backend.services.ai.agents.prompt_optimizer_agent import prompt_optimizer_agent
from backend.services.ai.external_research_service import external_research_service
from backend.services.ai.jurisdiction_context_service import jurisdiction_context_service
from backend.services.ai.llm_gateway import llm_gateway
from backend.services.ai.reranker_service import reranker_service
from backend.services.ai.legal_search_components import (
    JurisdictionRouter,
    LegalDomainClassifier,
    LegalApplicabilityMapper,
    LegalSourceRelevanceFilter,
    RestrictedLegalCorpusRetriever,
    LegalSearchResponseBuilder,
)

_logger = logging.getLogger(__name__)


class LegalSearchModeService:
    SUPPORTED_COUNTRIES = {"tunisia", "germany"}
    DEFAULT_CODE_SCOPE = ["code_civil", "code_succession", "code_international_prive"]
    DEFAULT_RESPONSE_SECTION_ORDER = [
        "matter_understood",
        "confirmed_facts",
        "legal_issue",
        "relevant_legal_basis",
        "rule_summary",
        "application_to_known_facts",
        "missing_facts_uncertainty",
        "counter_analysis",
        "practical_next_steps",
        "lawyer_review_note",
    ]
    LAWYER_REVIEW_NOTE = (
        "This is preliminary legal assistance for professional review; "
        "the final legal judgment belongs to the lawyer in charge of the matter."
    )
    CODE_SCOPE_ALIASES = {
        "codecivil": "code_civil",
        "civil": "code_civil",
        "procedure_civile": "code_civil",
        "procedure_civile_commerciale": "code_civil",
        "code_succession": "code_succession",
        "succession": "code_succession",
        "inheritance": "code_succession",
        "code_statut_personnel": "code_succession",
        "statut_personnel": "code_succession",
        "code_international_prive": "code_international_prive",
        "international_prive": "code_international_prive",
        "droit_international_prive": "code_international_prive",
    }
    CODE_SCOPE_LABELS = {
        "code_civil": "Code Civil",
        "code_succession": "Code de Succession",
        "code_international_prive": "Code International Prive",
    }
    ALLOWED_ROLES = {"admin", "lawyer", "assistant", "client"}
    OFFICIAL_DOMAINS = {
        "tunisia": {"legislation.tn", "iort.gov.tn", "justice.gov.tn", "pm.gov.tn", "wipo.int", "arp.tn"},
        "germany": {
            "gesetze-im-internet.de",
            "bundestag.de",
            "bverfg.de",
            "bundesverfassungsgericht.de",
            "bundesgerichtshof.de",
            "bmj.de",
            "justiz.de",
        },
    }
    JURISPRUDENCE_DOMAINS = {
        "tunisia": {"courdecassation.tn", "tribunaladministratif.tn"},
        "germany": {"openjur.de", "juris.bundesgerichtshof.de", "bverwg.de", "bverfg.de", "bundesgerichtshof.de"},
    }
    COUNTRY_DISPLAY = {"tunisia": "Tunisia", "germany": "Germany"}
    TRANSLATION_TARGETS = {"tunisia": ["ar", "fr"], "germany": ["de"]}
    LOCAL_LEGAL_CODES_CORPUS_PATH = Path(__file__).resolve().parent / "data" / "legal_codes_corpus.json"
    LOCAL_CONSTITUTION_CORPUS_PATH = Path(__file__).resolve().parent / "data" / "constitution_corpus.json"
    _local_legal_codes_corpus_cache: Dict[str, List[Dict[str, Any]]] | None = None

    def __init__(self) -> None:
        self.client = llm_gateway.create_client()
        self.model = llm_gateway.default_model
        self.jurisdiction_router = JurisdictionRouter()
        self.domain_classifier = LegalDomainClassifier()
        self.applicability_mapper = LegalApplicabilityMapper()
        self.relevance_filter = LegalSourceRelevanceFilter()
        self.corpus_retriever = RestrictedLegalCorpusRetriever()
        self.response_builder = LegalSearchResponseBuilder()

    def run(
        self,
        *,
        db: Session,
        tenant_id: int,
        user_role: str,
        message: str,
        top_k: int,
        case_id: Optional[int],
        document_id: Optional[int],
        conversation_history: Optional[List[Dict[str, Any]]] = None,
        intent: Optional[str] = None,
        target_type: Optional[str] = None,
        target_id: Optional[int] = None,
        retrieval_agent=None,
        multilingual_output: bool = False,
        code_scope: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        role = self._normalize_role(user_role)
        if role not in self.ALLOWED_ROLES:
            return self._denied_response(role)

        resolved_document = self._resolve_document_for_context(db=db, tenant_id=tenant_id, document_id=document_id)
        if document_id is not None and resolved_document is None:
            return self._scope_failure_response(
                kind="document",
                country=self._infer_country_from_context(message=message, conversation_history=conversation_history),
            )

        effective_case_id = case_id or (resolved_document.case_id if resolved_document else None)
        resolved_case = self._resolve_case_for_context(db=db, tenant_id=tenant_id, case_id=effective_case_id)
        if case_id is not None and resolved_case is None:
            return self._scope_failure_response(
                kind="case",
                country=self._infer_country_from_context(message=message, conversation_history=conversation_history),
            )

        case_bound = (case_id is not None)
        country, _jurisdiction_resolution = self.jurisdiction_router.resolve(
            case=resolved_case,
            case_is_bound=case_bound,
            message=message,
            conversation_history=conversation_history,
            normalize_fn=jurisdiction_context_service.normalize_country,
        )
        if country is None:
            return self._jurisdiction_missing_response(case_id=case_id)
        detected_user_language = self._detect_user_language(message)
        localized_lawyer_review_note = self._localized_lawyer_review_note(detected_user_language)
        jurisdiction = jurisdiction_context_service.get_response_context(country)
        optimized_query = self._optimize_query(
            message=message,
            intent=intent,
            target_type=target_type,
            target_id=target_id,
        )
        normalized_code_scope = self._normalize_code_scope(code_scope)
        cache_key = self._build_cache_key(
            tenant_id=tenant_id,
            country=country,
            query=optimized_query,
            case_id=resolved_case.id if resolved_case else None,
            document_id=resolved_document.id if resolved_document else None,
            code_scope=normalized_code_scope,
        )
        cached_payload = cache_service.get_json(cache_key)
        if isinstance(cached_payload, dict):
            return self._with_cache_metadata(cached_payload, key=cache_key, hit=True)

        internal_results = self._retrieve_internal_context(
            retrieval_agent=retrieval_agent,
            db=db,
            tenant_id=tenant_id,
            query=optimized_query,
            case_id=resolved_case.id if resolved_case else None,
            document_id=resolved_document.id if resolved_document else None,
            top_k=top_k,
        )
        case_focus_terms = self._extract_case_focus_terms(query=optimized_query, internal_results=internal_results)
        case_topic = self.domain_classifier.classify(
            query=optimized_query,
            case_focus_terms=case_focus_terms,
            internal_results=internal_results,
            code_scope=normalized_code_scope,
            country=country,
            case=resolved_case,
        )
        legal_sources_raw = self._retrieve_jurisdiction_sources(
            country=country,
            query=optimized_query,
            case_focus_terms=case_focus_terms,
            top_k=max(top_k, 5),
            case_topic=case_topic,
            case_bound=case_bound,
        )
        legal_sources, legal_sources_note = self.relevance_filter.filter(
            query=optimized_query,
            sources=legal_sources_raw,
            answer_text="",
            case_focus_terms=case_focus_terms,
        )
        applicability_mappings = self.applicability_mapper.map(
            query=optimized_query,
            legal_sources=legal_sources,
            case_focus_terms=case_focus_terms,
        )
        local_code_results = sum(1 for item in legal_sources_raw if item.get("source_origin") == "local_code")
        external_web_results = sum(1 for item in legal_sources_raw if item.get("source_origin") == "external_web")
        scope = self._scope(
            case_id=resolved_case.id if resolved_case else None,
            document_id=resolved_document.id if resolved_document else None,
        )
        execution_trace = [
            {
                "stage": "legal_search_scope_resolution",
                "country": country,
                "jurisdiction_resolution": _jurisdiction_resolution,
                "case_bound": case_bound,
                "scope": scope,
                "case_id": resolved_case.id if resolved_case else None,
                "document_id": resolved_document.id if resolved_document else None,
            },
            {
                "stage": "legal_search_retrieval",
                "internal_results": len(internal_results),
                "local_code_results": local_code_results,
                "external_web_results": external_web_results,
                "total_legal_results": len(legal_sources_raw),
                "case_focus_terms": case_focus_terms[:8],
                "case_topic": case_topic,
            },
            {
                "stage": "legal_source_relevance_filter",
                "raw_legal_sources_count": len(legal_sources_raw),
                "relevant_legal_sources_count": len(legal_sources),
                "legal_sources_note_present": bool(legal_sources_note),
            },
            {
                "stage": "applicability_mapping",
                "applicability_mapping_count": len(applicability_mappings),
                "direct_count": sum(1 for m in applicability_mappings if m.get("applicability") == "direct"),
                "partial_count": sum(1 for m in applicability_mappings if m.get("applicability") == "partial"),
                "weak_count": sum(1 for m in applicability_mappings if m.get("applicability") == "weak"),
                "domain_confidence": (case_topic or {}).get("confidence", "unknown"),
                "domain_reason": (case_topic or {}).get("reason", ""),
            },
        ]

        if legal_sources:
            answer_body = self._generate_grounded_answer(
                country=country,
                query=optimized_query,
                user_language=detected_user_language,
                legal_sources=legal_sources,
                internal_results=internal_results,
                include_english_summary=multilingual_output,
                case_topic=case_topic,
                applicability_mappings=applicability_mappings,
            )
            confidence, confidence_reason = self._compute_legal_match_confidence(
                legal_sources=legal_sources,
                applicability_mappings=applicability_mappings,
                legal_sources_note=legal_sources_note,
            )
            verification_status = self._verification_status_from_sources(legal_sources)
            payload = {
                "answer": self._format_legal_search_output(
                    country=self.COUNTRY_DISPLAY.get(country, country.title()),
                    source_lines=[self._to_source_line(item) for item in legal_sources],
                    answer_body=answer_body,
                    fallback_notice=None,
                    confidence=confidence,
                    verification_status=verification_status,
                    lawyer_review_note=localized_lawyer_review_note,
                    legal_sources_note=legal_sources_note,
                ),
                "used_fallback": False,
                "fallback_reason": None,
                "confidence": confidence,
                "confidence_reason": confidence_reason,
                "scope": scope,
                "sources": self._to_api_sources(legal_sources),
                "citations": self._to_api_citations(legal_sources),
                "execution_trace": execution_trace,
                "jurisdiction": jurisdiction,
                "legal_sources_note": legal_sources_note,
            }
            cache_service.set_json(cache_key, payload, ttl_seconds=settings.LEGAL_SEARCH_CACHE_TTL_SECONDS)
            return self._with_cache_metadata(payload, key=cache_key, hit=False)

        fallback_notice = "No direct legal source found; reasoning based on general legal principles"

        # ── Case-context path: case exists → structured 5-section output ──────
        # Use a fallback_reason that is NOT in the insufficient-evidence trigger set
        # {"no_direct_legal_source", "insufficient_evidence"} so _normalize_trust_state
        # does NOT clobber the answer.
        if resolved_case is not None or bool(internal_results):
            fallback_answer = self._generate_case_context_fallback_answer(
                db=db,
                tenant_id=tenant_id,
                case=resolved_case,
                internal_results=internal_results,
                country=country,
                query=optimized_query,
            )
            effective_fallback_reason = "case_context_no_legal_provisions"
            effective_sources: List[Dict[str, Any]] = []  # case docs are not legal provisions
        else:
            # Truly blank context: let _normalize_trust_state handle the override.
            fallback_answer = self._build_reasoning_fallback(
                db=db,
                tenant_id=tenant_id,
                country=country,
                query=optimized_query,
                case=resolved_case,
            )
            effective_fallback_reason = "no_direct_legal_source"
            effective_sources = self._to_api_sources(internal_results, fallback_score=0.3)

        fallback_answer = self._ensure_default_legal_response_structure(
            answer_body=fallback_answer,
            query=optimized_query,
            legal_sources=[],
            confidence="low",
            verification_status="not_verified_no_direct_source",
            user_language=detected_user_language,
        )
        payload = {
            "answer": self._format_legal_search_output(
                country=self.COUNTRY_DISPLAY.get(country, country.title()),
                source_lines=[],
                answer_body=fallback_answer,
                fallback_notice=fallback_notice,
                confidence="low",
                verification_status="not_verified_no_direct_source",
                lawyer_review_note=localized_lawyer_review_note,
                legal_sources_note=legal_sources_note,
            ),
            "used_fallback": True,
            "fallback_reason": effective_fallback_reason,
            "confidence": "low",
            "confidence_reason": "No relevant legal provisions survived the relevance filter. Case-based reasoning used.",
            "scope": scope,
            "sources": effective_sources,
            "citations": self._to_api_citations(legal_sources),
            "execution_trace": execution_trace,
            "jurisdiction": jurisdiction,
            "legal_sources_note": legal_sources_note,
        }
        cache_service.set_json(cache_key, payload, ttl_seconds=settings.LEGAL_SEARCH_CACHE_TTL_SECONDS)
        return self._with_cache_metadata(payload, key=cache_key, hit=False)

    @staticmethod
    def _normalize_role(value: str | None) -> str:
        return str(value or "").strip().lower() or "assistant"

    @staticmethod
    def _scope(*, case_id: Optional[int], document_id: Optional[int]) -> str:
        if document_id is not None:
            return "document"
        if case_id is not None:
            return "case"
        return "global"

    def _denied_response(self, role: str) -> Dict[str, Any]:
        answer = self._format_legal_search_output(
            country="Unknown",
            source_lines=[],
            answer_body=f"Permission denied for role '{role}'.",
            fallback_notice="Case-scoped legal search is restricted by role policy.",
            confidence="low",
            verification_status="not_verified_access_denied",
            lawyer_review_note=self.LAWYER_REVIEW_NOTE,
        )
        return {
            "answer": answer,
            "used_fallback": True,
            "fallback_reason": "permission_denied",
            "confidence": "low",
            "scope": "global",
            "sources": [],
            "jurisdiction": None,
        }

    def _scope_failure_response(self, *, kind: str, country: str) -> Dict[str, Any]:
        normalized_kind = "document" if kind == "document" else "case"
        answer = self._format_legal_search_output(
            country=self.COUNTRY_DISPLAY.get(country, country.title()),
            source_lines=[],
            answer_body=f"I could not access the requested {normalized_kind} in your current workspace scope.",
            fallback_notice=f"Case-scoped access check failed for the selected {normalized_kind}.",
            confidence="low",
            verification_status=f"not_verified_{normalized_kind}_scope_failure",
            lawyer_review_note=self.LAWYER_REVIEW_NOTE,
        )
        return {
            "answer": answer,
            "used_fallback": True,
            "fallback_reason": f"{normalized_kind}_scope_access_failed",
            "confidence": "low",
            "scope": normalized_kind,
            "sources": [],
            "jurisdiction": jurisdiction_context_service.get_response_context(country),
        }

    def _jurisdiction_missing_response(self, *, case_id: Optional[int]) -> Dict[str, Any]:
        note = (
            "The case record does not specify a supported jurisdiction (Tunisia or Germany). "
            "Please update the case jurisdiction before requesting legal search analysis."
        )
        answer = self._format_legal_search_output(
            country="Unknown",
            source_lines=[],
            answer_body=note,
            fallback_notice="Jurisdiction is required for corpus-restricted legal search.",
            confidence="low",
            verification_status="not_verified_jurisdiction_missing",
            lawyer_review_note=self.LAWYER_REVIEW_NOTE,
            legal_sources_note=LegalSourceRelevanceFilter.MISSING_AUTHORITY_NOTE,
        )
        return {
            "answer": answer,
            "used_fallback": True,
            "fallback_reason": "jurisdiction_missing",
            "confidence": "low",
            "scope": "case" if case_id else "global",
            "sources": [],
            "citations": [],
            "jurisdiction": None,
            "legal_sources_note": LegalSourceRelevanceFilter.MISSING_AUTHORITY_NOTE,
        }

    def _resolve_document_for_context(
        self,
        *,
        db: Session,
        tenant_id: int,
        document_id: Optional[int],
    ) -> Optional[Document]:
        if document_id is None:
            return None
        return (
            db.query(Document)
            .filter(
                Document.id == document_id,
                Document.tenant_id == tenant_id,
            )
            .first()
        )

    def _resolve_case_for_context(
        self,
        *,
        db: Session,
        tenant_id: int,
        case_id: Optional[int],
    ) -> Optional[Case]:
        if case_id is None:
            return None
        return (
            db.query(Case)
            .filter(
                Case.id == case_id,
                Case.tenant_id == tenant_id,
                Case.deleted_at.is_(None),
            )
            .first()
        )

    def _resolve_country(
        self,
        *,
        case: Optional[Case],
        message: str,
        conversation_history: Optional[List[Dict[str, Any]]],
    ) -> str:
        if case and case.jurisdiction_country:
            normalized = jurisdiction_context_service.normalize_country(case.jurisdiction_country)
            if normalized in self.SUPPORTED_COUNTRIES:
                return normalized

        inferred = self._infer_country_from_context(
            message=message,
            conversation_history=conversation_history,
        )
        normalized = jurisdiction_context_service.normalize_country(inferred)
        return normalized if normalized in self.SUPPORTED_COUNTRIES else "tunisia"

    @staticmethod
    def _infer_country_from_context(
        *,
        message: str,
        conversation_history: Optional[List[Dict[str, Any]]],
    ) -> str:
        corpus_parts = [str(message or "")]
        for item in conversation_history or []:
            content = str(item.get("content") or "").strip()
            if content:
                corpus_parts.append(content)
        corpus = " ".join(corpus_parts).lower()

        german_markers = {"germany", "deutschland", "german", "grundgesetz", "bgb", "stgb", "gesetz", "\u00a7"}
        tunisian_markers = {
            "tunisia",
            "tunisie",
            "tunisian",
            "\u062a\u0648\u0646\u0633",
            "\u0627\u0644\u062f\u0633\u062a\u0648\u0631 \u0627\u0644\u062a\u0648\u0646\u0633\u064a",
            "code des obligations",
            "code des contrats",
        }
        if any(token in corpus for token in german_markers):
            return "germany"
        if any(token in corpus for token in tunisian_markers):
            return "tunisia"
        return "tunisia"

    def _optimize_query(
        self,
        *,
        message: str,
        intent: Optional[str],
        target_type: Optional[str],
        target_id: Optional[int],
    ) -> str:
        optimized = prompt_optimizer_agent.optimize_query(
            raw_query=message,
            intent=intent,
            target_type=target_type,
            target_id=target_id,
            allow_llm=False,
        )
        candidate = optimized.payload.get("optimized_query") if optimized.success else ""
        return str(candidate or message).strip()

    @staticmethod
    def _cache_backend() -> str:
        return "redis" if cache_service.available else "memory"

    def _build_cache_key(
        self,
        *,
        tenant_id: int,
        country: str,
        query: str,
        case_id: Optional[int],
        document_id: Optional[int],
        code_scope: Optional[List[str]],
    ) -> str:
        normalized_scope = self._normalize_code_scope(code_scope)
        scope_token = ",".join(sorted(normalized_scope)) if normalized_scope else "default"
        return cache_service.build_key(
            "legal_search",
            f"tenant={tenant_id}",
            f"country={country}",
            f"case={case_id or 'none'}",
            f"document={document_id or 'none'}",
            f"code_scope={scope_token}",
            query.strip().lower(),
        )

    def _with_cache_metadata(self, payload: Dict[str, Any], *, key: str, hit: bool) -> Dict[str, Any]:
        response = dict(payload)
        response["cache"] = {
            "key": key,
            "hit": hit,
            "backend": self._cache_backend(),
        }
        return response

    def _normalize_code_scope(self, code_scope: Optional[List[str]]) -> List[str]:
        if not code_scope:
            return list(self.DEFAULT_CODE_SCOPE)

        normalized: List[str] = []
        for item in code_scope:
            token = re.sub(r"[^a-z0-9_]+", "_", str(item or "").strip().lower()).strip("_")
            if not token:
                continue
            canonical = self.CODE_SCOPE_ALIASES.get(token, token)
            if canonical in self.DEFAULT_CODE_SCOPE and canonical not in normalized:
                normalized.append(canonical)
        return normalized or list(self.DEFAULT_CODE_SCOPE)

    def _retrieve_internal_context(
        self,
        *,
        retrieval_agent,
        db: Session,
        tenant_id: int,
        query: str,
        case_id: Optional[int],
        document_id: Optional[int],
        top_k: int,
    ) -> List[Dict[str, Any]]:
        if retrieval_agent is None:
            return []

        result = retrieval_agent.retrieve(
            db=db,
            tenant_id=tenant_id,
            question=query,
            top_k=max(3, min(top_k, 10)),
            case_id=case_id,
            document_id=document_id,
        )
        if not result.success:
            return []
        return result.payload.get("results") or []

    def _infer_case_topic(
        self,
        *,
        country: str,
        query: str,
        case_focus_terms: List[str],
        internal_results: List[Dict[str, Any]],
        code_scope: List[str],
    ) -> Dict[str, Any]:
        normalized_scope = self._normalize_code_scope(code_scope)
        text_parts: List[str] = [query, " ".join(case_focus_terms)]
        for item in internal_results[:6]:
            text_parts.append(
                " ".join(
                    [
                        str(item.get("filename") or ""),
                        str(item.get("title") or ""),
                        str(item.get("snippet") or ""),
                    ]
                )
            )
        corpus = " ".join(text_parts).lower()

        family_markers = {
            "code_civil": [
                "contrat",
                "obligation",
                "responsabilite",
                "dommage",
                "vente",
                "bail",
                "property",
                "propriete",
                "assignation",
                "procedure civile",
                "procedure commerciale",
            ],
            "code_succession": [
                "succession",
                "inheritance",
                "heritage",
                "heritier",
                "testament",
                "estate",
                "partage",
                "mirath",
            ],
            "code_international_prive": [
                "international prive",
                "droit international prive",
                "conflit de lois",
                "competence internationale",
                "recognition of foreign",
                "foreign judgment",
                "exequatur",
            ],
        }

        scores: Dict[str, int] = {family: 0 for family in normalized_scope}
        for family in normalized_scope:
            for marker in family_markers.get(family, []):
                if marker in corpus:
                    scores[family] += 1

        ranked = [item[0] for item in sorted(scores.items(), key=lambda item: item[1], reverse=True) if item[1] > 0]
        selected = ranked[:2] if ranked else list(normalized_scope)
        primary = selected[0] if selected else normalized_scope[0]

        return {
            "country": country,
            "topic": self.CODE_SCOPE_LABELS.get(primary, "General Civil Matter"),
            "code_families": selected,
            "scope": normalized_scope,
            "signals": ranked,
        }

    def _retrieve_jurisdiction_sources(
        self,
        *,
        country: str,
        query: str,
        case_focus_terms: List[str],
        top_k: int,
        case_topic: Optional[Dict[str, Any]],
        case_bound: bool = False,
    ) -> List[Dict[str, Any]]:
        preferred_code_families = self._normalize_code_scope((case_topic or {}).get("code_families"))
        local_sources = self._retrieve_local_legal_code_sources(
            country=country,
            query=query,
            case_focus_terms=case_focus_terms,
            top_k=max(6, top_k),
            preferred_code_families=preferred_code_families,
        )
        strong_local_hits = sum(1 for item in local_sources if float(item.get("score", 0.0)) >= 44.0)
        if strong_local_hits >= min(4, max(2, top_k // 2)):
            ranked_local = self._rank_sources(query=query, results=local_sources, top_k=max(6, top_k))
            return ranked_local[: max(6, top_k)]

        translated_queries = self._translate_query_variants(country=country, query=query)
        search_queries = self._build_search_queries(
            country=country,
            translated_queries=translated_queries,
            case_topic=case_topic,
        )
        strict_domains = self.OFFICIAL_DOMAINS.get(country, set()) | self.JURISPRUDENCE_DOMAINS.get(country, set())

        gathered: List[Dict[str, Any]] = list(local_sources)
        seen_keys: set[str] = set()
        for item in local_sources:
            key = self._dedupe_key(item)
            if key:
                seen_keys.add(key)

        for item_query in search_queries[:5]:
            research = external_research_service.search(
                query=item_query,
                max_results=max(4, min(top_k + 2, 10)),
                allowed_domains=strict_domains,
            )
            self._collect_external_results(
                country=country,
                query=query,
                case_focus_terms=case_focus_terms,
                research_results=research.get("results") or [],
                seen_keys=seen_keys,
                destination=gathered,
                preferred_code_families=preferred_code_families,
            )

        if not case_bound and len(gathered) < max(4, top_k):
            for item_query in search_queries[:3]:
                research = external_research_service.search(
                    query=item_query,
                    max_results=max(3, min(top_k, 8)),
                )
                self._collect_external_results(
                    country=country,
                    query=query,
                    case_focus_terms=case_focus_terms,
                    research_results=research.get("results") or [],
                    seen_keys=seen_keys,
                    destination=gathered,
                    preferred_code_families=preferred_code_families,
                )

        if not gathered:
            return []
        return self._rank_sources(query=query, results=gathered, top_k=max(6, top_k))[: max(6, top_k)]

    @classmethod
    def _load_local_legal_codes_corpus(cls) -> Dict[str, List[Dict[str, Any]]]:
        if cls._local_legal_codes_corpus_cache is not None:
            return cls._local_legal_codes_corpus_cache

        raw_payload: Dict[str, Any] = {}
        path_candidates = [cls.LOCAL_LEGAL_CODES_CORPUS_PATH, cls.LOCAL_CONSTITUTION_CORPUS_PATH]
        for path in path_candidates:
            if not path.exists():
                continue
            try:
                loaded = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                continue
            if isinstance(loaded, dict):
                raw_payload = loaded
                break

        if not raw_payload:
            cls._local_legal_codes_corpus_cache = {}
            return cls._local_legal_codes_corpus_cache

        normalized_payload: Dict[str, List[Dict[str, Any]]] = {}
        for country_name, items in raw_payload.items():
            normalized_country = jurisdiction_context_service.normalize_country(country_name)
            if normalized_country not in cls.SUPPORTED_COUNTRIES:
                continue
            if not isinstance(items, list):
                continue

            cleaned_items: List[Dict[str, Any]] = []
            for item in items:
                if not isinstance(item, dict):
                    continue
                copy = dict(item)
                joined = " ".join(
                    [
                        str(copy.get("code_family") or ""),
                        str(copy.get("code_name") or ""),
                        str(copy.get("article") or ""),
                        str(copy.get("title") or ""),
                        str(copy.get("summary") or ""),
                        " ".join(str(tag) for tag in (copy.get("tags") or []) if str(tag).strip()),
                    ]
                ).lower()
                family = re.sub(r"[^a-z0-9_]+", "_", str(copy.get("code_family") or "").lower()).strip("_")
                family = cls.CODE_SCOPE_ALIASES.get(family, family)
                if family not in cls.DEFAULT_CODE_SCOPE:
                    if any(token in joined for token in ["international prive", "conflit de lois", "exequatur"]):
                        family = "code_international_prive"
                    elif any(token in joined for token in ["succession", "inheritance", "heritage", "testament", "statut personnel"]):
                        family = "code_succession"
                    else:
                        family = "code_civil"
                copy["code_family"] = family
                copy["code_name"] = str(copy.get("code_name") or cls.CODE_SCOPE_LABELS.get(family, "Code Civil")).strip()
                cleaned_items.append(copy)

            if cleaned_items:
                normalized_payload[normalized_country] = cleaned_items

        cls._local_legal_codes_corpus_cache = normalized_payload
        return cls._local_legal_codes_corpus_cache

    @classmethod
    def _load_local_constitution_corpus(cls) -> Dict[str, List[Dict[str, Any]]]:
        return cls._load_local_legal_codes_corpus()

    def _retrieve_local_legal_code_sources(
        self,
        *,
        country: str,
        query: str,
        case_focus_terms: List[str],
        top_k: int,
        preferred_code_families: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        corpus_items = self._load_local_legal_codes_corpus().get(country) or []
        if not corpus_items:
            return []

        preferred = self._normalize_code_scope(preferred_code_families)

        lowered_query = str(query or "").lower()
        ranked_items: List[Dict[str, Any]] = []

        for rank_index, entry in enumerate(corpus_items, start=1):
            article = str(entry.get("article") or "").strip()
            title = str(entry.get("title") or "").strip()
            summary = str(entry.get("summary") or "").strip()
            url = str(entry.get("url") or "").strip()
            code_family = str(entry.get("code_family") or "code_civil").strip().lower()
            if preferred and code_family not in preferred:
                continue
            code_name = str(entry.get("code_name") or self.CODE_SCOPE_LABELS.get(code_family, "Code Civil")).strip()
            raw_keywords = entry.get("keywords")
            raw_tags = entry.get("tags")
            keywords = [str(item).strip() for item in raw_keywords if str(item).strip()] if isinstance(raw_keywords, list) else []
            tags = [str(item).strip() for item in raw_tags if str(item).strip()] if isinstance(raw_tags, list) else []

            combined_text = " ".join([code_name, article, title, summary, *keywords, *tags]).strip()
            if not combined_text:
                continue

            keyword_overlap = self._keyword_score(query=query, text=combined_text)
            exact_keyword_hits = sum(1 for item in keywords if item.lower() in lowered_query)
            case_bonus = self._focus_term_bonus(case_focus_terms=case_focus_terms, text=combined_text)

            article_bonus = 0.0
            article_number_match = re.search(r"(\d+[a-zA-Z0-9\-]*)", article)
            if article and article.lower() in lowered_query:
                article_bonus = 8.0
            elif article_number_match and article_number_match.group(1).lower() in lowered_query:
                article_bonus = 5.0

            if keyword_overlap <= 0.0 and exact_keyword_hits == 0 and case_bonus <= 0.0 and article_bonus <= 0.0:
                continue

            base_score = 38.0
            family_bonus = 4.0 if code_family in preferred[:1] else 2.0 if code_family in preferred else 0.0
            score = (
                base_score
                + (keyword_overlap * 30.0)
                + (exact_keyword_hits * 3.5)
                + case_bonus
                + article_bonus
                + family_bonus
                + (1.5 if article else 0.0)
                - (rank_index * 0.05)
            )

            display_title = title or article or "Code Provision"
            domain = self._domain_from_url(url) if url else "local-legal-code-corpus"
            ranked_items.append(
                {
                    "title": display_title,
                    "url": url,
                    "domain": domain,
                    "snippet": summary or combined_text[:280],
                    "rank": rank_index,
                    "source_type": "official",
                    "source_origin": "local_code",
                    "priority": 4,
                    "reference": article or title,
                    "code_family": code_family,
                    "code_name": code_name,
                    "score": score,
                }
            )

        ranked_items.sort(key=lambda item: float(item.get("score", 0.0)), reverse=True)
        return ranked_items[: max(6, top_k)]

    def _retrieve_local_constitution_sources(
        self,
        *,
        country: str,
        query: str,
        case_focus_terms: List[str],
        top_k: int,
    ) -> List[Dict[str, Any]]:
        return self._retrieve_local_legal_code_sources(
            country=country,
            query=query,
            case_focus_terms=case_focus_terms,
            top_k=top_k,
            preferred_code_families=None,
        )

    def _extract_case_focus_terms(self, *, query: str, internal_results: List[Dict[str, Any]]) -> List[str]:
        terms: Dict[str, int] = {}
        for token in self._tokenize_terms(query):
            if len(token) >= 4:
                terms[token] = terms.get(token, 0) + 2

        for item in internal_results[:8]:
            text = " ".join(
                [
                    str(item.get("filename") or ""),
                    str(item.get("title") or ""),
                    str(item.get("snippet") or ""),
                    str(item.get("chunk_text") or ""),
                ]
            )
            for token in self._tokenize_terms(text):
                if len(token) < 5:
                    continue
                terms[token] = terms.get(token, 0) + 1

        ranked_terms = sorted(
            terms.items(),
            key=lambda item: (item[1], len(item[0]), item[0]),
            reverse=True,
        )
        return [item[0] for item in ranked_terms[:14]]

    def _focus_term_bonus(self, *, case_focus_terms: List[str], text: str) -> float:
        if not case_focus_terms:
            return 0.0
        lowered_text = str(text or "").lower()
        if not lowered_text:
            return 0.0

        hits = 0
        for term in case_focus_terms[:12]:
            normalized_term = str(term or "").strip().lower()
            if len(normalized_term) < 4:
                continue
            if normalized_term in lowered_text:
                hits += 1
        return min(8.0, float(hits) * 1.2)

    @staticmethod
    def _tokenize_terms(text: str) -> List[str]:
        return re.findall(r"[\w\u0600-\u06FF]+", str(text or "").lower())

    @staticmethod
    def _domain_from_url(url: str) -> str:
        raw = str(url or "").strip().lower()
        if not raw:
            return ""
        trimmed = re.sub(r"^https?://", "", raw)
        host = trimmed.split("/", 1)[0]
        return LegalSearchModeService._normalize_domain(host)

    def _collect_external_results(
        self,
        *,
        country: str,
        query: str,
        case_focus_terms: List[str],
        research_results: List[Dict[str, Any]],
        seen_keys: set[str],
        destination: List[Dict[str, Any]],
        preferred_code_families: Optional[List[str]] = None,
    ) -> None:
        for item in research_results:
            key = self._dedupe_key(item)
            if not key or key in seen_keys:
                continue
            seen_keys.add(key)
            normalized = self._normalize_external_result(
                country=country,
                item=item,
                query=query,
                case_focus_terms=case_focus_terms,
                preferred_code_families=preferred_code_families,
            )
            if normalized:
                destination.append(normalized)

    def _translate_query_variants(self, *, country: str, query: str) -> Dict[str, str]:
        variants: Dict[str, str] = {"original": query}
        for lang in self.TRANSLATION_TARGETS.get(country, []):
            translated = self._translate_text(query=query, target_language=lang)
            if translated:
                variants[lang] = translated
        return variants

    def _build_search_queries(
        self,
        *,
        country: str,
        translated_queries: Dict[str, str],
        case_topic: Optional[Dict[str, Any]],
    ) -> List[str]:
        queries: List[str] = []
        original = translated_queries.get("original", "")
        topic_terms = " ".join(self._search_terms_for_code_families((case_topic or {}).get("code_families")))
        if country == "tunisia":
            arabic = translated_queries.get("ar") or original
            french = translated_queries.get("fr") or original
            arabic_terms = (
                "\u062a\u0648\u0646\u0633 "
                "\u0645\u062c\u0644\u0629 \u0627\u0644\u0627\u0644\u062a\u0632\u0627\u0645\u0627\u062a \u0648\u0627\u0644\u0639\u0642\u0648\u062f "
                "\u0627\u0644\u0623\u062d\u0648\u0627\u0644 \u0627\u0644\u0634\u062e\u0635\u064a\u0629 "
                "\u0627\u0644\u0642\u0627\u0646\u0648\u0646 \u0627\u0644\u062f\u0648\u0644\u064a \u0627\u0644\u062e\u0627\u0635"
            )
            queries.append(f"{arabic} {arabic_terms} {topic_terms}")
            queries.append(
                f"{french} Tunisie code civil succession droit international prive jurisprudence {topic_terms}"
            )
            queries.append(f"{original} Tunisia legal source legislation.tn iort.gov.tn")
            queries.append(f"{original} site:wipo.int Tunisia legislation")
        elif country == "germany":
            german = translated_queries.get("de") or original
            queries.append(f"{german} Deutschland BGB StGB Gesetz \u00a7 {topic_terms}")
            queries.append(f"{german} site:gesetze-im-internet.de")
            queries.append(f"{original} Germany legal code BGB StGB {topic_terms}")
            queries.append(f"{original} site:bundestag.de site:bmj.de")
        else:
            queries.append(original)

        cleaned: List[str] = []
        for item in queries:
            normalized = " ".join(str(item or "").split()).strip()
            if normalized and normalized not in cleaned:
                cleaned.append(normalized)
        return cleaned

    def _search_terms_for_code_families(self, code_families: Optional[List[str]]) -> List[str]:
        normalized = self._normalize_code_scope(code_families)
        terms: List[str] = []
        if "code_civil" in normalized:
            terms.extend(["code civil", "obligations", "contracts", "responsabilite civile"])
        if "code_succession" in normalized:
            terms.extend(["succession", "heritage", "testament", "statut personnel"])
        if "code_international_prive" in normalized:
            terms.extend(["droit international prive", "conflit de lois", "exequatur"])
        return terms

    def _translate_text(self, *, query: str, target_language: str) -> str:
        if not self.client:
            return query

        prompt = (
            f"Translate the following legal search query to {target_language}.\n"
            "Return only the translated query string with no extra commentary.\n\n"
            f"Query:\n{query}"
        )
        try:
            response = self.client.responses.create(
                model=self.model,
                input=prompt,
            )
            translated = llm_gateway.extract_output_text(response).strip()
            return translated or query
        except Exception:
            return query

    @staticmethod
    def _dedupe_key(item: Dict[str, Any]) -> str:
        url = str(item.get("url") or "").strip().lower()
        title = str(item.get("title") or "").strip().lower()
        snippet = str(item.get("snippet") or "").strip().lower()
        if url:
            return url
        if title:
            return title
        return snippet[:200]

    def _normalize_external_result(
        self,
        *,
        country: str,
        item: Dict[str, Any],
        query: str,
        case_focus_terms: List[str],
        preferred_code_families: Optional[List[str]] = None,
    ) -> Optional[Dict[str, Any]]:
        title = str(item.get("title") or "").strip()
        url = str(item.get("url") or "").strip()
        domain = self._normalize_domain(str(item.get("domain") or ""))
        snippet = str(item.get("snippet") or "").strip()
        rank = int(item.get("rank") or 999)
        if not (title or snippet):
            return None

        source_type = self._classify_source_type(country=country, domain=domain, text=f"{title} {snippet}")
        priority = 3 if source_type == "official" else 2 if source_type == "jurisprudence" else 1
        reference = self._extract_reference(country=country, text=f"{title} {snippet}")
        code_family = self._infer_code_family_from_text(text=f"{title} {snippet}")
        normalized_preferred = self._normalize_code_scope(preferred_code_families)
        if code_family and normalized_preferred and code_family not in normalized_preferred:
            return None
        keyword_score = self._keyword_score(query=query, text=f"{title} {snippet}")
        case_focus_bonus = self._focus_term_bonus(case_focus_terms=case_focus_terms, text=f"{title} {snippet}")
        article_bonus = 1.5 if reference else 0.0
        family_bonus = 2.0 if code_family and code_family in normalized_preferred[:1] else 0.8 if code_family else 0.0
        score = (priority * 10.0) + (keyword_score * 5.0) + article_bonus + case_focus_bonus - (rank * 0.08)
        score += family_bonus

        return {
            "title": title or domain or "Legal Source",
            "url": url,
            "domain": domain,
            "snippet": snippet,
            "rank": rank,
            "source_type": source_type,
            "source_origin": "external_web",
            "priority": priority,
            "reference": reference,
            "code_family": code_family,
            "code_name": self.CODE_SCOPE_LABELS.get(code_family or "", ""),
            "score": score,
        }

    def _infer_code_family_from_text(self, *, text: str) -> str:
        lowered = str(text or "").lower()
        if any(token in lowered for token in ["international prive", "conflit de lois", "exequatur", "foreign judgment"]):
            return "code_international_prive"
        if any(token in lowered for token in ["succession", "inheritance", "heritage", "testament", "statut personnel"]):
            return "code_succession"
        if any(token in lowered for token in ["code civil", "obligation", "contract", "responsabilite", "procedure civile"]):
            return "code_civil"
        return ""

    def _classify_source_type(self, *, country: str, domain: str, text: str) -> str:
        lowered = (text or "").lower()
        if self._domain_matches(domain=domain, allowed_domains=self.OFFICIAL_DOMAINS.get(country, set())):
            return "official"
        if self._domain_matches(domain=domain, allowed_domains=self.JURISPRUDENCE_DOMAINS.get(country, set())):
            return "jurisprudence"

        if country == "germany":
            if any(token in lowered for token in ["grundgesetz", " bgb", " stgb", "gesetz", "\u00a7"]):
                return "official"
            if any(token in lowered for token in ["gericht", "urteil", "entscheidung", "case law", "jurisprudence"]):
                return "jurisprudence"

        if country == "tunisia":
            official_markers = [
                "\u0645\u062c\u0644\u0629",
                "code civil",
                "code de procedure civile",
                "code de procedure civile et commerciale",
                "code du statut personnel",
                "code de succession",
                "droit international prive",
                "code du droit international prive",
                "code penal",
                "code p\u00e9nal",
            ]
            if any(token in lowered for token in official_markers):
                return "official"
            if any(token in lowered for token in ["jurisprudence", "cour", "cassation", "tribunal"]):
                return "jurisprudence"

        return "secondary"

    @staticmethod
    def _extract_reference(*, country: str, text: str) -> str:
        patterns = [
            r"(\u00a7\s*\d+[a-zA-Z0-9\-]*)",
            r"(Art\.?\s*\d+[a-zA-Z0-9\-]*)",
            r"(Article\s+\d+[a-zA-Z0-9\-]*)",
            r"(Article\s+\d+[a-zA-Z0-9\-]*\s+du\s+Code\s+[A-Za-z\- ]+)",
            r"(\u0627\u0644\u0641\u0635\u0644\s*\d+)",
        ]
        for pattern in patterns:
            match = re.search(pattern, text, flags=re.IGNORECASE)
            if match:
                return match.group(1).strip()

        lowered = text.lower()
        if country == "germany":
            if "grundgesetz" in lowered:
                return "Grundgesetz"
            if " bgb" in lowered:
                return "BGB"
            if " stgb" in lowered:
                return "StGB"
        if country == "tunisia":
            if "code civil" in lowered or "procedure civile" in lowered:
                return "Code Civil"
            if "succession" in lowered or "statut personnel" in lowered or "inheritance" in lowered:
                return "Code de Succession"
            if "international prive" in lowered or "conflit de lois" in lowered:
                return "Code International Prive"
            if "code penal" in lowered or "code p\u00e9nal" in lowered:
                return "Code Penal"
        return ""

    @staticmethod
    def _keyword_score(*, query: str, text: str) -> float:
        query_tokens = set(re.findall(r"\w+", query.lower()))
        text_tokens = set(re.findall(r"\w+", text.lower()))
        if not query_tokens or not text_tokens:
            return 0.0
        overlap = query_tokens.intersection(text_tokens)
        return float(len(overlap)) / float(max(len(query_tokens), 1))

    def _rank_sources(self, *, query: str, results: List[Dict[str, Any]], top_k: int) -> List[Dict[str, Any]]:
        candidates: List[Dict[str, Any]] = []
        for item in results:
            enriched = dict(item)
            enriched["chunk_text"] = f"{item.get('title', '')}\n{item.get('snippet', '')}".strip()
            candidates.append(enriched)

        reranked, _ = reranker_service.rerank(
            query,
            candidates,
            top_k=min(max(top_k * 2, 8), len(candidates)),
        )
        pool = reranked or candidates
        normalized: List[Dict[str, Any]] = []
        for item in pool:
            copy = dict(item)
            copy["score"] = float(copy.get("score", 0.0)) + (float(copy.get("rerank_score", 0.0)) * 2.0)
            copy.pop("chunk_text", None)
            normalized.append(copy)

        normalized.sort(
            key=lambda x: (x.get("priority", 1), float(x.get("score", 0.0))),
            reverse=True,
        )
        return normalized

    def _generate_grounded_answer(
        self,
        *,
        country: str,
        query: str,
        user_language: str,
        legal_sources: List[Dict[str, Any]],
        internal_results: List[Dict[str, Any]],
        include_english_summary: bool,
        case_topic: Optional[Dict[str, Any]],
        applicability_mappings: Optional[List[Dict[str, Any]]] = None,
    ) -> str:
        compact_sources = legal_sources[:8]
        compact_internal = internal_results[:4]
        normalized_language = self._normalize_response_language(user_language)
        confidence = self._confidence_from_sources(compact_sources)
        verification_status = self._verification_status_from_sources(compact_sources)

        # Build structured applicability summary for the LLM
        direct_mappings = [m for m in (applicability_mappings or []) if m.get("applicability") in ("direct", "partial")]
        applicability_summary = self._build_applicability_summary(direct_mappings)
        domain_conf_note = ""
        if (case_topic or {}).get("needs_counsel_domain_verification"):
            domain_conf_note = (
                "\nDOMAIN UNCERTAINTY: The legal domain classifier has low confidence. "
                "Counsel must verify which corpus applies before relying on this analysis.\n"
            )

        if self.client:
            prompt = f"""You are a legal copilot designed to assist lawyers, not replace them.

Core operating principles:
- The human lawyer retains final legal judgment. You provide structured, reviewable legal analysis.
- You do NOT provide definitive legal advice.
- Distinguish confirmed facts, inferred facts, missing facts, and assumptions requiring validation.
- Ground every legal statement in the retrieved sources. Never fabricate articles or citations.
- If source support is weak, partial, or conflicting, state this explicitly.
- Use careful language: "based on the currently available facts", "may apply", "subject to lawyer review".

STRICT OUTPUT STRUCTURE — you MUST use exactly these five numbered sections in this order:

1. Case risks
   Summarise the concrete legal risks present in the case context based on the internal retrieval.
   If no internal case context: write "Insufficient case context to identify specific risks."

2. Applicable law
   List only the legal articles/provisions that are directly or partially applicable.
   For each article: one line — reference, plain-language rule summary, applicability level.
   If NO directly applicable provision exists, write exactly:
   "No directly applicable legal provision was confidently identified in the selected jurisdiction/domain corpus."

3. Legal assessment
   Map each applicable provision to the known case facts.
   Use the pre-computed applicability analysis below as your starting point.
   Flag every gap between the legal rule and the current facts.
   Use cautious language. Do NOT conclude when facts are missing.

4. Missing facts / verification needed
   Enumerate the specific facts, documents, or evidence that counsel must verify before
   relying on this analysis. Be specific, not generic.

5. Counsel note
   Final legal judgment remains with the responsible lawyer.
   Confidence: {confidence}. Verification status: {verification_status}.

RULES:
- Write in language code: {user_language}.
- Use only the provided legal sources as citations. Never invent references.
- Keep each section concise and professional.
- If include_english_summary is true, add a brief English summary after section 5.{domain_conf_note}

CONTEXT:
Jurisdiction: {self.COUNTRY_DISPLAY.get(country, country.title())}
User query: {query}
Case topic: {(case_topic or {}).get("topic") or "General civil matter"}
Domain confidence: {(case_topic or {}).get("confidence", "unknown")} — {(case_topic or {}).get("reason", "")}
Code families in scope: {(case_topic or {}).get("code_families") or self.DEFAULT_CODE_SCOPE}
include_english_summary: {str(include_english_summary).lower()}

PRE-COMPUTED APPLICABILITY ANALYSIS (use to populate section 3):
{applicability_summary}

LEGAL SOURCES (use only these for section 2 and 3):
{compact_sources}

INTERNAL CASE RETRIEVAL (use only for section 1 and section 4):
{compact_internal}
"""
            try:
                response = self.client.responses.create(
                    model=self.model,
                    input=prompt,
                )
                output = llm_gateway.extract_output_text(response).strip()
                if output:
                    _logger.info("[legal_search] legal_output_structure_applied=True")
                    return self._ensure_default_legal_response_structure(
                        answer_body=output,
                        query=query,
                        legal_sources=compact_sources,
                        confidence=confidence,
                        verification_status=verification_status,
                        user_language=normalized_language,
                    )
            except Exception:
                pass

        if compact_sources:
            top = compact_sources[0]
            reference = top.get("reference") or top.get("title")
            fallback = (
                f"Based on the retrieved legal material ({reference}), this answer stays source-grounded and cautious.\n"
                "Cross-check article-level wording in the linked official text before filing or advising."
            )
        else:
            fallback = "The available legal source snippets are limited; this answer remains cautious and source-bound."

        if include_english_summary:
            fallback += "\nEnglish summary: Source-grounded legal guidance was generated with limited available context."
        return self._ensure_default_legal_response_structure(
            answer_body=fallback,
            query=query,
            legal_sources=compact_sources,
            confidence=confidence,
            verification_status=verification_status,
            user_language=normalized_language,
        )

    def _generate_case_context_fallback_answer(
        self,
        *,
        db: Session,
        tenant_id: int,
        case: Optional[Case],
        internal_results: List[Dict[str, Any]],
        country: str,
        query: str,
    ) -> str:
        """
        Generate a structured 5-section answer when case context exists but no
        corpus-verified legal provisions were found. Uses case_reasoning_agent for
        risk extraction, then wraps results in the mandatory legal-practice template.

        This path sets fallback_reason="case_context_no_legal_provisions" and is
        NOT overridden by _normalize_trust_state (the string is not in the
        insufficient-evidence trigger set).
        """
        risks: List[str] = []
        missing_facts: List[str] = []

        # ── 1. Try to extract risks via case_reasoning_agent ──────────────────
        if case is not None:
            try:
                docs = (
                    db.query(Document)
                    .filter(
                        Document.case_id == case.id,
                        Document.tenant_id == tenant_id,
                    )
                    .order_by(Document.upload_timestamp.asc(), Document.id.asc())
                    .limit(10)
                    .all()
                )
                if docs:
                    reasoning_result = case_reasoning_agent.analyze_case(
                        case=case,
                        documents=docs,
                        jurisdiction_country=country,
                        consultation_requests=[],
                        voice_recordings=[],
                    )
                    if reasoning_result.success:
                        rp = reasoning_result.payload
                        risks = (rp.get("legal_risks") or [])[:3]
                        missing_facts = (
                            rp.get("missing_facts") or rp.get("open_questions") or []
                        )[:3]
            except Exception:
                pass

        # ── 2. Fallback: extract from internal_results snippets ───────────────
        if not risks:
            seen: set = set()
            for r in (internal_results or [])[:5]:
                snippet = str(r.get("snippet") or r.get("content") or "").strip()
                if snippet and snippet not in seen:
                    seen.add(snippet)
                    risks.append(snippet[:120])
            risks = risks[:3]

        # ── 3. Build the 5-section structured answer ──────────────────────────
        jurisdiction_display = self.COUNTRY_DISPLAY.get(country, country.title())
        risk_bullets = "\n".join(f"  - {r}" for r in risks) if risks else (
            "  - Unable to extract specific risks from available case materials."
        )
        missing_bullets = "\n".join(f"  - {m}" for m in missing_facts) if missing_facts else (
            "  - Full contract/document set not available for review.\n"
            "  - Applicable jurisdiction-specific precedents not confirmed."
        )

        return (
            f"**1. Case Risks**\n"
            f"{risk_bullets}\n\n"
            f"**2. Applicable Law**\n"
            f"  No directly applicable legal provision was confidently identified in the "
            f"{jurisdiction_display} legal corpus for this query. Counsel must verify "
            f"article-level authority before relying on this analysis.\n\n"
            f"**3. Legal Assessment**\n"
            f"  The case file supports a practical risk analysis, but no corpus-verified "
            f"legal authority was located. The risks identified above are based on case "
            f"materials only and carry low legal confidence without statutory grounding.\n\n"
            f"**4. Missing Facts / Verification Needed**\n"
            f"{missing_bullets}\n\n"
            f"**5. Counsel Note**\n"
            f"  Final legal judgment remains with qualified counsel. This output is "
            f"case-context reasoning only — not a legal opinion. Confidence: low."
        )

    def _build_reasoning_fallback(
        self,
        *,
        db: Session,
        tenant_id: int,
        country: str,
        query: str,
        case: Optional[Case],
    ) -> str:
        if case is not None:
            documents = (
                db.query(Document)
                .filter(
                    Document.case_id == case.id,
                    Document.tenant_id == tenant_id,
                )
                .order_by(Document.upload_timestamp.asc(), Document.id.asc())
                .all()
            )
            if documents:
                reasoning_result = case_reasoning_agent.analyze_case(
                    case=case,
                    documents=documents,
                    jurisdiction_country=country,
                    consultation_requests=[],
                    voice_recordings=[],
                )
                if reasoning_result.success:
                    payload = reasoning_result.payload
                    narrative = str(payload.get("narrative_summary") or payload.get("overview") or "").strip()
                    risks = payload.get("legal_risks") or []
                    steps = payload.get("recommended_next_steps") or []
                    lines = [narrative or "Case-level legal reasoning was generated from available case materials."]
                    if risks:
                        lines.append("Potential legal risks:")
                        lines.extend(f"- {item}" for item in risks[:3])
                    if steps:
                        lines.append("Recommended next steps:")
                        lines.extend(f"- {item}" for item in steps[:3])
                    return "\n".join(lines).strip()

        if self.client:
            analysis_framework = self._build_legal_analysis_framework(
                country=country,
                case_topic=None,
                has_internal_context=case is not None,
            )
            prompt = (
                "No direct legal source was retrieved for this question.\n"
                f"Provide concise legal reasoning based on general legal principles for {self.COUNTRY_DISPLAY.get(country, country)}.\n"
                "Do not fabricate article numbers.\n"
                "State uncertainty clearly.\n\n"
                f"Use this legal-practice reasoning flow:\n{analysis_framework}\n\n"
                f"Question:\n{query}"
            )
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

        if country == "germany":
            return (
                "General legal reasoning (Germany): assess the issue under the relevant statutory framework "
                "(e.g., Grundgesetz/BGB/StGB where applicable), verify facts and contract wording, and seek "
                "article-level confirmation in official legal text before relying on this conclusion."
            )
        return (
            "General legal reasoning (Tunisia): assess the issue under applicable Tunisian code-based "
            "principles, validate procedural and contractual facts, and confirm article-level support in official legal text "
            "before relying on this conclusion."
        )

    @staticmethod
    def _detect_user_language(text: str) -> str:
        raw = str(text or "")
        if re.search(r"[\u0600-\u06FF]", raw):
            return "ar"
        lowered = raw.lower()
        if any(token in lowered for token in ["deutsch", "deutschland", "grundgesetz", "gesetz", "bgb", "stgb"]):
            return "de"
        if any(token in lowered for token in ["bonjour", "tunisie", "droit", "juridique", "code civil"]):
            return "fr"
        return "en"

    @staticmethod
    def _build_applicability_summary(direct_mappings: List[Dict[str, Any]]) -> str:
        """Renders the LegalApplicabilityMapper results as a compact string for the LLM prompt."""
        if not direct_mappings:
            return "No direct or partial applicability mappings available."
        lines: List[str] = []
        for m in direct_mappings[:6]:
            ref = m.get("source_reference", "Unknown")
            appl = m.get("applicability", "unknown").upper()
            rule = m.get("rule_summary", "")
            facts = ", ".join(m.get("matching_case_facts", [])) or "none identified"
            missing = ", ".join(m.get("missing_facts", [])) or "none identified"
            assessment = m.get("assessment", "")
            lines.append(
                f"[{appl}] {ref}\n"
                f"  Rule: {rule}\n"
                f"  Matching facts: {facts}\n"
                f"  Missing facts: {missing}\n"
                f"  Assessment: {assessment}"
            )
        return "\n\n".join(lines)

    def _build_legal_analysis_framework(
        self,
        *,
        country: str,
        case_topic: Optional[Dict[str, Any]],
        has_internal_context: bool,
    ) -> str:
        topic_label = str((case_topic or {}).get("topic") or "General civil matter").strip()
        code_families = ", ".join(self._normalize_code_scope((case_topic or {}).get("code_families"))) or ", ".join(
            self.DEFAULT_CODE_SCOPE
        )
        lines = [
            "1. Identify the legal issue precisely before proposing any conclusion.",
            "2. Identify the governing legal basis from retrieved sources and explicitly mark scope limits.",
            f"3. Explain the rule for topic '{topic_label}' within code families [{code_families}].",
            "4. Apply the rule to known facts with clear fact-to-rule mapping.",
            "5. Separate confirmed facts, inferred facts, missing facts, and assumptions requiring validation.",
            "6. Add counter-analysis or alternative interpretation where reasonable.",
            "7. Use cautious language and avoid presenting uncertain points as settled law.",
        ]
        if has_internal_context:
            lines.append("8. Add a short case applicability check tied to the current matter record.")
            lines.append("9. Finish with practical next steps for the lawyer and verification actions.")
        else:
            lines.append("8. Finish with practical next steps for the lawyer and verification actions.")
        if country == "tunisia":
            lines.append("Use Tunisian code-based terminology and keep output review-ready for counsel.")
        elif country == "germany":
            lines.append("Use German statutory framing and keep output review-ready for counsel.")
        else:
            lines.append("Keep output review-ready for counsel.")
        return "\n".join(f"- {line}" for line in lines)

    @staticmethod
    def _normalize_response_language(user_language: str | None) -> str:
        language = str(user_language or "").strip().lower()
        if language in {"ar", "fr", "de", "en"}:
            return language
        return "en"

    def _response_section_label(self, section_key: str, user_language: str) -> str:
        labels = {
            "en": {
                "matter_understood": "Matter Understood",
                "confirmed_facts": "Confirmed Facts",
                "legal_issue": "Legal Issue",
                "relevant_legal_basis": "Relevant Legal Basis",
                "rule_summary": "Rule Summary",
                "application_to_known_facts": "Application to Known Facts",
                "missing_facts_uncertainty": "Missing Facts / Uncertainty",
                "counter_analysis": "Counter-Analysis / Alternative Interpretation",
                "practical_next_steps": "Practical Next Steps",
                "lawyer_review_note": "Lawyer Review Note",
            },
            "fr": {
                "matter_understood": "Question Comprise",
                "confirmed_facts": "Faits Confirmes",
                "legal_issue": "Question Juridique",
                "relevant_legal_basis": "Base Juridique Pertinente",
                "rule_summary": "Resume de la Regle",
                "application_to_known_facts": "Application aux Faits Connus",
                "missing_facts_uncertainty": "Faits Manquants / Incertitude",
                "counter_analysis": "Contre-Analyse / Interpretation Alternative",
                "practical_next_steps": "Prochaines Etapes Pratiques",
                "lawyer_review_note": "Note de Revue par l'Avocat",
            },
            "de": {
                "matter_understood": "Verstandene Angelegenheit",
                "confirmed_facts": "Bestaetigte Tatsachen",
                "legal_issue": "Rechtsfrage",
                "relevant_legal_basis": "Relevante Rechtsgrundlage",
                "rule_summary": "Regelzusammenfassung",
                "application_to_known_facts": "Anwendung auf bekannte Tatsachen",
                "missing_facts_uncertainty": "Fehlende Tatsachen / Unsicherheit",
                "counter_analysis": "Gegenanalyse / Alternative Auslegung",
                "practical_next_steps": "Praktische Naechste Schritte",
                "lawyer_review_note": "Hinweis zur anwaltlichen Pruefung",
            },
            "ar": {
                "matter_understood": "الموضوع المفهوم",
                "confirmed_facts": "الوقائع المؤكدة",
                "legal_issue": "المسألة القانونية",
                "relevant_legal_basis": "الاساس القانوني ذي الصلة",
                "rule_summary": "ملخص القاعدة",
                "application_to_known_facts": "تطبيق على الوقائع المعروفة",
                "missing_facts_uncertainty": "الوقائع الناقصة / عدم اليقين",
                "counter_analysis": "تحليل مضاد / تفسير بديل",
                "practical_next_steps": "الخطوات العملية التالية",
                "lawyer_review_note": "ملاحظة للمراجعة من قبل المحامي",
            },
        }
        normalized_language = self._normalize_response_language(user_language)
        return labels.get(normalized_language, labels["en"]).get(section_key, section_key)

    def _localized_lawyer_review_note(self, user_language: str) -> str:
        notes = {
            "en": self.LAWYER_REVIEW_NOTE,
            "fr": (
                "Il s'agit d'une assistance juridique preliminaire destinee a la revue professionnelle ; "
                "le jugement juridique final appartient a l'avocat en charge du dossier."
            ),
            "de": (
                "Dies ist eine vorlaeufige juristische Unterstuetzung zur professionellen Pruefung; "
                "die endgueltige rechtliche Beurteilung liegt beim zustaendigen Anwalt."
            ),
            "ar": (
                "هذه مساعدة قانونية اولية مخصصة للمراجعة المهنية؛ "
                "ويظل التقدير القانوني النهائي من اختصاص المحامي المسؤول عن الملف."
            ),
        }
        normalized_language = self._normalize_response_language(user_language)
        return notes.get(normalized_language, notes["en"])

    def _localized_no_direct_source_text(self, user_language: str) -> str:
        messages = {
            "en": "No direct article-level source retrieved.",
            "fr": "Aucune source directe au niveau de l'article n'a ete recuperee.",
            "de": "Es wurde keine direkte Quelle auf Artikelebene abgerufen.",
            "ar": "لم يتم استرجاع مصدر مباشر على مستوى المادة.",
        }
        normalized_language = self._normalize_response_language(user_language)
        return messages.get(normalized_language, messages["en"])

    def _default_response_structure_guide(self, user_language: str) -> str:
        return "\n".join(
            f"{index}. {self._response_section_label(section_key, user_language)}"
            for index, section_key in enumerate(self.DEFAULT_RESPONSE_SECTION_ORDER, start=1)
        )

    @staticmethod
    def _verification_status_from_sources(items: List[Dict[str, Any]]) -> str:
        if not items:
            return "not_verified_no_direct_source"
        has_reference = any(str(item.get("reference") or "").strip() for item in items)
        if has_reference:
            return "source_grounded_article_references_present"
        return "source_grounded_reference_partial"

    def _ensure_default_legal_response_structure(
        self,
        *,
        answer_body: str,
        query: str,
        legal_sources: List[Dict[str, Any]],
        confidence: str,
        verification_status: str,
        user_language: str,
    ) -> str:
        response = str(answer_body or "").strip()
        normalized_language = self._normalize_response_language(user_language)
        localized_lawyer_review_note = self._localized_lawyer_review_note(normalized_language)

        basis_items: List[str] = []
        for item in legal_sources[:4]:
            reference = str(item.get("reference") or item.get("title") or "").strip()
            if reference and reference not in basis_items:
                basis_items.append(reference)
        legal_basis = ", ".join(basis_items) if basis_items else self._localized_no_direct_source_text(normalized_language)

        placeholders_by_language: Dict[str, Dict[str, str]] = {
            "en": {
                "matter_understood": f"Based on the currently available facts, the matter concerns: {query}.",
                "confirmed_facts": (
                    "- Confirmed facts: Limited to retrieved sources and provided context.\n"
                    "- Inferred facts: Any interpretation beyond explicit source wording is provisional.\n"
                    "- Missing facts: Full chronology, parties, and documentary record may be incomplete.\n"
                    "- Assumptions that require validation: applicability of retrieved provisions to the final fact pattern."
                ),
                "legal_issue": "The legal issue should be confirmed by counsel against the complete factual record.",
                "relevant_legal_basis": f"- {legal_basis}",
                "rule_summary": "Rule extraction is limited to currently retrieved legal material and may require article-level verification.",
                "application_to_known_facts": "Application is preliminary and based on currently available facts; additional facts may change the conclusion.",
                "missing_facts_uncertainty": "Missing facts and evidentiary gaps should be resolved before relying on this analysis.",
                "counter_analysis": "An alternate interpretation may apply depending on disputed facts, procedural posture, or competing readings of the legal basis.",
                "practical_next_steps": (
                    "1) Verify article wording in official source text.\n"
                    "2) Request missing facts/documents that materially affect applicability.\n"
                    "3) Confirm final legal position with responsible counsel."
                ),
                "lawyer_review_note": (
                    f"Confidence level: {confidence}. Verification status: {verification_status}. "
                    f"{localized_lawyer_review_note}"
                ),
            },
            "fr": {
                "matter_understood": f"Sur la base des faits actuellement disponibles, le dossier concerne : {query}.",
                "confirmed_facts": (
                    "- Faits confirmes : limites aux sources recuperees et au contexte fourni.\n"
                    "- Faits inférés : toute interpretation au-dela du texte explicite reste provisoire.\n"
                    "- Faits manquants : la chronologie complete, les parties et le dossier documentaire peuvent etre incomplets.\n"
                    "- Hypotheses a verifier : l'applicabilite des dispositions recuperees au schema factuel final."
                ),
                "legal_issue": "La question juridique doit etre confirmee par l'avocat au regard du dossier factuel complet.",
                "relevant_legal_basis": f"- {legal_basis}",
                "rule_summary": "L'extraction de la regle est limitee au materiel juridique actuellement recupere et peut necessiter une verification article par article.",
                "application_to_known_facts": "L'application est preliminaire et basee sur les faits actuellement disponibles ; des faits supplementaires peuvent modifier la conclusion.",
                "missing_facts_uncertainty": "Les faits manquants et les lacunes probatoires doivent etre resolus avant de se fier a cette analyse.",
                "counter_analysis": "Une interpretation alternative peut s'appliquer selon les faits contestes, la posture procedurale ou une lecture concurrente de la base juridique.",
                "practical_next_steps": (
                    "1) Verifier le libelle des articles dans la source officielle.\n"
                    "2) Demander les faits ou documents manquants qui affectent materiellement l'applicabilite.\n"
                    "3) Confirmer la position juridique finale avec l'avocat responsable."
                ),
                "lawyer_review_note": (
                    f"Niveau de confiance : {confidence}. Statut de verification : {verification_status}. "
                    f"{localized_lawyer_review_note}"
                ),
            },
            "de": {
                "matter_understood": f"Auf Grundlage der derzeit verfuegbaren Tatsachen betrifft die Angelegenheit: {query}.",
                "confirmed_facts": (
                    "- Bestaetigte Tatsachen: beschraenkt auf die abgerufenen Quellen und den bereitgestellten Kontext.\n"
                    "- Abgeleitete Tatsachen: jede Auslegung ueber den ausdruecklichen Wortlaut hinaus ist vorlaeufig.\n"
                    "- Fehlende Tatsachen: die vollstaendige Chronologie, die Parteien und die Dokumentation koennen unvollstaendig sein.\n"
                    "- Zu verifizierende Annahmen: die Anwendbarkeit der abgerufenen Vorschriften auf den endgueltigen Sachverhalt."
                ),
                "legal_issue": "Die Rechtsfrage sollte durch den zustaendigen Anwalt anhand des vollstaendigen Sachverhalts bestaetigt werden.",
                "relevant_legal_basis": f"- {legal_basis}",
                "rule_summary": "Die Regelzusammenfassung ist auf das derzeit abgerufene Rechtsmaterial beschraenkt und kann eine artikelgenaue Verifikation erfordern.",
                "application_to_known_facts": "Die Anwendung ist vorlaeufig und beruht auf den derzeit bekannten Tatsachen; weitere Tatsachen koennen die Schlussfolgerung aendern.",
                "missing_facts_uncertainty": "Fehlende Tatsachen und Beweisluecken sollten geklaert werden, bevor auf diese Analyse vertraut wird.",
                "counter_analysis": "Je nach streitigen Tatsachen, Verfahrenslage oder konkurrierender Auslegung der Rechtsgrundlage kann auch eine andere Auslegung in Betracht kommen.",
                "practical_next_steps": (
                    "1) Den Wortlaut der Artikel in der offiziellen Quelle pruefen.\n"
                    "2) Fehlende Tatsachen oder Dokumente anfordern, die die Anwendbarkeit wesentlich beeinflussen.\n"
                    "3) Die endgueltige Rechtsposition mit dem verantwortlichen Anwalt abstimmen."
                ),
                "lawyer_review_note": (
                    f"Vertrauensniveau: {confidence}. Verifikationsstatus: {verification_status}. "
                    f"{localized_lawyer_review_note}"
                ),
            },
            "ar": {
                "matter_understood": f"استنادا إلى الوقائع المتاحة حاليا، يتعلق الموضوع بـ: {query}.",
                "confirmed_facts": (
                    "- الوقائع المؤكدة: تقتصر على المصادر المسترجعة والسياق المقدم.\n"
                    "- الوقائع المستنتجة: اي تفسير يتجاوز النص الصريح يبقى مؤقتا.\n"
                    "- الوقائع الناقصة: قد يكون التسلسل الزمني الكامل والاطراف والملف الوثائقي غير مكتمل.\n"
                    "- الافتراضات التي تتطلب التحقق: مدى انطباق المقتضيات المسترجعة على الوقائع النهائية."
                ),
                "legal_issue": "ينبغي تاكيد المسالة القانونية من قبل المحامي بالرجوع إلى السجل الوقائعي الكامل.",
                "relevant_legal_basis": f"- {legal_basis}",
                "rule_summary": "استخراج القاعدة محدود بالمواد القانونية المسترجعة حاليا وقد يتطلب تحققاً على مستوى النص الكامل للمادة.",
                "application_to_known_facts": "التطبيق أولي ويستند إلى الوقائع المعروفة حاليا، وقد تغير الوقائع الإضافية النتيجة.",
                "missing_facts_uncertainty": "يجب معالجة الوقائع الناقصة والثغرات الإثباتية قبل الاعتماد على هذا التحليل.",
                "counter_analysis": "قد ينطبق تفسير بديل بحسب الوقائع المتنازع عليها أو الوضع الإجرائي أو القراءة المختلفة للأساس القانوني.",
                "practical_next_steps": (
                    "1) التحقق من صياغة المواد في المصدر الرسمي.\n"
                    "2) طلب الوقائع أو الوثائق الناقصة التي تؤثر ماديا في مدى الانطباق.\n"
                    "3) تاكيد الموقف القانوني النهائي مع المحامي المسؤول."
                ),
                "lawyer_review_note": (
                    f"مستوى الثقة: {confidence}. حالة التحقق: {verification_status}. "
                    f"{localized_lawyer_review_note}"
                ),
            },
        }
        placeholders = placeholders_by_language.get(normalized_language, placeholders_by_language["en"])

        for index, section_key in enumerate(self.DEFAULT_RESPONSE_SECTION_ORDER, start=1):
            section_label = self._response_section_label(section_key, normalized_language)
            section_pattern = re.compile(
                rf"(?im)^\s*(?:\d+\.\s*)?(?:\*\*\s*)?{re.escape(section_label)}(?:\s*\*\*)?\s*$"
            )
            if section_pattern.search(response):
                continue
            fallback_block = f"{index}. {section_label}\n{placeholders.get(section_key, '')}".strip()
            response = f"{response}\n\n{fallback_block}".strip() if response else fallback_block

        return response.strip()

    @staticmethod
    def _to_source_line(item: Dict[str, Any]) -> str:
        reference = str(item.get("reference") or "").strip()
        title = str(item.get("title") or "Legal source").strip()
        url = str(item.get("url") or "").strip()
        origin = str(item.get("source_origin") or "").strip()
        code_name = str(item.get("code_name") or "").strip()
        local_tag = " [local legal code corpus]" if origin == "local_code" else ""
        code_tag = f" [{code_name}]" if code_name else ""
        if reference and url:
            return f"{reference} - {title}{code_tag}{local_tag} ({url})"
        if reference:
            return f"{reference} - {title}{code_tag}{local_tag}"
        if url:
            return f"{title}{code_tag}{local_tag} ({url})"
        return f"{title}{code_tag}{local_tag}".strip()

    def _to_api_sources(self, items: List[Dict[str, Any]], fallback_score: float = 0.55) -> List[Dict[str, Any]]:
        sources: List[Dict[str, Any]] = []
        for item in items[:12]:
            snippet = str(item.get("snippet") or item.get("chunk_text") or "").strip()
            title = str(item.get("title") or item.get("filename") or "Legal Source").strip()
            url = str(item.get("url") or "").strip()
            score = float(item.get("score", fallback_score))
            source_type = str(item.get("source_type") or "internal_chunk").strip()
            source_origin = str(item.get("source_origin") or "internal").strip()
            reference = str(item.get("reference") or "").strip()

            meta_parts = [f"source_type={source_type}", f"source_origin={source_origin}"]
            if reference:
                meta_parts.append(f"reference={reference}")
            snippet = f"[{'; '.join(meta_parts)}] {snippet}" if snippet else f"[{'; '.join(meta_parts)}]"
            if url:
                snippet = f"{snippet} (source: {url})"

            sources.append(
                {
                    "chunk_id": item.get("chunk_id"),
                    "document_id": item.get("document_id"),
                    "case_id": item.get("case_id"),
                    "filename": title[:120] or "Legal Source",
                    "chunk_index": item.get("chunk_index"),
                    "score": score,
                    "snippet": snippet[:300],
                }
            )
        return sources

    def _to_api_citations(self, items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        citations: list[dict[str, Any]] = []
        for item in items[:8]:
            reference = str(item.get("reference") or item.get("title") or "Legal source").strip()
            snippet = str(item.get("snippet") or "").strip()
            url = str(item.get("url") or "").strip()
            snippet_text = (snippet[:220] or "Relevant legal excerpt available.").strip()
            citations.append(
                {
                    "label": reference,
                    "document_id": item.get("document_id"),
                    "case_id": item.get("case_id"),
                    "snippet": snippet_text,
                    "url": url or None,
                }
            )
        return citations

    @staticmethod
    def _confidence_from_sources(items: List[Dict[str, Any]]) -> str:
        if not items:
            return "low"
        has_official = any(str(item.get("source_type")) == "official" for item in items)
        has_reference = any(str(item.get("reference") or "").strip() for item in items)
        if has_official and has_reference:
            return "high"
        return "medium"

    def _compute_legal_match_confidence(
        self,
        *,
        legal_sources: List[Dict[str, Any]],
        applicability_mappings: List[Dict[str, Any]],
        legal_sources_note: Optional[str],
    ) -> tuple:
        """Returns (confidence, confidence_reason) based on applicability mappings.

        High   — ≥1 direct-applicability source from correct jurisdiction/domain
        Medium — ≥1 partial-applicability source; facts incomplete but direction plausible
        Low    — weak sources only, no survivors, or authority missing
        """
        if legal_sources_note or not legal_sources:
            reason = "No applicable legal provisions identified in the selected jurisdiction/domain corpus."
            _logger.info("[legal_search] legal_match_confidence=low reason=%r", reason)
            return "low", reason

        direct = [m for m in applicability_mappings if m.get("applicability") == "direct"]
        partial = [m for m in applicability_mappings if m.get("applicability") == "partial"]

        if direct:
            refs = ", ".join(m.get("source_reference", "") for m in direct[:2] if m.get("source_reference"))
            reason = f"Direct applicability found: {refs}." if refs else "Direct applicability found."
            _logger.info("[legal_search] legal_match_confidence=high reason=%r", reason)
            return "high", reason

        if partial:
            refs = ", ".join(m.get("source_reference", "") for m in partial[:2] if m.get("source_reference"))
            reason = (
                f"Partial applicability only: {refs}. Facts incomplete — legal direction is plausible but unconfirmed."
                if refs
                else "Partial applicability only. Facts incomplete — legal direction is plausible but unconfirmed."
            )
            _logger.info("[legal_search] legal_match_confidence=medium reason=%r", reason)
            return "medium", reason

        reason = "Only weak source relevance found. Legal basis requires verification by counsel."
        _logger.info("[legal_search] legal_match_confidence=low reason=%r", reason)
        return "low", reason

    @staticmethod
    def _format_legal_search_output(
        *,
        country: str,
        source_lines: List[str],
        answer_body: str,
        fallback_notice: Optional[str],
        confidence: str,
        verification_status: str,
        lawyer_review_note: str,
        legal_sources_note: Optional[str] = None,
    ) -> str:
        lines = ["[Legal Source Answer]", f"- Country: {country}", "- Sources:"]
        if source_lines:
            lines.extend(f"    - {item}" for item in source_lines[:8])
        else:
            lines.append("    - None (no direct legal source retrieved)")
        lines.extend(["", "[Answer]", (answer_body or "No answer could be generated.").strip()])
        lines.extend(
            [
                "",
                "[Trust Status]",
                f"- Confidence: {confidence}",
                f"- Verification status: {verification_status}",
                "- Legal basis: See source list above.",
                f"- Lawyer review note: {lawyer_review_note}",
            ]
        )
        if legal_sources_note:
            lines.extend(["", "[Legal Authority Status]", legal_sources_note.strip()])
        if fallback_notice:
            lines.extend(["", "[Fallback Notice]", fallback_notice.strip()])
        return "\n".join(lines).strip()

    @staticmethod
    def _normalize_domain(value: str) -> str:
        domain = str(value or "").strip().lower()
        if domain.startswith("www."):
            domain = domain[4:]
        return domain

    @staticmethod
    def _domain_matches(*, domain: str, allowed_domains: Iterable[str]) -> bool:
        normalized_domain = LegalSearchModeService._normalize_domain(domain)
        if not normalized_domain:
            return False
        normalized_allowed = {
            LegalSearchModeService._normalize_domain(item)
            for item in allowed_domains
            if LegalSearchModeService._normalize_domain(item)
        }
        for allowed in normalized_allowed:
            if normalized_domain == allowed or normalized_domain.endswith(f".{allowed}"):
                return True
        return False


legal_search_mode_service = LegalSearchModeService()
