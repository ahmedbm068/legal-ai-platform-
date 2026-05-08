"""Canonical short summaries for the Tunisian CSP succession articles.

The succession part of the Code de Statut Personnel (arts 85–152) is the
authoritative source for inheritance shares in Tunisia. Our existing legal
corpus (`backend/services/ai/data/legal_codes_corpus.json`) chunks the CSP
by chapter rather than by numbered article, so direct article-level lookup
returns nothing. To still ship traceable citations alongside the
calculator's output, this module embeds the rule-level summary of each
article that the calculator can reference.

The summaries here are short, paraphrased descriptions of public law text —
identical in spirit to what a Tunisian succession textbook would print.
They are intentionally not the full article wording (which would belong in
the corpus). Each entry returns a ``CitationRef`` with ``article``,
``code_name``, ``summary`` and an empty ``snippet`` slot that the corpus
lookup fills opportunistically.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any


logger = logging.getLogger(__name__)


_CORPUS_PATH = (
    Path(__file__).resolve().parent.parent
    / "ai"
    / "data"
    / "legal_codes_corpus.json"
)


@dataclass(frozen=True)
class CitationRef:
    article: str
    code_name: str
    summary: str
    snippet: str = ""
    url: str | None = None


# Canonical paraphrases of CSP succession articles 85–152.
# Source: Tunisian Code de Statut Personnel (loi n° 58-274 + amendments).
# These are short, plain-language summaries — never substitute for the full
# article text. Counsel should always verify against the official Journal
# Officiel de la République Tunisienne.
_CSP_SUCCESSION_SUMMARIES: dict[str, str] = {
    "Article 85": (
        "La succession est ouverte par la mort réelle ou présumée du de cujus. "
        "Sont appelés à la succession les héritiers réservataires (fardh), "
        "puis les agnats (asaba), puis les cognats (dhawu al-arham)."
    ),
    "Article 86": (
        "Les conditions pour hériter : la mort du de cujus, l'existence de "
        "l'héritier au moment du décès, et l'absence d'empêchement légal."
    ),
    "Article 87": (
        "Empêchements : meurtre intentionnel du de cujus et différence de "
        "religion (sous réserve de la jurisprudence tunisienne moderne)."
    ),
    "Article 88": (
        "Le conjoint survivant hérite du de cujus, qu'il y ait ou non des "
        "descendants."
    ),
    "Article 89": (
        "Part du mari survivant : 1/2 en l'absence de descendant héritier, "
        "1/4 en présence d'un descendant héritier."
    ),
    "Article 90": (
        "Part de l'épouse survivante : 1/4 en l'absence de descendant "
        "héritier, 1/8 en présence d'un descendant héritier."
    ),
    "Article 91": (
        "Le père hérite à titre de fardh d'1/6 lorsqu'il existe un "
        "descendant héritier mâle ; il devient agnat lorsqu'il n'y a pas de "
        "descendant mâle."
    ),
    "Article 92": (
        "La mère a 1/6 en présence d'un descendant héritier ou de plusieurs "
        "frères et sœurs ; sinon 1/3 du total (ou 1/3 du résidu dans les "
        "cas dits 'omariennes')."
    ),
    "Article 99": (
        "Lorsqu'il n'existe qu'une seule fille, sa part est 1/2. Deux filles "
        "ou plus se partagent 2/3 par égales portions, en l'absence de "
        "fils héritier."
    ),
    "Article 100": (
        "En présence d'un fils, fils et filles héritent à titre d'agnats "
        "(asaba) et reçoivent le résidu après les fardh, le fils prenant "
        "le double de la part de la fille (li-l-dhakari mithlu hazzi "
        "al-unthayayn)."
    ),
    "Article 101": (
        "La sœur germaine a 1/2 si elle est seule, 2/3 si elles sont deux "
        "ou plus, à condition qu'il n'y ait ni descendant mâle ni père."
    ),
    "Article 110": (
        "L'agnat (asaba) prend la part résiduaire de la succession après "
        "service des parts de fardh. En l'absence de fardh, il prend la "
        "totalité."
    ),
    "Article 113": (
        "Hajb (exclusion) : le fils exclut tous les frères, sœurs et autres "
        "collatéraux. Le père exclut les frères et sœurs germains, "
        "consanguins et utérins."
    ),
    "Article 120": (
        "Awl : lorsque la somme des parts de fardh dépasse l'unité, toutes "
        "les parts sont réduites proportionnellement."
    ),
    "Article 130": (
        "Radd : lorsque la somme des fardh est inférieure à l'unité et qu'il "
        "n'existe pas d'agnat, le résidu est restitué aux héritiers "
        "réservataires (à l'exception du conjoint) au prorata de leurs "
        "parts."
    ),
    "Article 140": (
        "Les frères utérins reçoivent collectivement 1/6 (un seul) ou 1/3 "
        "(deux ou plus), partagés à parts égales entre eux, hommes et "
        "femmes."
    ),
    "Article 150": (
        "Les cognats (dhawu al-arham) ne sont appelés à la succession qu'en "
        "l'absence de fardh et d'agnat."
    ),
    "Article 152": (
        "L'État succède en l'absence de tout héritier connu, après "
        "épuisement des recherches généalogiques."
    ),
}


_CSP_SUCCESSION_KNOWN: set[str] = set(_CSP_SUCCESSION_SUMMARIES.keys())


@lru_cache(maxsize=1)
def _load_corpus() -> list[dict[str, Any]]:
    try:
        with _CORPUS_PATH.open(encoding="utf-8") as fh:
            data = json.load(fh)
        if isinstance(data, dict):
            tunisia = data.get("tunisia") or []
            return list(tunisia) if isinstance(tunisia, list) else []
        if isinstance(data, list):
            return data
        return []
    except Exception:
        logger.warning("legal_codes_corpus_load_failed", exc_info=True)
        return []


def _normalize_article_key(article: str) -> str:
    raw = (article or "").strip()
    if not raw:
        return ""
    raw = raw.replace("Art.", "Article").replace("art.", "Article")
    match = re.match(r"Article\s+(\d+)", raw, re.IGNORECASE)
    if match:
        return f"Article {match.group(1)}"
    return raw


def _find_in_corpus(article_key: str) -> dict[str, Any] | None:
    if not article_key:
        return None
    needle = article_key.lower()
    for entry in _load_corpus():
        article_field = str(entry.get("article") or "").strip().lower()
        if article_field == needle and entry.get("code_family") == "code_succession":
            return entry
    return None


def lookup(article: str) -> CitationRef | None:
    """Return a citation reference for a CSP succession article.

    Falls back to the embedded summary table when the corpus has no
    article-level entry. Returns ``None`` only when the article is not
    recognised at all.
    """
    key = _normalize_article_key(article)
    if not key or key not in _CSP_SUCCESSION_KNOWN:
        return None

    summary = _CSP_SUCCESSION_SUMMARIES[key]
    corpus_hit = _find_in_corpus(key)
    if corpus_hit is not None:
        snippet = (
            str(corpus_hit.get("summary") or corpus_hit.get("title") or "")
        ).strip()
        url = (corpus_hit.get("url") or "").strip() or None
    else:
        snippet = ""
        url = None

    return CitationRef(
        article=key,
        code_name="Code de Statut Personnel",
        summary=summary,
        snippet=snippet,
        url=url,
    )


def lookup_many(articles: list[str]) -> list[CitationRef]:
    """De-duplicating bulk lookup, preserving first-seen order."""
    seen: dict[str, CitationRef] = {}
    for art in articles:
        ref = lookup(art)
        if ref is None:
            continue
        seen.setdefault(ref.article, ref)
    return list(seen.values())


__all__ = ["CitationRef", "lookup", "lookup_many"]
