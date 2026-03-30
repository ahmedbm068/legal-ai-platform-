from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Literal

from fastapi import HTTPException, status
from sqlalchemy import and_, func
from sqlalchemy.orm import Session

from backend.models.case import Case
from backend.models.document import Document
from backend.models.generated_artifact_version import GeneratedArtifactVersion
from backend.services.ai.llm_gateway import llm_gateway


ArtifactType = Literal["document_summary", "case_email"]
SourceKind = Literal["agent_generation", "manual_edit", "agent_revision", "system_seed"]


class ArtifactVersioningService:
    VALID_TYPES = {"document_summary", "case_email"}

    def __init__(self) -> None:
        self.client = llm_gateway.create_client()
        self.model = llm_gateway.default_model

    def _validate_scope(
        self,
        *,
        db: Session,
        tenant_id: int,
        artifact_type: str,
        case_id: int | None,
        document_id: int | None,
    ) -> tuple[int | None, int | None]:
        if artifact_type not in self.VALID_TYPES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unsupported artifact_type '{artifact_type}'.",
            )

        if artifact_type == "document_summary":
            if document_id is None:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="document_id is required for document_summary artifacts.",
                )
            document = (
                db.query(Document)
                .filter(Document.id == document_id, Document.tenant_id == tenant_id)
                .first()
            )
            if not document:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found.")
            return document.case_id, document.id

        if case_id is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="case_id is required for case_email artifacts.",
            )

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
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case not found.")

        return case.id, None

    @staticmethod
    def _scope_filter(
        *,
        tenant_id: int,
        artifact_type: str,
        case_id: int | None,
        document_id: int | None,
    ):
        return and_(
            GeneratedArtifactVersion.tenant_id == tenant_id,
            GeneratedArtifactVersion.artifact_type == artifact_type,
            GeneratedArtifactVersion.case_id == case_id,
            GeneratedArtifactVersion.document_id == document_id,
        )

    def create_version(
        self,
        *,
        db: Session,
        tenant_id: int,
        artifact_type: ArtifactType,
        content: str,
        case_id: int | None = None,
        document_id: int | None = None,
        source_kind: SourceKind = "agent_generation",
        edit_instruction: str | None = None,
        parent_version_id: int | None = None,
        created_by_user_id: int | None = None,
        metadata: dict[str, Any] | None = None,
        auto_select: bool = True,
    ) -> GeneratedArtifactVersion:
        normalized_content = (content or "").strip()
        if not normalized_content:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Version content cannot be empty.",
            )

        resolved_case_id, resolved_document_id = self._validate_scope(
            db=db,
            tenant_id=tenant_id,
            artifact_type=artifact_type,
            case_id=case_id,
            document_id=document_id,
        )

        scope_filter = self._scope_filter(
            tenant_id=tenant_id,
            artifact_type=artifact_type,
            case_id=resolved_case_id,
            document_id=resolved_document_id,
        )

        latest_number = (
            db.query(func.max(GeneratedArtifactVersion.version_number))
            .filter(scope_filter)
            .scalar()
        ) or 0
        next_number = int(latest_number) + 1

        if auto_select:
            (
                db.query(GeneratedArtifactVersion)
                .filter(scope_filter)
                .update({GeneratedArtifactVersion.is_selected: False}, synchronize_session=False)
            )

        row = GeneratedArtifactVersion(
            tenant_id=tenant_id,
            case_id=resolved_case_id,
            document_id=resolved_document_id,
            artifact_type=artifact_type,
            version_number=next_number,
            content=normalized_content,
            source_kind=source_kind,
            edit_instruction=(edit_instruction or None),
            metadata_json=json.dumps(metadata or {}, ensure_ascii=False),
            is_selected=auto_select,
            parent_version_id=parent_version_id,
            created_by_user_id=created_by_user_id,
        )
        db.add(row)
        db.commit()
        db.refresh(row)

        if row.is_selected:
            self._apply_selected_to_primary_records(db=db, version=row)
            db.refresh(row)

        return row

    def list_versions(
        self,
        *,
        db: Session,
        tenant_id: int,
        artifact_type: ArtifactType,
        case_id: int | None = None,
        document_id: int | None = None,
    ) -> list[GeneratedArtifactVersion]:
        resolved_case_id, resolved_document_id = self._validate_scope(
            db=db,
            tenant_id=tenant_id,
            artifact_type=artifact_type,
            case_id=case_id,
            document_id=document_id,
        )

        return (
            db.query(GeneratedArtifactVersion)
            .filter(
                self._scope_filter(
                    tenant_id=tenant_id,
                    artifact_type=artifact_type,
                    case_id=resolved_case_id,
                    document_id=resolved_document_id,
                )
            )
            .order_by(GeneratedArtifactVersion.version_number.asc(), GeneratedArtifactVersion.id.asc())
            .all()
        )

    def select_version(
        self,
        *,
        db: Session,
        tenant_id: int,
        version_id: int,
    ) -> GeneratedArtifactVersion:
        target = (
            db.query(GeneratedArtifactVersion)
            .filter(
                GeneratedArtifactVersion.id == version_id,
                GeneratedArtifactVersion.tenant_id == tenant_id,
            )
            .first()
        )
        if not target:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Version not found.")

        scope_filter = self._scope_filter(
            tenant_id=tenant_id,
            artifact_type=target.artifact_type,
            case_id=target.case_id,
            document_id=target.document_id,
        )
        (
            db.query(GeneratedArtifactVersion)
            .filter(scope_filter)
            .update({GeneratedArtifactVersion.is_selected: False}, synchronize_session=False)
        )
        target.is_selected = True
        db.commit()
        db.refresh(target)

        self._apply_selected_to_primary_records(db=db, version=target)
        db.refresh(target)
        return target

    def revise_with_agent(
        self,
        *,
        artifact_type: ArtifactType,
        current_content: str,
        instruction: str,
        jurisdiction_country: str | None = None,
    ) -> str:
        base_text = (current_content or "").strip()
        edit_instruction = (instruction or "").strip()
        if not base_text:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Base content is empty.")
        if not edit_instruction:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Revision instruction is empty.")

        if not self.client:
            return f"{base_text}\n\n[Revision request applied as note]: {edit_instruction}"

        artifact_label = "client email" if artifact_type == "case_email" else "document summary"
        country_line = f"Jurisdiction context: {jurisdiction_country}.\n" if jurisdiction_country else ""
        prompt = f"""
You are a legal writing revision assistant.
Revise the provided {artifact_label} according to the instruction.

Rules:
- Keep original meaning and evidence-grounded details.
- Apply instruction precisely.
- Keep professional legal tone.
- Return only the revised full text.

{country_line}
Instruction:
{edit_instruction}

Current text:
{base_text}
"""
        try:
            response = self.client.responses.create(model=self.model, input=prompt)
            revised = llm_gateway.extract_output_text(response).strip()
            return revised or base_text
        except Exception:
            return base_text

    def ensure_seed_version_for_document_summary(
        self,
        *,
        db: Session,
        tenant_id: int,
        document: Document,
    ) -> GeneratedArtifactVersion | None:
        summary_text = (document.summary or "").strip()
        if not summary_text:
            return None

        existing = (
            db.query(GeneratedArtifactVersion)
            .filter(
                GeneratedArtifactVersion.tenant_id == tenant_id,
                GeneratedArtifactVersion.artifact_type == "document_summary",
                GeneratedArtifactVersion.document_id == document.id,
            )
            .first()
        )
        if existing:
            return existing

        return self.create_version(
            db=db,
            tenant_id=tenant_id,
            artifact_type="document_summary",
            content=summary_text,
            case_id=document.case_id,
            document_id=document.id,
            source_kind="system_seed",
            metadata={
                "summary_short": document.summary_short,
                "summary_source": document.summary_source,
                "summary_version": document.summary_version,
            },
            auto_select=True,
        )

    def _apply_selected_to_primary_records(self, *, db: Session, version: GeneratedArtifactVersion) -> None:
        if version.artifact_type != "document_summary" or version.document_id is None:
            return

        document = (
            db.query(Document)
            .filter(
                Document.id == version.document_id,
                Document.tenant_id == version.tenant_id,
            )
            .first()
        )
        if not document:
            return

        content = (version.content or "").strip()
        if not content:
            return

        document.summary = content
        document.summary_short = content[:500] + ("..." if len(content) > 500 else "")
        document.summary_status = "completed"
        document.summary_error = None
        document.summary_generated_at = datetime.now(timezone.utc)
        db.commit()

    @staticmethod
    def to_public_payload(row: GeneratedArtifactVersion) -> dict[str, Any]:
        metadata: dict[str, Any] = {}
        if row.metadata_json:
            try:
                parsed = json.loads(row.metadata_json)
                if isinstance(parsed, dict):
                    metadata = parsed
            except json.JSONDecodeError:
                metadata = {}

        return {
            "id": row.id,
            "tenant_id": row.tenant_id,
            "case_id": row.case_id,
            "document_id": row.document_id,
            "artifact_type": row.artifact_type,
            "version_number": row.version_number,
            "content": row.content,
            "source_kind": row.source_kind,
            "edit_instruction": row.edit_instruction,
            "metadata": metadata,
            "is_selected": row.is_selected,
            "parent_version_id": row.parent_version_id,
            "created_by_user_id": row.created_by_user_id,
            "created_at": row.created_at,
        }


artifact_versioning_service = ArtifactVersioningService()

