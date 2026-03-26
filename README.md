# Legal AI Platform

AI-powered legal case management and analysis platform.

## Features

- Case management
- Document management
- Call transcription
- AI document classification
- Legal entity extraction
- Case outcome prediction

## Architecture

The system follows a microservice-style architecture.

Frontend → FastAPI Backend → AI Services

Infrastructure:
- PostgreSQL
- Redis
- MinIO
- Docker

## API Documentation

Run backend:

uvicorn backend.main:app --reload

Open Swagger:

http://127.0.0.1:8000/docs