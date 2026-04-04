from __future__ import annotations

import base64
import re
from typing import Any

from pydantic import BaseModel, Field

from backend.services.ai.agent_contracts import validate_json_model
from backend.services.ai.agents.base_agent import BaseAgent, AgentResult
from backend.services.ai.image_authenticity_service import image_authenticity_service
from backend.services.ai.llm_gateway import llm_gateway
from backend.services.ai.ocr_service import ocr_service
from backend.services.ai.vision_errors import VisionServiceError


class VisionField(BaseModel):
    label: str
    value: str


class VisionCitation(BaseModel):
    label: str
    asset_id: int | None = None
    page_order: int | None = None
    snippet: str = ""


class VisionAuthenticityPayload(BaseModel):
    risk_score: int = Field(default=0, ge=0, le=100)
    confidence: str = "low"
    signals: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    analysis_text: str = ""


class VisionAnalysisPayload(BaseModel):
    task_kind: str = "ocr_extract"
    summary: str = ""
    answer: str = ""
    extracted_text: str = ""
    detected_language: str | None = None
    confidence: str = "medium"
    fields: list[VisionField] = Field(default_factory=list)
    citations: list[VisionCitation] = Field(default_factory=list)
    authenticity_review: VisionAuthenticityPayload | None = None


class VisionAnalysisAgent(BaseAgent):
    agent_name = "vision_analysis_agent"
    AUTHENTICITY_PATTERN = re.compile(
        r"\b(real|fake|modified|tamper|tampered|photoshop|photoshopped|forged|forgery|edited|authentic)\b",
        re.IGNORECASE,
    )
    FIELD_PATTERN = re.compile(
        r"\b(date|name|number|stamp|signature|id|passport|article|amount|who|when|where|extract|read)\b",
        re.IGNORECASE,
    )

    def __init__(self) -> None:
        self.client = None
        self.model = ""

    def analyze(
        self,
        *,
        message: str,
        attachments: list[dict[str, Any]],
    ) -> AgentResult:
        if not attachments:
            return self.result(success=False, error="No image attachments were provided.", trace=["Image analysis skipped."])

        trace = [f"Received {len(attachments)} image attachment(s) for multimodal analysis."]
        task_kind = self._detect_task(message)
        trace.append(f"Detected vision task '{task_kind}'.")
        if not llm_gateway.vision_available:
            reason = llm_gateway.vision_reason_unavailable or "Vision/OCR provider is not configured."
            trace.append(reason)
            return self.result(success=False, error=reason, trace=trace)

        ocr_pages: list[dict[str, Any]] = []
        combined_text_parts: list[str] = []
        key_fields: list[dict[str, str]] = []
        detected_language: str | None = None

        for index, item in enumerate(attachments, start=1):
            raw_bytes = item.get("bytes")
            if not isinstance(raw_bytes, (bytes, bytearray)):
                continue
            try:
                ocr_result = ocr_service.extract_from_image_bytes(
                    image_bytes=bytes(raw_bytes),
                    mime_type=str(item.get("mime_type") or "image/png"),
                    filename=str(item.get("name") or f"image-{index}.png"),
                    instruction="Focus on legal-document text, dates, signatures, stamps, and identifiers.",
                )
            except VisionServiceError as exc:
                trace.append(exc.user_message)
                return self.result(success=False, error=exc.user_message, trace=trace)
            page_text = ocr_result.text.strip()
            if page_text:
                combined_text_parts.append(f"Page {index}: {page_text}")
            if ocr_result.detected_language and not detected_language:
                detected_language = ocr_result.detected_language
            for field in ocr_result.key_fields:
                if field not in key_fields:
                    key_fields.append(field)
            ocr_pages.append(
                {
                    "label": str(item.get("name") or f"Image {index}"),
                    "asset_id": item.get("asset_id"),
                    "page_order": item.get("page_order") or index,
                    "snippet": page_text[:220],
                    "ocr_confidence": ocr_result.confidence,
                }
            )

        if not ocr_pages:
            trace.append("No valid image payloads were available for OCR.")
            return self.result(success=False, error="No valid image data was provided.", trace=trace)

        combined_text = "\n\n".join(part for part in combined_text_parts if part.strip()).strip()
        trace.append(f"OCR produced {len(combined_text)} characters of extracted text.")

        authenticity_payload: dict[str, Any] | None = None
        if task_kind == "tamper_review":
            try:
                auth_result = image_authenticity_service.analyze(images=attachments, user_prompt=message)
            except VisionServiceError as exc:
                trace.append(exc.user_message)
                return self.result(success=False, error=exc.user_message, trace=trace)
            authenticity_payload = {
                "risk_score": auth_result.risk_score,
                "confidence": auth_result.confidence,
                "signals": auth_result.signals,
                "limitations": auth_result.limitations,
                "analysis_text": auth_result.analysis_text,
            }
            trace.append("Completed authenticity screening for image attachments.")

        answer_payload = self._generate_answer(
            message=message,
            attachments=attachments,
            task_kind=task_kind,
            extracted_text=combined_text,
            key_fields=key_fields,
            citations=ocr_pages,
            authenticity_payload=authenticity_payload,
        )
        if answer_payload is None:
            answer_payload = VisionAnalysisPayload(
                task_kind=task_kind,
                summary="Image analysis completed with OCR-first fallback.",
                answer=self._fallback_answer(
                    task_kind=task_kind,
                    extracted_text=combined_text,
                    authenticity_payload=authenticity_payload,
                ),
                extracted_text=combined_text,
                detected_language=detected_language,
                confidence="medium" if combined_text else "low",
                fields=[VisionField(**field) for field in key_fields[:8] if field.get("label") and field.get("value")],
                citations=[VisionCitation(**item) for item in ocr_pages[:8]],
                authenticity_review=(
                    VisionAuthenticityPayload(**authenticity_payload) if isinstance(authenticity_payload, dict) else None
                ),
            )
            trace.append("Used OCR-first fallback answer because structured vision generation was unavailable.")
        else:
            trace.append("Generated structured multimodal answer with the vision model.")

        return self.result(
            success=True,
            payload=answer_payload.model_dump(),
            trace=trace,
        )

    def _generate_answer(
        self,
        *,
        message: str,
        attachments: list[dict[str, Any]],
        task_kind: str,
        extracted_text: str,
        key_fields: list[dict[str, str]],
        citations: list[dict[str, Any]],
        authenticity_payload: dict[str, Any] | None,
    ) -> VisionAnalysisPayload | None:
        client = llm_gateway.create_client("vision")
        if not client:
            return None

        content: list[dict[str, Any]] = [
            {
                "type": "input_text",
                "text": (
                    "You are a legal AI vision agent. Answer the user's question using the supplied document images "
                    "and OCR text. Stay factual and cautious. Return JSON only with this exact schema: "
                    '{"task_kind":"string","summary":"string","answer":"string","extracted_text":"string","detected_language":"string|null","confidence":"low|medium|high","fields":[{"label":"string","value":"string"}],"citations":[{"label":"string","asset_id":0,"page_order":1,"snippet":"string"}],"authenticity_review":{"risk_score":0,"confidence":"low","signals":["string"],"limitations":["string"],"analysis_text":"string"}|null}. '
                    f"Detected task: {task_kind}. User request: {message.strip() or 'Analyze this document image.'}\n\n"
                    f"OCR text:\n{extracted_text[:12000]}\n\n"
                    f"Detected fields: {key_fields[:12]}\n\n"
                    f"Citations: {citations[:8]}\n\n"
                    f"Authenticity payload: {authenticity_payload}"
                ),
            }
        ]
        for item in attachments[:4]:
            raw_bytes = item.get("bytes")
            if not isinstance(raw_bytes, (bytes, bytearray)):
                continue
            content.append(
                {
                    "type": "input_image",
                    "image_url": self._to_data_url(
                        image_bytes=bytes(raw_bytes),
                        mime_type=str(item.get("mime_type") or "image/png"),
                    ),
                }
            )

        try:
            response = client.responses.create(
                model=llm_gateway.resolve_model("vision"),
                input=[
                    {
                        "role": "system",
                        "content": [{"type": "input_text", "text": "You are a schema-strict legal document vision assistant."}],
                    },
                    {
                        "role": "user",
                        "content": content,
                    },
                ],
            )
        except Exception:
            return None
        raw_text = llm_gateway.extract_output_text(response).strip()
        return validate_json_model(raw_text, VisionAnalysisPayload)

    def _fallback_answer(
        self,
        *,
        task_kind: str,
        extracted_text: str,
        authenticity_payload: dict[str, Any] | None,
    ) -> str:
        if task_kind == "tamper_review" and authenticity_payload:
            return str(authenticity_payload.get("analysis_text") or "Best-effort authenticity screening completed.")
        if extracted_text:
            return extracted_text[:2400]
        return "No readable text could be extracted from the provided image attachments."

    def _detect_task(self, message: str) -> str:
        normalized = str(message or "").strip().lower()
        if self.AUTHENTICITY_PATTERN.search(normalized):
            return "tamper_review"
        if self.FIELD_PATTERN.search(normalized):
            return "field_extraction"
        if normalized:
            return "general_vision_qa"
        return "ocr_extract"

    @staticmethod
    def _to_data_url(*, image_bytes: bytes, mime_type: str) -> str:
        encoded = base64.b64encode(image_bytes).decode("ascii")
        safe_mime_type = (mime_type or "image/png").strip() or "image/png"
        return f"data:{safe_mime_type};base64,{encoded}"


vision_analysis_agent = VisionAnalysisAgent()
