"""Generate training triples for the Legal-Rerank-mTri fine-tune (Model 1).

Pipeline
--------
1. Load every article from ``backend/services/ai/data/legal_codes_corpus.json``
   (Tunisia + Germany; ~3 300 articles after the German ingest).
2. For each article, ask Groq's free-tier Llama 3.3 70B to generate three
   diverse legal questions that the article would answer best.
3. For each generated question, mine three hard negatives from the corpus
   using a pure-Python BM25 index.
4. Emit ``(query, passage, label, language, ...)`` rows as a parquet file
   ready to be loaded by the training notebook in Colab.

Why this matches the plan in
``docs/final_stretch_plan_2026-05-08.md`` and the Model 1 spec:
- Articles are real (Tunisian + German official codes).
- Questions are LLM-generated from those real articles.
- Hard negatives come from BM25 over the same corpus -- no external lookup.
- The 80-tuple hand-labelled eval set stays untouched and is used at
  evaluation time only.

Resumability
------------
The script writes a checkpoint every 50 articles. Re-run with ``--resume``
to pick up after a Ctrl-C or a Groq rate-limit timeout without losing
generated data.

Usage
-----
::

    # 1. Get a free API key at https://console.groq.com (no card required).
    # 2. export it (PowerShell):
    $env:GROQ_API_KEY = "gsk_..."
    # 3. Smoke test on 20 articles first:
    python scripts/generate_reranker_dataset.py --max-articles 20
    # 4. Then full run (~2 hours under the 30 RPM free tier):
    python scripts/generate_reranker_dataset.py --resume

Output
------
``data/training/reranker_triples.parquet`` -- columns:
    query, passage, label, query_language,
    passage_article, passage_country, passage_code_family

Dependencies
------------
``pip install groq pandas pyarrow tqdm``

The script only needs CPU. No GPU, no torch.
"""

from __future__ import annotations

import argparse
import json
import logging
import math
import os
import re
import sys
import time
from collections import Counter
from pathlib import Path

try:
    from openai import OpenAI as _OpenAIClient
except ImportError:  # pragma: no cover
    sys.exit("missing dependency 'openai' -- install with: pip install openai")

# Groq SDK is optional; only required when --provider groq is chosen.
try:
    from groq import Groq as _GroqClient
except ImportError:  # pragma: no cover
    _GroqClient = None

try:
    import pandas as pd
except ImportError:  # pragma: no cover
    sys.exit("missing dependency 'pandas' -- install with: pip install pandas pyarrow")

try:
    from tqdm import tqdm
except ImportError:  # pragma: no cover
    def tqdm(iterable, **kwargs):  # type: ignore
        return iterable


logger = logging.getLogger("generate_reranker_dataset")


# ─── paths and configuration ────────────────────────────────────────────────

ROOT = Path(__file__).resolve().parent.parent
CORPUS_PATH = ROOT / "backend" / "services" / "ai" / "data" / "legal_codes_corpus.json"
OUTPUT_PATH = ROOT / "data" / "training" / "reranker_triples.parquet"
CHECKPOINT_PATH = ROOT / "data" / "training" / ".reranker_progress.json"

DEFAULT_GROQ_MODEL = "llama-3.3-70b-versatile"
DEFAULT_OLLAMA_MODEL = "llama3.1:8b"
DEFAULT_OLLAMA_BASE_URL = "http://localhost:11434/v1"
DEFAULT_QUERIES_PER_ARTICLE = 3
DEFAULT_NEGATIVES_PER_POSITIVE = 3
MIN_SUMMARY_LEN = 60                    # skip articles too short to be useful
GROQ_RPM_LIMIT_SLEEP_SECONDS = 2.1      # 30 RPM ≈ 1 req per 2 s
OLLAMA_PACING_SECONDS = 0.0             # local: no rate limit, run as fast as the GPU allows

LANGUAGE_LABEL_BY_COUNTRY = {"tunisia": "French", "germany": "German"}
LANGUAGE_CODE_BY_COUNTRY = {"tunisia": "fr", "germany": "de"}


# ─── pure-Python BM25 (no extra dependency) ─────────────────────────────────


_TOKEN_RE = re.compile(r"[a-zA-ZäöüßÄÖÜàâéèêëïîôùûÿæœç]{2,}")


def tokenize(text: str) -> list[str]:
    return _TOKEN_RE.findall(text.lower())


