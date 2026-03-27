from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Dict, List


@dataclass
class DocumentClassificationResult:
    document_type: str
    confidence: float
    matched_keywords: List[str]


class DocumentClassifierService:
    DOCUMENT_TYPE_RULES: Dict[str, List[str]] = {
        "contract": [
            "agreement", "contract", "parties", "clause", "termination",
            "obligation", "payment terms", "governing law", "effective date",
            "signed", "landlord", "tenant", "lease", "rent", "security deposit",
            "supplier", "buyer", "confidentiality", "dispute resolution"
        ],
        "court_judgment": [
            "judgment", "court", "tribunal", "appeal", "judge",
            "decision", "ruling", "plaintiff", "defendant", "held that",
            "the court finds", "the court held"
        ],
        "invoice": [
            "invoice", "invoice number", "total amount", "vat",
            "tax", "payment due", "bill to", "amount due",
            "subtotal", "unit price", "balance due"
        ],
        "legal_letter": [
            "dear sir", "dear madam", "formal notice", "notice",
            "we hereby", "on behalf of", "yours faithfully",
            "yours sincerely", "to whom it may concern", "recipient"
        ],
        "complaint": [
            "complaint", "claimant", "respondent", "statement of claim",
            "facts of the case", "relief sought", "damages claimed",
            "petitioner", "cause of action"
        ],
        "identity_document": [
            "identity card", "passport", "nationality", "date of birth",
            "id number", "cin", "card number", "issued on", "place of birth"
        ],
        "evidence_attachment": [
            "annex", "appendix", "attachment", "exhibit", "supporting document",
            "evidence", "photo attached", "attached file", "schedule", "appendices"
        ],
        "case_memo": [
            "internal legal case memo", "preliminary assessment", "litigation risk",
            "evidentiary risk", "recommended next legal actions", "confidential internal note"
        ],
    }

    def classify(self, text: str) -> DocumentClassificationResult:
        if not text or not text.strip():
            return DocumentClassificationResult(
                document_type="unknown",
                confidence=0.0,
                matched_keywords=[]
            )

        lowered = self._normalize_text(text)
        scores: Dict[str, int] = {}
        matched_by_type: Dict[str, List[str]] = {}

        for doc_type, keywords in self.DOCUMENT_TYPE_RULES.items():
            matched_keywords: List[str] = []

            for keyword in keywords:
                if self._contains_keyword(lowered, keyword):
                    matched_keywords.append(keyword)

            scores[doc_type] = len(matched_keywords)
            matched_by_type[doc_type] = matched_keywords

        best_type = max(scores, key=scores.get)
        best_score = scores[best_type]

        if best_score == 0:
            return DocumentClassificationResult(
                document_type="unknown",
                confidence=0.0,
                matched_keywords=[]
            )

        sorted_scores = sorted(scores.values(), reverse=True)
        second_best = sorted_scores[1] if len(sorted_scores) > 1 else 0

        total_keywords = len(self.DOCUMENT_TYPE_RULES[best_type])
        confidence = best_score / max(total_keywords, 1)

        if best_score >= second_best + 2:
            confidence += 0.15
        elif best_score == second_best:
            confidence -= 0.10

        confidence = round(max(0.0, min(confidence, 1.0)), 2)

        return DocumentClassificationResult(
            document_type=best_type,
            confidence=confidence,
            matched_keywords=matched_by_type[best_type]
        )

    @staticmethod
    def _normalize_text(text: str) -> str:
        text = text.lower()
        text = re.sub(r"\s+", " ", text)
        return text.strip()

    @staticmethod
    def _contains_keyword(text: str, keyword: str) -> bool:
        escaped = re.escape(keyword.lower())
        pattern = rf"(?<!\w){escaped}(?!\w)"
        return bool(re.search(pattern, text))


document_classifier_service = DocumentClassifierService()