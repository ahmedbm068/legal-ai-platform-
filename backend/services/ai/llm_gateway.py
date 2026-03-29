from __future__ import annotations

import logging
from types import SimpleNamespace
from typing import Any, Optional

from openai import OpenAI

from backend.core.config import settings

logger = logging.getLogger(__name__)


def _normalized_base_url(value: str | None) -> str | None:
    normalized = (value or "").strip().rstrip("/")
    return normalized or None


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

            normalized_content = _extract_text_from_message_content(content)
            if not normalized_content and isinstance(item.get("text"), str):
                normalized_content = item["text"].strip()

            if normalized_content:
                messages.append({"role": role, "content": normalized_content})

        return messages

    if isinstance(input_payload, dict):
        role = str(input_payload.get("role") or "user").strip() or "user"
        content = _extract_text_from_message_content(input_payload.get("content") or input_payload.get("text"))
        if content:
            return [{"role": role, "content": content}]

    text_payload = str(input_payload or "").strip()
    return [{"role": "user", "content": text_payload}] if text_payload else []


class _ResponsesCompat:
    def __init__(self, *, raw_client: OpenAI, gateway: "LLMGateway") -> None:
        self._raw_client = raw_client
        self._gateway = gateway

    def create(self, *, model: str, input: Any, **kwargs):
        should_prefer_chat = self._gateway.provider_name == "groq"

        if not should_prefer_chat:
            native_responses = getattr(self._raw_client, "responses", None)
            if native_responses and hasattr(native_responses, "create"):
                try:
                    raw_response = native_responses.create(model=model, input=input, **kwargs)
                    return SimpleNamespace(
                        output_text=self._gateway.extract_output_text(raw_response),
                        raw_response=raw_response,
                    )
                except Exception as exc:
                    logger.debug("Native responses.create failed; trying chat-completions fallback: %s", exc)

        chat_api = getattr(getattr(self._raw_client, "chat", None), "completions", None)
        if not chat_api or not hasattr(chat_api, "create"):
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
    def __init__(self, *, raw_client: OpenAI, gateway: "LLMGateway") -> None:
        self._raw_client = raw_client
        self.responses = _ResponsesCompat(raw_client=raw_client, gateway=gateway)

    def __getattr__(self, item: str) -> Any:
        return getattr(self._raw_client, item)


class LLMGateway:
    def __init__(self) -> None:
        self.api_key = (settings.GROQ_API_KEY or settings.OPENAI_API_KEY or "").strip() or None
        configured_base_url = _normalized_base_url(settings.LLM_BASE_URL)
        if configured_base_url:
            self.base_url = configured_base_url
        elif self.api_key and self.api_key.startswith("gsk_"):
            self.base_url = _normalized_base_url(settings.GROQ_BASE_URL)
        else:
            self.base_url = None

        self.default_model = settings.LLM_MODEL
        self.summary_model = settings.SUMMARY_AGENT_MODEL or settings.LLM_MODEL
        self.timeout_seconds = max(5, int(settings.LLM_TIMEOUT_SECONDS))
        self.max_retries = max(0, int(settings.LLM_MAX_RETRIES))

    @property
    def available(self) -> bool:
        return bool(self.api_key)

    @property
    def provider_name(self) -> str:
        base = (self.base_url or "").lower()
        if "groq.com" in base or (self.api_key or "").startswith("gsk_"):
            return "groq"
        if "openrouter.ai" in base:
            return "openrouter"
        if base:
            return "openai-compatible"
        return "openai"

    def create_client(self) -> Optional[CompatibleOpenAIClient]:
        if not self.available:
            return None

        kwargs: dict = {
            "api_key": self.api_key,
            "timeout": self.timeout_seconds,
            "max_retries": self.max_retries,
        }

        if self.base_url:
            kwargs["base_url"] = self.base_url

        default_headers = self._build_default_headers()
        if default_headers:
            kwargs["default_headers"] = default_headers

        raw_client = OpenAI(**kwargs)
        return CompatibleOpenAIClient(raw_client=raw_client, gateway=self)

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

    def _build_default_headers(self) -> dict[str, str]:
        headers: dict[str, str] = {}

        if self.base_url and "openrouter.ai" in self.base_url:
            if settings.OPENROUTER_SITE_URL:
                headers["HTTP-Referer"] = settings.OPENROUTER_SITE_URL
            if settings.OPENROUTER_APP_NAME:
                headers["X-Title"] = settings.OPENROUTER_APP_NAME

        return headers


llm_gateway = LLMGateway()
