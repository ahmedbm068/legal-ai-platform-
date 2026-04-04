from __future__ import annotations

import base64
from dataclasses import dataclass, field
from typing import Any

from openai import BadRequestError
from pydantic import BaseModel, Field

from backend.services.ai.agent_contracts import validate_json_model
from backend.services.ai.llm_gateway import llm_gateway
from backend.services.ai.vision_errors import (
    InvalidVisionInputError,
    RemoteVisionProviderError,
    UnsupportedMultimodalProviderError,
    VisionProviderUnavailableError,
    VisionServiceError,
)


class OCRField(BaseModel):
    label: str
    value: str


class OCRContract(BaseModel):
    text: str = ""
    detected_language: str | None = None
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    key_fields: list[OCRField] = Field(default_factory=list)
    layout_notes: list[str] = Field(default_factory=list)


@dataclass
class OCRResult:
    text: str
    detected_language: str | None = None
    confidence: float = 0.0
    key_fields: list[dict[str, str]] = field(default_factory=list)
    layout_notes: list[str] = field(default_factory=list)
    provider: str = "unavailable"
    raw_response: str | None = None


class OCRService:
    @property
    def available(self) -> bool:
        return llm_gateway.vision_available

    @property
    def model(self) -> str:
        return llm_gateway.resolve_model("vision")

    def extract_from_image_bytes(
        self,
        *,
        image_bytes: bytes,
        mime_type: str,
        filename: str,
        instruction: str | None = None,
    ) -> OCRResult:
        if not image_bytes:
            raise InvalidVisionInputError("No image bytes were provided for OCR.")

        client = llm_gateway.create_client("vision")
        if not client:
            raise VisionProviderUnavailableError(
                llm_gateway.vision_reason_unavailable or "Vision/OCR provider is not configured."
            )
        if not llm_gateway.supports_multimodal_input("vision"):
            raise UnsupportedMultimodalProviderError(
                llm_gateway.vision_reason_unavailable
                or "The configured provider does not support multimodal image analysis."
            )

        prompt_text = (
            "Read this document image carefully. Perform multilingual OCR for Arabic, English, and German. "
            "Preserve names, dates, numbers, article references, stamps, and handwritten-looking fields when readable. "
            "If a character or word is uncertain, keep the closest readable text and mention the uncertainty in layout_notes. "
            "Return JSON only with this exact schema: "
            '{"text":"string","detected_language":"string|null","confidence":0.0,"key_fields":[{"label":"string","value":"string"}],"layout_notes":["string"]}.'
        )
        if instruction:
            prompt_text = f"{prompt_text}\nAdditional instruction: {instruction.strip()}"

        data_url = self._to_data_url(image_bytes=image_bytes, mime_type=mime_type)
        try:
            response = client.responses.create(
                model=self.model,
                input=[
                    {
                        "role": "system",
                        "content": [{"type": "input_text", "text": "You are a legal document OCR engine."}],
                    },
                    {
                        "role": "user",
                        "content": [
                            {"type": "input_text", "text": prompt_text},
                            {"type": "input_image", "image_url": data_url},
                        ],
                    },
                ],
            )
        except VisionServiceError:
            raise
        except BadRequestError as exc:
            raise RemoteVisionProviderError(
                "The configured vision model rejected the OCR request. Confirm that VISION_MODEL supports image input."
            ) from exc
        except Exception as exc:
            raise RemoteVisionProviderError(
                f"Vision/OCR request failed for '{filename}': {exc}"
            ) from exc
        raw_text = llm_gateway.extract_output_text(response).strip()
        payload = validate_json_model(raw_text, OCRContract)
        if payload is None:
            return OCRResult(
                text=raw_text,
                confidence=0.25 if raw_text else 0.0,
                provider=llm_gateway.vision_provider_name or llm_gateway.provider_name,
                raw_response=raw_text or f"OCR response for {filename} could not be validated.",
            )

        return OCRResult(
            text=payload.text.strip(),
            detected_language=(payload.detected_language or "").strip() or None,
            confidence=float(payload.confidence or 0.0),
            key_fields=[item.model_dump() for item in payload.key_fields],
            layout_notes=[str(item).strip() for item in payload.layout_notes if str(item).strip()],
            provider=llm_gateway.vision_provider_name or llm_gateway.provider_name,
            raw_response=raw_text,
        )

    @staticmethod
    def _to_data_url(*, image_bytes: bytes, mime_type: str) -> str:
        encoded = base64.b64encode(image_bytes).decode("ascii")
        safe_mime_type = (mime_type or "image/png").strip() or "image/png"
        return f"data:{safe_mime_type};base64,{encoded}"


ocr_service = OCRService()
