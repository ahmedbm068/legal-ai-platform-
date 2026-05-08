"""Phase A4 — Workflow blueprint catalog ("Harvey Workflows"-style).

Pre-defined, deterministic step graphs the lawyer can browse and trigger.
Each blueprint describes what the workflow does, the ordered list of steps
(each step references one or more existing mini-agents / services), the
expected outputs, and the prerequisites a case must satisfy before the
workflow can run.

This service is intentionally pure (no DB, no LLM, no IO). It exposes
catalog metadata only — actual execution is delegated to the existing
``agent_workflow_service.run_case_workflow`` for the legacy "case_brief"
blueprint, and is left to follow-up phases for the new ones.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Iterable, Mapping


# Workflow lifecycle
STATUS_AVAILABLE = "available"
STATUS_BLOCKED = "blocked"  # case missing prerequisites

# Prerequisite identifiers — the catalog never queries the DB itself.
# Callers (the API layer) compute these flags from a case payload and pass
# them to ``check_prerequisites`` to decide if a blueprint can run.
PREREQ_HAS_DOCUMENTS = "has_documents"
PREREQ_HAS_TRANSCRIPTS = "has_transcripts"
PREREQ_HAS_CASE_TITLE = "has_case_title"
PREREQ_HAS_JURISDICTION = "has_jurisdiction"

VALID_PREREQS: frozenset[str] = frozenset(
    {
        PREREQ_HAS_DOCUMENTS,
        PREREQ_HAS_TRANSCRIPTS,
        PREREQ_HAS_CASE_TITLE,
        PREREQ_HAS_JURISDICTION,
    }
)


@dataclass(frozen=True)
class WorkflowStep:
    """A single step in a workflow blueprint."""

    name: str
    description: str
    agent: str  # logical agent / service identifier
    output_keys: tuple[str, ...] = ()


@dataclass(frozen=True)
class WorkflowBlueprint:
    id: str
    title: str
    description: str
    harvey_equivalent: str | None
    estimated_runtime_seconds: int
    prerequisites: tuple[str, ...]
    steps: tuple[WorkflowStep, ...]
    output_keys: tuple[str, ...]
    executor: str  # which backend executor handles this blueprint

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "harvey_equivalent": self.harvey_equivalent,
            "estimated_runtime_seconds": self.estimated_runtime_seconds,
            "prerequisites": list(self.prerequisites),
            "steps": [asdict(step) for step in self.steps],
            "output_keys": list(self.output_keys),
            "executor": self.executor,
        }


# ──────────────────────────────────────────────────────────────────────────
# Blueprint catalog
# ──────────────────────────────────────────────────────────────────────────

_BLUEPRINTS: dict[str, WorkflowBlueprint] = {
    "case_brief_pack": WorkflowBlueprint(
        id="case_brief_pack",
        title="Case Brief Pack",
        description=(
            "End-to-end pack: intake, retrieval, case reasoning, evidence strength, "
            "memory, drafting, and a verifier pass. Mirrors the existing /ai/agent-workflow."
        ),
        harvey_equivalent="Workflows · Case Brief",
        estimated_runtime_seconds=45,
        prerequisites=(PREREQ_HAS_DOCUMENTS, PREREQ_HAS_CASE_TITLE),
        steps=(
            WorkflowStep(
                name="Intake",
                description="Pull voice transcripts and consultation context.",
                agent="intake_agent",
                output_keys=("intake",),
            ),
            WorkflowStep(
                name="Retrieval",
                description="Run hybrid retrieval over case documents and chunks.",
                agent="rag_service.retrieval_agent",
                output_keys=("retrieval",),
            ),
            WorkflowStep(
                name="Case reasoning",
                description="Synthesize parties, posture, and legal framing.",
                agent="case_reasoning_agent",
                output_keys=("case_reasoning",),
            ),
            WorkflowStep(
                name="Evidence strength",
                description="Score the evidentiary support for each claim.",
                agent="evidence_strength_agent",
                output_keys=("evidence_strength",),
            ),
            WorkflowStep(
                name="Memory consolidation",
                description="Persist key facts and decisions to case memory.",
                agent="case_memory_agent",
                output_keys=("case_memory",),
            ),
            WorkflowStep(
                name="Drafting",
                description="Produce a client-ready brief or update note.",
                agent="drafting_agent",
                output_keys=("drafting",),
            ),
            WorkflowStep(
                name="Verifier",
                description="Check claim grounding, contradictions, and citation coverage.",
                agent="verifier_agent",
                output_keys=("verifier",),
            ),
        ),
        output_keys=(
            "intake",
            "retrieval",
            "case_reasoning",
            "evidence_strength",
            "case_memory",
            "drafting",
            "verifier",
        ),
        executor="agent_workflow_service.run_case_workflow",
    ),
    "irac_analysis": WorkflowBlueprint(
        id="irac_analysis",
        title="IRAC Legal Analysis",
        description=(
            "Run the IRAC pipeline: Issue spotting, Rule synthesis, Application, "
            "and Conclusion drafting from case documents."
        ),
        harvey_equivalent="Workflows · Legal Analysis (IRAC)",
        estimated_runtime_seconds=60,
        prerequisites=(PREREQ_HAS_DOCUMENTS, PREREQ_HAS_CASE_TITLE),
        steps=(
            WorkflowStep(
                name="Fact extraction",
                description="Extract chronology, parties, and amounts from documents.",
                agent="legal_workflow_agent_pack.fact_extraction",
                output_keys=("facts",),
            ),
            WorkflowStep(
                name="Issue spotting",
                description="Identify the legal issues raised by the facts.",
                agent="legal_workflow_agent_pack.issue_spotting",
                output_keys=("issues",),
            ),
            WorkflowStep(
                name="Rule synthesis",
                description="Derive applicable rules from statutes and precedent.",
                agent="legal_workflow_agent_pack.rule_synthesis",
                output_keys=("rules",),
            ),
            WorkflowStep(
                name="Application",
                description="Apply the rules to the facts.",
                agent="legal_workflow_agent_pack.application",
                output_keys=("application",),
            ),
            WorkflowStep(
                name="Conclusion",
                description="Draft a reasoned conclusion with citations.",
                agent="legal_workflow_agent_pack.conclusion",
                output_keys=("conclusion",),
            ),
            WorkflowStep(
                name="Verifier",
                description="Cross-check claim mappings and contradictions.",
                agent="legal_workflow_agent_pack.verifier",
                output_keys=("verifier",),
            ),
        ),
        output_keys=("facts", "issues", "rules", "application", "conclusion", "verifier"),
        executor="legal_workflow_agent_pack",
    ),
    "risk_triage": WorkflowBlueprint(
        id="risk_triage",
        title="Risk Triage",
        description=(
            "Audit case documents and consultations for legal risks, urgent deadlines, "
            "and missing evidence. Outputs a prioritised action list."
        ),
        harvey_equivalent="Workflows · Risk Audit",
        estimated_runtime_seconds=25,
        prerequisites=(PREREQ_HAS_DOCUMENTS,),
        steps=(
            WorkflowStep(
                name="Insight extraction",
                description="Aggregate per-document insights (risks, missing evidence).",
                agent="document_insight_service",
                output_keys=("insights",),
            ),
            WorkflowStep(
                name="Risk scoring",
                description="Score risks by severity and recency.",
                agent="legal_risk_triage_agent",
                output_keys=("risk_scores",),
            ),
            WorkflowStep(
                name="Deadline scan",
                description="Surface upcoming legal and procedural deadlines.",
                agent="deadline_obligation_agent",
                output_keys=("deadlines",),
            ),
            WorkflowStep(
                name="Action plan",
                description="Generate a ranked checklist of next steps.",
                agent="insight_agent",
                output_keys=("action_plan",),
            ),
        ),
        output_keys=("insights", "risk_scores", "deadlines", "action_plan"),
        executor="legal_workflow_agent_pack",
    ),
    "contract_redline_pack": WorkflowBlueprint(
        id="contract_redline_pack",
        title="Contract Redline Pack",
        description=(
            "Identify clauses, propose redlines, and generate fallback positions "
            "for a contract under review."
        ),
        harvey_equivalent="Workflows · Contract Review",
        estimated_runtime_seconds=40,
        prerequisites=(PREREQ_HAS_DOCUMENTS,),
        steps=(
            WorkflowStep(
                name="Clause identification",
                description="Detect material clauses (term, liability, IP, payment).",
                agent="document_classifier_service",
                output_keys=("clauses",),
            ),
            WorkflowStep(
                name="Risk per clause",
                description="Score legal/commercial risk for each clause.",
                agent="contract_redline_agent",
                output_keys=("clause_risks",),
            ),
            WorkflowStep(
                name="Redline drafting",
                description="Propose redlines with rationale.",
                agent="contract_redline_agent",
                output_keys=("redlines",),
            ),
            WorkflowStep(
                name="Fallbacks",
                description="Suggest acceptable counterparty positions.",
                agent="negotiation_strategy_agent",
                output_keys=("fallbacks",),
            ),
        ),
        output_keys=("clauses", "clause_risks", "redlines", "fallbacks"),
        executor="copilot_drafting_execution_service",
    ),
    "client_call_recap": WorkflowBlueprint(
        id="client_call_recap",
        title="Client Call Recap",
        description=(
            "Turn a voice transcript into a structured recap: action items, "
            "open questions, and a draft client follow-up email."
        ),
        harvey_equivalent="Workflows · Meeting Recap",
        estimated_runtime_seconds=20,
        prerequisites=(PREREQ_HAS_TRANSCRIPTS,),
        steps=(
            WorkflowStep(
                name="Transcript intake",
                description="Normalize the transcript and tag speakers.",
                agent="transcript_intake_service",
                output_keys=("transcript",),
            ),
            WorkflowStep(
                name="Summarization",
                description="Produce a structured topic summary.",
                agent="summarization_service",
                output_keys=("summary",),
            ),
            WorkflowStep(
                name="Action items",
                description="Extract action items, owners, and due dates.",
                agent="deadline_obligation_agent",
                output_keys=("action_items",),
            ),
            WorkflowStep(
                name="Follow-up draft",
                description="Draft a client-ready follow-up email.",
                agent="drafting_agent",
                output_keys=("follow_up_email",),
            ),
        ),
        output_keys=("transcript", "summary", "action_items", "follow_up_email"),
        executor="copilot_drafting_execution_service",
    ),
    "succession_entitlement_analysis": WorkflowBlueprint(
        id="succession_entitlement_analysis",
        title="Succession entitlement analysis (Tunisia)",
        description=(
            "Compute per-heir entitlement under the Tunisian Code de Statut "
            "Personnel articles 85-152. Pure rules engine — no LLM call. "
            "Returns exact rational shares, percentages, and TND amounts "
            "with citations to the official articles."
        ),
        harvey_equivalent=None,
        estimated_runtime_seconds=2,
        prerequisites=(PREREQ_HAS_JURISDICTION,),
        steps=(
            WorkflowStep(
                name="Identify heirs",
                description="Enumerate spouse, descendants, ascendants, collaterals.",
                agent="succession_calculator",
                output_keys=("identified_heirs",),
            ),
            WorkflowStep(
                name="Apply fardh (Quranic shares)",
                description="Fixed fractions for spouse, parents, daughters-only, uterine siblings.",
                agent="succession_calculator",
                output_keys=("fardh_shares",),
            ),
            WorkflowStep(
                name="Apply asaba (residuary)",
                description="Sons and daughters absorb the residue at 2:1; father is asaba in absence of male descendants.",
                agent="succession_calculator",
                output_keys=("asaba_shares",),
            ),
            WorkflowStep(
                name="Apply ʿawl / radd",
                description="Scale proportionally when fardh sum > 1; return residue to fardh heirs when sum < 1.",
                agent="succession_calculator",
                output_keys=("awl_radd_outcome",),
            ),
            WorkflowStep(
                name="Cite articles",
                description="Attach short summaries of CSP arts 85-152 to each heir share.",
                agent="csp_article_lookup",
                output_keys=("citations",),
            ),
        ),
        output_keys=("heirs", "radd_applied", "awl_applied", "citations"),
        executor="succession_calculator",
    ),
}


@dataclass(frozen=True)
class WorkflowAvailability:
    """Per-case availability for a single blueprint."""

    blueprint_id: str
    status: str  # STATUS_AVAILABLE | STATUS_BLOCKED
    missing_prerequisites: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        return {
            "blueprint_id": self.blueprint_id,
            "status": self.status,
            "missing_prerequisites": list(self.missing_prerequisites),
        }


class WorkflowBlueprintService:
    """Stateless catalog. See module docstring."""

    def list_blueprints(self) -> tuple[WorkflowBlueprint, ...]:
        return tuple(_BLUEPRINTS.values())

    def get(self, blueprint_id: str) -> WorkflowBlueprint | None:
        return _BLUEPRINTS.get(blueprint_id)

    def check_prerequisites(
        self,
        *,
        blueprint_id: str,
        case_flags: Mapping[str, bool] | None,
    ) -> WorkflowAvailability:
        """Return availability for a blueprint given a case's prereq flags.

        ``case_flags`` is a mapping of prerequisite id → bool. Missing keys
        are treated as ``False``. Unknown prerequisite ids in the blueprint
        are skipped (defensive — a malformed blueprint won't crash callers).
        """

        blueprint = _BLUEPRINTS.get(blueprint_id)
        if blueprint is None:
            return WorkflowAvailability(
                blueprint_id=blueprint_id,
                status=STATUS_BLOCKED,
                missing_prerequisites=("unknown_blueprint",),
            )

        flags = dict(case_flags or {})
        missing: list[str] = []
        for prereq in blueprint.prerequisites:
            if prereq not in VALID_PREREQS:
                continue
            if not flags.get(prereq, False):
                missing.append(prereq)

        if missing:
            return WorkflowAvailability(
                blueprint_id=blueprint_id,
                status=STATUS_BLOCKED,
                missing_prerequisites=tuple(missing),
            )
        return WorkflowAvailability(
            blueprint_id=blueprint_id,
            status=STATUS_AVAILABLE,
        )

    def availability_for_case(
        self,
        *,
        case_flags: Mapping[str, bool] | None,
        blueprint_ids: Iterable[str] | None = None,
    ) -> tuple[WorkflowAvailability, ...]:
        """Return availability records for every blueprint (or a subset)."""

        ids = (
            tuple(blueprint_ids)
            if blueprint_ids is not None
            else tuple(_BLUEPRINTS.keys())
        )
        return tuple(
            self.check_prerequisites(blueprint_id=bp_id, case_flags=case_flags)
            for bp_id in ids
        )


workflow_blueprint_service = WorkflowBlueprintService()


def derive_case_flags(case_payload: Mapping[str, Any] | None) -> dict[str, bool]:
    """Compute prerequisite flags from a case-shaped payload.

    Used by the API layer so the catalog itself stays free of DB types.
    Accepts either a plain dict (for tests) or a ``Case``-row-derived dict.
    """

    payload = dict(case_payload or {})
    title = payload.get("title")
    jurisdiction = payload.get("jurisdiction_country")
    documents = payload.get("documents")
    transcripts = payload.get("voice_recordings") or payload.get("transcripts")
    document_count = payload.get("document_count")
    transcript_count = payload.get("voice_recording_count") or payload.get("transcript_count")

    has_documents = (
        (isinstance(documents, list) and len(documents) > 0)
        or (isinstance(document_count, int) and document_count > 0)
    )
    has_transcripts = (
        (isinstance(transcripts, list) and len(transcripts) > 0)
        or (isinstance(transcript_count, int) and transcript_count > 0)
    )

    return {
        PREREQ_HAS_DOCUMENTS: bool(has_documents),
        PREREQ_HAS_TRANSCRIPTS: bool(has_transcripts),
        PREREQ_HAS_CASE_TITLE: bool(isinstance(title, str) and title.strip()),
        PREREQ_HAS_JURISDICTION: bool(
            isinstance(jurisdiction, str) and jurisdiction.strip()
        ),
    }


__all__ = [
    "WorkflowStep",
    "WorkflowBlueprint",
    "WorkflowAvailability",
    "WorkflowBlueprintService",
    "workflow_blueprint_service",
    "derive_case_flags",
    "STATUS_AVAILABLE",
    "STATUS_BLOCKED",
    "PREREQ_HAS_DOCUMENTS",
    "PREREQ_HAS_TRANSCRIPTS",
    "PREREQ_HAS_CASE_TITLE",
    "PREREQ_HAS_JURISDICTION",
    "VALID_PREREQS",
]
