from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from backend.models.case import Case
from backend.models.consultation_request import ConsultationRequest
from backend.models.document import Document
from backend.models.voice_recording import VoiceRecording
from backend.services.ai.agents.booking_agent import booking_agent
from backend.services.ai.agents.case_reasoning_agent import case_reasoning_agent
from backend.services.ai.agents.drafting_agent import drafting_agent
from backend.services.ai.agents.document_comparison_agent import document_comparison_agent
from backend.services.ai.agents.prompt_optimizer_agent import prompt_optimizer_agent
from backend.services.ai.agents.timeline_agent import timeline_agent
from backend.services.ai.command_parsing_service import command_parsing_service
from backend.services.ai.external_research_service import external_research_service
from backend.services.ai.llm_gateway import llm_gateway
from backend.services.ai.rag_service import RagService
from backend.services.ai.summarization_service import summarization_service


class CopilotService:
    def __init__(self, rag_service: RagService):
        self.rag_service = rag_service
        self.client = llm_gateway.create_client()
        self.model = llm_gateway.default_model

    def handle_message(
        self,
        db: Session,
        tenant_id: int,
        message: str,
        top_k: int = 5,
        use_external_research: bool = True,
    ) -> Dict[str, Any]:
        parsed = command_parsing_service.parse(message)
        intent = parsed["intent"]

        handlers = {
            "optimize_prompt": lambda: self._optimize_prompt_intent(
                raw_prompt=parsed["clean_query"] or parsed["raw_message"],
                intent=parsed["intent"],
                target_type=parsed["target_type"],
                target_id=parsed["target_id"],
            ),
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
            "build_timeline_case": lambda: self._build_case_timeline(
                db=db,
                tenant_id=tenant_id,
                case_id=parsed["case_id"]
            ),
            "analyze_risks_case": lambda: self._analyze_case_risks(
                db=db,
                tenant_id=tenant_id,
                case_id=parsed["case_id"]
            ),
            "review_booking_case": lambda: self._review_case_booking(
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
            "ask_document": lambda: self._answer_with_optional_external_research(
                db=db,
                tenant_id=tenant_id,
                question=parsed["clean_query"],
                top_k=top_k,
                case_id=None,
                document_id=parsed["document_id"],
                use_external_research=use_external_research,
                intent="ask_document",
                target_type="document",
                target_id=parsed["document_id"],
            ),
            "ask_case": lambda: self._answer_with_optional_external_research(
                db=db,
                tenant_id=tenant_id,
                question=parsed["clean_query"],
                top_k=top_k,
                case_id=parsed["case_id"],
                document_id=None,
                use_external_research=use_external_research,
                intent="ask_case",
                target_type="case",
                target_id=parsed["case_id"],
            ),
            "ask_global": lambda: self._answer_with_optional_external_research(
                db=db,
                tenant_id=tenant_id,
                question=parsed["clean_query"],
                top_k=top_k,
                case_id=None,
                document_id=None,
                use_external_research=use_external_research,
                intent="ask_global",
                target_type="global",
                target_id=None,
            ),
            "summarize_global": lambda: self._answer_with_optional_external_research(
                db=db,
                tenant_id=tenant_id,
                question=parsed["clean_query"],
                top_k=top_k,
                case_id=None,
                document_id=None,
                use_external_research=use_external_research,
                intent="summarize_global",
                target_type="global",
                target_id=None,
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

    def _optimize_prompt_intent(
        self,
        *,
        raw_prompt: str,
        intent: str | None,
        target_type: str | None,
        target_id: int | None,
    ) -> Dict[str, Any]:
        optimized = prompt_optimizer_agent.optimize_query(
            raw_query=raw_prompt,
            intent=intent,
            target_type=target_type,
            target_id=target_id,
        )

        optimized_query = (
            optimized.payload.get("optimized_query")
            if optimized.success
            else raw_prompt
        )
        notes = optimized.payload.get("notes") if optimized.success else None

        answer_lines = [optimized_query or raw_prompt]
        if notes:
            answer_lines.append("")
            answer_lines.append(f"Notes: {notes}")

        return {
            "answer": "\n".join(answer_lines).strip(),
            "used_fallback": not bool(optimized.payload.get("used_llm")) if optimized.success else True,
            "fallback_reason": None if optimized.success else (optimized.error or "Prompt optimization failed"),
            "confidence": "high" if optimized.success and optimized.payload.get("used_llm") else "medium" if optimized.success else "low",
            "scope": "global",
            "sources": [],
        }

    @staticmethod
    def _optimize_prompt_for_query(
        *,
        question: str,
        intent: str | None,
        target_type: str | None,
        target_id: int | None,
    ) -> str:
        optimized = prompt_optimizer_agent.optimize_query(
            raw_query=question,
            intent=intent,
            target_type=target_type,
            target_id=target_id,
        )
        candidate = optimized.payload.get("optimized_query") if optimized.success else ""
        return str(candidate or question).strip()

    def _answer_with_optional_external_research(
        self,
        *,
        db: Session,
        tenant_id: int,
        question: str,
        top_k: int,
        case_id: Optional[int],
        document_id: Optional[int],
        use_external_research: bool,
        intent: str | None,
        target_type: str | None,
        target_id: int | None,
    ) -> Dict[str, Any]:
        optimized_question = self._optimize_prompt_for_query(
            question=question,
            intent=intent,
            target_type=target_type,
            target_id=target_id,
        )

        base_result = self.rag_service.answer_question(
            db=db,
            tenant_id=tenant_id,
            question=optimized_question,
            top_k=top_k,
            case_id=case_id,
            document_id=document_id,
        )

        if not use_external_research:
            return base_result

        research = external_research_service.search(
            query=optimized_question,
            max_results=max(3, min(top_k, 8)),
        )
        if not research.get("used_external"):
            return base_result

        external_results = research.get("results") or []
        if not external_results:
            return base_result

        synthesized_answer = self._synthesize_answer_with_external_research(
            question=question,
            internal_answer=base_result.get("answer", ""),
            internal_sources=base_result.get("sources") or [],
            external_results=external_results,
        )

        merged_sources = list(base_result.get("sources") or [])
        merged_sources.extend(self._external_results_to_sources(external_results))

        return {
            "answer": synthesized_answer or base_result.get("answer", ""),
            "used_fallback": bool(base_result.get("used_fallback")),
            "fallback_reason": base_result.get("fallback_reason"),
            "confidence": base_result.get("confidence", "medium"),
            "scope": base_result.get("scope", "global"),
            "sources": merged_sources[:20],
        }

    def _synthesize_answer_with_external_research(
        self,
        *,
        question: str,
        internal_answer: str,
        internal_sources: List[Dict[str, Any]],
        external_results: List[Dict[str, Any]],
    ) -> str:
        if not self.client:
            return self._build_fallback_external_answer(
                internal_answer=internal_answer,
                external_results=external_results,
            )

        compact_internal_sources = internal_sources[:6]
        compact_external = external_results[:6]

        prompt = f"""
You are a legal AI copilot.
Synthesize one practical answer to the user's question using:
1) internal case/document evidence
2) external web research snippets

Rules:
- Prioritize internal evidence when there is conflict.
- Do not invent facts.
- Keep the answer concise and professional.
- End with a short "Web references" line listing up to 3 URLs.

Question:
{question}

Internal grounded answer:
{internal_answer}

Internal sources (JSON):
{json.dumps(compact_internal_sources, ensure_ascii=False)}

External research snippets (JSON):
{json.dumps(compact_external, ensure_ascii=False)}
"""
        try:
            response = self.client.responses.create(
                model=self.model,
                input=prompt,
            )
            output = llm_gateway.extract_output_text(response).strip()
            if output:
                return output
        except Exception:
            pass

        return self._build_fallback_external_answer(
            internal_answer=internal_answer,
            external_results=external_results,
        )

    @staticmethod
    def _external_results_to_sources(external_results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        sources: List[Dict[str, Any]] = []
        for item in external_results:
            title = str(item.get("title") or item.get("domain") or "Web Research").strip()
            url = str(item.get("url") or "").strip()
            snippet = str(item.get("snippet") or "").strip()

            source_text = snippet
            if url:
                source_text = f"{source_text} (source: {url})".strip()

            sources.append(
                {
                    "chunk_id": None,
                    "document_id": None,
                    "case_id": None,
                    "filename": title[:120] or "Web Research",
                    "chunk_index": None,
                    "score": 0.35,
                    "snippet": source_text[:300],
                }
            )
        return sources

    @staticmethod
    def _build_fallback_external_answer(*, internal_answer: str, external_results: List[Dict[str, Any]]) -> str:
        lines = [internal_answer.strip() or "No internal answer was generated."]
        lines.append("")
        lines.append("External web findings:")
        for item in external_results[:5]:
            title = str(item.get("title") or item.get("domain") or "Web Result").strip()
            snippet = str(item.get("snippet") or "").strip()
            url = str(item.get("url") or "").strip()
            combined = f"- {title}: {snippet}"
            if url:
                combined += f" ({url})"
            lines.append(combined[:360])
        return "\n".join(lines).strip()

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

    def _get_case_consultation_requests(
        self,
        db: Session,
        tenant_id: int,
        case_id: int
    ) -> List[ConsultationRequest]:
        return (
            db.query(ConsultationRequest)
            .filter(
                ConsultationRequest.case_id == case_id,
                ConsultationRequest.tenant_id == tenant_id
            )
            .order_by(ConsultationRequest.created_at.desc(), ConsultationRequest.id.desc())
            .all()
        )

    def _get_case_voice_recordings(
        self,
        db: Session,
        tenant_id: int,
        case_id: int
    ) -> List[VoiceRecording]:
        return (
            db.query(VoiceRecording)
            .filter(
                VoiceRecording.case_id == case_id,
                VoiceRecording.tenant_id == tenant_id
            )
            .order_by(VoiceRecording.created_at.desc(), VoiceRecording.id.desc())
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

    def _run_case_reasoning(
        self,
        *,
        db: Session,
        tenant_id: int,
        case: Case,
        documents: List[Document]
    ) -> Dict[str, Any]:
        agent_result = case_reasoning_agent.analyze_case(
            case=case,
            documents=documents,
            consultation_requests=self._get_case_consultation_requests(
                db=db,
                tenant_id=tenant_id,
                case_id=case.id
            ),
            voice_recordings=self._get_case_voice_recordings(
                db=db,
                tenant_id=tenant_id,
                case_id=case.id
            ),
        )

        if agent_result.success:
            return agent_result.payload

        return {
            "overview": f"Case {case.id} - {case.title}",
            "narrative_summary": f"Case {case.id} could not be fully synthesized by the case reasoning agent.",
            "main_issues": [],
            "key_dates": [],
            "legal_risks": [],
            "recommended_next_steps": [
                "Review the case documents manually.",
                "Regenerate case intelligence after more documents are processed.",
            ],
            "sources": [],
            "used_llm": False,
        }

    @staticmethod
    def _format_case_reasoning_answer(reasoning_payload: Dict[str, Any]) -> str:
        sections: List[str] = []

        narrative_summary = (reasoning_payload.get("narrative_summary") or "").strip()
        if narrative_summary:
            sections.append(narrative_summary)
        else:
            overview = (reasoning_payload.get("overview") or "").strip()
            if overview:
                sections.append("Overview:")
                sections.append(overview)

        sections.append("")
        sections.append("Main Issues:")
        main_issues = reasoning_payload.get("main_issues") or []
        if main_issues:
            sections.extend(f"- {item}" for item in main_issues[:8])
        else:
            sections.append("- No major issues were clearly extracted.")

        sections.append("")
        sections.append("Key Dates:")
        key_dates = reasoning_payload.get("key_dates") or []
        if key_dates:
            sections.extend(
                f"- {item['label']}: {item['value']}"
                for item in key_dates[:10]
                if item.get("label") and item.get("value")
            )
        else:
            sections.append("- No major dates were clearly detected.")

        sections.append("")
        sections.append("Legal Risks:")
        legal_risks = reasoning_payload.get("legal_risks") or []
        if legal_risks:
            sections.extend(f"- {item}" for item in legal_risks[:8])
        else:
            sections.append("- No major legal risks were clearly detected.")

        sections.append("")
        sections.append("Recommended Next Steps:")
        next_steps = reasoning_payload.get("recommended_next_steps") or []
        if next_steps:
            sections.extend(f"- {item}" for item in next_steps[:8])
        else:
            sections.append("- Review the case evidence manually.")

        return "\n".join(sections).strip()

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

        for document in documents:
            self._ensure_document_summary(db=db, document=document)

        reasoning_payload = self._run_case_reasoning(
            db=db,
            tenant_id=tenant_id,
            case=case,
            documents=documents
        )

        return {
            "answer": self._format_case_reasoning_answer(reasoning_payload),
            "used_fallback": not bool(reasoning_payload.get("used_llm")),
            "fallback_reason": None if reasoning_payload.get("used_llm") else "Used case reasoning agent heuristic synthesis",
            "confidence": "high" if reasoning_payload.get("used_llm") else "medium",
            "scope": "case",
            "sources": (reasoning_payload.get("sources") or [])[:10]
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

    def _build_case_timeline(
        self,
        db: Session,
        tenant_id: int,
        case_id: Optional[int]
    ) -> Dict[str, Any]:
        case = self._get_case_or_404(db=db, tenant_id=tenant_id, case_id=case_id)
        documents = self._get_case_documents(db=db, tenant_id=tenant_id, case_id=case.id)
        consultations = self._get_case_consultation_requests(db=db, tenant_id=tenant_id, case_id=case.id)

        timeline_result = timeline_agent.build_case_timeline(
            case_id=case.id,
            case_title=case.title,
            documents=documents,
            consultations=consultations,
        )

        if timeline_result.success:
            sources: List[Dict[str, Any]] = []
            for document in documents:
                insights = self._safe_load_insights(document)
                for item in insights.get("important_dates", []):
                    label = self._normalize_text(item.get("label"))
                    value = self._normalize_text(item.get("value"))
                    if label and value:
                        sources.append(self._build_source(document=document, snippet=f"{label}: {value}"))

            return {
                "answer": timeline_result.payload.get("timeline_text") or "No timeline could be generated.",
                "used_fallback": not bool(timeline_result.payload.get("used_llm")),
                "fallback_reason": None if timeline_result.payload.get("used_llm") else "Used timeline agent heuristic synthesis",
                "confidence": "high" if timeline_result.payload.get("events") else "medium",
                "scope": "case",
                "sources": sources[:10],
            }

        return {
            "answer": "I could not build a timeline for this case yet.",
            "used_fallback": True,
            "fallback_reason": timeline_result.error or "Timeline agent failed",
            "confidence": "low",
            "scope": "case",
            "sources": [],
        }

    def _analyze_case_risks(
        self,
        db: Session,
        tenant_id: int,
        case_id: Optional[int]
    ) -> Dict[str, Any]:
        case = self._get_case_or_404(db=db, tenant_id=tenant_id, case_id=case_id)
        documents = self._get_case_documents(db=db, tenant_id=tenant_id, case_id=case.id)

        for document in documents:
            self._ensure_document_summary(db=db, document=document)

        reasoning_payload = self._run_case_reasoning(
            db=db,
            tenant_id=tenant_id,
            case=case,
            documents=documents
        )
        collected_risks = reasoning_payload.get("legal_risks") or []

        if collected_risks:
            return {
                "answer": (
                    f"Detected legal risks for case {case.id}:\n\n"
                    + "\n".join(f"- {risk}" for risk in collected_risks[:12])
                ),
                "used_fallback": not bool(reasoning_payload.get("used_llm")),
                "fallback_reason": None if reasoning_payload.get("used_llm") else "Used case reasoning agent heuristic synthesis",
                "confidence": "high" if reasoning_payload.get("used_llm") else "medium",
                "scope": "case",
                "sources": (reasoning_payload.get("sources") or [])[:10]
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

        draft_result = drafting_agent.draft_client_update_email(
            case_id=case.id,
            case_title=case.title,
            case_summary=case_summary["answer"],
        )

        return {
            "answer": (draft_result.payload.get("email_body") or "").strip(),
            "used_fallback": not bool(draft_result.payload.get("used_llm")),
            "fallback_reason": None if draft_result.payload.get("used_llm") else "Used drafting agent template fallback",
            "confidence": "high" if draft_result.payload.get("used_llm") else "medium",
            "scope": "case",
            "sources": case_summary["sources"]
        }

    def _review_case_booking(
        self,
        db: Session,
        tenant_id: int,
        case_id: Optional[int]
    ) -> Dict[str, Any]:
        case = self._get_case_or_404(db=db, tenant_id=tenant_id, case_id=case_id)
        consultations = self._get_case_consultation_requests(db=db, tenant_id=tenant_id, case_id=case.id)

        booking_result = booking_agent.analyze_consultations(
            case_id=case.id,
            case_title=case.title,
            consultations=consultations,
        )

        if booking_result.success:
            payload = booking_result.payload
            answer_lines = [
                payload.get("narrative_summary") or f"Booking overview for case {case.id}.",
                "",
                f"Booking intent: {payload.get('booking_intent') or 'not_detected'}",
                f"Urgency: {payload.get('urgency_level') or 'normal'}",
                f"Preferred schedule: {payload.get('preferred_schedule') or 'Not provided'}",
                f"Recommended action: {payload.get('recommended_action') or 'Follow up with the client to confirm scheduling.'}",
            ]
            return {
                "answer": "\n".join(answer_lines).strip(),
                "used_fallback": not bool(payload.get("used_llm")),
                "fallback_reason": None if payload.get("used_llm") else "Used booking agent heuristic synthesis",
                "confidence": "high" if payload.get("booking_intent") == "requested" else "medium",
                "scope": "case",
                "sources": [],
            }

        return {
            "answer": "No consultation booking details are available for this case yet.",
            "used_fallback": True,
            "fallback_reason": booking_result.error or "Booking agent failed",
            "confidence": "low",
            "scope": "case",
            "sources": [],
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

        sources: List[Dict[str, Any]] = []

        for document in documents[:10]:
            document = self._ensure_document_summary(db=db, document=document)
            summary = self._normalize_text(
                document.summary_short
                or document.summary
                or (document.redacted_text or document.extracted_text or "")[:250]
            )
            if summary:
                sources.append(self._build_source(document=document, snippet=summary))

        comparison_result = document_comparison_agent.compare_case_documents(
            case_id=case.id,
            documents=documents,
        )

        return {
            "answer": comparison_result.payload.get("comparison_text") or f"Comparison overview for case {case.id} is not available.",
            "used_fallback": not bool(comparison_result.payload.get("used_llm")),
            "fallback_reason": None if comparison_result.payload.get("used_llm") else "Used document comparison agent heuristic synthesis",
            "confidence": "high" if comparison_result.success else "low",
            "scope": "case",
            "sources": sources[:10]
        }
