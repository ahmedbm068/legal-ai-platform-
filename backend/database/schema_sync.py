from __future__ import annotations

from sqlalchemy import text

from backend.database.database import engine


LEGACY_SCHEMA_PATCHES = [
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
    ADD COLUMN IF NOT EXISTS uploaded_by_user_id INTEGER;
    """,
]


def apply_legacy_schema_patches() -> None:
    with engine.begin() as connection:
        for statement in LEGACY_SCHEMA_PATCHES:
            connection.execute(text(statement))
