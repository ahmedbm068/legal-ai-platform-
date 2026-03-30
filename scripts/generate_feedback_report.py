from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from backend.database.database import Base, SessionLocal, engine
from backend.models.case import Case  # noqa: F401
from backend.models.client import Client  # noqa: F401
from backend.models.client_portal_account import ClientPortalAccount  # noqa: F401
from backend.models.client_portal_login_code import ClientPortalLoginCode  # noqa: F401
from backend.models.consultation_request import ConsultationRequest  # noqa: F401
from backend.models.copilot_feedback import CopilotFeedback
from backend.models.document import Document  # noqa: F401
from backend.models.document_chunk import DocumentChunk  # noqa: F401
from backend.models.document_entity import DocumentEntity  # noqa: F401
from backend.models.generated_artifact_version import GeneratedArtifactVersion  # noqa: F401
from backend.models.tenant import Tenant  # noqa: F401
from backend.models.user import User  # noqa: F401
from backend.models.voice_recording import VoiceRecording  # noqa: F401


@dataclass
class IntentStats:
    intent: str
    up: int = 0
    down: int = 0
    total: int = 0
    up_rate: float = 0.0


@dataclass
class WeeklyIntentStats:
    week_start: str
    intent: str
    up: int = 0
    down: int = 0
    total: int = 0
    up_rate: float = 0.0


def _week_start_iso(value: datetime | None) -> str:
    if value is None:
        return "unknown"
    normalized = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    monday = normalized - timedelta(days=normalized.weekday())
    return monday.date().isoformat()


def _safe_parse_metadata(raw_value: str | None) -> dict[str, Any]:
    if not raw_value:
        return {}
    try:
        payload = json.loads(raw_value)
        return payload if isinstance(payload, dict) else {}
    except Exception:
        return {}


def _load_feedback_rows(db: Session, *, weeks: int, tenant_id: int | None) -> list[CopilotFeedback]:
    horizon = datetime.now(timezone.utc) - timedelta(weeks=weeks)
    query = db.query(CopilotFeedback).filter(CopilotFeedback.created_at >= horizon)
    if tenant_id is not None:
        query = query.filter(CopilotFeedback.tenant_id == tenant_id)
    return query.order_by(CopilotFeedback.created_at.desc()).all()


def _ensure_feedback_table() -> None:
    Base.metadata.create_all(bind=engine, tables=[CopilotFeedback.__table__])


def _build_intent_summary(rows: list[CopilotFeedback]) -> list[IntentStats]:
    grouped: dict[str, IntentStats] = {}
    for row in rows:
        intent = (row.parsed_intent or "unknown").strip() or "unknown"
        bucket = grouped.setdefault(intent, IntentStats(intent=intent))
        bucket.total += 1
        if row.feedback_value == "up":
            bucket.up += 1
        else:
            bucket.down += 1

    summary = list(grouped.values())
    for item in summary:
        item.up_rate = round((item.up / item.total), 4) if item.total else 0.0
    summary.sort(key=lambda item: (item.up_rate, item.total), reverse=False)
    return summary


def _build_weekly_summary(rows: list[CopilotFeedback]) -> list[WeeklyIntentStats]:
    grouped: dict[tuple[str, str], WeeklyIntentStats] = {}
    for row in rows:
        intent = (row.parsed_intent or "unknown").strip() or "unknown"
        week_start = _week_start_iso(row.created_at)
        key = (week_start, intent)
        bucket = grouped.setdefault(
            key,
            WeeklyIntentStats(week_start=week_start, intent=intent),
        )
        bucket.total += 1
        if row.feedback_value == "up":
            bucket.up += 1
        else:
            bucket.down += 1

    summary = list(grouped.values())
    for item in summary:
        item.up_rate = round((item.up / item.total), 4) if item.total else 0.0
    summary.sort(key=lambda item: (item.week_start, item.total), reverse=True)
    return summary


def _collect_negative_samples(rows: list[CopilotFeedback], limit_per_intent: int = 3) -> dict[str, list[dict[str, str]]]:
    output: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        if row.feedback_value != "down":
            continue

        intent = (row.parsed_intent or "unknown").strip() or "unknown"
        bucket = output[intent]
        if len(bucket) >= limit_per_intent:
            continue

        metadata = _safe_parse_metadata(row.metadata_json)
        bucket.append(
            {
                "prompt_text": (row.prompt_text or "").strip(),
                "response_text": (row.response_text or "").strip(),
                "comment": (row.comment or "").strip(),
                "created_at": row.created_at.isoformat() if row.created_at else "",
                "ui_language": str(metadata.get("ui_language") or ""),
            }
        )
    return output


def _summarize_global_metrics(rows: list[CopilotFeedback]) -> dict[str, Any]:
    up = sum(1 for row in rows if row.feedback_value == "up")
    down = sum(1 for row in rows if row.feedback_value == "down")
    total = up + down
    return {
        "up": up,
        "down": down,
        "total": total,
        "up_rate": round((up / total), 4) if total else 0.0,
    }


