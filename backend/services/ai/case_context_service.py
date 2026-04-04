from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from backend.models.case import Case
from backend.models.case_memory_entry import CaseMemoryEntry
from backend.models.consultation_request import ConsultationRequest
from backend.models.document import Document
from backend.models.voice_recording import VoiceRecording


class CaseContextService:
    def build_context(
        self,
        *,
        db: Session,
        tenant_id: int,
        case_id: int | None,
        document_id: int | None = None,
    ) -> dict[str, Any]:
        if not isinstance(case_id, int):
            return {
                "scope": "global",
                "case": None,
                "timeline": [],
                "risk_signals": [],
                "memory": {
                    "recent_turns": 0,
                },
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
                "scope": "case",
                "case": None,
                "timeline": [],
                "risk_signals": [],
                "memory": {
                    "recent_turns": 0,
                },
            }

        documents = (
            db.query(Document)
            .filter(
                Document.tenant_id == tenant_id,
                Document.case_id == case.id,
            )
            .order_by(Document.upload_timestamp.desc(), Document.id.desc())
            .all()
        )
        consultations = (
            db.query(ConsultationRequest)
            .filter(
                ConsultationRequest.tenant_id == tenant_id,
                ConsultationRequest.case_id == case.id,
            )
            .order_by(ConsultationRequest.updated_at.desc(), ConsultationRequest.id.desc())
            .all()
        )
        recordings = (
            db.query(VoiceRecording)
            .filter(
                VoiceRecording.tenant_id == tenant_id,
                VoiceRecording.case_id == case.id,
            )
            .order_by(VoiceRecording.updated_at.desc(), VoiceRecording.id.desc())
            .all()
        )

        memory_rows = (
            db.query(CaseMemoryEntry)
            .filter(
                CaseMemoryEntry.tenant_id == tenant_id,
                CaseMemoryEntry.case_id == case.id,
            )
            .order_by(CaseMemoryEntry.created_at.desc(), CaseMemoryEntry.id.desc())
            .limit(24)
            .all()
        )

        return {
            "scope": "document" if isinstance(document_id, int) else "case",
            "case": {
                "id": case.id,
                "title": case.title,
                "status": case.status,
                "jurisdiction_country": case.jurisdiction_country,
                "document_count": len(documents),
                "consultation_count": len(consultations),
                "voice_recording_count": len(recordings),
            },
            "timeline": self._build_timeline_snapshot(documents=documents, consultations=consultations, recordings=recordings),
            "risk_signals": self._build_risk_signals(documents=documents, consultations=consultations),
            "memory": {
                "recent_turns": len(memory_rows),
                "latest_intents": self._latest_intents(memory_rows),
            },
        }

    @staticmethod
    def _build_timeline_snapshot(
        *,
        documents: list[Document],
        consultations: list[ConsultationRequest],
        recordings: list[VoiceRecording],
    ) -> list[dict[str, Any]]:
        events: list[dict[str, Any]] = []

        for row in documents[:8]:
            if row.upload_timestamp is None:
                continue
            events.append(
                {
                    "event_type": "document_uploaded",
                    "label": row.filename,
                    "timestamp": row.upload_timestamp.isoformat(),
                }
            )

        for row in consultations[:8]:
            if row.updated_at is None:
                continue
            events.append(
                {
                    "event_type": "consultation_status",
                    "label": row.status,
                    "timestamp": row.updated_at.isoformat(),
                }
            )

        for row in recordings[:8]:
            if row.updated_at is None:
                continue
            events.append(
                {
                    "event_type": "voice_recording",
                    "label": row.transcription_status,
                    "timestamp": row.updated_at.isoformat(),
                }
            )

        def parse_ts(item: dict[str, Any]) -> datetime:
            value = str(item.get("timestamp") or "").strip()
            if not value:
                return datetime.min
            try:
                return datetime.fromisoformat(value.replace("Z", "+00:00"))
            except Exception:
                return datetime.min

        events.sort(key=parse_ts, reverse=True)
        return events[:12]

    @staticmethod
    def _build_risk_signals(
        *,
        documents: list[Document],
        consultations: list[ConsultationRequest],
    ) -> list[str]:
        risks: list[str] = []

        for row in documents:
            if row.processing_status == "failed":
                risks.append(f"Document processing failed: {row.filename}")
            if row.summary_status == "failed":
                risks.append(f"Document summary failed: {row.filename}")

            insights_payload = CaseContextService._safe_load_json(row.insights_json)
            for item in insights_payload.get("legal_risks") or []:
                text = str(item or "").strip()
                if text and text not in risks:
                    risks.append(text)
                if len(risks) >= 12:
                    break
            if len(risks) >= 12:
                break

        if any(row.urgency_level == "urgent" for row in consultations):
            risks.append("At least one consultation request is marked urgent.")

        deduped: list[str] = []
        for item in risks:
            if item not in deduped:
                deduped.append(item)
        return deduped[:12]

    @staticmethod
    def _safe_load_json(raw_value: str | None) -> dict[str, Any]:
        if not raw_value:
            return {}
        try:
            payload = json.loads(raw_value)
            return payload if isinstance(payload, dict) else {}
        except Exception:
            return {}

    @staticmethod
    def _latest_intents(rows: list[CaseMemoryEntry]) -> list[str]:
        intents: list[str] = []
        for row in rows:
            parsed_intent = str(row.parsed_intent or "").strip()
            if not parsed_intent:
                continue
            if parsed_intent not in intents:
                intents.append(parsed_intent)
            if len(intents) >= 5:
                break
        return intents


case_context_service = CaseContextService()
