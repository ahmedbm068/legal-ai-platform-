from __future__ import annotations

import math
import re
from collections import Counter, defaultdict
from typing import Any, Dict, List, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.models.document import Document
from backend.models.document_chunk import DocumentChunk


TOKEN_PATTERN = re.compile(r"\w+", re.UNICODE)


def _tokenize(text: str) -> List[str]:
    if not text:
        return []
    return TOKEN_PATTERN.findall(text.lower())


def _build_snippet(content: str, query: str, max_chars: int = 240) -> str:
    if not content:
        return ""

    query_lower = query.strip().lower()
    content_lower = content.lower()

    idx = content_lower.find(query_lower) if query_lower else -1

    if idx >= 0:
        start = max(0, idx - 80)
        end = min(len(content), idx + len(query) + 80)
        snippet = content[start:end]
    else:
        snippet = content[:max_chars]

    return " ".join(snippet.split())


def _bm25_score(
    query_tokens: List[str],
    doc_tokens: List[str],
    doc_freqs: Dict[str, int],
    corpus_doc_freq: Dict[str, int],
    total_docs: int,
    avg_doc_len: float,
    k1: float = 1.5,
    b: float = 0.75,
) -> float:
    if not doc_tokens or not query_tokens or total_docs == 0 or avg_doc_len == 0:
        return 0.0

    score = 0.0
    doc_len = len(doc_tokens)

    for token in query_tokens:
        if token not in doc_freqs:
            continue

        tf = doc_freqs[token]
        df = corpus_doc_freq.get(token, 0)

        idf = math.log(1 + ((total_docs - df + 0.5) / (df + 0.5)))
        numerator = tf * (k1 + 1)
        denominator = tf + k1 * (1 - b + b * (doc_len / avg_doc_len))

        score += idf * (numerator / denominator)

    return float(score)


def search_chunks_lexically(
    db: Session,
    tenant_id: Optional[int],
    query: str,
    top_k: int = 5,
    case_id: Optional[int] = None,
    document_id: Optional[int] = None,
) -> List[Dict[str, Any]]:
    normalized_query = query.strip()
    if not normalized_query:
        return []

    postgres_results = _search_chunks_postgres(
        db=db,
        tenant_id=tenant_id,
        query=normalized_query,
        top_k=top_k,
        case_id=case_id,
        document_id=document_id,
    )
    if postgres_results:
        return postgres_results

    rows_query = db.query(DocumentChunk, Document).join(Document, Document.id == DocumentChunk.document_id)

    if tenant_id is not None:
        rows_query = rows_query.filter(DocumentChunk.tenant_id == tenant_id).filter(Document.tenant_id == tenant_id)

    if case_id is not None:
        rows_query = rows_query.filter(DocumentChunk.case_id == case_id)

    if document_id is not None:
        rows_query = rows_query.filter(DocumentChunk.document_id == document_id)

    rows = rows_query.all()

    if not rows:
        return []

    query_tokens = _tokenize(normalized_query)
    if not query_tokens:
        return []

    corpus_doc_freq = defaultdict(int)
    prepared_docs = []

    for chunk, document in rows:
        doc_tokens = _tokenize(chunk.content)
        token_counts = Counter(doc_tokens)

        for token in set(doc_tokens):
            corpus_doc_freq[token] += 1

        prepared_docs.append({
            "chunk": chunk,
            "document": document,
            "tokens": doc_tokens,
            "token_counts": token_counts,
        })

    total_docs = len(prepared_docs)
    avg_doc_len = sum(len(item["tokens"]) for item in prepared_docs) / max(total_docs, 1)

    scored_results = []

    for item in prepared_docs:
        chunk = item["chunk"]
        document = item["document"]
        doc_tokens = item["tokens"]
        token_counts = item["token_counts"]

        bm25_score = _bm25_score(
            query_tokens=query_tokens,
            doc_tokens=doc_tokens,
            doc_freqs=token_counts,
            corpus_doc_freq=corpus_doc_freq,
            total_docs=total_docs,
            avg_doc_len=avg_doc_len,
        )

        if bm25_score <= 0:
            continue

        scored_results.append({
            "chunk_id": chunk.id,
            "document_id": document.id,
            "case_id": chunk.case_id,
            "filename": document.filename,
            "chunk_index": chunk.chunk_index,
            "chunk_text": chunk.content,
            "score": bm25_score,
            "bm25_score": bm25_score,
            "semantic_score": 0.0,
            "retrieval_method": "lexical",
            "matched_text": _build_snippet(chunk.content, normalized_query),
        })

    scored_results.sort(key=lambda item: item["score"], reverse=True)
    return scored_results[:top_k]


def lexical_search_documents(
    db: Session,
    tenant_id: Optional[int],
    query: str,
    top_k: int = 5,
    case_id: Optional[int] = None,
    document_id: Optional[int] = None,
) -> List[Dict[str, Any]]:
    results = search_chunks_lexically(
        db=db,
        tenant_id=tenant_id,
        query=query,
        top_k=top_k,
        case_id=case_id,
        document_id=document_id,
    )

    return [
        {
            "document_id": item["document_id"],
            "filename": item["filename"],
            "matched_text": item["matched_text"],
        }
        for item in results
    ]


def _search_chunks_postgres(
    *,
    db: Session,
    tenant_id: int | None,
    query: str,
    top_k: int,
    case_id: int | None,
    document_id: int | None,
) -> list[dict[str, Any]]:
    bind = db.get_bind()
    if bind is None or bind.dialect.name != "postgresql":
        return []

    statement = text(
        """
        SELECT
            dc.id AS chunk_id,
            dc.document_id AS document_id,
            dc.case_id AS case_id,
            d.filename AS filename,
            dc.chunk_index AS chunk_index,
            dc.content AS chunk_text,
            ts_rank_cd(
                to_tsvector('simple', COALESCE(dc.content, '')),
                websearch_to_tsquery('simple', :query)
            ) AS bm25_score
        FROM document_chunks dc
        INNER JOIN documents d ON d.id = dc.document_id
        WHERE (:tenant_id IS NULL OR dc.tenant_id = :tenant_id)
          AND (:case_id IS NULL OR dc.case_id = :case_id)
          AND (:document_id IS NULL OR dc.document_id = :document_id)
          AND to_tsvector('simple', COALESCE(dc.content, '')) @@ websearch_to_tsquery('simple', :query)
        ORDER BY bm25_score DESC, dc.id DESC
        LIMIT :top_k
        """
    )

    try:
        rows = db.execute(
            statement,
            {
                "tenant_id": tenant_id,
                "case_id": case_id,
                "document_id": document_id,
                "query": query,
                "top_k": max(1, int(top_k)),
            },
        ).mappings().all()
    except Exception:
        return []

    results = []
    for row in rows:
        bm25_score = float(row.get("bm25_score") or 0.0)
        chunk_text = str(row.get("chunk_text") or "")
        results.append(
            {
                "chunk_id": row.get("chunk_id"),
                "document_id": row.get("document_id"),
                "case_id": row.get("case_id"),
                "filename": row.get("filename") or "unknown",
                "chunk_index": row.get("chunk_index"),
                "chunk_text": chunk_text,
                "score": bm25_score,
                "bm25_score": bm25_score,
                "semantic_score": 0.0,
                "retrieval_method": "lexical",
                "matched_text": _build_snippet(chunk_text, query),
            }
        )
    return results
