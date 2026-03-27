from __future__ import annotations

import os
import tempfile
import uuid

from minio import Minio

from backend.core.config import settings


client = Minio(
    settings.MINIO_ENDPOINT,
    access_key=settings.MINIO_ACCESS_KEY,
    secret_key=settings.MINIO_SECRET_KEY,
    secure=False
)

BUCKET_NAME = settings.MINIO_BUCKET


def ensure_bucket_exists() -> None:
    if not client.bucket_exists(BUCKET_NAME):
        client.make_bucket(BUCKET_NAME)


def upload_file(file_data, filename: str) -> str:
    ensure_bucket_exists()

    object_name = f"documents/{uuid.uuid4()}_{filename}"

    client.put_object(
        BUCKET_NAME,
        object_name,
        file_data,
        length=-1,
        part_size=10 * 1024 * 1024
    )

    return object_name


def download_file_to_temp(object_name: str) -> str:
    ensure_bucket_exists()

    suffix = os.path.splitext(object_name)[1] or ".pdf"

    temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    temp_file.close()

    client.fget_object(BUCKET_NAME, object_name, temp_file.name)

    return temp_file.name