class BM25:
    """Minimal BM25 over a fixed corpus. Built once, queried many times."""

    def __init__(self, docs: list[list[str]], k1: float = 1.5, b: float = 0.75) -> None:
        self.docs = docs
        self.k1 = k1
        self.b = b
        self.N = len(docs)
        self.avgdl = (sum(len(d) for d in docs) / self.N) if self.N else 1.0
        self.doc_freq: Counter = Counter()
        for d in docs:
            for term in set(d):
                self.doc_freq[term] += 1
        self.idf = {
            term: math.log(1 + (self.N - df + 0.5) / (df + 0.5))
            for term, df in self.doc_freq.items()
        }
        self.term_freqs = [Counter(d) for d in docs]

    def score(self, query_tokens: list[str], doc_idx: int) -> float:
        d = self.docs[doc_idx]
        dl = len(d)
        tf = self.term_freqs[doc_idx]
        s = 0.0
        for t in query_tokens:
            if t not in self.idf or t not in tf:
                continue
            f = tf[t]
            denom = f + self.k1 * (1 - self.b + self.b * dl / max(self.avgdl, 1.0))
            s += self.idf[t] * (f * (self.k1 + 1)) / denom
        return s

    def top_k(self, query: str, k: int, exclude: set[int] | None = None) -> list[int]:
        exclude = exclude or set()
        q_tokens = tokenize(query)
        if not q_tokens:
            return []
        scored = [
            (i, self.score(q_tokens, i))
            for i in range(self.N)
            if i not in exclude
        ]
        scored.sort(key=lambda x: -x[1])
        return [i for i, _ in scored[:k]]


# ─── corpus loading ─────────────────────────────────────────────────────────


def load_corpus(country_filter: str = "all") -> list[dict]:
    if not CORPUS_PATH.exists():
        sys.exit(f"corpus not found: {CORPUS_PATH}")
    payload = json.loads(CORPUS_PATH.read_text(encoding="utf-8"))
    out: list[dict] = []
    for country, items in payload.items():
        if country_filter != "all" and country != country_filter:
            continue
        if not isinstance(items, list):
            continue
        for item in items:
            if not isinstance(item, dict):
                continue
            article = dict(item)
            article["country"] = country
            out.append(article)
    return out


def passage_text(article: dict) -> str:
    """The text the reranker sees as the 'passage' side of a pair."""
    parts = [
        article.get("article", ""),
        article.get("title", ""),
        article.get("summary", ""),
    ]
    return "\n".join(p for p in parts if p).strip()


# ─── prompt + parsing ───────────────────────────────────────────────────────


PROMPT_TEMPLATE = """You are a legal research assistant.
Below is a single article from a {country_label} legal code.

Generate EXACTLY 3 distinct legal questions that this article would best answer.

Requirements:
- Write all 3 questions in {language_label}.
- Mix the styles:
  1. A direct statutory question (formal, precise).
  2. A practical application question (how the rule applies to facts).
  3. A client-style question (how a non-lawyer would phrase it).
- Each question must be answerable primarily from THIS article.
- Do NOT mention the article number or "Art. X" / "§ X" inside the questions.
- Output STRICT JSON: a JSON object with one key "questions" whose value is
  an array of exactly 3 strings. No extra text.

Article reference: {article}
Title: {title}

Article text:
{summary}

JSON output:"""


def build_prompt(article: dict) -> str:
    country = article.get("country", "tunisia")
    return PROMPT_TEMPLATE.format(
        country_label=country.title(),
        language_label=LANGUAGE_LABEL_BY_COUNTRY.get(country, "French"),
        article=article.get("article", ""),
        title=article.get("title", ""),
        summary=article.get("summary", ""),
    )


_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)


def parse_questions(raw: str) -> list[str]:
    if not raw:
        return []
    text = _FENCE_RE.sub("", raw).strip()
    candidates: list[str] = [text]
    # First-brace-to-last-brace fallback for models that prepend prose.
    first, last = text.find("{"), text.rfind("}")
    if 0 <= first < last:
        candidates.append(text[first : last + 1])
    first, last = text.find("["), text.rfind("]")
    if 0 <= first < last:
        candidates.append(text[first : last + 1])
    for c in candidates:
        try:
            payload = json.loads(c)
        except (json.JSONDecodeError, ValueError):
            continue
        # Accept either {"questions": [...]} or a bare list
        items: list = []
        if isinstance(payload, dict):
            value = payload.get("questions") or payload.get("queries") or []
            if isinstance(value, list):
                items = value
        elif isinstance(payload, list):
            items = payload
        cleaned = [str(q).strip() for q in items if isinstance(q, str) and str(q).strip()]
        # Drop suspiciously short questions (likely model artifacts).
        cleaned = [q for q in cleaned if len(q) >= 10]
        if len(cleaned) >= 2:
            return cleaned[:3]
    return []


