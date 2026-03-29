from __future__ import annotations

import json
import logging
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen

from backend.core.config import settings


logger = logging.getLogger(__name__)


class ExternalResearchService:
    def __init__(self) -> None:
        self.enabled = settings.EXTERNAL_RESEARCH_ENABLED
        self.provider = (settings.EXTERNAL_RESEARCH_PROVIDER or "tavily").strip().lower()
        self.max_results = max(1, int(settings.EXTERNAL_RESEARCH_MAX_RESULTS))
        self.timeout_seconds = max(3, int(settings.EXTERNAL_RESEARCH_TIMEOUT_SECONDS))
        self.tavily_api_key = (settings.TAVILY_API_KEY or "").strip()
        self.serpapi_api_key = (settings.SERPAPI_API_KEY or "").strip()

    @property
    def available(self) -> bool:
        provider = self._resolve_provider()
        return provider is not None

    def search(self, *, query: str, max_results: int | None = None) -> dict[str, Any]:
        normalized_query = (query or "").strip()
        if not normalized_query:
            return {
                "used_external": False,
                "provider": None,
                "query": "",
                "results": [],
                "error": "Empty query.",
            }

        if not self.enabled:
            return {
                "used_external": False,
                "provider": None,
                "query": normalized_query,
                "results": [],
                "error": "External research is disabled.",
            }

        provider = self._resolve_provider()
        if not provider:
            return {
                "used_external": False,
                "provider": None,
                "query": normalized_query,
                "results": [],
                "error": "No external research API key is configured.",
            }

        limit = self._bound_max_results(max_results)
        try:
            if provider == "tavily":
                results = self._search_tavily(query=normalized_query, max_results=limit)
            else:
                results = self._search_serpapi(query=normalized_query, max_results=limit)
        except (HTTPError, URLError, TimeoutError, ValueError) as exc:
            logger.warning("External research request failed via provider=%s: %s", provider, exc)
            return {
                "used_external": False,
                "provider": provider,
                "query": normalized_query,
                "results": [],
                "error": str(exc),
            }
        except Exception as exc:
            logger.exception("Unexpected external research error via provider=%s: %s", provider, exc)
            return {
                "used_external": False,
                "provider": provider,
                "query": normalized_query,
                "results": [],
                "error": f"Unexpected external research error: {exc}",
            }

        return {
            "used_external": bool(results),
            "provider": provider,
            "query": normalized_query,
            "results": results,
            "error": None if results else "No external research results were returned.",
        }

    def _resolve_provider(self) -> str | None:
        preferred = self.provider
        if preferred == "serpapi" and self.serpapi_api_key:
            return "serpapi"
        if preferred == "tavily" and self.tavily_api_key:
            return "tavily"

        if self.tavily_api_key:
            return "tavily"
        if self.serpapi_api_key:
            return "serpapi"
        return None

    def _bound_max_results(self, value: int | None) -> int:
        candidate = self.max_results if value is None else int(value)
        return max(1, min(candidate, 10))

    def _search_tavily(self, *, query: str, max_results: int) -> list[dict[str, Any]]:
        payload = {
            "api_key": self.tavily_api_key,
            "query": query,
            "search_depth": "basic",
            "max_results": max_results,
            "include_answer": True,
        }
        body = json.dumps(payload).encode("utf-8")
        request = Request(
            url="https://api.tavily.com/search",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        response_payload = self._load_json(request=request)
        results: list[dict[str, Any]] = []

        answer = str(response_payload.get("answer") or "").strip()
        if answer:
            results.append(
                self._normalized_result(
                    provider="tavily",
                    rank=1,
                    title="Tavily Answer",
                    url="",
                    snippet=answer,
                )
            )

        source_items = response_payload.get("results") or []
        for index, item in enumerate(source_items, start=len(results) + 1):
            if not isinstance(item, dict):
                continue

            title = str(item.get("title") or "").strip()
            url = str(item.get("url") or "").strip()
            snippet = str(item.get("content") or item.get("snippet") or "").strip()
            if not (title or url or snippet):
                continue

            results.append(
                self._normalized_result(
                    provider="tavily",
                    rank=index,
                    title=title,
                    url=url,
                    snippet=snippet,
                )
            )
            if len(results) >= max_results:
                break

        return results[:max_results]

    def _search_serpapi(self, *, query: str, max_results: int) -> list[dict[str, Any]]:
        params = urlencode(
            {
                "engine": "google",
                "q": query,
                "num": max_results,
                "api_key": self.serpapi_api_key,
            }
        )
        request = Request(
            url=f"https://serpapi.com/search.json?{params}",
            method="GET",
        )
        response_payload = self._load_json(request=request)

        organic_results = response_payload.get("organic_results") or []
        results: list[dict[str, Any]] = []

        for index, item in enumerate(organic_results, start=1):
            if not isinstance(item, dict):
                continue
            title = str(item.get("title") or "").strip()
            url = str(item.get("link") or "").strip()
            snippet = str(item.get("snippet") or "").strip()
            if not (title or url or snippet):
                continue

            results.append(
                self._normalized_result(
                    provider="serpapi",
                    rank=index,
                    title=title,
                    url=url,
                    snippet=snippet,
                )
            )
            if len(results) >= max_results:
                break

        return results[:max_results]

    def _load_json(self, *, request: Request) -> dict[str, Any]:
        with urlopen(request, timeout=self.timeout_seconds) as response:
            raw_bytes = response.read()
        decoded = raw_bytes.decode("utf-8", errors="ignore")
        payload = json.loads(decoded or "{}")
        return payload if isinstance(payload, dict) else {}

    @staticmethod
    def _normalized_result(
        *,
        provider: str,
        rank: int,
        title: str,
        url: str,
        snippet: str,
    ) -> dict[str, Any]:
        parsed = urlparse(url) if url else None
        domain = (parsed.netloc or "").lower() if parsed else ""
        cleaned_title = title or domain or "Web Result"
        return {
            "provider": provider,
            "rank": rank,
            "title": cleaned_title,
            "url": url,
            "domain": domain,
            "snippet": snippet[:1200],
        }


external_research_service = ExternalResearchService()
