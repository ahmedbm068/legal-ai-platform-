"""Review Big Agent — Harvey "Vault" equivalent.

Bulk and per-document review: classification, clause extraction,
deadline/obligation detection, contradiction flagging, comparison.
"""

from __future__ import annotations

from .base import BigAgent, big_agent_registry


review_agent = BigAgent(
    name="review_agent",
    tier="core",
    description=(
        "Reviews documents at scale: classifies, extracts key clauses, "
        "flags deadlines and obligations, detects contradictions across "
        "the matter, and produces a per-document risk matrix."
    ),
    mini_agents_used=(
        "matter_classification_agent",
        "deadline_obligation_agent",
        "contradiction_detection_agent",
        "evidence_strength_agent",
        "document_comparison_agent",
        "vision_analysis_agent",
        "summarization_agent",
    ),
    intents_handled=(
        "summarize_document",
        "compare_case_documents",
        "trace_case_evidence",
        "review_booking_case",
    ),
    delegates_to=(
        "backend.services.ai.document_ai_pipeline",
        "backend.services.ai.document_insight_service",
        "backend.services.ai.scanned_document_service",
    ),
    ui_route="/cases/{case_id}/review-table",
    harvey_equivalent="Vault",
    legora_equivalent="Review",
)

big_agent_registry.register(review_agent)
