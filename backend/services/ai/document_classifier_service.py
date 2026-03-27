from __future__ import annotations

from dataclasses import dataclass


@dataclass
class DocumentClassificationResult:
    document_type: str
    confidence: float


class DocumentClassifierService:
    """
    Rule-based legal document classifier.

    Supported types:
    - contract
    - court_judgment
    - invoice
    - legal_letter
    - complaint
    - identity_document
    - evidence_attachment
    - unknown
    """

    DOCUMENT_TYPE_RULES = {
        "contract": [
            "agreement", "contract", "parties", "party", "clause",
            "termination", "obligation", "payment terms", "governing law",
            "effective date", "signature", "signed", "landlord", "tenant",
            "lease", "rent", "security deposit"
        ],
        "court_judgment": [
            "judgment", "court", "tribunal", "appeal", "judge",
            "decision", "ruling", "plaintiff", "defendant", "case number",
            "held that", "the court finds", "the court held"
        ],
        "invoice": [
            "invoice", "invoice number", "total amount", "vat",
            "tax", "payment due", "bill to", "amount due",
            "subtotal", "unit price", "balance due"
        ],
        "legal_letter": [
            "dear sir", "dear madam", "formal notice", "notice",
            "we hereby", "on behalf of", "yours faithfully",
            "yours sincerely", "to whom it may concern"
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
    }

    def classify(self, text: str) -> DocumentClassificationResult:
        if not text or not text.strip():
            return DocumentClassificationResult(document_type="unknown", confidence=0.0)

        lowered = text.lower()
        scores: dict[str, int] = {}

        for doc_type, keywords in self.DOCUMENT_TYPE_RULES.items():
            score = 0
            for keyword in keywords:
                if keyword in lowered:
                    score += 1
            scores[doc_type] = score

        best_type = max(scores, key=scores.get)
        best_score = scores[best_type]

        if best_score == 0:
            return DocumentClassificationResult(document_type="unknown", confidence=0.0)

        sorted_scores = sorted(scores.values(), reverse=True)
        second_best = sorted_scores[1] if len(sorted_scores) > 1 else 0

        total_keywords = len(self.DOCUMENT_TYPE_RULES[best_type])
        base_confidence = best_score / max(total_keywords, 1)

        if best_score >= second_best + 2:
            base_confidence += 0.15
        elif best_score == second_best:
            base_confidence -= 0.10

        confidence = round(max(0.0, min(base_confidence, 1.0)), 2)

        return DocumentClassificationResult(
            document_type=best_type,
            confidence=confidence
        )


document_classifier_service = DocumentClassifierService()