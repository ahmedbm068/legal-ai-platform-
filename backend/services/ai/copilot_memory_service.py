from __future__ import annotations

import json
from typing import Any, Iterable

from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from backend.models.case_memory_entry import CaseMemoryEntry


class CopilotMemoryService:
    MAX_HISTORY_ITEMS = 30
    MAX_MESSAGE_CHARS = 12000

    def load_recent_history(
        self,
        *,
        db: Session,
        tenant_id: int,
        user_id: int | None,
        case_id: int | None,
        document_id: int | None,
        conversation_history: Iterable[dict[str, Any]] | None = None,
        max_items: int | None = None,
    ) -> list[dict[str, Any]]:
        limit = max(1, min(int(max_items or self.MAX_HISTORY_ITEMS), 60))
        client_history = self._normalize_history(conversation_history)
        persisted = self._load_persisted_history(
            db=db,
            tenant_id=tenant_id,
            user_id=user_id,
            case_id=case_id,
            document_id=document_id,
            limit=limit,
        )

        merged: list[dict[str, Any]] = []
        seen: set[tuple[Any, ...]] = set()
        for item in [*persisted, *client_history]:
            key = (
                item.get("role"),
                item.get("content"),
                item.get("parsed_intent"),
                item.get("case_id"),
                item.get("document_id"),
            )
            if key in seen:
                continue
            seen.add(key)
            merged.append(item)

        return merged[-limit:]

    def append_exchange(
        self,
        *,
        db: Session,
        tenant_id: int,
        user_id: int | None,
        mode: str,
        parsed_intent: str | None,
        user_message: str,
        assistant_message: str,
        case_id: int | None,
        document_id: int | None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        normalized_user = str(user_message or "").strip()
        normalized_assistant = str(assistant_message or "").strip()
        if not normalized_user or not normalized_assistant:
            return

        safe_mode = str(mode or "default").strip().lower() or "default"
        safe_intent = str(parsed_intent or "").strip() or None

        try:
            db.add(
                CaseMemoryEntry(
                    tenant_id=tenant_id,
                    user_id=user_id,
                    case_id=case_id,
                    document_id=document_id,
                    role="user",
                    message=normalized_user[: self.MAX_MESSAGE_CHARS],
                    parsed_intent=safe_intent,
                    mode=safe_mode,
                    metadata_json=None,
                )
            )
            db.add(
                CaseMemoryEntry(
                    tenant_id=tenant_id,
                    user_id=user_id,
                    case_id=case_id,
                    document_id=document_id,
                    role="assistant",
                    message=normalized_assistant[: self.MAX_MESSAGE_CHARS],
                    parsed_intent=safe_intent,
                    mode=safe_mode,
                    metadata_json=self._dumps_metadata(metadata or {}),
                )
            )
            db.commit()
        except Exception:
            db.rollback()

    def _load_persisted_history(
        self,
        *,
        db: Session,
        tenant_id: int,
        user_id: int | None,
        case_id: int | None,
        document_id: int | None,
        limit: int,
    ) -> list[dict[str, Any]]:
        query = db.query(CaseMemoryEntry).filter(CaseMemoryEntry.tenant_id == tenant_id)
        if user_id is not None:
            query = query.filter(CaseMemoryEntry.user_id == user_id)

        if document_id is not None:
            scope_filters: list[Any] = [CaseMemoryEntry.document_id == document_id]
            if case_id is not None:
                scope_filters.append(
                    and_(
                        CaseMemoryEntry.document_id.is_(None),
                        CaseMemoryEntry.case_id == case_id,
                    )
                )
            query = query.filter(or_(*scope_filters))
        elif case_id is not None:
            query = query.filter(CaseMemoryEntry.case_id == case_id)
        else:
            query = query.filter(
                CaseMemoryEntry.case_id.is_(None),
                CaseMemoryEntry.document_id.is_(None),
            )

        rows = (
            query.order_by(CaseMemoryEntry.created_at.desc(), CaseMemoryEntry.id.desc())
            .limit(limit * 3)
            .all()
        )
        rows = list(reversed(rows))

        history: list[dict[str, Any]] = []
        for row in rows:
            role = str(row.role or "").strip().lower()
            if role not in {"user", "assistant"}:
                continue
            content = str(row.message or "").strip()
            if not content:
                continue
            history.append(
                {
                    "role": role,
                    "content": content,
                    "parsed_intent": row.parsed_intent,
                    "case_id": row.case_id,
                    "document_id": row.document_id,
                }
            )
        return history[-limit:]

    @staticmethod
    def _normalize_history(conversation_history: Iterable[dict[str, Any]] | None) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        for item in conversation_history or []:
            if not isinstance(item, dict):
                continue
            role = str(item.get("role") or "").strip().lower()
            content = str(item.get("content") or "").strip()
            if role not in {"user", "assistant"} or not content:
                continue
            case_id = item.get("case_id")
            document_id = item.get("document_id")
            items.append(
                {
                    "role": role,
                    "content": content,
                    "parsed_intent": str(item.get("parsed_intent") or "").strip() or None,
                    "case_id": int(case_id) if isinstance(case_id, int) else None,
                    "document_id": int(document_id) if isinstance(document_id, int) else None,
                }
            )
        return items

    @staticmethod
    def _dumps_metadata(value: dict[str, Any]) -> str | None:
        if not value:
            return None
        try:
            return json.dumps(value, ensure_ascii=False)
        except Exception:
            return None


copilot_memory_service = CopilotMemoryService()
