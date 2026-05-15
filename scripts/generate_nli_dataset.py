"""Generate training triples for the Legal-NLI-XLM fine-tune (Model 2).

Pipeline
--------
1. Load every article from ``backend/services/ai/data/legal_codes_corpus.json``
   (Tunisia + Germany).
2. Sample premises with a language mix of 40% EN / 20% AR / 20% FR / 20% DE.
   - FR premises come straight from the Tunisian corpus.
   - DE premises come straight from the German corpus.
   - AR premises are translated from Tunisian (FR) articles via the local LLM.
   - EN premises are translated from FR/DE/AR articles via the local LLM.
3. For each premise, generate THREE (hypothesis, label) pairs:
     - one "entailed"      : paraphrase a single rule from the article.
     - one "neutral"       : claim about a BM25-adjacent but different article.
     - one "contradicted"  : direct contradiction (negate quantifiers, flip
                             thresholds, swap subjects).
4. ~66% of pairs are cross-lingual (every premise-lang has hypotheses drawn
   from all 4 languages, see HYPOTHESIS_LANG_DIST). This forces the model
   to learn semantic alignment, not surface-token overlap -- so at inference
   it works on any (premise_lang, hypothesis_lang) combination.
5. Emit ``(premise, hypothesis, label, premise_lang, hypothesis_lang, ...)``
   rows as a parquet file ready for the XLM-R-large fine-tune notebook.

Real vs synthetic
-----------------
Premises are 100% real legal articles (Tunisian CSP/COC/etc. + German BGB/etc.).
Only the hypotheses + labels are LLM-generated. Hand-validate ~15% before
training -- the contradicted class especially.

Why this matches the Model 2 spec
---------------------------------
- Multilingual: 40/20/20/20 EN/AR/FR/DE with cross-lingual transfer pairs.
- 5K triples target (configurable via --target-triples).
- 3-class NLI (entailed / neutral / contradicted), balanced per language.
- Compatible with the xlm-roberta-large training notebook.

Resumability
------------
Checkpoint every 50 premises with the full premise+hypothesis content (not
just indices). Re-run with ``--resume`` to continue after Ctrl-C / Ollama
crash without losing data.

Usage
-----
::

    # 1. Have Ollama running locally with llama3.1:8b pulled:
    ollama pull llama3.1:8b
    ollama serve   # (usually already running as a background service)

    # 2. Smoke test on 30 premises first:
    python scripts/generate_nli_dataset.py --max-premises 30

    # 3. Full run (~5-10 hours on a consumer GPU):
    python scripts/generate_nli_dataset.py --target-triples 5000 --resume

    # Optional: bump concurrency if VRAM allows
    python scripts/generate_nli_dataset.py --concurrency 4 --resume

Output
------
``data/training/nli_triples.parquet`` -- columns:
    premise, hypothesis, label,
    premise_lang, hypothesis_lang, is_cross_lingual,
    premise_article, premise_country, premise_code_family

Dependencies
------------
``pip install openai pandas pyarrow tqdm``

Only needs CPU on the Python side; Ollama uses your GPU.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import math
import os
import random
import re
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

try:
    from openai import AsyncOpenAI as _AsyncOpenAIClient
    from openai import OpenAI as _OpenAIClient
except ImportError:  # pragma: no cover
    sys.exit("missing dependency 'openai' -- install with: pip install openai")

try:
    import pandas as pd
except ImportError:  # pragma: no cover
    sys.exit("missing dependency 'pandas' -- install with: pip install pandas pyarrow")

try:
    from tqdm import tqdm
except ImportError:  # pragma: no cover
    def tqdm(iterable, **kwargs):  # type: ignore
        return iterable


logger = logging.getLogger("generate_nli_dataset")


# --- paths and configuration ------------------------------------------------

ROOT = Path(__file__).resolve().parent.parent
CORPUS_PATH = ROOT / "backend" / "services" / "ai" / "data" / "legal_codes_corpus.json"
OUTPUT_PATH = ROOT / "data" / "training" / "nli_triples.parquet"
CHECKPOINT_PATH = ROOT / "data" / "training" / ".nli_progress.json"

DEFAULT_OLLAMA_MODEL = "llama3.1:8b"
DEFAULT_OLLAMA_BASE_URL = "http://localhost:11434/v1"
DEFAULT_GROQ_MODEL = "llama-3.3-70b-versatile"
DEFAULT_GROQ_BASE_URL = "https://api.groq.com/openai/v1"
DEFAULT_TARGET_TRIPLES = 5000
DEFAULT_CONCURRENCY = 2
GROQ_CONCURRENCY = 4        # Groq handles parallel requests well
GROQ_RPM_SLEEP = 1.5        # ~40 RPM free tier safety margin

MIN_SUMMARY_LEN = 60

# Premise-language distribution (English-dominant per the demo requirement).
LANG_MIX = {"en": 0.40, "ar": 0.20, "fr": 0.20, "de": 0.20}

LANG_NAME = {"en": "English", "ar": "Arabic", "fr": "French", "de": "German"}

# How many triples per premise (1 entailed + 1 neutral + 1 contradicted).
LABELS = ["entailed", "neutral", "contradicted"]

# Cross-lingual matrix: for each premise language, the probability distribution
# over hypothesis languages. ~66% of pairs end up cross-lingual overall, so the
# model learns true semantic alignment instead of surface-token matching --
# i.e. it works correctly no matter what language combo it sees at inference.
#
# Read row-by-row: "given a premise in lang X, the hypothesis language is..."
HYPOTHESIS_LANG_DIST = {
    "en": {"en": 0.40, "ar": 0.20, "fr": 0.20, "de": 0.20},
    "ar": {"en": 0.40, "ar": 0.30, "fr": 0.15, "de": 0.15},
    "fr": {"en": 0.40, "ar": 0.15, "fr": 0.30, "de": 0.15},
    "de": {"en": 0.40, "ar": 0.15, "fr": 0.15, "de": 0.30},
}


# --- pure-Python BM25 (for neutral-class adjacent-article mining) -----------

_TOKEN_RE = re.compile(r"[a-zA-ZÀ-ɏ؀-ۿ]{2,}")


def tokenize(text: str) -> list[str]:
    return _TOKEN_RE.findall(text.lower())


class BM25:
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


# --- corpus loading ---------------------------------------------------------


def load_corpus() -> list[dict]:
    if not CORPUS_PATH.exists():
        sys.exit(f"corpus not found: {CORPUS_PATH}")
    payload = json.loads(CORPUS_PATH.read_text(encoding="utf-8"))
    out: list[dict] = []
    for country, items in payload.items():
        if not isinstance(items, list):
            continue
        for item in items:
            if not isinstance(item, dict):
                continue
            a = dict(item)
            a["country"] = country
            out.append(a)
    return out


def passage_text(article: dict) -> str:
    parts = [article.get("title", ""), article.get("summary", "")]
    return "\n".join(p for p in parts if p).strip()


def article_native_lang(article: dict) -> str:
    return {"tunisia": "fr", "germany": "de"}.get(article.get("country", ""), "fr")


# --- prompts ----------------------------------------------------------------


TRANSLATE_PROMPT = """Translate the following legal article from {src_lang} into {tgt_lang}.

