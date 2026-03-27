from __future__ import annotations

import json
import re
from typing import Any

from backend.models.document import Document
from backend.services.ai.document_classifier_service import document_classifier_service
from backend.services.ai.legal_text_formatter import LegalTextFormatter


class DocumentInsightService:
    MAX_INPUT_CHARS = 30000
    MAX_KEY_POINTS = 8
    MAX_DATES = 8
    MAX_PARTIES = 6
    MAX_RISKS = 8
    MAX_ACTIONS = 8
    MAX_MISSING_EVIDENCE = 5
    MAX_PAYMENT_TERMS = 4
    MAX_TERMINATION_TERMS = 4

    MONTH_NAMES = (
        "january|february|march|april|may|june|july|august|"
        "september|october|november|december"
    )

    GENERIC_ROLES = [
        "Landlord", "Tenant", "Buyer", "Seller", "Lessor", "Lessee",
        "Plaintiff", "Defendant", "Claimant", "Respondent",
        "Employer", "Employee", "Supplier", "Recipient",
    ]

    LEGAL_KEYWORDS = [
        "agreement", "contract", "court", "judge", "claim", "payment",
        "deadline", "termination", "liability", "obligation", "invoice",
        "hearing", "appeal", "article", "law", "damages", "evidence",
        "rent", "tenant", "landlord", "deposit", "notice", "breach",
        "supplier", "buyer", "defect", "delivery", "settlement",
        "cure period", "amicable settlement", "formal notice", "material breach",
    ]

    NOISY_PARTY_FRAGMENTS = [
        "invoice records",
        "warehouse logs",
        "question answering",
        "key dates",
        "document overview",
        "used to test",
        "prepared for testing",
        "under the terms",
        "located at",
        "payment terms",
        "recommended next steps",
        "main issues",
        "important dates",
        "legal risks",
        "missing evidence",
        "summary",
        "overview",
        "invoice number",
        "invoice date",
        "invoice due date",
        "order date",
        "document type",
        "jurisdiction",
        "this case concerns",
        "commercial dispute between",
        "confidential internal note",
    ]

    SECTION_HEADERS = {
        "overview",
        "summary",
        "main issues",
        "key dates",
        "important dates",
        "legal risks",
        "missing evidence",
        "recommended next steps",
        "recommended actions",
        "payment terms",
        "termination terms",
        "document overview",
        "case overview",
        "client",
    }

    MISSING_EVIDENCE_HINTS = [
        "signed delivery slip",
        "delivery slip",
        "warehouse entry log",
        "proof of handover",
        "delivery timestamp",
        "technical report",
        "technical inspection report",
        "inspection report",
        "expert report",
        "laboratory defect report",
        "defect report",
        "photo",
        "photos",
        "authenticated timestamp",
        "email acknowledgment",
        "proof of receipt",
        "courier proof of receipt",
        "server log",
        "accounting statement",
        "resale contract",
        "downstream loss document",
    ]

    PAYMENT_PATTERNS = [
        r"payment shall be made within [^.\n]{10,120}",
        r"payment is due within [^.\n]{10,120}",
        r"payment shall be due within [^.\n]{10,120}",
        r"amount due[:\s]+[^.\n]{5,80}",
        r"total unpaid amount[^.\n]{5,80}",
        r"invoice amount[:\s]+[^.\n]{5,80}",
    ]

    TERMINATION_PATTERNS = [
        r"either party may terminate[^.\n]{10,120}",
        r"cure period of [^.\n]{5,80}",
        r"granted a cure period of [^.\n]{5,80}",
        r"written notice of the breach[^.\n]{10,120}",
        r"material breach[^.\n]{5,120}",
    ]

    def build_insights(self, document: Document) -> dict[str, Any]:
        source_text = document.redacted_text or document.extracted_text

        if not source_text or not source_text.strip():
            raise ValueError("Document has no processed text available for intelligence extraction.")

        text = LegalTextFormatter.prepare_for_summary(source_text, max_chars=self.MAX_INPUT_CHARS)
        sanitized_text = self._remove_structured_sections(text)

        classification = document_classifier_service.classify(sanitized_text)

        parties_detected = self._extract_parties(sanitized_text, classification.document_type)
        important_dates = self._extract_important_dates(sanitized_text)
        payment_terms = self._extract_payment_terms(sanitized_text)
        termination_terms = self._extract_termination_terms(sanitized_text)
        missing_evidence = self._extract_missing_evidence(sanitized_text)

        legal_risks = self._detect_legal_risks(
            text=sanitized_text,
            document_type=classification.document_type,
            parties_detected=parties_detected,
            important_dates=important_dates,
            payment_terms=payment_terms,
            termination_terms=termination_terms,
            missing_evidence=missing_evidence,
        )

        recommended_actions = self._recommend_next_actions(
            text=sanitized_text,
            document_type=classification.document_type,
            legal_risks=legal_risks,
            important_dates=important_dates,
            missing_evidence=missing_evidence,
        )

        key_points = self._extract_key_points(
            text=sanitized_text,
            important_dates=important_dates,
            payment_terms=payment_terms,
            termination_terms=termination_terms,
            missing_evidence=missing_evidence,
            legal_risks=legal_risks,
        )

        general_summary = self._generate_general_summary(
            document_type=classification.document_type,
            parties_detected=parties_detected,
            important_dates=important_dates,
            payment_terms=payment_terms,
            termination_terms=termination_terms,
            legal_risks=legal_risks,
            missing_evidence=missing_evidence,
        )

        return {
            "document_type": classification.document_type,
            "document_type_confidence": classification.confidence,
            "general_summary": general_summary,
            "key_points": key_points,
            "important_dates": important_dates,
            "parties_detected": parties_detected,
            "payment_terms": payment_terms,
            "termination_terms": termination_terms,
            "missing_evidence": missing_evidence,
            "legal_risks": legal_risks,
            "recommended_actions": recommended_actions,
            "summary_source": "elite_heuristic",
            "summary_version": "v9",
        }

    def to_json_string(self, insights: dict[str, Any]) -> str:
        return json.dumps(insights, ensure_ascii=False)

    def _generate_general_summary(
        self,
        document_type: str,
        parties_detected: list[str],
        important_dates: list[dict[str, str]],
        payment_terms: list[str],
        termination_terms: list[str],
        legal_risks: list[str],
        missing_evidence: list[str],
    ) -> str:
        intro_map = {
            "contract": "This document is a contract or contract-related record.",
            "court_judgment": "This document is a court judgment or court-related decision.",
            "invoice": "This document is an invoice or payment-related billing record.",
            "legal_letter": "This document is a legal letter or formal notice.",
            "complaint": "This document is a complaint or adversarial pleading.",
            "identity_document": "This document is an identity-related document.",
            "evidence_attachment": "This document is a supporting evidence attachment.",
            "case_memo": "This document is an internal legal case memo.",
            "unknown": "This document concerns legal or administrative matters.",
        }

        parts: list[str] = [intro_map.get(document_type, intro_map["unknown"])]

        named_parties = [p for p in parties_detected if p not in self.GENERIC_ROLES]
        role_parties = [p for p in parties_detected if p in self.GENERIC_ROLES]

        if named_parties:
            parts.append("The main named parties are " + ", ".join(named_parties[:2]) + ".")
        elif role_parties:
            parts.append("The main legal roles identified are " + ", ".join(role_parties[:3]) + ".")

        if payment_terms:
            parts.append("The document includes a payment obligation.")
        if termination_terms:
            parts.append("The document includes termination or notice-related mechanics.")
        if important_dates:
            parts.append("The document contains relevant dates or time limits.")
        if legal_risks:
            parts.append("Potential legal or evidentiary risks were detected.")
        if missing_evidence:
            parts.append("Possible gaps in supporting evidence were also identified.")

        return self._normalize_summary_sentence(" ".join(parts))

    def _extract_key_points(
        self,
        text: str,
        important_dates: list[dict[str, str]],
        payment_terms: list[str],
        termination_terms: list[str],
        missing_evidence: list[str],
        legal_risks: list[str],
    ) -> list[str]:
        key_points: list[str] = []

        for item in payment_terms[:2]:
            self._append_unique(key_points, f"Payment term: {item}")

        for item in termination_terms[:2]:
            self._append_unique(key_points, f"Termination term: {item}")

        for item in important_dates[:2]:
            label = self._normalize_summary_sentence(item.get("label", "date")).replace("_", " ")
            value = self._normalize_summary_sentence(item.get("value", ""))
            if value and label != "mentioned date":
                self._append_unique(key_points, f"{label}: {value}")

        for item in legal_risks[:2]:
            self._append_unique(key_points, f"Risk: {item}")

        for item in missing_evidence[:2]:
            self._append_unique(key_points, f"Missing evidence: {item}")

        for sentence in self._fallback_summary_sentences(text):
            self._append_unique(key_points, sentence)
            if len(key_points) >= self.MAX_KEY_POINTS:
                break

        return key_points[:self.MAX_KEY_POINTS]

    def _extract_important_dates(self, text: str) -> list[dict[str, str]]:
        absolute_patterns = [
            rf"\b\d{{1,2}}\s+(?:{self.MONTH_NAMES})\s+\d{{4}}\b",
            r"\b\d{4}-\d{2}-\d{2}\b",
            r"\b\d{1,2}/\d{1,2}/\d{2,4}\b",
            r"\b\d{1,2}-\d{1,2}-\d{2,4}\b",
        ]

        relative_patterns = [
            r"\bwithin\s+\d+\s+business\s+days\b",
            r"\bwithin\s+\d+\s+calendar\s+days\b",
            r"\bwithin\s+\d+\s+days\b",
            r"\bwithin\s+\d+\s+hours\b",
            r"\b\d{1,3}-day\s+written\s+notice\b",
            r"\b\d{1,3}\s+day\s+written\s+notice\b",
            r"\bfirst day of each month\b",
            r"\bcure period of\s+\d+\s+(?:business\s+)?days\b",
            r"\bamicable settlement period\b",
        ]

        results: list[dict[str, str]] = []
        seen: set[tuple[str, str]] = set()

        for pattern in absolute_patterns:
            for match in re.finditer(pattern, text, flags=re.IGNORECASE):
                raw_value = match.group(0)
                value = self._normalize_date_value(raw_value)
                label = self._label_date_from_context(text, raw_value)
                key = (label, value.lower())

                if label == "mentioned_date":
                    continue
                if key in seen:
                    continue

                seen.add(key)
                results.append({"label": label, "value": value})

        for pattern in relative_patterns:
            for match in re.finditer(pattern, text, flags=re.IGNORECASE):
                value = self._normalize_summary_sentence(match.group(0))
                lowered = value.lower()

                if "notice" in lowered:
                    label = "notice_period"
                elif "cure period" in lowered:
                    label = "cure_period"
                elif "settlement period" in lowered:
                    label = "settlement_period"
                elif "first day of each month" in lowered:
                    label = "recurring_payment_date"
                else:
                    label = "deadline_or_time_limit"

                key = (label, value.lower())
                if key in seen:
                    continue

                seen.add(key)
                results.append({"label": label, "value": value})

        results = sorted(
            results,
            key=lambda x: self._rank_date_priority(x["label"]),
            reverse=True
        )

        return results[:self.MAX_DATES]

    def _rank_date_priority(self, label: str) -> int:
        priority_map = {
            "contract_start_date": 10,
            "invoice_due_date": 9,
            "hearing_date": 9,
            "invoice_date": 8,
            "notice_date": 8,
            "deadline_or_due_date": 8,
            "cure_period_related_date": 7,
            "settlement_related_date": 7,
            "delivery_date": 6,
            "order_date": 5,
            "response_date": 5,
            "recurring_payment_date": 4,
            "deadline_or_time_limit": 4,
            "notice_period": 4,
            "cure_period": 4,
            "settlement_period": 4,
        }
        return priority_map.get(label, 1)

    def _extract_parties(self, text: str, document_type: str) -> list[str]:
        named_parties: list[str] = []
        role_parties: list[str] = []

        case_title_match = re.search(r"(?i)case title\s*:\s*([^\n]+)", text)
        if case_title_match:
            title = self._normalize_summary_sentence(case_title_match.group(1))
            split_parties = re.split(r"(?i)\s+v\.?\s+|\s+vs\.?\s+", title)
            for part in split_parties[:2]:
                cleaned = self._clean_party_name(part)
                if self._is_valid_party_name(cleaned):
                    self._append_unique(named_parties, cleaned)

        corporate_patterns = [
            r"\b([A-Z][A-Za-z0-9&,\.\-\s]{1,60}\s+SARL)\b",
            r"\b([A-Z][A-Za-z0-9&,\.\-\s]{1,60}\s+LLC)\b",
            r"\b([A-Z][A-Za-z0-9&,\.\-\s]{1,60}\s+Ltd)\b",
            r"\b([A-Z][A-Za-z0-9&,\.\-\s]{1,60}\s+Inc)\b",
            r"\b([A-Z][A-Za-z0-9&,\.\-\s]{1,60}\s+GmbH)\b",
            r"\b([A-Z][A-Za-z0-9&,\.\-\s]{1,60}\s+SA)\b",
        ]

        for pattern in corporate_patterns:
            for match in re.finditer(pattern, text):
                cleaned = self._clean_party_name(match.group(1))
                if self._is_valid_party_name(cleaned):
                    self._append_unique(named_parties, cleaned)

        between_match = re.search(
            r"\bbetween\s+(.{2,80}?)\s+and\s+(.{2,80}?)(?:[\.,;\n]|$)",
            text,
            flags=re.IGNORECASE,
        )
        if between_match:
            left = self._clean_party_name(between_match.group(1))
            right = self._clean_party_name(between_match.group(2))

            if self._is_valid_party_name(left):
                self._append_unique(named_parties, left)
            if self._is_valid_party_name(right):
                self._append_unique(named_parties, right)

        named_patterns = [
            r"\bclaimant\s*/\s*supplier\s*:\s*([A-Z][A-Za-z0-9&,\.\-\s]{2,80})",
            r"\brespondent\s*/\s*buyer\s*:\s*([A-Z][A-Za-z0-9&,\.\-\s]{2,80})",
            r"\bplaintiff[:\s]+([A-Z][A-Za-z0-9&,\.\-\s]{2,80})",
            r"\bdefendant[:\s]+([A-Z][A-Za-z0-9&,\.\-\s]{2,80})",
            r"\bclaimant[:\s]+([A-Z][A-Za-z0-9&,\.\-\s]{2,80})",
            r"\brespondent[:\s]+([A-Z][A-Za-z0-9&,\.\-\s]{2,80})",
            r"\blandlord[:\s]+([A-Z][A-Za-z0-9&,\.\-\s]{2,80})",
            r"\btenant[:\s]+([A-Z][A-Za-z0-9&,\.\-\s]{2,80})",
            r"\bsender[:\s]+([A-Z][A-Za-z0-9&,\.\-\s]{2,80})",
            r"\brecipient[:\s]+([A-Z][A-Za-z0-9&,\.\-\s]{2,80})",
        ]

        for pattern in named_patterns:
            for match in re.findall(pattern, text, flags=re.IGNORECASE):
                cleaned = self._clean_party_name(match)
                if self._is_valid_party_name(cleaned):
                    self._append_unique(named_parties, cleaned)

        for role in self.GENERIC_ROLES:
            if re.search(rf"\b{re.escape(role)}\b", text, flags=re.IGNORECASE):
                self._append_unique(role_parties, role)

        if document_type == "contract" and not named_parties and not role_parties:
            if "landlord" in text.lower():
                self._append_unique(role_parties, "Landlord")
            if "tenant" in text.lower():
                self._append_unique(role_parties, "Tenant")

        final_parties: list[str] = []
        for party in named_parties + role_parties:
            if party not in final_parties:
                final_parties.append(party)

        return final_parties[:self.MAX_PARTIES]

    def _extract_payment_terms(self, text: str) -> list[str]:
        results: list[str] = []

        for pattern in self.PAYMENT_PATTERNS:
            for match in re.finditer(pattern, text, flags=re.IGNORECASE):
                cleaned = self._normalize_summary_sentence(match.group(0))

                lowered = cleaned.lower()
                if "total unpaid amount" in lowered:
                    cleaned = re.sub(
                        r"(?i)^total unpaid amount claimed as immediately due by\s+",
                        "Outstanding amount: ",
                        cleaned,
                    )
                elif lowered.startswith("amount due"):
                    cleaned = re.sub(r"(?i)^amount due[:\s]*", "Amount due: ", cleaned)

                if not self._is_clean_text(cleaned):
                    continue
                if len(cleaned) < 15:
                    continue

                self._append_unique(results, cleaned)

        return results[:self.MAX_PAYMENT_TERMS]

    def _extract_termination_terms(self, text: str) -> list[str]:
        results: list[str] = []

        for pattern in self.TERMINATION_PATTERNS:
            for match in re.finditer(pattern, text, flags=re.IGNORECASE):
                raw = match.group(0)
                cleaned = self._normalize_summary_sentence(raw)
                lowered = cleaned.lower()

                if "cure period" in lowered:
                    period_match = re.search(r"(?i)cure period of ([^.,\n]+)", cleaned)
                    if period_match:
                        cleaned = f"A cure period of {period_match.group(1).strip()} is provided before termination."
                    else:
                        cleaned = "A cure period is provided before termination."

                elif "terminate" in lowered and "material breach" in lowered:
                    cleaned = "Either party may terminate the agreement in case of a material breach."

                elif "written notice" in lowered:
                    cleaned = "Termination requires prior written notice."

                elif "material breach" in lowered:
                    cleaned = "Termination rights are triggered by a material breach."

                cleaned = cleaned.replace("expir", "expire")
                cleaned = re.sub(r"\s*,\s*-\s*", ", ", cleaned)

                if not self._is_clean_text(cleaned):
                    continue
                if len(cleaned) < 20:
                    continue

                self._append_unique(results, cleaned)

        return results[:self.MAX_TERMINATION_TERMS]

    def _extract_missing_evidence(self, text: str) -> list[str]:
        results: list[str] = []

        for line in text.splitlines():
            stripped = line.strip(" -•\t")
            if not stripped:
                continue

            lowered = stripped.lower()

            if lowered.rstrip(":") in self.SECTION_HEADERS:
                continue
            if lowered.startswith("records:"):
                continue
            if any(header in lowered for header in self.SECTION_HEADERS):
                continue

            if any(hint in lowered for hint in self.MISSING_EVIDENCE_HINTS):
                cleaned = self._trim_missing_evidence(stripped)
                if self._is_reasonable_missing_evidence(cleaned):
                    self._append_unique(results, cleaned)

            if lowered.startswith(("did not attach", "no signed", "no ", "missing ")):
                cleaned = self._trim_missing_evidence(stripped)
                if self._is_reasonable_missing_evidence(cleaned):
                    self._append_unique(results, cleaned)

        return results[:self.MAX_MISSING_EVIDENCE]

    def _detect_legal_risks(
        self,
        text: str,
        document_type: str,
        parties_detected: list[str],
        important_dates: list[dict[str, str]],
        payment_terms: list[str],
        termination_terms: list[str],
        missing_evidence: list[str],
    ) -> list[str]:
        lowered = text.lower()
        risks: list[str] = []

        if len(text.strip()) < 300:
            risks.append("The extracted text is relatively short, which may indicate incomplete processing or limited legal context.")

        if document_type == "contract":
            named_parties = [p for p in parties_detected if p not in self.GENERIC_ROLES]

            if len(parties_detected) < 2:
                risks.append("The contractual parties are not clearly identified and may require manual verification.")
            if not payment_terms and "rent" not in lowered:
                risks.append("No clear payment obligation was confidently extracted from this contract-like document.")
            if not termination_terms and "termination" not in lowered:
                risks.append("No explicit termination mechanics were confidently extracted.")
            if "governing law" not in lowered and "applicable law" not in lowered:
                risks.append("No governing law clause was clearly detected.")
            if "signature" not in lowered and "signed" not in lowered:
                risks.append("No clear signature reference was detected in the contract text.")
            if named_parties and len(named_parties) < 2 and len(parties_detected) >= 2:
                risks.append("The document identifies legal roles more clearly than fully named parties, so party resolution may require manual review.")

        if "[redacted_" in lowered:
            risks.append("The document contains redacted content that may hide legally relevant information.")

        if any(item["label"] in {"deadline_or_time_limit", "notice_period", "cure_period"} for item in important_dates):
            risks.append("The document contains deadlines or notice periods that may require active timeline monitoring.")

        if missing_evidence:
            risks.append("Potential evidentiary gaps were detected and may weaken the legal position.")

        if "late fee" in lowered or "late penalty" in lowered or "penalty" in lowered:
            risks.append("Penalty or late-fee language was detected and should be reviewed for enforceability and clarity.")

        if "premature" in lowered or "terminate too early" in lowered:
            risks.append("The file references a risk of premature termination.")

        if "amicable settlement period" in lowered:
            risks.append("There may be a procedural risk if litigation begins before the amicable settlement period ends.")

        if "discrep" in lowered or "inconsistent" in lowered or "conflict" in lowered:
            risks.append("Potential factual inconsistencies or conflicting records were detected and should be reconciled.")

        return self._deduplicate(risks)[:self.MAX_RISKS]

    def _recommend_next_actions(
        self,
        text: str,
        document_type: str,
        legal_risks: list[str],
        important_dates: list[dict[str, str]],
        missing_evidence: list[str],
    ) -> list[str]:
        actions: list[str] = []

        if document_type == "contract":
            actions.append("Review the clauses governing obligations, payment terms, termination mechanics, and dispute resolution.")
        elif document_type == "court_judgment":
            actions.append("Review the judgment outcome, legal reasoning, and appeal implications.")
        elif document_type == "invoice":
            actions.append("Verify the invoiced amounts, payment schedule, and any overdue balances.")
        elif document_type == "complaint":
            actions.append("Review the allegations, requested remedies, and factual support presented in the complaint.")
        elif document_type == "case_memo":
            actions.append("Review the internal memo findings and validate them against the underlying primary documents.")
        else:
            actions.append("Review the document manually to confirm its legal relevance, context, and operational impact.")

        if important_dates:
            actions.append("Validate the extracted dates and time references, then add critical deadlines to the case timeline.")

        if missing_evidence:
            actions.append("Collect and verify the missing evidence or supporting proof referenced in the document.")

        if legal_risks:
            actions.append("Prioritize manual legal review of the detected risk indicators before relying on the document operationally.")

        if "compare" in text.lower() or "inconsistent" in text.lower() or "discrep" in text.lower():
            actions.append("Cross-check this document against related case documents for contradictions and inconsistent factual timelines.")
        else:
            actions.append("Cross-check this document against related case documents for consistency and missing context.")

        return self._deduplicate(actions)[:self.MAX_ACTIONS]

    def _fallback_summary_sentences(self, text: str) -> list[str]:
        sentences = self._split_sentences(text)
        ranked = self._rank_sentences(sentences)

        results: list[str] = []
        for sentence in ranked:
            cleaned = self._normalize_summary_sentence(sentence)
            if not self._is_clean_text(cleaned):
                continue
            if cleaned and cleaned not in results:
                results.append(cleaned)
            if len(results) >= 2:
                break

        return results

    def _split_sentences(self, text: str) -> list[str]:
        normalized = text.replace("\n", " ")
        raw_sentences = re.split(r"(?<=[\.\!\?])\s+", normalized)

        cleaned: list[str] = []
        for sentence in raw_sentences:
            normalized_sentence = self._normalize_summary_sentence(sentence)
            if len(normalized_sentence) >= 25 and self._is_clean_text(normalized_sentence):
                cleaned.append(normalized_sentence)

        return cleaned

    def _rank_sentences(self, sentences: list[str]) -> list[str]:
        def score(sentence: str) -> int:
            lowered = sentence.lower()
            points = 0

            for keyword in self.LEGAL_KEYWORDS:
                if keyword in lowered:
                    points += 3

            if re.search(rf"\b\d{{1,2}}\s+(?:{self.MONTH_NAMES})\s+\d{{4}}\b", sentence, flags=re.IGNORECASE):
                points += 3
            if re.search(r"\b\d{4}-\d{2}-\d{2}\b", sentence):
                points += 2
            if re.search(r"\b\d{1,2}/\d{1,2}/\d{2,4}\b", sentence):
                points += 2
            if re.search(r"\bwithin\s+\d+\s+(business\s+)?days?\b", lowered):
                points += 2
            if re.search(r"\b\d{1,3}-day\s+written\s+notice\b", lowered):
                points += 3
            if "formal notice" in lowered:
                points += 3
            if "material breach" in lowered:
                points += 3
            if "total unpaid amount" in lowered:
                points += 3
            if "missing evidence" in lowered or "did not attach" in lowered:
                points += 2

            return points

        return sorted(sentences, key=score, reverse=True)

    def _label_date_from_context(self, text: str, date: str) -> str:
        around = self._extract_context_around_value(text, date).lower()

        if "invoice due date" in around or "payment due date" in around:
            return "invoice_due_date"
        if "invoice date" in around:
            return "invoice_date"
        if "order date" in around:
            return "order_date"
        if "delivery date" in around or "receipt on" in around:
            return "delivery_date"
        if "hearing" in around or "audience" in around:
            return "hearing_date"
        if "effective date" in around or "start date" in around or "agreement signed" in around:
            return "contract_start_date"
        if "breach notice" in around or "formal notice" in around or "date of notice" in around:
            return "notice_date"
        if "cure period" in around:
            return "cure_period_related_date"
        if "settlement period" in around or "amicable settlement" in around:
            return "settlement_related_date"
        if "deadline" in around:
            return "deadline_or_due_date"
        if "response" in around:
            return "response_date"

        return "mentioned_date"

    def _extract_context_around_value(self, text: str, value: str, window: int = 120) -> str:
        index = text.lower().find(value.lower())
        if index == -1:
            return value

        start = max(0, index - window)
        end = min(len(text), index + len(value) + window)
        return text[start:end]

    def _remove_structured_sections(self, text: str) -> str:
        lines = text.splitlines()
        cleaned_lines: list[str] = []

        for line in lines:
            lowered = line.strip().lower().rstrip(":")
            if lowered in self.SECTION_HEADERS:
                continue
            cleaned_lines.append(line)

        return "\n".join(cleaned_lines)

    @staticmethod
    def _normalize_summary_sentence(sentence: str) -> str:
        cleaned = sentence.replace("\\n", " ").replace("\n", " ")
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        cleaned = re.sub(r"\(\s*\)", "", cleaned)
        return re.sub(r"\s{2,}", " ", cleaned).strip(" ,;:-")

    @staticmethod
    def _normalize_date_value(value: str) -> str:
        cleaned = value.replace("\n", " ")
        return re.sub(r"\s+", " ", cleaned).strip()

    def _clean_party_name(self, value: str) -> str:
        cleaned = value.replace("\n", " ")
        cleaned = re.sub(r"\s+", " ", cleaned).strip(" ,.;:-")

        stop_markers = [
            "this document",
            "this case concerns",
            "commercial dispute between",
            "under the terms",
            "located at",
            "agrees to",
            "shall",
            " may ",
            " is a ",
            "for the",
            "payment terms",
            "prepared for testing",
            "question answering",
            "key dates for",
            "document type",
            "jurisdiction",
            "invoice number",
            "invoice date",
            "order date",
        ]

        lowered = cleaned.lower()
        for marker in stop_markers:
            index = lowered.find(marker)
            if index >= 0:
                cleaned = cleaned[:index].strip(" ,.;:-")
                lowered = cleaned.lower()

        cleaned = re.sub(r"(?i)\s*[-–—:]?\s*(claimant|respondent|buyer|supplier|plaintiff|defendant|landlord|tenant|sender|recipient)\s*$", "", cleaned)
        cleaned = re.sub(r"(?i)\s+\bv\b\s*$", "", cleaned)
        cleaned = re.sub(r"(?i)\s+\bvs\.?\b\s*$", "", cleaned)

        if "," in cleaned:
            parts = [p.strip() for p in cleaned.split(",") if p.strip()]
            if parts:
                cleaned = parts[0]

        return cleaned.strip(" ,.;:-")

    def _is_valid_party_name(self, value: str) -> bool:
        if not value or len(value) < 2:
            return False

        lowered = value.lower()

        if any(fragment in lowered for fragment in self.NOISY_PARTY_FRAGMENTS):
            return False
        if len(value) > 70:
            return False
        if re.fullmatch(r"[=\-_/\\\d\s]+", value):
            return False
        if ":" in value:
            return False
        if lowered in {"v", "vs", "none", "unknown"}:
            return False
        if any(token in lowered for token in ["invoice", "date", "amount due", "payment due"]):
            return False
        if "," in value:
            return False

        return True

    def _trim_missing_evidence(self, value: str) -> str:
        cleaned = self._normalize_summary_sentence(value)

        for token in [" and ", " but ", " while ", " however ", ". ", "; "]:
            parts = cleaned.split(token)
            if parts:
                candidate = parts[0].strip()
                if len(candidate) >= 12:
                    cleaned = candidate
                    break

        cleaned = re.sub(r"(?i)^records:\s*", "", cleaned)
        return cleaned[:110].strip(" ,;:-")

    def _is_reasonable_missing_evidence(self, value: str) -> bool:
        if not value:
            return False

        lowered = value.lower()

        if len(value) < 8:
            return False
        if len(value) > 110:
            return False
        if lowered in {"missing", "proof of", "no"}:
            return False
        if any(header in lowered for header in self.SECTION_HEADERS):
            return False
        if lowered.startswith("risk that "):
            return False
        if lowered.startswith("records:"):
            return False

        return True

    def _is_clean_text(self, value: str) -> bool:
        lowered = value.lower().strip()

        if len(lowered) < 5:
            return False

        blocked_fragments = [
            "question answering",
            "used to test",
            "sample document",
            "invoice number",
            "order date",
            "summary:",
            "overview:",
            "main issues:",
            "key dates:",
            "legal risks:",
            "missing evidence:",
            "recommended next steps:",
            "document overview",
            "prepared for testing",
            "this case concerns",
            "commercial dispute between",
        ]

        if any(fragment in lowered for fragment in blocked_fragments):
            return False

        return True

    def _append_unique(self, items: list[str], value: str) -> None:
        cleaned = self._normalize_summary_sentence(value)

        if not cleaned:
            return
        if not self._is_clean_text(cleaned):
            return
        if cleaned not in items:
            items.append(cleaned)

    def _deduplicate(self, items: list[str]) -> list[str]:
        deduplicated: list[str] = []
        seen: set[str] = set()

        for item in items:
            normalized = self._normalize_summary_sentence(item).lower()
            if normalized and normalized not in seen:
                seen.add(normalized)
                deduplicated.append(self._normalize_summary_sentence(item))

        return deduplicated


document_insight_service = DocumentInsightService()