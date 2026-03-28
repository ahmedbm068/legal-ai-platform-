from __future__ import annotations

import os
from typing import Any

from openai import APIError, AuthenticationError, RateLimitError

from backend.services.ai.llm_gateway import llm_gateway


class TranscriptionService:
    def __init__(self) -> None:
        self.client = llm_gateway.create_client()

    def transcribe_file(self, file_path: str, filename: str) -> dict[str, Any]:
        if not self.client:
            return {
                "success": False,
                "text": None,
                "language": None,
                "source": None,
                "error": "OPENAI_API_KEY not configured for transcription.",
            }

        try:
            with open(file_path, "rb") as audio_file:
                response = self.client.audio.transcriptions.create(
                    model="gpt-4o-mini-transcribe",
                    file=audio_file
                )

            transcript_text = getattr(response, "text", None) or ""
            language = getattr(response, "language", None)

            if not transcript_text.strip():
                return {
                    "success": False,
                    "text": None,
                    "language": language,
                    "source": "gpt-4o-mini-transcribe",
                    "error": "Transcription returned no text.",
                }

            return {
                "success": True,
                "text": transcript_text.strip(),
                "language": language,
                "source": "gpt-4o-mini-transcribe",
                "error": None,
            }
        except (RateLimitError, APIError, AuthenticationError) as exc:
            return {
                "success": False,
                "text": None,
                "language": None,
                "source": "gpt-4o-mini-transcribe",
                "error": str(exc),
            }
        except Exception as exc:
            return {
                "success": False,
                "text": None,
                "language": None,
                "source": "gpt-4o-mini-transcribe",
                "error": f"Unexpected transcription error: {exc}",
            }


transcription_service = TranscriptionService()
