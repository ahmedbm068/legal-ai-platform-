from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from backend.models.case import Case
from backend.models.case_context_snapshot import CaseContextSnapshot
from backend.models.consultation_request import ConsultationRequest
from backend.models.document import Document
from backend.models.voice_recording import VoiceRecording
from backend.services.ai.agents.case_reasoning_agent import case_reasoning_agent


class CaseSnapshotService:
    def get_snapshot(
        self,
        *,
        db: Session,
        tenant_id: int,
        case_id: int | None,
    ) -> CaseContextSnapshot | None:
        if not isinstance(case_id, int):
            return None
        return (
            db.query(CaseContextSnapshot)
            .filter(
                CaseContextSnapshot.tenant_id == tenant_id,
                CaseContextSnapshot.case_id == case_id,
            )
            .first()
        )

    def refresh_case_snapshot(
        self,
        *,
        db: Session,
        tenant_id: int,
        case_id: int,
    ) -> dict[str, Any]:
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
            raise ValueError("Case not found for snapshot refresh.")

        documents = (
            db.query(Document)
            .filter(
                Document.case_id == case.id,
                Document.tenant_id == tenant_id,
            )
            .order_by(Document.upload_timestamp.desc(), Document.id.desc())
            .all()
        )
        consultations = (
            db.query(ConsultationRequest)
            .filter(
                ConsultationRequest.case_id == case.id,
                ConsultationRequest.tenant_id == tenant_id,
            )
            .order_by(ConsultationRequest.updated_at.desc(), ConsultationRequest.id.desc())
            .all()
        )
        recordings = (
            db.query(VoiceRecording)
            .filter(
                VoiceRecording.case_id == case.id,
                VoiceRecording.tenant_id == tenant_id,
            )
            .order_by(VoiceRecording.updated_at.desc(), VoiceRecording.id.desc())
            .all()
        )

        reasoning = {}
        summary_text = ""
        if documents:
            reasoning_result = case_reasoning_agent.analyze_case(
                case=case,
                documents=documents,
                jurisdiction_country=case.jurisdiction_country,
                consultation_requests=consultations,
                voice_recordings=recordings,
            )
            if reasoning_result.success:
                reasoning = dict(reasoning_result.payload)
                summary_text = str(
                    reasoning.get("narrative_summary")
                    or reasoning.get("overview")
                    or reasoning.get("summary")
                    or ""
                ).strip()

        latest_source_update = self._latest_source_update(documents=documents, consultations=consultations, recordings=recordings)
        payload = {
            "case": {
                "id": case.id,
                "title": case.title,
                "status": case.status,
                "jurisdiction_country": case.jurisdiction_country,
            },
            "facts": {
                "document_count": len(documents),
                "consultation_count": len(consultations),
                "voice_recording_count": len(recordings),
            },
            "reasoning": reasoning,
            "citations": self._build_citations(reasoning),
            "source_updated_at": latest_source_update.isoformat() if latest_source_update else None,
        }

        snapshot = self.get_snapshot(db=db, tenant_id=tenant_id, case_id=case_id)
        next_version = 1
        if snapshot:
            next_version = int(snapshot.version or 0) + 1
            snapshot.version = next_version
            snapshot.summary_text = summary_text or snapshot.summary_text
            snapshot.snapshot_json = json.dumps(payload, ensure_ascii=False)
            snapshot.source_updated_at = latest_source_update
            snapshot.refreshed_at = datetime.now(timezone.utc)
        else:
            snapshot = CaseContextSnapshot(
                tenant_id=tenant_id,
                case_id=case_id,
                version=next_version,
                summary_text=summary_text,
                snapshot_json=json.dumps(payload, ensure_ascii=False),
                source_updated_at=latest_source_update,
                refreshed_at=datetime.now(timezone.utc),
            )
            db.add(snapshot)

        db.commit()
        db.refresh(snapshot)
        return self.to_public_payload(snapshot)

    @staticmethod
    def to_public_payload(snapshot: CaseContextSnapshot | None) -> dict[str, Any] | None:
        if snapshot is None:
            return None
        try:
            parsed = json.loads(snapshot.snapshot_json or "{}")
            payload = parsed if isinstance(parsed, dict) else {}
        except Exception:
            payload = {}
        payload.update(
            {
                "version": snapshot.version,
                "summary_text": snapshot.summary_text,
                "refreshed_at": snapshot.refreshed_at.isoformat() if snapshot.refreshed_at else None,
            }
        )
        return payload

    @staticmethod
    def _build_citations(reasoning_payload: dict[str, Any]) -> list[dict[str, Any]]:
        citations = []
        for item in reasoning_payload.get("sources") or []:
            snippet = str(item.get("snippet") or "").strip()
            citations.append(
                {
                    "label": str(item.get("filename") or "Source").strip(),
                    "document_id": item.get("document_id"),
                    "case_id": item.get("case_id"),
                    "snippet": snippet[:280],
                }
            )
        return citations[:10]

    @staticmethod
    def _latest_source_update(
        *,
        documents: list[Document],
        consultations: list[ConsultationRequest],
        recordings: list[VoiceRecording],
    ) -> datetime | None:
        candidates: list[datetime] = []
        for row in documents:
            if row.upload_timestamp:
                candidates.append(row.upload_timestamp)
            if row.last_intelligence_run_at:
                candidates.append(row.last_intelligence_run_at)
        for row in consultations:
            if row.updated_at:
                candidates.append(row.updated_at)
        for row in recordings:
            if row.updated_at:
                candidates.append(row.updated_at)
        return max(candidates) if candidates else None


case_snapshot_service = CaseSnapshotService()
