from __future__ import annotations

import json
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from fastapi import BackgroundTasks
from sqlalchemy.orm import Session

from backend.core.config import settings
from backend.models.background_job import BackgroundJob


_job_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="legal-ai-job")


class BackgroundJobService:
    DEFAULT_QUEUE = "default"
    ALL_QUEUES = ("default", "documents", "voice", "snapshots", "images")

    def __init__(self) -> None:
        self._client = None
        self._client_checked = False
        self._worker_thread: threading.Thread | None = None
        self._stop_event = threading.Event()

    def _get_client(self):
        if self._client_checked:
            return self._client

        self._client_checked = True
        try:
            import redis  # type: ignore

            client = redis.Redis.from_url(settings.REDIS_URL, decode_responses=True)
            client.ping()
            self._client = client
        except Exception:
            self._client = None
        return self._client

    @property
    def redis_available(self) -> bool:
        return self._get_client() is not None

    @staticmethod
    def queue_key(queue_name: str) -> str:
        normalized = str(queue_name or BackgroundJobService.DEFAULT_QUEUE).strip().lower() or BackgroundJobService.DEFAULT_QUEUE
        return f"legal-ai:jobs:{normalized}"

    def enqueue(
        self,
        *,
        db: Session,
        job_type: str,
        payload: dict[str, Any],
        tenant_id: int | None = None,
        case_id: int | None = None,
        document_id: int | None = None,
        voice_recording_id: int | None = None,
        consultation_request_id: int | None = None,
        queue_name: str = DEFAULT_QUEUE,
        background_tasks: BackgroundTasks | None = None,
    ) -> BackgroundJob:
        job = BackgroundJob(
            tenant_id=tenant_id,
            case_id=case_id,
            document_id=document_id,
            voice_recording_id=voice_recording_id,
            consultation_request_id=consultation_request_id,
            job_type=job_type,
            queue_name=queue_name or self.DEFAULT_QUEUE,
            status="queued",
            payload_json=json.dumps(payload or {}, ensure_ascii=False),
        )
        db.add(job)
        db.commit()
        db.refresh(job)

        if not self._push_to_redis(job):
            if background_tasks is not None:
                background_tasks.add_task(run_background_job, job.id)
            else:
                _job_executor.submit(run_background_job, job.id)

        return job

    def get_job(self, *, db: Session, job_id: str) -> BackgroundJob | None:
        return db.query(BackgroundJob).filter(BackgroundJob.id == job_id).first()

    @staticmethod
    def to_public_payload(job: BackgroundJob | None) -> dict[str, Any] | None:
        if job is None:
            return None
        return {
            "id": job.id,
            "job_type": job.job_type,
            "queue_name": job.queue_name,
            "status": job.status,
            "tenant_id": job.tenant_id,
            "case_id": job.case_id,
            "document_id": job.document_id,
            "voice_recording_id": job.voice_recording_id,
            "consultation_request_id": job.consultation_request_id,
            "attempts": job.attempts,
            "max_attempts": job.max_attempts,
            "error": job.error,
            "created_at": job.created_at.isoformat() if job.created_at else None,
            "started_at": job.started_at.isoformat() if job.started_at else None,
            "completed_at": job.completed_at.isoformat() if job.completed_at else None,
        }

    def _push_to_redis(self, job: BackgroundJob) -> bool:
        client = self._get_client()
        if client is None:
            return False

        try:
            client.rpush(self.queue_key(job.queue_name), job.id)
            return True
        except Exception:
            return False

    def start_worker(self) -> None:
        if not self.redis_available:
            return
        if self._worker_thread and self._worker_thread.is_alive():
            return

        self._stop_event.clear()
        self._worker_thread = threading.Thread(
            target=self._worker_loop,
            daemon=True,
            name="legal-ai-job-worker",
        )
        self._worker_thread.start()

    def stop_worker(self) -> None:
        self._stop_event.set()
        worker = self._worker_thread
        if worker and worker.is_alive():
            worker.join(timeout=2.0)

    def _worker_loop(self) -> None:
        client = self._get_client()
        if client is None:
            return

        queue_keys = [self.queue_key(name) for name in self.ALL_QUEUES]
        while not self._stop_event.is_set():
            try:
                item = client.blpop(queue_keys, timeout=1)
            except Exception:
                continue

            if not item:
                continue

            _, job_id = item
            if not job_id:
                continue
            run_background_job(job_id)


def run_background_job(job_id: str) -> None:
    from backend.services.jobs.job_runner import process_background_job

    process_background_job(job_id)


background_job_service = BackgroundJobService()
