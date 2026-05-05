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
    ALTER TABLE documents
    ADD COLUMN IF NOT EXISTS archived_at TIMESTAMPTZ;
    """,
    """
    ALTER TABLE voice_recordings
    ADD COLUMN IF NOT EXISTS archived_at TIMESTAMPTZ;
    """,
    """
    ALTER TABLE image_document_batches
    ADD COLUMN IF NOT EXISTS archived_at TIMESTAMPTZ;
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
    """
    ALTER TABLE IF EXISTS copilot_feedback
    ADD COLUMN IF NOT EXISTS root_cause VARCHAR;
    """,
    """
    ALTER TABLE IF EXISTS copilot_feedback
    ADD COLUMN IF NOT EXISTS legal_domain BOOLEAN;
    """,
    """
    ALTER TABLE IF EXISTS copilot_feedback
    ADD COLUMN IF NOT EXISTS jurisdiction VARCHAR;
    """,
    """
    CREATE INDEX IF NOT EXISTS ix_copilot_feedback_root_cause
    ON copilot_feedback (root_cause);
    """,
    """
    CREATE INDEX IF NOT EXISTS ix_copilot_feedback_legal_domain
    ON copilot_feedback (legal_domain);
    """,
    """
    CREATE INDEX IF NOT EXISTS ix_copilot_feedback_jurisdiction
    ON copilot_feedback (jurisdiction);
    """,
    """
    CREATE TABLE IF NOT EXISTS ai_response_audit_logs (
        id SERIAL PRIMARY KEY,
        tenant_id INTEGER NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
        user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
        case_id INTEGER REFERENCES cases(id) ON DELETE CASCADE,
        document_id INTEGER REFERENCES documents(id) ON DELETE CASCADE,
        endpoint VARCHAR NOT NULL,
        parsed_intent VARCHAR,
        response_version VARCHAR NOT NULL DEFAULT 'legal_trust_response_v1',
        model_name VARCHAR,
        prompt_version VARCHAR,
        question_text TEXT NOT NULL,
        answer_text TEXT NOT NULL,
        sources_json TEXT,
        trust_panel_json TEXT,
        validation_json TEXT,
        metadata_json TEXT,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );
    """,
    """
    CREATE INDEX IF NOT EXISTS ix_ai_response_audit_logs_tenant_created
    ON ai_response_audit_logs (tenant_id, created_at DESC);
    """,
    """
    CREATE INDEX IF NOT EXISTS ix_ai_response_audit_logs_case_created
    ON ai_response_audit_logs (case_id, created_at DESC);
    """,
    """
    CREATE INDEX IF NOT EXISTS ix_ai_response_audit_logs_intent
    ON ai_response_audit_logs (parsed_intent);
    """,
    """
    CREATE TABLE IF NOT EXISTS calendar_events (
        id SERIAL PRIMARY KEY,
        tenant_id INTEGER NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
        case_id INTEGER REFERENCES cases(id) ON DELETE CASCADE,
        client_id INTEGER REFERENCES clients(id) ON DELETE SET NULL,
        lawyer_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
        title VARCHAR NOT NULL,
        description TEXT,
        event_type VARCHAR NOT NULL DEFAULT 'other',
        status VARCHAR NOT NULL DEFAULT 'scheduled',
        priority VARCHAR NOT NULL DEFAULT 'medium',
        start_datetime TIMESTAMPTZ NOT NULL,
        end_datetime TIMESTAMPTZ,
        all_day BOOLEAN NOT NULL DEFAULT FALSE,
        timezone VARCHAR NOT NULL DEFAULT 'UTC',
        location VARCHAR,
        source_type VARCHAR NOT NULL DEFAULT 'manual',
        source_document_id INTEGER REFERENCES documents(id) ON DELETE SET NULL,
        source_chunk_id INTEGER REFERENCES document_chunks(id) ON DELETE SET NULL,
        source_quote TEXT,
        extraction_confidence DOUBLE PRECISION,
        requires_review BOOLEAN NOT NULL DEFAULT FALSE,
        reviewed_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
        reviewed_at TIMESTAMPTZ,
        created_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        deleted_at TIMESTAMPTZ
    );
    """,
    """
    CREATE INDEX IF NOT EXISTS ix_calendar_events_tenant_start
    ON calendar_events (tenant_id, start_datetime ASC);
    """,
    """
    CREATE INDEX IF NOT EXISTS ix_calendar_events_case_start
    ON calendar_events (case_id, start_datetime ASC);
    """,
    """
    CREATE INDEX IF NOT EXISTS ix_calendar_events_review
    ON calendar_events (tenant_id, requires_review, status);
    """,
    """
    CREATE INDEX IF NOT EXISTS ix_calendar_events_source_document
    ON calendar_events (source_document_id);
    """,
    """
    CREATE TABLE IF NOT EXISTS calendar_event_sources (
        id SERIAL PRIMARY KEY,
        tenant_id INTEGER NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
        event_id INTEGER NOT NULL REFERENCES calendar_events(id) ON DELETE CASCADE,
        source_type VARCHAR NOT NULL DEFAULT 'manual',
        document_id INTEGER REFERENCES documents(id) ON DELETE SET NULL,
        chunk_id INTEGER REFERENCES document_chunks(id) ON DELETE SET NULL,
        quote TEXT,
        confidence DOUBLE PRECISION,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );
    """,
    """
    CREATE INDEX IF NOT EXISTS ix_calendar_event_sources_event
    ON calendar_event_sources (event_id);
    """,
    """
    CREATE TABLE IF NOT EXISTS calendar_reminders (
        id SERIAL PRIMARY KEY,
        tenant_id INTEGER NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
        event_id INTEGER NOT NULL REFERENCES calendar_events(id) ON DELETE CASCADE,
        remind_at TIMESTAMPTZ NOT NULL,
        method VARCHAR NOT NULL DEFAULT 'in_app',
        status VARCHAR NOT NULL DEFAULT 'pending',
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );
    """,
    """
    CREATE INDEX IF NOT EXISTS ix_calendar_reminders_due
    ON calendar_reminders (tenant_id, status, remind_at ASC);
    """,
    """
    CREATE TABLE IF NOT EXISTS calendar_event_attendees (
        id SERIAL PRIMARY KEY,
        tenant_id INTEGER NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
        event_id INTEGER NOT NULL REFERENCES calendar_events(id) ON DELETE CASCADE,
        user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
        email VARCHAR,
        name VARCHAR,
        role VARCHAR NOT NULL DEFAULT 'attendee',
        response_status VARCHAR NOT NULL DEFAULT 'needs_action',
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );
    """,
    """
    CREATE INDEX IF NOT EXISTS ix_calendar_event_attendees_event
    ON calendar_event_attendees (event_id);
    """,
    """
    CREATE TABLE IF NOT EXISTS calendar_sync_providers (
        id SERIAL PRIMARY KEY,
        tenant_id INTEGER NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
        lawyer_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
        provider VARCHAR NOT NULL,
        external_calendar_id VARCHAR,
        status VARCHAR NOT NULL DEFAULT 'disabled',
        webhook_url TEXT,
        n8n_workflow_hint VARCHAR,
        is_enabled BOOLEAN NOT NULL DEFAULT FALSE,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );
    """,
    """
    CREATE INDEX IF NOT EXISTS ix_calendar_sync_providers_tenant_lawyer
    ON calendar_sync_providers (tenant_id, lawyer_id);
    """,
    """
    CREATE TABLE IF NOT EXISTS draft_documents (
        id SERIAL PRIMARY KEY,
        tenant_id INTEGER NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
        case_id INTEGER REFERENCES cases(id) ON DELETE SET NULL,
        created_by_user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
        title VARCHAR NOT NULL,
        document_type VARCHAR NOT NULL DEFAULT 'general',
        content_json TEXT NOT NULL DEFAULT '{}',
        content_html TEXT NOT NULL DEFAULT '',
        content_text TEXT NOT NULL DEFAULT '',
        status VARCHAR NOT NULL DEFAULT 'draft',
        source_context_json TEXT,
        citations_json TEXT,
        version INTEGER NOT NULL DEFAULT 1,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        deleted_at TIMESTAMPTZ
    );
    """,
    """
    CREATE INDEX IF NOT EXISTS ix_draft_documents_tenant_updated
    ON draft_documents (tenant_id, updated_at DESC);
    """,
    """
    CREATE INDEX IF NOT EXISTS ix_draft_documents_case_updated
    ON draft_documents (case_id, updated_at DESC);
    """,
    """
    CREATE TABLE IF NOT EXISTS draft_document_versions (
        id SERIAL PRIMARY KEY,
        draft_document_id INTEGER NOT NULL REFERENCES draft_documents(id) ON DELETE CASCADE,
        version_number INTEGER NOT NULL,
        content_json TEXT NOT NULL DEFAULT '{}',
        content_html TEXT NOT NULL DEFAULT '',
        content_text TEXT NOT NULL DEFAULT '',
        created_by_user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
        change_summary TEXT,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );
    """,
    """
    CREATE INDEX IF NOT EXISTS ix_draft_document_versions_document_version
    ON draft_document_versions (draft_document_id, version_number DESC);
    """,
    # ── Week 1: general request audit log ──────────────────────────────────
    """
    DO $$
    BEGIN
        IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'userrole')
        THEN
            CREATE TYPE userrole AS ENUM ('admin', 'lawyer', 'client', 'assistant');
        ELSE
            BEGIN
                ALTER TYPE userrole ADD VALUE IF NOT EXISTS 'client';
            EXCEPTION WHEN others THEN NULL;
            END;
        END IF;
    END$$;
    """,
    """
    CREATE TABLE IF NOT EXISTS request_audit_logs (
        id          SERIAL PRIMARY KEY,
        tenant_id   INTEGER,
        user_id     INTEGER,
        method      VARCHAR(10)  NOT NULL,
        path        VARCHAR(512) NOT NULL,
        status_code INTEGER      NOT NULL,
        duration_ms DOUBLE PRECISION NOT NULL,
        created_at  TIMESTAMPTZ  NOT NULL DEFAULT NOW()
    );
    """,
    """
    CREATE INDEX IF NOT EXISTS ix_request_audit_logs_created
    ON request_audit_logs (created_at DESC);
    """,
    """
    CREATE INDEX IF NOT EXISTS ix_request_audit_logs_tenant
    ON request_audit_logs (tenant_id, created_at DESC);
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