Rules:
- Preserve every legal term, number, threshold, and quantifier exactly.
- Do NOT paraphrase or summarise. Translate literally.
- Output STRICT JSON: {{"translation": "<the translated text>"}}. No extra text.

Source article:
{text}

JSON output:"""


ENTAILED_PROMPT = """You are a legal NLI dataset builder.

Given the legal article below (the PREMISE), write ONE sentence in {tgt_lang}
that is STRICTLY ENTAILED by the article -- i.e., the article unambiguously
supports the sentence.

Rules:
- The sentence must restate ONE rule, threshold, obligation, or right from
  the article. Stay faithful to numbers and quantifiers.
- Do NOT copy a full sentence verbatim. Paraphrase, but keep meaning identical.
- Do NOT mention the article number.
- Output STRICT JSON: {{"hypothesis": "<one sentence>"}}. No extra text.

PREMISE (article text):
{premise}

JSON output:"""


NEUTRAL_PROMPT = """You are a legal NLI dataset builder.

Below are TWO different legal articles from the same domain. Write ONE
sentence in {tgt_lang} that:
- Restates a rule from ARTICLE B.
- Is on a topic PLAUSIBLY RELATED to ARTICLE A, but is NEITHER entailed
  NOR contradicted by ARTICLE A.

In other words, a reader of ARTICLE A alone cannot tell whether the sentence
is true or false from ARTICLE A.

