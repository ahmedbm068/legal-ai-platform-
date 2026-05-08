"""Synthetic eval-set generator.

Picks N random article-sized chunks from the legal corpus and asks an LLM
to generate ``Q`` realistic legal questions whose answer lives inside that
chunk, plus the expected citation IDs. Output is a JSONL file in the same
shape as a hand-labelled eval set:

    {
      "id": "syn-2026-05-07-0007",
      "query": "Quelles sont les conditions de validité d'un testament olographe ?",
      "expected_intent": "legal_search",
      "expected_citations": ["doc:142#chunk:7"],
      "expected_answer_summary": "Un testament olographe doit être ...",
      "language": "fr",
      "source_chunk_id": 8421,
      "source_document_id": 142,
      "generation_model": "llama-3.3-70b-versatile",
      "generated_at": "2026-05-07T18:30:00Z",
      "kind": "synthetic"
    }

Usage
-----
    python scripts/synthetic_eval_generator.py --tenant-id 1 --count 60 \
        --questions-per-chunk 1 --languages fr,ar,en \
        --out scripts/evals/synthetic_eval_2026_05_07.jsonl

Why this is defensible at viva
------------------------------
* No human labels, but the *grounding* is real: each question is generated
  from a real article in the user's corpus, and the expected citation is
  the chunk it was generated from. Recall@k and citation-coverage on this
  set are real signals about the retrieval and citation pipelines.
* For faithfulness / answer quality, run the system on this set and use
  ``scripts/run_ragas_eval.py`` (RAGAS-style LLM-as-judge metrics) to get
  numbers without any human labels.
* Mark every row with ``"kind": "synthetic"`` so a defense panel can see
  exactly which subset is automated vs. (eventually) hand-curated.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import random
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

# Make ``backend`` importable when running this file as a script.
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


from sqlalchemy import text  # noqa: E402

from backend.core.deps import SessionLocal  # noqa: E402
from backend.services.ai.llm_gateway import llm_gateway  # noqa: E402


logger = logging.getLogger(__name__)


GENERATION_SYSTEM_PROMPT = """You generate REALISTIC legal questions for a Tunisian law eval set.

Given a single chunk of a legal document, output {n} question(s) a lawyer or paralegal might ask whose answer lies INSIDE that chunk.

Hard constraints:
- Questions must be ANSWERABLE solely from the chunk — no outside knowledge required.
- Questions must sound natural (no "What does this article say?" meta-questions).
- For each question, also produce a 1-sentence ANSWER SUMMARY drawn ONLY from the chunk.
- Vary phrasing: a mix of formal legal vocabulary and lay phrasing.
- Output language: {language_name}. The question, summary, and any quoted phrases must all be in {language_name}.

