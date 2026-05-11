"""Ingest German federal legal texts into ``legal_codes_corpus.json``.

Source: ``gesetze-im-internet.de`` (Federal Ministry of Justice). Federal
laws (BGB, EGBGB, GG, …) are public domain under § 5 UrhG, so we are
allowed to download, parse and re-index them.

The script:
  1. Downloads the published XML zip for each requested law.
  2. Parses the gii ``<dokumente>/<norm>`` structure.
  3. Extracts per-article entries (those with an ``§ …`` enbez).
  4. Routes paragraphs to ``code_civil`` / ``code_succession`` /
     ``code_international_prive`` so the existing legal-search ranker
     scopes them correctly.
  5. Replaces (or creates) the ``germany`` top-level key in
     ``backend/services/ai/data/legal_codes_corpus.json``.

Idempotent: re-running overwrites the ``germany`` key, leaving Tunisian
entries untouched. Rerun this script whenever you want to refresh from
the upstream source.

Usage::

    python scripts/ingest_german_law.py                 # default: BGB + EGBGB
    python scripts/ingest_german_law.py --include-gg    # also Grundgesetz
    python scripts/ingest_german_law.py --dry-run       # don't write anything
"""

from __future__ import annotations

import argparse
import io
import json
import logging
import re
import sys
import urllib.request
import xml.etree.ElementTree as ET
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


logger = logging.getLogger("ingest_german_law")


CORPUS_PATH = (
    Path(__file__).resolve().parent.parent
    / "backend"
    / "services"
    / "ai"
    / "data"
    / "legal_codes_corpus.json"
)


GII_BASE = "https://www.gesetze-im-internet.de"
USER_AGENT = (
    "legal-ai-platform-pfe/1.0 "
    "(public-domain ingestion under §5 UrhG; arbimostaisser@gmail.com)"
)


@dataclass(frozen=True)
class GermanLaw:
    slug: str            # gesetze-im-internet.de URL slug, e.g. 'bgb'
    code_name: str       # canonical display name, e.g. 'Bürgerliches Gesetzbuch'
    abbrev: str          # 'BGB', 'EGBGB', 'GG'
    default_family: str  # 'code_civil' | 'code_succession' | 'code_international_prive'
    succession_paragraph_range: tuple[int, int] | None = None
    # Topic tags injected on every article (helps keyword scoring).
    extra_tags: tuple[str, ...] = ()


# Default ingest list. BGB §§ 1922–2385 are routed to code_succession
# (Erbrecht); everything else in BGB to code_civil. EGBGB is the German
# Private International Law statute, so it maps to code_international_prive.
DEFAULT_LAWS: list[GermanLaw] = [
    GermanLaw(
        slug="bgb",
        code_name="Bürgerliches Gesetzbuch",
        abbrev="BGB",
        default_family="code_civil",
        succession_paragraph_range=(1922, 2385),
        extra_tags=("germany", "federal-statute", "private-law"),
    ),
    GermanLaw(
        slug="bgbeg",
        code_name="Einführungsgesetz zum Bürgerlichen Gesetzbuche (EGBGB)",
        abbrev="EGBGB",
        default_family="code_international_prive",
        extra_tags=("germany", "federal-statute", "international-private-law", "ipr"),
    ),
]


GG_LAW = GermanLaw(
    slug="gg",
    code_name="Grundgesetz für die Bundesrepublik Deutschland",
    abbrev="GG",
    default_family="code_civil",
    extra_tags=("germany", "constitution", "grundgesetz"),
)


# Stop-word strip for keyword extraction (so we don't pollute the corpus
# with German function words).
_GERMAN_STOPWORDS: frozenset[str] = frozenset({
    "der", "die", "das", "den", "dem", "des", "ein", "eine", "einen", "einem", "einer", "eines",
    "und", "oder", "aber", "auch", "wenn", "ist", "sind", "war", "wird", "werden", "worden",
    "auf", "an", "in", "im", "zu", "zur", "zum", "von", "vom", "für", "über", "unter",
    "bei", "nach", "vor", "mit", "ohne", "durch", "gegen", "wegen", "während", "trotz",
    "nicht", "kein", "keine", "keinen", "keinem", "keiner", "keines",
    "diese", "dieser", "diesem", "dieses", "diesen",
    "sich", "sie", "er", "es", "ihm", "ihn", "ihr", "ihre", "ihren", "ihrem", "ihrer", "ihres",
    "absatz", "satz", "paragraph", "paragraphen", "auch",
})


_PARA_NUMBER_RE = re.compile(r"§\s*(\d+)([a-z]?)")


def _http_get(url: str, *, timeout: int = 60) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def _download_xml(slug: str) -> str:
    """Download the gii XML for a given law slug. Returns decoded text."""
    url = f"{GII_BASE}/{slug}/xml.zip"
    logger.info("downloading %s", url)
    payload = _http_get(url)
    zf = zipfile.ZipFile(io.BytesIO(payload))
    xml_members = [m for m in zf.namelist() if m.lower().endswith(".xml")]
    if not xml_members:
        raise RuntimeError(f"no XML found in {url}")
    return zf.read(xml_members[0]).decode("utf-8", errors="replace")


def _norm_text(elem: ET.Element | None) -> str:
    if elem is None:
        return ""
    return re.sub(r"\s+", " ", "".join(elem.itertext())).strip()


