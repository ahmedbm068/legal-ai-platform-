from __future__ import annotations

import re
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


class LegalSearchModeService:
    SUPPORTED_COUNTRIES = {"tunisia", "germany"}
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

    def __init__(self) -> None:
        self.client = llm_gateway.create_client()
        self.model = llm_gateway.default_model

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

        country = self._resolve_country(
            case=resolved_case,
            message=message,
            conversation_history=conversation_history,
        )
        jurisdiction = jurisdiction_context_service.get_response_context(country)
        optimized_query = self._optimize_query(
            message=message,
            intent=intent,
            target_type=target_type,
            target_id=target_id,
        )
        cache_key = self._build_cache_key(
            tenant_id=tenant_id,
            country=country,
            query=optimized_query,
            case_id=resolved_case.id if resolved_case else None,
            document_id=resolved_document.id if resolved_document else None,
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
        legal_sources = self._retrieve_jurisdiction_sources(
            country=country,
            query=optimized_query,
            top_k=max(top_k, 5),
        )
        scope = self._scope(
            case_id=resolved_case.id if resolved_case else None,
            document_id=resolved_document.id if resolved_document else None,
        )
        execution_trace = [
            {
                "stage": "legal_search_scope_resolution",
                "country": country,
                "scope": scope,
                "case_id": resolved_case.id if resolved_case else None,
                "document_id": resolved_document.id if resolved_document else None,
            },
            {
                "stage": "legal_search_retrieval",
                "internal_results": len(internal_results),
                "external_results": len(legal_sources),
            },
        ]

        if legal_sources:
            answer_body = self._generate_grounded_answer(
                country=country,
                query=optimized_query,
                user_language=self._detect_user_language(message),
                legal_sources=legal_sources,
                internal_results=internal_results,
                include_english_summary=multilingual_output,
            )
            payload = {
                "answer": self._format_legal_search_output(
                    country=self.COUNTRY_DISPLAY.get(country, country.title()),
                    source_lines=[self._to_source_line(item) for item in legal_sources],
                    answer_body=answer_body,
                    fallback_notice=None,
                ),
                "used_fallback": False,
                "fallback_reason": None,
                "confidence": self._confidence_from_sources(legal_sources),
                "scope": scope,
                "sources": self._to_api_sources(legal_sources),
                "citations": self._to_api_citations(legal_sources),
                "execution_trace": execution_trace,
                "jurisdiction": jurisdiction,
            }
            cache_service.set_json(cache_key, payload, ttl_seconds=settings.LEGAL_SEARCH_CACHE_TTL_SECONDS)
            return self._with_cache_metadata(payload, key=cache_key, hit=False)

        fallback_notice = "No direct legal source found; reasoning based on general legal principles"
        fallback_answer = self._build_reasoning_fallback(
            db=db,
            tenant_id=tenant_id,
            country=country,
            query=optimized_query,
            case=resolved_case,
        )
        payload = {
            "answer": self._format_legal_search_output(
                country=self.COUNTRY_DISPLAY.get(country, country.title()),
                source_lines=[],
                answer_body=fallback_answer,
                fallback_notice=fallback_notice,
            ),
            "used_fallback": True,
            "fallback_reason": "no_direct_legal_source",
            "confidence": "low",
            "scope": scope,
            "sources": self._to_api_sources(internal_results, fallback_score=0.3),
            "citations": self._to_api_citations(legal_sources),
            "execution_trace": execution_trace,
            "jurisdiction": jurisdiction,
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
    ) -> str:
        return cache_service.build_key(
            "legal_search",
            f"tenant={tenant_id}",
            f"country={country}",
            f"case={case_id or 'none'}",
            f"document={document_id or 'none'}",
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

    def _retrieve_jurisdiction_sources(
        self,
        *,
        country: str,
        query: str,
        top_k: int,
    ) -> List[Dict[str, Any]]:
        translated_queries = self._translate_query_variants(country=country, query=query)
        search_queries = self._build_search_queries(country=country, translated_queries=translated_queries)
        strict_domains = self.OFFICIAL_DOMAINS.get(country, set()) | self.JURISPRUDENCE_DOMAINS.get(country, set())

        gathered: List[Dict[str, Any]] = []
        seen_keys: set[str] = set()

        for item_query in search_queries[:5]:
            research = external_research_service.search(
                query=item_query,
                max_results=max(4, min(top_k + 2, 10)),
                allowed_domains=strict_domains,
            )
            self._collect_external_results(
                country=country,
                query=query,
                research_results=research.get("results") or [],
                seen_keys=seen_keys,
                destination=gathered,
            )

        if not gathered:
            for item_query in search_queries[:3]:
                research = external_research_service.search(
                    query=item_query,
                    max_results=max(3, min(top_k, 8)),
                )
                self._collect_external_results(
                    country=country,
                    query=query,
                    research_results=research.get("results") or [],
                    seen_keys=seen_keys,
                    destination=gathered,
                )

        if not gathered:
            return []
        return self._rank_sources(query=query, results=gathered, top_k=max(6, top_k))[: max(6, top_k)]

    def _collect_external_results(
        self,
        *,
        country: str,
        query: str,
        research_results: List[Dict[str, Any]],
        seen_keys: set[str],
        destination: List[Dict[str, Any]],
    ) -> None:
        for item in research_results:
            key = self._dedupe_key(item)
            if not key or key in seen_keys:
                continue
            seen_keys.add(key)
            normalized = self._normalize_external_result(country=country, item=item, query=query)
            if normalized:
                destination.append(normalized)

    def _translate_query_variants(self, *, country: str, query: str) -> Dict[str, str]:
        variants: Dict[str, str] = {"original": query}
        for lang in self.TRANSLATION_TARGETS.get(country, []):
            translated = self._translate_text(query=query, target_language=lang)
            if translated:
                variants[lang] = translated
        return variants

    def _build_search_queries(self, *, country: str, translated_queries: Dict[str, str]) -> List[str]:
        queries: List[str] = []
        original = translated_queries.get("original", "")
        if country == "tunisia":
            arabic = translated_queries.get("ar") or original
            french = translated_queries.get("fr") or original
            arabic_terms = (
                "\u062a\u0648\u0646\u0633 "
                "\u0627\u0644\u062f\u0633\u062a\u0648\u0631 \u0627\u0644\u062a\u0648\u0646\u0633\u064a "
                "\u0645\u062c\u0644\u0629 \u0627\u0644\u0627\u0644\u062a\u0632\u0627\u0645\u0627\u062a \u0648\u0627\u0644\u0639\u0642\u0648\u062f"
            )
            queries.append(f"{arabic} {arabic_terms}")
            queries.append(f"{french} Tunisie constitution code civil code penal jurisprudence")
            queries.append(f"{original} Tunisia legal source legislation.tn iort.gov.tn")
            queries.append(f"{original} site:wipo.int Tunisia legislation")
        elif country == "germany":
            german = translated_queries.get("de") or original
            queries.append(f"{german} Deutschland Grundgesetz BGB StGB Gesetz \u00a7")
            queries.append(f"{german} site:gesetze-im-internet.de")
            queries.append(f"{original} Germany legal code Grundgesetz BGB StGB")
            queries.append(f"{original} site:bundestag.de site:bmj.de")
        else:
            queries.append(original)

        cleaned: List[str] = []
        for item in queries:
            normalized = " ".join(str(item or "").split()).strip()
            if normalized and normalized not in cleaned:
                cleaned.append(normalized)
        return cleaned

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

    def _normalize_external_result(self, *, country: str, item: Dict[str, Any], query: str) -> Optional[Dict[str, Any]]:
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
        keyword_score = self._keyword_score(query=query, text=f"{title} {snippet}")
        article_bonus = 1.5 if reference else 0.0
        score = (priority * 10.0) + (keyword_score * 5.0) + article_bonus - (rank * 0.08)

        return {
            "title": title or domain or "Legal Source",
            "url": url,
            "domain": domain,
            "snippet": snippet,
            "rank": rank,
            "source_type": source_type,
            "priority": priority,
            "reference": reference,
            "score": score,
        }

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
                "\u0627\u0644\u062f\u0633\u062a\u0648\u0631",
                "\u0645\u062c\u0644\u0629",
                "constitution tunisienne",
                "code civil",
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
            if "constitution" in lowered or "\u0627\u0644\u062f\u0633\u062a\u0648\u0631" in lowered:
                return "Tunisian Constitution"
            if "code civil" in lowered:
                return "Code Civil"
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
    ) -> str:
        compact_sources = legal_sources[:8]
        compact_internal = internal_results[:4]

        if self.client:
            prompt = f"""
You are a legal copilot operating in jurisdiction-aware legal search mode.

Rules:
- Use only the provided legal sources as legal citations.
- Never fabricate legal articles, sections, or citations.
- If source evidence is partial, explicitly state uncertainty.
- Keep answer concise and professional.
- Write the answer in language code: {user_language}.
- If include_english_summary is true, add a short English summary as the final line.

Jurisdiction: {self.COUNTRY_DISPLAY.get(country, country.title())}
User query: {query}
include_english_summary: {str(include_english_summary).lower()}

Legal sources JSON:
{compact_sources}

Internal case retrieval JSON (context only):
{compact_internal}
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
        return fallback

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
            prompt = (
                "No direct legal source was retrieved for this question.\n"
                f"Provide concise legal reasoning based on general legal principles for {self.COUNTRY_DISPLAY.get(country, country)}.\n"
                "Do not fabricate article numbers.\n"
                "State uncertainty clearly.\n\n"
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
            "General legal reasoning (Tunisia): assess the issue under applicable Tunisian constitutional and code-based "
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
    def _to_source_line(item: Dict[str, Any]) -> str:
        reference = str(item.get("reference") or "").strip()
        title = str(item.get("title") or "Legal source").strip()
        url = str(item.get("url") or "").strip()
        if reference and url:
            return f"{reference} - {title} ({url})"
        if reference:
            return f"{reference} - {title}"
        if url:
            return f"{title} ({url})"
        return title

    def _to_api_sources(self, items: List[Dict[str, Any]], fallback_score: float = 0.55) -> List[Dict[str, Any]]:
        sources: List[Dict[str, Any]] = []
        for item in items[:12]:
            snippet = str(item.get("snippet") or item.get("chunk_text") or "").strip()
            title = str(item.get("title") or item.get("filename") or "Legal Source").strip()
            url = str(item.get("url") or "").strip()
            score = float(item.get("score", fallback_score))
            source_type = str(item.get("source_type") or "internal_chunk").strip()
            reference = str(item.get("reference") or "").strip()

            meta_parts = [f"source_type={source_type}"]
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
            snippet_text = snippet[:220]
            if url:
                snippet_text = f"{snippet_text} ({url})".strip()
            citations.append(
                {
                    "label": reference,
                    "document_id": item.get("document_id"),
                    "case_id": item.get("case_id"),
                    "snippet": snippet_text,
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

    @staticmethod
    def _format_legal_search_output(
        *,
        country: str,
        source_lines: List[str],
        answer_body: str,
        fallback_notice: Optional[str],
    ) -> str:
        lines = ["[Legal Source Answer]", f"- Country: {country}", "- Sources:"]
        if source_lines:
            lines.extend(f"    - {item}" for item in source_lines[:8])
        else:
            lines.append("    - None (no direct legal source retrieved)")
        lines.extend(["", "[Answer]", (answer_body or "No answer could be generated.").strip()])
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
