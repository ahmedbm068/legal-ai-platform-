from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class AgentResult:
    agent_name: str
    success: bool
    payload: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    error: str | None = None
    trace: list[str] = field(default_factory=list)


class BaseAgent:
    agent_name = "base_agent"

    def result(
        self,
        *,
        success: bool,
        payload: dict[str, Any] | None = None,
        warnings: list[str] | None = None,
        error: str | None = None,
        trace: list[str] | None = None,
    ) -> AgentResult:
        return AgentResult(
            agent_name=self.agent_name,
            success=success,
            payload=payload or {},
            warnings=warnings or [],
            error=error,
            trace=trace or [],
        )
