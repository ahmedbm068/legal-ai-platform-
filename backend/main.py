from fastapi import FastAPI
from backend.database.database import Base, engine
from backend.api import users

app = FastAPI(title="Legal AI Platform")

Base.metadata.create_all(bind=engine)

app.include_router(users.router)

@app.get("/")
def root():
    return {"message": "Legal AI Platform API is running"}

@app.get("/health")
def health():
    return {"status": "ok"}