def _write_reports(
    *,
    output_dir: Path,
    weeks: int,
    tenant_id: int | None,
    rows: list[CopilotFeedback],
    intent_stats: list[IntentStats],
    weekly_stats: list[WeeklyIntentStats],
    negative_samples: dict[str, list[dict[str, str]]],
) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    json_path = output_dir / f"feedback_report_{stamp}.json"
    md_path = output_dir / f"feedback_report_{stamp}.md"

    metrics = _summarize_global_metrics(rows)
    weak_intents = [
        item
        for item in intent_stats
        if item.total >= 3 and (item.up_rate < 0.70 or item.down >= 2)
    ]

    payload = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "weeks": weeks,
        "tenant_id": tenant_id,
        "metrics": metrics,
        "intent_stats": [asdict(item) for item in intent_stats],
        "weekly_stats": [asdict(item) for item in weekly_stats],
        "weak_intents": [asdict(item) for item in weak_intents],
        "negative_samples": negative_samples,
    }
    json_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    lines: list[str] = [
        f"# Copilot Feedback Report ({stamp} UTC)",
        "",
        f"- Window: last `{weeks}` week(s)",
        f"- Tenant scope: `{tenant_id if tenant_id is not None else 'all tenants'}`",
        f"- Total votes: `{metrics['total']}`",
        f"- Upvotes: `{metrics['up']}`",
        f"- Downvotes: `{metrics['down']}`",
        f"- Up rate: `{metrics['up_rate']:.1%}`",
        "",
        "## Intent Quality",
        "",
        "| Intent | Total | Up | Down | Up Rate |",
        "|---|---:|---:|---:|---:|",
    ]

    for item in sorted(intent_stats, key=lambda row: row.total, reverse=True):
        lines.append(
            f"| `{item.intent}` | {item.total} | {item.up} | {item.down} | {item.up_rate:.1%} |"
        )

    lines.extend(
        [
            "",
            "## Weekly Trend",
            "",
            "| Week Start | Intent | Total | Up Rate |",
            "|---|---|---:|---:|",
        ]
    )
    for item in weekly_stats[:80]:
        lines.append(
            f"| `{item.week_start}` | `{item.intent}` | {item.total} | {item.up_rate:.1%} |"
        )

    lines.extend(["", "## Refinement Priorities", ""])
    if not weak_intents:
        lines.append("- No high-friction intent bucket crossed the alert threshold this week.")
    else:
        for item in weak_intents:
            lines.append(
                f"- `{item.intent}` needs tuning: up_rate={item.up_rate:.1%}, total={item.total}, down={item.down}."
            )
            lines.append(
                "  Action: tighten agent prompt constraints, add 2-4 eval prompts for this failure mode, and rerun regression."
            )

    lines.extend(["", "## Negative Samples", ""])
    if not negative_samples:
        lines.append("- No downvote samples captured in this window.")
    else:
        for intent, samples in negative_samples.items():
            lines.append(f"### `{intent}`")
            for sample in samples:
                prompt_preview = sample["prompt_text"].replace("\n", " ").strip()[:220]
                response_preview = sample["response_text"].replace("\n", " ").strip()[:220]
                comment_preview = sample["comment"][:180] if sample["comment"] else ""
                lines.append(f"- Prompt: `{prompt_preview}`")
                lines.append(f"- Response: `{response_preview}`")
                if comment_preview:
                    lines.append(f"- Comment: `{comment_preview}`")
                if sample["ui_language"]:
                    lines.append(f"- UI language: `{sample['ui_language']}`")
                lines.append("")

    md_path.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")
    return json_path, md_path


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate weekly Copilot thumbs-up/down quality reports.")
    parser.add_argument("--weeks", type=int, default=8, help="Lookback window in weeks (default: 8).")
    parser.add_argument("--tenant-id", type=int, default=None, help="Optional tenant scope.")
    parser.add_argument("--output-dir", default="advancement/feedback", help="Report output directory.")
    args = parser.parse_args()

    if args.weeks < 1:
        print("--weeks must be >= 1", file=sys.stderr)
        return 1

    db: Session = SessionLocal()
    try:
        _ensure_feedback_table()
        rows = _load_feedback_rows(db, weeks=args.weeks, tenant_id=args.tenant_id)
        intent_stats = _build_intent_summary(rows)
        weekly_stats = _build_weekly_summary(rows)
        negative_samples = _collect_negative_samples(rows)
        json_path, md_path = _write_reports(
            output_dir=Path(args.output_dir),
            weeks=args.weeks,
            tenant_id=args.tenant_id,
            rows=rows,
            intent_stats=intent_stats,
            weekly_stats=weekly_stats,
            negative_samples=negative_samples,
        )
        print(f"Feedback JSON report: {json_path}")
        print(f"Feedback Markdown report: {md_path}")
        return 0
    except Exception as exc:
        print(f"Failed to generate feedback report: {exc}", file=sys.stderr)
        return 1
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
