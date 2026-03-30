from __future__ import annotations

import re
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from backend.models.case import Case
from backend.models.consultation_request import ConsultationRequest
from backend.models.document import Document
from backend.models.voice_recording import VoiceRecording
from backend.services.ai.agents.booking_agent import booking_agent
from backend.services.ai.agents.case_reasoning_agent import case_reasoning_agent
from backend.services.ai.agents.drafting_agent import drafting_agent
from backend.services.ai.agents.intake_agent import intake_agent
from backend.services.ai.agents.timeline_agent import timeline_agent
from backend.services.ai.agents.verifier_agent import verifier_agent
from backend.services.ai.artifact_versioning_service import artifact_versioning_service
from backend.services.ai.rag_service import RagService
from backend.services.ai.summarization_service import summarization_service


class AgentWorkflowService:
    TEMPLATE_NOISE_PATTERNS = (
        r"<case_id>",
        r"<document_id>",
        r"optimize prompt:",
        r"what success looks like",
        r"email for case #<",
        r"#<case_id>",
        r"sources appea",
        r"pdf_ready\.md",
    )

    def __init__(self, rag_service: RagService) -> None:
        self.rag_service = rag_service

    def run_case_workflow(
        self,
        *,
        db: Session,
        tenant_id: int,
        case_id: int,
        objective: str | None = None,
        top_k: int = 5,
    ) -> dict[str, Any]:
        case = self._get_case_or_404(db=db, tenant_id=tenant_id, case_id=case_id)
        documents = self._get_case_documents(db=db, tenant_id=tenant_id, case_id=case.id)
        if not documents:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="This case has no documents yet, so the workflow cannot run."
            )

        for document in documents:
            self._ensure_document_summary(db=db, document=document)

        consultation_requests = self._get_case_consultation_requests(
            db=db,
            tenant_id=tenant_id,
            case_id=case.id,
        )
        voice_recordings = self._get_case_voice_recordings(
            db=db,
            tenant_id=tenant_id,
            case_id=case.id,
        )

        workflow_objective = (
            (objective or "").strip()
            or "Prepare a grounded case brief, confirm the strongest evidence, and draft a client-ready update."
        )

        stages: dict[str, dict[str, Any]] = {}
        stage_outputs: dict[str, dict[str, Any]] = {}

        intake_stage = self._run_intake_stage(voice_recordings=voice_recordings)
        stages["intake"] = self._serialize_stage(intake_stage)
        stage_outputs["intake"] = intake_stage.payload

        retrieval_query = self._build_retrieval_query(case=case, objective=workflow_objective)
        retrieval_stage = self.rag_service.retrieval_agent.retrieve(
            db=db,
            tenant_id=tenant_id,
            question=retrieval_query,
            top_k=top_k,
            case_id=case.id,
            document_id=None,
        )
        stages["retrieval"] = self._serialize_stage(retrieval_stage)
        stage_outputs["retrieval"] = retrieval_stage.payload

        case_reasoning_stage = case_reasoning_agent.analyze_case(
            case=case,
            documents=documents,
            jurisdiction_country=case.jurisdiction_country,
            consultation_requests=consultation_requests,
            voice_recordings=voice_recordings,
        )
        stages["case_reasoning"] = self._serialize_stage(case_reasoning_stage)
        stage_outputs["case_reasoning"] = case_reasoning_stage.payload

        timeline_stage = timeline_agent.build_case_timeline(
            case_id=case.id,
            case_title=case.title,
            documents=documents,
            consultations=consultation_requests,
        )
        stages["timeline"] = self._serialize_stage(timeline_stage)
        stage_outputs["timeline"] = timeline_stage.payload

        booking_stage = booking_agent.analyze_consultations(
            case_id=case.id,
            case_title=case.title,
            consultations=consultation_requests,
        )
        stages["booking"] = self._serialize_stage(booking_stage)
        stage_outputs["booking"] = booking_stage.payload

        summary_text = self._sanitize_workflow_text(
            self._format_reasoning_summary(case_reasoning_stage.payload)
        ) or "Case evidence was retrieved, but no stable summary could be generated."
        formatted_sources = self._format_sources(retrieval_stage.payload.get("results") or [])
        verifier_stage = verifier_agent.verify_answer(
            question=retrieval_query,
            answer=summary_text,
            sources=formatted_sources,
        )
        stages["verifier"] = self._serialize_stage(verifier_stage)
        stage_outputs["verifier"] = verifier_stage.payload

        verified_candidate = str(verifier_stage.payload.get("supported_answer") or "").strip()
        use_verified_candidate = bool(
            verifier_stage.success
            and verified_candidate
            and len(verified_candidate) >= 80
            and not self._looks_like_prompt_template_noise(verified_candidate)
        )
        grounded_summary = self._sanitize_workflow_text(
            verified_candidate if use_verified_candidate else summary_text
        )
        if not grounded_summary:
            grounded_summary = summary_text

        drafting_stage = drafting_agent.draft_client_update_email(
            case_id=case.id,
            case_title=case.title,
            case_summary=grounded_summary,
            jurisdiction_country=case.jurisdiction_country,
        )
        stages["drafting"] = self._serialize_stage(drafting_stage)
        stage_outputs["drafting"] = drafting_stage.payload

        drafted_email = (drafting_stage.payload.get("email_body") or "").strip()
        if drafted_email:
            try:
                artifact_versioning_service.create_version(
                    db=db,
                    tenant_id=tenant_id,
                    artifact_type="case_email",
                    content=drafted_email,
                    case_id=case.id,
                    source_kind="agent_generation",
                    metadata={
                        "workflow": "agent_workflow",
                        "objective": workflow_objective,
                        "used_llm": bool(drafting_stage.payload.get("used_llm")),
                    },
                    auto_select=True,
                )
            except Exception:
                pass

        return {
            "case_id": case.id,
            "case_title": case.title,
            "objective": workflow_objective,
            "retrieval_query": retrieval_query,
            "summary": summary_text,
            "verified_summary": grounded_summary,
            "client_email": drafted_email,
            "sources": formatted_sources,
            "stages": stages,
            "stage_outputs": stage_outputs,
        }

    @classmethod
    def _looks_like_prompt_template_noise(cls, text: str) -> bool:
        candidate = str(text or "").strip().lower()
        if not candidate:
            return False
        return any(re.search(pattern, candidate) for pattern in cls.TEMPLATE_NOISE_PATTERNS)

    @classmethod
    def _sanitize_workflow_text(cls, text: str) -> str:
        candidate = str(text or "").strip()
        if not candidate:
            return ""

        lines: list[str] = []
        for raw_line in candidate.splitlines():
            line = raw_line.rstrip()
            if not line.strip():
                lines.append("")
                continue
            if cls._looks_like_prompt_template_noise(line):
                continue
            lines.append(line)

        sanitized = "\n".join(lines).strip()
        if not sanitized:
            return ""

        if cls._looks_like_prompt_template_noise(sanitized):
            return ""

        return sanitized

    def _run_intake_stage(self, *, voice_recordings: list[VoiceRecording]):
        transcript_parts = [
            (recording.transcript_text or "").strip()
            for recording in voice_recordings
            if (recording.transcript_text or "").strip()
        ]
        if not transcript_parts:
            return intake_agent.result(
                success=True,
                payload={},
                warnings=["No transcripts were available for intake-stage orchestration."],
                trace=["Skipped intake stage because no voice transcripts were available."],
            )

        merged_transcript = "\n\n".join(transcript_parts[:3])
        return intake_agent.process_transcript(transcript_text=merged_transcript)

    @staticmethod
    def _serialize_stage(stage_result) -> dict[str, Any]:
        return {
            "agent_name": stage_result.agent_name,
            "success": stage_result.success,
            "warnings": stage_result.warnings,
            "error": stage_result.error,
            "trace": stage_result.trace,
        }

    @staticmethod
    def _build_retrieval_query(*, case: Case, objective: str) -> str:
        return (
            f"For case {case.id} ({case.title}), find the strongest evidence related to this objective: "
            f"{objective}"
        )

    @staticmethod
    def _format_reasoning_summary(reasoning_payload: dict[str, Any]) -> str:
        sections: list[str] = []

        overview = (reasoning_payload.get("overview") or "").strip()
        if overview:
            sections.append("Overview:")
            sections.append(overview)

        main_issues = reasoning_payload.get("main_issues") or []
        sections.append("")
        sections.append("Main Issues:")
        if main_issues:
            sections.extend(f"- {item}" for item in main_issues[:8])
        else:
            sections.append("- No major issues were clearly extracted.")

        key_dates = reasoning_payload.get("key_dates") or []
        sections.append("")
        sections.append("Key Dates:")
        if key_dates:
            sections.extend(
                f"- {item['label']}: {item['value']}"
                for item in key_dates[:10]
                if item.get("label") and item.get("value")
            )
        else:
            sections.append("- No major dates were clearly detected.")

        legal_risks = reasoning_payload.get("legal_risks") or []
        sections.append("")
        sections.append("Legal Risks:")
        if legal_risks:
            sections.extend(f"- {item}" for item in legal_risks[:8])
        else:
            sections.append("- No major legal risks were clearly detected.")

        next_steps = reasoning_payload.get("recommended_next_steps") or []
        sections.append("")
        sections.append("Recommended Next Steps:")
        if next_steps:
            sections.extend(f"- {item}" for item in next_steps[:8])
        else:
            sections.append("- Review the case evidence manually.")

        return "\n".join(sections).strip()

    @staticmethod
    def _format_sources(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [
            {
                "chunk_id": item.get("chunk_id"),
                "document_id": item.get("document_id"),
                "case_id": item.get("case_id"),
                "filename": item.get("filename"),
                "chunk_index": item.get("chunk_index"),
                "score": round(float(item.get("score", 0.0)), 4),
                "snippet": item.get("chunk_text", "")[:300],
            }
            for item in results
        ]

    @staticmethod
    def _get_case_or_404(db: Session, tenant_id: int, case_id: int) -> Case:
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
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Case not found."
            )
        return case

    @staticmethod
    def _get_case_documents(db: Session, tenant_id: int, case_id: int) -> list[Document]:
        return (
            db.query(Document)
            .filter(
                Document.case_id == case_id,
                Document.tenant_id == tenant_id,
            )
            .order_by(Document.upload_timestamp.asc(), Document.id.asc())
            .all()
        )

    @staticmethod
    def _get_case_consultation_requests(
        db: Session,
        tenant_id: int,
        case_id: int,
    ) -> list[ConsultationRequest]:
        return (
            db.query(ConsultationRequest)
            .filter(
                ConsultationRequest.case_id == case_id,
                ConsultationRequest.tenant_id == tenant_id,
            )
            .order_by(ConsultationRequest.created_at.desc(), ConsultationRequest.id.desc())
            .all()
        )

    @staticmethod
    def _get_case_voice_recordings(
        db: Session,
        tenant_id: int,
        case_id: int,
    ) -> list[VoiceRecording]:
        return (
            db.query(VoiceRecording)
            .filter(
                VoiceRecording.case_id == case_id,
                VoiceRecording.tenant_id == tenant_id,
            )
            .order_by(VoiceRecording.created_at.desc(), VoiceRecording.id.desc())
            .all()
        )

    @staticmethod
    def _ensure_document_summary(db: Session, document: Document) -> Document:
        if document.summary and document.summary.strip():
            return document

        if not (document.redacted_text or document.extracted_text):
            return document

        try:
            return summarization_service.summarize_document(db=db, document=document)
        except Exception:
            return document
