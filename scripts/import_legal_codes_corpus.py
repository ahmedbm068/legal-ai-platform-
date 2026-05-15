"""Import Tunisian legal codes from PDF into the local JSON corpus.

Extracts text with PyMuPDF (clean Unicode, unlike pypdf on these scanned-but-
text-layered PDFs), splits each document into article-level chunks, and tags
each chunk with the correct code family.

Key design notes
----------------
* ``Code du Statut Personnel`` is treated as its own family
  (``code_personnel_status``) rather than being conflated with
  ``code_succession``. The CSP covers marriage, divorce, filiation, tutelle
  AND succession; lumping it under "succession" was the bug that broke
  every marriage-law query.
* Detection runs filename FIRST then text markers, with the most specific
  family checked first, so a file named ``code du statut personnel.pdf``
  is never mistaken for the succession code.
* Article-level chunking is the goal (one entry per article). The
  structural fallback only fires when fewer than ``SPARSE_ARTICLE_THRESHOLD``
  article headers are found — a defensive guard for tables of contents.
"""

from __future__ import annotations

import argparse
import json
import re
import unicodedata
from collections import Counter
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

import fitz  # PyMuPDF


# ─────────────────────────────────────────────────────────────────────────────
# Regex
# ─────────────────────────────────────────────────────────────────────────────
# Match Article / Art. / Art. 1er / Article Premier / الفصل ١ / الفصل الأول
ARTICLE_HEADER_RE = re.compile(
    r"(?im)^\s*(?:article|art\.?|الفصل)"
    r"\s+"
    r"(?:"
    r"premier|1\s*er|"                              # "Premier" / "1er"
    r"[0-9]{1,4}(?:\s*(?:bis|ter|quater))?|"        # 1, 2, 17 bis
    r"[٠-٩]{1,4}|"                        # Arabic-Indic digits
    r"الأول"               # الأول
    r")"
    r"\b[^\n]*"
)
STRUCTURE_HEADER_RE = re.compile(
    r"(?im)^\s*(livre|titre|chapitre|section|sous[\s\-]?section|partie)"
    r"\s+([0-9ivxlcdm]+|premier|unique|[٠-٩]+)\b[^\n]*"
)
WORD_RE = re.compile(r"[a-z]{4,}")

SPARSE_ARTICLE_THRESHOLD = 10
MIN_STRUCTURE_BODY_LENGTH = 120
MIN_ARTICLE_BODY_LENGTH = 25


STOPWORDS = {
    "avec", "aussi", "avoir", "cette", "code", "dans", "dont", "elle",
    "elles", "etre", "fait", "font", "pour", "plus", "sans", "sont",
    "tous", "toute", "toutes", "leurs", "leur", "ainsi", "comme", "entre",
    "moins", "partie", "parties", "article", "titre", "section",
    "chapitre", "civil", "droit", "peut", "doit", "sera", "sous", "tout",
}


# ─────────────────────────────────────────────────────────────────────────────
# Code-family configuration
# ─────────────────────────────────────────────────────────────────────────────
# IMPORTANT: order matters in _detect_code_family — more specific patterns
# must come first. The CSP filename ("statut personnel") contains the word
# "personnel", so its check must precede any broader family that also
# mentions inheritance markers.
FAMILY_CONFIG: Dict[str, Dict[str, Any]] = {
    "code_personnel_status": {
        "label": "Code du Statut Personnel",
        # Filename patterns and unambiguous text markers for the CSP
        "filename_markers": ["statut personnel", "ahwal shakhsiya"],
        "text_markers": ["code du statut personnel", "livre premier du mariage"],
        "keywords": [
            "statut personnel", "mariage", "divorce", "filiation",
            "tutelle", "succession", "famille",
        ],
        "tags": ["family-law", "personal-status", "marriage", "succession"],
    },
    "code_international_prive": {
        "label": "Code International Prive",
        "filename_markers": ["international", "international prive"],
        "text_markers": ["droit international prive", "conflit de lois", "exequatur"],
        "keywords": [
            "conflict of laws", "private international law",
            "foreign judgment", "jurisdiction",
        ],
        "tags": ["private-international-law"],
    },
    "code_succession": {
        # Kept as a separate family ONLY if a dedicated succession code PDF
        # is ever ingested in isolation. The CSP's succession chapters
        # belong under code_personnel_status because that's where Tunisian
        # law actually places them.
        "label": "Code de Succession",
        "filename_markers": ["code de succession", "succession"],
        "text_markers": ["code de succession"],
        "keywords": ["succession", "inheritance", "estate", "heirs", "testament"],
        "tags": ["family-law", "inheritance"],
    },
    "code_civil": {
        "label": "Code Civil",
        "filename_markers": ["code civil", "procedure civile", "procedure commerciale"],
        "text_markers": ["code des obligations", "obligations et des contrats"],
        "keywords": ["contract", "obligation", "liability", "procedure", "civil"],
        "tags": ["private-law", "civil"],
    },
}


