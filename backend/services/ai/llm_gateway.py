from __future__ import annotations

from dataclasses import dataclass, field
import logging
from types import SimpleNamespace
from typing import Any, Optional

from openai import OpenAI

from backend.core.config import settings
from backend.services.ai.vision_errors import (
    RemoteVisionProviderError,
    UnsupportedMultimodalProviderError,
    VisionProviderUnavailableError,
)

logger = logging.getLogger(__name__)


def _normalized_base_url(value: str | None) -> str | None:
    normalized = (value or "").strip().rstrip("/")
    return normalized or None


@dataclass(frozen=True)
class ProviderProfile:
    api_key: str | None
    base_url: str | None
    provider_name: str
    supports_text_chat: bool
    supports_responses_api: bool
    supports_multimodal_input: bool
    default_headers: dict[str, str] = field(default_factory=dict)
    reason_unavailable: str | None = None

    @property
    def available(self) -> bool:
        return bool(self.api_key)


def _provider_name_from(*, api_key: str | None, base_url: str | None) -> str:
    base = (base_url or "").lower()
    if "groq.com" in base or (api_key or "").startswith("gsk_"):
        return "groq"
    if "openrouter.ai" in base:
        return "openrouter"
    if base:
        return "openai-compatible"
    return "openai"


def _provider_capabilities(provider_name: str) -> tuple[bool, bool, bool]:
    normalized = (provider_name or "").strip().lower()
    if normalized == "groq":
        return True, False, False
    if normalized == "openrouter":
        return True, False, False
    if normalized in {"openai", "openai-compatible"}:
        return True, True, True
    return True, False, False


def _content_contains_image(content: Any) -> bool:
    if isinstance(content, list):
        return any(_content_contains_image(item) for item in content)

    if isinstance(content, dict):
        block_type = str(content.get("type") or "").strip().lower()
        if block_type in {"input_image", "image_url"}:
            return True
        nested_content = content.get("content")
        if nested_content is not None and _content_contains_image(nested_content):
            return True

    return False


def _payload_contains_image_input(input_payload: Any) -> bool:
    if isinstance(input_payload, list):
        return any(_payload_contains_image_input(item) for item in input_payload)

    if isinstance(input_payload, dict):
        block_type = str(input_payload.get("type") or "").strip().lower()
        if block_type in {"input_image", "image_url"}:
            return True
        content = input_payload.get("content")
        if content is not None and _content_contains_image(content):
            return True

    return False


def _extract_text_from_message_content(content: Any) -> str:
    if isinstance(content, str):
        return content.strip()

    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                cleaned = item.strip()
                if cleaned:
                    parts.append(cleaned)
                continue

            if isinstance(item, dict):
                candidate = (
                    item.get("text")
                    or item.get("content")
                    or item.get("output_text")
                    or item.get("value")
                )
                if isinstance(candidate, str) and candidate.strip():
                    parts.append(candidate.strip())
                    continue

                nested_content = item.get("content")
                if isinstance(nested_content, list):
                    nested = _extract_text_from_message_content(nested_content)
                    if nested:
                        parts.append(nested)

        return "\n".join(parts).strip()

    return ""


def _normalize_chat_content_block(block: Any) -> dict[str, Any] | None:
    if isinstance(block, str):
        cleaned = block.strip()
        if cleaned:
            return {"type": "text", "text": cleaned}
        return None

    if not isinstance(block, dict):
        return None

    block_type = str(block.get("type") or "").strip().lower()
    if block_type in {"input_text", "text"}:
        text_value = str(block.get("text") or block.get("value") or "").strip()
        if text_value:
            return {"type": "text", "text": text_value}
        return None

    if block_type in {"input_image", "image_url"}:
        image_url = block.get("image_url") or block.get("url")
        detail = block.get("detail")
        if isinstance(image_url, dict):
            url_value = str(image_url.get("url") or "").strip()
            detail = image_url.get("detail") or detail
        else:
            url_value = str(image_url or "").strip()

        if not url_value:
            return None

        payload: dict[str, Any] = {
            "type": "image_url",
            "image_url": {"url": url_value},
        }
        if detail:
            payload["image_url"]["detail"] = detail
        return payload

    candidate_text = _extract_text_from_message_content(block)
    if candidate_text:
        return {"type": "text", "text": candidate_text}
    return None


