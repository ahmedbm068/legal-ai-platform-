"""Step 3D — Legal Search execution extracted from CopilotService.

Wraps the LegalSearchModeService call + trust-state normalisation that
previously lived inline inside CopilotService.handle_message().

CopilotService keeps a compatibility shim that delegates here.
All logic inside LegalSearchModeService is untouched.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

_logger = logging.getLogger("copilot.legal_search")


class CopilotLegalSearchExecutionService:
    """Dedicated execution service for the Legal Search / Legal Research mode.

    Instantiated once in CopilotService.__init__ and called via the
    compatibility shim that replaces the ``use_trust_engine`` branch.

    The ``runtime`` parameter (CopilotService instance) is accepted so that
    ``_normalize_trust_state`` and ``_strip_heavy_trust_diagnostics`` remain in
    one place without duplication.  It is typed as Any to avoid a circular
    import.
    """

    def __init__(
        self,
        *,
        legal_search_mode_service: Any,
    ) -> None:
        self.legal_search_mode_service = legal_search_mode_service

    # ──────────────────────────────────────────────────────────────────────────
    # Public entry point
    # ──────────────────────────────────────────────────────────────────────────

    def execute(
        self,
        *,
        runtime: Any,  # CopilotService — typed Any to avoid circular import
        db: Session,
        tenant_id: int,
        user_role: str,
        message: str,
        top_k: int,
        case_id: Optional[int] = None,
        document_id: Optional[int] = None,
        conversation_history: Optional[List[Dict[str, Any]]] = None,
        intent: Optional[str] = None,
        target_type: Optional[str] = None,
        target_id: Optional[int] = None,
        retrieval_agent: Any = None,
        multilingual_output: bool = False,
        code_scope: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        started = time.perf_counter()
        _logger.debug(
            "[LEGAL_SEARCH] legal_search_execution_start | intent=%s case_id=%s mode=legal_search",
            intent,
            case_id,
        )

        result = self.legal_search_mode_service.run(
            db=db,
            tenant_id=tenant_id,
            user_role=user_role,
            message=message,
            top_k=top_k,
            case_id=case_id,
            document_id=document_id,
            conversation_history=conversation_history,
            intent=intent,
            target_type=target_type,
            target_id=target_id,
            retrieval_agent=retrieval_agent,
            multilingual_output=multilingual_output,
            code_scope=code_scope,
        )

        # Normalise trust state exactly as before — delegates to CopilotService
        # so the logic stays in one place.
        result = runtime._normalize_trust_state(result)

        duration_ms = (time.perf_counter() - started) * 1000.0

        # Probe result for log fields — never log full message/document text
        sources_count = len(result.get("sources") or [])
        citations_count = len(result.get("citations") or [])
        trust_panel = result.get("trust_panel") or {}
        jurisdiction = (
            str(result.get("jurisdiction_country") or "")
            or str((trust_panel if isinstance(trust_panel, dict) else {}).get("jurisdiction_country") or "")
            or "unknown"
        )
        _logger.debug(
            "[LEGAL_SEARCH] legal_search_execution_end | intent=%s case_id=%s jurisdiction=%s "
            "sources_count=%s citations_count=%s confidence=%s used_fallback=%s duration_ms=%.0f",
            intent,
            case_id,
            jurisdiction,
            sources_count,
            citations_count,
            result.get("confidence"),
            result.get("used_fallback"),
            duration_ms,
        )

        return result


__all__ = ["CopilotLegalSearchExecutionService"]
