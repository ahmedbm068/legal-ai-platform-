from __future__ import annotations

import logging
from typing import Any


logger = logging.getLogger(__name__)


class CalendarAutomationHookService:
    """Central place for future n8n/webhook delivery.

    The current implementation records an app log only. Keeping the boundary
    explicit makes it straightforward to later POST these payloads into n8n.
    """

    def emit(self, event_name: str, payload: dict[str, Any]) -> None:
        safe_payload = {
            key: value
            for key, value in payload.items()
            if key not in {"source_quote", "description"}
        }
        logger.info("calendar automation hook: %s %s", event_name, safe_payload)


calendar_automation_hook_service = CalendarAutomationHookService()
