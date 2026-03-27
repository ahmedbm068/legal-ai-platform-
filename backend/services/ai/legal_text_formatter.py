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
        """
        Removes common OCR / extraction noise while preserving legal meaning.
        """
        if not text:
            return ""

        text = re.sub(r"[ \t]+\n", "\n", text)
        text = re.sub(r"\n[ \t]+", "\n", text)

        # Remove page numbers (Page X or Page X of Y)
        text = re.sub(r"Page\s+\d+\s*(of\s*\d+)?", "", text, flags=re.IGNORECASE)

        # Remove long underscores (forms, scans)
        text = re.sub(r"_{3,}", "", text)

        # Fix hyphenated line breaks
        text = re.sub(r"-\n", "", text)

        return text.strip()

    @classmethod
    def prepare_for_summary(cls, text: str) -> str:
        """
        Full cleaning pipeline before summarization.
        """
        if not text:
            return ""

        text = cls.normalize_whitespace(text)
        text = cls.remove_noise(text)
        return text