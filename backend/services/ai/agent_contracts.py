from __future__ import annotations

import json
import re
from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError


ModelT = TypeVar("ModelT", bound=BaseModel)


def extract_json_object(raw_text: str) -> dict[str, Any] | None:
    candidate = str(raw_text or "").strip()
    if not candidate:
        return None

    if candidate.startswith("```"):
        fenced_match = re.search(r"```(?:json)?\s*(\{[\s\S]*\})\s*```", candidate, flags=re.IGNORECASE)
        if fenced_match:
            candidate = fenced_match.group(1).strip()

    try:
        payload = json.loads(candidate)
        return payload if isinstance(payload, dict) else None
    except json.JSONDecodeError:
        start = candidate.find("{")
        end = candidate.rfind("}")
        if start < 0 or end <= start:
            return None
        try:
            payload = json.loads(candidate[start : end + 1])
            return payload if isinstance(payload, dict) else None
        except json.JSONDecodeError:
            return None


def validate_json_model(raw_text: str, model_cls: type[ModelT]) -> ModelT | None:
    payload = extract_json_object(raw_text)
    if payload is None:
        return None

    try:
        return model_cls.model_validate(payload)
    except ValidationError:
        return None

