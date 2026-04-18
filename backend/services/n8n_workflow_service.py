from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

import requests

from backend.core.config import settings
from backend.models.call_session import CallSession
from backend.models.case import Case
from backend.models.client import Client
from backend.models.user import User
from backend.services.call_transcript_service import build_conversation_transcript, build_call_summary


logger = logging.getLogger(__name__)


class N8nWorkflowService:
    def is_configured(self) -> bool:
        return bool((settings.N8N_WORKFLOW_WEBHOOK_URL or "").strip())

    def build_manual_whatsapp_url(self, phone: str, message: str) -> str | None:
        normalized_phone = "".join(character for character in (phone or "") if character.isdigit())
        if not normalized_phone:
            return None

        encoded_message = requests.utils.quote(message or "")
        return f"https://web.whatsapp.com/send?phone={normalized_phone}&text={encoded_message}"

    def build_consent_message(self, *, case: Case, client: Client, lawyer: User | None, caller_phone: str) -> str:
        lawyer_name = lawyer.name if lawyer else "your lawyer"
        case_title = (case.title or "your case").strip()
        client_name = (client.name or "there").strip()
        return (
            f"Hello {client_name}, this is {lawyer_name} from Legal AI about {case_title}. "
            f"Please reply YES to confirm that we can continue this WhatsApp call and record the conversation. "
            f"If you agree, we will continue from {caller_phone}."
        )

    def dispatch_event(self, *, event_type: str, payload: dict[str, Any]) -> dict[str, Any]:
        webhook_url = (settings.N8N_WORKFLOW_WEBHOOK_URL or "").strip()
        if not webhook_url:
            return {
                "success": False,
                "reason": "N8N_WORKFLOW_WEBHOOK_URL is not configured.",
            }

        headers = {"Content-Type": "application/json"}
        if settings.N8N_WEBHOOK_SECRET:
            headers["X-N8N-SECRET"] = settings.N8N_WEBHOOK_SECRET

        body = {
            "event_type": event_type,
            "dispatched_at": datetime.now(timezone.utc).isoformat(),
            **payload,
        }

        try:
            response = requests.post(
                webhook_url,
                json=body,
                headers=headers,
                timeout=max(5, int(settings.N8N_REQUEST_TIMEOUT_SECONDS)),
            )
            response.raise_for_status()
            return {
                "success": True,
                "status_code": response.status_code,
                "response_text": response.text[:500] if response.text else "",
            }
        except Exception as exc:
            logger.warning("N8N event dispatch failed for event_type=%s: %s", event_type, exc)
            return {
                "success": False,
                "reason": str(exc),
            }

    def request_consent(self, *, call_session: CallSession, case: Case, client: Client, lawyer: User | None) -> dict[str, Any]:
        caller_phone = (call_session.caller_phone or lawyer.phone or "").strip()
        consent_message = self.build_consent_message(case=case, client=client, lawyer=lawyer, caller_phone=caller_phone)
        whatsapp_chat_url = self.build_manual_whatsapp_url(call_session.client_phone or client.phone or "", consent_message)
        return {
            "success": False,
            "consent_message": consent_message,
            "delivery_mode": "manual",
            "whatsapp_chat_url": whatsapp_chat_url,
        }

    def build_conversation_transcript(self, *, transcript_text: str | None, conversation_turns: list[dict[str, Any]] | None = None) -> str | None:
        return build_conversation_transcript(transcript_text, conversation_turns=conversation_turns)

    def build_summary(self, transcript_text: str | None) -> str | None:
        return build_call_summary(transcript_text)


n8n_workflow_service = N8nWorkflowService()