def _paragraph_number(enbez: str) -> int | None:
    """Return the integer paragraph number from an enbez like '§ 1922a'."""
    match = _PARA_NUMBER_RE.search(enbez)
    if not match:
        return None
    try:
        return int(match.group(1))
    except ValueError:
        return None


def _extract_keywords(text: str, *, top_n: int = 10) -> list[str]:
    """Pull a handful of distinctive lowercase words from the body."""
    candidates = re.findall(r"[A-Za-zÄÖÜäöüß]{4,}", text)
    counts: dict[str, int] = {}
    for word in candidates:
        lower = word.lower()
        if lower in _GERMAN_STOPWORDS:
            continue
        counts[lower] = counts.get(lower, 0) + 1
    ranked = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
    return [word for word, _ in ranked[:top_n]]


def _build_article_url(slug: str, enbez: str) -> str:
    """Build a stable deep-link to the article on gesetze-im-internet.de."""
    para = _PARA_NUMBER_RE.search(enbez)
    if not para:
        return f"{GII_BASE}/{slug}/index.html"
    return f"{GII_BASE}/{slug}/__{para.group(1)}{para.group(2) or ''}.html"


def _norm_to_entry(norm: ET.Element, law: GermanLaw) -> dict | None:
    enbez = (_norm_text(norm.find("metadaten/enbez")) or "").strip()
    if not enbez.startswith("§") and not enbez.startswith("Art"):
        # Skip section / book / Untertitel headers — only keep articles.
        return None

    titel = _norm_text(norm.find("metadaten/titel"))
    paras = norm.findall("textdaten/text/Content/P")
    body = " ".join(_norm_text(p) for p in paras if _norm_text(p)).strip()
    if not body:
        return None

    # Cap summary at ~600 chars to keep ranker payload small.
    summary = body if len(body) <= 600 else body[:600].rsplit(" ", 1)[0] + "…"

    # Family routing.
    family = law.default_family
    para_num = _paragraph_number(enbez)
    if (
        law.succession_paragraph_range
        and para_num is not None
        and law.succession_paragraph_range[0] <= para_num <= law.succession_paragraph_range[1]
    ):
        family = "code_succession"

    # Extra topical hint based on enbez markers.
    text_lower = (titel + " " + body).lower()
    if "international" in text_lower or "ausland" in text_lower or "fremd" in text_lower:
        # Light bias only — don't override a strong family signal.
        if family == "code_civil" and law.abbrev == "EGBGB":
            family = "code_international_prive"

    article_id = f"{enbez} {law.abbrev}".strip()
    return {
        "country": "germany",
        "code_family": family,
        "code_name": law.code_name,
        "article": article_id,
        "title": f"{law.abbrev} - {enbez}{(' — ' + titel) if titel else ''}",
        "summary": summary,
        "keywords": _extract_keywords(body),
        "tags": list(law.extra_tags) + [family, "local-legal-code"],
        "url": _build_article_url(law.slug, enbez),
        "source_filename": f"{law.slug}/xml.zip",
    }


def ingest_law(law: GermanLaw) -> list[dict]:
    xml_text = _download_xml(law.slug)
    root = ET.fromstring(xml_text)
    entries: list[dict] = []
    skipped = 0
    for norm in root.findall("norm"):
        entry = _norm_to_entry(norm, law)
        if entry is None:
            skipped += 1
            continue
        entries.append(entry)
    logger.info("%s — %d articles ingested (%d skipped)", law.abbrev, len(entries), skipped)
    return entries


def ingest_all(laws: Iterable[GermanLaw]) -> list[dict]:
    all_entries: list[dict] = []
    for law in laws:
        all_entries.extend(ingest_law(law))
    return all_entries


def update_corpus_file(germany_entries: list[dict], *, dry_run: bool) -> None:
    if not CORPUS_PATH.exists():
        raise SystemExit(f"corpus file not found: {CORPUS_PATH}")
    payload = json.loads(CORPUS_PATH.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise SystemExit("legal_codes_corpus.json is not a dict at the top level")

    before_tunisia = len(payload.get("tunisia") or [])
    before_germany = len(payload.get("germany") or [])
    payload["germany"] = germany_entries
    after_tunisia = len(payload.get("tunisia") or [])
    after_germany = len(payload.get("germany") or [])

    logger.info(
        "corpus update: tunisia %d -> %d (unchanged), germany %d -> %d",
        before_tunisia, after_tunisia, before_germany, after_germany,
    )

    if dry_run:
        logger.info("--dry-run set; skipping write")
        return

    CORPUS_PATH.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    logger.info("wrote %s (%d bytes)", CORPUS_PATH, CORPUS_PATH.stat().st_size)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--include-gg", action="store_true",
        help="Also ingest the Grundgesetz (constitution).",
    )
    parser.add_argument(
        "--only", nargs="*", default=None, metavar="ABBREV",
        help="Restrict ingest to these abbrevs (e.g. --only BGB).",
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )

    laws = list(DEFAULT_LAWS)
    if args.include_gg:
        laws.append(GG_LAW)
    if args.only:
        wanted = {a.upper() for a in args.only}
        laws = [law for law in laws if law.abbrev in wanted]
        if not laws:
            raise SystemExit(f"no laws matched --only {args.only}")

    entries = ingest_all(laws)
    if not entries:
        raise SystemExit("no entries ingested; refusing to overwrite corpus")
    update_corpus_file(entries, dry_run=args.dry_run)
    return 0


if __name__ == "__main__":
    sys.exit(main())