def _normalize_chat_message_content(content: Any) -> str | list[dict[str, Any]]:
    if isinstance(content, str):
        return content.strip()

    if isinstance(content, list):
        normalized_blocks: list[dict[str, Any]] = []
        for item in content:
            normalized = _normalize_chat_content_block(item)
            if normalized:
                normalized_blocks.append(normalized)

        if normalized_blocks and all(block.get("type") == "text" for block in normalized_blocks):
            return "\n\n".join(
                str(block.get("text") or "").strip()
                for block in normalized_blocks
                if str(block.get("text") or "").strip()
            ).strip()
        return normalized_blocks

    if isinstance(content, dict):
        normalized = _normalize_chat_content_block(content)
        if not normalized:
            return ""
        if normalized["type"] == "text":
            return str(normalized.get("text") or "").strip()
        return [normalized]

    return _extract_text_from_message_content(content)


def _coerce_responses_input_to_messages(input_payload: Any) -> list[dict[str, Any]]:
    if isinstance(input_payload, str):
        cleaned = input_payload.strip()
        return [{"role": "user", "content": cleaned}] if cleaned else []

    if isinstance(input_payload, list):
        messages: list[dict[str, Any]] = []
        for item in input_payload:
            if isinstance(item, str):
                cleaned = item.strip()
                if cleaned:
                    messages.append({"role": "user", "content": cleaned})
                continue

            if not isinstance(item, dict):
                continue

            role = str(item.get("role") or "user").strip() or "user"
            content = item.get("content")
            if content is None and item.get("type") == "input_text":
                content = item.get("text")

            normalized_content = _normalize_chat_message_content(content)
            if (not normalized_content) and isinstance(item.get("text"), str):
                normalized_content = item["text"].strip()

            if normalized_content:
                messages.append({"role": role, "content": normalized_content})

        return messages

    if isinstance(input_payload, dict):
        role = str(input_payload.get("role") or "user").strip() or "user"
        content = _normalize_chat_message_content(input_payload.get("content") or input_payload.get("text"))
        if content:
            return [{"role": role, "content": content}]

    text_payload = str(input_payload or "").strip()
    return [{"role": "user", "content": text_payload}] if text_payload else []


class _ResponsesCompat:
    def __init__(self, *, raw_client: OpenAI, gateway: "LLMGateway", provider: ProviderProfile) -> None:
        self._raw_client = raw_client
        self._gateway = gateway
        self._provider = provider

    def create(self, *, model: str, input: Any, **kwargs):
        contains_image_input = _payload_contains_image_input(input)
        native_responses_error: Exception | None = None

        if contains_image_input and not self._provider.supports_multimodal_input:
            raise UnsupportedMultimodalProviderError(
                f"The configured vision provider '{self._provider.provider_name}' does not support image inputs."
            )

        if self._provider.supports_responses_api:
            native_responses = getattr(self._raw_client, "responses", None)
            if native_responses and hasattr(native_responses, "create"):
                try:
                    raw_response = native_responses.create(model=model, input=input, **kwargs)
                    return SimpleNamespace(
                        output_text=self._gateway.extract_output_text(raw_response),
                        raw_response=raw_response,
                    )
                except Exception as exc:
                    native_responses_error = exc
                    if contains_image_input:
                        logger.info(
                            "Native responses.create failed for provider '%s'; trying multimodal chat fallback: %s",
                            self._provider.provider_name,
                            exc,
                        )
                    else:
                        logger.debug("Native responses.create failed; trying chat-completions fallback: %s", exc)

        chat_api = getattr(getattr(self._raw_client, "chat", None), "completions", None)
        if not chat_api or not hasattr(chat_api, "create"):
            if contains_image_input and native_responses_error is not None:
                raise RemoteVisionProviderError(
                    f"Vision provider request failed: {native_responses_error}"
                ) from native_responses_error
            raise RuntimeError("No supported text generation API is available for the configured provider.")

        messages = _coerce_responses_input_to_messages(input)
        if not messages:
            raise RuntimeError("Cannot generate a response from an empty input payload.")

        chat_kwargs: dict[str, Any] = {}
        temperature = kwargs.get("temperature")
        if temperature is not None:
            chat_kwargs["temperature"] = temperature

        max_output_tokens = kwargs.get("max_output_tokens")
        if max_output_tokens is not None:
            chat_kwargs["max_tokens"] = max_output_tokens

        raw_response = chat_api.create(
            model=model,
            messages=messages,
            **chat_kwargs,
        )
        return SimpleNamespace(
            output_text=self._gateway.extract_output_text(raw_response),
            raw_response=raw_response,
        )