Rules:
- Stay faithful to ARTICLE B's content. Do not invent rules.
- Do NOT mention article numbers.
- Output STRICT JSON: {{"hypothesis": "<one sentence>"}}. No extra text.

ARTICLE A (the premise the NLI model will see):
{premise}

ARTICLE B (the source of the hypothesis):
{adjacent}

JSON output:"""


CONTRADICTED_PROMPT_FEWSHOT = """You are a legal NLI dataset builder.

Given the legal article below (the PREMISE), write ONE sentence in {tgt_lang}
that DIRECTLY CONTRADICTS the article. A reader who believes the article
must judge the sentence to be FALSE.

How to contradict (pick one technique):
- Negate an obligation ("shall" -> "shall not", "must" -> "must not").
- Flip a threshold or number ("18 years" -> "16 years", "1/4" -> "1/2").
- Swap the subject of a right ("the spouse" -> "the parents").
- Invert a permission ("is permitted" -> "is prohibited").

Examples of GOOD contradictions:
- Premise says "The legal age of marriage is 18 years."
  Contradiction: "The legal age of marriage is 16 years."
- Premise says "The surviving spouse inherits one quarter of the estate when
  there are descendants."
  Contradiction: "The surviving spouse inherits one half of the estate when
  there are descendants."
- Premise says "Tenants must give three months' notice before terminating
  the lease."
  Contradiction: "Tenants are not required to give any notice before
  terminating the lease."

Rules:
- The contradiction must be on the SAME topic as the article (not unrelated).
- Do NOT just negate every sentence; pick ONE rule and flip it cleanly.
- Do NOT mention the article number.
- Output STRICT JSON: {{"hypothesis": "<one sentence>"}}. No extra text.

PREMISE (article text):
{premise}

