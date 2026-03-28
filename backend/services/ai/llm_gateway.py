from __future__ import annotations

from typing import Optional

from openai import OpenAI

from backend.core.config import settings


class LLMGateway:
    def __init__(self) -> None:
        self.api_key = settings.OPENAI_API_KEY
        self.base_url = settings.LLM_BASE_URL
        self.default_model = settings.LLM_MODEL
        self.summary_model = settings.SUMMARY_AGENT_MODEL or settings.LLM_MODEL

    @property
    def available(self) -> bool:
        return bool(self.api_key)

    def create_client(self) -> Optional[OpenAI]:
        if not self.available:
            return None

        kwargs: dict = {
            "api_key": self.api_key,
        }

        if self.base_url:
            kwargs["base_url"] = self.base_url

        default_headers = self._build_default_headers()
        if default_headers:
            kwargs["default_headers"] = default_headers

        return OpenAI(**kwargs)

    def _build_default_headers(self) -> dict[str, str]:
        headers: dict[str, str] = {}

        if self.base_url and "openrouter.ai" in self.base_url:
            if settings.OPENROUTER_SITE_URL:
                headers["HTTP-Referer"] = settings.OPENROUTER_SITE_URL
            if settings.OPENROUTER_APP_NAME:
                headers["X-Title"] = settings.OPENROUTER_APP_NAME

        return headers


llm_gateway = LLMGateway()
