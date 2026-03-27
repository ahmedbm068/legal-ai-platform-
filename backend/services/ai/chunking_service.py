from __future__ import annotations

import re
from typing import List


CLAUSE_HEADING_PATTERN = re.compile(
    r"^\s*(?:"
    r"\d+(?:\.\d+)*[.)]?"           # 1 / 1.1 / 1.1.2 / 1)
    r"|[A-Z][.)]"                   # A) / B.
    r"|ARTICLE\s+\d+"               # ARTICLE 1
    r"|SECTION\s+\d+"               # SECTION 2
    r"|CLAUSE\s+\d+"                # CLAUSE 3
    r")\s+",
    re.IGNORECASE
)


def _normalize_text(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _split_paragraphs(text: str) -> List[str]:
    """
    Split text while trying to preserve legal structure.
    We first split on blank lines, then further split overly long blocks
    on line boundaries when they look like legal headings.
    """
    raw_blocks = [block.strip() for block in re.split(r"\n\s*\n", text) if block.strip()]
    paragraphs: List[str] = []

    for block in raw_blocks:
        lines = [line.strip() for line in block.split("\n") if line.strip()]
        if not lines:
            continue

        current: List[str] = []

        for line in lines:
            if current and CLAUSE_HEADING_PATTERN.match(line):
                paragraphs.append(" ".join(current).strip())
                current = [line]
            else:
                current.append(line)

        if current:
            paragraphs.append(" ".join(current).strip())

    return [p for p in paragraphs if p]


def _split_large_paragraph(paragraph: str, max_size: int) -> List[str]:
    """
    If a single paragraph is too large, split it by sentence boundaries.
    If sentence splitting still fails, do a hard character split.
    """
    if len(paragraph) <= max_size:
        return [paragraph]

    sentence_parts = re.split(r"(?<=[\.\!\?\:;])\s+", paragraph)
    sentence_parts = [part.strip() for part in sentence_parts if part.strip()]

    if not sentence_parts:
        return [paragraph[i:i + max_size].strip() for i in range(0, len(paragraph), max_size)]

    chunks: List[str] = []
    current = ""

    for sentence in sentence_parts:
        candidate = sentence if not current else f"{current} {sentence}"
        if len(candidate) <= max_size:
            current = candidate
        else:
            if current:
                chunks.append(current.strip())

            if len(sentence) <= max_size:
                current = sentence
            else:
                hard_splits = [
                    sentence[i:i + max_size].strip()
                    for i in range(0, len(sentence), max_size)
                    if sentence[i:i + max_size].strip()
                ]
                chunks.extend(hard_splits[:-1])
                current = hard_splits[-1] if hard_splits else ""

    if current.strip():
        chunks.append(current.strip())

    return chunks


def _take_tail_by_word_boundary(text: str, overlap: int) -> str:
    if overlap <= 0 or len(text) <= overlap:
        return text.strip()

    tail = text[-overlap:]
    first_space = tail.find(" ")
    if first_space != -1 and first_space < len(tail) - 1:
        tail = tail[first_space + 1:]

    return tail.strip()


def chunk_text(text: str, chunk_size: int = 1000, overlap: int = 180) -> List[str]:
    """
    Chunk legal text while preserving paragraph and clause structure as much as possible.

    Improvements over the old version:
    - better paragraph splitting
    - better handling of legal headings
    - better handling of oversized paragraphs
    - safer overlap on word boundaries
    - avoids tiny broken chunks
    """
    if not text or not text.strip():
        return []

    if chunk_size <= 0:
        raise ValueError("chunk_size must be greater than 0")

    if overlap < 0:
        raise ValueError("overlap cannot be negative")

    if overlap >= chunk_size:
        overlap = max(0, chunk_size // 4)

    normalized = _normalize_text(text)
    paragraphs = _split_paragraphs(normalized)

    expanded_paragraphs: List[str] = []
    for paragraph in paragraphs:
        expanded_paragraphs.extend(_split_large_paragraph(paragraph, chunk_size))

    if not expanded_paragraphs:
        return []

    chunks: List[str] = []
    current = ""

    for paragraph in expanded_paragraphs:
        candidate = paragraph if not current else f"{current}\n\n{paragraph}"

        if len(candidate) <= chunk_size:
            current = candidate
            continue

        if current.strip():
            chunks.append(current.strip())

        if overlap > 0 and chunks:
            tail = _take_tail_by_word_boundary(chunks[-1], overlap)
            with_overlap = f"{tail}\n\n{paragraph}".strip()
            if len(with_overlap) <= chunk_size:
                current = with_overlap
            else:
                current = paragraph
        else:
            current = paragraph

    if current.strip():
        chunks.append(current.strip())

    # Remove accidental duplicates / empty chunks
    final_chunks: List[str] = []
    for chunk in chunks:
        cleaned = chunk.strip()
        if cleaned and (not final_chunks or final_chunks[-1] != cleaned):
            final_chunks.append(cleaned)

    return final_chunks