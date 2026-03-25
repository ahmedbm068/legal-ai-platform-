from fastapi import FastAPI

app = FastAPI(title="Legal AI Platform")

@app.get("/")
def root():
    return {"message": "Legal AI Platform API is running"}

@app.get("/health")
def health():
    return {"status": "ok"}