JSON output:"""


_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)


def parse_json_field(raw: str, field: str) -> str | None:
    if not raw:
        return None
    text = _FENCE_RE.sub("", raw).strip()
    candidates: list[str] = [text]
    first, last = text.find("{"), text.rfind("}")
    if 0 <= first < last:
        candidates.append(text[first : last + 1])
    for c in candidates:
        try:
            payload = json.loads(c)
        except (json.JSONDecodeError, ValueError):
            continue
        if isinstance(payload, dict):
            value = payload.get(field)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return None


# --- Ollama async caller ----------------------------------------------------


async def ollama_chat(
    client, *, model: str, prompt: str, temperature: float = 0.6,
    max_tokens: int = 400, max_attempts: int = 3, use_json_mode: bool = True,
) -> str:
    backoff = 2.0
    for _ in range(max_attempts):
        try:
            kwargs = dict(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                temperature=temperature,
                max_tokens=max_tokens,
            )
            if use_json_mode:
                kwargs["response_format"] = {"type": "json_object"}
            resp = await client.chat.completions.create(**kwargs)
            return resp.choices[0].message.content or ""
        except Exception as exc:
            logger.debug("ollama call failed: %s", exc)
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 20)
    return ""


# --- per-premise generation -------------------------------------------------


async def translate_text(client, model: str, text: str, src_lang: str, tgt_lang: str) -> str | None:
    if src_lang == tgt_lang:
        return text
    prompt = TRANSLATE_PROMPT.format(
        src_lang=LANG_NAME[src_lang],
        tgt_lang=LANG_NAME[tgt_lang],
        text=text,
    )
    raw = await ollama_chat(client, model=model, prompt=prompt, temperature=0.2, max_tokens=600)
    return parse_json_field(raw, "translation")


async def gen_entailed(client, model: str, premise: str, tgt_lang: str) -> str | None:
    prompt = ENTAILED_PROMPT.format(premise=premise, tgt_lang=LANG_NAME[tgt_lang])
    raw = await ollama_chat(client, model=model, prompt=prompt, temperature=0.55)
    return parse_json_field(raw, "hypothesis")


async def gen_neutral(client, model: str, premise: str, adjacent: str, tgt_lang: str) -> str | None:
    prompt = NEUTRAL_PROMPT.format(
        premise=premise, adjacent=adjacent, tgt_lang=LANG_NAME[tgt_lang],
    )
    raw = await ollama_chat(client, model=model, prompt=prompt, temperature=0.6)
    return parse_json_field(raw, "hypothesis")


async def gen_contradicted(client, model: str, premise: str, tgt_lang: str) -> str | None:
    prompt = CONTRADICTED_PROMPT_FEWSHOT.format(
        premise=premise, tgt_lang=LANG_NAME[tgt_lang],
    )
    raw = await ollama_chat(client, model=model, prompt=prompt, temperature=0.7)
    return parse_json_field(raw, "hypothesis")


# --- language allocation ----------------------------------------------------


def plan_premise_languages(n_premises: int, rng: random.Random) -> list[str]:
    """Return a shuffled list of n_premises language codes matching LANG_MIX."""
    plan: list[str] = []
    for lang, share in LANG_MIX.items():
        plan.extend([lang] * int(round(n_premises * share)))
    while len(plan) < n_premises:
        plan.append("en")
    plan = plan[:n_premises]
    rng.shuffle(plan)
    return plan


def pick_hypothesis_lang(premise_lang: str, rng: random.Random) -> tuple[str, bool]:
    """Pick the hypothesis target language for a given premise.

    Draws from HYPOTHESIS_LANG_DIST. Overall ~66% of pairs are cross-lingual
    so the model must learn semantic alignment, not surface-token matching.
    Returns (lang, is_cross_lingual).
    """
    dist = HYPOTHESIS_LANG_DIST[premise_lang]
    langs = list(dist.keys())
    weights = list(dist.values())
    hyp_lang = rng.choices(langs, weights=weights, k=1)[0]
    return hyp_lang, hyp_lang != premise_lang


# --- checkpointing ---------------------------------------------------------


def save_progress(out_path: Path, rows: list[dict], completed_keys: list[str]) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if rows:
        pd.DataFrame(rows).to_parquet(out_path, index=False)
    CHECKPOINT_PATH.parent.mkdir(parents=True, exist_ok=True)
    CHECKPOINT_PATH.write_text(json.dumps(completed_keys))


def load_progress(out_path: Path) -> tuple[list[dict], set[str]]:
    rows: list[dict] = []
    completed: set[str] = set()
    if out_path.exists():
        try:
            rows = pd.read_parquet(out_path).to_dict("records")
        except Exception:
            logger.warning("failed to load existing rows from %s", out_path)
    if CHECKPOINT_PATH.exists():
        try:
            completed = set(json.loads(CHECKPOINT_PATH.read_text()))
        except Exception:
            logger.warning("failed to load checkpoint")
    return rows, completed


# --- main pipeline ---------------------------------------------------------


def premise_key(article: dict, idx: int, premise_lang: str) -> str:
    return f"{article['country']}::{article.get('article', '')}::{idx}::{premise_lang}"


async def process_premise(
    client, *, model: str, article: dict, idx: int, premise_lang: str,
    articles: list[dict], passages_native: list[str], bm25: BM25, rng: random.Random,
) -> list[dict]:
    """Generate the 3 labelled triples for one (article, premise_lang) pair."""
    native_lang = article_native_lang(article)
    native_text = passages_native[idx]

    # 1. obtain the premise in the desired language (translate if needed)
    if premise_lang == native_lang:
        premise = native_text
    else:
        premise = await translate_text(client, model, native_text, native_lang, premise_lang)
        if not premise:
            return []

    # 2. find a BM25-adjacent article (different from the premise) for `neutral`
    adj_idxs = bm25.top_k(native_text, k=8, exclude={idx})
    same_country = [i for i in adj_idxs if articles[i]["country"] == article["country"]]
    adj_pool = same_country or adj_idxs
    if not adj_pool:
        return []
    adj_idx = rng.choice(adj_pool[:5])
    adj_native = passages_native[adj_idx]

    # 3. for each label, pick the hypothesis language (may be cross-lingual)
    out_rows: list[dict] = []
    for label in LABELS:
        hyp_lang, is_xling = pick_hypothesis_lang(premise_lang, rng)

        if label == "entailed":
            hypothesis = await gen_entailed(client, model, premise, hyp_lang)
        elif label == "neutral":
            # translate the adjacent article into the hypothesis language first
            adj_for_hyp = await translate_text(
                client, model, adj_native, article_native_lang(articles[adj_idx]), hyp_lang,
            )
            if not adj_for_hyp:
                continue
            hypothesis = await gen_neutral(client, model, premise, adj_for_hyp, hyp_lang)
        else:  # contradicted
            hypothesis = await gen_contradicted(client, model, premise, hyp_lang)

        if not hypothesis:
            continue

        out_rows.append({
            "premise": premise,
            "hypothesis": hypothesis,
            "label": label,
            "premise_lang": premise_lang,
            "hypothesis_lang": hyp_lang,
            "is_cross_lingual": is_xling,
            "premise_article": article.get("article", ""),
            "premise_country": article["country"],
            "premise_code_family": article.get("code_family", ""),
        })

    return out_rows


async def run_async(
    *, client, model: str, articles: list[dict], passages_native: list[str],
    bm25: BM25, premise_plan: list[tuple[int, str]], existing_rows: list[dict],
    completed: set[str], output: Path, concurrency: int, save_every: int,
) -> tuple[list[dict], set[str]]:
    rows = list(existing_rows)
    rng = random.Random(1337)
    sem = asyncio.Semaphore(concurrency)
    pbar = tqdm(total=len(premise_plan), desc="premises", initial=len(completed))

    async def worker(idx: int, premise_lang: str) -> None:
        key = premise_key(articles[idx], idx, premise_lang)
        if key in completed:
            pbar.update(1)
            return
        async with sem:
            try:
                triples = await process_premise(
                    client, model=model, article=articles[idx], idx=idx,
                    premise_lang=premise_lang, articles=articles,
                    passages_native=passages_native, bm25=bm25, rng=rng,
                )
            except Exception as exc:
                logger.debug("premise %d (%s) failed: %s", idx, premise_lang, exc)
                triples = []
        rows.extend(triples)
        completed.add(key)
        pbar.update(1)
        pbar.set_postfix(rows=len(rows))
        if len(completed) % save_every == 0:
            save_progress(output, rows, sorted(completed))

    tasks = [asyncio.create_task(worker(i, lang)) for i, lang in premise_plan]
    try:
        await asyncio.gather(*tasks)
    except KeyboardInterrupt:
        logger.warning("interrupted; saving before exit...")
    finally:
        pbar.close()

    return rows, completed


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--provider", choices=["ollama", "groq"], default="ollama",
        help="LLM provider. 'groq' uses the Groq API (set GROQ_API_KEY env var).",
    )
    parser.add_argument("--model", default=None,
        help="Model name. Defaults: ollama->llama3.1:8b, groq->llama-3.3-70b-versatile",
    )
    parser.add_argument("--ollama-base-url", default=DEFAULT_OLLAMA_BASE_URL)
    parser.add_argument(
        "--target-triples", type=int, default=DEFAULT_TARGET_TRIPLES,
        help="Approximate total triples to produce when --no-use-all-articles is set.",
    )
    parser.add_argument(
        "--max-premises", type=int, default=None,
        help="Hard cap on premises (for smoke tests). Overrides --target-triples and --use-all-articles.",
    )
    parser.add_argument(
        "--use-all-articles", dest="use_all_articles",
        action="store_true", default=True,
        help="Use every article in the corpus as a premise (default). ~3252 premises => ~9750 triples.",
    )
    parser.add_argument(
        "--no-use-all-articles", dest="use_all_articles", action="store_false",
        help="Sample only enough premises to hit --target-triples (faster, less data).",
    )
    parser.add_argument(
        "--all-tunisia-plus", type=int, default=None, metavar="N_GERMAN",
        help="Use ALL Tunisian articles + N random German articles. Overrides --use-all-articles. "
             "Example: --all-tunisia-plus 900 yields ~1482 premises => ~4446 triples.",
    )
    parser.add_argument("--concurrency", type=int, default=DEFAULT_CONCURRENCY)
    parser.add_argument("--save-every", type=int, default=50)
    parser.add_argument("--output", type=Path, default=OUTPUT_PATH)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
    )

    if args.provider == "groq":
        api_key = os.environ.get("GROQ_API_KEY", "").strip()
        if not api_key:
            sys.exit(
                "GROQ_API_KEY not set.\n"
                "PowerShell: $env:GROQ_API_KEY = 'gsk_...'\n"
                "Kaggle: Add-ons -> Secrets -> GROQ_API_KEY"
            )
        client = _AsyncOpenAIClient(api_key=api_key, base_url=DEFAULT_GROQ_BASE_URL)
        model_name = args.model or DEFAULT_GROQ_MODEL
        concurrency_default = GROQ_CONCURRENCY
        logger.info("provider=groq model=%s (rate-limited, ~40 RPM)", model_name)
    else:
        client = _AsyncOpenAIClient(api_key="ollama", base_url=args.ollama_base_url)
        model_name = args.model or DEFAULT_OLLAMA_MODEL
        concurrency_default = DEFAULT_CONCURRENCY
        logger.info("ollama model=%s base_url=%s", model_name, args.ollama_base_url)

    articles = load_corpus()
    articles = [a for a in articles if len(a.get("summary") or "") >= MIN_SUMMARY_LEN]
    logger.info("loaded %d articles after filters", len(articles))

    passages_native = [passage_text(a) for a in articles]
    logger.info("building BM25 index over %d passages...", len(articles))
    tokenized = [tokenize(p) for p in passages_native]
    bm25 = BM25(tokenized)

    rng = random.Random(42)

    if args.all_tunisia_plus is not None:
        tn_idxs = [i for i, a in enumerate(articles) if a["country"] == "tunisia"]
        de_idxs = [i for i, a in enumerate(articles) if a["country"] == "germany"]
        rng.shuffle(de_idxs)
        de_sample = de_idxs[: max(0, args.all_tunisia_plus)]
        article_indices = tn_idxs + de_sample
        rng.shuffle(article_indices)
        n_premises = len(article_indices)
        logger.info(
            "all-tunisia-plus mode: %d Tunisian + %d German = %d premises",
            len(tn_idxs), len(de_sample), n_premises,
        )
    elif args.max_premises is not None:
        n_premises = min(args.max_premises, len(articles))
        article_indices = list(range(len(articles)))
        rng.shuffle(article_indices)
        article_indices = article_indices[:n_premises]
    elif args.use_all_articles:
        n_premises = len(articles)
        article_indices = list(range(len(articles)))
        rng.shuffle(article_indices)
    else:
        n_premises = min(max(1, args.target_triples // len(LABELS)), len(articles))
        article_indices = list(range(len(articles)))
        rng.shuffle(article_indices)
        article_indices = article_indices[:n_premises]

    logger.info(
        "premises=%d => target ~%d triples (3 per premise)",
        n_premises, n_premises * len(LABELS),
    )

    premise_langs = plan_premise_languages(n_premises, rng)
    premise_plan = list(zip(article_indices, premise_langs))

    if args.resume:
        existing_rows, completed = load_progress(args.output)
        logger.info(
            "resuming with %d rows, %d completed premises",
            len(existing_rows), len(completed),
        )
    else:
        existing_rows, completed = [], set()

    effective_concurrency = args.concurrency if args.concurrency != DEFAULT_CONCURRENCY else concurrency_default

    start = time.time()
    try:
        rows, completed = asyncio.run(run_async(
            client=client, model=model_name, articles=articles,
            passages_native=passages_native, bm25=bm25,
            premise_plan=premise_plan, existing_rows=existing_rows,
            completed=completed, output=args.output,
            concurrency=effective_concurrency, save_every=args.save_every,
        ))
    except KeyboardInterrupt:
        logger.warning("interrupted at top level")
        rows = existing_rows

    save_progress(args.output, rows, sorted(completed))

    if not rows:
        logger.warning("no rows generated")
        return 0

    df = pd.DataFrame(rows)
    elapsed = time.time() - start
    logger.info("=== final ===")
    logger.info("rows total       : %d", len(df))
    logger.info("by label         : %s", df["label"].value_counts().to_dict())
    logger.info("by premise_lang  : %s", df["premise_lang"].value_counts().to_dict())
    logger.info("by hypothesis_lang: %s", df["hypothesis_lang"].value_counts().to_dict())
    logger.info("cross-lingual    : %d (%.1f%%)",
                int(df["is_cross_lingual"].sum()),
                100 * df["is_cross_lingual"].mean())
    logger.info("elapsed          : %.1f min", elapsed / 60)
    logger.info("saved to %s", args.output)
    return 0


if __name__ == "__main__":
    sys.exit(main())
