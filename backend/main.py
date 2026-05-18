from __future__ import annotations

import logging
import os
from threading import Thread
from time import perf_counter
from uuid import uuid4

from backend.core.logging_config import configure_logging

configure_logging(level=os.getenv("LOG_LEVEL", "INFO"))

from fastapi import FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from sqlalchemy.exc import SQLAlchemyError
from starlette.exceptions import HTTPException as StarletteHTTPException

from backend.api import auth, billing, case_messages, cases, clients, users
from backend.api import messages_ws
from backend.api.admin import router as admin_router
from backend.api.assistant import router as assistant_router
from backend.api.appointments import router as appointments_router
from backend.api.calendar_events import router as legal_calendar_router
from backend.api.calls import router as calls_router
from backend.api.client_portal import router as client_portal_router
from backend.api.consultations import router as consultations_router
from backend.api.document_router import router as document_router
from backend.api.draft_documents import router as draft_documents_router
from backend.api.evidence_reviews import router as evidence_reviews_router
from backend.api.integrations import router as integrations_router
from backend.api.intelligence import router as intelligence_router
from backend.api.public import router as public_router
from backend.api.prompt_library import router as prompt_library_router
from backend.api.rag import router as rag_router
from backend.api.search import router as search_router
from backend.api.succession import router as succession_router
from backend.api.voice import router as voice_router
from backend.core.config import settings
from backend.core.rate_limiter import limiter
from backend.database.database import Base, engine
from backend.database.schema_sync import apply_legacy_schema_patches
from backend.models.background_job import BackgroundJob
from backend.models.case import Case
from backend.models.appointment import Appointment
from backend.models.ai_response_audit_log import AIResponseAuditLog
from backend.models.call_session import CallSession
from backend.models.calendar_event import CalendarEvent
from backend.models.calendar_event_attendee import CalendarEventAttendee
from backend.models.calendar_event_source import CalendarEventSource
from backend.models.calendar_reminder import CalendarReminder
from backend.models.calendar_sync_provider import CalendarSyncProvider
from backend.models.case_context_snapshot import CaseContextSnapshot
from backend.models.copilot_trace import CopilotTrace
from backend.models.case_image_asset import CaseImageAsset
from backend.models.case_memory_entry import CaseMemoryEntry
from backend.models.client import Client
from backend.models.client_portal_account import ClientPortalAccount
from backend.models.client_portal_login_code import ClientPortalLoginCode
from backend.models.case_message import CaseMessage
from backend.models.invoice import Invoice, InvoiceLineItem
from backend.models.consultation_request import ConsultationRequest
from backend.models.copilot_feedback import CopilotFeedback
from backend.models.document import Document
from backend.models.document_chunk import DocumentChunk
from backend.models.document_entity import DocumentEntity
from backend.models.draft_document import DraftDocument
from backend.models.draft_document_version import DraftDocumentVersion
from backend.models.evidence_analysis_review import EvidenceAnalysisReview
from backend.models.generated_artifact_version import GeneratedArtifactVersion
from backend.models.image_document_batch import ImageDocumentBatch
from backend.models.prompt_library_entry import PromptLibraryEntry
from backend.models.llm_call_log import LLMCallLog
from backend.models.request_audit_log import RequestAuditLog
from backend.models.staff_invite import StaffInvite
from backend.models.tenant import Tenant
from backend.models.user import User
from backend.models.voice_recording import VoiceRecording
from backend.services.ai.transcription_service import transcription_service
from backend.services.jobs.job_queue_service import background_job_service

logger = logging.getLogger(__name__)

app = FastAPI(title="Legal AI Platform", version="1.0.0")

# ── Rate limiter ──────────────────────────────────────────────────────────────
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


# ── RFC 7807 problem+json error envelopes ────────────────────────────────────

def _problem(status_code: int, title: str, detail: str, instance: str = "") -> JSONResponse:
    body = {
        "type": f"https://legal-ai.local/errors/{status_code}",
        "title": title,
        "status": status_code,
        "detail": detail,
    }
    if instance:
        body["instance"] = instance
    return JSONResponse(
        status_code=status_code,
        content=body,
        media_type="application/problem+json",
    )


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    titles = {
        400: "Bad Request",
        401: "Unauthorized",
        403: "Forbidden",
        404: "Not Found",
        405: "Method Not Allowed",
        409: "Conflict",
        422: "Unprocessable Entity",
        429: "Too Many Requests",
        500: "Internal Server Error",
    }
    title = titles.get(exc.status_code, "Error")
    detail = exc.detail if isinstance(exc.detail, str) else str(exc.detail)
    return _problem(exc.status_code, title, detail, str(request.url.path))


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    errors = exc.errors()
    detail = "; ".join(
        f"{' → '.join(str(l) for l in e['loc'])}: {e['msg']}" for e in errors
    )
    return _problem(422, "Validation Error", detail, str(request.url.path))


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled exception on %s %s", request.method, request.url.path)
    return _problem(500, "Internal Server Error", "An unexpected error occurred.", str(request.url.path))

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
app.include_router(case_messages.router)
app.include_router(billing.router)
app.include_router(appointments_router)
app.include_router(legal_calendar_router)
app.include_router(calls_router)
app.include_router(consultations_router)
app.include_router(integrations_router)
app.include_router(public_router)
app.include_router(prompt_library_router)
app.include_router(document_router)
app.include_router(draft_documents_router)
app.include_router(assistant_router)
app.include_router(evidence_reviews_router)
app.include_router(rag_router)
app.include_router(intelligence_router)
app.include_router(search_router)
app.include_router(succession_router)
app.include_router(voice_router)
app.include_router(admin_router)
app.include_router(messages_ws.router)


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

    # ── Request audit log (mutating methods only) ─────────────────────────
    if request.method in ("POST", "PUT", "PATCH", "DELETE"):
        try:
            from backend.database.database import SessionLocal
            from backend.core.jwt_handler import decode_access_token

            tenant_id: int | None = None
            user_id: int | None = None
            auth_header = request.headers.get("Authorization", "")
            if auth_header.startswith("Bearer "):
                try:
                    payload = decode_access_token(auth_header[7:])
                    user_id = int(payload.get("sub", 0)) or None
                    tenant_id = int(payload.get("tenant_id", 0)) or None
                except Exception:
                    pass

            db = SessionLocal()
            try:
                entry = RequestAuditLog(
                    tenant_id=tenant_id,
                    user_id=user_id,
                    method=request.method,
                    path=str(request.url.path),
                    status_code=response.status_code,
                    duration_ms=duration_ms,
                )
                db.add(entry)
                db.commit()
            finally:
                db.close()
        except Exception as _audit_exc:
            logger.warning("Audit log write failed: %s", _audit_exc)

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
async def capture_ws_event_loop() -> None:
    import asyncio

    from backend.core.ws_manager import room_manager

    room_manager.set_loop(asyncio.get_running_loop())


@app.on_event("startup")
def validate_prompt_integrity() -> None:
    from backend.core.prompt_lock import validate_prompt_lock
    validate_prompt_lock()


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


# Per-namespace log levels. Root level + JSON-vs-console formatting are set
# by `configure_logging()` at the top of this file (driven by LOG_LEVEL and
# LOG_FORMAT env vars). The lines below only override module verbosity.
for _name in (
    "copilot.graph",
    "copilot.retrieval",
    "copilot.drafting",
    "copilot.legal_search",
    "copilot.response",
    "copilot",
    "backend.services.ai.copilot_service",
):
    logging.getLogger(_name).setLevel(logging.DEBUG)