# ─────────────────────────────────────────────────────────────────────────────
# Text helpers
# ─────────────────────────────────────────────────────────────────────────────
def _normalize_text(text: str) -> str:
    normalized = str(text or "").replace(" ", " ")
    # Strip stray control characters left behind by some PDF extractors.
    normalized = "".join(
        ch for ch in normalized
        if ch == "\n" or ch == "\t" or ord(ch) >= 0x20
    )
    normalized = re.sub(r"[ \t]+", " ", normalized)
    normalized = re.sub(r"\n{3,}", "\n\n", normalized)
    return normalized.strip()


def _fold_text(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", str(text or ""))
    return "".join(ch for ch in normalized if not unicodedata.combining(ch)).lower()


def _detect_code_family(file_name: str, sample_text: str) -> str:
    """Return the family key. Filename signals win over text signals."""
    name = _fold_text(file_name)
    text = _fold_text(sample_text)

    # First pass: filename markers (highest precision)
    for family, cfg in FAMILY_CONFIG.items():
        for marker in cfg.get("filename_markers", []):
            if _fold_text(marker) in name:
                return family

    # Second pass: in-document text markers
    for family, cfg in FAMILY_CONFIG.items():
        for marker in cfg.get("text_markers", []):
            if _fold_text(marker) in text:
                return family

    # Default
    return "code_civil"


# ─────────────────────────────────────────────────────────────────────────────
# PDF extraction (PyMuPDF — clean Unicode for accented French / Arabic)
# ─────────────────────────────────────────────────────────────────────────────
def _extract_pdf_text(pdf_path: Path) -> str:
    pages: List[str] = []
    with fitz.open(str(pdf_path)) as doc:
        for page in doc:
            raw = page.get_text("text") or ""
            cleaned = _normalize_text(raw)
            if cleaned:
                pages.append(cleaned)
    return "\n\n".join(pages)


# ─────────────────────────────────────────────────────────────────────────────
# Chunking
# ─────────────────────────────────────────────────────────────────────────────
def _iter_article_chunks(text: str) -> Iterable[Tuple[str, str]]:
    """Yield (header, body) tuples, one per article.

    Many Tunisian codes put the article number, colon, and rule text on a
    single line (``Art. 18 : La polygamie est interdite.``). The header is
    everything up to (and including) the colon; the body is the rest of the
    paragraph plus any following lines until the next article.
    """
    matches = list(ARTICLE_HEADER_RE.finditer(text))
    chunks: List[Tuple[str, str]] = []
    for index, match in enumerate(matches):
        start = match.start()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        segment = _normalize_text(text[start:end])
        if not segment:
            continue
        # Prefer splitting on the first colon (covers the "Art. N : body" form).
        # Fall back to first newline if no colon is present in the first line.
        first_line, _, after_colon = segment.partition(":")
        if after_colon and len(first_line) < 80:
            heading = _normalize_text(first_line + ":")
            body = _normalize_text(after_colon)
        else:
            lines = segment.splitlines()
            heading = _normalize_text(lines[0])
            body = _normalize_text("\n".join(lines[1:]))
        if len(body) < MIN_ARTICLE_BODY_LENGTH:
            continue
        chunks.append((heading, body))
    return chunks


def _iter_structural_chunks(text: str) -> Iterable[Tuple[str, str]]:
    matches = list(STRUCTURE_HEADER_RE.finditer(text))
    chunks: List[Tuple[str, str]] = []
    for index, match in enumerate(matches):
        start = match.start()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        segment = _normalize_text(text[start:end])
        if not segment:
            continue
        lines = [line.strip() for line in segment.splitlines() if line.strip()]
        if not lines:
            continue
        first_line = _normalize_text(lines[0])
        body = _normalize_text("\n".join(lines[1:]))
        if len(body) < MIN_STRUCTURE_BODY_LENGTH:
            continue
        chunks.append((first_line, body))
    return chunks


def _select_chunks_for_document(text: str) -> List[Tuple[str, str]]:
    # Normalize once up front so the regex and chunker see clean text.
    text = _normalize_text(text)
    article_chunks = list(_iter_article_chunks(text))
    if len(article_chunks) >= SPARSE_ARTICLE_THRESHOLD:
        return article_chunks
    structural_chunks = list(_iter_structural_chunks(text))
    return article_chunks if len(article_chunks) >= len(structural_chunks) else structural_chunks


# ─────────────────────────────────────────────────────────────────────────────
# Entry construction
# ─────────────────────────────────────────────────────────────────────────────
def _extract_keywords(text: str, family: str, max_keywords: int = 10) -> List[str]:
    counts: Counter[str] = Counter()
    for token in WORD_RE.findall(text.lower()):
        if token in STOPWORDS:
            continue
        counts[token] += 1
    ranked = [item[0] for item in counts.most_common(max_keywords)]
    seeded = FAMILY_CONFIG[family]["keywords"]
    merged: List[str] = []
    for token in [*seeded, *ranked]:
        candidate = str(token).strip().lower()
        if candidate and candidate not in merged:
            merged.append(candidate)
    return merged[:max_keywords]


def _normalize_article_ref(heading: str) -> str:
    """Return a canonical article reference like 'Article 18' from a heading."""
    raw = _normalize_text(heading)
    if not raw:
        return raw
    # French
    m = re.search(
        r"(?i)(?:article|art\.?)\s+(premier|1\s*er|[0-9]{1,4}(?:\s*(?:bis|ter|quater))?)",
        raw,
    )
    if m:
        num = m.group(1).strip()
        if num.lower() in {"premier", "1er", "1 er"}:
            num = "Premier"
        return f"Article {num}"
    # Arabic
    m = re.search(r"(الفصل)\s+([٠-٩]+|الأول)", raw)
    if m:
        return f"الفصل {m.group(2).strip()}"
    return raw


def _build_entry(
    *,
    country: str,
    family: str,
    file_name: str,
    heading: str,
    body: str,
) -> Dict[str, Any]:
    heading_clean = _normalize_text(heading)
    body_clean = _normalize_text(body)
    article_ref = _normalize_article_ref(heading_clean)

    label = FAMILY_CONFIG[family]["label"]
    title = f"{label} - {article_ref}"
    summary = _normalize_text((body_clean or heading_clean)[:480])
    keywords = _extract_keywords(f"{heading_clean} {body_clean}", family)
    tags = [family, "local-legal-code", *FAMILY_CONFIG[family]["tags"]]

    return {
        "country": country,
        "code_family": family,
        "code_name": label,
        "article": article_ref,
        "title": title,
        "summary": summary,
        "keywords": keywords,
        "tags": tags,
        "url": "",
        "source_filename": file_name,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Driver
# ─────────────────────────────────────────────────────────────────────────────
def build_corpus_from_dir(input_dir: Path, country: str) -> Dict[str, List[Dict[str, Any]]]:
    pdf_files = sorted(input_dir.glob("*.pdf"))
    entries: List[Dict[str, Any]] = []
    stats: Counter[str] = Counter()

    for pdf_path in pdf_files:
        text = _extract_pdf_text(pdf_path)
        if not text:
            print(f"  ! {pdf_path.name}: empty text after extraction")
            continue

        family = _detect_code_family(pdf_path.name, text[:4000])
        chunks = _select_chunks_for_document(text)
        if not chunks:
            print(f"  ! {pdf_path.name}: no chunks extracted")
            continue

        for heading, body in chunks:
            entries.append(_build_entry(
                country=country,
                family=family,
                file_name=pdf_path.name,
                heading=heading,
                body=body,
            ))
        stats[family] += len(chunks)
        print(f"  • {pdf_path.name} -> family={family}  chunks={len(chunks)}")

    print(f"\nTotals by family: {dict(stats)}")
    return {country: entries}


def main() -> None:
    parser = argparse.ArgumentParser(description="Import legal codes from PDF files into a local JSON corpus.")
    parser.add_argument(
        "--input-dir",
        type=Path,
        default=Path(r"C:\Users\ahmed\Downloads\code"),
        help="Directory containing legal code PDFs.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("backend/services/ai/data/legal_codes_corpus.json"),
        help="Output corpus JSON path.",
    )
    parser.add_argument("--country", type=str, default="tunisia")
    parser.add_argument(
        "--merge",
        action="store_true",
        help="Merge into the existing output file instead of overwriting (preserves other countries).",
    )
    args = parser.parse_args()

    input_dir = args.input_dir.resolve()
    if not input_dir.exists() or not input_dir.is_dir():
        raise SystemExit(f"Input directory not found: {input_dir}")

    country = args.country.strip().lower()
    print(f"Importing PDFs from {input_dir} as country={country}")
    corpus = build_corpus_from_dir(input_dir=input_dir, country=country)

    output_path = args.output.resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if args.merge and output_path.exists():
        with output_path.open(encoding="utf-8") as fh:
            existing = json.load(fh)
        if not isinstance(existing, dict):
            existing = {}
        existing[country] = corpus[country]
        merged = existing
    else:
        merged = corpus

    output_path.write_text(json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8")
    count = len(merged.get(country, []))
    print(f"\nWrote {count} {country} entries to {output_path}")


if __name__ == "__main__":
    main()
