"""LLM cost & latency baseline report.

Reads `llm_call_log` and produces a snapshot you can paste into your jury
slides:

    P50 / P95 / P99 latency (ms)
    avg / total tokens (input, output)
    avg / total cost (USD)
    top models by call count
    top models by spend
    rolling 24h trend

Run:
    .venv\\Scripts\\python.exe scripts\\llm_cost_latency_baseline.py
    .venv\\Scripts\\python.exe scripts\\llm_cost_latency_baseline.py --hours 168 --json

Outputs both human-readable text (stdout) and optional JSON for piping
into a chart-building script.
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Allow running as `python scripts/llm_cost_latency_baseline.py` from repo root.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import func  # noqa: E402

from backend.database.database import SessionLocal  # noqa: E402
from backend.models.llm_call_log import LLMCallLog  # noqa: E402


def percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    if len(values) == 1:
        return values[0]
    sorted_values = sorted(values)
    rank = (p / 100.0) * (len(sorted_values) - 1)
    lower = int(rank)
    upper = min(lower + 1, len(sorted_values) - 1)
    weight = rank - lower
    return sorted_values[lower] * (1 - weight) + sorted_values[upper] * weight


def build_report(hours: int) -> dict:
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)

    db = SessionLocal()
    try:
        rows = (
            db.query(LLMCallLog)
            .filter(LLMCallLog.created_at >= cutoff)
            .order_by(LLMCallLog.created_at.asc())
            .all()
        )
    finally:
        db.close()

    if not rows:
        return {
            "window_hours": hours,
            "sample_size": 0,
            "message": (
                "No llm_call_log rows in the requested window. Make sure "
                "persist_llm_call() is wired into the LLM gateway path."
            ),
        }

    latencies = [float(row.duration_ms or 0.0) for row in rows]
    input_tokens = [int(row.input_tokens or 0) for row in rows]
    output_tokens = [int(row.output_tokens or 0) for row in rows]
    costs = [float(row.cost_usd or 0.0) for row in rows]

    by_model_count: Counter[str] = Counter()
    by_model_cost: dict[str, float] = defaultdict(float)
    by_model_latency: dict[str, list[float]] = defaultdict(list)
    for row in rows:
        model = str(row.model or "unknown")
        by_model_count[model] += 1
        by_model_cost[model] += float(row.cost_usd or 0.0)
        by_model_latency[model].append(float(row.duration_ms or 0.0))

    by_hour: Counter[str] = Counter()
    for row in rows:
        bucket = row.created_at.replace(minute=0, second=0, microsecond=0).isoformat()
        by_hour[bucket] += 1

    return {
        "window_hours": hours,
        "sample_size": len(rows),
        "latency_ms": {
            "p50": round(percentile(latencies, 50), 2),
            "p95": round(percentile(latencies, 95), 2),
            "p99": round(percentile(latencies, 99), 2),
            "avg": round(statistics.fmean(latencies), 2),
            "max": round(max(latencies), 2),
        },
        "tokens": {
            "input_total": sum(input_tokens),
            "output_total": sum(output_tokens),
            "input_avg": round(statistics.fmean(input_tokens), 1),
            "output_avg": round(statistics.fmean(output_tokens), 1),
        },
        "cost_usd": {
            "total": round(sum(costs), 4),
            "avg_per_call": round(statistics.fmean(costs), 6),
            "max_call": round(max(costs), 6),
        },
        "top_models_by_calls": [
            {"model": name, "calls": n} for name, n in by_model_count.most_common(10)
        ],
        "top_models_by_spend": sorted(
            (
                {"model": name, "cost_usd": round(total, 4)}
                for name, total in by_model_cost.items()
            ),
            key=lambda item: item["cost_usd"],
            reverse=True,
        )[:10],
        "model_latency_p95_ms": [
            {"model": name, "p95": round(percentile(samples, 95), 2)}
            for name, samples in sorted(by_model_latency.items())
        ],
        "calls_per_hour": [
            {"hour": hour, "calls": count}
            for hour, count in sorted(by_hour.items())
        ],
    }


def render_text(report: dict) -> str:
    if report.get("sample_size", 0) == 0:
        return f"[no data in last {report['window_hours']}h] {report.get('message', '')}"

    lines = []
    lines.append(f"=== LLM baseline (last {report['window_hours']}h) ===")
    lines.append(f"Sample size: {report['sample_size']} calls")
    lat = report["latency_ms"]
    lines.append(
        f"Latency ms — p50={lat['p50']}  p95={lat['p95']}  p99={lat['p99']}  "
        f"avg={lat['avg']}  max={lat['max']}"
    )
    tok = report["tokens"]
    lines.append(
        f"Tokens — in={tok['input_total']:,} (avg {tok['input_avg']}) | "
        f"out={tok['output_total']:,} (avg {tok['output_avg']})"
    )
    cost = report["cost_usd"]
    lines.append(
        f"Cost — total=${cost['total']}  avg=${cost['avg_per_call']}  "
        f"max=${cost['max_call']}"
    )
    lines.append("")
    lines.append("Top models by calls:")
    for item in report["top_models_by_calls"]:
        lines.append(f"  {item['calls']:>6}  {item['model']}")
    lines.append("")
    lines.append("Top models by spend:")
    for item in report["top_models_by_spend"]:
        lines.append(f"  ${item['cost_usd']:>10}  {item['model']}")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--hours",
        type=int,
        default=24,
        help="Window size in hours (default: 24)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit JSON instead of human-readable text",
    )
    args = parser.parse_args()

    report = build_report(hours=args.hours)
    if args.json:
        json.dump(report, sys.stdout, indent=2, default=str)
        sys.stdout.write("\n")
    else:
        print(render_text(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
