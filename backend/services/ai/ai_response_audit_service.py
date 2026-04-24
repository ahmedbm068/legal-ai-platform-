from __future__ import annotations

import json
from typing import Any

from sqlalchemy.orm import Session

from backend.models.ai_response_audit_log import AIResponseAuditLog
from backend.services.ai.llm_gateway import llm_gateway


class AIResponseAuditService:
    MAX_TEXT_CHARS = 64000

    @staticmethod
    def _dumps(value: Any) -> str | None:
        if value is None:
            return None
        try:
            return json.dumps(value, ensure_ascii=False)
        except Exception:
            return None

    def record(
        self,
        *,
        db: Session,
        tenant_id: int,
        user_id: int | None,
        endpoint: str,
        question: str,
        answer: str,
        parsed_intent: str | None = None,
        case_id: int | None = None,
        document_id: int | None = None,
        sources: list[dict[str, Any]] | None = None,
        trust_panel: dict[str, Any] | None = None,
        validation: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        question_text = str(question or "").strip()
        answer_text = str(answer or "").strip()
        if not question_text or not answer_text:
            return

        trust_panel_payload = trust_panel or {}
        try:
            db.add(
                AIResponseAuditLog(
                    tenant_id=tenant_id,
                    user_id=user_id,
                    case_id=case_id,
                    document_id=document_id,
                    endpoint=str(endpoint or "unknown").strip() or "unknown",
                    parsed_intent=str(parsed_intent or "").strip() or None,
                    response_version=str(trust_panel_payload.get("response_version") or "legal_trust_response_v1"),
                    model_name=llm_gateway.default_model,
                    prompt_version=str(trust_panel_payload.get("prompt_version") or "").strip() or None,
                    question_text=question_text[: self.MAX_TEXT_CHARS],
                    answer_text=answer_text[: self.MAX_TEXT_CHARS],
                    sources_json=self._dumps(sources or []),
                    trust_panel_json=self._dumps(trust_panel_payload),
                    validation_json=self._dumps(validation or {}),
                    metadata_json=self._dumps(metadata or {}),
                )
            )
            db.commit()
        except Exception:
            db.rollback()


ai_response_audit_service = AIResponseAuditService()
