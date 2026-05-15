"""Quick health-check on the in-progress reranker training data.

Run anytime (even while generation is still going) with::

    python scripts/inspect_reranker_dataset.py

It answers four questions:

1. **Volume** — how many rows so far, how many positives vs. negatives,
   how many unique queries / unique passages.
2. **Coverage** — how many articles have we covered, and is each
   article producing the expected ~12 rows (3 questions × 4 candidates)?
3. **Quality (queries)** — are the generated questions reasonable
   (length, language detection, duplicate detection, junk detection)?
4. **Quality (negatives)** — are the BM25 hard negatives actually
   different from the positive (sanity: positive passage != negative
   passage for the same query).

It also dumps **20 random rows** so you can eyeball them.
"""

from __future__ import annotations

import json
import random
import re
from collections import Counter
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parent.parent
PARQUET = REPO_ROOT / "data" / "training" / "reranker_triples.parquet"
PROGRESS = REPO_ROOT / "data" / "training" / ".reranker_progress.json"


def _detect_lang(text: str) -> str:
    """Cheap language guess based on script + a couple of stop words."""
    if re.search(r"[؀-ۿ]", text):
        return "ar"
    lower = text.lower()
    fr_markers = (" le ", " la ", " les ", " des ", " une ", " est ", "qu'", "quel", "quelle", "comment", "selon")
    de_markers = (" der ", " die ", " das ", " und ", " ist ", "welche", "welcher", "nach", "wenn ein")
    if any(m in f" {lower} " for m in fr_markers):
        return "fr"
    if any(m in f" {lower} " for m in de_markers):
        return "de"
    return "other"


def main() -> None:
    if not PARQUET.exists():
        raise SystemExit(f"no parquet yet at {PARQUET}")

    df = pd.read_parquet(PARQUET)
    print(f"\n=== File ===")
    print(f"path: {PARQUET}")
    print(f"size: {PARQUET.stat().st_size / 1024:.1f} KB")
    print(f"rows: {len(df):,}")
    print(f"columns: {list(df.columns)}")

    # ---------------------------------------------------------------
    # 1. Volume
    # ---------------------------------------------------------------
    print(f"\n=== Volume ===")
    pos = (df["label"] == 1).sum()
    neg = (df["label"] == 0).sum()
    print(f"positives: {pos:,}")
    print(f"negatives: {neg:,}")
    if pos:
        print(f"neg / pos ratio: {neg / pos:.2f}  (target ~3.0)")
    print(f"unique queries:  {df['query'].nunique():,}")
    print(f"unique passages: {df['passage'].nunique():,}")

    # ---------------------------------------------------------------
    # 2. Coverage
    # ---------------------------------------------------------------
    print(f"\n=== Coverage ===")
    if PROGRESS.exists():
        prog = json.loads(PROGRESS.read_text(encoding="utf-8"))
        done = len(prog.get("processed_articles", [])) if isinstance(prog, dict) else 0
        print(f"articles processed (per checkpoint): {done:,}")
    pos_articles = df.loc[df["label"] == 1, "passage_article"].nunique()
    print(f"articles with at least 1 positive: {pos_articles:,}")
    rows_per_article = df.loc[df["label"] == 1].groupby("passage_article").size()
    if len(rows_per_article):
        print(f"avg positives per article: {rows_per_article.mean():.2f}  (target 3.0)")
        odd = (rows_per_article != 3).sum()
        print(f"articles NOT producing exactly 3 positives: {odd:,}")

    # ---------------------------------------------------------------
    # 3. Country / family distribution
    # ---------------------------------------------------------------
    print(f"\n=== Country / family distribution (positives only) ===")
    pos_df = df[df["label"] == 1]
    if "passage_country" in pos_df.columns:
        print(pos_df["passage_country"].value_counts().to_string())
    if "passage_code_family" in pos_df.columns:
        print()
        print(pos_df["passage_code_family"].value_counts().to_string())

    # ---------------------------------------------------------------
    # 4. Query quality
    # ---------------------------------------------------------------
    print(f"\n=== Query quality ===")
    queries = pos_df["query"].astype(str)
    lens = queries.str.len()
    print(f"query length — min/median/max: {lens.min()} / {int(lens.median())} / {lens.max()}")
    too_short = (lens < 15).sum()
    too_long = (lens > 300).sum()
    print(f"too short (<15 chars): {too_short:,}")
    print(f"too long  (>300 chars): {too_long:,}")
    dup = queries.duplicated().sum()
    print(f"exact duplicate queries: {dup:,}")
    # Junk detection: things that often leak from sloppy LLM output.
    junk_markers = ("here are", "voici", "as an ai", "i'm sorry", "json", "```")
    junk = queries.str.lower().str.contains("|".join(junk_markers), regex=True).sum()
    print(f"queries containing LLM-junk markers: {junk:,}")

    langs = Counter(_detect_lang(q) for q in queries.sample(min(500, len(queries)), random_state=0))
    print(f"language sample (n=500): {dict(langs)}")

    # ---------------------------------------------------------------
    # 5. Negative sanity
    # ---------------------------------------------------------------
    print(f"\n=== Negative sanity ===")
    leak = 0
    for query, group in df.groupby("query"):
        pos_passages = set(group.loc[group["label"] == 1, "passage"])
        neg_passages = set(group.loc[group["label"] == 0, "passage"])
        if pos_passages & neg_passages:
            leak += 1
    print(f"queries where a negative passage == positive passage (BAD): {leak:,}")

    # ---------------------------------------------------------------
    # 6. Random sample dump
    # ---------------------------------------------------------------
    print(f"\n=== 20 random rows (eyeball pass) ===")
    sample = df.sample(min(20, len(df)), random_state=42)
    for i, row in enumerate(sample.itertuples(index=False), 1):
        label = "POS" if row.label == 1 else "neg"
        passage_short = (row.passage[:140] + "…") if len(row.passage) > 140 else row.passage
        print(f"\n[{i:02d}] {label}  article={row.passage_article}  lang={row.query_language}")
        print(f"     Q: {row.query}")
        print(f"     P: {passage_short}")


if __name__ == "__main__":
    main()
