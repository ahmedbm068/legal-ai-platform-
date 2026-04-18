from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy.orm import Session

from backend.models.appointment import Appointment
from backend.models.case import Case
from backend.models.document import Document
from backend.services.ai.document_insight_service import document_insight_service
from backend.services.calendar_service import normalize_appointment_type, normalize_scope, normalize_status


class DocumentCalendarSyncService:
    AUTO_SOURCE = "document_key_dates"
    AUTO_NOTES_PREFIX = "doc_key_date"
    MAX_EVENTS_PER_DOCUMENT = 8
    DEFAULT_EVENT_HOUR_UTC = 9
    MONTH_NAMES = (
        "january|february|march|april|may|june|july|august|"
        "september|october|november|december"
    )

    def sync_document_key_dates(self, *, db: Session, document: Document) -> dict[str, Any]:
        case_id = int(document.case_id or 0)
        tenant_id = int(document.tenant_id or 0)
        if case_id <= 0 or tenant_id <= 0:
            return {
                "created_count": 0,
                "skipped_count": 0,
                "reason": "missing_case_or_tenant",
            }

        key_date_items = self._load_key_date_items(document)
        if not key_date_items:
            return {
                "created_count": 0,
                "skipped_count": 0,
                "reason": "no_key_dates_found",
            }

        case = (
            db.query(Case)
            .filter(
                Case.id == case_id,
                Case.tenant_id == tenant_id,
                Case.deleted_at.is_(None),
            )
            .first()
        )
        if not case:
            return {
                "created_count": 0,
                "skipped_count": 0,
                "reason": "case_not_found",
            }

        existing_markers = self._existing_markers(db=db, case_id=case.id)
        created_ids: list[int] = []
        skipped_count = 0

        for item in key_date_items[: self.MAX_EVENTS_PER_DOCUMENT]:
            label = self._normalize_label(item.get("label"))
            raw_value = str(item.get("value") or "").strip()
            if not label or not raw_value:
                skipped_count += 1
                continue

            parsed_dt = self._parse_absolute_datetime(raw_value)
            if parsed_dt is None:
                skipped_count += 1
                continue

            marker = self._build_marker(document_id=document.id, label=label, scheduled_at=parsed_dt)
            if marker in existing_markers:
                skipped_count += 1
                continue

            appointment = Appointment(
                case_id=case.id,
                tenant_id=case.tenant_id,
                lawyer_id=case.lawyer_id,
                client_id=case.client_id,
                consultation_request_id=None,
                created_by_user_id=None,
                title=f"Key date: {self._humanize_label(label)}",
                description=(
                    f"Extracted from document '{document.filename}' as '{raw_value}'. "
                    "Please validate and adjust if needed."
                )[:4000],
                appointment_type=normalize_appointment_type("deadline"),
                visibility_scope=normalize_scope("shared"),
                status=normalize_status("tentative"),
                scheduled_at=parsed_dt,
                duration_minutes=30,
                location="Document timeline",
                timezone_name="UTC",
                ai_summary=f"Auto-created from document key date: {raw_value}"[:4000],
                ai_recommendation="Validate this extracted key date and keep it if it is legally relevant."[:4000],
                ai_confidence="medium",
                ai_source=self.AUTO_SOURCE,
                notes=marker,
            )
            db.add(appointment)
            db.flush()

            created_ids.append(int(appointment.id))
            existing_markers.add(marker)

        if created_ids:
            db.commit()

        return {
            "created_count": len(created_ids),
            "created_ids": created_ids,
            "skipped_count": skipped_count,
            "considered_count": len(key_date_items[: self.MAX_EVENTS_PER_DOCUMENT]),
        }

    def _load_key_date_items(self, document: Document) -> list[dict[str, str]]:
        parsed_insights: dict[str, Any] = {}
        if document.insights_json:
            try:
                loaded = json.loads(document.insights_json)
                if isinstance(loaded, dict):
                    parsed_insights = loaded
            except Exception:
                parsed_insights = {}

        if not parsed_insights:
            try:
                parsed_insights = document_insight_service.build_insights(document)
            except Exception:
                parsed_insights = {}

        raw_dates = parsed_insights.get("important_dates") or []
        if not isinstance(raw_dates, list):
            return []

        normalized: list[dict[str, str]] = []
        for item in raw_dates:
            if not isinstance(item, dict):
                continue
            label = self._normalize_label(item.get("label"))
            value = str(item.get("value") or "").strip()
            if label and value:
                normalized.append({"label": label, "value": value})

        return normalized

    def _existing_markers(self, *, db: Session, case_id: int) -> set[str]:
        rows = (
            db.query(Appointment.notes)
            .filter(
                Appointment.case_id == case_id,
                Appointment.ai_source == self.AUTO_SOURCE,
                Appointment.notes.isnot(None),
            )
            .all()
        )
        markers: set[str] = set()
        for row in rows:
            value = row[0] if isinstance(row, tuple) else row
            marker = str(value or "").strip()
            if marker:
                markers.add(marker)
        return markers

    @staticmethod
    def _normalize_label(value: Any) -> str:
        cleaned = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
        cleaned = re.sub(r"[^a-z0-9_]+", "", cleaned)
        cleaned = re.sub(r"_+", "_", cleaned).strip("_")
        return cleaned

    @staticmethod
    def _humanize_label(value: str) -> str:
        return " ".join(part.capitalize() for part in str(value or "").replace("_", " ").split()) or "Date"

    def _build_marker(self, *, document_id: int, label: str, scheduled_at: datetime) -> str:
        normalized_dt = scheduled_at.astimezone(timezone.utc).replace(microsecond=0).isoformat()
        return (
            f"{self.AUTO_NOTES_PREFIX}"
            f"|document_id={int(document_id)}"
            f"|label={label}"
            f"|scheduled_at={normalized_dt}"
        )

    def _parse_absolute_datetime(self, value: str) -> Optional[datetime]:
        text = self._normalize_date_text(value)
        if not text:
            return None

        iso_match = re.search(
            r"\b\d{4}-\d{2}-\d{2}(?:[T\s]\d{2}:\d{2}(?::\d{2})?)?(?:Z|[+-]\d{2}:?\d{2})?\b",
            text,
            flags=re.IGNORECASE,
        )
        if iso_match:
            iso_text = iso_match.group(0).replace("Z", "+00:00")
            parsed_iso = self._parse_iso_datetime(iso_text)
            if parsed_iso is not None:
                return parsed_iso

        month_day_match = re.search(
            rf"\b\d{{1,2}}\s+(?:{self.MONTH_NAMES})\s+\d{{4}}(?:\s+\d{{2}}:\d{{2}}(?::\d{{2}})?)?\b",
            text,
            flags=re.IGNORECASE,
        )
        if month_day_match:
            parsed = self._parse_with_patterns(
                month_day_match.group(0),
                patterns=("%d %B %Y %H:%M:%S", "%d %B %Y %H:%M", "%d %b %Y %H:%M:%S", "%d %b %Y %H:%M", "%d %B %Y", "%d %b %Y"),
            )
            if parsed is not None:
                return parsed

        month_lead_match = re.search(
            rf"\b(?:{self.MONTH_NAMES})\s+\d{{1,2}}\s+\d{{4}}(?:\s+\d{{2}}:\d{{2}}(?::\d{{2}})?)?\b",
            text,
            flags=re.IGNORECASE,
        )
        if month_lead_match:
            parsed = self._parse_with_patterns(
                month_lead_match.group(0),
                patterns=("%B %d %Y %H:%M:%S", "%B %d %Y %H:%M", "%b %d %Y %H:%M:%S", "%b %d %Y %H:%M", "%B %d %Y", "%b %d %Y"),
            )
            if parsed is not None:
                return parsed

        numeric_match = re.search(
            r"\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}(?:\s+\d{2}:\d{2}(?::\d{2})?)?\b",
            text,
            flags=re.IGNORECASE,
        )
        if numeric_match:
            parsed = self._parse_with_patterns(
                numeric_match.group(0),
                patterns=(
                    "%d/%m/%Y %H:%M:%S",
                    "%d/%m/%Y %H:%M",
                    "%m/%d/%Y %H:%M:%S",
                    "%m/%d/%Y %H:%M",
                    "%d-%m-%Y %H:%M:%S",
                    "%d-%m-%Y %H:%M",
                    "%m-%d-%Y %H:%M:%S",
                    "%m-%d-%Y %H:%M",
                    "%d/%m/%Y",
                    "%m/%d/%Y",
                    "%d-%m-%Y",
                    "%m-%d-%Y",
                ),
            )
            if parsed is not None:
                return parsed

        return None

    def _parse_iso_datetime(self, value: str) -> Optional[datetime]:
        try:
            parsed = datetime.fromisoformat(value)
        except ValueError:
            return None

        if parsed.tzinfo is None:
            if "T" not in value and " " not in value:
                parsed = parsed.replace(hour=self.DEFAULT_EVENT_HOUR_UTC, minute=0, second=0, microsecond=0)
            parsed = parsed.replace(tzinfo=timezone.utc)
        else:
            parsed = parsed.astimezone(timezone.utc)

        return parsed

    def _parse_with_patterns(self, value: str, *, patterns: tuple[str, ...]) -> Optional[datetime]:
        cleaned = self._normalize_date_text(value)
        if not cleaned:
            return None

        has_explicit_time = bool(re.search(r"\b\d{2}:\d{2}(?::\d{2})?\b", cleaned))
        for pattern in patterns:
            try:
                parsed = datetime.strptime(cleaned, pattern)
            except ValueError:
                continue

            if not has_explicit_time:
                parsed = parsed.replace(hour=self.DEFAULT_EVENT_HOUR_UTC, minute=0, second=0, microsecond=0)
            return parsed.replace(tzinfo=timezone.utc)

        return None

    @staticmethod
    def _normalize_date_text(value: str) -> str:
        cleaned = str(value or "").strip()
        cleaned = re.sub(r"(\d{1,2})(st|nd|rd|th)\b", r"\1", cleaned, flags=re.IGNORECASE)
        cleaned = cleaned.replace(",", " ")
        cleaned = re.sub(r"\s+", " ", cleaned)
        return cleaned


document_calendar_sync_service = DocumentCalendarSyncService()
