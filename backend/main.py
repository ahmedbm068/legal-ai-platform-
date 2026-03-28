from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.database.database import Base, engine
from backend.core.config import settings

from backend.models.case import Case
from backend.models.client import Client
from backend.models.document import Document
from backend.models.document_chunk import DocumentChunk
from backend.models.document_entity import DocumentEntity
from backend.models.tenant import Tenant
from backend.models.user import User

from backend.api import auth, users, clients, cases
from backend.api.document_router import router as document_router
from backend.api.intelligence import router as intelligence_router
from backend.api.rag import router as rag_router
from backend.api.search import router as search_router


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

app.include_router(auth.router)
app.include_router(users.router)
app.include_router(clients.router)
app.include_router(cases.router)
app.include_router(document_router)
app.include_router(rag_router)
app.include_router(intelligence_router)
app.include_router(search_router)


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
