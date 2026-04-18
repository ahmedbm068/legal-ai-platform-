from __future__ import annotations

import logging

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from backend.database.database import engine


logger = logging.getLogger(__name__)


BASE_SCHEMA_PATCHES = [
    """
    ALTER TABLE cases
    ADD COLUMN IF NOT EXISTS jurisdiction_country VARCHAR NOT NULL DEFAULT 'tunisia';
    """,
    """
    ALTER TABLE tenants
    ADD COLUMN IF NOT EXISTS slug VARCHAR;
    """,
    """
    ALTER TABLE tenants
    ADD COLUMN IF NOT EXISTS portal_access_enabled BOOLEAN NOT NULL DEFAULT TRUE;
    """,
    """
    ALTER TABLE users
    ADD COLUMN IF NOT EXISTS phone VARCHAR;
    """,
    """
    CREATE UNIQUE INDEX IF NOT EXISTS ix_tenants_slug_unique
    ON tenants (slug)
    WHERE slug IS NOT NULL;
    """,
    """
    ALTER TABLE consultation_requests
    ADD COLUMN IF NOT EXISTS public_reference VARCHAR;
    """,
    """
    ALTER TABLE consultation_requests
    ADD COLUMN IF NOT EXISTS source_channel VARCHAR NOT NULL DEFAULT 'internal';
    """,
    """
    ALTER TABLE voice_recordings
    ADD COLUMN IF NOT EXISTS transcript_source VARCHAR;
    """,
    """
    ALTER TABLE voice_recordings
    ADD COLUMN IF NOT EXISTS transcript_language VARCHAR;
    """,
    """
    ALTER TABLE voice_recordings
    ADD COLUMN IF NOT EXISTS conversation_transcript_text TEXT;
    """,
    """
    ALTER TABLE voice_recordings
    ADD COLUMN IF NOT EXISTS recording_kind VARCHAR NOT NULL DEFAULT 'voice_note';
    """,
    """
    ALTER TABLE voice_recordings
    ADD COLUMN IF NOT EXISTS call_session_id INTEGER;
    """,
    """
    CREATE INDEX IF NOT EXISTS ix_voice_recordings_call_session_id
    ON voice_recordings (call_session_id);
    """,
    """
    ALTER TABLE voice_recordings
    ADD COLUMN IF NOT EXISTS uploaded_by_user_id INTEGER;
    """,
    """
    ALTER TABLE client_portal_accounts
    ADD COLUMN IF NOT EXISTS phone VARCHAR;
    """,
    """
    ALTER TABLE client_portal_accounts
    ADD COLUMN IF NOT EXISTS address VARCHAR;
    """,
    """
    ALTER TABLE client_portal_accounts
    ADD COLUMN IF NOT EXISTS requires_email_verification BOOLEAN NOT NULL DEFAULT TRUE;
    """,
    """
    ALTER TABLE client_portal_accounts
    ADD COLUMN IF NOT EXISTS verified_at TIMESTAMPTZ;
    """,
    """
    ALTER TABLE client_portal_accounts
    ADD COLUMN IF NOT EXISTS last_login_at TIMESTAMPTZ;
    """,
    """
    CREATE INDEX IF NOT EXISTS ix_document_chunks_content_tsv
    ON document_chunks
    USING GIN (to_tsvector('simple', COALESCE(content, '')));
    """,
    """
    ALTER TABLE documents
    ADD COLUMN IF NOT EXISTS source_image_batch_id INTEGER;
    """,
    """
    CREATE INDEX IF NOT EXISTS ix_documents_source_image_batch_id
    ON documents (source_image_batch_id);
    """,
    """
    CREATE INDEX IF NOT EXISTS ix_case_image_assets_case_created
    ON case_image_assets (case_id, created_at DESC);
    """,
    """
    CREATE INDEX IF NOT EXISTS ix_image_document_batches_case_created
    ON image_document_batches (case_id, created_at DESC);
    """,
    """
    CREATE TABLE IF NOT EXISTS call_sessions (
        id SERIAL PRIMARY KEY,
        case_id INTEGER NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
        tenant_id INTEGER NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
        client_id INTEGER NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
        started_by_user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
        provider_name VARCHAR,
        provider_call_id VARCHAR,
        caller_phone VARCHAR,
        client_phone VARCHAR,
        call_status VARCHAR NOT NULL DEFAULT 'planned',
        recording_status VARCHAR NOT NULL DEFAULT 'waiting_for_audio',
        summary_status VARCHAR NOT NULL DEFAULT 'pending',
        consent_accepted BOOLEAN NOT NULL DEFAULT FALSE,
        consent_accepted_at TIMESTAMPTZ,
        consent_request_status VARCHAR NOT NULL DEFAULT 'not_requested',
        consent_requested_at TIMESTAMPTZ,
        consent_message TEXT,
        consent_response_text TEXT,
        consent_responded_at TIMESTAMPTZ,
        started_at TIMESTAMPTZ,
        ended_at TIMESTAMPTZ,
        duration_seconds INTEGER,
        summary_text TEXT,
        transcript_text TEXT,
        conversation_transcript_text TEXT,
        transcript_source VARCHAR,
        transcription_error TEXT,
        notes TEXT,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );
    """,
    """
    ALTER TABLE call_sessions
    ADD COLUMN IF NOT EXISTS caller_phone VARCHAR;
    """,
    """
    ALTER TABLE call_sessions
    ADD COLUMN IF NOT EXISTS consent_request_status VARCHAR NOT NULL DEFAULT 'not_requested';
    """,
    """
    ALTER TABLE call_sessions
    ADD COLUMN IF NOT EXISTS consent_requested_at TIMESTAMPTZ;
    """,
    """
    ALTER TABLE call_sessions
    ADD COLUMN IF NOT EXISTS consent_message TEXT;
    """,
    """
    ALTER TABLE call_sessions
    ADD COLUMN IF NOT EXISTS consent_response_text TEXT;
    """,
    """
    ALTER TABLE call_sessions
    ADD COLUMN IF NOT EXISTS consent_responded_at TIMESTAMPTZ;
    """,
    """
    ALTER TABLE call_sessions
    ADD COLUMN IF NOT EXISTS conversation_transcript_text TEXT;
    """,
    """
    CREATE INDEX IF NOT EXISTS ix_call_sessions_case_created
    ON call_sessions (case_id, created_at DESC);
    """,
    """
    CREATE INDEX IF NOT EXISTS ix_call_sessions_tenant_created
    ON call_sessions (tenant_id, created_at DESC);
    """,
    """
    CREATE TABLE IF NOT EXISTS appointments (
        id SERIAL PRIMARY KEY,
        case_id INTEGER NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
        tenant_id INTEGER NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
        lawyer_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
        client_id INTEGER REFERENCES clients(id) ON DELETE SET NULL,
        consultation_request_id INTEGER REFERENCES consultation_requests(id) ON DELETE SET NULL,
        created_by_user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
        title VARCHAR NOT NULL,
        description TEXT,
        appointment_type VARCHAR NOT NULL DEFAULT 'meeting',
        visibility_scope VARCHAR NOT NULL DEFAULT 'shared',
        status VARCHAR NOT NULL DEFAULT 'scheduled',
        scheduled_at TIMESTAMPTZ NOT NULL,
        duration_minutes INTEGER NOT NULL DEFAULT 30,
        location VARCHAR,
        timezone_name VARCHAR NOT NULL DEFAULT 'UTC',
        ai_summary TEXT,
        ai_recommendation TEXT,
        ai_confidence VARCHAR,
        ai_source VARCHAR,
        notes TEXT,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );
    """,
    """
    CREATE INDEX IF NOT EXISTS ix_appointments_case_scheduled_at
    ON appointments (case_id, scheduled_at ASC);
    """,
    """
    CREATE INDEX IF NOT EXISTS ix_appointments_tenant_scheduled_at
    ON appointments (tenant_id, scheduled_at ASC);
    """,
    """
    CREATE INDEX IF NOT EXISTS ix_appointments_lawyer_scheduled_at
    ON appointments (lawyer_id, scheduled_at ASC);
    """,
    """
    CREATE INDEX IF NOT EXISTS ix_evidence_analysis_reviews_case_status
    ON evidence_analysis_reviews (case_id, status, created_at DESC);
    """,
    """
    CREATE TABLE IF NOT EXISTS prompt_library_entries (
        id SERIAL PRIMARY KEY,
        tenant_id INTEGER NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
        created_by_user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
        title VARCHAR NOT NULL,
        prompt_text TEXT NOT NULL,
        description TEXT,
        category VARCHAR,
        is_favorite BOOLEAN NOT NULL DEFAULT FALSE,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );
    """,
    """
    CREATE INDEX IF NOT EXISTS ix_prompt_library_entries_tenant_category
    ON prompt_library_entries (tenant_id, category, updated_at DESC);
    """,
]

