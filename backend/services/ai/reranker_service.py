from __future__ import annotations

from pathlib import Path
from typing import Any

from sentence_transformers import CrossEncoder

from backend.core.config import settings

PROJECT_ROOT = Path(__file__).resolve().parents[3]


def _resolve_model_path(model_name: str) -> str:
    candidate = PROJECT_ROOT / model_name
    if candidate.exists():
        return str(candidate)
    return model_name


class RerankerService:
    def __init__(self, model_name: str | None = None) -> None:
        raw_name = model_name or settings.RERANKER_MODEL
        self.model_name = _resolve_model_path(raw_name)
        self._model: CrossEncoder | None = None
        self._load_error: str | None = None

    @property
    def available(self) -> bool:
        return settings.RERANKER_ENABLED

    def _get_model(self) -> CrossEncoder:
        if self._model is not None:
            return self._model

        if self._load_error:
            raise RuntimeError(self._load_error)

        try:
            self._model = CrossEncoder(self.model_name)
            return self._model
        except Exception as exc:
            self._load_error = f"Unable to load reranker model '{self.model_name}': {exc}"
            raise RuntimeError(self._load_error) from exc

    def rerank(self, query: str, results: list[dict[str, Any]], top_k: int) -> tuple[list[dict[str, Any]], list[str]]:
        if not self.available or not query.strip() or not results:
            return results[:top_k], ["Reranker skipped."]

        try:
            model = self._get_model()
            pairs = [(query, item.get("chunk_text", "")) for item in results]
            scores = model.predict(pairs)

            reranked: list[dict[str, Any]] = []
            for item, score in zip(results, scores):
                enriched = dict(item)
                enriched["rerank_score"] = float(score)
                enriched["score"] = float((0.75 * float(score)) + (0.25 * float(item.get("score", 0.0))))
                reranked.append(enriched)

            reranked.sort(key=lambda item: item.get("score", 0.0), reverse=True)
            return reranked[:top_k], [f"Reranked {len(reranked)} chunks with {self.model_name}."]
        except Exception as exc:
            return results[:top_k], [f"Reranker unavailable: {exc}"]


reranker_service = RerankerService()
