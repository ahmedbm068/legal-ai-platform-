from __future__ import annotations

import json
import re
from typing import Any

from backend.models.document import Document
from backend.services.ai.document_classifier_service import document_classifier_service
from backend.services.ai.legal_text_formatter import LegalTextFormatter


class DocumentInsightService:
    """
    Structured legal intelligence extraction service.

    Generates:
    - document_type
    - general_summary
    - key_points
    - important_dates
    - parties_detected
    - legal_risks
    - recommended_next_actions
    """

    MAX_INPUT_CHARS = 18000
    MAX_KEY_POINTS = 5
    MAX_DATES = 8
    MAX_PARTIES = 6
    MAX_RISKS = 6
    MAX_ACTIONS = 6

    LEGAL_KEYWORDS = [
        "agreement", "contract", "court", "judge", "claim", "payment",
        "deadline", "termination", "liability", "obligation", "invoice",
        "hearing", "appeal", "article", "law", "damages", "evidence",
        "rent", "tenant", "landlord", "deposit", "notice", "breach"
    ]

    def build_insights(self, document: Document) -> dict[str, Any]:
        source_text = document.redacted_text or document.extracted_text

        if not source_text or not source_text.strip():
            raise ValueError("Document has no processed text available for intelligence extraction.")

        text = LegalTextFormatter.prepare_for_summary(source_text)
        text = text[: self.MAX_INPUT_CHARS]

        classification = document_classifier_service.classify(text)

        general_summary = self._generate_general_summary(text, classification.document_type)
        key_points = self._extract_key_points(text)
        important_dates = self._extract_important_dates(text)
        parties_detected = self._extract_parties(text, classification.document_type)
        legal_risks = self._detect_legal_risks(
            text=text,
            document_type=classification.document_type,
            parties_detected=parties_detected,
            important_dates=important_dates
        )
        recommended_next_actions = self._recommend_next_actions(
            document_type=classification.document_type,
            legal_risks=legal_risks,
            important_dates=important_dates,
            parties_detected=parties_detected
        )

        return {
            "document_type": classification.document_type,
            "document_type_confidence": classification.confidence,
            "general_summary": general_summary,
            "key_points": key_points,
            "important_dates": important_dates,
            "parties_detected": parties_detected,
            "legal_risks": legal_risks,
            "recommended_next_actions": recommended_next_actions,
            "summary_source": "heuristic",
            "summary_version": "v3"
        }

    def to_json_string(self, insights: dict[str, Any]) -> str:
        return json.dumps(insights, ensure_ascii=False)

    def _generate_general_summary(self, text: str, document_type: str) -> str:
        sentences = self._split_sentences(text)
        if not sentences:
            return "No meaningful summary could be generated."

        ranked = self._rank_sentences(sentences)
        selected = ranked[:3]

        if not selected:
            return "No meaningful summary could be generated."

        cleaned_sentences = []
        for sentence in selected:
            normalized = self._normalize_summary_sentence(sentence)
            if normalized and normalized not in cleaned_sentences:
                cleaned_sentences.append(normalized)

        body = " ".join(cleaned_sentences).strip()

        intro_map = {
            "contract": "This document appears to be a contract. It primarily sets out the relationship, obligations, and terms between the parties.",
            "court_judgment": "This document appears to be a court judgment. It primarily summarizes the dispute, the court's reasoning, and the outcome.",
            "invoice": "This document appears to be an invoice. It primarily records billed amounts, payment obligations, and commercial details.",
            "legal_letter": "This document appears to be a legal letter. It primarily communicates a formal legal or procedural position.",
            "complaint": "This document appears to be a legal complaint. It primarily presents allegations, factual claims, and requested relief.",
            "identity_document": "This document appears to be an identity-related document. It primarily contains personal identification details.",
            "evidence_attachment": "This document appears to be a supporting evidence attachment. It primarily contains supplementary factual material.",
            "unknown": "This document appears to concern legal or administrative matters.",
        }

        intro = intro_map.get(document_type, intro_map["unknown"])

        return f"{intro} Key content includes: {body}"

    def _extract_key_points(self, text: str) -> list[str]:
        sentences = self._split_sentences(text)
        ranked = self._rank_sentences(sentences)
        results: list[str] = []

        for sentence in ranked:
            cleaned = self._normalize_summary_sentence(sentence)
            if cleaned and cleaned not in results:
                results.append(cleaned)
            if len(results) >= self.MAX_KEY_POINTS:
                break

        return results

    def _extract_important_dates(self, text: str) -> list[dict[str, str]]:
        exact_date_patterns = [
            r"\b\d{4}-\d{2}-\d{2}\b",
            r"\b\d{1,2}/\d{1,2}/\d{2,4}\b",
            r"\b\d{1,2}-\d{1,2}-\d{2,4}\b",
        ]

        relative_patterns = [
            r"\bwithin\s+\d+\s+days?\b",
            r"\bwithin\s+\d+\s+hours?\b",
            r"\b\d{1,3}-day\s+written\s+notice\b",
            r"\b\d{1,3}\s+day\s+written\s+notice\b",
            r"\bfirst day of each month\b",
            r"\bdue within\s+\d+\s+days?\b",
            r"\bnotice period of\s+\d+\s+days?\b",
        ]

        results: list[dict[str, str]] = []
        seen: set[tuple[str, str]] = set()

        for pattern in exact_date_patterns:
            for match in re.findall(pattern, text, flags=re.IGNORECASE):
                label = self._label_date_from_context(text, match)
                key = (label, match)
                if key not in seen:
                    seen.add(key)
                    results.append({
                        "label": label,
                        "value": match
                    })

        for pattern in relative_patterns:
            for match in re.findall(pattern, text, flags=re.IGNORECASE):
                normalized = match.strip()
                lowered = normalized.lower()

                if "written notice" in lowered or "notice period" in lowered:
                    label = "notice_period"
                elif "first day of each month" in lowered:
                    label = "recurring_payment_date"
                elif "within" in lowered and "days" in lowered:
                    label = "deadline_or_time_limit"
                elif "within" in lowered and "hours" in lowered:
                    label = "urgent_deadline"
                else:
                    label = "mentioned_time_reference"

                key = (label, normalized)
                if key not in seen:
                    seen.add(key)
                    results.append({
                        "label": label,
                        "value": normalized
                    })

        return results[: self.MAX_DATES]

    def _extract_parties(self, text: str, document_type: str) -> list[str]:
        parties: list[str] = []

        role_keywords = [
            "Landlord", "Tenant", "Buyer", "Seller", "Lessor", "Lessee",
            "Plaintiff", "Defendant", "Claimant", "Respondent", "Employer", "Employee"
        ]

        for role in role_keywords:
            if re.search(rf"\b{re.escape(role)}\b", text, flags=re.IGNORECASE):
                self._append_unique(parties, role)

        between_match = re.search(
            r"\bbetween\s+(.{2,80}?)\s+and\s+(.{2,80}?)(?:[\.,;\n]|$)",
            text,
            flags=re.IGNORECASE
        )
        if between_match:
            left = self._clean_party_name(between_match.group(1))
            right = self._clean_party_name(between_match.group(2))

            if self._is_valid_party_name(left):
                self._append_unique(parties, left)
            if self._is_valid_party_name(right):
                self._append_unique(parties, right)

        named_patterns = [
            r"\bplaintiff[:\s]+([A-Z][A-Za-z0-9&,\.\-\s]{2,80})",
            r"\bdefendant[:\s]+([A-Z][A-Za-z0-9&,\.\-\s]{2,80})",
            r"\bclaimant[:\s]+([A-Z][A-Za-z0-9&,\.\-\s]{2,80})",
            r"\brespondent[:\s]+([A-Z][A-Za-z0-9&,\.\-\s]{2,80})",
            r"\blandlord[:\s]+([A-Z][A-Za-z0-9&,\.\-\s]{2,80})",
            r"\btenant[:\s]+([A-Z][A-Za-z0-9&,\.\-\s]{2,80})",
        ]

        for pattern in named_patterns:
            matches = re.findall(pattern, text, flags=re.IGNORECASE)
            for match in matches:
                cleaned = self._clean_party_name(match)
                if self._is_valid_party_name(cleaned):
                    self._append_unique(parties, cleaned)

        if document_type == "contract" and not parties:
            if "landlord" in text.lower():
                self._append_unique(parties, "Landlord")
            if "tenant" in text.lower():
                self._append_unique(parties, "Tenant")

        cleaned_parties: list[str] = []

        for party in parties:
            p = party.strip()

            if p.lower().startswith("the "):
                p = p[4:]

            if len(p) < 3:
                continue

            if any(bad in p.lower() for bad in [
                "and the", "agrees to", "this document", "under the terms"
            ]):
                continue

            if p not in cleaned_parties:
                cleaned_parties.append(p)

        return cleaned_parties[: self.MAX_PARTIES]

    def _detect_legal_risks(
        self,
        text: str,
        document_type: str,
        parties_detected: list[str],
        important_dates: list[dict[str, str]]
    ) -> list[str]:
        lowered = text.lower()
        risks: list[str] = []

        if len(text.strip()) < 300:
            risks.append("The extracted text is relatively short, which may indicate incomplete processing or limited legal context.")

        if document_type == "contract":
            if len(parties_detected) < 2:
                risks.append("The contractual parties are not clearly identified, which may require manual review.")

            if "payment" not in lowered and "rent" not in lowered:
                risks.append("No clear payment obligation was detected in this contract-like document.")

            if "termination" not in lowered:
                risks.append("No explicit termination clause was detected.")

            if "governing law" not in lowered and "applicable law" not in lowered:
                risks.append("No governing law clause was clearly detected.")

            if "signature" not in lowered and "signed" not in lowered:
                risks.append("No clear signature reference was detected in the contract text.")

            if "security deposit" in lowered and "refundable" not in lowered:
                risks.append("A deposit is mentioned, but refund conditions may require closer review.")

        if "[redacted_" in lowered or "[redacted]" in lowered:
            risks.append("This document contains redacted content that may hide legally relevant information.")

        if any(item["label"] in {"urgent_deadline", "deadline_or_time_limit", "notice_period"} for item in important_dates):
            risks.append("The document contains deadlines or notice periods that may require timeline monitoring.")

        if "late fee" in lowered or "penalty" in lowered:
            risks.append("Penalty or late-fee language was detected and should be reviewed for enforceability and clarity.")

        return risks[: self.MAX_RISKS]

    def _recommend_next_actions(
        self,
        document_type: str,
        legal_risks: list[str],
        important_dates: list[dict[str, str]],
        parties_detected: list[str]
    ) -> list[str]:
        actions: list[str] = []

        if document_type == "contract":
            actions.append("Review the contract clauses governing obligations, payment terms, termination, and dispute-related provisions.")
        elif document_type == "court_judgment":
            actions.append("Review the judgment outcome, legal reasoning, and possible appeal implications.")
        elif document_type == "invoice":
            actions.append("Verify the invoiced amounts, payment schedule, and any overdue balances.")
        elif document_type == "complaint":
            actions.append("Review the allegations, requested remedies, and factual support presented in the complaint.")
        else:
            actions.append("Review the document manually to confirm its legal relevance, context, and operational impact.")

        if len(parties_detected) >= 2:
            actions.append("Verify the identity and role of each detected party against the rest of the case file.")

        if important_dates:
            actions.append("Validate the extracted dates and time references, then add critical deadlines to the case timeline.")

        if legal_risks:
            actions.append("Prioritize manual legal review of the detected risk indicators before relying on the document operationally.")

        actions.append("Cross-check this document against related case documents for consistency, contradictions, and missing context.")

        return self._deduplicate(actions)[: self.MAX_ACTIONS]

    def _split_sentences(self, text: str) -> list[str]:
        raw_sentences = re.split(r"(?<=[\.\!\?])\s+", text)
        cleaned = []

        for sentence in raw_sentences:
            s = sentence.strip()
            if len(s) >= 25:
                cleaned.append(s)

        return cleaned

    def _rank_sentences(self, sentences: list[str]) -> list[str]:
        def score(sentence: str) -> int:
            lowered = sentence.lower()
            points = 0

            for keyword in self.LEGAL_KEYWORDS:
                if keyword in lowered:
                    points += 3

            if re.search(r"\b\d{4}-\d{2}-\d{2}\b", sentence):
                points += 2
            if re.search(r"\b\d{1,2}/\d{1,2}/\d{2,4}\b", sentence):
                points += 2
            if re.search(r"\bwithin\s+\d+\s+days?\b", lowered):
                points += 2
            if re.search(r"\b\d{1,3}-day\s+written\s+notice\b", lowered):
                points += 3
            if len(sentence) > 80:
                points += 1
            if len(sentence) > 160:
                points += 1

            return points

        return sorted(sentences, key=score, reverse=True)

    def _label_date_from_context(self, text: str, date: str) -> str:
        around = self._extract_context_around_value(text, date).lower()

        if "hearing" in around or "audience" in around:
            return "hearing_date"
        if "effective date" in around or "start date" in around:
            return "contract_start_date"
        if "deadline" in around or "due date" in around or "payment due" in around:
            return "deadline_or_due_date"
        if "termination" in around or "notice period" in around:
            return "termination_related_date"

        return "mentioned_date"

    def _extract_context_around_value(self, text: str, value: str, window: int = 80) -> str:
        index = text.find(value)
        if index == -1:
            return value

        start = max(0, index - window)
        end = min(len(text), index + len(value) + window)
        return text[start:end]

    def _normalize_summary_sentence(self, sentence: str) -> str:
        cleaned = re.sub(r"\s+", " ", sentence).strip()
        cleaned = cleaned.replace("\\n", " ")

        cleaned = re.sub(r"\b(sample document)\b", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\(\s*\)", "", cleaned)

        cleaned = re.sub(r"\s{2,}", " ", cleaned).strip(" ,;:-")
        return cleaned

    def _clean_party_name(self, value: str) -> str:
        cleaned = value.replace("\n", " ")
        cleaned = re.sub(r"\s+", " ", cleaned).strip(" ,.;:-")

        stop_markers = [
            "this document",
            "under the terms",
            "located at",
            "agrees to",
            "shall",
            "may",
            "is a",
            "for the"
        ]

        lowered = cleaned.lower()
        for marker in stop_markers:
            index = lowered.find(marker)
            if index > 0:
                cleaned = cleaned[:index].strip(" ,.;:-")
                lowered = cleaned.lower()

        return cleaned

    def _is_valid_party_name(self, value: str) -> bool:
        if not value or len(value) < 2:
            return False

        lowered = value.lower()

        invalid_fragments = [
            "this document",
            "used to test",
            "question answering",
            "example contract",
            "under the terms",
            "located at"
        ]

        if any(fragment in lowered for fragment in invalid_fragments):
            return False

        if len(value) > 50:
            return False

        return True

    def _append_unique(self, items: list[str], value: str) -> None:
        if value not in items:
            items.append(value)

    def _deduplicate(self, items: list[str]) -> list[str]:
        deduplicated = []
        for item in items:
            if item not in deduplicated:
                deduplicated.append(item)
        return deduplicated


document_insight_service = DocumentInsightService()