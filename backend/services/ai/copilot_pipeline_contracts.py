from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class PipelineStageStatus(str, Enum):
    success = "success"
    failed = "failed"
    skipped = "skipped"


class PipelineStageRecord(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    name: str
    status: PipelineStageStatus
    detail: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class CopilotPipelineRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    message: str
    top_k: int = 5
    use_external_research: bool = True
    mode: str = "default"
    legal_search_multilingual_output: bool = False
    legal_search_code_scope: list[str] = Field(default_factory=list)
    reasoning_level: str = "medium"
    agent_mode: bool = False
    workspace_case_id: int | None = None
    workspace_document_id: int | None = None
    attachments_count: int = 0
    save_attachments_to_case: bool = False
    attachment_case_id: int | None = None


class CopilotExecutionContext(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    corrected_message: str
    optimized_message: str | None = None
    parsed_intent: str = "ask_global"
    target_type: str | None = None
    target_id: int | None = None
    planned_matter_type: str | None = None
    planned_workflow: str | None = None
    planned_output_format: str | None = None
    requested_user_goal: str | None = None