VECTOR_SCHEMA_PATCHES = [
    """
    CREATE TABLE IF NOT EXISTS document_chunk_embeddings (
        chunk_id INTEGER PRIMARY KEY REFERENCES document_chunks(id) ON DELETE CASCADE,
        document_id INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
        case_id INTEGER REFERENCES cases(id) ON DELETE CASCADE,
        tenant_id INTEGER REFERENCES tenants(id) ON DELETE CASCADE,
        filename VARCHAR,
        chunk_index INTEGER,
        chunk_text TEXT,
        embedding vector(384),
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );
    """,
    """
    CREATE INDEX IF NOT EXISTS ix_document_chunk_embeddings_tenant_case_document
    ON document_chunk_embeddings (tenant_id, case_id, document_id);
    """,
]


def _enable_pgvector_extension(connection) -> bool:
    try:
        if engine.dialect.name != "postgresql":
            return False

        extension_available = connection.execute(
            text("SELECT EXISTS (SELECT 1 FROM pg_available_extensions WHERE name = 'vector')")
        ).scalar()
        if not bool(extension_available):
            logger.info(
                "pgvector is not installed in this PostgreSQL instance. "
                "Using FAISS fallback and skipping vector DDL."
            )
            return False

        connection.execute(text("CREATE EXTENSION IF NOT EXISTS vector;"))
        return True
    except SQLAlchemyError as exc:
        logger.warning(
            "pgvector extension is unavailable in the current PostgreSQL instance. "
            "Continuing with FAISS fallback and skipping vector DDL."
        )
        logger.debug("pgvector extension enablement failed with: %s", exc)
        return False


def apply_legacy_schema_patches() -> None:
    with engine.begin() as connection:
        for statement in BASE_SCHEMA_PATCHES:
            connection.execute(text(statement))

    with engine.begin() as connection:
        if _enable_pgvector_extension(connection):
            for statement in VECTOR_SCHEMA_PATCHES:
                connection.execute(text(statement))