Output STRICT JSON in this exact shape, no extra text:
{{
  "items": [
    {{
      "query": "...",
      "expected_answer_summary": "..."
    }}
  ]
}}
"""


_JSON_FENCE_RE = re.compile(r"```(?:json)?\s*(\{[\s\S]*\})\s*```", re.IGNORECASE)
_LANGUAGE_NAMES = {"fr": "French", "ar": "Arabic", "en": "English"}


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Generate a synthetic legal eval set.")
    p.add_argument("--tenant-id", type=int, required=True, help="Tenant ID to scope corpus by.")
    p.add_argument("--count", type=int, default=50, help="Number of chunks to sample.")
    p.add_argument(
        "--questions-per-chunk",
        type=int,
        default=1,
        help="Number of questions to generate per sampled chunk.",
    )
    p.add_argument(
        "--languages",
        type=str,
        default="fr",
        help="Comma-separated language codes to round-robin across (fr,ar,en).",
    )
    p.add_argument(
        "--min-chunk-chars",
        type=int,
        default=300,
        help="Skip chunks shorter than this; too-short chunks produce trivial questions.",
    )
    p.add_argument(
        "--max-chunk-chars",
        type=int,
        default=2000,
        help="Truncate chunks longer than this before sending to the LLM.",
    )
    p.add_argument(
        "--out",
        type=str,
        default="",
        help="Output JSONL path. Defaults to scripts/evals/synthetic_eval_<DATE>.jsonl",
    )
    p.add_argument("--seed", type=int, default=0, help="Random seed for chunk sampling.")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    logging.basicConfig(
        level=os.environ.get("LAI_LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    rng = random.Random(args.seed or None)
    languages = [l.strip().lower() for l in args.languages.split(",") if l.strip()]
    if not languages:
        languages = ["fr"]
    for lang in languages:
        if lang not in _LANGUAGE_NAMES:
            logger.error("Unsupported language %r — pick from fr,ar,en", lang)
            return 2

    out_path = Path(args.out) if args.out else _default_output_path()
    out_path.parent.mkdir(parents=True, exist_ok=True)

    client = llm_gateway.create_client()
    if client is None:
        logger.error("LLM gateway unavailable — cannot generate synthetic questions.")
        return 3
    model = llm_gateway.resolve_model("text") or llm_gateway.default_model

    chunks = list(_sample_chunks(
        tenant_id=args.tenant_id,
        count=args.count,
        min_chars=args.min_chunk_chars,
        rng=rng,
    ))
    if not chunks:
        logger.error("No chunks found for tenant_id=%d — corpus empty?", args.tenant_id)
        return 4
    logger.info("Sampled %d chunks. Generating questions → %s", len(chunks), out_path)

    written = 0
    with out_path.open("w", encoding="utf-8") as fh:
        for i, chunk in enumerate(chunks):
            language = languages[i % len(languages)]
            chunk_text = chunk["chunk_text"]
            if len(chunk_text) > args.max_chunk_chars:
                chunk_text = chunk_text[: args.max_chunk_chars]
            items = _generate_questions(
                client=client,
                model=model,
                chunk_text=chunk_text,
                n=args.questions_per_chunk,
                language=language,
            )
            if not items:
                logger.warning("No questions generated for chunk %s — skipping.", chunk["id"])
                continue
            for q_index, item in enumerate(items):
                row = _build_eval_row(
                    chunk=chunk,
                    item=item,
                    language=language,
                    model=model,
                    seq_index=written,
                )
                fh.write(json.dumps(row, ensure_ascii=False) + "\n")
                written += 1
            if (i + 1) % 10 == 0:
                logger.info("progress %d/%d chunks", i + 1, len(chunks))
            time.sleep(0.05)  # gentle pacing — provider rate limits

    logger.info("Wrote %d synthetic eval rows to %s", written, out_path)
    return 0


# ──────────────────────────────────────────────────────────────────────────


def _default_output_path() -> Path:
    today = datetime.now(timezone.utc).strftime("%Y_%m_%d")
    return ROOT / "scripts" / "evals" / f"synthetic_eval_{today}.jsonl"


def _sample_chunks(
    *, tenant_id: int, count: int, min_chars: int, rng: random.Random
) -> Iterable[dict[str, Any]]:
    """Sample chunks from the document_chunks table for a tenant.

    Uses a single SQL ORDER BY random() — fine for corpora up to a few
    hundred thousand rows. For larger corpora, consider TABLESAMPLE.
    """

    query = text(
        """
        SELECT
            dc.id           AS chunk_id,
            dc.document_id  AS document_id,
            dc.chunk_index  AS chunk_index,
            dc.chunk_text   AS chunk_text,
            d.filename      AS filename
        FROM document_chunks dc
        JOIN documents d ON d.id = dc.document_id
        WHERE d.tenant_id = :tenant_id
          AND char_length(dc.chunk_text) >= :min_chars
        ORDER BY random()
        LIMIT :limit
        """
    )
    with SessionLocal() as session:
        rows = session.execute(
            query,
            {"tenant_id": tenant_id, "min_chars": min_chars, "limit": count},
        ).mappings().all()
        for r in rows:
            yield {
                "id": int(r["chunk_id"]),
                "document_id": int(r["document_id"]),
                "chunk_index": int(r["chunk_index"]),
                "chunk_text": str(r["chunk_text"]),
                "filename": str(r["filename"] or ""),
            }


def _generate_questions(
    *,
    client: Any,
    model: str,
    chunk_text: str,
    n: int,
    language: str,
) -> list[dict[str, str]]:
    system_prompt = GENERATION_SYSTEM_PROMPT.format(
        n=n, language_name=_LANGUAGE_NAMES.get(language, language)
    )
    try:
        completion = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": f"CHUNK:\n{chunk_text}\n\nReturn STRICT JSON per the system instructions.",
                },
            ],
            temperature=0.4,
            max_tokens=600,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("synthetic_question_generation_failed err=%s", exc)
        return []
    text_out = llm_gateway.extract_output_text(completion).strip()
    payload = _parse_json(text_out)
    if not isinstance(payload, dict):
        return []
    items = payload.get("items")
    if not isinstance(items, list):
        return []
    out: list[dict[str, str]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        q = str(item.get("query") or "").strip()
        a = str(item.get("expected_answer_summary") or "").strip()
        if q and a:
            out.append({"query": q, "expected_answer_summary": a})
        if len(out) >= n:
            break
    return out


def _build_eval_row(
    *,
    chunk: dict[str, Any],
    item: dict[str, str],
    language: str,
    model: str,
    seq_index: int,
) -> dict[str, Any]:
    today = datetime.now(timezone.utc)
    return {
        "id": f"syn-{today.strftime('%Y-%m-%d')}-{seq_index:04d}",
        "query": item["query"],
        "expected_intent": "legal_search",
        "expected_citations": [f"doc:{chunk['document_id']}#chunk:{chunk['chunk_index']}"],
        "expected_answer_summary": item["expected_answer_summary"],
        "language": language,
        "source_chunk_id": chunk["id"],
        "source_document_id": chunk["document_id"],
        "source_filename": chunk["filename"],
        "generation_model": model,
        "generated_at": today.isoformat(),
        "kind": "synthetic",
    }


def _parse_json(text_out: str) -> Any:
    if not text_out:
        return None
    candidates = [text_out]
    fenced = _JSON_FENCE_RE.search(text_out)
    if fenced:
        candidates.insert(0, fenced.group(1))
    first = text_out.find("{")
    last = text_out.rfind("}")
    if 0 <= first < last:
        candidates.append(text_out[first : last + 1])
    for c in candidates:
        try:
            return json.loads(c)
        except (json.JSONDecodeError, TypeError, ValueError):
            continue
    return None


if __name__ == "__main__":
    sys.exit(main())
