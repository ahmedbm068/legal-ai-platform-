from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional

from sqlalchemy.orm import Session


@dataclass(slots=True)
class CopilotIntentExecutionContext:
    db: Session
    tenant_id: int
    user_id: Optional[int]
    user_role: str
    message: str
    top_k: int
    use_external_research: bool
    workspace_case_id: Optional[int]
    resolved_query: str
    parsed: Dict[str, Any]
    preoptimized_query: Optional[str]
    normalized_allowed_case_ids: Optional[set[int]]
    normalized_allowed_document_ids: Optional[set[int]]
    case_context: Dict[str, Any] | None = None
    case_snapshot: Dict[str, Any] | None = None


class CopilotIntentExecutionAgent:
    """Executes parsed copilot intents by delegating to runtime handlers."""

    def execute(
        self,
        *,
        intent: str,
        runtime: Any,
        ctx: CopilotIntentExecutionContext,
    ) -> Dict[str, Any]:
        handlers = {
            "create_case": lambda: runtime._create_case_action(
                db=ctx.db,
                tenant_id=ctx.tenant_id,
                user_id=ctx.user_id,
                user_role=ctx.user_role,
                requested_case_title=ctx.parsed.get("requested_case_title"),
                requested_case_description=ctx.parsed.get("requested_case_description"),
                requested_client_id=ctx.parsed.get("requested_client_id"),
                requested_client_name=ctx.parsed.get("requested_client_name"),
                requested_jurisdiction_country=ctx.parsed.get("requested_jurisdiction_country"),
                workspace_case_id=ctx.workspace_case_id,
                raw_message=ctx.parsed.get("raw_message") or ctx.message,
            ),
            "create_client": lambda: runtime._create_client_action(
                db=ctx.db,
                tenant_id=ctx.tenant_id,
                user_role=ctx.user_role,
                requested_client_name=ctx.parsed.get("requested_client_name"),
                raw_message=ctx.parsed.get("raw_message") or ctx.message,
            ),
            "list_cases": lambda: runtime._list_cases(
                db=ctx.db,
                tenant_id=ctx.tenant_id,
                allowed_case_ids=ctx.normalized_allowed_case_ids,
            ),
            "list_clients": lambda: runtime._list_clients(
                db=ctx.db,
                tenant_id=ctx.tenant_id,
            ),
            "list_case_documents": lambda: runtime._list_case_documents(
                db=ctx.db,
                tenant_id=ctx.tenant_id,
                case_id=ctx.parsed["case_id"],
            ),
            "list_case_appointments": lambda: runtime._list_case_appointments(
                db=ctx.db,
                tenant_id=ctx.tenant_id,
                case_id=ctx.parsed["case_id"],
            ),
            "request_document_upload": lambda: runtime._request_document_upload_action(
                db=ctx.db,
                tenant_id=ctx.tenant_id,
                case_id=ctx.parsed.get("case_id"),
            ),
            "request_audio_upload": lambda: runtime._request_audio_upload_action(
                db=ctx.db,
                tenant_id=ctx.tenant_id,
                case_id=ctx.parsed.get("case_id"),
            ),
            "create_case_appointment": lambda: runtime._create_case_appointment(
                db=ctx.db,
                tenant_id=ctx.tenant_id,
                case_id=ctx.parsed["case_id"],
                user_role=ctx.user_role,
                message=ctx.parsed.get("clean_query") or ctx.parsed.get("raw_message") or ctx.message,
            ),
            "update_case_status": lambda: runtime._update_case_status(
                db=ctx.db,
                tenant_id=ctx.tenant_id,
                case_id=ctx.parsed["case_id"],
                user_role=ctx.user_role,
                user_id=ctx.user_id,
                requested_status=ctx.parsed.get("requested_case_status"),
            ),
            "optimize_prompt": lambda: runtime._optimize_prompt_intent(
                raw_prompt=ctx.parsed["clean_query"] or ctx.parsed["raw_message"],
                intent=ctx.parsed["intent"],
                target_type=ctx.parsed["target_type"],
                target_id=ctx.parsed["target_id"],
            ),
            "summarize_case": lambda: runtime._summarize_case(
                db=ctx.db,
                tenant_id=ctx.tenant_id,
                case_id=ctx.parsed["case_id"],
                requested_count=ctx.parsed.get("requested_count"),
                requested_contractual_context=bool(ctx.parsed.get("requested_contractual_context")),
                summary_request_text=ctx.parsed.get("clean_query") or ctx.parsed.get("raw_message"),
            ),
            "summarize_and_analyze_risks_case": lambda: runtime._summarize_and_analyze_case_risks(
                db=ctx.db,
                tenant_id=ctx.tenant_id,
                case_id=ctx.parsed["case_id"],
                requested_count=ctx.parsed.get("requested_count"),
            ),
            "summarize_document": lambda: runtime._summarize_document(
                db=ctx.db,
                tenant_id=ctx.tenant_id,
                document_id=ctx.parsed["document_id"],
            ),
            "list_deadlines_case": lambda: runtime._list_case_deadlines(
                db=ctx.db,
                tenant_id=ctx.tenant_id,
                case_id=ctx.parsed["case_id"],
                requested_count=ctx.parsed.get("requested_count"),
            ),
            "build_timeline_case": lambda: runtime._build_case_timeline(
                db=ctx.db,
                tenant_id=ctx.tenant_id,
                case_id=ctx.parsed["case_id"],
            ),
            "generate_case_insights": lambda: runtime._generate_case_insights(
                db=ctx.db,
                tenant_id=ctx.tenant_id,
                case_id=ctx.parsed["case_id"],
            ),
            "generate_case_memory": lambda: runtime._generate_case_memory(
                db=ctx.db,
                tenant_id=ctx.tenant_id,
                case_id=ctx.parsed["case_id"],
                objective=ctx.parsed.get("clean_query") or ctx.parsed.get("raw_message") or ctx.message,
            ),
            "analyze_risks_case": lambda: runtime._analyze_case_risks(
                db=ctx.db,
                tenant_id=ctx.tenant_id,
                case_id=ctx.parsed["case_id"],
                requested_count=ctx.parsed.get("requested_count"),
                risk_request_text=ctx.parsed.get("clean_query") or ctx.parsed.get("raw_message"),
            ),
            "trace_case_evidence": lambda: runtime._trace_case_evidence(
                db=ctx.db,
                tenant_id=ctx.tenant_id,
                case_id=ctx.parsed["case_id"],
                objective=ctx.parsed.get("clean_query") or ctx.parsed.get("raw_message") or ctx.message,
            ),
            "monitor_deadlines_case": lambda: runtime._monitor_deadlines_case(
                db=ctx.db,
                tenant_id=ctx.tenant_id,
                case_id=ctx.parsed["case_id"],
                document_id=ctx.parsed.get("document_id"),
                objective=ctx.parsed.get("clean_query") or ctx.parsed.get("raw_message") or ctx.message,
            ),
            "review_booking_case": lambda: runtime._review_case_booking(
                db=ctx.db,
                tenant_id=ctx.tenant_id,
                case_id=ctx.parsed["case_id"],
            ),
            "draft_contract_redline_case": lambda: runtime._draft_contract_redline_for_case(
                db=ctx.db,
                tenant_id=ctx.tenant_id,
                case_id=ctx.parsed["case_id"],
                document_id=ctx.parsed.get("document_id"),
                objective=ctx.parsed.get("clean_query") or ctx.parsed.get("raw_message") or ctx.message,
            ),
            "draft_client_email_case": lambda: runtime._draft_client_email_for_case(
                db=ctx.db,
                tenant_id=ctx.tenant_id,
                case_id=ctx.parsed["case_id"],
            ),
            "draft_internal_email_case": lambda: runtime._draft_internal_email_for_case(
                db=ctx.db,
                tenant_id=ctx.tenant_id,
                case_id=ctx.parsed["case_id"],
            ),
            "draft_partner_strategy_note_case": lambda: runtime._draft_partner_strategy_note_for_case(
                db=ctx.db,
                tenant_id=ctx.tenant_id,
                case_id=ctx.parsed["case_id"],
            ),
            "compare_case_documents": lambda: runtime._compare_case_documents(
                db=ctx.db,
                tenant_id=ctx.tenant_id,
                case_id=ctx.parsed["case_id"],
            ),
            "draft_negotiation_strategy": lambda: runtime._draft_negotiation_strategy(
                objective=ctx.parsed.get("clean_query") or ctx.parsed.get("raw_message") or ctx.message,
                horizon_days=ctx.parsed.get("requested_horizon_days") or ctx.parsed.get("requested_count"),
                use_external_research=ctx.use_external_research,
                case_context=ctx.case_context,
                case_snapshot=ctx.case_snapshot,
            ),
            "ask_document": lambda: runtime._answer_with_optional_external_research(
                db=ctx.db,
                tenant_id=ctx.tenant_id,
                question=ctx.resolved_query,
                top_k=ctx.top_k,
                case_id=None,
                document_id=ctx.parsed["document_id"],
                use_external_research=ctx.use_external_research,
                intent="ask_document",
                target_type="document",
                target_id=ctx.parsed["document_id"],
                already_optimized=bool(ctx.preoptimized_query),
            ),
            "ask_case": lambda: runtime._answer_with_optional_external_research(
                db=ctx.db,
                tenant_id=ctx.tenant_id,
                question=ctx.resolved_query,
                top_k=ctx.top_k,
                case_id=ctx.parsed["case_id"],
                document_id=None,
                use_external_research=ctx.use_external_research,
                intent="ask_case",
                target_type="case",
                target_id=ctx.parsed["case_id"],
                already_optimized=bool(ctx.preoptimized_query),
            ),
            "ask_global": lambda: runtime._answer_with_optional_external_research(
                db=ctx.db,
                tenant_id=ctx.tenant_id,
                question=ctx.resolved_query,
                top_k=ctx.top_k,
                case_id=None,
                document_id=None,
                use_external_research=ctx.use_external_research,
                intent="ask_global",
                target_type="global",
                target_id=None,
                already_optimized=bool(ctx.preoptimized_query),
            ),
            "summarize_global": lambda: runtime._answer_with_optional_external_research(
                db=ctx.db,
                tenant_id=ctx.tenant_id,
                question=ctx.resolved_query,
                top_k=ctx.top_k,
                case_id=None,
                document_id=None,
                use_external_research=ctx.use_external_research,
                intent="summarize_global",
                target_type="global",
                target_id=None,
                already_optimized=bool(ctx.preoptimized_query),
            ),
        }

        return handlers.get(intent, runtime._unsupported_intent_response)()


copilot_intent_execution_agent = CopilotIntentExecutionAgent()
