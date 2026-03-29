from __future__ import annotations

import logging
import os
import re
import tempfile
from threading import RLock
import uuid

from minio import Minio
from minio.error import S3Error

from backend.core.config import settings

logger = logging.getLogger(__name__)

client = Minio(
    settings.MINIO_ENDPOINT,
    access_key=settings.MINIO_ACCESS_KEY,
    secret_key=settings.MINIO_SECRET_KEY,
    secure=settings.MINIO_SECURE
)

BUCKET_NAME = settings.MINIO_BUCKET
_BUCKET_READY = False
_BUCKET_LOCK = RLock()


def _sanitize_filename(filename: str) -> str:
    base_filename = os.path.basename((filename or "").strip())
    if not base_filename:
        raise ValueError("Filename is required.")

    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", base_filename).strip("._")
    if not cleaned:
        cleaned = f"file_{uuid.uuid4().hex[:8]}"

    return cleaned[:180]


def _sanitize_prefix(prefix: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9/_-]+", "_", (prefix or "documents").strip())
    cleaned = cleaned.replace("\\", "/").strip("/")
    cleaned = re.sub(r"/{2,}", "/", cleaned)
    return cleaned or "documents"


def ensure_bucket_exists() -> None:
    global _BUCKET_READY

    if _BUCKET_READY:
        return

    with _BUCKET_LOCK:
        if _BUCKET_READY:
            return

        try:
            if not client.bucket_exists(BUCKET_NAME):
                client.make_bucket(BUCKET_NAME)
        except S3Error as exc:
            raise RuntimeError(f"Storage bucket check failed for '{BUCKET_NAME}': {exc}") from exc

        _BUCKET_READY = True


def upload_file(file_data, filename: str, prefix: str = "documents") -> str:
    ensure_bucket_exists()

    safe_prefix = _sanitize_prefix(prefix)
    safe_filename = _sanitize_filename(filename)
    object_name = f"{safe_prefix}/{uuid.uuid4().hex}_{safe_filename}"

    try:
        client.put_object(
            BUCKET_NAME,
            object_name,
            file_data,
            length=-1,
            part_size=10 * 1024 * 1024
        )
    except S3Error as exc:
        logger.exception("Failed to upload object '%s' to bucket '%s'.", object_name, BUCKET_NAME)
        raise RuntimeError(f"Failed to upload file to object storage: {exc}") from exc

    return object_name


def download_file_to_temp(object_name: str) -> str:
    ensure_bucket_exists()

    normalized_object_name = (object_name or "").replace("\\", "/").strip().lstrip("/")
    if not normalized_object_name:
        raise ValueError("Storage object path is required.")

    suffix = os.path.splitext(os.path.basename(normalized_object_name))[1] or ".bin"

    temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    temp_file.close()

    try:
        client.fget_object(BUCKET_NAME, normalized_object_name, temp_file.name)
    except S3Error as exc:
        try:
            os.remove(temp_file.name)
        except OSError:
            pass
        logger.exception("Failed to download object '%s' from bucket '%s'.", normalized_object_name, BUCKET_NAME)
        raise RuntimeError(f"Failed to download file from object storage: {exc}") from exc

    return temp_file.name
