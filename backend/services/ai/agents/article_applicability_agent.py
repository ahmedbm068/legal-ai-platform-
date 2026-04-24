from __future__ import annotations

import re
from typing import Any

from backend.services.ai.agents.base_agent import BaseAgent, AgentResult


ARTICLE_PATTERN = re.compile(
    r"\b(?:article|art\.?|section|§)\s*([0-9]+(?:[-\.][0-9]+)?[a-zA-Z]?)\b",
    flags=re.IGNORECASE,
)
TOKEN_REGEX = re.compile(r"\b\w+\b")
STOPWORDS = {
    "the", "and", "for", "with", "that", "this", "from", "case", "document",
    "article", "section", "under", "legal", "rule", "facts", "may", "must",
    "shall", "would", "could", "should", "provided", "source",
}


class ArticleApplicabilityAgent(BaseAgent):
    agent_name = "article_applicability_agent"

    @staticmethod
    def _source_text(source: dict[str, Any]) -> str:
        return str(source.get("chunk_text") or source.get("snippet") or source.get("short_relevant_excerpt") or "").strip()

    @staticmethod
    def _source_label(source: dict[str, Any]) -> str:
        label = str(source.get("filename") or source.get("label") or "Source").strip()
        chunk_index = source.get("chunk_index")
        if isinstance(chunk_index, int):
            return f"{label} - chunk {chunk_index}"
        return label

    @staticmethod
    def _tokens(value: str) -> set[str]:
        return {
            token.lower()
            for token in TOKEN_REGEX.findall(str(value or ""))
            if len(token) > 2 and token.lower() not in STOPWORDS
        }

    @staticmethod
    def _code_family(source: dict[str, Any], text: str) -> str:
        combined = f"{source.get('filename') or ''} {source.get('label') or ''} {text}".lower()
        if "succession" in combined or "inheritance" in combined:
            return "succession"
        if "international" in combined or "conflit" in combined or "conflict of laws" in combined:
            return "international_private_law"
        if "civil" in combined or "obligation" in combined or "contract" in combined:
            return "civil_obligations"
        return "unknown"

    @staticmethod
    def _quote_for_article(text: str, match: re.Match[str]) -> str:
        start = max(0, match.start() - 120)
        end = min(len(text), match.end() + 360)
        return re.sub(r"\s+", " ", text[start:end]).strip()

    def review(
        self,
        *,
        issue: str,
        application: str,
        sources: list[dict[str, Any]],
    ) -> AgentResult:
        issue_tokens = self._tokens(f"{issue} {application}")
        rows: list[dict[str, Any]] = []
        rejected: list[dict[str, Any]] = []

        for source in sources or []:
            if not isinstance(source, dict):
                continue
            text = self._source_text(source)
            if not text:
                continue
            for match in ARTICLE_PATTERN.finditer(f"{self._source_label(source)}\n{text}"):
                article_id = match.group(1)
                source_tokens = self._tokens(text)
                overlap = len(issue_tokens.intersection(source_tokens)) / float(max(len(issue_tokens), 1))
                quote = self._quote_for_article(text, match) if match.start() < len(text) else text[:420]
                payload = {
                    "article_id": article_id,
                    "source_label": self._source_label(source),
                    "document_id": source.get("document_id") if isinstance(source.get("document_id"), int) else None,
                    "chunk_id": source.get("chunk_id") if isinstance(source.get("chunk_id"), int) else None,
                    "code_family": self._code_family(source, text),
                    "exact_quote": quote,
                    "applicability_score": round(max(0.0, min(overlap, 1.0)), 4),
                    "applicability": "MAY_APPLY" if overlap >= 0.14 else "NEEDS_MORE_FACTS",
                    "reason": (
                        "Article text overlaps with the issue/application facts."
                        if overlap >= 0.14
                        else "Article was retrieved, but factual overlap is weak; lawyer must verify applicability."
                    ),
                }
                if overlap >= 0.08:
                    rows.append(payload)
                else:
                    rejected.append({**payload, "applicability": "NOT_ENOUGH_SUPPORT"})

        rows = rows[:8]
        rejected = rejected[:8]
        has_article_source = bool(rows or rejected)
        confidence = 0.0
        if rows:
            confidence = min(1.0, max(item["applicability_score"] for item in rows) + 0.25)

        return self.result(
            success=True,
            payload={
                "status": "ARTICLE_SOURCES_FOUND" if has_article_source else "NO_ARTICLE_SOURCE_FOUND",
                "applicable_articles": rows,
                "rejected_articles": rejected,
                "code_family_confidence": round(confidence, 4),
                "message": (
                    "Article-level sources found and classified."
                    if has_article_source
                    else "No article-level source found in retrieved evidence."
                ),
            },
            trace=[f"Article applicability reviewed {len(sources or [])} source(s); applicable={len(rows)}, rejected={len(rejected)}."],
        )


article_applicability_agent = ArticleApplicabilityAgent()
