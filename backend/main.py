from __future__ import annotations

import logging
from threading import Thread
from time import perf_counter
from uuid import uuid4

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.exc import SQLAlchemyError

from backend.api import auth, cases, clients, users
from backend.api.appointments import router as appointments_router
from backend.api.calls import router as calls_router
from backend.api.client_portal import router as client_portal_router
from backend.api.consultations import router as consultations_router
from backend.api.document_router import router as document_router
from backend.api.evidence_reviews import router as evidence_reviews_router
from backend.api.integrations import router as integrations_router
from backend.api.intelligence import router as intelligence_router
from backend.api.public import router as public_router
from backend.api.prompt_library import router as prompt_library_router
from backend.api.rag import router as rag_router
from backend.api.search import router as search_router
from backend.api.voice import router as voice_router
from backend.core.config import settings
from backend.database.database import Base, engine
from backend.database.schema_sync import apply_legacy_schema_patches
from backend.models.background_job import BackgroundJob
from backend.models.case import Case
from backend.models.appointment import Appointment
from backend.models.ai_response_audit_log import AIResponseAuditLog
from backend.models.call_session import CallSession
from backend.models.case_context_snapshot import CaseContextSnapshot
from backend.models.case_image_asset import CaseImageAsset
from backend.models.case_memory_entry import CaseMemoryEntry
from backend.models.client import Client
from backend.models.client_portal_account import ClientPortalAccount
from backend.models.client_portal_login_code import ClientPortalLoginCode
from backend.models.consultation_request import ConsultationRequest
from backend.models.copilot_feedback import CopilotFeedback
from backend.models.document import Document
from backend.models.document_chunk import DocumentChunk
from backend.models.document_entity import DocumentEntity
from backend.models.evidence_analysis_review import EvidenceAnalysisReview
from backend.models.generated_artifact_version import GeneratedArtifactVersion
from backend.models.image_document_batch import ImageDocumentBatch
from backend.models.prompt_library_entry import PromptLibraryEntry
from backend.models.staff_invite import StaffInvite
from backend.models.tenant import Tenant
from backend.models.user import User
from backend.models.voice_recording import VoiceRecording
from backend.services.ai.transcription_service import transcription_service
from backend.services.jobs.job_queue_service import background_job_service

logger = logging.getLogger(__name__)

app = FastAPI(title="Legal AI Platform", version="1.0.0")

cors_origins = [origin.strip() for origin in settings.CORS_ORIGINS.split(",") if origin.strip()]
local_network_origin_regex = (
    r"^https?://("
    r"localhost|"
    r"127\.0\.0\.1|"
    r"10(?:\.\d{1,3}){3}|"
    r"172\.(?:1[6-9]|2\d|3[0-1])(?:\.\d{1,3}){2}|"
    r"192\.168(?:\.\d{1,3}){2}"
    r")(?::\d+)?$"
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins or ["*"],
    allow_origin_regex=local_network_origin_regex,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(client_portal_router)
app.include_router(users.router)
app.include_router(clients.router)
app.include_router(cases.router)
app.include_router(appointments_router)
app.include_router(calls_router)
app.include_router(consultations_router)
app.include_router(integrations_router)
app.include_router(public_router)
app.include_router(prompt_library_router)
app.include_router(document_router)
app.include_router(evidence_reviews_router)
app.include_router(rag_router)
app.include_router(intelligence_router)
app.include_router(search_router)
app.include_router(voice_router)


def initialize_database() -> None:
    try:
        Base.metadata.create_all(bind=engine)
        apply_legacy_schema_patches()
        logger.info("Database schema initialization completed.")
    except SQLAlchemyError as exc:
        logger.exception("Database schema initialization failed.")
        raise RuntimeError(
            "Database startup failed. Confirm PostgreSQL is running and DATABASE_URL is correct."
        ) from exc


@app.middleware("http")
async def add_request_id_and_timing(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID", str(uuid4()))
    started = perf_counter()
    response: Response = await call_next(request)
    duration_ms = (perf_counter() - started) * 1000.0
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Process-Time-Ms"] = f"{duration_ms:.2f}"
    return response


def _prewarm_local_transcription_pipeline() -> None:
    try:
        transcription_service._get_local_pipeline()
        logger.info("Local transcription pipeline prewarm completed.")
    except Exception as exc:
        logger.warning("Local transcription pipeline prewarm failed: %s", exc)


@app.on_event("startup")
def initialize_app_database() -> None:
    initialize_database()


@app.on_event("startup")
def maybe_prewarm_transcription() -> None:
    background_job_service.start_worker()

    if not settings.TRANSCRIPTION_PREWARM_ON_STARTUP:
        return

    should_use_local_path = (
        not settings.TRANSCRIPTION_REMOTE_ENABLED
        or transcription_service._should_skip_remote_transcription()
        or transcription_service._get_client() is None
    )
    if not should_use_local_path:
        return

    Thread(
        target=_prewarm_local_transcription_pipeline,
        daemon=True,
        name="transcription-prewarm",
    ).start()


@app.on_event("shutdown")
def stop_background_workers() -> None:
    background_job_service.stop_worker()


@app.get("/")
def root():
    return {"message": "Legal AI Platform API is running"}


@app.get("/health")
def health():
    return {"status": "ok"}
