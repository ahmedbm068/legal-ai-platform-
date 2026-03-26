from minio import Minio
from backend.core.config import settings


client = Minio(
    settings.MINIO_ENDPOINT,
    access_key=settings.MINIO_ACCESS_KEY,
    secret_key=settings.MINIO_SECRET_KEY,
    secure=False
)

BUCKET_NAME = settings.MINIO_BUCKET


def upload_file(file_data, filename):

    if not client.bucket_exists(BUCKET_NAME):
        client.make_bucket(BUCKET_NAME)

    client.put_object(
        BUCKET_NAME,
        filename,
        file_data,
        length=-1,
        part_size=10 * 1024 * 1024
    )