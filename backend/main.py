from fastapi import FastAPI

from backend.database.database import Base, engine
from backend.models.user import User
from backend.models.tenant import Tenant
from backend.models.client import Client
from backend.models.case import Case
from backend.api.document_router import router as document_router
from backend.api.rag import router as rag_router

from backend.api import auth, users, clients, cases

app = FastAPI(title="Legal AI Platform")

Base.metadata.create_all(bind=engine)

app.include_router(auth.router)
app.include_router(users.router)
app.include_router(clients.router)
app.include_router(cases.router)
app.include_router(document_router)
app.include_router(rag_router)


@app.get("/")
def root():
    return {"message": "Legal AI Platform API is running"}


@app.get("/health")
def health():
    return {"status": "ok"}