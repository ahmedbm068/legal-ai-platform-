from __future__ import annotations

import re
from difflib import SequenceMatcher
from typing import Any

from backend.services.ai.agents.base_agent import BaseAgent, AgentResult
from backend.services.ai.legal_trust_models import (
    ClaimSupportStatus,
    ClaimValidationItem,
    EvidenceStrength,
    SentenceSourceMapping,
)


SENTENCE_SPLIT_REGEX = re.compile(r"(?<=[.!?])\s+|\n+")
TOKEN_REGEX = re.compile(r"\b\w+\b")
STOPWORDS = {
    "the",
    "and",
    "for",
    "with",
    "that",
    "this",
    "from",
    "have",
    "has",
    "into",
    "case",
    "document",
    "chunk",
    "are",
    "was",
    "were",
    "been",
    "will",
    "would",
    "shall",
    "about",
    "there",
    "their",
    "them",
    "they",
    "your",
    "you",
    "only",
    "using",
    "used",
    "than",
    "then",
    "when",
    "what",
    "which",
    "where",
    "while",
    "also",
    "under",
    "over",
    "more",
    "some",
    "such",
    "just",
    "into",
}


class ClaimValidationAgent(BaseAgent):
    agent_name = "claim_validation_agent"

    @staticmethod
    def _split_sentences(text: str) -> list[str]:
        rows = [part.strip() for part in SENTENCE_SPLIT_REGEX.split(str(text or "").strip())]
        normalized: list[str] = []
        for row in rows:
            cleaned = re.sub(r"^[-*\d\.)\s]+", "", row).strip()
            if len(cleaned) < 10:
                continue
            if cleaned not in normalized:
                normalized.append(cleaned)
        return normalized

    @staticmethod
    def _tokenize(text: str) -> set[str]:
        raw = {token.lower() for token in TOKEN_REGEX.findall(str(text or ""))}
        return {token for token in raw if len(token) > 2 and token not in STOPWORDS}

    @staticmethod
    def _source_snippet(source: dict[str, Any]) -> str:
        return str(
            source.get("snippet")
            or source.get("chunk_text")
            or source.get("short_relevant_excerpt")
            or ""
        ).strip()

    @staticmethod
    def _source_label(source: dict[str, Any]) -> str:
        filename = str(source.get("filename") or source.get("label") or source.get("source_identifier") or "Source").strip()
        chunk_index = source.get("chunk_index")
        if isinstance(chunk_index, int):
            return f"{filename} - chunk {chunk_index}"
        return filename

    @staticmethod
    def _coerce_score(source: dict[str, Any]) -> float:
        try:
            score = float(source.get("score", 0.0))
        except (TypeError, ValueError):
            score = 0.0
        if score > 1.0:
            score = score / 100.0
        return max(0.0, min(score, 1.0))

    @staticmethod
    def _best_overlap(sentence_tokens: set[str], snippet: str) -> float:
        if not sentence_tokens:
            return 0.0
        snippet_tokens = ClaimValidationAgent._tokenize(snippet)
        if not snippet_tokens:
            return 0.0
        overlap = len(sentence_tokens.intersection(snippet_tokens))
        return overlap / float(max(len(sentence_tokens), 1))

    @staticmethod
    def _quote_span(sentence: str, snippet: str) -> tuple[str, str]:
        normalized_sentence = str(sentence or "").strip()
        normalized_snippet = str(snippet or "").strip()
        if not normalized_sentence or not normalized_snippet:
            return "", ""

        matcher = SequenceMatcher(None, normalized_sentence.lower(), normalized_snippet.lower())
        match = matcher.find_longest_match(0, len(normalized_sentence), 0, len(normalized_snippet))
        if match.size >= 12:
            start = match.b
            end = match.b + match.size
            return f"{start}:{end}", normalized_snippet[start:end]

        sentence_tokens = [token for token in TOKEN_REGEX.findall(normalized_sentence) if len(token) >= 4]
        lowered_snippet = normalized_snippet.lower()
        for token in sentence_tokens:
            idx = lowered_snippet.find(token.lower())
            if idx >= 0:
                start = max(0, idx - 24)
                end = min(len(normalized_snippet), idx + max(len(token), 32))
                return f"{start}:{end}", normalized_snippet[start:end]
        return "", ""

    @staticmethod
    def _strength(overlap: float, source_score: float) -> EvidenceStrength:
        if overlap >= 0.55 or (overlap >= 0.40 and source_score >= 0.60):
            return EvidenceStrength.STRONG
        if overlap >= 0.32:
            return EvidenceStrength.MEDIUM
        if overlap >= 0.18:
            return EvidenceStrength.WEAK
        return EvidenceStrength.NONE

    @staticmethod
    def _support_status(strength: EvidenceStrength) -> ClaimSupportStatus:
        if strength == EvidenceStrength.STRONG:
            return ClaimSupportStatus.VERIFIED
        if strength in {EvidenceStrength.MEDIUM, EvidenceStrength.WEAK}:
            return ClaimSupportStatus.PARTIALLY_SUPPORTED
        return ClaimSupportStatus.UNSUPPORTED

    def validate(
        self,
        *,
        answer: str,
        sources: list[dict[str, Any]],
        not_found_message: str = "Not found in provided documents",
    ) -> AgentResult:
        sentences = self._split_sentences(answer)
        if not sentences:
            return self.result(
                success=False,
                error="No sentences found in answer.",
                trace=["Claim validation skipped because answer had no valid sentences."],
            )

        normalized_sources = [item for item in (sources or []) if isinstance(item, dict)]
        mappings: list[SentenceSourceMapping] = []
        verified_claims: list[ClaimValidationItem] = []
        partially_supported_claims: list[ClaimValidationItem] = []
        unsupported_claims: list[ClaimValidationItem] = []

        for sentence in sentences:
            sentence_tokens = self._tokenize(sentence)
            best_source: dict[str, Any] | None = None
            best_overlap = 0.0
            for source in normalized_sources:
                snippet = self._source_snippet(source)
                overlap = self._best_overlap(sentence_tokens, snippet)
                if overlap > best_overlap:
                    best_overlap = overlap
                    best_source = source

            if best_source is None:
                mapping = SentenceSourceMapping(
                    sentence=sentence,
                    source_label="No matching source",
                    document_id=None,
                    chunk_id=None,
                    chunk_index=None,
                    exact_quote_span="",
                    quote="",
                    evidence_strength=EvidenceStrength.NONE,
                )
            else:
                snippet = self._source_snippet(best_source)
                quote_span, quote = self._quote_span(sentence, snippet)
                source_score = self._coerce_score(best_source)
                strength = self._strength(best_overlap, source_score)
                mapping = SentenceSourceMapping(
                    sentence=sentence,
                    source_label=self._source_label(best_source),
                    document_id=best_source.get("document_id") if isinstance(best_source.get("document_id"), int) else None,
                    chunk_id=best_source.get("chunk_id") if isinstance(best_source.get("chunk_id"), int) else None,
                    chunk_index=best_source.get("chunk_index") if isinstance(best_source.get("chunk_index"), int) else None,
                    exact_quote_span=quote_span,
                    quote=quote,
                    evidence_strength=strength,
                )

            mappings.append(mapping)
            status = self._support_status(mapping.evidence_strength)
            claim_item = ClaimValidationItem(
                claim=sentence,
                support_status=status,
                evidence_strength=mapping.evidence_strength,
                mappings=[mapping],
                note=("" if status != ClaimSupportStatus.UNSUPPORTED else not_found_message),
            )
            if status == ClaimSupportStatus.UNSUPPORTED:
                unsupported_claims.append(claim_item)
            elif status == ClaimSupportStatus.PARTIALLY_SUPPORTED:
                partially_supported_claims.append(claim_item)
                verified_claims.append(claim_item)
            else:
                verified_claims.append(claim_item)

        total_claims = len(mappings)
        mapped_claims = sum(1 for row in mappings if row.evidence_strength != EvidenceStrength.NONE)
        citation_coverage = (mapped_claims / float(total_claims)) if total_claims else 0.0
        hallucination_rate = (len(unsupported_claims) / float(total_claims)) if total_claims else 1.0

        strength_counts = {
            EvidenceStrength.STRONG.value: 0,
            EvidenceStrength.MEDIUM.value: 0,
            EvidenceStrength.WEAK.value: 0,
            EvidenceStrength.NONE.value: 0,
        }
        for row in mappings:
            strength_counts[row.evidence_strength.value] += 1

        strongest_bucket = max(strength_counts.items(), key=lambda item: item[1])[0] if strength_counts else EvidenceStrength.NONE.value

        return self.result(
            success=True,
            payload={
                "sentence_to_source_mapping": [row.model_dump(mode="json") for row in mappings],
                "verified_claims": [row.model_dump(mode="json") for row in verified_claims],
                "partially_supported_claims": [row.model_dump(mode="json") for row in partially_supported_claims],
                "unsupported_claims": [row.model_dump(mode="json") for row in unsupported_claims],
                "citation_coverage": round(citation_coverage, 4),
                "hallucination_rate": round(hallucination_rate, 4),
                "total_claims": total_claims,
                "mapped_claims": mapped_claims,
                "evidence_strength_counts": strength_counts,
                "dominant_evidence_strength": strongest_bucket,
            },
            warnings=(["Some claims were not mapped to evidence."] if unsupported_claims else []),
            trace=[
                f"Validated {total_claims} claim sentence(s) against {len(normalized_sources)} source chunk(s).",
            ],
        )


claim_validation_agent = ClaimValidationAgent()
