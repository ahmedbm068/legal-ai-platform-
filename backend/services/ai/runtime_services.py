from __future__ import annotations

from backend.services.ai.agent_workflow_service import AgentWorkflowService
from backend.services.ai.copilot_service import CopilotService
from backend.services.ai.document_ai_pipeline import DocumentAIPipeline
from backend.services.ai.embedding_service import embedding_service
from backend.services.ai.rag_service import RagService
from backend.services.ai.runtime_copilot_orchestrator import RuntimeCopilotOrchestrator
from backend.services.ai.vector_store import VectorStore

shared_vector_store = VectorStore(dimension=embedding_service.dimension)
rag_service = RagService(vector_store=shared_vector_store, embedding_service=embedding_service)
shared_document_pipeline = DocumentAIPipeline(
    embedding_service=embedding_service,
    vector_store=shared_vector_store,
)
copilot_service = CopilotService(
    rag_service=rag_service,
    document_pipeline=shared_document_pipeline,
)
copilot_orchestration_service = RuntimeCopilotOrchestrator(
    copilot_service=copilot_service,
)
agent_workflow_service = AgentWorkflowService(rag_service=rag_service)

__all__ = [
    "agent_workflow_service",
    "copilot_orchestration_service",
    "copilot_service",
    "rag_service",
    "shared_document_pipeline",
    "shared_vector_store",
]
