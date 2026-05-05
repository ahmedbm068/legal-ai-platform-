from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from backend.core.deps import get_db
from backend.core.permissions import require_admin
from backend.models.case import Case
from backend.models.document import Document
from backend.models.request_audit_log import RequestAuditLog
from backend.models.user import User
from backend.services.ai.big_agents import big_agent_registry
from backend.services.ai.copilot_trace_service import copilot_trace_service

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
