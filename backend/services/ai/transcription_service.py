from __future__ import annotations

import wave
from typing import Any

import numpy as np
from openai import OpenAI
from openai import APIError, AuthenticationError, RateLimitError

from backend.core.config import settings


def looks_like_html_error_page(value: str) -> bool:
    normalized = value.lstrip().lower()
    return normalized.startswith("<!doctype html") or normalized.startswith("<html")


class TranscriptionService:
    def __init__(self) -> None:
        self._local_pipeline = None

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
        return "openrouter.ai" in base_url and not settings.TRANSCRIPTION_BASE_URL

    def _get_local_pipeline(self):
        if self._local_pipeline is not None:
            return self._local_pipeline

        from transformers import pipeline

        self._local_pipeline = pipeline(
            "automatic-speech-recognition",
            model=settings.LOCAL_TRANSCRIPTION_MODEL,
            device=-1,
        )
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

    def _local_transcribe_file(self, file_path: str) -> dict[str, Any]:
        if not file_path.lower().endswith(".wav"):
            return {
                "success": False,
                "text": None,
                "language": None,
                "source": settings.LOCAL_TRANSCRIPTION_MODEL,
                "error": "Local fallback currently supports WAV audio only.",
            }

        try:
            audio, sample_rate = self._load_wav_audio(file_path)
            if audio.size == 0:
                return {
                    "success": False,
                    "text": None,
                    "language": None,
                    "source": settings.LOCAL_TRANSCRIPTION_MODEL,
                    "error": "The WAV file contains no readable audio samples.",
                }

            recognizer = self._get_local_pipeline()
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

    def transcribe_file(self, file_path: str, filename: str) -> dict[str, Any]:
        client = self._get_client()
        model = settings.TRANSCRIPTION_MODEL

        if self._should_skip_remote_transcription():
            # OpenRouter model routes are great for text LLM tasks but often unreliable for speech endpoints.
            return self._local_transcribe_file(file_path)

        if not client:
            return self._local_transcribe_file(file_path)

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
                return failure_result

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
                return failure_result

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
            return failure_result
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
            return failure_result


transcription_service = TranscriptionService()
