from __future__ import annotations

import argparse
import json
import re
import unicodedata
from collections import Counter
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

from pypdf import PdfReader

ARTICLE_HEADER_RE = re.compile(
    r"(?im)^\s*(article|\u0627\u0644\u0641\u0635\u0644)\s+([0-9]{1,4}(?:\s*(?:bis|ter))?|premier)\b[^\n]*"
)
STRUCTURE_HEADER_RE = re.compile(
    r"(?im)^\s*(livre|titre|chapitre|section|sous[\s\-]?section|partie)\s+([0-9ivxlcdm]+|premier|unique)\b[^\n]*"
)
WORD_RE = re.compile(r"[a-z]{4,}")
SPARSE_ARTICLE_THRESHOLD = 20
MIN_STRUCTURE_BODY_LENGTH = 120

STOPWORDS = {
    "avec",
    "aussi",
    "avoir",
    "cette",
    "code",
    "dans",
    "dont",
    "elle",
    "elles",
    "etre",
    "fait",
    "font",
    "pour",
    "plus",
    "sans",
    "sont",
    "tous",
    "toute",
    "toutes",
    "leurs",
    "leur",
    "ainsi",
    "comme",
    "entre",
    "moins",
    "partie",
    "parties",
    "article",
    "titre",
    "section",
    "chapitre",
    "code",
    "civil",
    "droit",
    "peut",
    "doit",
    "etre",
    "sera",
    "sous",
    "dans",
    "tout",
    "toute",
}

FAMILY_CONFIG: Dict[str, Dict[str, Any]] = {
    "code_civil": {
        "label": "Code Civil",
        "markers": ["procedure", "civile", "commerciale", "contrat", "obligation"],
        "keywords": ["contract", "obligation", "liability", "procedure", "civil"],
        "tags": ["private-law", "civil"],
    },
    "code_succession": {
        "label": "Code de Succession",
        "markers": ["succession", "heritage", "heritier", "testament", "statut personnel"],
        "keywords": ["succession", "inheritance", "estate", "heirs", "testament"],
        "tags": ["family-law", "inheritance"],
    },
    "code_international_prive": {
        "label": "Code International Prive",
        "markers": ["international", "prive", "conflit", "exequatur", "etranger"],
        "keywords": ["conflict of laws", "private international law", "foreign judgment", "jurisdiction"],
        "tags": ["private-international-law"],
    },
}


def _normalize_text(text: str) -> str:
    normalized = str(text or "").replace("\u00a0", " ")
    normalized = re.sub(r"[ \t]+", " ", normalized)
    normalized = re.sub(r"\n{3,}", "\n\n", normalized)
    return normalized.strip()


def _fold_text(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", str(text or ""))
    return "".join(ch for ch in normalized if not unicodedata.combining(ch)).lower()


def _detect_code_family(file_name: str, sample_text: str) -> str:
    haystack = _fold_text(f"{file_name} {sample_text}")
    if "international" in haystack and ("prive" in haystack or "conflit" in haystack):
        return "code_international_prive"
    if any(token in haystack for token in ["statut personnel", "succession", "heritage", "heritier"]):
        return "code_succession"
    return "code_civil"


def _extract_pdf_text(pdf_path: Path) -> str:
    reader = PdfReader(str(pdf_path))
    pages: List[str] = []
    for page in reader.pages:
        raw = page.extract_text() or ""
        cleaned = _normalize_text(raw)
        if cleaned:
            pages.append(cleaned)
    return "\n\n".join(pages)


def _iter_article_chunks(text: str) -> Iterable[Tuple[str, str]]:
    matches = list(ARTICLE_HEADER_RE.finditer(text))
    if not matches:
        return []

    chunks: List[Tuple[str, str]] = []
    for index, match in enumerate(matches):
        start = match.start()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        segment = _normalize_text(text[start:end])
        if not segment:
            continue
        first_line = _normalize_text(segment.splitlines()[0])
        body = _normalize_text(segment[len(first_line) :])
        chunks.append((first_line, body))
    return chunks


def _iter_structural_chunks(text: str) -> Iterable[Tuple[str, str]]:
    matches = list(STRUCTURE_HEADER_RE.finditer(text))
    if not matches:
        return []

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
    article_chunks = list(_iter_article_chunks(text))
    if len(article_chunks) >= SPARSE_ARTICLE_THRESHOLD:
        return article_chunks

    structural_chunks = list(_iter_structural_chunks(text))
    if not article_chunks:
        return structural_chunks

    if len(structural_chunks) > len(article_chunks):
        return structural_chunks

    return article_chunks


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
    article_match = re.search(r"(?i)(article|\u0627\u0644\u0641\u0635\u0644)\s+([0-9]{1,4}(?:\s*(?:bis|ter))?|premier)", heading_clean)
    article_ref = heading_clean
    if article_match:
        article_ref = f"Article {article_match.group(2).strip()}"

    title_parts = re.split(r"\s[-:\u2013]\s", heading_clean, maxsplit=1)
    if len(title_parts) > 1:
        title = _normalize_text(title_parts[1])
    else:
        title = f"{FAMILY_CONFIG[family]['label']} - {article_ref}"

    summary_source = body_clean or heading_clean
    summary = _normalize_text(summary_source[:420])
    keywords = _extract_keywords(f"{heading_clean} {body_clean}", family)

    tags = [family, "local-legal-code", *FAMILY_CONFIG[family]["tags"]]

    return {
        "country": country,
        "code_family": family,
        "code_name": FAMILY_CONFIG[family]["label"],
        "article": article_ref,
        "title": title,
        "summary": summary,
        "keywords": keywords,
        "tags": tags,
        "url": "",
        "source_filename": file_name,
    }


def build_corpus_from_dir(input_dir: Path, country: str) -> Dict[str, List[Dict[str, Any]]]:
    pdf_files = sorted(input_dir.glob("*.pdf"))
    entries: List[Dict[str, Any]] = []

    for pdf_path in pdf_files:
        text = _extract_pdf_text(pdf_path)
        if not text:
            continue

        family = _detect_code_family(pdf_path.name, text[:2000])
        chunks = _select_chunks_for_document(text)
        if not chunks:
            continue

        for heading, body in chunks:
            entry = _build_entry(
                country=country,
                family=family,
                file_name=pdf_path.name,
                heading=heading,
                body=body,
            )
            entries.append(entry)

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
    parser.add_argument("--country", type=str, default="tunisia", help="Country key for the generated corpus.")
    args = parser.parse_args()

    input_dir = args.input_dir.resolve()
    if not input_dir.exists() or not input_dir.is_dir():
        raise SystemExit(f"Input directory not found: {input_dir}")

    corpus = build_corpus_from_dir(input_dir=input_dir, country=args.country.strip().lower())
    output_path = args.output.resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(corpus, ensure_ascii=False, indent=2), encoding="utf-8")

    count = len(corpus.get(args.country.strip().lower(), []))
    print(f"Imported {count} code entries into {output_path}")


if __name__ == "__main__":
    main()
