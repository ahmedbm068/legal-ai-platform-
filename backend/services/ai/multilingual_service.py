"""Multilingual answer service.

Post-orchestration step that ensures the assistant message is rendered in
the user's requested language (``fr`` / ``ar`` / ``en``) while keeping
citation markers, statute names, and ``[cite:doc:N]`` tokens in their
original language so legal precision is preserved.

Design notes
------------
* Retrieval and grounding stay in the source language. Translation happens
  *after* the orchestrator has produced its grounded answer so the verifier
  decision is unaffected.
* Detection uses a lightweight script-based heuristic so we do not pull a
  langdetect dependency. For mixed-script Tunisian content (FR + AR) the
  heuristic returns the dominant script's language.
* Translation is delegated to the existing LLM gateway. If the gateway is
  unavailable the original answer is returned unchanged with a warning.
* ``[cite:doc:N]`` tokens are masked before translation and restored after,
  so the citation IDs cannot drift.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any

from backend.services.ai.llm_gateway import llm_gateway


logger = logging.getLogger(__name__)


SUPPORTED_LANGUAGES = ("fr", "ar", "en", "auto")
LANGUAGE_NAMES = {
    "fr": "French",
    "ar": "Arabic",
    "en": "English",
}

_CITE_TOKEN_RE = re.compile(r"\[cite:[^\]]+\]")
_ARABIC_RE = re.compile(r"[؀-ۿݐ-ݿ]")
_LATIN_RE = re.compile(r"[A-Za-z]")
# Quick French-vs-English heuristic: characters that strongly suggest French.
_FRENCH_HINTS = re.compile(r"[àâäéèêëïîôöùûüÿçœÀÂÄÉÈÊËÏÎÔÖÙÛÜŸÇŒ]")
_FRENCH_WORDS = re.compile(
    r"\b(le|la|les|des|une|du|et|ou|que|qui|dans|pour|avec|sur|par|"
    r"selon|article|loi|code|tribunal|jugement|arrêt|"
    r"droit|civil|pénal|succession)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class LanguageOutcome:
    """Result of the multilingual post-pass."""

    requested: str
    detected_input: str
    final: str
    translated: bool
    used_fallback: bool
    fallback_reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "requested": self.requested,
            "detected_input": self.detected_input,
            "final": self.final,
            "translated": self.translated,
            "used_fallback": self.used_fallback,
            "fallback_reason": self.fallback_reason,
        }


def detect_language(text: str) -> str:
    """Best-effort language detection. Returns ``fr``, ``ar``, ``en`` or ``en`` as fallback.

    The legal corpus is a mix of French and Arabic with occasional English.
    A character-class heuristic is sufficient and avoids extra dependencies.
    """

    if not text or not isinstance(text, str):
        return "en"

    arabic_chars = len(_ARABIC_RE.findall(text))
    latin_chars = len(_LATIN_RE.findall(text))
    if arabic_chars > latin_chars and arabic_chars > 0:
        return "ar"
    if latin_chars == 0:
        return "en"

    if _FRENCH_HINTS.search(text):
        return "fr"
    french_word_hits = len(_FRENCH_WORDS.findall(text))
    if french_word_hits >= 2:
        return "fr"

    # Default to English when we cannot tell French from English with confidence.
    return "en"


def normalize_language(value: str | None, *, default: str = "auto") -> str:
    """Normalize a language code into the supported set."""

    if not value:
        return default
    candidate = str(value).strip().lower()
    if candidate in SUPPORTED_LANGUAGES:
        return candidate
    return default


def _mask_citations(text: str) -> tuple[str, list[str]]:
    """Replace ``[cite:doc:N]`` tokens with stable placeholders the LLM
    will not translate, returning the masked text and the ordered token list.
    """

    tokens: list[str] = []

    def _swap(match: re.Match[str]) -> str:
        tokens.append(match.group(0))
        return f"␟{len(tokens) - 1}␟"  # rare control chars as fence

    masked = _CITE_TOKEN_RE.sub(_swap, text)
    return masked, tokens


def _restore_citations(text: str, tokens: list[str]) -> str:
    if not tokens:
        return text
    restored = text

    def _swap(match: re.Match[str]) -> str:
        idx = int(match.group(1))
        return tokens[idx] if 0 <= idx < len(tokens) else match.group(0)

    return re.sub(r"␟(\d+)␟", _swap, restored)


class MultilingualService:
    """Stateless service that enforces an output language on a copilot response."""

    def ensure_language(
        self,
        response: dict[str, Any],
        *,
        target_language: str,
        language_strict: bool = True,
    ) -> LanguageOutcome:
        """Translate ``response['answer']`` (and ``response['message']``) into
        ``target_language`` when needed. Mutates ``response`` in place.

        ``target_language`` may be one of ``fr | ar | en | auto``. ``auto``
        means "match the user's input language" — handled by the caller; this
        service treats ``auto`` as a no-op.
        """

        answer = str(response.get("answer") or "")
        target = normalize_language(target_language, default="auto")
        detected = detect_language(answer)

        if target == "auto" or target == detected or not answer.strip():
            outcome = LanguageOutcome(
                requested=target,
                detected_input=detected,
                final=detected,
                translated=False,
                used_fallback=False,
            )
            response["language"] = outcome.to_dict()
            return outcome

        translated, used_fallback, reason = self._translate(
            text=answer,
            source_language=detected,
            target_language=target,
            strict=language_strict,
        )

        if used_fallback:
            outcome = LanguageOutcome(
                requested=target,
                detected_input=detected,
                final=detected,
                translated=False,
                used_fallback=True,
                fallback_reason=reason,
            )
            response["language"] = outcome.to_dict()
            return outcome

        response["answer"] = translated
        # Mirror onto ``message`` if it duplicates the answer (UI surfaces both).
        if response.get("message") == answer:
            response["message"] = translated

        outcome = LanguageOutcome(
            requested=target,
            detected_input=detected,
            final=target,
            translated=True,
            used_fallback=False,
        )
        response["language"] = outcome.to_dict()
        return outcome

    def _translate(
        self,
        *,
        text: str,
        source_language: str,
        target_language: str,
        strict: bool,
    ) -> tuple[str, bool, str | None]:
        client = llm_gateway.create_client()
        if client is None:
            return text, True, "llm_gateway_unavailable"

        masked, tokens = _mask_citations(text)
        target_name = LANGUAGE_NAMES.get(target_language, target_language)
        source_name = LANGUAGE_NAMES.get(source_language, source_language)

        instruction_lines = [
            f"Translate the assistant's legal answer from {source_name} into {target_name}.",
            "Keep statute names, code references, and quoted article text in their ORIGINAL language.",
            "Preserve every placeholder of the form ␟<digits>␟ EXACTLY — do not translate, "
            "reorder, or remove them.",
            "Preserve markdown structure (headings, bullets, bold).",
        ]
        if strict:
            instruction_lines.append(
                "Do not switch to any other language even if part of the input is already in the "
                f"target language — the entire answer must be in {target_name}."
            )

        system_prompt = " ".join(instruction_lines)

        try:
            model = llm_gateway.resolve_model("text") or llm_gateway.default_model
            completion = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": masked},
                ],
                temperature=0.0,
                max_tokens=2000,
            )
            translated_masked = llm_gateway.extract_output_text(completion).strip()
            if not translated_masked:
                return text, True, "empty_translation"
            return _restore_citations(translated_masked, tokens), False, None
        except Exception as exc:  # noqa: BLE001 — translation is best-effort
            logger.warning(
                "multilingual_translate_failed source=%s target=%s err=%s",
                source_language,
                target_language,
                exc,
                exc_info=True,
            )
            return text, True, "translation_error"


multilingual_service = MultilingualService()


__all__ = [
    "SUPPORTED_LANGUAGES",
    "LANGUAGE_NAMES",
    "LanguageOutcome",
    "MultilingualService",
    "detect_language",
    "normalize_language",
    "multilingual_service",
]