# ─── Groq call with retries + rate-limit backoff ────────────────────────────


def generate_questions(
    client, article: dict, *, model: str, use_json_mode: bool = True,
    max_attempts: int = 4,
) -> list[str]:
    prompt = build_prompt(article)
    backoff = 4.0
    for attempt in range(max_attempts):
        try:
            kwargs = dict(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.55,
                max_tokens=400,
            )
            if use_json_mode:
                kwargs["response_format"] = {"type": "json_object"}
            resp = client.chat.completions.create(**kwargs)
            text = resp.choices[0].message.content or ""
            questions = parse_questions(text)
            if questions:
                return questions
            logger.debug(
                "parse failed for %s; raw=%r",
                article.get("article"), text[:240],
            )
        except Exception as exc:
            err = str(exc).lower()
            is_rate_limit = (
                "rate" in err or "429" in err or "too many" in err or "quota" in err
            )
            if is_rate_limit:
                logger.warning("rate limit hit; sleeping %.1fs", backoff)
                time.sleep(backoff)
                backoff = min(backoff * 2, 60)
                continue
            logger.debug("call failed for %s: %s", article.get("article"), exc)
            time.sleep(1.0)
    return []


# ─── checkpointing ─────────────────────────────────────────────────────────


def save_progress(out_path: Path, rows: list[dict], completed: set[str]) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if rows:
        pd.DataFrame(rows).to_parquet(out_path, index=False)
    CHECKPOINT_PATH.parent.mkdir(parents=True, exist_ok=True)
    CHECKPOINT_PATH.write_text(json.dumps(sorted(completed)))


def load_progress(out_path: Path) -> tuple[list[dict], set[str]]:
    rows: list[dict] = []
    completed: set[str] = set()
    if out_path.exists():
        try:
            rows = pd.read_parquet(out_path).to_dict("records")
        except Exception:
            logger.warning("failed to load existing rows from %s; starting fresh", out_path)
    if CHECKPOINT_PATH.exists():
        try:
            completed = set(json.loads(CHECKPOINT_PATH.read_text()))
        except Exception:
            logger.warning("failed to load checkpoint; starting fresh")
    return rows, completed


# ─── main pipeline ─────────────────────────────────────────────────────────


