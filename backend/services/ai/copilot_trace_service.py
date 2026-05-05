"""Phase B \u2014 Copilot trace persistence service.

Pure helper that turns the orchestrator's final ``CopilotGraphState`` + result
into a ``CopilotTrace`` row. Never raises \u2014 a tracing failure must never
break the user-facing response.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable, Mapping

from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.models.copilot_trace import CopilotTrace
from backend.services.ai.big_agents import big_agent_registry


logger = logging.getLogger("backend.copilot_trace")


VERDICT_VERIFIED = "verified"
VERDICT_PARTIAL = "partial"
VERDICT_UNVERIFIED = "unverified"
VERDICT_REFUSED = "refused"
VERDICT_ERROR = "error"
VERDICT_NOT_RUN = "not_run"

_KNOWN_VERDICTS: frozenset[str] = frozenset(
    {
        VERDICT_VERIFIED,
        VERDICT_PARTIAL,
        VERDICT_UNVERIFIED,
        VERDICT_REFUSED,
        VERDICT_ERROR,
        VERDICT_NOT_RUN,
    }
)


def _safe_json_dumps(value: Any) -> str | None:
    if value is None:
        return None
    try:
        return json.dumps(value, default=str, ensure_ascii=False)
    except Exception:  # pragma: no cover - defensive
        return None


def _safe_json_loads(value: Any) -> Any:
    if value is None:
        return None
    if not isinstance(value, str):
        return value
    if not value.strip():
        return None
    try:
        return json.loads(value)
    except Exception:
        return None


def _normalize_verdict(value: Any) -> str:
    token = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
    if token in _KNOWN_VERDICTS:
        return token
    if token in {"verified", "source_grounded_article_references_present", "source_grounded_verified"}:
        return VERDICT_VERIFIED
    if token in {"partially_verified", "source_grounded_partial", "grounded_partial"}:
        return VERDICT_PARTIAL
    if token.startswith("not_verified") or token == "unverified":
        return VERDICT_UNVERIFIED
    if token in {"refused", "weak_grounding"}:
        return VERDICT_REFUSED
    return VERDICT_UNVERIFIED


def extract_mini_agents(state: Mapping[str, Any], result: Mapping[str, Any]) -> list[str]:
    """Pull the mini-agent identifiers exercised by this run.

    Sources, in priority order:
    1. ``state["selected_agents"]`` \u2014 workflow-planned sequence.
    2. ``state["agent_outputs"]`` keys.
    3. Legal-agent-pack ``agent_sequence`` recorded inside structured_result.
    """

    seen: dict[str, None] = {}

    selected = state.get("selected_agents")
    if isinstance(selected, list):
        for item in selected:
            cleaned = str(item or "").strip()
            if cleaned:
                seen.setdefault(cleaned, None)

    outputs = state.get("agent_outputs")
    if isinstance(outputs, dict):
        for key in outputs.keys():
            cleaned = str(key or "").strip()
            if cleaned:
                seen.setdefault(cleaned, None)

    structured = result.get("structured_result") if isinstance(result, Mapping) else None
    if isinstance(structured, dict):
        legal = structured.get("legal_workflow_agents")
        if isinstance(legal, dict):
            seq = legal.get("agent_sequence")
            if isinstance(seq, list):
                for item in seq:
                    cleaned = str(item or "").strip()
                    if cleaned:
                        seen.setdefault(cleaned, None)

    return list(seen.keys())


def extract_verdict(state: Mapping[str, Any], result: Mapping[str, Any]) -> str:
    """Best-effort verdict extraction from the orchestrator final state."""

    if isinstance(result, Mapping) and result.get("permission_denied"):
        return VERDICT_REFUSED

    contract = None
    structured = result.get("structured_result") if isinstance(result, Mapping) else None
    if isinstance(structured, dict):
        contract = structured.get("global_output_contract")
    if isinstance(contract, dict):
        status = contract.get("verification_status")
        if status:
            return _normalize_verdict(status)

    verification = state.get("verification_result")
    if isinstance(verification, dict):
        contract = verification.get("global_output_contract")
        if isinstance(contract, dict) and contract.get("verification_status"):
            return _normalize_verdict(contract.get("verification_status"))

    if isinstance(result, Mapping):
        grounding = str(result.get("grounding") or "").strip().lower()
        if grounding in {"case-grounded", "fully grounded", "verified"}:
            return VERDICT_VERIFIED
        if grounding == "partial":
            return VERDICT_PARTIAL

    if isinstance(result, Mapping) and result.get("used_fallback"):
        return VERDICT_UNVERIFIED

    if state.get("errors"):
        return VERDICT_ERROR

    return VERDICT_NOT_RUN


class CopilotTraceService:
    """Persist + read traces. All methods are best-effort (never raise)."""

    def record(
        self,
        *,
        db: Session,
        state: Mapping[str, Any],
        result: Mapping[str, Any] | None,
        duration_ms: float | None = None,
    ) -> int | None:
        """Insert a trace row. Returns the new id or ``None`` on failure."""

        result = result or {}
        try:
            call_id = str(state.get("request_id") or "").strip()
            if not call_id:
                return None

            intent = str(state.get("intent_name") or state.get("intent") or "").strip() or None
            big_agent = None
            if intent:
                descriptor = big_agent_registry.find_by_intent(intent)
                if descriptor is not None:
                    big_agent = descriptor.name

            route = str(state.get("route") or "").strip() or None
            mode = str(state.get("mode") or "").strip() or None
            effective_mode = str(state.get("effective_mode") or "").strip() or None

            mini_agents = extract_mini_agents(state, result)
            verdict = extract_verdict(state, result)

            confidence = None
            if isinstance(result, Mapping):
                conf = result.get("confidence")
                if conf:
                    confidence = str(conf).strip().lower()[:32]

            used_fallback = None
            if isinstance(result, Mapping) and "used_fallback" in result:
                used_fallback = 1 if result.get("used_fallback") else 0

            errors = state.get("errors")
            error_count = len(errors) if isinstance(errors, list) else 0

            stage_records = state.get("stage_records") or []
            stages_payload: list[Any] = []
            for record in stage_records:
                if hasattr(record, "model_dump"):
                    try:
                        stages_payload.append(record.model_dump(mode="json"))
                        continue
                    except Exception:
                        pass
                if isinstance(record, dict):
                    stages_payload.append(record)

            metadata = {
                "trust_enabled": bool(state.get("trust_enabled")),
                "use_trust_engine": bool(state.get("use_trust_engine")),
                "matter_type": state.get("matter_type"),
                "task_type": state.get("task_type"),
                "warnings": state.get("warnings") or [],
                "errors": [
                    {
                        "node": (e.get("node") if isinstance(e, dict) else None),
                        "error_type": (e.get("error_type") if isinstance(e, dict) else None),
                    }
                    for e in (errors or [])
                ]
                if isinstance(errors, list)
                else [],
                "fallback_reason": result.get("fallback_reason") if isinstance(result, Mapping) else None,
            }

            row = CopilotTrace(
                call_id=call_id[:64],
                tenant_id=state.get("tenant_id"),
                user_id=state.get("user_id"),
                case_id=state.get("resolved_case_id") or state.get("workspace_case_id"),
                document_id=state.get("resolved_document_id") or state.get("workspace_document_id"),
                intent=intent[:128] if intent else None,
                big_agent=big_agent[:64] if big_agent else None,
                route=route[:64] if route else None,
                mode=mode[:64] if mode else None,
                effective_mode=effective_mode[:64] if effective_mode else None,
                verdict=verdict[:64],
                confidence=confidence,
                used_fallback=used_fallback,
                error_count=error_count,
                duration_ms=int(duration_ms) if duration_ms is not None else None,
                mini_agents_used_json=_safe_json_dumps(mini_agents),
                stages_json=_safe_json_dumps(stages_payload),
                metadata_json=_safe_json_dumps(metadata),
            )
            db.add(row)
            db.commit()
            db.refresh(row)
            return int(row.id)
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("[copilot_trace] failed to record: %s", exc)
            try:
                db.rollback()
            except Exception:
                pass
            return None

    def get_by_call_id(self, *, db: Session, call_id: str) -> CopilotTrace | None:
        try:
            return db.query(CopilotTrace).filter(CopilotTrace.call_id == call_id).first()
        except Exception:
            return None

    def serialize(self, row: CopilotTrace) -> dict[str, Any]:
        return {
            "id": int(row.id),
            "call_id": row.call_id,
            "tenant_id": row.tenant_id,
            "user_id": row.user_id,
            "case_id": row.case_id,
            "document_id": row.document_id,
            "intent": row.intent,
            "big_agent": row.big_agent,
            "route": row.route,
            "mode": row.mode,
            "effective_mode": row.effective_mode,
            "verdict": row.verdict,
            "confidence": row.confidence,
            "used_fallback": bool(row.used_fallback) if row.used_fallback is not None else None,
            "error_count": int(row.error_count or 0),
            "duration_ms": row.duration_ms,
            "mini_agents_used": _safe_json_loads(row.mini_agents_used_json) or [],
            "stages": _safe_json_loads(row.stages_json) or [],
            "metadata": _safe_json_loads(row.metadata_json) or {},
            "created_at": row.created_at.isoformat() if row.created_at else None,
        }

    def list_recent(
        self,
        *,
        db: Session,
        limit: int = 100,
        big_agent: str | None = None,
        verdict: str | None = None,
    ) -> list[CopilotTrace]:
        try:
            q = db.query(CopilotTrace)
            if big_agent:
                q = q.filter(CopilotTrace.big_agent == big_agent)
            if verdict:
                q = q.filter(CopilotTrace.verdict == verdict)
            return q.order_by(CopilotTrace.created_at.desc()).limit(int(limit)).all()
        except Exception:
            return []

    def call_counts_last_24h(self, *, db: Session) -> dict[str, int]:
        """Return ``{big_agent_name: count}`` over the past 24h."""

        try:
            since = datetime.now(timezone.utc) - timedelta(hours=24)
            rows = (
                db.query(CopilotTrace.big_agent, func.count(CopilotTrace.id))
                .filter(CopilotTrace.created_at >= since)
                .filter(CopilotTrace.big_agent.isnot(None))
                .group_by(CopilotTrace.big_agent)
                .all()
            )
            return {str(name): int(count) for name, count in rows if name}
        except Exception:
            return {}


copilot_trace_service = CopilotTraceService()


__all__ = [
    "CopilotTraceService",
    "copilot_trace_service",
    "extract_mini_agents",
    "extract_verdict",
    "VERDICT_VERIFIED",
    "VERDICT_PARTIAL",
    "VERDICT_UNVERIFIED",
    "VERDICT_REFUSED",
    "VERDICT_ERROR",
    "VERDICT_NOT_RUN",
]
