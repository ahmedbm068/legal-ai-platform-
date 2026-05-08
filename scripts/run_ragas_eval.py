"""RAGAS-style evaluation runner.

Reads a JSONL eval set (synthetic or hand-labelled) and computes four
LLM-as-judge / heuristic metrics per query, then aggregates them:

* **citation_recall@k** — does the gold ``expected_citations`` appear in
  the system's returned sources for the query? Pure heuristic, no LLM.

* **context_relevance** — fraction of retrieved chunks that an LLM judges
  *relevant* to answering the question. Detects retrieval drift.

* **faithfulness** — fraction of atomic claims in the answer that an LLM
  judges *supported* by the retrieved sources. Same idea as the runtime
  NLI service (``nli_faithfulness_service``) but using the LLM as judge,
  for cases where the NLI model is unavailable.

* **answer_relevance** — does the answer address the question? Computed
  by asking the LLM to generate N hypothetical questions from the answer
  alone, then measuring cosine similarity to the original query (proxy
  for "does the answer talk about what was asked").

Output is a per-row JSONL plus a summary JSON. Both go in
``scripts/evals/runs/<timestamp>/`` so each run is reproducible.

Usage
-----
    python scripts/run_ragas_eval.py \
        --eval-set scripts/evals/synthetic_eval_2026_05_07.jsonl \
        --tenant-id 1 --user-id 1 \
        --metrics citation_recall,context_relevance,faithfulness,answer_relevance \
        --limit 0   # 0 = run all
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


from backend.core.deps import SessionLocal  # noqa: E402
from backend.services.ai.llm_gateway import llm_gateway  # noqa: E402
from backend.services.ai.runtime_services import copilot_orchestration_service  # noqa: E402


logger = logging.getLogger(__name__)


SUPPORTED_METRICS = (
    "citation_recall",
    "context_relevance",
    "faithfulness",
    "answer_relevance",
)


CONTEXT_RELEVANCE_PROMPT = """You are evaluating whether a retrieved chunk is RELEVANT to a legal question.

Question: {question}

Retrieved chunk:
\"\"\"{chunk}\"\"\"

Reply with STRICT JSON: {{"relevant": true|false, "reason": "1-sentence justification"}}.
"""

FAITHFULNESS_PROMPT = """You are checking whether each CLAIM in a legal answer is SUPPORTED by the retrieved sources.

QUESTION: {question}

SOURCES:
{sources}

ANSWER:
{answer}

Step 1: extract atomic factual claims from the ANSWER (skip pure opinions or hedges).
Step 2: for each claim, judge whether it is fully supported, partially supported, or unsupported by the SOURCES.

Reply with STRICT JSON: {{"claims": [{{"text": "...", "verdict": "supported|partial|unsupported"}}]}}
"""

ANSWER_RELEVANCE_PROMPT = """Generate {n} alternative QUESTIONS that this ANSWER would directly satisfy.

ANSWER:
\"\"\"{answer}\"\"\"

