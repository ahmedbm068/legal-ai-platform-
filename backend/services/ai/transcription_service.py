from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import tempfile
import time
import uuid
import wave
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import numpy as np
from openai import OpenAI
from openai import APIError, AuthenticationError, RateLimitError

from backend.core.config import settings


logger = logging.getLogger(__name__)


def looks_like_html_error_page(value: str) -> bool:
    normalized = value.lstrip().lower()
    return normalized.startswith("<!doctype html") or normalized.startswith("<html")


class TranscriptionService:
    def __init__(self) -> None:
        self._local_pipeline = None
        self._logged_remote_skip = False
        self._logged_local_pipeline = False

    @staticmethod
    def _normalized_url(value: str | None) -> str:
        return (value or "").strip().rstrip("/")

    def _speechmatics_available(self) -> bool:
        return bool((settings.SPEECHMATICS_API_KEY or "").strip())

    def _speechmatics_base_url(self) -> str:
        base_url = self._normalized_url(settings.SPEECHMATICS_BASE_URL)
        if not base_url:
            raise ValueError("SPEECHMATICS_BASE_URL is not configured.")
        return base_url

    def _speechmatics_request_timeout_seconds(self) -> int:
        max_wait = max(30, int(settings.SPEECHMATICS_MAX_WAIT_SECONDS))
        return max(10, min(max_wait, 120))

    def _speechmatics_headers(self, *, content_type: str | None = None) -> dict[str, str]:
        api_key = (settings.SPEECHMATICS_API_KEY or "").strip()
        if not api_key:
            raise ValueError("SPEECHMATICS_API_KEY is not configured.")

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Accept": "application/json",
        }
        if content_type:
            headers["Content-Type"] = content_type
        return headers

    def _speechmatics_build_config(self) -> dict[str, Any]:
        language = (settings.SPEECHMATICS_LANGUAGE or "").strip()
        transcription_config: dict[str, Any] = {}

        if language and language.lower() != "auto":
            transcription_config["language"] = language

        payload: dict[str, Any] = {
            "type": "transcription",
            "transcription_config": transcription_config,
        }
        return payload

    @staticmethod
    def _build_multipart_form_data(
        *,
        config_payload: dict[str, Any],
        file_path: str,
        filename: str,
    ) -> tuple[bytes, str]:
        boundary = f"----speechmatics-{uuid.uuid4().hex}"
        config_json = json.dumps(config_payload, ensure_ascii=False)
        safe_filename = (filename or os.path.basename(file_path) or "audio").strip()

        with open(file_path, "rb") as uploaded_file:
            file_bytes = uploaded_file.read()

        body = bytearray()
        line_break = b"\r\n"

        body.extend(f"--{boundary}\r\n".encode("utf-8"))
        body.extend(b'Content-Disposition: form-data; name="config"\r\n')
        body.extend(b"Content-Type: application/json\r\n\r\n")
        body.extend(config_json.encode("utf-8"))
        body.extend(line_break)

        body.extend(f"--{boundary}\r\n".encode("utf-8"))
        body.extend(
            f'Content-Disposition: form-data; name="data_file"; filename="{safe_filename}"\r\n'.encode("utf-8")
        )
        body.extend(b"Content-Type: application/octet-stream\r\n\r\n")
        body.extend(file_bytes)
        body.extend(line_break)

        body.extend(f"--{boundary}--\r\n".encode("utf-8"))
        return bytes(body), f"multipart/form-data; boundary={boundary}"

    def _speechmatics_request_json(
        self,
        *,
        method: str,
        url: str,
        data: bytes | None = None,
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        request = Request(url=url, data=data, method=method, headers=headers or {})
        with urlopen(request, timeout=self._speechmatics_request_timeout_seconds()) as response:
            raw_payload = response.read().decode("utf-8", errors="ignore")

        if not raw_payload.strip():
            return {}

        parsed = json.loads(raw_payload)
        return parsed if isinstance(parsed, dict) else {}

    @staticmethod
    def _extract_nested_string(payload: dict[str, Any], *keys: str) -> str:
        current: Any = payload
        for key in keys:
            if not isinstance(current, dict):
                return ""
            current = current.get(key)
        return str(current or "").strip()

    def _speechmatics_extract_job_id(self, payload: dict[str, Any]) -> str:
        candidates = [
            self._extract_nested_string(payload, "id"),
            self._extract_nested_string(payload, "job", "id"),
            self._extract_nested_string(payload, "job", "job_id"),
            self._extract_nested_string(payload, "job_id"),
        ]
        for item in candidates:
            if item:
                return item
        return ""

    def _speechmatics_create_job(self, *, file_path: str, filename: str) -> str:
        body, content_type = self._build_multipart_form_data(
            config_payload=self._speechmatics_build_config(),
            file_path=file_path,
            filename=filename,
        )
        base_url = self._speechmatics_base_url()
        payload = self._speechmatics_request_json(
            method="POST",
            url=f"{base_url}/jobs/",
            data=body,
            headers=self._speechmatics_headers(content_type=content_type),
        )
        job_id = self._speechmatics_extract_job_id(payload)
        if not job_id:
            raise RuntimeError(f"Speechmatics did not return a job id: {payload}")
        return job_id

    def _speechmatics_get_job_status(self, *, job_id: str) -> str:
        base_url = self._speechmatics_base_url()
        payload = self._speechmatics_request_json(
            method="GET",
            url=f"{base_url}/jobs/{job_id}",
            headers=self._speechmatics_headers(),
        )
        status = (
            self._extract_nested_string(payload, "status")
            or self._extract_nested_string(payload, "job", "status")
        )
        return status.lower()

    def _speechmatics_wait_for_job(self, *, job_id: str) -> None:
        poll_interval = max(1, int(settings.SPEECHMATICS_POLL_INTERVAL_SECONDS))
        deadline = time.monotonic() + max(30, int(settings.SPEECHMATICS_MAX_WAIT_SECONDS))

        completed_states = {"done", "completed", "succeeded", "success"}
        failed_states = {"rejected", "failed", "error", "cancelled", "expired"}

        while time.monotonic() <= deadline:
            status = self._speechmatics_get_job_status(job_id=job_id)
            if status in completed_states:
                return
            if status in failed_states:
                raise RuntimeError(f"Speechmatics transcription job failed with status='{status}'.")
            time.sleep(poll_interval)

        raise TimeoutError("Speechmatics transcription job timed out before completion.")

    @staticmethod
    def _speechmatics_extract_text_from_payload(payload: dict[str, Any]) -> str:
        direct_text = str(payload.get("transcript") or payload.get("text") or "").strip()
        if direct_text:
            return direct_text

        results = payload.get("results")
        if not isinstance(results, list):
            return ""

        parts: list[str] = []
        for item in results:
            if not isinstance(item, dict):
                continue
            alternatives = item.get("alternatives") or []
            first_alternative = alternatives[0] if alternatives and isinstance(alternatives[0], dict) else {}
            token = str(first_alternative.get("content") or "").strip()
            if not token:
                continue

            token_type = str(item.get("type") or "").lower()
            if token_type in {"punctuation", "punct"}:
                if parts:
                    parts[-1] = f"{parts[-1]}{token}"
                else:
                    parts.append(token)
            else:
                parts.append(token)

        text = " ".join(parts).strip()
        return text.replace(" ,", ",").replace(" .", ".").replace(" !", "!").replace(" ?", "?")

    def _speechmatics_fetch_transcript(self, *, job_id: str) -> tuple[str, str | None]:
        base_url = self._speechmatics_base_url()
        language = (settings.SPEECHMATICS_LANGUAGE or "").strip() or None
        headers = self._speechmatics_headers()

        text_url = f"{base_url}/jobs/{job_id}/transcript?{urlencode({'format': 'txt'})}"
        text_request = Request(url=text_url, method="GET", headers={**headers, "Accept": "text/plain"})
        try:
            with urlopen(text_request, timeout=self._speechmatics_request_timeout_seconds()) as response:
                transcript_text = response.read().decode("utf-8", errors="ignore").strip()
            if transcript_text:
                return transcript_text, language
        except Exception:
            pass

        for transcript_format in ("json-v2", "json"):
            transcript_url = f"{base_url}/jobs/{job_id}/transcript?{urlencode({'format': transcript_format})}"
            try:
                payload = self._speechmatics_request_json(
                    method="GET",
                    url=transcript_url,
                    headers=headers,
                )
                transcript_text = self._speechmatics_extract_text_from_payload(payload)
                if transcript_text:
                    language = (
                        self._extract_nested_string(payload, "metadata", "transcription_config", "language")
                        or self._extract_nested_string(payload, "language")
                        or language
                    )
                    return transcript_text, language
            except Exception:
                continue

        raise RuntimeError("Speechmatics completed but transcript content was empty.")

    def _speechmatics_transcribe_file(self, *, file_path: str, filename: str) -> dict[str, Any]:
        if not self._speechmatics_available():
            return {
                "success": False,
                "text": None,
                "language": None,
                "source": "speechmatics",
                "error": "Speechmatics API key is not configured.",
            }

        try:
            job_id = self._speechmatics_create_job(file_path=file_path, filename=filename)
            self._speechmatics_wait_for_job(job_id=job_id)
            transcript_text, language = self._speechmatics_fetch_transcript(job_id=job_id)
            return {
                "success": True,
                "text": transcript_text,
                "language": language,
                "source": "speechmatics",
                "error": None,
            }
        except (HTTPError, URLError, TimeoutError, ValueError, RuntimeError) as exc:
            return {
                "success": False,
                "text": None,
                "language": None,
                "source": "speechmatics",
                "error": f"Speechmatics transcription error: {exc}",
            }
        except Exception as exc:
            return {
                "success": False,
                "text": None,
                "language": None,
                "source": "speechmatics",
                "error": f"Unexpected Speechmatics error: {exc}",
            }

    def _get_client(self) -> OpenAI | None:
        if not settings.TRANSCRIPTION_REMOTE_ENABLED:
            return None

        api_key = settings.TRANSCRIPTION_API_KEY or settings.OPENAI_API_KEY
        if not api_key:
            return None

        kwargs: dict[str, Any] = {"api_key": api_key}
        base_url = settings.TRANSCRIPTION_BASE_URL or settings.LLM_BASE_URL
        if base_url:
            kwargs["base_url"] = base_url

        return OpenAI(**kwargs)

    def _should_skip_remote_transcription(self) -> bool:
        base_url = (settings.TRANSCRIPTION_BASE_URL or settings.LLM_BASE_URL or "").lower().strip()
        if "openrouter.ai" in base_url and not settings.TRANSCRIPTION_BASE_URL:
            return True
        if "groq.com" in base_url and not settings.TRANSCRIPTION_BASE_URL:
            return True
        return False

    def _resolve_local_device(self) -> int | str:
        configured_device = (settings.TRANSCRIPTION_DEVICE or "auto").strip().lower()
        if configured_device == "auto":
            try:
                import torch

                return 0 if torch.cuda.is_available() else -1
            except Exception:
                return -1

        if configured_device == "cpu":
            return -1

        if configured_device == "cuda":
            return 0

        return settings.TRANSCRIPTION_DEVICE

    def _get_local_pipeline(self):
        if self._local_pipeline is not None:
            return self._local_pipeline

        from transformers import pipeline

        device = self._resolve_local_device()
        pipeline_kwargs: dict[str, Any] = {
            "task": "automatic-speech-recognition",
            "model": settings.LOCAL_TRANSCRIPTION_MODEL,
            "device": device,
        }

        if settings.LOCAL_TRANSCRIPTION_PREFER_LOCAL_FILES:
            try:
                self._local_pipeline = pipeline(
                    **pipeline_kwargs,
                    model_kwargs={"local_files_only": True},
                )
            except Exception:
                # Cache miss or partial cache: retry online so first-time setup still works.
                self._local_pipeline = pipeline(**pipeline_kwargs)
        else:
            self._local_pipeline = pipeline(**pipeline_kwargs)

        if not self._logged_local_pipeline:
            logger.info(
                "Loaded local transcription pipeline with model=%s device=%s",
                settings.LOCAL_TRANSCRIPTION_MODEL,
                device,
            )
            self._logged_local_pipeline = True
        return self._local_pipeline

    def _load_wav_audio(self, file_path: str) -> tuple[np.ndarray, int]:
        with wave.open(file_path, "rb") as wav_file:
            sample_rate = wav_file.getframerate()
            sample_width = wav_file.getsampwidth()
            channel_count = wav_file.getnchannels()
            frame_count = wav_file.getnframes()
            raw_audio = wav_file.readframes(frame_count)

        dtype_map = {
            1: np.int8,
            2: np.int16,
            4: np.int32,
        }

        dtype = dtype_map.get(sample_width)
        if dtype is None:
            raise ValueError(f"Unsupported WAV sample width: {sample_width}")

        audio = np.frombuffer(raw_audio, dtype=dtype).astype(np.float32)

        if channel_count > 1:
            audio = audio.reshape(-1, channel_count).mean(axis=1)

        max_abs = float(np.max(np.abs(audio))) if audio.size else 1.0
        if max_abs > 0:
            audio /= max_abs

        return audio, sample_rate

    def _resample_audio(self, audio: np.ndarray, source_rate: int, target_rate: int) -> np.ndarray:
        if source_rate == target_rate or audio.size == 0:
            return audio

        if source_rate <= 0 or target_rate <= 0:
            raise ValueError("Invalid sample rate for resampling.")

        source_indices = np.arange(audio.size, dtype=np.float64)
        duration = audio.size / float(source_rate)
        target_size = max(1, int(round(duration * float(target_rate))))
        target_indices = np.arange(target_size, dtype=np.float64) * (float(source_rate) / float(target_rate))
        target_indices = np.clip(target_indices, 0.0, max(0.0, audio.size - 1))
        resampled = np.interp(target_indices, source_indices, audio.astype(np.float64))
        return resampled.astype(np.float32)

    def _convert_audio_to_wav(self, file_path: str) -> str | None:
        ffmpeg_binary = shutil.which("ffmpeg")
        if not ffmpeg_binary:
            return None

        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".wav")
        temp_file_path = temp_file.name
        temp_file.close()

        command = [
            ffmpeg_binary,
            "-y",
            "-i",
            file_path,
            "-ac",
            "1",
            "-ar",
            "16000",
            temp_file_path,
        ]

        try:
            completed = subprocess.run(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
            )
            if completed.returncode != 0:
                try:
                    os.remove(temp_file_path)
                except OSError:
                    pass
                logger.warning(
                    "ffmpeg audio conversion failed for '%s' with exit_code=%s stderr=%s",
                    file_path,
                    completed.returncode,
                    (completed.stderr or "").strip()[:400],
                )
                return None

            return temp_file_path
        except Exception as exc:
            try:
                os.remove(temp_file_path)
            except OSError:
                pass
            logger.warning("ffmpeg audio conversion raised an unexpected error for '%s': %s", file_path, exc)
            return None

    def _local_transcribe_file(self, file_path: str) -> dict[str, Any]:
        cleanup_path: str | None = None
        target_file_path = file_path

        if not file_path.lower().endswith(".wav"):
            converted_path = self._convert_audio_to_wav(file_path)
            if converted_path:
                target_file_path = converted_path
                cleanup_path = converted_path
            else:
                try:
                    recognizer = self._get_local_pipeline()
                    result = recognizer(file_path, return_timestamps=False)
                    text = (result.get("text") or "").strip()
                    if text:
                        return {
                            "success": True,
                            "text": text,
                            "language": None,
                            "source": settings.LOCAL_TRANSCRIPTION_MODEL,
                            "error": None,
                        }
                except Exception as exc:
                    error_message = str(exc)
                    if "torchaudio is required" in error_message.lower():
                        error_message = (
                            "Local transcription requires torchaudio for this audio format. "
                            "Install it with `pip install torchaudio`, or install ffmpeg to auto-convert uploads."
                        )
                    return {
                        "success": False,
                        "text": None,
                        "language": None,
                        "source": settings.LOCAL_TRANSCRIPTION_MODEL,
                        "error": f"Local transcription error: {error_message}",
                    }

                return {
                    "success": False,
                    "text": None,
                    "language": None,
                    "source": settings.LOCAL_TRANSCRIPTION_MODEL,
                    "error": (
                        "Local transcription could not decode this audio format. "
                        "Install ffmpeg or torchaudio, or upload WAV audio."
                    ),
                }

        try:
            audio, sample_rate = self._load_wav_audio(target_file_path)
            if audio.size == 0:
                return {
                    "success": False,
                    "text": None,
                    "language": None,
                    "source": settings.LOCAL_TRANSCRIPTION_MODEL,
                    "error": "The WAV file contains no readable audio samples.",
                }

            recognizer = self._get_local_pipeline()
            target_rate = int(
                getattr(getattr(recognizer, "feature_extractor", None), "sampling_rate", sample_rate)
            )
            if sample_rate != target_rate:
                audio = self._resample_audio(audio, sample_rate, target_rate)
                sample_rate = target_rate

            result = recognizer(
                {"array": audio, "sampling_rate": sample_rate},
                return_timestamps=False,
            )
            text = (result.get("text") or "").strip()

            if not text:
                return {
                    "success": False,
                    "text": None,
                    "language": None,
                    "source": settings.LOCAL_TRANSCRIPTION_MODEL,
                    "error": "Local transcription returned no text.",
                }

            return {
                "success": True,
                "text": text,
                "language": None,
                "source": settings.LOCAL_TRANSCRIPTION_MODEL,
                "error": None,
            }
        except Exception as exc:
            return {
                "success": False,
                "text": None,
                "language": None,
                "source": settings.LOCAL_TRANSCRIPTION_MODEL,
                "error": f"Local transcription error: {exc}",
            }
        finally:
            if cleanup_path and os.path.exists(cleanup_path):
                try:
                    os.remove(cleanup_path)
                except OSError:
                    pass

    def transcribe_file(self, file_path: str, filename: str) -> dict[str, Any]:
        speechmatics_error: str | None = None
        if self._speechmatics_available():
            speechmatics_result = self._speechmatics_transcribe_file(file_path=file_path, filename=filename)
            if speechmatics_result["success"]:
                return speechmatics_result
            speechmatics_error = str(speechmatics_result.get("error") or "").strip() or None
            if speechmatics_error:
                logger.warning("Speechmatics transcription failed; falling back. reason=%s", speechmatics_error)

        def _with_speechmatics_context(result: dict[str, Any]) -> dict[str, Any]:
            if not speechmatics_error:
                return result
            if result.get("success"):
                return result
            base_error = str(result.get("error") or "").strip()
            if base_error:
                result["error"] = f"{base_error} | {speechmatics_error}"
            else:
                result["error"] = speechmatics_error
            return result

        client = self._get_client()
        model = settings.TRANSCRIPTION_MODEL

        if self._should_skip_remote_transcription():
            # OpenRouter model routes are great for text LLM tasks but often unreliable for speech endpoints.
            if not self._logged_remote_skip:
                logger.info(
                    "Skipping remote transcription because base_url=%s appears to be OpenRouter without a dedicated "
                    "TRANSCRIPTION_BASE_URL. Falling back to local model=%s.",
                    settings.LLM_BASE_URL,
                    settings.LOCAL_TRANSCRIPTION_MODEL,
                )
                self._logged_remote_skip = True
            return _with_speechmatics_context(self._local_transcribe_file(file_path))

        if not client:
            return _with_speechmatics_context(self._local_transcribe_file(file_path))

        try:
            with open(file_path, "rb") as audio_file:
                response = client.audio.transcriptions.create(
                    model=model,
                    file=audio_file
                )

            transcript_text = getattr(response, "text", None) or ""
            language = getattr(response, "language", None)

            if looks_like_html_error_page(transcript_text):
                failure_result = {
                    "success": False,
                    "text": None,
                    "language": language,
                    "source": model,
                    "error": (
                        "The transcription provider returned an HTML error page instead of transcript text. "
                        "Falling back to local transcription if possible."
                    ),
                }
                fallback_result = self._local_transcribe_file(file_path)
                if fallback_result["success"]:
                    return fallback_result
                return _with_speechmatics_context(failure_result)

            if not transcript_text.strip():
                failure_result = {
                    "success": False,
                    "text": None,
                    "language": language,
                    "source": model,
                    "error": "Transcription returned no text.",
                }
                fallback_result = self._local_transcribe_file(file_path)
                if fallback_result["success"]:
                    return fallback_result
                return _with_speechmatics_context(failure_result)

            return {
                "success": True,
                "text": transcript_text.strip(),
                "language": language,
                "source": model,
                "error": None,
            }
        except (RateLimitError, APIError, AuthenticationError) as exc:
            failure_result = {
                "success": False,
                "text": None,
                "language": None,
                "source": model,
                "error": str(exc),
            }
            fallback_result = self._local_transcribe_file(file_path)
            if fallback_result["success"]:
                return fallback_result
            return _with_speechmatics_context(failure_result)
        except Exception as exc:
            failure_result = {
                "success": False,
                "text": None,
                "language": None,
                "source": model,
                "error": f"Unexpected transcription error: {exc}",
            }
            fallback_result = self._local_transcribe_file(file_path)
            if fallback_result["success"]:
                return fallback_result
            return _with_speechmatics_context(failure_result)


transcription_service = TranscriptionService()
