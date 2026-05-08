from __future__ import annotations

import statistics
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from backend.core.deps import get_db
from backend.core.permissions import require_admin
from backend.models.case import Case
from backend.models.document import Document
from backend.models.llm_call_log import LLMCallLog
from backend.models.request_audit_log import RequestAuditLog
from backend.models.user import User
from backend.services.ai.big_agents import big_agent_registry
from backend.services.ai.copilot_trace_service import copilot_trace_service


def _percentile(values: list[float], p: float) -> float:
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

router = APIRouter(prefix="/admin", tags=["Admin"])


# ─── Health ──────────────────────────────────────────────────────────────────


@router.get("/health")
def system_health(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    total_users = db.query(User).filter(User.deleted_at.is_(None)).count()
    total_cases = db.query(Case).filter(Case.deleted_at.is_(None)).count()
    total_documents = db.query(Document).filter(Document.archived_at.is_(None)).count()
    total_audit_entries = db.query(RequestAuditLog).count()

    return {
        "total_users": total_users,
        "total_cases": total_cases,
        "total_documents": total_documents,
        "total_audit_entries": total_audit_entries,
    }


# ─── Audit Log ───────────────────────────────────────────────────────────────


@router.get("/audit-log")
def list_audit_log(
    limit: int = Query(default=200, ge=1, le=1000),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    entries = (
        db.query(RequestAuditLog)
        .order_by(RequestAuditLog.created_at.desc())
        .limit(limit)
        .all()
    )
    return entries


# ─── Big Agent Catalog ───────────────────────────────────────────────────────


@router.get("/big-agents")
def list_big_agents(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Catalog of specialist agents the orchestrator routes to.

    Each entry is a declarative descriptor \u2014 see
    `backend/services/ai/big_agents/`. The ``last_24h_call_count`` field is
    populated from ``copilot_traces`` (Phase B).
    """
    agents = big_agent_registry.list_all()
    counts = copilot_trace_service.call_counts_last_24h(db=db)
    return {
        "count": len(agents),
        "agents": [
            {
                **agent.to_dict(),
                "last_24h_call_count": int(counts.get(agent.name, 0)),
            }
            for agent in agents
        ],
    }


# \u2500\u2500\u2500 Copilot Trace \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500


@router.get("/copilot/traces")
def list_copilot_traces(
    limit: int = Query(default=100, ge=1, le=500),
    big_agent: str | None = Query(default=None),
    verdict: str | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Recent copilot reasoning traces (orchestrator runs)."""
    rows = copilot_trace_service.list_recent(
        db=db,
        limit=limit,
        big_agent=big_agent,
        verdict=verdict,
    )
    return {
        "count": len(rows),
        "traces": [copilot_trace_service.serialize(row) for row in rows],
    }


@router.get("/llm/baseline")
def llm_baseline(
    hours: int = Query(default=24, ge=1, le=24 * 30),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """LLM cost & latency baseline for the admin dashboard.

    Aggregates `llm_call_log` over the last N hours into the numbers you
    quote in a defense slide: latency P50/P95/P99, token totals, USD cost,
    top models by calls and by spend.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    rows = (
        db.query(LLMCallLog)
        .filter(LLMCallLog.created_at >= cutoff)
        .all()
    )
    if not rows:
        return {
            "window_hours": hours,
            "sample_size": 0,
            "latency_ms": {"p50": 0, "p95": 0, "p99": 0, "avg": 0, "max": 0},
            "tokens": {"input_total": 0, "output_total": 0, "input_avg": 0, "output_avg": 0},
            "cost_usd": {"total": 0.0, "avg_per_call": 0.0, "max_call": 0.0},
            "top_models_by_calls": [],
            "top_models_by_spend": [],
        }

    latencies = [float(row.duration_ms or 0.0) for row in rows]
    input_tokens = [int(row.input_tokens or 0) for row in rows]
    output_tokens = [int(row.output_tokens or 0) for row in rows]
    costs = [float(row.cost_usd or 0.0) for row in rows]

    by_model_count: Counter[str] = Counter()
    by_model_cost: dict[str, float] = defaultdict(float)
    for row in rows:
        model = str(row.model or "unknown")
        by_model_count[model] += 1
        by_model_cost[model] += float(row.cost_usd or 0.0)

    return {
        "window_hours": hours,
        "sample_size": len(rows),
        "latency_ms": {
            "p50": round(_percentile(latencies, 50), 2),
            "p95": round(_percentile(latencies, 95), 2),
            "p99": round(_percentile(latencies, 99), 2),
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
    }


@router.get("/copilot/trace/{call_id}")
def get_copilot_trace(
    call_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Full reasoning trail for a single orchestrator run.

    Returns: orchestrator decision \u2192 big agent \u2192 mini agents used \u2192
    verifier verdict, plus the full ordered stage records.
    """
    row = copilot_trace_service.get_by_call_id(db=db, call_id=call_id)
    if row is None:
        raise HTTPException(status_code=404, detail=f"Trace not found: {call_id}")
    return copilot_trace_service.serialize(row)