Reply with STRICT JSON: {{"questions": ["q1", "q2", ...]}}
Output exactly {n} questions.
"""


_JSON_FENCE_RE = re.compile(r"```(?:json)?\s*([\{\[][\s\S]*[\}\]])\s*```", re.IGNORECASE)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="RAGAS-style eval runner.")
    p.add_argument("--eval-set", required=True, help="Path to a JSONL eval set.")
    p.add_argument("--tenant-id", type=int, required=True)
    p.add_argument("--user-id", type=int, required=True)
    p.add_argument(
        "--metrics",
        type=str,
        default=",".join(SUPPORTED_METRICS),
        help=f"Comma-separated subset of: {','.join(SUPPORTED_METRICS)}",
    )
    p.add_argument("--limit", type=int, default=0, help="Limit number of rows (0 = all).")
    p.add_argument("--top-k", type=int, default=5)
    p.add_argument(
        "--out-dir",
        type=str,
        default="",
        help="Output directory. Defaults to scripts/evals/runs/<timestamp>/",
    )
    return p.parse_args()


def main() -> int:
    args = parse_args()
    logging.basicConfig(
        level=os.environ.get("LAI_LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    metrics = [m.strip() for m in args.metrics.split(",") if m.strip()]
    for m in metrics:
        if m not in SUPPORTED_METRICS:
            logger.error("Unsupported metric %r — pick from %s", m, SUPPORTED_METRICS)
            return 2

    eval_path = Path(args.eval_set)
    if not eval_path.exists():
        logger.error("Eval set not found: %s", eval_path)
        return 3

    out_dir = (
        Path(args.out_dir)
        if args.out_dir
        else ROOT
        / "scripts"
        / "evals"
        / "runs"
        / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    )
    out_dir.mkdir(parents=True, exist_ok=True)
    rows_path = out_dir / "rows.jsonl"
    summary_path = out_dir / "summary.json"

    rows = list(_load_eval_rows(eval_path))
    if args.limit > 0:
        rows = rows[: args.limit]
    logger.info("Loaded %d eval rows from %s", len(rows), eval_path)

    judge_client = llm_gateway.create_client()
    judge_model = llm_gateway.resolve_model("text") or llm_gateway.default_model
    if judge_client is None and any(m in metrics for m in ("context_relevance", "faithfulness", "answer_relevance")):
        logger.warning("LLM gateway unavailable — LLM-judged metrics will be skipped.")

    aggregates: dict[str, list[float]] = {m: [] for m in metrics}
    per_language: dict[str, dict[str, list[float]]] = {}
    latencies_ms: list[float] = []

    with SessionLocal() as db, rows_path.open("w", encoding="utf-8") as fh:
        for i, row in enumerate(rows):
            language = str(row.get("language") or "fr")
            t0 = time.monotonic()
            try:
                response = copilot_orchestration_service.run(
                    db=db,
                    tenant_id=args.tenant_id,
                    user_id=args.user_id,
                    user_role="lawyer",
                    message=row["query"],
                    top_k=args.top_k,
                    use_external_research=False,
                    mode="legal_search",
                    reasoning_level="medium",
                )
            except Exception as exc:  # noqa: BLE001
                logger.exception("orchestrator_failed row_id=%s err=%s", row.get("id"), exc)
                continue
            latency_ms = (time.monotonic() - t0) * 1000.0
            latencies_ms.append(latency_ms)

            scored: dict[str, Any] = {
                "row_id": row.get("id"),
                "query": row["query"],
                "language": language,
                "latency_ms": round(latency_ms, 2),
                "answer_preview": str(response.get("answer") or "")[:240],
                "source_count": len(response.get("sources") or []),
                "metrics": {},
            }

            if "citation_recall" in metrics:
                scored["metrics"]["citation_recall"] = _citation_recall(
                    expected=row.get("expected_citations") or [],
                    response=response,
                )
            if "context_relevance" in metrics and judge_client is not None:
                scored["metrics"]["context_relevance"] = _context_relevance(
                    judge_client, judge_model, row["query"], response
                )
            if "faithfulness" in metrics and judge_client is not None:
                scored["metrics"]["faithfulness"] = _faithfulness(
                    judge_client, judge_model, row["query"], response
                )
            if "answer_relevance" in metrics and judge_client is not None:
                scored["metrics"]["answer_relevance"] = _answer_relevance(
                    judge_client, judge_model, row["query"], response
                )

            fh.write(json.dumps(scored, ensure_ascii=False) + "\n")

            for m, v in scored["metrics"].items():
                if isinstance(v, (int, float)):
                    aggregates.setdefault(m, []).append(float(v))
                    per_language.setdefault(language, {}).setdefault(m, []).append(float(v))

            if (i + 1) % 5 == 0:
                logger.info("progress %d/%d", i + 1, len(rows))

    summary = {
        "eval_set": str(eval_path),
        "rows_evaluated": len(rows),
        "metrics": {m: _summary_stats(values) for m, values in aggregates.items()},
        "per_language": {
            lang: {m: _summary_stats(values) for m, values in per_metric.items()}
            for lang, per_metric in per_language.items()
        },
        "latency_ms": _summary_stats(latencies_ms),
        "completed_at": datetime.now(timezone.utc).isoformat(),
    }
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    logger.info("Wrote per-row results → %s", rows_path)
    logger.info("Wrote summary → %s", summary_path)
    print(json.dumps(summary["metrics"], indent=2, ensure_ascii=False))
    return 0


# ──────────────────────────────────────────────────────────────────────────
# Metric implementations
# ──────────────────────────────────────────────────────────────────────────


def _citation_recall(*, expected: list[str], response: Mapping[str, Any]) -> float:
    """1.0 if any expected citation key appears in response.sources, else 0.0.

    Expected format: ``"doc:142#chunk:7"``. We match by ``document_id`` and
    ``chunk_index`` so cosmetic differences (filename casing, etc.) do not
    sink the metric.
    """

    if not expected:
        return 0.0
    sources = response.get("sources") if isinstance(response.get("sources"), list) else []
    retrieved = set()
    for s in sources:
        if not isinstance(s, Mapping):
            continue
        doc_id = s.get("document_id")
        chunk_idx = s.get("chunk_index")
        if doc_id is not None and chunk_idx is not None:
            retrieved.add(f"doc:{doc_id}#chunk:{chunk_idx}")
    return 1.0 if any(e in retrieved for e in expected) else 0.0


def _context_relevance(client: Any, model: str, question: str, response: Mapping[str, Any]) -> float:
    sources = response.get("sources") if isinstance(response.get("sources"), list) else []
    if not sources:
        return 0.0
    relevant = 0
    counted = 0
    for s in sources[:8]:  # cap to keep latency bounded
        chunk = ""
        if isinstance(s, Mapping):
            chunk = str(s.get("snippet") or s.get("chunk_text") or s.get("text") or "")
        if not chunk:
            continue
        verdict = _llm_json(
            client,
            model,
            CONTEXT_RELEVANCE_PROMPT.format(question=question, chunk=chunk[:1200]),
            temperature=0.0,
            max_tokens=180,
        )
        counted += 1
        if isinstance(verdict, Mapping) and bool(verdict.get("relevant")):
            relevant += 1
    return (relevant / counted) if counted else 0.0


def _faithfulness(client: Any, model: str, question: str, response: Mapping[str, Any]) -> float:
    answer = str(response.get("answer") or "")
    sources = response.get("sources") if isinstance(response.get("sources"), list) else []
    if not answer or not sources:
        return 0.0
    sources_text = "\n\n".join(
        f"[doc:{i}] {str(s.get('snippet') or s.get('chunk_text') or '')[:600]}"
        for i, s in enumerate(sources)
        if isinstance(s, Mapping)
    )[:4000]
    verdict = _llm_json(
        client,
        model,
        FAITHFULNESS_PROMPT.format(question=question, sources=sources_text, answer=answer[:2400]),
        temperature=0.0,
        max_tokens=900,
    )
    if not isinstance(verdict, Mapping):
        return 0.0
    claims = verdict.get("claims")
    if not isinstance(claims, list) or not claims:
        return 0.0
    weights = {"supported": 1.0, "partial": 0.5, "unsupported": 0.0}
    score = sum(weights.get(str(c.get("verdict")).lower(), 0.0) for c in claims if isinstance(c, Mapping))
    return score / len(claims)


def _answer_relevance(client: Any, model: str, question: str, response: Mapping[str, Any]) -> float:
    """Approximation of RAGAS answer-relevance: ask the LLM to generate N
    questions the answer satisfies, then return mean string similarity to
    the original question (Jaccard over tokens — no embedding model needed).
    """

    answer = str(response.get("answer") or "")
    if not answer:
        return 0.0
    n = 3
    verdict = _llm_json(
        client,
        model,
        ANSWER_RELEVANCE_PROMPT.format(answer=answer[:2400], n=n),
        temperature=0.4,
        max_tokens=300,
    )
    if not isinstance(verdict, Mapping):
        return 0.0
    questions = verdict.get("questions")
    if not isinstance(questions, list) or not questions:
        return 0.0
    sims = [_jaccard_tokens(question, str(q)) for q in questions if isinstance(q, str)]
    return sum(sims) / len(sims) if sims else 0.0


# ──────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────


_TOKEN_RE = re.compile(r"\w+", re.UNICODE)


def _jaccard_tokens(a: str, b: str) -> float:
    aa = {t.lower() for t in _TOKEN_RE.findall(a)}
    bb = {t.lower() for t in _TOKEN_RE.findall(b)}
    if not aa or not bb:
        return 0.0
    return len(aa & bb) / len(aa | bb)


def _llm_json(
    client: Any,
    model: str,
    prompt: str,
    *,
    temperature: float,
    max_tokens: int,
) -> Any:
    try:
        completion = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": "You are a precise legal evaluator. Output STRICT JSON only."},
                {"role": "user", "content": prompt},
            ],
            temperature=temperature,
            max_tokens=max_tokens,
        )
        text = llm_gateway.extract_output_text(completion).strip()
    except Exception as exc:  # noqa: BLE001
        logger.warning("eval_judge_call_failed err=%s", exc)
        return None
    if not text:
        return None
    candidates = [text]
    fenced = _JSON_FENCE_RE.search(text)
    if fenced:
        candidates.insert(0, fenced.group(1))
    first = text.find("{")
    last = text.rfind("}")
    if 0 <= first < last:
        candidates.append(text[first : last + 1])
    for c in candidates:
        try:
            return json.loads(c)
        except (json.JSONDecodeError, TypeError, ValueError):
            continue
    return None


def _summary_stats(values: list[float]) -> dict[str, Any]:
    if not values:
        return {"count": 0, "mean": None, "min": None, "max": None}
    sorted_vals = sorted(values)
    return {
        "count": len(values),
        "mean": round(sum(values) / len(values), 4),
        "min": round(sorted_vals[0], 4),
        "max": round(sorted_vals[-1], 4),
        "p50": round(sorted_vals[len(sorted_vals) // 2], 4),
        "p95": round(sorted_vals[min(len(sorted_vals) - 1, int(0.95 * len(sorted_vals)))], 4),
    }


def _load_eval_rows(path: Path) -> Iterable[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except (json.JSONDecodeError, TypeError, ValueError):
                continue
            if isinstance(row, dict) and row.get("query"):
                yield row


if __name__ == "__main__":
    sys.exit(main())
