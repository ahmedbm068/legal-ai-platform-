from __future__ import annotations

import base64
from dataclasses import dataclass, field

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


class AuthenticityContract(BaseModel):
    risk_score: int = Field(default=0, ge=0, le=100)
    confidence: str = "low"
    signals: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    analysis_text: str = ""


@dataclass
class AuthenticityResult:
    risk_score: int
    confidence: str
    signals: list[str] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)
    analysis_text: str = ""
    provider: str = "unavailable"


class ImageAuthenticityService:
    @property
    def available(self) -> bool:
        return llm_gateway.vision_available

    @property
    def model(self) -> str:
        return llm_gateway.resolve_model("vision")

    def analyze(
        self,
        *,
        images: list[dict[str, object]],
        user_prompt: str,
    ) -> AuthenticityResult:
        limitations = [
            "This is best-effort visual screening, not forensic proof.",
            "Hidden edits, metadata tampering, or compression history may not be detectable from the visible image alone.",
        ]
        if not images:
            raise InvalidVisionInputError("No images were provided for authenticity analysis.")

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

        content = [
            {
                "type": "input_text",
                "text": (
                    "Assess whether these document images show visible signs of tampering, editing, or inconsistency. "
                    "Be conservative. This is risk screening only, not forensic proof. "
                    "Return JSON only with this exact schema: "
                    '{"risk_score":0,"confidence":"low","signals":["string"],"limitations":["string"],"analysis_text":"string"}. '
                    f"User request: {user_prompt.strip() or 'Check whether this looks authentic.'}"
                ),
            }
        ]
        for image in images:
            image_bytes = image.get("bytes")
            if not isinstance(image_bytes, (bytes, bytearray)):
                continue
            content.append(
                {
                    "type": "input_image",
                    "image_url": self._to_data_url(
                        image_bytes=bytes(image_bytes),
                        mime_type=str(image.get("mime_type") or "image/png"),
                    ),
                }
            )

        try:
            response = client.responses.create(
                model=self.model,
                input=[
                    {
                        "role": "system",
                        "content": [{"type": "input_text", "text": "You are a cautious visual authenticity screener."}],
                    },
                    {
                        "role": "user",
                        "content": content,
                    },
                ],
            )
        except VisionServiceError:
            raise
        except BadRequestError as exc:
            raise RemoteVisionProviderError(
                "The configured vision model rejected the authenticity request. Confirm that VISION_MODEL supports image input."
            ) from exc
        except Exception as exc:
            raise RemoteVisionProviderError(
                f"Visual authenticity screening failed: {exc}"
            ) from exc
        raw_text = llm_gateway.extract_output_text(response).strip()
        payload = validate_json_model(raw_text, AuthenticityContract)
        if payload is None:
            return AuthenticityResult(
                risk_score=35,
                confidence="low",
                signals=["The authenticity model returned an unstructured response."],
                limitations=limitations,
                analysis_text=raw_text or "The system could not produce a structured authenticity analysis.",
                provider=llm_gateway.vision_provider_name or llm_gateway.provider_name,
            )

        merged_limitations = list(limitations)
        for item in payload.limitations:
            cleaned = str(item).strip()
            if cleaned and cleaned not in merged_limitations:
                merged_limitations.append(cleaned)

        return AuthenticityResult(
            risk_score=int(payload.risk_score),
            confidence=str(payload.confidence or "low").strip() or "low",
            signals=[str(item).strip() for item in payload.signals if str(item).strip()],
            limitations=merged_limitations,
            analysis_text=str(payload.analysis_text or "").strip(),
            provider=llm_gateway.vision_provider_name or llm_gateway.provider_name,
        )

    @staticmethod
    def _to_data_url(*, image_bytes: bytes, mime_type: str) -> str:
        encoded = base64.b64encode(image_bytes).decode("ascii")
        safe_mime_type = (mime_type or "image/png").strip() or "image/png"
        return f"data:{safe_mime_type};base64,{encoded}"


image_authenticity_service = ImageAuthenticityService()
