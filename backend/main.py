from __future__ import annotations

import logging
from threading import Thread
from time import perf_counter
from uuid import uuid4

from fastapi import FastAPI
from fastapi import Request
from fastapi import Response
from fastapi.middleware.cors import CORSMiddleware

from backend.database.database import Base, engine
from backend.database.schema_sync import apply_legacy_schema_patches
from backend.core.config import settings

from backend.models.case import Case
from backend.models.client import Client
from backend.models.client_portal_account import ClientPortalAccount
from backend.models.client_portal_login_code import ClientPortalLoginCode
from backend.models.document import Document
from backend.models.document_chunk import DocumentChunk
from backend.models.document_entity import DocumentEntity
from backend.models.generated_artifact_version import GeneratedArtifactVersion
from backend.models.tenant import Tenant
from backend.models.user import User
from backend.models.voice_recording import VoiceRecording
from backend.models.consultation_request import ConsultationRequest

from backend.api import auth, users, clients, cases
from backend.api.client_portal import router as client_portal_router
from backend.api.consultations import router as consultations_router
from backend.api.document_router import router as document_router
from backend.api.intelligence import router as intelligence_router
from backend.api.public import router as public_router
from backend.api.rag import router as rag_router
from backend.api.search import router as search_router
from backend.api.voice import router as voice_router
from backend.services.ai.transcription_service import transcription_service


logger = logging.getLogger(__name__)


app = FastAPI(
    title="Legal AI Platform",
    version="1.0.0"
)

cors_origins = [
    origin.strip()
    for origin in settings.CORS_ORIGINS.split(",")
    if origin.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins or ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

Base.metadata.create_all(bind=engine)
apply_legacy_schema_patches()

app.include_router(auth.router)
app.include_router(client_portal_router)
app.include_router(users.router)
app.include_router(clients.router)
app.include_router(cases.router)
app.include_router(consultations_router)
app.include_router(public_router)
app.include_router(document_router)
app.include_router(rag_router)
app.include_router(intelligence_router)
app.include_router(search_router)
app.include_router(voice_router)


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
def maybe_prewarm_transcription() -> None:
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


@app.get("/")
def root():
    return {
        "message": "Legal AI Platform API is running"
    }


@app.get("/health")
def health():
    return {
        "status": "ok"
    }
