from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from backend.services.ai.llm_gateway import llm_gateway


PROMPT_DIR = Path(__file__).parent


class ChronologyAgent:
    def __init__(self) -> None:
        self.client = llm_gateway.create_client()
        self.model = llm_gateway.default_model
        self._chronology_prompt_template: str | None = None

    @property
    def available(self) -> bool:
        return self.client is not None

    def _get_chronology_prompt_template(self) -> str | None:
        if self._chronology_prompt_template is None:
            try:
                self._chronology_prompt_template = (PROMPT_DIR / "chronology_prompt.md").read_text(
                    encoding="utf-8"
                )
            except FileNotFoundError:
                return None
        return self._chronology_prompt_template

    def _build_chronology_prompt(self, *, documents: list[dict]) -> str | None:
        template = self._get_chronology_prompt_template()
        if not template:
            return None

        doc_snippets = []
        for doc in documents:
            filename = str(doc.get("filename") or "unknown")
            content = str(doc.get("content") or "")[:4000]
            doc_snippets.append(
                f"--- START OF {filename} ---\n{content}\n--- END OF {filename} ---"
            )

        return template + "\n\n" + "\n".join(doc_snippets)

    def extract_chronology_from_case(self, *, case_id: int, documents: list[dict]) -> Optional[dict[str, Any]]:
        if not self.client:
            return None

        prompt = self._build_chronology_prompt(documents=documents)
        if not prompt:
            return None

        try:
            response = self.client.responses.create(
                model=self.model,
                input=prompt,
            )
            raw_text = (response.output_text or "").strip()
            if not raw_text:
                return None
            return {
                "chronology": raw_text,
                "chronology_source": "llm_chronology_agent",
                "chronology_version": "v1_strict_chronology",
            }
        except Exception:
            return None

chronology_agent = ChronologyAgent()
