from __future__ import annotations

import re


class LegalTextFormatter:
    @staticmethod
    def normalize_whitespace(text: str) -> str:
        if not text:
            return ""

        text = re.sub(r"\r\n?", "\n", text)
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()

    @staticmethod
    def remove_noise(text: str) -> str:
        if not text:
            return ""

        text = re.sub(r"[ \t]+\n", "\n", text)
        text = re.sub(r"\n[ \t]+", "\n", text)
        text = re.sub(r"\bPage\s+\d+\s*(of\s*\d+)?\b", "", text, flags=re.IGNORECASE)
        text = re.sub(r"_{3,}", "", text)
        text = re.sub(r"-\n", "", text)
        text = re.sub(r"\n[=\-]{20,}\n", "\n", text)
        text = re.sub(r"\n{3,}", "\n\n", text)

        return text.strip()

    @staticmethod
    def preserve_legal_structure(text: str) -> str:
        if not text:
            return ""

        text = re.sub(r"\s*:\s*", ": ", text)

        text = re.sub(
            r"\bINV\s*-\s*(\d{4})\s*-\s*(\d+)\b",
            r"INV-\1-\2",
            text,
            flags=re.IGNORECASE
        )
        text = re.sub(
            r"\b([A-Z]{2,10})\s*-\s*([A-Z]{2,10})\s*-\s*(\d{1,6})\b",
            r"\1-\2-\3",
            text
        )

        text = re.sub(r"\n(?=(\d+\.\d+|\d+\)|ARTICLE\s+\d+|SECTION\s+\d+|CLAUSE\s+\d+))", "\n", text, flags=re.IGNORECASE)

        return text.strip()

    @staticmethod
    def trim_for_ai(text: str, max_chars: int = 18000) -> str:
        if not text:
            return ""
        return text[:max_chars].strip()

    @classmethod
    def prepare_for_summary(cls, text: str, max_chars: int | None = None) -> str:
        if not text:
            return ""

        text = cls.normalize_whitespace(text)
        text = cls.remove_noise(text)
        text = cls.preserve_legal_structure(text)

        if max_chars is not None:
            text = cls.trim_for_ai(text, max_chars=max_chars)

        return text