class CompatibleOpenAIClient:
    def __init__(self, *, raw_client: OpenAI, gateway: "LLMGateway", provider: ProviderProfile) -> None:
        self._raw_client = raw_client
        self.responses = _ResponsesCompat(raw_client=raw_client, gateway=gateway, provider=provider)

    def __getattr__(self, item: str) -> Any:
        return getattr(self._raw_client, item)


class LLMGateway:
    def __init__(self) -> None:
        self.default_model = settings.LLM_MODEL
        self.small_model = settings.LLM_SMALL_MODEL or settings.LLM_MODEL
        self.standard_model = settings.LLM_STANDARD_MODEL or settings.LLM_MODEL
        self.heavy_model = settings.LLM_HEAVY_MODEL or self.standard_model
        self.vision_model = settings.VISION_MODEL or self.standard_model
        self.summary_model = settings.SUMMARY_AGENT_MODEL or settings.LLM_MODEL
        self.timeout_seconds = max(5, int(settings.LLM_TIMEOUT_SECONDS))
        self.max_retries = max(0, int(settings.LLM_MAX_RETRIES))
        self._text_provider = self._build_text_provider()
        self._vision_provider = self._build_vision_provider()

    def _build_provider_profile(
        self,
        *,
        api_key: str | None,
        base_url: str | None,
        reason_unavailable: str | None = None,
    ) -> ProviderProfile:
        provider_name = _provider_name_from(api_key=api_key, base_url=base_url)
        supports_text_chat, supports_responses_api, supports_multimodal_input = _provider_capabilities(provider_name)
        return ProviderProfile(
            api_key=api_key,
            base_url=base_url,
            provider_name=provider_name,
            supports_text_chat=supports_text_chat,
            supports_responses_api=supports_responses_api,
            supports_multimodal_input=supports_multimodal_input,
            default_headers=self._build_default_headers(base_url),
            reason_unavailable=reason_unavailable if not api_key else None,
        )

    def _build_text_provider(self) -> ProviderProfile:
        api_key = (settings.GROQ_API_KEY or settings.OPENAI_API_KEY or "").strip() or None
        configured_base_url = _normalized_base_url(settings.LLM_BASE_URL)
        if configured_base_url:
            base_url = configured_base_url
        elif api_key and api_key.startswith("gsk_"):
            base_url = _normalized_base_url(settings.GROQ_BASE_URL)
        else:
            base_url = None

        return self._build_provider_profile(
            api_key=api_key,
            base_url=base_url,
            reason_unavailable="No text model provider is configured.",
        )

    def _build_vision_provider(self) -> ProviderProfile:
        explicit_vision_model = (settings.VISION_MODEL or "").strip()
        explicit_api_key = (settings.VISION_API_KEY or "").strip() or None
        explicit_base_url = _normalized_base_url(settings.VISION_BASE_URL)
        openai_api_key = (settings.OPENAI_API_KEY or "").strip() or None

        if explicit_api_key or explicit_base_url or explicit_vision_model:
            if not explicit_vision_model and not self._text_provider.supports_multimodal_input:
                return self._build_provider_profile(
                    api_key=None,
                    base_url=None,
                    reason_unavailable="VISION_MODEL must be configured for image analysis.",
                )

            api_key = explicit_api_key or openai_api_key
            base_url = explicit_base_url
            if not api_key:
                return self._build_provider_profile(
                    api_key=None,
                    base_url=base_url,
                    reason_unavailable="A vision-capable API key is not configured.",
                )

            profile = self._build_provider_profile(
                api_key=api_key,
                base_url=base_url,
            )
            if not profile.supports_multimodal_input:
                return ProviderProfile(
                    api_key=profile.api_key,
                    base_url=profile.base_url,
                    provider_name=profile.provider_name,
                    supports_text_chat=profile.supports_text_chat,
                    supports_responses_api=profile.supports_responses_api,
                    supports_multimodal_input=profile.supports_multimodal_input,
                    default_headers=profile.default_headers,
                    reason_unavailable=f"The provider '{profile.provider_name}' does not support image analysis.",
                )
            return profile

        if self._text_provider.available and self._text_provider.supports_multimodal_input:
            return self._text_provider

        return self._build_provider_profile(
            api_key=None,
            base_url=None,
            reason_unavailable="Vision/OCR provider is not configured.",
        )

    @property
    def available(self) -> bool:
        return self._text_provider.available

    @property
    def provider_name(self) -> str:
        return self._text_provider.provider_name

    @property
    def api_key(self) -> str | None:
        return self._text_provider.api_key

    @property
    def base_url(self) -> str | None:
        return self._text_provider.base_url

    @property
    def vision_available(self) -> bool:
        return self._vision_provider.available and self._vision_provider.supports_multimodal_input

    @property
    def vision_provider_name(self) -> str | None:
        return self._vision_provider.provider_name if self._vision_provider.api_key else None

    @property
    def vision_reason_unavailable(self) -> str | None:
        if self.vision_available:
            return None
        if self._vision_provider.reason_unavailable:
            return self._vision_provider.reason_unavailable
        if not self._vision_provider.api_key:
            return "Vision/OCR provider is not configured."
        return f"The provider '{self._vision_provider.provider_name}' does not support image analysis."

    def supports_text_chat(self, tier: str | None = None) -> bool:
        return self._provider_for_tier(tier).supports_text_chat

    def supports_responses_api(self, tier: str | None = None) -> bool:
        return self._provider_for_tier(tier).supports_responses_api

    def supports_multimodal_input(self, tier: str | None = None) -> bool:
        return self._provider_for_tier(tier).supports_multimodal_input

    def create_client(self, tier: str | None = None) -> Optional[CompatibleOpenAIClient]:
        provider = self._provider_for_tier(tier)
        if tier == "vision" and not self.vision_available:
            return None
        if tier != "vision" and not provider.available:
            return None

        kwargs: dict = {
            "api_key": provider.api_key,
            "timeout": self.timeout_seconds,
            "max_retries": self.max_retries,
        }

        if provider.base_url:
            kwargs["base_url"] = provider.base_url

        default_headers = provider.default_headers
        if default_headers:
            kwargs["default_headers"] = default_headers

        raw_client = OpenAI(**kwargs)
        return CompatibleOpenAIClient(raw_client=raw_client, gateway=self, provider=provider)

    def resolve_model(self, tier: str | None = None) -> str:
        normalized = str(tier or "standard").strip().lower()
        if normalized == "small":
            return self.small_model
        if normalized == "heavy":
            return self.heavy_model
        if normalized == "vision":
            return self.vision_model
        if normalized == "summary":
            return self.summary_model
        return self.standard_model

    @staticmethod
    def extract_output_text(response: Any) -> str:
        direct = getattr(response, "output_text", None)
        if isinstance(direct, str) and direct.strip():
            return direct.strip()

        output = getattr(response, "output", None)
        if isinstance(output, list):
            parts: list[str] = []
            for item in output:
                candidate = ""
                if isinstance(item, dict):
                    candidate = _extract_text_from_message_content(item.get("content") or item.get("text"))
                else:
                    candidate = _extract_text_from_message_content(getattr(item, "content", None))
                if candidate:
                    parts.append(candidate)
            if parts:
                return "\n".join(parts).strip()

        choices = getattr(response, "choices", None)
        if choices and len(choices) > 0:
            message = getattr(choices[0], "message", None)
            content = getattr(message, "content", None) if message is not None else None
            extracted = _extract_text_from_message_content(content)
            if extracted:
                return extracted

        return ""

    def _provider_for_tier(self, tier: str | None = None) -> ProviderProfile:
        if str(tier or "").strip().lower() == "vision":
            return self._vision_provider
        return self._text_provider

    def _build_default_headers(self, base_url: str | None) -> dict[str, str]:
        headers: dict[str, str] = {}

        if base_url and "openrouter.ai" in base_url:
            if settings.OPENROUTER_SITE_URL:
                headers["HTTP-Referer"] = settings.OPENROUTER_SITE_URL
            if settings.OPENROUTER_APP_NAME:
                headers["X-Title"] = settings.OPENROUTER_APP_NAME

        return headers


llm_gateway = LLMGateway()
