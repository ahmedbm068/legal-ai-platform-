"""Per-request context for LLM call instrumentation.

Stores DB session + tenant identity in a ``ContextVar`` so the LLM gateway can
persist call records without callers having to thread ``db`` and ``tenant_id``
through every call site.

Usage:
    token = set_llm_call_context(db=db, tenant_id=..., user_id=..., request_id=...)
    try:
        ...  # any LLM call here will be persisted via record_llm_call()
    finally:
        reset_llm_call_context(token)

The FastAPI dependency in ``backend.api.rag`` sets and resets the contextvar
automatically for each request that may issue LLM calls.
"""

from __future__ import annotations

import uuid as _uuid
from contextvars import ContextVar, Token
from typing import TYPE_CHECKING, Any

from fastapi import Depends
from sqlalchemy.orm import Session

from backend.core.deps import get_current_user, get_db

if TYPE_CHECKING:
    from backend.models.user import User


_LLM_CALL_CONTEXT: ContextVar[dict[str, Any] | None] = ContextVar(
    "llm_call_context", default=None
)


def set_llm_call_context(
    *,
    db: "Session | None" = None,
    tenant_id: int | None = None,
    user_id: int | None = None,
    request_id: str | None = None,
) -> Token:
    payload: dict[str, Any] = {
        "db": db,
        "tenant_id": tenant_id,
        "user_id": user_id,
        "request_id": request_id,
    }
    return _LLM_CALL_CONTEXT.set(payload)


def reset_llm_call_context(token: Token) -> None:
    try:
        _LLM_CALL_CONTEXT.reset(token)
    except (LookupError, ValueError):
        pass


def get_llm_call_context() -> dict[str, Any] | None:
    return _LLM_CALL_CONTEXT.get()


def llm_call_context_dep(
    db: Session = Depends(get_db),
    current_user: "User" = Depends(get_current_user),
):
    """FastAPI dependency: scope an llm_call_context to the current request.

    Apply to LLM-bearing endpoints so every record_llm_call() invocation in
    the underlying gateway also writes a row to ``llm_call_log`` tagged with
    the requesting tenant + a per-request id. Resets on request exit.
    """
    request_id = str(_uuid.uuid4())
    token = set_llm_call_context(
        db=db,
        tenant_id=getattr(current_user, "tenant_id", None),
        user_id=getattr(current_user, "id", None),
        request_id=request_id,
    )
    try:
        yield request_id
    finally:
        reset_llm_call_context(token)


__all__ = [
    "set_llm_call_context",
    "reset_llm_call_context",
    "get_llm_call_context",
    "llm_call_context_dep",
]
