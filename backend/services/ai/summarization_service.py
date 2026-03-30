from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any

from sqlalchemy.orm import Session

from backend.models.document import Document
from backend.services.ai.agents.summarization_agent import summarization_agent
from backend.services.ai.artifact_versioning_service import artifact_versioning_service
from backend.services.ai.document_insight_service import document_insight_service
from backend.services.ai.legal_text_formatter import LegalTextFormatter


class SummarizationService:
    MIN_TEXT_LENGTH = 120
    MAX_INPUT_CHARS = 22000
    MAX_SHORT_SUMMARY_CHARS = 500

    GENERIC_ROLE_NAMES = {
        "Landlord", "Tenant", "Buyer", "Seller", "Lessor", "Lessee",
        "Plaintiff", "Defendant", "Claimant", "Respondent",
        "Employer", "Employee", "Supplier", "Recipient",
    }

    BLOCKED_SUMMARY_FRAGMENTS = {
        "question answering",
        "used to test",
        "sample document",
        "invoice number",
        "order date",
        "document overview",
        "summary:",
        "overview:",
        "main issues:",
        "legal risks:",
        "missing evidence:",
        "recommended next steps:",
        "this case concerns",
        "commercial dispute between",
    }

    def get_source_text(self, document: Document) -> str:
        source_text = document.redacted_text or document.extracted_text

        if not source_text or not source_text.strip():
            raise ValueError("Document has no processed text available for summarization.")

        return LegalTextFormatter.prepare_for_summary(source_text, max_chars=self.MAX_INPUT_CHARS)

    def summarize_document(self, db: Session, document: Document) -> Document:
        document.summary_status = "processing"
        document.summary_error = None
        db.commit()
        db.refresh(document)

        try:
            text = self.get_source_text(document)

            if len(text) < self.MIN_TEXT_LENGTH:
                raise ValueError("Processed document text is too short to summarize reliably.")

            temp_document = SimpleNamespace(
                extracted_text=text,
                redacted_text=None,
            )

            insights = document_insight_service.build_insights(temp_document)
            agent_result = summarization_agent.summarize_document(
                filename=document.filename,
                document_text=text,
                heuristic_insights=insights,
            )

            if agent_result and agent_result.get("summary"):
                long_summary = self._clean_summary_output(agent_result["summary"])
                short_summary = self._clean_summary_output(
                    agent_result.get("summary_short")
                    or self._build_short_summary(insights=agent_result, long_summary=long_summary)
                )

                insights["document_type"] = agent_result.get("document_type") or insights.get("document_type")
                insights["key_points"] = agent_result.get("key_points") or insights.get("key_points", [])
                insights["important_dates"] = agent_result.get("important_dates") or insights.get("important_dates", [])
                insights["parties_detected"] = agent_result.get("parties_detected") or insights.get("parties_detected", [])
                insights["legal_risks"] = agent_result.get("legal_risks") or insights.get("legal_risks", [])
                insights["recommended_actions"] = (
                    agent_result.get("recommended_actions") or insights.get("recommended_actions", [])
                )
                insights["summary_source"] = agent_result.get("summary_source") or "llm_summary_agent"
                insights["summary_version"] = agent_result.get("summary_version") or "v1"
            else:
                long_summary = self._build_final_summary(insights=insights)
                short_summary = self._build_short_summary(insights=insights, long_summary=long_summary)

            now = datetime.now(timezone.utc)

            document.summary = long_summary
            document.summary_short = short_summary
            document.summary_status = "completed"
            document.summary_error = None
            document.summary_generated_at = now

            document.document_type = insights.get("document_type")
            document.summary_version = insights.get("summary_version")
            document.summary_source = insights.get("summary_source")
            document.insights_json = document_insight_service.to_json_string(insights)
            document.last_intelligence_run_at = now

            db.commit()
            db.refresh(document)

            try:
                artifact_versioning_service.create_version(
                    db=db,
                    tenant_id=document.tenant_id,
                    artifact_type="document_summary",
                    content=document.summary or document.summary_short or "",
                    case_id=document.case_id,
                    document_id=document.id,
                    source_kind="agent_generation",
                    metadata={
                        "summary_short": document.summary_short,
                        "summary_source": document.summary_source,
                        "summary_version": document.summary_version,
                    },
                    auto_select=True,
                )
            except Exception:
                # Version history should never block summary generation itself.
                pass

            return document

        except Exception as exc:
            document.summary_status = "failed"
            document.summary_error = str(exc)
            document.last_intelligence_run_at = datetime.now(timezone.utc)

            db.commit()
            db.refresh(document)
            raise

    def regenerate_document_summary(self, db: Session, document: Document) -> Document:
        return self.summarize_document(db=db, document=document)

    def _build_final_summary(self, insights: dict[str, Any]) -> str:
        document_type = self._clean_text(insights.get("document_type", "unknown"))
        general_summary = self._clean_text(insights.get("general_summary", ""))

        parties = self._clean_parties(insights.get("parties_detected", []))
        important_dates = self._clean_date_items(insights.get("important_dates", []))
        payment_terms = self._clean_string_list(insights.get("payment_terms", []))
        termination_terms = self._clean_string_list(insights.get("termination_terms", []))
        missing_evidence = self._clean_string_list(insights.get("missing_evidence", []))
        legal_risks = self._clean_string_list(insights.get("legal_risks", []))
        recommended_actions = self._clean_string_list(insights.get("recommended_actions", []))
        key_points = self._clean_string_list(insights.get("key_points", []))

        sections: list[str] = []

        overview_lines: list[str] = []
        if general_summary:
            overview_lines.append(self._make_summary_more_assertive(general_summary))
        else:
            overview_lines.append(
                f"This document is a {document_type.replace('_', ' ')}."
                if document_type and document_type != "unknown"
                else "This document concerns legal or administrative matters."
            )

        named_parties = [p for p in parties if p not in self.GENERIC_ROLE_NAMES]
        role_parties = [p for p in parties if p in self.GENERIC_ROLE_NAMES]

        if named_parties:
            overview_lines.append("Main parties: " + ", ".join(named_parties[:2]) + ".")
        elif role_parties:
            overview_lines.append("Main roles mentioned: " + ", ".join(role_parties[:3]) + ".")

        sections.append("Overview:\n" + " ".join(overview_lines).strip())

        issues_lines: list[str] = []
        for item in key_points[:5]:
            cleaned = self._clean_text(item)
            if cleaned:
                issues_lines.append(f"- {cleaned}")

        if issues_lines:
            sections.append("Main Issues:\n" + "\n".join(issues_lines))

        obligations_lines: list[str] = []
        for item in payment_terms[:2]:
            obligations_lines.append(f"- Payment: {item}")
        for item in termination_terms[:2]:
            obligations_lines.append(f"- Termination / Notice: {item}")

        if obligations_lines:
            sections.append("Key Obligations / Clauses:\n" + "\n".join(obligations_lines))

        date_lines: list[str] = []
        for item in important_dates[:4]:
            label = self._clean_text(item.get("label", "date")).replace("_", " ")
            value = self._clean_text(item.get("value", ""))
            if value and label != "mentioned date":
                date_lines.append(f"- {value} ({label})")

        if date_lines:
            sections.append("Key Dates:\n" + "\n".join(date_lines))

        if legal_risks:
            sections.append("Legal Risks:\n" + "\n".join(f"- {risk}" for risk in legal_risks[:5]))

        if missing_evidence:
            sections.append(
                "Missing Evidence / Evidentiary Gaps:\n"
                + "\n".join(f"- {item}" for item in missing_evidence[:4])
            )

        if recommended_actions:
            sections.append(
                "Recommended Next Steps:\n"
                + "\n".join(f"- {action}" for action in recommended_actions[:5])
            )

        final_summary = "\n\n".join(section.strip() for section in sections if section.strip())
        return self._clean_summary_output(final_summary)

    def _build_short_summary(self, insights: dict[str, Any], long_summary: str) -> str:
        document_type = self._clean_text(insights.get("document_type", "unknown")).replace("_", " ")
        parties = self._clean_parties(insights.get("parties_detected", []))
        legal_risks = self._clean_string_list(insights.get("legal_risks", []))
        important_dates = self._clean_date_items(insights.get("important_dates", []))
        payment_terms = self._clean_string_list(insights.get("payment_terms", []))

        parts: list[str] = []

        if document_type and document_type != "unknown":
            parts.append(f"This document is a {document_type}.")
        else:
            parts.append("This document concerns legal or administrative matters.")

        named_parties = [p for p in parties if p not in self.GENERIC_ROLE_NAMES]
        if named_parties:
            parts.append("Main parties: " + ", ".join(named_parties[:2]) + ".")

        if payment_terms:
            parts.append("A payment obligation is identified in the document.")

        for date_item in important_dates:
            label = self._clean_text(date_item.get("label", "date")).replace("_", " ")
            value = self._clean_text(date_item.get("value", ""))
            if value and label != "mentioned date":
                parts.append(f"One important date is {value} ({label}).")
                break

        if legal_risks:
            parts.append("The document also presents at least one legal or evidentiary risk.")

        short_summary = self._clean_summary_output(" ".join(part.strip() for part in parts if part.strip()))

        if not short_summary:
            short_summary = long_summary

        if len(short_summary) <= self.MAX_SHORT_SUMMARY_CHARS:
            return short_summary

        trimmed = short_summary[:self.MAX_SHORT_SUMMARY_CHARS].rsplit(" ", 1)[0].strip()
        return trimmed + "..."

    def _make_summary_more_assertive(self, text: str) -> str:
        if not text:
            return ""

        text = text.replace("appears to be", "is")
        text = text.replace("appears to concern", "concerns")
        text = text.replace("may indicate", "indicates")
        return text

    def _clean_parties(self, items: list[Any]) -> list[str]:
        results: list[str] = []

        for item in items or []:
            cleaned = self._clean_text(str(item))
            if not cleaned:
                continue
            if not self._is_summary_safe(cleaned):
                continue

            lowered = cleaned.lower()
            if " v. " in lowered or " vs " in lowered or "this case concerns" in lowered or "," in cleaned:
                continue

            if cleaned not in results:
                results.append(cleaned)

        return results

    def _clean_string_list(self, items: list[Any]) -> list[str]:
        results: list[str] = []

        for item in items or []:
            cleaned = self._clean_text(str(item))
            if not cleaned:
                continue
            if not self._is_summary_safe(cleaned):
                continue
            if cleaned not in results:
                results.append(cleaned)

        return results

    def _clean_date_items(self, items: list[Any]) -> list[dict[str, str]]:
        results: list[dict[str, str]] = []
        seen: set[tuple[str, str]] = set()

        for item in items or []:
            if not isinstance(item, dict):
                continue

            label = self._clean_text(str(item.get("label", "")))
            value = self._clean_text(str(item.get("value", "")))

            if not value:
                continue
            if label == "mentioned_date":
                continue
            if not self._is_summary_safe(label or "date"):
                continue
            if not self._is_summary_safe(value):
                continue

            key = (label.lower(), value.lower())
            if key in seen:
                continue
            seen.add(key)

            results.append({
                "label": label or "date",
                "value": value,
            })

        return results

    def _is_summary_safe(self, value: str) -> bool:
        lowered = value.lower()

        if not lowered:
            return False

        if any(fragment in lowered for fragment in self.BLOCKED_SUMMARY_FRAGMENTS):
            return False

        return True

    @staticmethod
    def _clean_text(value: str) -> str:
        if not value:
            return ""

        value = value.replace("\\n", " ").replace("\n", " ").replace("\r", " ").replace("\t", " ")
        value = " ".join(value.split())
        return value.strip(" -:;,")

    @staticmethod
    def _clean_summary_output(value: str) -> str:
        cleaned = value.replace(" .", ".").replace(" ,", ",").replace(" ;", ";").replace(" :", ":")
        cleaned = "\n".join(line.rstrip() for line in cleaned.splitlines())
        return cleaned.strip()


summarization_service = SummarizationService()
