from __future__ import annotations

import re
from typing import Any


def _normalize_text(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def build_call_summary(transcript_text: str | None) -> str | None:
    clean_text = _normalize_text(transcript_text)
    if not clean_text:
        return None

    sentences = [segment.strip() for segment in re.split(r"(?<=[.!?])\s+", clean_text) if segment.strip()]
    if not sentences:
        return clean_text[:500].rstrip()

    summary_sentences: list[str] = []
    summary_length = 0
    for sentence in sentences:
        summary_sentences.append(sentence)
        summary_length += len(sentence)
        if len(summary_sentences) >= 3 or summary_length >= 420:
            break

    summary = " ".join(summary_sentences).strip()
    if len(summary) > 520:
        summary = summary[:517].rsplit(" ", 1)[0].rstrip() + "..."
    return summary


def _speaker_label_from_value(value: Any, fallback_index: int | None = None) -> str:
    normalized = _normalize_text(value).lower()
    if not normalized:
        if fallback_index is None:
            return "Speaker"
        return f"Speaker {fallback_index + 1}"

    lawyer_signals = ("lawyer", "attorney", "counsel", "advocate", "solicitor")
    client_signals = ("client", "caller", "customer", "petitioner", "respondent")
    assistant_signals = ("assistant", "agent", "operator", "speaker")

    if any(signal in normalized for signal in lawyer_signals):
        return "Lawyer"
    if any(signal in normalized for signal in client_signals):
        return "Client"
    if any(signal in normalized for signal in assistant_signals):
        if fallback_index is None:
            return "Speaker"
        return f"Speaker {fallback_index + 1}"
    return normalized.title()


def _extract_turn_text(turn: dict[str, Any]) -> str:
    candidate_values = (
        turn.get("text"),
        turn.get("utterance"),
        turn.get("transcript"),
        turn.get("content"),
        turn.get("value"),
    )
    for candidate in candidate_values:
        cleaned = _normalize_text(candidate)
        if cleaned:
            return cleaned
    return ""


def _extract_turn_label(turn: dict[str, Any], index: int) -> str:
    for key in ("speaker", "role", "label", "name"):
        label = _normalize_text(turn.get(key))
        if label:
            return _speaker_label_from_value(label, fallback_index=index)

    speaker_id = _normalize_text(turn.get("speaker_id") or turn.get("speakerId"))
    if speaker_id:
        return _speaker_label_from_value(speaker_id, fallback_index=index)

    return _speaker_label_from_value(None, fallback_index=index)


def _format_turn_lines(turns: list[dict[str, Any]]) -> list[str]:
    lines: list[str] = []
    for index, turn in enumerate(turns):
        if not isinstance(turn, dict):
            continue
        text = _extract_turn_text(turn)
        if not text:
            continue

        label = _extract_turn_label(turn, index)
        start_time = _normalize_text(turn.get("start_time") or turn.get("startTime"))
        if start_time:
            lines.append(f"[{start_time}] {label}: {text}")
        else:
            lines.append(f"{label}: {text}")
    return lines


def _normalize_existing_speaker_lines(transcript_text: str) -> list[str]:
    lines: list[str] = []
    for raw_line in transcript_text.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        match = re.match(r"^(?P<label>[A-Za-z][A-Za-z0-9 _-]{0,30})\s*[:\-]\s*(?P<text>.+)$", line)
        if match:
            label = _speaker_label_from_value(match.group("label"))
            lines.append(f"{label}: {_normalize_text(match.group('text'))}")
        else:
            lines.append(line)
    return lines


def build_conversation_transcript(
    transcript_text: str | None,
    *,
    conversation_turns: list[dict[str, Any]] | None = None,
) -> str | None:
    turns = conversation_turns or []
    if turns:
        lines = _format_turn_lines(turns)
        if lines:
            return "\n".join(lines).strip()

    clean_text = _normalize_text(transcript_text)
    if not clean_text:
        return None

    if "\n" in str(transcript_text or ""):
        normalized_lines = _normalize_existing_speaker_lines(str(transcript_text))
        if normalized_lines:
            return "\n".join(normalized_lines).strip()

    sentences = [segment.strip() for segment in re.split(r"(?<=[.!?])\s+", clean_text) if segment.strip()]
    if len(sentences) <= 1:
        return clean_text

    alternating_lines: list[str] = []
    for index, sentence in enumerate(sentences):
        label = "Lawyer" if index % 2 == 0 else "Client"
        alternating_lines.append(f"{label}: {sentence}")
    return "\n".join(alternating_lines).strip()
