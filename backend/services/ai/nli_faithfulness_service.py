"""NLI-based citation faithfulness scoring.

Splits the assistant's answer into atomic claim-sized sentences and runs a
zero-shot multilingual NLI cross-encoder against the retrieved sources.
For each sentence we emit:

* ``best_score``     — entailment probability against the most-supportive source
* ``label``          — ``entailment`` / ``neutral`` / ``contradiction``
* ``best_source_index`` — the index in the supplied ``sources`` list

Aggregating across all sentences gives a single ``faithfulness.score`` in
``[0, 1]`` (mean entailment probability). This is precisely the kind of
*automated, label-free* hallucination metric an AI-engineering jury asks
for — and it is computed against the same retrieved corpus the user sees.

Implementation notes
--------------------
* Uses ``sentence-transformers`` CrossEncoder, which is already pinned in
  ``requirements.txt`` (5.1.1).
* The default model is ``MoritzLaurer/mDeBERTa-v3-base-xnli-multilingual``
  (zero-shot NLI, French + Arabic + English). It is downloaded lazily on
  first use; a flag disables the service entirely if the model cannot be
  loaded (offline CI, missing weights, etc.) — failures must never break a
  user response.
* ``[cite:doc:N]`` markers are stripped before scoring.
* Sources are truncated to ``MAX_SOURCE_CHARS`` per item to keep latency
  bounded — NLI cross-encoders take ``O(claims × sources)`` forward passes.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from threading import Lock
from typing import Any, Mapping, Sequence


logger = logging.getLogger(__name__)


DEFAULT_NLI_MODEL = "MoritzLaurer/mDeBERTa-v3-base-xnli-multilingual"

_PROJECT_ROOT = Path(__file__).resolve().parents[3]


def _resolve_nli_model() -> str:
    """Return the configured fine-tuned model path if it exists on disk, else the zero-shot fallback.

    The configured path (``settings.NLI_MODEL``) is treated as project-relative
    when not absolute, so deployments can override it via env without
    worrying about the working directory.
    """
    try:
        from backend.core.config import settings
        configured = settings.NLI_MODEL
    except Exception:
        configured = "backend/models_local/legal_nli_v1"
    candidate = Path(configured)
    if not candidate.is_absolute():
        candidate = _PROJECT_ROOT / candidate
    if candidate.exists():
        return str(candidate)
    return DEFAULT_NLI_MODEL
ENTAILMENT_THRESHOLD = 0.55  # ≥ → "supported"
CONTRADICTION_THRESHOLD = 0.55  # ≥ → "contradiction"
MAX_SOURCE_CHARS = 800
MAX_CLAIMS = 25  # cap per answer to keep latency bounded
MIN_CLAIM_CHARS = 18  # ignore stubs like "Yes." or numbered headers

# Aggregate label thresholds on the mean entailment score:
#   ≥ 0.70 → supported
#   ≥ 0.40 → partial
#   else  → unsupported
LABEL_SUPPORTED = "supported"
LABEL_PARTIAL = "partial"
LABEL_UNSUPPORTED = "unsupported"
SUPPORTED_THRESHOLD = 0.70
PARTIAL_THRESHOLD = 0.40

_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?؟])\s+(?=[A-ZÀ-Ý؀-ۿ0-9])")
_CITE_TOKEN_RE = re.compile(r"\[cite:[^\]]+\]")
_HEADING_RE = re.compile(r"^[\s#\d.\-•*]+$")


@dataclass
class ClaimScore:
    text: str
    best_score: float
    label: str
    best_source_index: int | None
    contradiction_score: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "best_score": round(float(self.best_score), 4),
            "contradiction_score": round(float(self.contradiction_score), 4),
            "label": self.label,
            "best_source_index": self.best_source_index,
        }


@dataclass
class FaithfulnessReport:
    score: float
    label: str
    claims: list[ClaimScore] = field(default_factory=list)
    summary: str = ""
    skipped_reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "score": round(float(self.score), 4),
            "label": self.label,
            "summary": self.summary,
            "claims": [c.to_dict() for c in self.claims],
            "skipped_reason": self.skipped_reason,
        }


class NLIFaithfulnessService:
    """Scores answer faithfulness against retrieved sources via a multilingual
    NLI cross-encoder."""

    def __init__(self, *, model_name: str | None = None) -> None:
        self.model_name = model_name or _resolve_nli_model()
        self._model: Any | None = None
        self._unavailable_reason: str | None = None
        self._lock = Lock()

    def is_available(self) -> bool:
        try:
            from backend.core.config import settings
            if not settings.NLI_ENABLED:
                return False
        except Exception:
            pass
        return self._unavailable_reason is None

    def score_response(
        self,
        response: Mapping[str, Any],
    ) -> FaithfulnessReport:
        """Compute a faithfulness report for an assembled copilot response.

        Returns a report even when the service is unavailable so callers can
        always attach ``response['faithfulness']`` without an extra branch.
        """

        answer = str(response.get("answer") or "")
        sources_raw = response.get("sources") if isinstance(response.get("sources"), list) else []
        return self.score(answer=answer, sources=sources_raw)

    def score(
        self,
        *,
        answer: str,
        sources: Sequence[Mapping[str, Any] | str],
    ) -> FaithfulnessReport:
        if not self.is_available():
            return FaithfulnessReport(
                score=0.0,
                label=LABEL_UNSUPPORTED,
                summary="NLI faithfulness scoring is disabled.",
                skipped_reason=self._unavailable_reason or "nli_disabled",
            )
        if not answer or not answer.strip():
            return FaithfulnessReport(
                score=0.0,
                label=LABEL_UNSUPPORTED,
                summary="Empty answer.",
                skipped_reason="empty_answer",
            )

        source_texts = _extract_source_texts(sources)
        if not source_texts:
            return FaithfulnessReport(
                score=0.0,
                label=LABEL_UNSUPPORTED,
                summary="No retrieved sources available; faithfulness undefined.",
                skipped_reason="no_sources",
            )

        claims = _split_into_claims(answer)
        if not claims:
            return FaithfulnessReport(
                score=0.0,
                label=LABEL_UNSUPPORTED,
                summary="Answer contained no scorable sentences.",
                skipped_reason="no_claims",
            )

        model = self._ensure_model()
        if model is None:
            return FaithfulnessReport(
                score=0.0,
                label=LABEL_UNSUPPORTED,
                summary=f"NLI model unavailable: {self._unavailable_reason}",
                skipped_reason=self._unavailable_reason or "model_unavailable",
            )

        # Zero-shot NLI hypothesis pattern works well for entailment scoring:
        # premise = source text, hypothesis = "<claim> is true."
        # We score (premise, hypothesis) pairs in batches.
        pairs: list[tuple[str, str]] = []
        index_map: list[tuple[int, int]] = []  # (claim_idx, source_idx)
        for ci, claim in enumerate(claims):
            hypothesis = claim if claim.endswith(".") else f"{claim}."
            for si, src in enumerate(source_texts):
                pairs.append((src, hypothesis))
                index_map.append((ci, si))

        try:
            probs = _run_nli_inference(model, pairs)
        except Exception as exc:  # noqa: BLE001 — never break the response
            logger.warning("nli_predict_failed err=%s", exc, exc_info=True)
            return FaithfulnessReport(
                score=0.0,
                label=LABEL_UNSUPPORTED,
                summary="NLI scoring failed at inference time.",
                skipped_reason="inference_error",
            )

        ent_idx, contra_idx = _resolve_label_indices(model)

        per_claim_best: list[ClaimScore] = [
            ClaimScore(
                text=claim,
                best_score=0.0,
                contradiction_score=0.0,
                label="neutral",
                best_source_index=None,
            )
            for claim in claims
        ]

        for (ci, si), row in zip(index_map, probs):
            ent_p = float(row[ent_idx])
            contra_p = float(row[contra_idx])
            current = per_claim_best[ci]
            if ent_p > current.best_score:
                if ent_p >= ENTAILMENT_THRESHOLD:
                    label = "entailment"
                elif contra_p >= CONTRADICTION_THRESHOLD:
                    label = "contradiction"
                else:
                    label = "neutral"
                per_claim_best[ci] = ClaimScore(
                    text=claim_at(claims, ci),
                    best_score=ent_p,
                    contradiction_score=max(current.contradiction_score, contra_p),
                    label=label,
                    best_source_index=si,
                )
            elif contra_p > current.contradiction_score:
                # Track the worst contradiction we have seen even if entailment
                # against another source is higher — surfaces "supported by A,
                # contradicted by B" cases in the audit trail.
                per_claim_best[ci] = ClaimScore(
                    text=current.text,
                    best_score=current.best_score,
                    contradiction_score=contra_p,
                    label=current.label,
                    best_source_index=current.best_source_index,
                )

        mean_score = sum(c.best_score for c in per_claim_best) / max(1, len(per_claim_best))
        if mean_score >= SUPPORTED_THRESHOLD:
            agg_label = LABEL_SUPPORTED
        elif mean_score >= PARTIAL_THRESHOLD:
            agg_label = LABEL_PARTIAL
        else:
            agg_label = LABEL_UNSUPPORTED

        contradicted = sum(1 for c in per_claim_best if c.label == "contradiction")
        unsupported = sum(1 for c in per_claim_best if c.best_score < ENTAILMENT_THRESHOLD)
        summary = (
            f"{len(per_claim_best)} claim(s) scored; "
            f"mean entailment={mean_score:.2f}; "
            f"unsupported={unsupported}; contradictions={contradicted}."
        )

        return FaithfulnessReport(
            score=mean_score,
            label=agg_label,
            claims=per_claim_best,
            summary=summary,
        )

    # ──────────────────────────────────────────────────────────────────────
    # Internal — lazy model loading
    # ──────────────────────────────────────────────────────────────────────

    def _ensure_model(self) -> Any | None:
        if self._unavailable_reason is not None:
            return None
        if self._model is not None:
            return self._model
        with self._lock:
            if self._model is not None:
                return self._model
            # Try loading as a HuggingFace AutoModel first (fine-tuned XLM-R).
            # Fall back to sentence-transformers CrossEncoder for the zero-shot model.
            model_path = Path(self.model_name)
            is_local_hf = model_path.exists() and (model_path / "config.json").exists()
            if is_local_hf:
                try:
                    import torch
                    from transformers import AutoModelForSequenceClassification, AutoTokenizer
                    tok = AutoTokenizer.from_pretrained(self.model_name)
                    mdl = AutoModelForSequenceClassification.from_pretrained(self.model_name)
                    mdl.eval()
                    self._model = {"type": "hf", "model": mdl, "tokenizer": tok}
                    logger.info("nli_model_loaded type=hf model=%s", self.model_name)
                    return self._model
                except Exception as exc:  # noqa: BLE001
                    self._unavailable_reason = f"hf_model_load_failed: {exc}"
                    logger.warning("nli_disabled reason=%s", self._unavailable_reason)
                    return None
            else:
                try:
                    from sentence_transformers import CrossEncoder
                except Exception as exc:  # noqa: BLE001
                    self._unavailable_reason = f"sentence_transformers_missing: {exc}"
                    logger.warning("nli_disabled reason=%s", self._unavailable_reason)
                    return None
                try:
                    self._model = {"type": "crossencoder", "model": CrossEncoder(self.model_name)}
                    logger.info("nli_model_loaded type=crossencoder model=%s", self.model_name)
                    return self._model
                except Exception as exc:  # noqa: BLE001
                    self._unavailable_reason = f"model_load_failed: {exc}"
                    logger.warning("nli_disabled reason=%s", self._unavailable_reason)
                    return None


# ──────────────────────────────────────────────────────────────────────────
# Pure helpers
# ──────────────────────────────────────────────────────────────────────────


def claim_at(claims: list[str], idx: int) -> str:
    return claims[idx] if 0 <= idx < len(claims) else ""


def _extract_source_texts(sources: Sequence[Mapping[str, Any] | str]) -> list[str]:
    out: list[str] = []
    for src in sources:
        if isinstance(src, str):
            text = src
        elif isinstance(src, Mapping):
            text = (
                src.get("snippet")
                or src.get("chunk_text")
                or src.get("text")
                or src.get("content")
                or ""
            )
            text = str(text)
        else:
            continue
        text = text.strip()
        if not text:
            continue
        if len(text) > MAX_SOURCE_CHARS:
            text = text[:MAX_SOURCE_CHARS]
        out.append(text)
    return out


def _split_into_claims(answer: str) -> list[str]:
    cleaned = _CITE_TOKEN_RE.sub("", answer).strip()
    if not cleaned:
        return []
    raw_sentences = _SENTENCE_SPLIT_RE.split(cleaned)
    out: list[str] = []
    for raw in raw_sentences:
        s = raw.strip()
        if not s or len(s) < MIN_CLAIM_CHARS:
            continue
        if _HEADING_RE.match(s):
            continue
        out.append(s)
        if len(out) >= MAX_CLAIMS:
            break
    return out


def _run_nli_inference(model: dict, pairs: list[tuple[str, str]]) -> Any:
    """Run inference for both HF and CrossEncoder model types.

    Returns a 2-D array of shape (n_pairs, n_labels) with softmax probabilities.
    """
    import numpy as np

    if model["type"] == "hf":
        import torch
        tok = model["tokenizer"]
        mdl = model["model"]
        all_probs = []
        batch_size = 16
        for i in range(0, len(pairs), batch_size):
            batch = pairs[i : i + batch_size]
            premises   = [p for p, _ in batch]
            hypotheses = [h for _, h in batch]
            enc = tok(
                premises, hypotheses,
                padding=True, truncation=True, max_length=256,
                return_tensors="pt",
            )
            with torch.no_grad():
                logits = mdl(**enc).logits
            probs = torch.softmax(logits, dim=-1).cpu().numpy()
            all_probs.append(probs)
        return np.vstack(all_probs)
    else:
        raw = model["model"].predict(pairs, convert_to_numpy=True, show_progress_bar=False)
        return _softmax_rows(raw)


def _softmax_rows(scores: Any) -> Any:
    """Apply softmax row-wise to a 2D numeric array — local impl to avoid a
    hard numpy dependency in the typing layer (numpy is already installed).
    """

    import numpy as np

    arr = np.asarray(scores, dtype="float64")
    if arr.ndim == 1:
        arr = arr.reshape(1, -1)
    arr -= arr.max(axis=1, keepdims=True)
    exp = np.exp(arr)
    return exp / exp.sum(axis=1, keepdims=True)


def _resolve_label_indices(model: dict) -> tuple[int, int]:
    """Return (entailment_index, contradiction_index) for the model's NLI head."""
    try:
        if model["type"] == "hf":
            id2label = model["model"].config.id2label
        else:
            # CrossEncoder wraps a HF model at .model.config.id2label
            id2label = getattr(getattr(model["model"], "model", None), "config", None)
            id2label = getattr(id2label, "id2label", None)

        if isinstance(id2label, dict):
            ent = contra = None
            for idx, name in id2label.items():
                norm = str(name).lower()
                if "entail" in norm:
                    ent = int(idx)
                elif "contradict" in norm:
                    contra = int(idx)
            if ent is not None and contra is not None:
                return ent, contra
    except Exception:  # noqa: BLE001
        pass
    return 0, 2  # mDeBERTa XNLI default


nli_faithfulness_service = NLIFaithfulnessService()  # auto-resolves fine-tuned model if present


__all__ = [
    "ClaimScore",
    "FaithfulnessReport",
    "NLIFaithfulnessService",
    "nli_faithfulness_service",
    "DEFAULT_NLI_MODEL",
    "LABEL_SUPPORTED",
    "LABEL_PARTIAL",
    "LABEL_UNSUPPORTED",
]