def article_key(article: dict, idx: int) -> str:
    return f"{article['country']}::{article.get('article', '')}::{idx}"


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--provider", choices=["groq", "ollama"], default="groq",
        help="LLM provider for query generation. 'ollama' = local model on your GPU (no rate limit).",
    )
    parser.add_argument(
        "--model", default=None,
        help="Model name. Defaults: groq->llama-3.3-70b-versatile, ollama->llama3.1:8b",
    )
    parser.add_argument(
        "--ollama-base-url", default=DEFAULT_OLLAMA_BASE_URL,
        help="Base URL for the Ollama OpenAI-compatible endpoint.",
    )
    parser.add_argument("--queries-per-article", type=int, default=DEFAULT_QUERIES_PER_ARTICLE)
    parser.add_argument(
        "--negatives-per-positive", type=int, default=DEFAULT_NEGATIVES_PER_POSITIVE,
        help="Hard negatives mined per generated query.",
    )
    parser.add_argument(
        "--max-articles", type=int, default=None,
        help="Cap on articles processed (for quick smoke tests).",
    )
    parser.add_argument(
        "--country", choices=["tunisia", "germany", "all"], default="all",
        help="Restrict to one jurisdiction (defaults to both).",
    )
    parser.add_argument("--output", type=Path, default=OUTPUT_PATH)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
    )

    if args.provider == "groq":
        if _GroqClient is None:
            sys.exit("groq SDK missing -- install with: pip install groq")
        api_key = os.environ.get("GROQ_API_KEY", "").strip()
        if not api_key:
            sys.exit(
                "GROQ_API_KEY not set. Get a free key at https://console.groq.com\n"
                "Then in PowerShell: $env:GROQ_API_KEY = \"gsk_...\""
            )
        client = _GroqClient(api_key=api_key)
        model_name = args.model or DEFAULT_GROQ_MODEL
        use_json_mode = True
        pacing = GROQ_RPM_LIMIT_SLEEP_SECONDS
        logger.info("provider=groq model=%s (rate-limited)", model_name)
    else:  # ollama
        client = _OpenAIClient(
            api_key="ollama",  # ignored by the local server
            base_url=args.ollama_base_url,
        )
        model_name = args.model or DEFAULT_OLLAMA_MODEL
        # Ollama supports OpenAI-compatible JSON mode for many models;
        # if a model rejects it the parser falls back gracefully.
        use_json_mode = True
        pacing = OLLAMA_PACING_SECONDS
        logger.info("provider=ollama model=%s base_url=%s", model_name, args.ollama_base_url)

    articles = load_corpus(args.country)
    articles = [a for a in articles if len(a.get("summary") or "") >= MIN_SUMMARY_LEN]
    if args.max_articles:
        articles = articles[: args.max_articles]
    logger.info("loaded %d articles after filters", len(articles))

    logger.info("building BM25 index over %d passages...", len(articles))
    passages = [passage_text(a) for a in articles]
    tokenized = [tokenize(p) for p in passages]
    bm25 = BM25(tokenized)

    if args.resume:
        rows, completed = load_progress(args.output)
        logger.info("resuming with %d existing rows, %d completed articles",
                    len(rows), len(completed))
    else:
        rows, completed = [], set()

    queries_failed = 0
    pbar = tqdm(enumerate(articles), total=len(articles), desc="generating")
    try:
        for idx, article in pbar:
            key = article_key(article, idx)
            if key in completed:
                continue

            questions = generate_questions(
                client, article, model=model_name, use_json_mode=use_json_mode,
            )[: args.queries_per_article]
            if not questions:
                queries_failed += 1
                completed.add(key)
                continue

            for q in questions:
                # positive
                rows.append({
                    "query": q,
                    "passage": passages[idx],
                    "label": 1,
                    "query_language": LANGUAGE_CODE_BY_COUNTRY.get(article["country"], "fr"),
                    "passage_article": article.get("article", ""),
                    "passage_country": article["country"],
                    "passage_code_family": article.get("code_family", ""),
                })
                # hard negatives — prefer same-country to make them harder
                neg_pool = bm25.top_k(q, k=args.negatives_per_positive + 8, exclude={idx})
                same_country = [i for i in neg_pool if articles[i]["country"] == article["country"]]
                cross_country = [i for i in neg_pool if articles[i]["country"] != article["country"]]
                ordered = same_country + cross_country
                for ni in ordered[: args.negatives_per_positive]:
                    rows.append({
                        "query": q,
                        "passage": passages[ni],
                        "label": 0,
                        "query_language": LANGUAGE_CODE_BY_COUNTRY.get(article["country"], "fr"),
                        "passage_article": articles[ni].get("article", ""),
                        "passage_country": articles[ni]["country"],
                        "passage_code_family": articles[ni].get("code_family", ""),
                    })

            completed.add(key)

            if (idx + 1) % 50 == 0:
                save_progress(args.output, rows, completed)
                pbar.set_postfix(rows=len(rows), failed=queries_failed)

            # polite pacing — Groq free tier is 30 RPM; Ollama is unrestricted
            if pacing > 0:
                time.sleep(pacing)

    except KeyboardInterrupt:
        logger.warning("interrupted by user; saving progress before exit...")

    save_progress(args.output, rows, completed)

    # summary
    if not rows:
        logger.warning("no rows generated -- nothing to summarise")
        return 0

    df = pd.DataFrame(rows)
    pos = int((df["label"] == 1).sum())
    neg = int((df["label"] == 0).sum())
    logger.info("=== final ===")
    logger.info("rows total      : %d", len(df))
    logger.info("positives       : %d", pos)
    logger.info("hard negatives  : %d", neg)
    logger.info("queries failed  : %d (%.1f%%)",
                queries_failed,
                100 * queries_failed / max(len(articles), 1))
    logger.info("by language     : %s", df["query_language"].value_counts().to_dict())
    logger.info("by country      : %s", df["passage_country"].value_counts().to_dict())
    logger.info("by code family  : %s", df["passage_code_family"].value_counts().to_dict())
    logger.info("saved to %s (%d rows)", args.output, len(df))
    return 0


if __name__ == "__main__":
    sys.exit(main())
