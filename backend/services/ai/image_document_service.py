from __future__ import annotations

import base64
import json
import os
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from typing import Any

from fastapi import BackgroundTasks, HTTPException, status
from sqlalchemy.orm import Session

from backend.models.case import Case
from backend.models.case_image_asset import CaseImageAsset
from backend.models.document import Document
from backend.models.evidence_analysis_review import EvidenceAnalysisReview
from backend.models.image_document_batch import ImageDocumentBatch
from backend.services.ai.case_snapshot_service import case_snapshot_service
from backend.services.ai.image_authenticity_service import image_authenticity_service
from backend.services.ai.ocr_service import ocr_service
from backend.services.ai.vision_errors import VisionServiceError
from backend.services.jobs.job_queue_service import background_job_service
from backend.services.storage_service import download_file_to_temp, upload_file


class ImageDocumentService:
    ALLOWED_IMAGE_CONTENT_TYPES = {
        "image/png",
        "image/jpeg",
        "image/jpg",
        "image/webp",
        "image/heic",
        "image/heif",
    }
    ALLOWED_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".heic", ".heif"}

    def create_image_batch_upload(
        self,
        *,
        db: Session,
        case: Case,
        files: list[Any],
        title: str | None,
        generate_document: bool,
        run_authenticity_check: bool,
        created_by_user_id: int | None,
        background_tasks: BackgroundTasks | None = None,
    ) -> tuple[ImageDocumentBatch, dict[str, Any]]:
        if not files:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="At least one image is required.")

        batch = ImageDocumentBatch(
            tenant_id=case.tenant_id,
            case_id=case.id,
            created_by_user_id=created_by_user_id,
            title=(title or case.title or "Scanned document").strip(),
            status="queued",
            asset_count=len(files),
            generate_document=bool(generate_document),
            run_authenticity_check=bool(run_authenticity_check),
        )
        db.add(batch)
        db.commit()
        db.refresh(batch)

        for index, file in enumerate(files, start=1):
            filename = str(getattr(file, "filename", "") or "").strip()
            if not filename:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Every image file must have a filename.")
            self._validate_upload(filename=filename, content_type=getattr(file, "content_type", None))

            file.file.seek(0, 2)
            file_size = file.file.tell()
            file.file.seek(0)

            storage_path = upload_file(file.file, filename, prefix=f"case-images/case-{case.id}")
            db.add(
                CaseImageAsset(
                    tenant_id=case.tenant_id,
                    case_id=case.id,
                    batch_id=batch.id,
                    created_by_user_id=created_by_user_id,
                    filename=filename,
                    storage_path=storage_path,
                    mime_type=(getattr(file, "content_type", None) or self._guess_content_type(filename)).strip(),
                    file_size=file_size,
                    page_order=index,
                    source_scope="case_batch",
                    processing_status="queued",
                )
            )

        db.commit()
        job = background_job_service.enqueue(
            db=db,
            job_type="image_batch_process",
            payload={"batch_id": batch.id},
            tenant_id=batch.tenant_id,
            case_id=batch.case_id,
            queue_name="images",
            background_tasks=background_tasks,
        )
        db.refresh(batch)
        return batch, background_job_service.to_public_payload(job) or {}

    def save_prompt_attachments(
        self,
        *,
        db: Session,
        case: Case,
        attachments: list[dict[str, Any]],
        created_by_user_id: int | None,
        extracted_text: str | None = None,
        detected_language: str | None = None,
        ocr_confidence: float | None = None,
    ) -> list[CaseImageAsset]:
        created_assets: list[CaseImageAsset] = []
        for index, item in enumerate(attachments, start=1):
            name = str(item.get("name") or f"attachment-{index}.png").strip()
            mime_type = str(item.get("mime_type") or self._guess_content_type(name)).strip() or "image/png"
            image_bytes = self._attachment_to_bytes(item)
            if not image_bytes:
                continue
            storage_path = upload_file(BytesIO(image_bytes), name, prefix=f"copilot-images/case-{case.id}")
            asset = CaseImageAsset(
                tenant_id=case.tenant_id,
                case_id=case.id,
                created_by_user_id=created_by_user_id,
                filename=name,
                storage_path=storage_path,
                mime_type=mime_type,
                file_size=len(image_bytes),
                page_order=index,
                source_scope="copilot_attachment",
                processing_status="processed",
                extracted_text=extracted_text if index == 1 else None,
                detected_language=detected_language if index == 1 else None,
                ocr_confidence=ocr_confidence if index == 1 else None,
            )
            db.add(asset)
            created_assets.append(asset)

        if created_assets:
            db.commit()
            for asset in created_assets:
                db.refresh(asset)
        return created_assets

    def process_image_batch(
        self,
        *,
        db: Session,
        batch_id: int,
    ) -> dict[str, Any]:
        batch = db.query(ImageDocumentBatch).filter(ImageDocumentBatch.id == batch_id).first()
        if not batch:
            raise ValueError("Image batch not found.")

        assets = (
            db.query(CaseImageAsset)
            .filter(CaseImageAsset.batch_id == batch.id)
            .order_by(CaseImageAsset.page_order.asc(), CaseImageAsset.id.asc())
            .all()
        )
        if not assets:
            raise ValueError("Image batch has no assets.")

        batch.status = "processing"
        batch.processing_error = None
        db.commit()

        pages: list[dict[str, Any]] = []
        image_payloads: list[dict[str, Any]] = []
        processing_errors: list[str] = []
        downloaded_images: list[tuple[CaseImageAsset, bytes]] = []

        for asset in assets:
            asset.processing_status = "processing"
            asset.processing_error = None
            db.commit()

            temp_file_path = download_file_to_temp(asset.storage_path)
            try:
                with open(temp_file_path, "rb") as file_handle:
                    image_bytes = file_handle.read()
                downloaded_images.append((asset, image_bytes))
                image_payloads.append(
                    {
                        "asset_id": asset.id,
                        "name": asset.filename,
                        "mime_type": asset.mime_type,
                        "page_order": asset.page_order,
                        "bytes": image_bytes,
                    }
                )
            finally:
                try:
                    os.remove(temp_file_path)
                except OSError:
                    pass

        review = None
        review_error: str | None = None
        if batch.run_authenticity_check and image_payloads:
            try:
                review = self._create_authenticity_review(
                    db=db,
                    batch=batch,
                    images=image_payloads,
                    created_by_user_id=batch.created_by_user_id,
                )
            except VisionServiceError as exc:
                review_error = exc.user_message

        for asset, image_bytes in downloaded_images:
            try:
                ocr_result = ocr_service.extract_from_image_bytes(
                    image_bytes=image_bytes,
                    mime_type=asset.mime_type,
                    filename=asset.filename,
                )
                asset.processing_status = "processed"
                asset.processing_error = None
                asset.extracted_text = ocr_result.text or None
                asset.detected_language = ocr_result.detected_language
                asset.ocr_confidence = float(ocr_result.confidence or 0.0)
                asset.metadata_json = json.dumps(
                    {
                        "key_fields": ocr_result.key_fields,
                        "layout_notes": ocr_result.layout_notes,
                        "ocr_provider": ocr_result.provider,
                    },
                    ensure_ascii=False,
                )
                pages.append(
                    {
                        "asset_id": asset.id,
                        "page_order": asset.page_order,
                        "filename": asset.filename,
                        "language": asset.detected_language,
                        "ocr_confidence": asset.ocr_confidence,
                        "text": ocr_result.text.strip(),
                    }
                )
                db.commit()
            except Exception as exc:
                error_message = str(exc)
                processing_errors.append(error_message)
                asset.processing_status = "failed"
                asset.processing_error = error_message
                db.commit()

        generated_document = None
        if batch.generate_document and pages:
            generated_document = self._create_generated_document(
                db=db,
                batch=batch,
                pages=pages,
            )

        batch.ocr_provider = ocr_service.model if ocr_service.available else None
        if pages:
            batch.status = "completed"
            batch.processing_error = review_error
        elif processing_errors:
            batch.status = "failed"
            batch.processing_error = processing_errors[0]
        else:
            batch.status = "failed"
            batch.processing_error = review_error or "No text could be extracted from the uploaded images."
        batch.completed_at = datetime.now(timezone.utc)
        if generated_document is not None:
            batch.generated_document_id = generated_document.id
        db.commit()
        db.refresh(batch)

        if generated_document is None:
            case_snapshot_service.refresh_case_snapshot(db=db, tenant_id=batch.tenant_id, case_id=batch.case_id)

        return self.to_batch_detail_payload(db=db, batch=batch, review=review)

    def create_review_from_analysis(
        self,
        *,
        db: Session,
        case_id: int,
        tenant_id: int,
        asset_ids: list[int],
        created_by_user_id: int | None,
        analysis_payload: dict[str, Any],
    ) -> EvidenceAnalysisReview:
        signals = analysis_payload.get("signals") if isinstance(analysis_payload.get("signals"), list) else []
        limitations = analysis_payload.get("limitations") if isinstance(analysis_payload.get("limitations"), list) else []
        review = EvidenceAnalysisReview(
            tenant_id=tenant_id,
            case_id=case_id,
            image_asset_id=asset_ids[0] if len(asset_ids) == 1 else None,
            created_by_user_id=created_by_user_id,
            status="ready_for_review",
            risk_score=int(analysis_payload.get("risk_score") or 0),
            confidence=str(analysis_payload.get("confidence") or "low").strip() or "low",
            analysis_text=str(analysis_payload.get("analysis_text") or "").strip() or "Image authenticity analysis completed.",
            signals_json=json.dumps([str(item).strip() for item in signals if str(item).strip()], ensure_ascii=False),
            limitations_json=json.dumps([str(item).strip() for item in limitations if str(item).strip()], ensure_ascii=False),
            evidence_json=json.dumps({"asset_ids": asset_ids}, ensure_ascii=False),
        )
        db.add(review)
        db.commit()
        db.refresh(review)
        return review

    def apply_review_decision(
        self,
        *,
        db: Session,
        review: EvidenceAnalysisReview,
        decision: str,
        reviewed_by_user_id: int,
        note: str | None = None,
    ) -> EvidenceAnalysisReview:
        normalized = str(decision or "").strip().lower()
        if normalized not in {"approved", "rejected"}:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported review decision.")

        review.status = "approved" if normalized == "approved" else "rejected"
        review.review_decision = normalized
        review.reviewed_by_user_id = reviewed_by_user_id
        review.reviewed_at = datetime.now(timezone.utc)

        evidence = self._loads_json(review.evidence_json)
        if note:
            evidence["review_note"] = note.strip()
        review.evidence_json = json.dumps(evidence, ensure_ascii=False)
        db.commit()
        db.refresh(review)

        if normalized == "approved":
            case_snapshot_service.refresh_case_snapshot(db=db, tenant_id=review.tenant_id, case_id=review.case_id)
        return review

    def to_batch_detail_payload(
        self,
        *,
        db: Session,
        batch: ImageDocumentBatch,
        review: EvidenceAnalysisReview | None = None,
    ) -> dict[str, Any]:
        assets = (
            db.query(CaseImageAsset)
            .filter(CaseImageAsset.batch_id == batch.id)
            .order_by(CaseImageAsset.page_order.asc(), CaseImageAsset.id.asc())
            .all()
        )
        generated_document = None
        if batch.generated_document_id:
            generated_document = db.query(Document).filter(Document.id == batch.generated_document_id).first()
        if review is None:
            review = (
                db.query(EvidenceAnalysisReview)
                .filter(EvidenceAnalysisReview.image_batch_id == batch.id)
                .order_by(EvidenceAnalysisReview.created_at.desc(), EvidenceAnalysisReview.id.desc())
                .first()
            )
        return {
            "batch": batch,
            "assets": assets,
            "generated_document": generated_document,
            "review": self.to_review_public_payload(review),
        }

    def to_review_public_payload(self, review: EvidenceAnalysisReview | None) -> dict[str, Any] | None:
        if review is None:
            return None
        return {
            "id": review.id,
            "tenant_id": review.tenant_id,
            "case_id": review.case_id,
            "image_asset_id": review.image_asset_id,
            "image_batch_id": review.image_batch_id,
            "created_by_user_id": review.created_by_user_id,
            "reviewed_by_user_id": review.reviewed_by_user_id,
            "status": review.status,
            "review_decision": review.review_decision,
            "risk_score": int(review.risk_score or 0),
            "confidence": review.confidence,
            "analysis_text": review.analysis_text,
            "signals": self._loads_list(review.signals_json),
            "limitations": self._loads_list(review.limitations_json),
            "evidence": self._loads_json(review.evidence_json),
            "created_at": review.created_at,
            "updated_at": review.updated_at,
            "reviewed_at": review.reviewed_at,
        }

    def _create_generated_document(
        self,
        *,
        db: Session,
        batch: ImageDocumentBatch,
        pages: list[dict[str, Any]],
    ) -> Document:
        lines = [f"# OCR document for {batch.title}", ""]
        for page in pages:
            page_label = page.get("page_order") or "?"
            language = page.get("language") or "unknown"
            confidence = float(page.get("ocr_confidence") or 0.0)
            lines.extend(
                [
                    f"## Page {page_label} - {page.get('filename')}",
                    f"Language: {language}",
                    f"OCR confidence: {confidence:.2f}",
                    "",
                    str(page.get("text") or "").strip(),
                    "",
                ]
            )

        filename = f"{self._safe_stem(batch.title)}_ocr.md"
        storage_path = upload_file(
            BytesIO("\n".join(lines).encode("utf-8")),
            filename,
            prefix=f"documents/case-{batch.case_id}/ocr",
        )
        document = Document(
            filename=filename,
            storage_path=storage_path,
            processing_status="queued",
            file_size=len("\n".join(lines).encode("utf-8")),
            file_type="text/markdown",
            case_id=batch.case_id,
            tenant_id=batch.tenant_id,
            source_image_batch_id=batch.id,
        )
        db.add(document)
        db.commit()
        db.refresh(document)

        background_job_service.enqueue(
            db=db,
            job_type="document_process",
            payload={"document_id": document.id},
            tenant_id=document.tenant_id,
            case_id=document.case_id,
            document_id=document.id,
            queue_name="documents",
        )
        return document

    def _create_authenticity_review(
        self,
        *,
        db: Session,
        batch: ImageDocumentBatch,
        images: list[dict[str, Any]],
        created_by_user_id: int | None,
    ) -> EvidenceAnalysisReview:
        result = image_authenticity_service.analyze(
            images=images,
            user_prompt=f"Check whether the scanned document batch '{batch.title}' looks modified or authentic.",
        )
        review = EvidenceAnalysisReview(
            tenant_id=batch.tenant_id,
            case_id=batch.case_id,
            image_batch_id=batch.id,
            created_by_user_id=created_by_user_id,
            status="ready_for_review",
            risk_score=result.risk_score,
            confidence=result.confidence,
            analysis_text=result.analysis_text,
            signals_json=json.dumps(result.signals, ensure_ascii=False),
            limitations_json=json.dumps(result.limitations, ensure_ascii=False),
            evidence_json=json.dumps({"asset_ids": [int(item["asset_id"]) for item in images if item.get("asset_id")]}, ensure_ascii=False),
        )
        db.add(review)
        db.commit()
        db.refresh(review)
        return review

    def _attachment_to_bytes(self, attachment: dict[str, Any]) -> bytes:
        raw_bytes = attachment.get("bytes")
        if isinstance(raw_bytes, (bytes, bytearray)):
            return bytes(raw_bytes)

        data_url = str(attachment.get("data_url") or "").strip()
        if not data_url:
            return b""
        if "," in data_url:
            _, encoded = data_url.split(",", 1)
        else:
            encoded = data_url
        return base64.b64decode(encoded)

    def _validate_upload(self, *, filename: str, content_type: str | None) -> None:
        normalized_type = (content_type or "").split(";")[0].strip().lower()
        extension = Path(filename).suffix.lower()
        if normalized_type in self.ALLOWED_IMAGE_CONTENT_TYPES or extension in self.ALLOWED_IMAGE_EXTENSIONS:
            return
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unsupported image format. Use PNG, JPG, JPEG, WEBP, or HEIC.",
        )

    @staticmethod
    def _guess_content_type(filename: str) -> str:
        extension = Path(filename).suffix.lower()
        return {
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".webp": "image/webp",
            ".heic": "image/heic",
            ".heif": "image/heif",
        }.get(extension, "image/png")

    @staticmethod
    def _safe_stem(value: str) -> str:
        stem = "".join(ch if ch.isalnum() or ch in {"_", "-"} else "_" for ch in (value or "scanned_document"))
        stem = stem.strip("_") or "scanned_document"
        return stem[:80]

    @staticmethod
    def _loads_list(raw_value: str | None) -> list[str]:
        try:
            payload = json.loads(raw_value or "[]")
            if not isinstance(payload, list):
                return []
            return [str(item).strip() for item in payload if str(item).strip()]
        except Exception:
            return []

    @staticmethod
    def _loads_json(raw_value: str | None) -> dict[str, Any]:
        try:
            payload = json.loads(raw_value or "{}")
            return payload if isinstance(payload, dict) else {}
        except Exception:
            return {}


image_document_service = ImageDocumentService()

