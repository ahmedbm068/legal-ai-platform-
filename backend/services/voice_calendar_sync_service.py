from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy.orm import Session

from backend.models.appointment import Appointment
from backend.models.case import Case
from backend.models.voice_recording import VoiceRecording
from backend.services.ai.document_insight_service import document_insight_service
from backend.services.calendar_service import normalize_appointment_type, normalize_scope, normalize_status
from backend.services.document_calendar_sync_service import document_calendar_sync_service


class VoiceCalendarSyncService:
    AUTO_SOURCE = "voice_key_dates"
    AUTO_NOTES_PREFIX = "voice_key_date"
    MAX_EVENTS_PER_RECORDING = 8
    CONTEXT_WINDOW_CHARS = 90

    MONTH_NAMES = (
        "january|february|march|april|may|june|july|august|"
        "september|october|november|december"
    )

    def sync_recording_key_dates(self, *, db: Session, recording: VoiceRecording) -> dict[str, Any]:
        case_id = int(recording.case_id or 0)
        tenant_id = int(recording.tenant_id or 0)
        if case_id <= 0 or tenant_id <= 0:
            return {
                "created_count": 0,
                "skipped_count": 0,
                "reason": "missing_case_or_tenant",
            }

        transcript_text = str(recording.conversation_transcript_text or recording.transcript_text or "").strip()
        if not transcript_text:
            return {
                "created_count": 0,
                "skipped_count": 0,
                "reason": "no_transcript_text",
            }

        key_date_items = self._extract_key_date_items(transcript_text)
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

        for item in key_date_items[: self.MAX_EVENTS_PER_RECORDING]:
            label = self._normalize_label(item.get("label"))
            raw_value = str(item.get("value") or "").strip()
            if not label or not raw_value:
                skipped_count += 1
                continue

            parsed_dt = self._parse_absolute_datetime(raw_value)
            if parsed_dt is None:
                skipped_count += 1
                continue

            marker = self._build_marker(recording_id=recording.id, label=label, scheduled_at=parsed_dt)
            if marker in existing_markers:
                skipped_count += 1
                continue

            context = self._extract_context_around_value(transcript_text, raw_value)
            appointment = Appointment(
                case_id=case.id,
                tenant_id=case.tenant_id,
                lawyer_id=case.lawyer_id,
                client_id=case.client_id,
                consultation_request_id=None,
                created_by_user_id=None,
                title=f"Voice date: {self._humanize_label(label)}",
                description=(
                    f"Extracted from voice recording '{recording.filename}' as '{raw_value}'."
                    + (f" Context: {context}" if context else "")
                    + " Please validate and adjust if needed."
                )[:4000],
                appointment_type=normalize_appointment_type("deadline"),
                visibility_scope=normalize_scope("shared"),
                status=normalize_status("tentative"),
                scheduled_at=parsed_dt,
                duration_minutes=30,
                location="Voice transcript",
                timezone_name="UTC",
                ai_summary=f"Auto-created from voice transcript date: {raw_value}"[:4000],
                ai_recommendation="Validate this extracted date from the transcript and keep it if it is legally relevant."[:4000],
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
            "considered_count": len(key_date_items[: self.MAX_EVENTS_PER_RECORDING]),
        }

    def _extract_key_date_items(self, text: str) -> list[dict[str, str]]:
        results: list[dict[str, str]] = []
        seen: set[tuple[str, str]] = set()

        try:
            insight_items = document_insight_service._extract_important_dates(text)
        except Exception:
            insight_items = []

        if isinstance(insight_items, list):
            for item in insight_items:
                if not isinstance(item, dict):
                    continue
                label = self._normalize_label(item.get("label"))
                value = self._normalize_date_text(str(item.get("value") or ""))
                if not value:
                    continue

                if not label:
                    label = "mentioned_date"

                key = (label, value.lower())
                if key in seen:
                    continue

                seen.add(key)
                results.append({"label": label, "value": value})

        for raw_value in self._extract_absolute_date_strings(text):
            value = self._normalize_date_text(raw_value)
            if not value:
                continue

            key = ("mentioned_date", value.lower())
            if key in seen:
                continue

            seen.add(key)
            results.append({"label": "mentioned_date", "value": value})

        return results[: self.MAX_EVENTS_PER_RECORDING]

    def _extract_absolute_date_strings(self, text: str) -> list[str]:
        if not text:
            return []

        patterns = (
            r"\b\d{4}-\d{2}-\d{2}(?:[T\s]\d{2}:\d{2}(?::\d{2})?)?(?:Z|[+-]\d{2}:?\d{2})?\b",
            rf"\b\d{{1,2}}(?:st|nd|rd|th)?\s+(?:{self.MONTH_NAMES})(?:,\s*|\s+)\d{{4}}(?:\s+\d{{2}}:\d{{2}}(?::\d{{2}})?)?\b",
            rf"\b(?:{self.MONTH_NAMES})\s+\d{{1,2}}(?:st|nd|rd|th)?(?:,\s*|\s+)\d{{4}}(?:\s+\d{{2}}:\d{{2}}(?::\d{{2}})?)?\b",
            r"\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}(?:\s+\d{2}:\d{2}(?::\d{2})?)?\b",
        )

        seen: set[str] = set()
        values: list[str] = []
        for pattern in patterns:
            for match in re.finditer(pattern, text, flags=re.IGNORECASE):
                raw = str(match.group(0) or "").strip()
                normalized = self._normalize_date_text(raw)
                if not normalized:
                    continue
                lowered = normalized.lower()
                if lowered in seen:
                    continue
                seen.add(lowered)
                values.append(normalized)
        return values

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

    def _build_marker(self, *, recording_id: int, label: str, scheduled_at: datetime) -> str:
        normalized_dt = scheduled_at.astimezone(timezone.utc).replace(microsecond=0).isoformat()
        return (
            f"{self.AUTO_NOTES_PREFIX}"
            f"|recording_id={int(recording_id)}"
            f"|label={label}"
            f"|scheduled_at={normalized_dt}"
        )

    def _parse_absolute_datetime(self, value: str) -> Optional[datetime]:
        return document_calendar_sync_service._parse_absolute_datetime(value)

    def _normalize_date_text(self, value: str) -> str:
        return document_calendar_sync_service._normalize_date_text(value)

    def _extract_context_around_value(self, text: str, value: str) -> str:
        normalized_text = re.sub(r"\s+", " ", str(text or "")).strip()
        needle = str(value or "").strip()
        if not normalized_text or not needle:
            return ""

        start_index = normalized_text.lower().find(needle.lower())
        if start_index < 0:
            return ""

        start = max(0, start_index - self.CONTEXT_WINDOW_CHARS)
        end = min(len(normalized_text), start_index + len(needle) + self.CONTEXT_WINDOW_CHARS)
        excerpt = normalized_text[start:end].strip()
        if start > 0:
            excerpt = f"...{excerpt}"
        if end < len(normalized_text):
            excerpt = f"{excerpt}..."
        return excerpt[:320]


voice_calendar_sync_service = VoiceCalendarSyncService()
