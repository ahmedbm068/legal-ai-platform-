from __future__ import annotations

import json
import re
from typing import Any


class AgentOutputFormatter:
    @staticmethod
    def normalize_text(value: Any) -> str:
        return str(value or "").strip()

    @staticmethod
    def sanitize_text(value: Any) -> str:
        text = AgentOutputFormatter.normalize_text(value)
        text = re.sub(r"\s+", " ", text).strip()
        return text

    @staticmethod
    def extract_json_payload(raw_text: str) -> dict[str, Any] | None:
        candidate = AgentOutputFormatter.normalize_text(raw_text)
        if not candidate:
            return None

        if candidate.startswith("```"):
            candidate = candidate.strip("`")
            candidate = candidate.replace("json", "", 1).strip()

        try:
            payload = json.loads(candidate)
            return payload if isinstance(payload, dict) else None
        except json.JSONDecodeError:
            start = candidate.find("{")
            end = candidate.rfind("}")
            if start == -1 or end == -1 or end <= start:
                return None
            try:
                payload = json.loads(candidate[start : end + 1])
                return payload if isinstance(payload, dict) else None
            except json.JSONDecodeError:
                return None

    @classmethod
    def normalize_string_list(cls, values: Any, *, limit: int | None = None) -> list[str]:
        if not isinstance(values, list):
            return []

        normalized: list[str] = []
        for item in values:
            cleaned = cls.sanitize_text(item).rstrip(".")
            if not cleaned:
                continue
            if cleaned not in normalized:
                normalized.append(cleaned)
            if limit is not None and len(normalized) >= limit:
                break
        return normalized

    @classmethod
    def normalize_date_items(cls, values: Any) -> list[dict[str, str]]:
        if not isinstance(values, list):
            return []

        normalized: list[dict[str, str]] = []
        for item in values:
            if not isinstance(item, dict):
                continue
            label = cls.sanitize_text(item.get("label"))
            value = cls.sanitize_text(item.get("value"))
            if label and value:
                entry = {"label": label, "value": value}
                if entry not in normalized:
                    normalized.append(entry)
        return normalized

    @staticmethod
    def build_legal_copilot_guardrails() -> list[str]:
        return [
            "- Act as legal decision-support for lawyers, not as a final decision-maker.",
            "- Keep legal method order: issue, legal basis, rule, application, uncertainty, counter-analysis, next steps.",
            "- Separate confirmed facts, inferred facts, missing facts, and assumptions requiring validation.",
            "- Ground legal statements in supplied sources only; never fabricate authority or article content.",
            "- Use cautious language and flag points that require verification or lawyer review.",
            "- Treat output as draft work product subject to professional legal review.",
        ]

    @staticmethod
    def build_quality_guidance(*, task: str, structured_json: bool = False) -> str:
        lines = [
            f"Task: {task}",
            "- Use only the provided evidence and context.",
            "- Be concrete, specific, and outcome-oriented.",
            "- Ground each conclusion in the supplied record and, when possible, name the supporting document, clause, date, amount, or transcript cue.",
            "- Avoid generic legal boilerplate, filler intros, and vague closing lines.",
            "- Prefer bullet points, named issues, dates, amounts, and clause-level references when available.",
            "- If something is uncertain, say so plainly instead of guessing.",
        ]
        lines.extend(AgentOutputFormatter.build_legal_copilot_guardrails())
        if structured_json:
            lines.insert(1, "- Return valid JSON only.")
            lines.append("- Do not wrap the JSON in markdown fences unless explicitly requested.")
        return "\n".join(lines)