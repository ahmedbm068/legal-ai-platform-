from __future__ import annotations

import re
from typing import Any


class LegalCaseReadingService:
    """Builds a lawyer-style case brief from a reported judgment."""

    MAX_FACTS = 6
    MAX_ISSUES = 4
    MAX_HOLDINGS = 4
    MAX_RATIO = 4
    MAX_OBITER = 4

    CASE_NAME_PATTERNS = (
        r"\bR\s+v\.?\s+[A-Z][A-Za-z0-9'&.\- ]{2,80}",
        r"\b[A-Z][A-Za-z0-9'&.\- ]{2,80}\s+v\.?\s+[A-Z][A-Za-z0-9'&.\- ]{2,80}",
        r"\b[A-Z][A-Za-z0-9'&.\- ]{2,80}\s+vs\.?\s+[A-Z][A-Za-z0-9'&.\- ]{2,80}",
    )

    COURT_PATTERNS = (
        "Supreme Court",
        "House of Lords",
        "Court of Appeal",
        "High Court",
        "Crown Court",
        "County Court",
        "Upper Tribunal",
        "First-tier Tribunal",
        "Tribunal",
    )

    LEGAL_TOPICS = (
        "negligence",
        "duty of care",
        "contract",
        "breach",
        "causation",
        "damages",
        "appeal",
        "precedent",
        "jurisdiction",
        "liability",
        "evidence",
        "property",
        "possession",
        "criminal",
        "constitutional",
    )

    def build_case_analysis(
        self,
        *,
        text: str,
        document_type: str,
        filename: str = "",
    ) -> dict[str, Any] | None:
        if not self._looks_like_legal_case(text=text, document_type=document_type, filename=filename):
            return None

        normalized = self._normalize_text(text)
        sentences = self._split_sentences(normalized)

        case_name = self._extract_case_name(normalized) or self._case_name_from_filename(filename)
        court_level = self._extract_court_level(normalized)
        citation = self._extract_citation(normalized)
        judges = self._extract_judges(normalized)
        catchwords = self._extract_catchwords(normalized)
        fact_flowchart = self._extract_fact_flowchart(sentences)
        legal_issues = self._extract_by_markers(
            sentences,
            markers=("issue", "question", "whether", "dispute", "appeal concerned", "the point was"),
            limit=self.MAX_ISSUES,
        )
        holding = self._extract_by_markers(
            sentences,
            markers=("held", "allowed", "dismissed", "ruled", "found that", "concluded"),
            limit=self.MAX_HOLDINGS,
        )
        ratio = self._extract_ratio(sentences)
        obiter = self._extract_obiter(sentences)

        summary_bullets = self._build_summary_bullets(
            case_name=case_name,
            court_level=court_level,
            fact_flowchart=fact_flowchart,
            legal_issues=legal_issues,
            holding=holding,
            ratio=ratio,
            obiter=obiter,
        )

        return {
            "case_name": case_name,
            "court_level": court_level,
            "citation": citation,
            "judges": judges,
            "catchwords": catchwords,
            "headnote_warning": (
                "Treat headnotes as orientation only; verify facts, holding, ratio, and obiter against the judgment text."
            ),
            "fact_flowchart": fact_flowchart,
            "legal_issues": legal_issues,
            "holding": holding,
            "ratio": ratio,
            "obiter": obiter,
            "summary_bullets": summary_bullets,
        }

    def _looks_like_legal_case(self, *, text: str, document_type: str, filename: str) -> bool:
        lowered = f"{filename} {document_type} {text[:4000]}".lower()
        if document_type == "court_judgment":
            return True
        signals = [
            " v ",
            " v. ",
            " r v ",
            "judgment",
            "court held",
            "held that",
            "appeal",
            "ratio",
            "obiter",
            "headnote",
            "citation",
        ]
        return sum(1 for signal in signals if signal in lowered) >= 3

    @classmethod
    def _extract_case_name(cls, text: str) -> str:
        first_lines = "\n".join(text.splitlines()[:20])
        for pattern in cls.CASE_NAME_PATTERNS:
            match = re.search(pattern, first_lines)
            if match:
                return cls._clean(match.group(0))
        for pattern in cls.CASE_NAME_PATTERNS:
            match = re.search(pattern, text[:3000])
            if match:
                return cls._clean(match.group(0))
        return ""

    @staticmethod
    def _case_name_from_filename(filename: str) -> str:
        stem = re.sub(r"\.[A-Za-z0-9]{2,5}$", "", filename or "")
        stem = stem.replace("_", " ").replace("-", " ")
        return " ".join(stem.split()).strip()

    @classmethod
    def _extract_court_level(cls, text: str) -> str:
        for court in cls.COURT_PATTERNS:
            if re.search(rf"\b{re.escape(court)}\b", text, flags=re.IGNORECASE):
                return court
        return "Court level not clearly identified"

    @staticmethod
    def _extract_citation(text: str) -> str:
        patterns = (
            r"\[\d{4}\]\s+[A-Z]{2,8}\s+\d+",
            r"\[\d{4}\]\s+\d+\s+[A-Z][A-Za-z. ]+\s+\d+",
            r"\(\d{4}\)\s+\d+\s+[A-Z][A-Za-z. ]+\s+\d+",
            r"\[\d{4}\]\s+[A-Z][A-Za-z. ]+\s+\d+",
        )
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                return LegalCaseReadingService._clean(match.group(0))
        return ""

    @staticmethod
    def _extract_judges(text: str) -> list[str]:
        candidates: list[str] = []
        for pattern in (r"(?:Before|Coram):\s*([^\n]{5,220})", r"(Lord\s+[A-Z][A-Za-z]+)", r"(Lady\s+[A-Z][A-Za-z]+)"):
            for match in re.finditer(pattern, text[:4000], flags=re.IGNORECASE):
                raw = match.group(1)
                for part in re.split(r",|;|\band\b", raw):
                    cleaned = LegalCaseReadingService._clean(part)
                    if cleaned and cleaned not in candidates:
                        candidates.append(cleaned)
                    if len(candidates) >= 6:
                        return candidates
        return candidates

    @classmethod
    def _extract_catchwords(cls, text: str) -> list[str]:
        lowered = text.lower()
        return [topic for topic in cls.LEGAL_TOPICS if topic in lowered][:8]

    def _extract_fact_flowchart(self, sentences: list[str]) -> list[str]:
        fact_markers = (
            "on ",
            "the claimant",
            "the plaintiff",
            "the defendant",
            "the appellant",
            "the respondent",
            "the parties",
            "entered into",
            "agreed",
            "failed",
            "refused",
            "sought",
            "brought",
        )
        facts: list[str] = []
        for sentence in sentences[:40]:
            lowered = sentence.lower()
            has_date = bool(re.search(r"\b\d{4}\b|\b\d{1,2}\s+[A-Z][a-z]+\s+\d{4}\b", sentence))
            if has_date or any(marker in lowered for marker in fact_markers):
                self._append_unique(facts, sentence)
            if len(facts) >= self.MAX_FACTS:
                break
        if not facts:
            facts = [sentence for sentence in sentences[: self.MAX_FACTS] if sentence]
        return facts[: self.MAX_FACTS]

    def _extract_ratio(self, sentences: list[str]) -> list[str]:
        ratio_markers = (
            "held that",
            "the court held",
            "the principle",
            "the test",
            "must",
            "is bound",
            "duty of care",
            "therefore",
            "as a matter of law",
        )
        return self._extract_by_markers(sentences, markers=ratio_markers, limit=self.MAX_RATIO)

    def _extract_obiter(self, sentences: list[str]) -> list[str]:
        obiter_markers = (
            "obiter",
            "not necessary",
            "would have",
            "had the facts",
            "if the facts",
            "dissent",
            "dissenting",
            "in any event",
        )
        return self._extract_by_markers(sentences, markers=obiter_markers, limit=self.MAX_OBITER)

    def _extract_by_markers(self, sentences: list[str], *, markers: tuple[str, ...], limit: int) -> list[str]:
        results: list[str] = []
        for sentence in sentences:
            lowered = sentence.lower()
            if any(marker in lowered for marker in markers):
                self._append_unique(results, sentence)
            if len(results) >= limit:
                break
        return results

    def _build_summary_bullets(
        self,
        *,
        case_name: str,
        court_level: str,
        fact_flowchart: list[str],
        legal_issues: list[str],
        holding: list[str],
        ratio: list[str],
        obiter: list[str],
    ) -> list[str]:
        bullets: list[str] = []
        if case_name:
            bullets.append(f"Case: {case_name}.")
        if court_level:
            bullets.append(f"Authority: {court_level}.")
        if fact_flowchart:
            bullets.append(f"Key fact: {fact_flowchart[0]}")
        if legal_issues:
            bullets.append(f"Issue: {legal_issues[0]}")
        if holding:
            bullets.append(f"Held: {holding[0]}")
        if ratio:
            bullets.append(f"Ratio: {ratio[0]}")
        if obiter:
            bullets.append(f"Obiter: {obiter[0]}")
        return bullets[:8]

    @staticmethod
    def _normalize_text(text: str) -> str:
        text = str(text or "").replace("\r\n", "\n").replace("\r", "\n")
        text = re.sub(r"[ \t]+", " ", text)
        return text.strip()

    @staticmethod
    def _split_sentences(text: str) -> list[str]:
        compact = re.sub(r"\s+", " ", text)
        raw_sentences = re.split(r"(?<=[.!?])\s+(?=[A-Z0-9])", compact)
        return [LegalCaseReadingService._clean(sentence) for sentence in raw_sentences if LegalCaseReadingService._clean(sentence)]

    @staticmethod
    def _clean(value: str) -> str:
        value = re.sub(r"\s+", " ", str(value or "")).strip()
        return value.strip(" -:;,")

    @staticmethod
    def _append_unique(items: list[str], value: str) -> None:
        cleaned = LegalCaseReadingService._clean(value)
        if cleaned and cleaned not in items:
            items.append(cleaned)


legal_case_reading_service = LegalCaseReadingService()
