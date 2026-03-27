from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from backend.models.case import Case
from backend.models.document import Document
from backend.services.ai.command_parsing_service import command_parsing_service
from backend.services.ai.rag_service import RagService
from backend.services.ai.summarization_service import summarization_service


class CopilotService:
    def __init__(self, rag_service: RagService):
        self.rag_service = rag_service

    def handle_message(
        self,
        db: Session,
        tenant_id: int,
        message: str,
        top_k: int = 5
    ) -> Dict[str, Any]:
        parsed = command_parsing_service.parse(message)
        intent = parsed["intent"]

        handlers = {
            "summarize_case": lambda: self._summarize_case(
                db=db,
                tenant_id=tenant_id,
                case_id=parsed["case_id"]
            ),
            "summarize_document": lambda: self._summarize_document(
                db=db,
                tenant_id=tenant_id,
                document_id=parsed["document_id"]
            ),
            "list_deadlines_case": lambda: self._list_case_deadlines(
                db=db,
                tenant_id=tenant_id,
                case_id=parsed["case_id"]
            ),
            "analyze_risks_case": lambda: self._analyze_case_risks(
                db=db,
                tenant_id=tenant_id,
                case_id=parsed["case_id"]
            ),
            "draft_client_email_case": lambda: self._draft_client_email_for_case(
                db=db,
                tenant_id=tenant_id,
                case_id=parsed["case_id"]
            ),
            "compare_case_documents": lambda: self._compare_case_documents(
                db=db,
                tenant_id=tenant_id,
                case_id=parsed["case_id"]
            ),
            "ask_case": lambda: self.rag_service.answer_question(
                db=db,
                tenant_id=tenant_id,
                question=parsed["clean_query"],
                top_k=top_k,
                case_id=parsed["case_id"],
                document_id=None
            ),
            "ask_document": lambda: self.rag_service.answer_question(
                db=db,
                tenant_id=tenant_id,
                question=parsed["clean_query"],
                top_k=top_k,
                case_id=None,
                document_id=parsed["document_id"]
            ),
            "ask_global": lambda: self.rag_service.answer_question(
                db=db,
                tenant_id=tenant_id,
                question=parsed["clean_query"],
                top_k=top_k,
                case_id=None,
                document_id=None
            ),
            "summarize_global": lambda: self.rag_service.answer_question(
                db=db,
                tenant_id=tenant_id,
                question=parsed["clean_query"],
                top_k=top_k,
                case_id=None,
                document_id=None
            ),
        }

        result = handlers.get(intent, self._unsupported_intent_response)()

        return {
            "message": message,
            "parsed_intent": parsed["intent"],
            "target_type": parsed["target_type"],
            "target_id": parsed["target_id"],
            **result
        }

    def _unsupported_intent_response(self) -> Dict[str, Any]:
        return {
            "answer": "I could not understand the command clearly.",
            "used_fallback": True,
            "fallback_reason": "Unsupported intent",
            "confidence": "low",
            "scope": "global",
            "sources": []
        }

    def _get_case_or_404(self, db: Session, tenant_id: int, case_id: Optional[int]) -> Case:
        if case_id is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Case id could not be detected from the message."
            )

        case = (
            db.query(Case)
            .filter(
                Case.id == case_id,
                Case.tenant_id == tenant_id,
                Case.deleted_at.is_(None)
            )
            .first()
        )

        if not case:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Case not found."
            )

        return case

    def _get_document_or_404(
        self,
        db: Session,
        tenant_id: int,
        document_id: Optional[int]
    ) -> Document:
        if document_id is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Document id could not be detected from the message."
            )

        document = (
            db.query(Document)
            .filter(
                Document.id == document_id,
                Document.tenant_id == tenant_id
            )
            .first()
        )

        if not document:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Document not found."
            )

        return document

    def _get_case_documents(self, db: Session, tenant_id: int, case_id: int) -> List[Document]:
        return (
            db.query(Document)
            .filter(
                Document.case_id == case_id,
                Document.tenant_id == tenant_id
            )
            .order_by(Document.upload_timestamp.asc(), Document.id.asc())
            .all()
        )

    def _safe_load_insights(self, document: Document) -> Dict[str, Any]:
        if not document.insights_json:
            return {}

        try:
            payload = json.loads(document.insights_json)
            return payload if isinstance(payload, dict) else {}
        except json.JSONDecodeError:
            return {}

    def _ensure_document_summary(self, db: Session, document: Document) -> Document:
        if document.summary and document.summary.strip():
            return document

        if not (document.redacted_text or document.extracted_text):
            return document

        try:
            return summarization_service.summarize_document(db=db, document=document)
        except Exception:
            return document

    @staticmethod
    def _normalize_text(value: Optional[str]) -> str:
        return (value or "").strip()

    def _append_unique(self, items: List[str], value: Optional[str]) -> None:
        cleaned = self._normalize_text(value)
        if cleaned and cleaned not in items:
            items.append(cleaned)

    def _build_source(
        self,
        *,
        document: Document,
        snippet: str,
        score: float = 1.0
    ) -> Dict[str, Any]:
        return {
            "chunk_id": None,
            "document_id": document.id,
            "case_id": document.case_id,
            "filename": document.filename,
            "chunk_index": None,
            "score": score,
            "snippet": snippet[:300]
        }

    def _is_reasonable_party(self, value: str) -> bool:
        lowered = value.lower().strip()
        if not lowered:
            return False

        blocked_fragments = [
            "invoice records",
            "warehouse logs",
            "document overview",
            "this document",
            "question answering",
            "sample document",
            "used to test",
            "key dates"
        ]

        if any(fragment in lowered for fragment in blocked_fragments):
            return False

        return len(value) <= 60

    def _summarize_document(
        self,
        db: Session,
        tenant_id: int,
        document_id: Optional[int]
    ) -> Dict[str, Any]:
        document = self._get_document_or_404(db=db, tenant_id=tenant_id, document_id=document_id)
        document = self._ensure_document_summary(db=db, document=document)

        summary_text = (
            document.summary
            or document.summary_short
            or (document.redacted_text or document.extracted_text or "")[:1200]
        ).strip()

        if not summary_text:
            return {
                "answer": "I could not summarize this document because no processed text is available.",
                "used_fallback": True,
                "fallback_reason": "Document has no processed text",
                "confidence": "low",
                "scope": "document",
                "sources": []
            }

        return {
            "answer": summary_text,
            "used_fallback": False,
            "fallback_reason": None,
            "confidence": "high" if document.summary else "medium",
            "scope": "document",
            "sources": [
                self._build_source(
                    document=document,
                    snippet=document.summary_short or summary_text
                )
            ]
        }

    def _summarize_case(
        self,
        db: Session,
        tenant_id: int,
        case_id: Optional[int]
    ) -> Dict[str, Any]:
        case = self._get_case_or_404(db=db, tenant_id=tenant_id, case_id=case_id)
        documents = self._get_case_documents(db=db, tenant_id=tenant_id, case_id=case.id)

        if not documents:
            return {
                "answer": f"Case {case.id} has no documents yet.",
                "used_fallback": True,
                "fallback_reason": "No documents found in case",
                "confidence": "low",
                "scope": "case",
                "sources": []
            }

        document_summaries: List[str] = []
        parties: List[str] = []
        dates: List[Dict[str, str]] = []
        risks: List[str] = []
        actions: List[str] = []
        document_types: List[str] = []
        sources: List[Dict[str, Any]] = []

        for document in documents:
            document = self._ensure_document_summary(db=db, document=document)
            insights = self._safe_load_insights(document)

            summary_text = self._normalize_text(
                document.summary_short
                or document.summary
                or (document.redacted_text or document.extracted_text or "")[:500]
            )

            if summary_text:
                document_summaries.append(f"{document.filename}: {summary_text}")

            document_type = self._normalize_text(
                insights.get("document_type") or document.document_type
            )
            if document_type and document_type not in document_types:
                document_types.append(document_type)

            for party in insights.get("parties_detected", []):
                if self._is_reasonable_party(party):
                    self._append_unique(parties, party)

            for date_item in insights.get("important_dates", []):
                label = self._normalize_text(date_item.get("label"))
                value = self._normalize_text(date_item.get("value"))
                if label and value:
                    item = {"label": label, "value": value}
                    if item not in dates:
                        dates.append(item)

            for risk in insights.get("legal_risks", []):
                self._append_unique(risks, risk)

            for action in insights.get("recommended_actions", []):
                self._append_unique(actions, action)

            if summary_text:
                sources.append(self._build_source(document=document, snippet=summary_text))

        if self.rag_service.client:
            context_parts: List[str] = [
                f"Case title: {case.title}",
                f"Number of documents: {len(documents)}"
            ]

            if document_types:
                context_parts.append("Document types:\n- " + "\n- ".join(document_types[:10]))
            if document_summaries:
                context_parts.append("Document summaries:\n- " + "\n- ".join(document_summaries[:12]))
            if parties:
                context_parts.append("Detected parties:\n- " + "\n- ".join(parties[:12]))
            if dates:
                context_parts.append(
                    "Important dates:\n- " + "\n- ".join(
                        f"{item['label']}: {item['value']}" for item in dates[:15]
                    )
                )
            if risks:
                context_parts.append("Legal risks:\n- " + "\n- ".join(risks[:12]))
            if actions:
                context_parts.append("Recommended actions:\n- " + "\n- ".join(actions[:12]))

            prompt = f"""
You are a legal AI copilot.

Using ONLY the provided case intelligence, write a professional case summary.

Requirements:
- Do NOT dump raw document text
- Do NOT list every document mechanically
- Synthesize the case into one coherent summary
- Be concise but informative
- Use this exact structure:

Overview:
<short narrative overview>

Main Issues:
- ...
- ...

Key Dates:
- ...
- ...

Legal Risks:
- ...
- ...

Recommended Next Steps:
- ...
- ...

If a section has limited evidence, say so briefly instead of inventing facts.

Case intelligence:
{chr(10).join(context_parts)}
"""

            try:
                response = self.rag_service.client.responses.create(
                    model="gpt-4o-mini",
                    input=prompt
                )
                answer_text = (response.output_text or "").strip()

                if answer_text:
                    return {
                        "answer": answer_text,
                        "used_fallback": False,
                        "fallback_reason": None,
                        "confidence": "high",
                        "scope": "case",
                        "sources": sources[:10]
                    }
            except Exception:
                pass

        overview_parts = [
            f"Case {case.id} — {case.title}",
            f"This case contains {len(documents)} document(s)."
        ]

        if document_types:
            overview_parts.append("Detected document types: " + ", ".join(document_types[:6]) + ".")

        if parties:
            overview_parts.append("Main parties detected: " + ", ".join(parties[:6]) + ".")

        answer_sections = [
            "\n".join(overview_parts),
            "",
            "Main Issues:"
        ]

        if document_summaries:
            for summary in document_summaries[:4]:
                answer_sections.append(f"- {summary}")
        else:
            answer_sections.append("- No document summaries are currently available.")

        answer_sections.append("")
        answer_sections.append("Key Dates:")
        if dates:
            for item in dates[:10]:
                answer_sections.append(f"- {item['label']}: {item['value']}")
        else:
            answer_sections.append("- No major dates were clearly detected.")

        answer_sections.append("")
        answer_sections.append("Legal Risks:")
        if risks:
            for risk in risks[:8]:
                answer_sections.append(f"- {risk}")
        else:
            answer_sections.append("- No major legal risks were clearly detected.")

        answer_sections.append("")
        answer_sections.append("Recommended Next Steps:")
        if actions:
            for action in actions[:8]:
                answer_sections.append(f"- {action}")
        else:
            answer_sections.append("- Review the document set for consistency.")
            answer_sections.append("- Verify deadlines, obligations, and supporting evidence.")
            answer_sections.append("- Regenerate intelligence if the case documents were recently updated.")

        return {
            "answer": "\n".join(answer_sections).strip(),
            "used_fallback": True,
            "fallback_reason": "Used structured case-summary fallback",
            "confidence": "medium",
            "scope": "case",
            "sources": sources[:10]
        }

    def _list_case_deadlines(
        self,
        db: Session,
        tenant_id: int,
        case_id: Optional[int]
    ) -> Dict[str, Any]:
        case = self._get_case_or_404(db=db, tenant_id=tenant_id, case_id=case_id)
        documents = self._get_case_documents(db=db, tenant_id=tenant_id, case_id=case.id)

        deadline_items: List[Dict[str, str]] = []
        sources: List[Dict[str, Any]] = []

        for document in documents:
            insights = self._safe_load_insights(document)

            for item in insights.get("important_dates", []):
                label = self._normalize_text(item.get("label"))
                value = self._normalize_text(item.get("value"))

                if not label or not value:
                    continue

                normalized_item = {
                    "label": label,
                    "value": value,
                    "filename": document.filename,
                    "document_id": document.id,
                    "case_id": document.case_id
                }

                if normalized_item not in deadline_items:
                    deadline_items.append(normalized_item)

        if deadline_items:
            grouped: Dict[str, List[Dict[str, str]]] = {
                "Deadlines / Due Dates": [],
                "Notice Periods": [],
                "Recurring Dates": [],
                "Other Time References": []
            }

            for item in deadline_items[:25]:
                label = item["label"].lower()

                if "notice" in label:
                    grouped["Notice Periods"].append(item)
                elif "recurring" in label:
                    grouped["Recurring Dates"].append(item)
                elif "deadline" in label or "due" in label or "hearing" in label:
                    grouped["Deadlines / Due Dates"].append(item)
                else:
                    grouped["Other Time References"].append(item)

                sources.append({
                    "chunk_id": None,
                    "document_id": item["document_id"],
                    "case_id": item["case_id"],
                    "filename": item["filename"],
                    "chunk_index": None,
                    "score": 1.0,
                    "snippet": f"{item['label']}: {item['value']}"
                })

            lines = [f"Detected deadlines and time-related obligations for case {case.id}:"]

            for section, items in grouped.items():
                if not items:
                    continue
                lines.append("")
                lines.append(f"{section}:")
                for item in items[:10]:
                    lines.append(f"- {item['value']} ({item['label']}) — {item['filename']}")

            return {
                "answer": "\n".join(lines),
                "used_fallback": False,
                "fallback_reason": None,
                "confidence": "high",
                "scope": "case",
                "sources": sources[:10]
            }

        rag_result = self.rag_service.answer_question(
            db=db,
            tenant_id=tenant_id,
            question="What deadlines, notice periods, due dates, or hearing dates are mentioned in this case?",
            top_k=5,
            case_id=case.id,
            document_id=None
        )
        rag_result["scope"] = "case"
        return rag_result

    def _analyze_case_risks(
        self,
        db: Session,
        tenant_id: int,
        case_id: Optional[int]
    ) -> Dict[str, Any]:
        case = self._get_case_or_404(db=db, tenant_id=tenant_id, case_id=case_id)
        documents = self._get_case_documents(db=db, tenant_id=tenant_id, case_id=case.id)

        collected_risks: List[str] = []
        sources: List[Dict[str, Any]] = []

        for document in documents:
            insights = self._safe_load_insights(document)

            for risk in insights.get("legal_risks", []):
                risk_text = self._normalize_text(risk)
                if not risk_text or risk_text in collected_risks:
                    continue

                collected_risks.append(risk_text)
                sources.append(self._build_source(document=document, snippet=risk_text))

        if collected_risks:
            return {
                "answer": (
                    f"Detected legal risks for case {case.id}:\n\n"
                    + "\n".join(f"- {risk}" for risk in collected_risks[:12])
                ),
                "used_fallback": False,
                "fallback_reason": None,
                "confidence": "high",
                "scope": "case",
                "sources": sources[:10]
            }

        rag_result = self.rag_service.answer_question(
            db=db,
            tenant_id=tenant_id,
            question="What legal risks, missing clauses, missing evidence, or timeline issues are mentioned in this case?",
            top_k=5,
            case_id=case.id,
            document_id=None
        )
        rag_result["scope"] = "case"
        return rag_result

    def _draft_client_email_for_case(
        self,
        db: Session,
        tenant_id: int,
        case_id: Optional[int]
    ) -> Dict[str, Any]:
        case_summary = self._summarize_case(db=db, tenant_id=tenant_id, case_id=case_id)
        case = self._get_case_or_404(db=db, tenant_id=tenant_id, case_id=case_id)

        base_summary = case_summary["answer"]

        if self.rag_service.client:
            prompt = f"""
You are a legal AI assistant drafting a professional client update email.
Use only the provided case summary.
Do not invent facts.
Keep the tone clear, professional, and concise.

Case summary:
{base_summary}

Return only the email body.
"""
            try:
                response = self.rag_service.client.responses.create(
                    model="gpt-4o-mini",
                    input=prompt
                )
                email_body = (response.output_text or "").strip()

                if email_body:
                    return {
                        "answer": email_body,
                        "used_fallback": False,
                        "fallback_reason": None,
                        "confidence": "high",
                        "scope": "case",
                        "sources": case_summary["sources"]
                    }
            except Exception:
                pass

        fallback_email = (
            f"Subject: Update on Case {case.id} - {case.title}\n\n"
            "Dear Client,\n\n"
            "I am writing to provide you with an update regarding your case.\n\n"
            f"{base_summary}\n\n"
            "Please let me know if you would like a more detailed breakdown of any document or issue.\n\n"
            "Best regards,\n"
            "Your Legal Team"
        )

        return {
            "answer": fallback_email,
            "used_fallback": True,
            "fallback_reason": "Used template-based drafting fallback",
            "confidence": "medium",
            "scope": "case",
            "sources": case_summary["sources"]
        }

    def _compare_case_documents(
        self,
        db: Session,
        tenant_id: int,
        case_id: Optional[int]
    ) -> Dict[str, Any]:
        case = self._get_case_or_404(db=db, tenant_id=tenant_id, case_id=case_id)
        documents = self._get_case_documents(db=db, tenant_id=tenant_id, case_id=case.id)

        if len(documents) < 2:
            return {
                "answer": f"Case {case.id} does not contain enough documents to compare.",
                "used_fallback": True,
                "fallback_reason": "Need at least two documents",
                "confidence": "low",
                "scope": "case",
                "sources": []
            }

        lines = [f"Comparison overview for case {case.id}:"]
        sources: List[Dict[str, Any]] = []

        for document in documents[:10]:
            document = self._ensure_document_summary(db=db, document=document)
            insights = self._safe_load_insights(document)

            summary = self._normalize_text(
                document.summary_short
                or document.summary
                or (document.redacted_text or document.extracted_text or "")[:250]
            )
            document_type = self._normalize_text(
                insights.get("document_type") or document.document_type or "unknown"
            )
            date_count = len(insights.get("important_dates", []))
            risk_count = len(insights.get("legal_risks", []))

            lines.append(
                f"- {document.filename}: type={document_type}, "
                f"dates_detected={date_count}, risks_detected={risk_count}, summary={summary}"
            )

            if summary:
                sources.append(self._build_source(document=document, snippet=summary))

        lines.append("")
        lines.append(
            "Manual follow-up: review differences in detected dates, risks, parties, and obligations across these documents."
        )

        return {
            "answer": "\n".join(lines),
            "used_fallback": False,
            "fallback_reason": None,
            "confidence": "medium",
            "scope": "case",
            "sources": sources[:10]
        }