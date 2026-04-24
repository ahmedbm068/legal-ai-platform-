from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from backend.core.config import settings
from backend.services.ai.agent_contracts import validate_json_model
from backend.services.ai.agents.base_agent import BaseAgent, AgentResult
from backend.services.ai.llm_gateway import llm_gateway


def _normalize_string_list(values: Any, *, limit: int = 12) -> list[str]:
    if not isinstance(values, list):
        return []
    normalized: list[str] = []
    for item in values:
        text = str(item or "").strip()
        if text and text not in normalized:
            normalized.append(text)
        if len(normalized) >= limit:
            break
    return normalized


def _split_sentences(value: str, *, limit: int = 8) -> list[str]:
    text = re.sub(r"\s+", " ", str(value or "").strip())
    if not text:
        return []
    chunks = re.split(r"(?<=[.!?])\s+", text)
    normalized: list[str] = []
    for chunk in chunks:
        cleaned = chunk.strip(" -")
        if cleaned and cleaned not in normalized:
            normalized.append(cleaned)
        if len(normalized) >= limit:
            break
    return normalized


def _tokenize(value: str) -> set[str]:
    return {token for token in re.findall(r"\w+", str(value or "").lower()) if len(token) >= 4}


def _clamp_score(value: float, *, minimum: int = 0, maximum: int = 100) -> int:
    return max(minimum, min(maximum, int(round(value))))


def _parse_timeline_date(value: str) -> datetime | None:
    normalized = str(value or "").strip()
    if not normalized:
        return None
    for fmt in ("%Y-%m-%d", "%B %d, %Y", "%b %d, %Y"):
        try:
            return datetime.strptime(normalized, fmt)
        except ValueError:
            continue
    inline = re.search(r"\d{4}-\d{2}-\d{2}", normalized)
    if inline:
        try:
            return datetime.strptime(inline.group(0), "%Y-%m-%d")
        except ValueError:
            return None
    return None


def _timeline_sort_key(item: dict[str, str]) -> tuple[int, datetime]:
    parsed = _parse_timeline_date(item.get("date") or "")
    if parsed is None:
        return (1, datetime.max)
    return (0, parsed)


def _infer_source_type(*, reference: str, snippet: str, source_identifier: str) -> str:
    combined = " ".join([reference, snippet, source_identifier]).lower()
    if any(
        token in combined
        for token in (
            "article",
            "art.",
            "§",
            "code",
            "gesetz",
            "civil",
            "succession",
            "international prive",
            "statute",
            "statut",
            "bgb",
            "stgb",
        )
    ):
        return "statute"
    if any(
        token in combined
        for token in (
            "cassation",
            "court",
            "judgment",
            "jurisprudence",
            "openjur",
            "tribunal",
            "appeal",
            "decision",
            "cour",
        )
    ):
        return "jurisprudence"
    if any(
        token in combined
        for token in (
            "document",
            ".pdf",
            ".doc",
            ".docx",
            "contract",
            "notice",
            "annex",
            "exhibit",
            "consultation",
            "record",
            "timeline",
        )
    ):
        return "structured_document"
    return "indirect"


def _evidence_strength_bucket(source_type: str) -> str:
    normalized = str(source_type or "").strip().lower()
    if normalized == "statute":
        return "strong"
    if normalized in {"jurisprudence", "structured_document"}:
        return "medium"
    return "weak"


def _dedupe_text_rows(values: list[str], *, limit: int = 12) -> list[str]:
    deduped: list[str] = []
    for value in values:
        cleaned = str(value or "").strip()
        if cleaned and cleaned not in deduped:
            deduped.append(cleaned)
        if len(deduped) >= limit:
            break
    return deduped


def _normalize_confidence(value: Any) -> str:
    token = str(value or "").strip().lower()
    if token in {"high", "medium", "low"}:
        return token
    return "low"


def _is_serious_legal_workflow(*, workflow_plan: dict[str, Any]) -> bool:
    workflow_kind = str(workflow_plan.get("workflow_kind") or "").strip().lower()
    matter_type = str(workflow_plan.get("matter_type") or "").strip().lower()
    if workflow_kind == "legal_analysis":
        return True
    return matter_type in {
        "civil obligation",
        "succession",
        "international private law",
        "mixed private law matter",
        "litigation position memo",
        "article applicability review",
    }


def _normalize_chronology_rows(values: Any, *, limit: int = 12) -> list[dict[str, str]]:
    if not isinstance(values, list):
        return []
    rows: list[dict[str, str]] = []
    for item in values:
        if not isinstance(item, dict):
            continue
        date = str(item.get("date") or "").strip()
        event = str(item.get("event") or "").strip()
        source = str(item.get("source") or "").strip()
        if not (date or event or source):
            continue
        rows.append(
            {
                "date": date or "unknown",
                "event": event or "timeline event",
                "source": source or "case context",
            }
        )
        if len(rows) >= limit:
            break
    rows.sort(key=_timeline_sort_key)
    return rows


def _normalize_contradiction_rows(values: Any, *, limit: int = 12) -> list[dict[str, Any]]:
    if not isinstance(values, list):
        return []
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in values:
        if isinstance(item, str):
            description = item.strip()
            impact = "medium"
            sources: list[str] = []
        elif isinstance(item, dict):
            description = str(item.get("description") or "").strip()
            impact_token = str(item.get("impact") or "medium").strip().lower()
            impact = impact_token if impact_token in {"low", "medium", "high"} else "medium"
            sources = _normalize_string_list(item.get("sources"), limit=5)
        else:
            continue
        if not description:
            continue
        fingerprint = f"{description}|{impact}|{','.join(sources)}".lower()
        if fingerprint in seen:
            continue
        seen.add(fingerprint)
        rows.append({"description": description, "impact": impact, "sources": sources})
        if len(rows) >= limit:
            break
    return rows


def _extract_dates_from_text_rows(rows: list[str], *, limit: int = 10) -> list[str]:
    dates: list[str] = []
    patterns = (
        r"\b\d{4}-\d{2}-\d{2}\b",
        r"\b\d{2}/\d{2}/\d{4}\b",
        r"\b\d{1,2}\s+[A-Za-z]+\s+\d{4}\b",
    )
    for row in rows:
        for pattern in patterns:
            for match in re.findall(pattern, row):
                value = str(match).strip()
                if value and value not in dates:
                    dates.append(value)
                if len(dates) >= limit:
                    return dates
    return dates


def _extract_amounts_from_text_rows(rows: list[str], *, limit: int = 10) -> list[str]:
    amounts: list[str] = []
    patterns = (
        r"\b\d{1,3}(?:[,\s]\d{3})*(?:\.\d{2})?\s?(?:TND|EUR|USD|DINAR|dinar|euros?|dollars?)\b",
        r"\b(?:TND|EUR|USD)\s?\d{1,3}(?:[,\s]\d{3})*(?:\.\d{2})?\b",
        r"\b\d+(?:\.\d{2})?\b",
    )
    for row in rows:
        for pattern in patterns:
            for match in re.findall(pattern, row):
                candidate = str(match).strip()
                if not candidate:
                    continue
                if candidate not in amounts:
                    amounts.append(candidate)
                if len(amounts) >= limit:
                    return amounts
    return amounts


def _extract_parties_from_text_rows(rows: list[str], *, limit: int = 10) -> list[str]:
    parties: list[str] = []
    markers = (
        "claimant",
        "defendant",
        "plaintiff",
        "respondent",
        "seller",
        "buyer",
        "employer",
        "employee",
        "tenant",
        "landlord",
        "heir",
        "decedent",
        "counterparty",
        "party",
    )
    for row in rows:
        lowered = row.lower()
        if not any(marker in lowered for marker in markers):
            continue
        cleaned = row.strip(" -")
        if cleaned and cleaned not in parties:
            parties.append(cleaned)
        if len(parties) >= limit:
            break
    return parties


class _FactChronologyRow(BaseModel):
    model_config = ConfigDict(extra="ignore")

    date: str = ""
    event: str = ""
    source: str = ""


class _FactExtractionLLMContract(BaseModel):
    model_config = ConfigDict(extra="ignore")

    confirmed_facts: list[str] = Field(default_factory=list)
    inferred_facts: list[str] = Field(default_factory=list)
    missing_facts: list[str] = Field(default_factory=list)
    fact_chronology: list[_FactChronologyRow] = Field(default_factory=list)
    parties: list[str] = Field(default_factory=list)
    amounts: list[str] = Field(default_factory=list)
    dates: list[str] = Field(default_factory=list)
    procedural_posture: str = ""
    confidence: Literal["low", "medium", "high"] = "low"


class _RuleSynthesisLLMContract(BaseModel):
    model_config = ConfigDict(extra="ignore")

    governing_rule: str = ""
    rule_summary: str = ""
    scope_conditions: list[str] = Field(default_factory=list)
    limits_or_ambiguities: list[str] = Field(default_factory=list)
    source_references: list[str] = Field(default_factory=list)
    confidence: Literal["low", "medium", "high"] = "low"


class _VerifierEvidenceStrengthContract(BaseModel):
    model_config = ConfigDict(extra="ignore")

    strong: list[str] = Field(default_factory=list)
    medium: list[str] = Field(default_factory=list)
    weak: list[str] = Field(default_factory=list)


class _VerifierClaimMapRow(BaseModel):
    model_config = ConfigDict(extra="ignore")

    claim: str = ""
    source: str = ""
    support: str = ""


class _VerifierLLMContract(BaseModel):
    model_config = ConfigDict(extra="ignore")

    verification_status: Literal["unverified", "partial", "verified"] = "unverified"
    claim_to_source_map: list[_VerifierClaimMapRow] = Field(default_factory=list)
    unsupported_claims: list[str] = Field(default_factory=list)
    overstated_claims: list[str] = Field(default_factory=list)
    evidence_strength: _VerifierEvidenceStrengthContract = Field(default_factory=_VerifierEvidenceStrengthContract)
    warnings: list[str] = Field(default_factory=list)
    confidence: Literal["low", "medium", "high"] = "low"


class FactExtractionAgent(BaseAgent):
    agent_name = "fact_extraction_agent"

    PROMPT = """You are the FactExtractionAgent.

Your role is to extract legally relevant facts from the user request and available documents.

Separate the result into:
- confirmed facts explicitly supported by the materials
- inferred facts that appear likely but are not fully confirmed
- missing facts that may change the legal outcome

Do not perform legal reasoning yet.
Do not conclude on liability, validity, entitlement, or outcome.
Your task is fact structuring only.
Focus on operative facts, dates, parties, amounts, clauses, chronology, and procedural posture where available."""

    def __init__(self) -> None:
        self.client = llm_gateway.create_client()
        self.model = llm_gateway.resolve_model("standard")

    @staticmethod
    def _determine_procedural_posture(*, workflow_plan: dict[str, Any], case_context: dict[str, Any]) -> str:
        case_payload = case_context.get("case") if isinstance(case_context.get("case"), dict) else {}
        status = str(case_payload.get("status") or "").strip()
        if status:
            return f"Case status appears to be '{status}'."
        workflow_kind = str(workflow_plan.get("workflow_kind") or "").strip()
        if workflow_kind == "legal_analysis":
            return "Matter is in preliminary legal analysis posture pending lawyer review."
        if workflow_kind == "document_review":
            return "Matter appears to be in document review posture."
        return "Procedural posture remains incomplete from current materials."

    def _build_deterministic_payload(
        self,
        *,
        workflow_plan: dict[str, Any],
        output_contract: dict[str, Any],
        case_context: dict[str, Any],
    ) -> dict[str, Any]:
        chronology = _normalize_chronology_rows(case_context.get("timeline"), limit=12)
        confirmed_facts = _normalize_string_list(
            output_contract.get("confirmed_facts") or workflow_plan.get("confirmed_facts"),
            limit=10,
        )
        inferred_facts = _normalize_string_list(output_contract.get("inferred_facts"), limit=8)
        missing_facts = _normalize_string_list(
            output_contract.get("missing_facts") or workflow_plan.get("missing_facts"),
            limit=10,
        )
        text_rows = [*confirmed_facts, *inferred_facts, *missing_facts]
        chronology_events = [str(item.get("event") or "").strip() for item in chronology]
        chronology_dates = [str(item.get("date") or "").strip() for item in chronology]
        parties = _extract_parties_from_text_rows([*text_rows, *chronology_events], limit=8)
        amounts = _extract_amounts_from_text_rows(text_rows, limit=8)
        dates = _dedupe_text_rows([*chronology_dates, *_extract_dates_from_text_rows(text_rows, limit=8)], limit=10)
        confidence = "low"
        if confirmed_facts and len(missing_facts) <= 1:
            confidence = "high"
        elif confirmed_facts:
            confidence = "medium"
        return {
            "confirmed_facts": confirmed_facts,
            "inferred_facts": inferred_facts,
            "missing_facts": missing_facts,
            "fact_chronology": chronology,
            "parties": parties,
            "amounts": amounts,
            "dates": dates,
            "procedural_posture": self._determine_procedural_posture(
                workflow_plan=workflow_plan,
                case_context=case_context,
            ),
            "confidence": confidence,
        }

    def _should_use_llm(
        self,
        *,
        workflow_plan: dict[str, Any],
        deterministic_payload: dict[str, Any],
    ) -> bool:
        if not settings.LEGAL_WORKFLOW_LLM_AGENTS_ENABLED:
            return False
        if self.client is None:
            return False
        if not _is_serious_legal_workflow(workflow_plan=workflow_plan):
            return False
        return bool(
            deterministic_payload.get("confirmed_facts")
            or deterministic_payload.get("inferred_facts")
            or deterministic_payload.get("missing_facts")
            or deterministic_payload.get("fact_chronology")
        )

    def _generate_llm_payload(
        self,
        *,
        workflow_plan: dict[str, Any],
        output_contract: dict[str, Any],
        deterministic_payload: dict[str, Any],
    ) -> dict[str, Any] | None:
        if self.client is None:
            return None
        prompt = f"""
You are the FactExtractionAgent for a legal AI copilot assisting lawyers.

Return VALID JSON only with this exact schema:
{{
  "confirmed_facts": [],
  "inferred_facts": [],
  "missing_facts": [],
  "fact_chronology": [{{"date": "", "event": "", "source": ""}}],
  "parties": [],
  "amounts": [],
  "dates": [],
  "procedural_posture": "",
  "confidence": "low|medium|high"
}}

Rules:
- Extract and structure facts only.
- Do not perform legal reasoning or final conclusions.
- Do not invent facts.
- Keep missing facts explicit when information is incomplete.

Workflow context:
{json.dumps(workflow_plan, ensure_ascii=True, indent=2)}

Current deterministic extraction:
{json.dumps(deterministic_payload, ensure_ascii=True, indent=2)}

Legal issue context:
{json.dumps({"legal_issue": output_contract.get("legal_issue"), "jurisdiction": output_contract.get("jurisdiction")}, ensure_ascii=True, indent=2)}
"""
        try:
            response = self.client.responses.create(
                model=self.model,
                input=prompt,
                max_output_tokens=1200,
            )
            raw_text = llm_gateway.extract_output_text(response).strip()
            contract = validate_json_model(raw_text, _FactExtractionLLMContract)
            if contract is None:
                return None
            chronology = _normalize_chronology_rows(
                [row.model_dump(mode="python") for row in contract.fact_chronology],
                limit=12,
            )
            return {
                "confirmed_facts": _normalize_string_list(contract.confirmed_facts, limit=10),
                "inferred_facts": _normalize_string_list(contract.inferred_facts, limit=8),
                "missing_facts": _normalize_string_list(contract.missing_facts, limit=10),
                "fact_chronology": chronology,
                "parties": _normalize_string_list(contract.parties, limit=8),
                "amounts": _normalize_string_list(contract.amounts, limit=8),
                "dates": _normalize_string_list(contract.dates, limit=10),
                "procedural_posture": str(contract.procedural_posture or "").strip(),
                "confidence": _normalize_confidence(contract.confidence),
            }
        except Exception:
            return None

    def extract(
        self,
        *,
        workflow_plan: dict[str, Any],
        output_contract: dict[str, Any],
        case_context: dict[str, Any],
    ) -> AgentResult:
        deterministic_payload = self._build_deterministic_payload(
            workflow_plan=workflow_plan,
            output_contract=output_contract,
            case_context=case_context,
        )
        trace = ["Structured facts before legal reasoning."]
        payload = deterministic_payload
        if self._should_use_llm(workflow_plan=workflow_plan, deterministic_payload=deterministic_payload):
            llm_payload = self._generate_llm_payload(
                workflow_plan=workflow_plan,
                output_contract=output_contract,
                deterministic_payload=deterministic_payload,
            )
            if llm_payload:
                payload = llm_payload
                trace.append("Applied LLM-backed fact extraction with validated JSON contract.")
            else:
                trace.append("LLM fact extraction unavailable or invalid JSON; used deterministic fallback.")
        else:
            trace.append("Skipped LLM fact extraction for non-serious workflow or unavailable provider.")
        return self.result(
            success=True,
            payload=payload,
            trace=trace,
        )


class RetrievalAgent(BaseAgent):
    agent_name = "retrieval_agent_legal_workflow"

    PROMPT = """You are the RetrievalAgent.

Your role is to retrieve the most relevant legal sources for the identified matter.

Your objective is not to maximize quantity.
Your objective is to maximize relevance, legal fit, and traceability.

Retrieve only sources that appear materially relevant to:
- the legal issue
- the likely code family
- the known facts

Return:
- source identifier
- article or section reference
- short relevant excerpt
- why this source matters
- confidence in relevance

Do not synthesize the final legal rule yet.
Do not give the final answer."""

    def retrieve(
        self,
        *,
        workflow_plan: dict[str, Any],
        output_contract: dict[str, Any],
        result: dict[str, Any],
    ) -> AgentResult:
        likely_code_family = str(workflow_plan.get("likely_code_family") or "context_dependent").strip()
        legal_issue = str(output_contract.get("legal_issue") or workflow_plan.get("user_goal") or "").strip()
        ranked_sources: list[dict[str, Any]] = []
        for index, item in enumerate(output_contract.get("relevant_sources") or [], start=1):
            if not isinstance(item, dict):
                continue
            label = str(item.get("label") or f"Source {index}").strip()
            snippet = str(item.get("snippet") or "").strip()
            url = str(item.get("url") or "").strip()
            reference = label
            source_type = _infer_source_type(
                reference=reference,
                snippet=snippet,
                source_identifier=url or label,
            )
            evidence_bucket = _evidence_strength_bucket(source_type)
            if "article" in label.lower() or "art" in label.lower() or "§" in label:
                confidence = "high"
            elif snippet:
                confidence = "medium"
            else:
                confidence = "low"
            ranked_sources.append(
                {
                    "source_identifier": url or label,
                    "article_or_section_reference": reference,
                    "short_relevant_excerpt": snippet[:240],
                    "why_this_source_matters": (
                        f"Appears relevant to '{legal_issue or likely_code_family}' "
                        f"and the likely code family '{likely_code_family}'."
                    ),
                    "confidence_in_relevance": confidence,
                    "source_type": source_type,
                    "evidence_strength_bucket": evidence_bucket,
                }
            )
            if len(ranked_sources) >= 8:
                break

        return self.result(
            success=True,
            payload={
                "ranked_sources": ranked_sources,
                "retrieval_rationale": (
                    "Prioritized sources that match the legal issue, likely code family, and available facts."
                ),
                "source_confidence": str(result.get("confidence") or output_contract.get("confidence") or "low").strip(),
            },
            trace=["Ranked retrieved legal sources for traceability."],
        )


class RuleSynthesisAgent(BaseAgent):
    agent_name = "rule_synthesis_agent"

    PROMPT = """You are the RuleSynthesisAgent.

Your role is to convert retrieved legal sources into a clear governing rule.

Use only the provided sources.
Do not invent legal content.
Do not overstate what the sources establish.

Return:
- governing rule
- source-supported explanation
- scope conditions
- any ambiguity or limit in the rule

This is not the final legal conclusion.
It is the legal rule stage only."""

    def __init__(self) -> None:
        self.client = llm_gateway.create_client()
        self.model = llm_gateway.resolve_model("standard")

    def _build_deterministic_payload(
        self,
        *,
        workflow_plan: dict[str, Any],
        output_contract: dict[str, Any],
        retrieval_payload: dict[str, Any],
    ) -> dict[str, Any]:
        ranked_sources = retrieval_payload.get("ranked_sources") if isinstance(retrieval_payload, dict) else []
        source_labels = [
            str(item.get("article_or_section_reference") or "").strip()
            for item in ranked_sources or []
            if isinstance(item, dict) and str(item.get("article_or_section_reference") or "").strip()
        ]
        governing_rule = str(output_contract.get("governing_rule") or "").strip()
        if not governing_rule and source_labels:
            governing_rule = (
                "The governing rule should be derived conservatively from these sources: "
                f"{', '.join(source_labels[:3])}."
            )
        ambiguity = []
        verification_status = str(output_contract.get("verification_status") or "").strip().lower()
        if verification_status != "verified":
            ambiguity.append("Source support is not fully verified and should be checked article by article.")
        if str(workflow_plan.get("likely_code_family") or "").strip() == "mixed_or_ambiguous":
            ambiguity.append("The likely code family remains mixed or ambiguous.")
        confidence = "low"
        if governing_rule and source_labels and verification_status == "verified":
            confidence = "high"
        elif governing_rule and source_labels:
            confidence = "medium"
        return {
            "governing_rule": governing_rule,
            "rule_summary": (
                f"Rule summary is grounded in retrieved legal basis: {', '.join(source_labels[:4]) or 'limited sources'}."
            ),
            "scope_conditions": [
                f"Likely code family: {workflow_plan.get('likely_code_family') or 'context_dependent'}.",
                f"Legal dimension: {workflow_plan.get('legal_dimension') or 'mixed'}.",
            ],
            "limits_or_ambiguities": ambiguity,
            "source_references": source_labels[:8],
            "confidence": confidence,
            "source_supported_explanation": (
                f"Rule summary is grounded in retrieved legal basis: {', '.join(source_labels[:4]) or 'limited sources'}."
            ),
            "ambiguity_or_limit": ambiguity,
        }

    def _should_use_llm(
        self,
        *,
        workflow_plan: dict[str, Any],
        deterministic_payload: dict[str, Any],
    ) -> bool:
        if not settings.LEGAL_WORKFLOW_LLM_AGENTS_ENABLED:
            return False
        if self.client is None:
            return False
        if not _is_serious_legal_workflow(workflow_plan=workflow_plan):
            return False
        return bool(deterministic_payload.get("source_references") or deterministic_payload.get("governing_rule"))

    def _generate_llm_payload(
        self,
        *,
        workflow_plan: dict[str, Any],
        output_contract: dict[str, Any],
        retrieval_payload: dict[str, Any],
        deterministic_payload: dict[str, Any],
    ) -> dict[str, Any] | None:
        if self.client is None:
            return None
        prompt = f"""
You are the RuleSynthesisAgent for a legal AI copilot.

Return VALID JSON only with this exact schema:
{{
  "governing_rule": "",
  "rule_summary": "",
  "scope_conditions": [],
  "limits_or_ambiguities": [],
  "source_references": [],
  "confidence": "low|medium|high"
}}

Rules:
- Use only retrieved sources and provided context.
- Do not invent legal content.
- Do not overstate source support.
- This is rule synthesis, not final legal advice.

Workflow context:
{json.dumps(workflow_plan, ensure_ascii=True, indent=2)}

Retrieved sources:
{json.dumps(retrieval_payload, ensure_ascii=True, indent=2)}

Current deterministic rule synthesis:
{json.dumps(deterministic_payload, ensure_ascii=True, indent=2)}

Output contract context:
{json.dumps({"legal_issue": output_contract.get("legal_issue"), "verification_status": output_contract.get("verification_status")}, ensure_ascii=True, indent=2)}
"""
        try:
            response = self.client.responses.create(
                model=self.model,
                input=prompt,
                max_output_tokens=1000,
            )
            raw_text = llm_gateway.extract_output_text(response).strip()
            contract = validate_json_model(raw_text, _RuleSynthesisLLMContract)
            if contract is None:
                return None
            summary = str(contract.rule_summary or "").strip()
            limits = _normalize_string_list(contract.limits_or_ambiguities, limit=8)
            return {
                "governing_rule": str(contract.governing_rule or "").strip(),
                "rule_summary": summary,
                "scope_conditions": _normalize_string_list(contract.scope_conditions, limit=8),
                "limits_or_ambiguities": limits,
                "source_references": _normalize_string_list(contract.source_references, limit=8),
                "confidence": _normalize_confidence(contract.confidence),
                "source_supported_explanation": summary,
                "ambiguity_or_limit": limits,
            }
        except Exception:
            return None

    def synthesize(
        self,
        *,
        workflow_plan: dict[str, Any],
        output_contract: dict[str, Any],
        retrieval_payload: dict[str, Any],
    ) -> AgentResult:
        deterministic_payload = self._build_deterministic_payload(
            workflow_plan=workflow_plan,
            output_contract=output_contract,
            retrieval_payload=retrieval_payload,
        )
        trace = ["Synthesized governing rule from retrieved sources without final conclusion."]
        payload = deterministic_payload
        if self._should_use_llm(workflow_plan=workflow_plan, deterministic_payload=deterministic_payload):
            llm_payload = self._generate_llm_payload(
                workflow_plan=workflow_plan,
                output_contract=output_contract,
                retrieval_payload=retrieval_payload,
                deterministic_payload=deterministic_payload,
            )
            if llm_payload:
                payload = llm_payload
                trace.append("Applied LLM-backed rule synthesis with validated JSON contract.")
            else:
                trace.append("LLM rule synthesis unavailable or invalid JSON; used deterministic fallback.")
        else:
            trace.append("Skipped LLM rule synthesis for non-serious workflow or unavailable provider.")
        return self.result(
            success=True,
            payload=payload,
            trace=trace,
        )


class ApplicationAgent(BaseAgent):
    agent_name = "application_agent"

    PROMPT = """You are the ApplicationAgent.

Your role is to compare the governing legal rule against the confirmed facts.

You must:
- apply the rule only to confirmed or clearly identified inferred facts
- avoid treating assumptions as established truth
- explain where the factual fit is strong or weak
- remain cautious when facts are incomplete

Return:
- preliminary application
- facts supporting applicability
- facts weakening applicability
- points requiring lawyer verification

Do not present the result as a final legal judgment."""

    def apply(
        self,
        *,
        output_contract: dict[str, Any],
        fact_payload: dict[str, Any],
    ) -> AgentResult:
        confirmed_facts = _normalize_string_list(fact_payload.get("confirmed_facts"), limit=5)
        inferred_facts = _normalize_string_list(fact_payload.get("inferred_facts"), limit=4)
        missing_facts = _normalize_string_list(fact_payload.get("missing_facts"), limit=4)
        contradiction_rows = _normalize_contradiction_rows(output_contract.get("contradictions"), limit=3)
        contradictions = [str(item.get("description") or "").strip() for item in contradiction_rows if str(item.get("description") or "").strip()]
        weakening = [*missing_facts, *contradictions]
        verification_points = list(weakening)
        for item in inferred_facts:
            marker = f"Inferred fact requires confirmation: {item}"
            if marker not in verification_points:
                verification_points.append(marker)
        return self.result(
            success=True,
            payload={
                "preliminary_application": str(output_contract.get("application") or "").strip()
                or "Preliminary application remains limited because the factual record is incomplete.",
                "facts_supporting_applicability": confirmed_facts,
                "facts_weakening_applicability": weakening[:6],
                "points_requiring_lawyer_verification": verification_points[:6],
                "provisional_fit_assessment": "cautious_preliminary_fit",
            },
            trace=["Applied governing rule to confirmed and clearly identified inferred facts only."],
        )


class MissingFactsAgent(BaseAgent):
    agent_name = "missing_facts_agent"

    PROMPT = """You are the MissingFactsAgent.

Your role is to identify facts, documents, or procedural details that may materially change the legal outcome.

For each missing item, explain:
- what is missing
- why it matters legally
- what document or clarification could resolve it

Do not answer the main legal question.
Do not repeat facts already established.
Focus only on legally meaningful gaps."""

    @staticmethod
    def _suggest_document(missing_item: str) -> str:
        lowered = str(missing_item or "").lower()
        if any(token in lowered for token in ("contract", "clause", "notice", "cure")):
            return "Request the full contract, notice letter, and any amendment or annex."
        if any(token in lowered for token in ("testament", "heir", "inheritance", "family")):
            return "Request testament documents, civil-status records, heir certificates, and succession filings."
        if any(token in lowered for token in ("foreign", "jurisdiction", "governing-law", "governing law", "exequatur")):
            return "Request governing-law clauses, foreign judgment copies, and cross-border connecting-factor evidence."
        if any(token in lowered for token in ("chronology", "date", "timeline")):
            return "Request a dated chronology, notices, filings, and communications."
        return "Request the document or clarification that directly confirms this fact."

    def identify(
        self,
        *,
        output_contract: dict[str, Any],
        workflow_plan: dict[str, Any],
    ) -> AgentResult:
        items: list[dict[str, str]] = []
        for entry in _normalize_string_list(output_contract.get("missing_facts") or workflow_plan.get("missing_facts"), limit=8):
            items.append(
                {
                    "what_is_missing": entry,
                    "why_it_matters_legally": "This gap may materially affect rule applicability, entitlement, or risk assessment.",
                    "document_or_clarification_to_request": self._suggest_document(entry),
                }
            )
        return self.result(
            success=True,
            payload={"missing_facts_list": items},
            trace=["Surfaced legally meaningful factual and documentary gaps."],
        )


class CounterAnalysisAgent(BaseAgent):
    agent_name = "counter_analysis_agent"

    PROMPT = """You are the CounterAnalysisAgent.

Your role is to challenge the preliminary legal analysis.

You must identify:
- alternative legal interpretations
- competing readings of the facts
- assumptions that may be too strong
- reasons the initial legal theory may fail or weaken

Your task is not to destroy the analysis blindly.
Your task is to improve legal robustness by surfacing plausible counterpoints.
Return a structured counter-analysis only."""

    def challenge(
        self,
        *,
        output_contract: dict[str, Any],
        fact_payload: dict[str, Any],
    ) -> AgentResult:
        counter_analysis = str(output_contract.get("counter_analysis") or "").strip()
        alternative_interpretations = _split_sentences(counter_analysis, limit=4)
        weak_assumptions = [
            f"Inferred fact may be overstated: {item}"
            for item in _normalize_string_list(fact_payload.get("inferred_facts"), limit=4)
        ]
        if not alternative_interpretations and weak_assumptions:
            alternative_interpretations = ["The initial legal theory may weaken if inferred facts are not ultimately proven."]
        return self.result(
            success=True,
            payload={
                "opposing_reading": alternative_interpretations,
                "weak_assumptions": weak_assumptions[:4],
                "alternative_applicability_path": (
                    "Alternative applicability may depend on disputed facts, procedural posture, or narrower article interpretation."
                ),
            },
            trace=["Generated structured counter-analysis to improve robustness."],
        )


class ContradictionAgent(BaseAgent):
    agent_name = "contradiction_agent"

    PROMPT = """You are the ContradictionAgent.

Your role is to detect meaningful contradictions in the legal analysis context.

Detect:
- conflicting facts between documents
- inconsistencies in timeline
- mismatch between claims and evidence

Return:
- description
- impact
- sources

Do not overstate weak signals. Use cautious wording when the contradiction is only probable."""

    def detect(
        self,
        *,
        output_contract: dict[str, Any],
        fact_payload: dict[str, Any],
        verification_payload: dict[str, Any],
    ) -> AgentResult:
        contradictions: list[dict[str, Any]] = _normalize_contradiction_rows(
            output_contract.get("contradictions"),
            limit=6,
        )

        chronology = fact_payload.get("fact_chronology") if isinstance(fact_payload, dict) else []
        if isinstance(chronology, list):
            seen_dates_by_event: dict[str, set[str]] = {}
            for entry in chronology:
                if not isinstance(entry, dict):
                    continue
                event = str(entry.get("event") or "").strip().lower()
                date = str(entry.get("date") or "").strip()
                if not event or not date:
                    continue
                seen_dates_by_event.setdefault(event, set()).add(date)
            for event, dates in seen_dates_by_event.items():
                if len(dates) >= 2:
                    contradictions.append(
                        {
                            "description": f"The event '{event}' appears with multiple dates: {', '.join(sorted(dates))}.",
                            "impact": "high",
                            "sources": ["fact_chronology"],
                        }
                    )

            notice_dates = []
            response_dates = []
            for entry in chronology:
                if not isinstance(entry, dict):
                    continue
                event = str(entry.get("event") or "").lower()
                parsed = _parse_timeline_date(str(entry.get("date") or ""))
                if parsed is None:
                    continue
                if "notice" in event:
                    notice_dates.append(parsed)
                if "response" in event:
                    response_dates.append(parsed)
            if notice_dates and response_dates and min(response_dates) < min(notice_dates):
                contradictions.append(
                    {
                        "description": "Timeline suggests a response may predate the earliest recorded notice event.",
                        "impact": "high",
                        "sources": ["fact_chronology"],
                    }
                )

        source_hints: list[str] = []
        mapping_rows = verification_payload.get("claim_to_source_map")
        if isinstance(mapping_rows, list):
            for row in mapping_rows:
                if not isinstance(row, dict):
                    continue
                source_hint = str(row.get("source") or "").strip()
                if source_hint and source_hint != "No adequate source match" and source_hint not in source_hints:
                    source_hints.append(source_hint)
                if len(source_hints) >= 3:
                    break
        for claim in _normalize_string_list(verification_payload.get("unsupported_claims"), limit=4):
            contradictions.append(
                {
                    "description": f"Claim-evidence mismatch detected: {claim}",
                    "impact": "high",
                    "sources": source_hints,
                }
            )

        deduped: list[dict[str, Any]] = []
        seen: set[str] = set()
        for item in contradictions:
            key = f"{item.get('description')}|{item.get('impact')}|{','.join(_normalize_string_list(item.get('sources'), limit=5))}".lower()
            if key in seen:
                continue
            seen.add(key)
            deduped.append(
                {
                    "description": str(item.get("description") or "").strip(),
                    "impact": str(item.get("impact") or "medium").strip().lower() or "medium",
                    "sources": _normalize_string_list(item.get("sources"), limit=5),
                }
            )
            if len(deduped) >= 8:
                break

        return self.result(
            success=True,
            payload={"contradictions": deduped},
            trace=["Detected contradictions across facts, chronology, and claim-to-source support."],
        )


class VerifierAgent(BaseAgent):
    agent_name = "verifier_agent_legal_workflow"

    PROMPT = """You are the VerifierAgent.

Your role is to verify whether each material legal claim is actually supported by the retrieved sources.

For each important claim:
- identify the supporting source
- mark whether support is direct, partial, or missing
- flag any unsupported or overstated statement

Return:
- claim-to-source mapping
- verification status
- unsupported claims
- warning notes where support is incomplete

You must be strict.
If support is partial, say partial.
If support is weak, say weak.
If a claim is unsupported, say unsupported."""

    def __init__(self) -> None:
        self.client = llm_gateway.create_client()
        self.model = llm_gateway.resolve_model("standard")

    @staticmethod
    def _claims_for_verification(
        *,
        rule_payload: dict[str, Any],
        application_payload: dict[str, Any],
        counter_payload: dict[str, Any],
    ) -> list[str]:
        claims: list[str] = []
        claims.extend(_split_sentences(str(rule_payload.get("governing_rule") or ""), limit=2))
        claims.extend(_split_sentences(str(rule_payload.get("rule_summary") or ""), limit=2))
        claims.extend(_split_sentences(str(application_payload.get("preliminary_application") or ""), limit=2))
        claims.extend(_split_sentences(" ".join(counter_payload.get("opposing_reading") or []), limit=2))
        return _dedupe_text_rows(claims, limit=8)

    @staticmethod
    def _evidence_strength_from_sources(*, sources: list[dict[str, Any]]) -> dict[str, list[str]]:
        evidence_strength = {"strong": [], "medium": [], "weak": []}
        for source in sources:
            if not isinstance(source, dict):
                continue
            bucket = _evidence_strength_bucket(str(source.get("source_type") or ""))
            reference = str(source.get("article_or_section_reference") or source.get("source_identifier") or "").strip()
            if reference and reference not in evidence_strength[bucket]:
                evidence_strength[bucket].append(reference)
        return evidence_strength

    def _build_deterministic_payload(
        self,
        *,
        output_contract: dict[str, Any],
        retrieval_payload: dict[str, Any],
        rule_payload: dict[str, Any],
        application_payload: dict[str, Any],
        counter_payload: dict[str, Any],
    ) -> dict[str, Any]:
        claims = self._claims_for_verification(
            rule_payload=rule_payload,
            application_payload=application_payload,
            counter_payload=counter_payload,
        )
        sources = retrieval_payload.get("ranked_sources") if isinstance(retrieval_payload, dict) else []
        sources = [item for item in (sources or []) if isinstance(item, dict)]
        evidence_strength = self._evidence_strength_from_sources(sources=sources)

        claim_map: list[dict[str, str]] = []
        unsupported_claims: list[str] = []
        overstated_claims: list[str] = []
        for claim in claims[:8]:
            claim_tokens = _tokenize(claim)
            best_source: dict[str, Any] | None = None
            best_score = 0.0
            for source in sources:
                source_text = " ".join(
                    [
                        str(source.get("article_or_section_reference") or ""),
                        str(source.get("short_relevant_excerpt") or ""),
                    ]
                )
                source_tokens = _tokenize(source_text)
                if not claim_tokens or not source_tokens:
                    continue
                overlap = len(claim_tokens.intersection(source_tokens)) / float(max(len(claim_tokens), 1))
                if overlap > best_score:
                    best_score = overlap
                    best_source = source
            if best_source is None or best_score < 0.12:
                support = "missing"
                source_ref = ""
                unsupported_claims.append(claim)
            elif best_score < 0.28:
                support = "partial"
                source_ref = str(best_source.get("article_or_section_reference") or "").strip()
                if any(marker in claim.lower() for marker in ("always", "clearly", "definitive", "certainly")):
                    overstated_claims.append(claim)
            else:
                support = "direct"
                source_ref = str(best_source.get("article_or_section_reference") or "").strip()
            claim_map.append(
                {
                    "claim": claim,
                    "source": source_ref or "No adequate source match",
                    "support": support,
                }
            )

        explicit_status = str(output_contract.get("verification_status") or "").strip().lower()
        if not sources:
            verification_status = "unverified"
        elif unsupported_claims:
            verification_status = "partial"
        elif any(item.get("support") == "partial" for item in claim_map):
            verification_status = "partial"
        elif explicit_status == "verified":
            verification_status = "verified"
        else:
            verification_status = "verified"
        warnings = []
        if not sources:
            warnings.append("No legal sources are available for strict claim verification.")
        if unsupported_claims:
            warnings.append("Some material claims remain unsupported by retrieved sources.")
        if overstated_claims:
            warnings.append("Some claims appear overstated compared with available source support.")
        confidence = "high" if verification_status == "verified" else "medium" if verification_status == "partial" else "low"
        return {
            "verification_status": verification_status,
            "claim_to_source_map": claim_map,
            "claim_to_source_mapping": [
                {
                    "claim": row["claim"],
                    "supporting_source": row["source"],
                    "support_level": row["support"],
                }
                for row in claim_map
            ],
            "unsupported_claims": unsupported_claims,
            "overstated_claims": overstated_claims,
            "evidence_strength": evidence_strength,
            "warnings": warnings,
            "warning_notes": warnings,
            "confidence": confidence,
        }

    def _should_use_llm(
        self,
        *,
        workflow_plan: dict[str, Any],
        deterministic_payload: dict[str, Any],
    ) -> bool:
        if not settings.LEGAL_WORKFLOW_LLM_AGENTS_ENABLED:
            return False
        if self.client is None:
            return False
        if not _is_serious_legal_workflow(workflow_plan=workflow_plan):
            return False
        return bool(deterministic_payload.get("claim_to_source_map"))

    def _generate_llm_payload(
        self,
        *,
        workflow_plan: dict[str, Any],
        output_contract: dict[str, Any],
        retrieval_payload: dict[str, Any],
        deterministic_payload: dict[str, Any],
    ) -> dict[str, Any] | None:
        if self.client is None:
            return None
        prompt = f"""
You are the VerifierAgent for a legal AI copilot.

Return VALID JSON only with this exact schema:
{{
  "verification_status": "unverified|partial|verified",
  "claim_to_source_map": [{{"claim": "", "source": "", "support": "direct|partial|missing"}}],
  "unsupported_claims": [],
  "overstated_claims": [],
  "evidence_strength": {{
    "strong": [],
    "medium": [],
    "weak": []
  }},
  "warnings": [],
  "confidence": "low|medium|high"
}}

Rules:
- Never fabricate source support.
- Never mark unsupported claims as verified.
- If support is partial, status must be "partial".
- If sources are missing, status must be "unverified".
- Maintain cautious lawyer-review framing.

Workflow context:
{json.dumps(workflow_plan, ensure_ascii=True, indent=2)}

Relevant sources:
{json.dumps(retrieval_payload, ensure_ascii=True, indent=2)}

Current deterministic verification:
{json.dumps(deterministic_payload, ensure_ascii=True, indent=2)}

Output contract context:
{json.dumps({"legal_issue": output_contract.get("legal_issue"), "application": output_contract.get("application")}, ensure_ascii=True, indent=2)}
"""
        try:
            response = self.client.responses.create(
                model=self.model,
                input=prompt,
                max_output_tokens=1200,
            )
            raw_text = llm_gateway.extract_output_text(response).strip()
            contract = validate_json_model(raw_text, _VerifierLLMContract)
            if contract is None:
                return None
            claim_map = []
            for row in contract.claim_to_source_map:
                claim = str(row.claim or "").strip()
                source = str(row.source or "").strip()
                support = str(row.support or "").strip().lower()
                if support not in {"direct", "partial", "missing"}:
                    support = "missing"
                if not claim:
                    continue
                claim_map.append(
                    {
                        "claim": claim,
                        "source": source or "No adequate source match",
                        "support": support,
                    }
                )
            unsupported_claims = _normalize_string_list(contract.unsupported_claims, limit=8)
            overstated_claims = _normalize_string_list(contract.overstated_claims, limit=8)
            evidence_strength = {
                "strong": _normalize_string_list(contract.evidence_strength.strong, limit=8),
                "medium": _normalize_string_list(contract.evidence_strength.medium, limit=8),
                "weak": _normalize_string_list(contract.evidence_strength.weak, limit=8),
            }
            if not any(evidence_strength.values()):
                return None
            if not claim_map:
                claim_map = deterministic_payload.get("claim_to_source_map") or []
            verification_status = str(contract.verification_status or "unverified").strip().lower()
            if unsupported_claims and verification_status == "verified":
                verification_status = "partial"
            if not any(evidence_strength.values()):
                verification_status = "unverified"
            if verification_status not in {"unverified", "partial", "verified"}:
                verification_status = "unverified"
            warnings = _normalize_string_list(contract.warnings, limit=8)
            if unsupported_claims and not warnings:
                warnings.append("Some material claims remain unsupported by retrieved sources.")
            return {
                "verification_status": verification_status,
                "claim_to_source_map": claim_map,
                "claim_to_source_mapping": [
                    {
                        "claim": row["claim"],
                        "supporting_source": row["source"],
                        "support_level": row["support"],
                    }
                    for row in claim_map
                ],
                "unsupported_claims": unsupported_claims,
                "overstated_claims": overstated_claims,
                "evidence_strength": evidence_strength,
                "warnings": warnings,
                "warning_notes": warnings,
                "confidence": _normalize_confidence(contract.confidence),
            }
        except Exception:
            return None

    def verify(
        self,
        *,
        workflow_plan: dict[str, Any],
        output_contract: dict[str, Any],
        retrieval_payload: dict[str, Any],
        rule_payload: dict[str, Any],
        application_payload: dict[str, Any],
        counter_payload: dict[str, Any],
    ) -> AgentResult:
        deterministic_payload = self._build_deterministic_payload(
            output_contract=output_contract,
            retrieval_payload=retrieval_payload,
            rule_payload=rule_payload,
            application_payload=application_payload,
            counter_payload=counter_payload,
        )
        trace = ["Checked whether material claims are actually supported by retrieved sources."]
        payload = deterministic_payload
        if self._should_use_llm(workflow_plan=workflow_plan, deterministic_payload=deterministic_payload):
            llm_payload = self._generate_llm_payload(
                workflow_plan=workflow_plan,
                output_contract=output_contract,
                retrieval_payload=retrieval_payload,
                deterministic_payload=deterministic_payload,
            )
            if llm_payload:
                payload = llm_payload
                trace.append("Applied LLM-backed verification with validated JSON contract.")
            else:
                trace.append("LLM verification unavailable or invalid JSON; used deterministic fallback.")
        else:
            trace.append("Skipped LLM verification for non-serious workflow or unavailable provider.")
        warnings = _normalize_string_list(payload.get("warnings") or payload.get("warning_notes"), limit=8)
        return self.result(
            success=True,
            payload=payload,
            warnings=warnings,
            trace=trace,
        )


class PositionStrengthAgent(BaseAgent):
    agent_name = "position_strength_agent"

    PROMPT = """You are the PositionStrengthAgent.

Your role is to estimate how strong the current legal position appears for internal lawyer decision support.

Base the result on:
- quality of legal sources
- completeness of facts
- verification status
- contradictions and counter-analysis

Do not present this as final legal advice.
Return a cautious preliminary strength assessment only."""

    def score(
        self,
        *,
        fact_payload: dict[str, Any],
        verification_payload: dict[str, Any],
        contradiction_payload: dict[str, Any],
        counter_payload: dict[str, Any],
    ) -> AgentResult:
        strong_sources = len(
            _normalize_string_list((verification_payload.get("evidence_strength") or {}).get("strong"), limit=8)
        )
        medium_sources = len(
            _normalize_string_list((verification_payload.get("evidence_strength") or {}).get("medium"), limit=8)
        )
        weak_sources = len(
            _normalize_string_list((verification_payload.get("evidence_strength") or {}).get("weak"), limit=8)
        )
        confirmed_facts = len(_normalize_string_list(fact_payload.get("confirmed_facts"), limit=12))
        missing_facts = len(_normalize_string_list(fact_payload.get("missing_facts"), limit=12))
        contradiction_rows = contradiction_payload.get("contradictions") if isinstance(contradiction_payload, dict) else []
        contradiction_rows = _normalize_contradiction_rows(contradiction_rows, limit=12)
        counter_strength = len(_normalize_string_list(counter_payload.get("opposing_reading"), limit=8))
        verification_status = str(verification_payload.get("verification_status") or "").strip().lower()

        score = 50
        if verification_status == "verified":
            score += 20
        elif verification_status == "partial":
            score += 8
        else:
            score -= 18

        score += min(18, strong_sources * 6)
        score += min(8, medium_sources * 2)
        score -= min(6, weak_sources * 2)
        score += min(10, confirmed_facts * 2)
        score -= min(20, missing_facts * 5)

        for item in contradiction_rows:
            impact = str(item.get("impact") or "").strip().lower()
            if impact == "high":
                score -= 15
            elif impact == "medium":
                score -= 8
            else:
                score -= 4

        if counter_strength >= 3:
            score -= 10
        elif counter_strength >= 1:
            score -= 4

        score = _clamp_score(score)
        if score >= 70:
            label = "strong"
        elif score >= 40:
            label = "arguable"
        else:
            label = "weak"

        reason = (
            f"Started from neutral baseline 50; adjusted by verification '{verification_status or 'unverified'}', "
            f"source strength ({strong_sources} strong / {medium_sources} medium / {weak_sources} weak), "
            f"fact completeness ({confirmed_facts} confirmed / {missing_facts} missing), "
            f"{len(contradiction_rows)} contradiction signal(s), and counter-analysis depth ({counter_strength})."
        )

        return self.result(
            success=True,
            payload={
                "position_strength": {
                    "score": score,
                    "label": label,
                    "reason": reason,
                }
            },
            trace=["Estimated legal position strength for lawyer decision support."],
        )


class StrategyAgent(BaseAgent):
    agent_name = "strategy_agent"

    PROMPT = """You are the StrategyAgent.

Your role is to propose a realistic legal strategy recommendation for lawyer decision support.

Consider:
- confidence level
- missing facts
- contradictions
- legal strength
- urgency

Return:
- recommended strategy type
- reason
- risk level

Do not present the recommendation as final legal advice."""

    def recommend(
        self,
        *,
        workflow_plan: dict[str, Any],
        output_contract: dict[str, Any],
        position_payload: dict[str, Any],
        verification_payload: dict[str, Any],
        contradiction_payload: dict[str, Any],
        timeline_payload: dict[str, Any],
    ) -> AgentResult:
        position_strength = position_payload.get("position_strength") if isinstance(position_payload, dict) else {}
        score = int(position_strength.get("score") or 0)
        label = str(position_strength.get("label") or "weak").strip()
        missing_count = len(_normalize_string_list(output_contract.get("missing_facts"), limit=12))
        contradiction_items = contradiction_payload.get("contradictions") if isinstance(contradiction_payload, dict) else []
        high_contradictions = sum(
            1 for item in contradiction_items or []
            if isinstance(item, dict) and str(item.get("impact") or "").strip().lower() == "high"
        )
        urgency = "low"
        for item in timeline_payload.get("timeline_legal_impact") or []:
            if not isinstance(item, dict):
                continue
            risk = str(item.get("risk") or "").strip().lower()
            if risk == "high":
                urgency = "high"
                break
            if risk == "medium":
                urgency = "medium"

        matter_type = str(workflow_plan.get("matter_type") or "").strip().lower()
        verification_status = str(
            verification_payload.get("verification_status")
            or output_contract.get("verification_status")
            or ""
        ).strip().lower()
        confidence = _normalize_confidence(output_contract.get("confidence") or workflow_plan.get("trust_level"))
        if missing_count >= 2 or verification_status in {"partial", "unverified"}:
            strategy_type = "gather_evidence"
        elif score >= 75 and urgency == "high" and verification_status == "verified":
            strategy_type = "escalate"
        elif score >= 75 and matter_type in {"litigation position memo", "civil obligation"} and verification_status == "verified":
            strategy_type = "litigate"
        elif label == "arguable" and confidence in {"low", "medium"}:
            strategy_type = "negotiate"
        elif score < 40 and urgency == "low":
            strategy_type = "wait"
        elif score >= 55:
            strategy_type = "negotiate"
        elif urgency == "low":
            strategy_type = "wait"
        else:
            strategy_type = "gather_evidence"

        if high_contradictions >= 1 or verification_status == "unverified":
            risk_level = "high"
        elif score < 60 or missing_count >= 1 or urgency == "medium":
            risk_level = "medium"
        else:
            risk_level = "low"

        reason = (
            f"Recommended strategy is '{strategy_type}' because position strength is {label} (score {score}), "
            f"verification status is '{verification_status or 'unverified'}', "
            f"confidence is '{confidence}', missing facts count is {missing_count}, "
            f"and urgency is {urgency}. This remains a preliminary recommendation for lawyer review."
        )

        return self.result(
            success=True,
            payload={
                "recommended_strategy": {
                    "type": strategy_type,
                    "reason": reason,
                    "risk_level": risk_level,
                }
            },
            trace=["Derived strategy from confidence, verification, contradictions, and position strength."],
        )


class TimelineImpactAgent(BaseAgent):
    agent_name = "timeline_impact_agent"

    PROMPT = """You are the TimelineImpactAgent.

Your role is to convert chronology into legal significance.

For each key event, identify:
- the event
- its legal effect
- its practical risk

Keep the assessment cautious and review-oriented."""

    @staticmethod
    def _effect_for_event(label: str) -> tuple[str, str]:
        lowered = str(label or "").lower()
        if "notice" in lowered:
            return ("May trigger a notice or cure-period analysis.", "medium")
        if "response" in lowered:
            return ("May affect admissions, dispute posture, or waiver arguments.", "medium")
        if any(token in lowered for token in ("hearing", "appeal", "filing", "deadline", "judgment")):
            return ("May create direct procedural consequences or time bars.", "high")
        if any(token in lowered for token in ("contract", "agreement", "signature", "signed")):
            return ("Helps anchor the baseline legal obligations and chronology.", "medium")
        if any(token in lowered for token in ("invoice", "payment", "default")):
            return ("May affect damages, default, or performance calculations.", "medium")
        return ("May influence chronology, factual fit, or narrative consistency.", "low")

    def analyze(self, *, fact_payload: dict[str, Any]) -> AgentResult:
        chronology = fact_payload.get("fact_chronology") if isinstance(fact_payload, dict) else []
        impacts: list[dict[str, str]] = []
        for entry in chronology or []:
            if not isinstance(entry, dict):
                continue
            event = str(entry.get("event") or "").strip()
            date = str(entry.get("date") or "").strip()
            if not (event or date):
                continue
            legal_effect, risk = self._effect_for_event(event)
            impacts.append(
                {
                    "event": f"{date} | {event}".strip(" |"),
                    "legal_effect": legal_effect,
                    "risk": risk,
                }
            )
            if len(impacts) >= 8:
                break
        return self.result(
            success=True,
            payload={"timeline_legal_impact": impacts},
            trace=["Mapped chronology to legal effect and risk."],
        )


class ClientRiskAgent(BaseAgent):
    agent_name = "client_risk_agent"

    PROMPT = """You are the ClientRiskAgent.

Your role is to translate legal analysis into practical client consequences.

Return:
- financial risk
- legal risk
- urgency
- short summary

Do not remove uncertainty. Keep the assessment cautious and lawyer-review oriented."""

    def summarize(
        self,
        *,
        workflow_plan: dict[str, Any],
        output_contract: dict[str, Any],
        position_payload: dict[str, Any],
        strategy_payload: dict[str, Any],
        timeline_payload: dict[str, Any],
    ) -> AgentResult:
        matter_type = str(workflow_plan.get("matter_type") or "").strip().lower()
        position_strength = position_payload.get("position_strength") if isinstance(position_payload, dict) else {}
        strategy = strategy_payload.get("recommended_strategy") if isinstance(strategy_payload, dict) else {}
        score = int(position_strength.get("score") or 0)
        risk_level = str(strategy.get("risk_level") or "medium").strip().lower()

        if matter_type == "succession":
            financial_risk = "Potential asset-distribution or entitlement exposure remains uncertain until heir and testament evidence is complete."
            legal_risk = "Succession rights may shift if heir status, civil-status records, or testament validity change."
        elif matter_type == "international private law":
            financial_risk = "Cross-border delay, enforcement cost, and forum inefficiency may increase overall client exposure."
            legal_risk = "Jurisdiction, governing-law, or recognition issues may materially change enforceability."
        else:
            financial_risk = "Potential payment, damages, or recovery exposure remains provisional pending stronger factual support."
            legal_risk = "Liability and remedy analysis may shift with missing contract, notice, or chronology evidence."

        urgency = "low"
        for item in timeline_payload.get("timeline_legal_impact") or []:
            if not isinstance(item, dict):
                continue
            item_risk = str(item.get("risk") or "").strip().lower()
            if item_risk == "high":
                urgency = "high"
                break
            if item_risk == "medium":
                urgency = "medium"
        if urgency == "low" and risk_level == "high":
            urgency = "medium"

        summary = (
            f"The client-facing risk picture is currently {risk_level}. "
            f"The position strength is {position_strength.get('label') or 'uncertain'} "
            f"(score {score}), so business or litigation action should remain tied to lawyer review and missing-fact reduction."
        )

        return self.result(
            success=True,
            payload={
                "client_risk_summary": {
                    "financial_risk": financial_risk,
                    "legal_risk": legal_risk,
                    "urgency": urgency,
                    "summary": summary,
                }
            },
            trace=["Translated legal analysis into a client risk view."],
        )


class MemoDraftingAgent(BaseAgent):
    agent_name = "memo_drafting_agent"

    PROMPT = """You are the MemoDraftingAgent.

Your role is to draft an internal legal working memo for lawyer review.

The memo must be:
- structured
- concise
- source-grounded
- cautious
- editable

Include:
- issue
- confirmed facts
- relevant legal basis
- rule summary
- preliminary application
- missing facts
- counter-analysis
- recommended next steps

Do not write as if this memo is final legal advice.
Write as a draft for internal professional review."""

    def draft(
        self,
        *,
        output_contract: dict[str, Any],
        retrieval_payload: dict[str, Any],
        rule_payload: dict[str, Any],
        application_payload: dict[str, Any],
        missing_payload: dict[str, Any],
        counter_payload: dict[str, Any],
        next_steps_payload: dict[str, Any],
    ) -> AgentResult:
        source_lines = []
        for item in retrieval_payload.get("ranked_sources") or []:
            if not isinstance(item, dict):
                continue
            label = str(item.get("article_or_section_reference") or "").strip()
            if label:
                source_lines.append(f"- {label}")
        missing_lines = []
        for item in missing_payload.get("missing_facts_list") or []:
            if not isinstance(item, dict):
                continue
            text = str(item.get("what_is_missing") or "").strip()
            if text:
                missing_lines.append(f"- {text}")
        next_steps = [f"- {step}" for step in (next_steps_payload.get("next_actions") or []) if str(step).strip()]
        memo = "\n".join(
            [
                "Internal Legal Working Memo",
                "",
                f"Issue: {output_contract.get('legal_issue') or 'Pending confirmation.'}",
                "",
                "Confirmed Facts:",
                *[f"- {fact}" for fact in output_contract.get("confirmed_facts") or []][:6],
                "",
                "Relevant Legal Basis:",
                *(source_lines[:6] or ["- Retrieved legal basis remains limited."]),
                "",
                "Rule Summary:",
                str(rule_payload.get("governing_rule") or "Rule summary pending."),
                "",
                "Preliminary Application:",
                str(application_payload.get("preliminary_application") or "Preliminary application pending."),
                "",
                "Missing Facts:",
                *(missing_lines[:6] or ["- No additional missing facts captured."]),
                "",
                "Counter-Analysis:",
                *[f"- {item}" for item in counter_payload.get("opposing_reading") or []][:4],
                "",
                "Recommended Next Steps:",
                *(next_steps[:6] or ["- Continue lawyer review before acting on this analysis."]),
            ]
        ).strip()
        return self.result(success=True, payload={"internal_memo": memo}, trace=["Drafted internal working memo."])


class ClientExplanationAgent(BaseAgent):
    agent_name = "client_explanation_agent"

    PROMPT = """You are the ClientExplanationAgent.

Your role is to convert a legal analysis into a clear client-facing explanation.

You must:
- simplify legal language
- preserve accuracy
- preserve uncertainty where it exists
- avoid sounding like a final court ruling
- make next steps understandable

Do not remove important caveats.
Do not invent reassurance.
Keep the explanation clear, respectful, and realistic."""

    def explain(
        self,
        *,
        output_contract: dict[str, Any],
        next_steps_payload: dict[str, Any],
        client_risk_payload: dict[str, Any],
    ) -> AgentResult:
        issue = str(output_contract.get("legal_issue") or "the legal issue").strip()
        application = str(output_contract.get("application") or "").strip()
        next_step = next((str(step).strip() for step in next_steps_payload.get("next_actions") or [] if str(step).strip()), "")
        risk_summary = str((client_risk_payload.get("client_risk_summary") or {}).get("summary") or "").strip()
        explanation = (
            f"At this stage, the matter appears to concern {issue}. "
            f"{application or 'The current information allows only a preliminary view.'} "
            f"{risk_summary or ''} "
            "This is not a final legal determination, and additional facts or documents may change the position. "
            f"The next practical step is: {next_step or 'confirm the missing facts and supporting documents with your lawyer.'}"
        ).strip()
        return self.result(
            success=True,
            payload={"client_explanation": re.sub(r"\s+", " ", explanation).strip()},
            trace=["Prepared client-facing explanation with preserved uncertainty."],
        )


class DraftingAgent(BaseAgent):
    agent_name = "drafting_agent_legal_workflow"

    PROMPT = """You are the DraftingAgent.

Your role is to prepare draft legal or professional text that the lawyer can review and edit.

You must:
- draft in a professional tone
- reflect only supported facts
- use placeholders where facts are missing
- avoid pretending the draft is final or approved
- preserve editability

Where important facts are missing, visibly mark them for completion."""

    def draft_text(
        self,
        *,
        workflow_plan: dict[str, Any],
        output_contract: dict[str, Any],
        missing_payload: dict[str, Any],
    ) -> AgentResult:
        missing_items = missing_payload.get("missing_facts_list") or []
        placeholders = []
        for item in missing_items[:4]:
            if not isinstance(item, dict):
                continue
            what = str(item.get("what_is_missing") or "").strip()
            if what:
                placeholders.append(f"[TO COMPLETE: {what}]")
        scaffold = "\n".join(
            [
                f"Draft type: {workflow_plan.get('recommended_output_format') or 'editable_draft'}",
                f"Matter: {workflow_plan.get('matter_type') or 'legal matter'}",
                f"Purpose: {workflow_plan.get('user_goal') or output_contract.get('legal_issue') or 'Pending clarification'}",
                "",
                "Supported facts to preserve:",
                *[f"- {fact}" for fact in output_contract.get("confirmed_facts") or []][:5],
                "",
                "Placeholders requiring completion:",
                *(placeholders or ["[TO COMPLETE: missing factual details before finalizing the draft]"]),
            ]
        ).strip()
        return self.result(
            success=True,
            payload={"draft_scaffold": scaffold},
            trace=["Prepared editable drafting scaffold with visible placeholders."],
        )


class NextStepsAgent(BaseAgent):
    agent_name = "next_steps_agent"

    PROMPT = """You are the NextStepsAgent.

Your role is to propose practical next actions for the lawyer.

Possible next actions include:
- request missing document
- verify article applicability
- prepare internal memo
- draft client explanation
- compare alternate interpretation
- build chronology
- review procedural posture

Only suggest actions that logically follow from the current analysis.
Do not suggest generic filler steps.
Prioritize actions that reduce uncertainty or move the matter forward."""

    def propose(
        self,
        *,
        output_contract: dict[str, Any],
        workflow_plan: dict[str, Any],
        verification_payload: dict[str, Any],
        strategy_payload: dict[str, Any],
    ) -> AgentResult:
        actions = _normalize_string_list(output_contract.get("next_steps"), limit=6)
        for item in _normalize_string_list(workflow_plan.get("source_needs"), limit=4):
            step = f"Request or verify: {item}"
            if step not in actions:
                actions.append(step)
        if str(verification_payload.get("verification_status") or "").strip().lower() in {"partial", "unverified"}:
            warning_step = "Verify article applicability and claim support before relying on the analysis."
            if warning_step not in actions:
                actions.insert(0, warning_step)
        strategy_type = str((strategy_payload.get("recommended_strategy") or {}).get("type") or "").strip()
        if strategy_type == "gather_evidence":
            gather_step = "Prioritize missing-document collection before taking an irreversible legal position."
            if gather_step not in actions:
                actions.insert(0, gather_step)
        elif strategy_type == "negotiate":
            negotiate_step = "Prepare a negotiation-ready summary anchored in the strongest verified sources."
            if negotiate_step not in actions:
                actions.append(negotiate_step)
        elif strategy_type in {"litigate", "escalate"}:
            escalation_step = "Prepare escalation materials and confirm procedural posture before moving forward."
            if escalation_step not in actions:
                actions.append(escalation_step)
        return self.result(
            success=True,
            payload={"next_actions": actions[:8]},
            trace=["Converted analysis into practical next actions."],
        )


class FeedbackLoopAgent(BaseAgent):
    agent_name = "feedback_loop_agent"

    PROMPT = """You are the FeedbackLoopAgent.

Your role is to prepare the backend for lawyer feedback, correction capture, and future personalization.

Keep it simple:
- store corrections
- store preferred reasoning paths
- expose the fields needed for later personalization

Do not change the legal analysis itself."""

    def prepare(self) -> AgentResult:
        return self.result(
            success=True,
            payload={
                "feedback_loop": {
                    "enabled": True,
                    "correction_capture_ready": True,
                    "preferred_reasoning_path_ready": True,
                    "personalization_ready": True,
                    "storage_fields": [
                        "lawyer_correction",
                        "preferred_reasoning_path",
                        "position_strength_override",
                        "strategy_override",
                    ],
                }
            },
            trace=["Prepared feedback-loop metadata for correction capture and future personalization."],
        )


class FinalLegalOutputComposer:
    PROMPT = """You are the Final Legal Output Composer.

Your role is to combine the outputs of the specialized legal agents into one clear lawyer-assistance response.

You must preserve:
- legal method
- source grounding
- uncertainty
- trust signals
- non-replacement positioning

Your final response must include:

1. Matter Understood
2. Confirmed Facts
3. Legal Issue
4. Relevant Legal Basis
5. Rule Summary
6. Preliminary Application
7. Missing Facts / Uncertainty
8. Counter-Analysis
9. Practical Next Steps
10. Lawyer Review Note
11. Position Strength
12. Recommended Strategy
13. Evidence Strength
14. Contradictions
15. Client Risk Summary

Additional rules:
- Keep distinctions between confirmed and inferred facts visible.
- Mention verification status when important.
- If support is partial, say so.
- If information is insufficient, avoid a firm conclusion.
- Use professional, cautious language.
- Frame the output as material for lawyer review."""

    LAWYER_REVIEW_TEMPLATE = (
        "Lawyer review note:\n"
        "This analysis is AI-assisted and intended as a structured working draft for professional legal review. "
        "It is based on the currently available facts and retrieved sources. Missing facts, additional documents, "
        "or jurisdiction-specific interpretation may change the result."
    )

    @classmethod
    def compose(
        cls,
        *,
        workflow_plan: dict[str, Any],
        output_contract: dict[str, Any],
        fact_payload: dict[str, Any],
        retrieval_payload: dict[str, Any],
        rule_payload: dict[str, Any],
        application_payload: dict[str, Any],
        missing_payload: dict[str, Any],
        counter_payload: dict[str, Any],
        verification_payload: dict[str, Any],
        next_steps_payload: dict[str, Any],
        position_payload: dict[str, Any],
        strategy_payload: dict[str, Any],
        contradiction_payload: dict[str, Any],
        timeline_payload: dict[str, Any],
        client_risk_payload: dict[str, Any],
    ) -> str:
        confirmed_facts = _normalize_string_list(fact_payload.get("confirmed_facts"), limit=6)
        inferred_facts = _normalize_string_list(fact_payload.get("inferred_facts"), limit=4)
        missing_items = []
        for item in missing_payload.get("missing_facts_list") or []:
            if not isinstance(item, dict):
                continue
            what = str(item.get("what_is_missing") or "").strip()
            why = str(item.get("why_it_matters_legally") or "").strip()
            if what:
                missing_items.append(f"- {what}: {why or 'This may materially affect the legal analysis.'}")

        source_lines = []
        for item in retrieval_payload.get("ranked_sources") or []:
            if not isinstance(item, dict):
                continue
            ref = str(item.get("article_or_section_reference") or item.get("source_identifier") or "").strip()
            why = str(item.get("why_this_source_matters") or "").strip()
            if ref:
                source_lines.append(f"- {ref}: {why or 'Retrieved as materially relevant legal basis.'}")

        counter_lines = [f"- {item}" for item in counter_payload.get("opposing_reading") or [] if str(item).strip()]
        for item in counter_payload.get("weak_assumptions") or []:
            text = str(item).strip()
            if text:
                counter_lines.append(f"- {text}")

        evidence_strength = verification_payload.get("evidence_strength") if isinstance(verification_payload, dict) else {}
        evidence_lines = []
        for bucket in ("strong", "medium", "weak"):
            rows = _normalize_string_list(evidence_strength.get(bucket), limit=6) if isinstance(evidence_strength, dict) else []
            if rows:
                evidence_lines.append(f"- {bucket.title()}: {', '.join(rows)}")

        contradiction_lines = []
        for item in contradiction_payload.get("contradictions") or []:
            if not isinstance(item, dict):
                continue
            description = str(item.get("description") or "").strip()
            impact = str(item.get("impact") or "").strip()
            sources = _normalize_string_list(item.get("sources"), limit=4)
            if description:
                if sources:
                    contradiction_lines.append(
                        f"- {description} (impact: {impact or 'unknown'}; sources: {', '.join(sources)})"
                    )
                else:
                    contradiction_lines.append(f"- {description} (impact: {impact or 'unknown'})")

        position_strength = position_payload.get("position_strength") if isinstance(position_payload, dict) else {}
        strategy = strategy_payload.get("recommended_strategy") if isinstance(strategy_payload, dict) else {}
        client_risk_summary = client_risk_payload.get("client_risk_summary") if isinstance(client_risk_payload, dict) else {}
        verification_status = str(verification_payload.get("verification_status") or output_contract.get("verification_status") or "unverified").strip()
        confidence = str(output_contract.get("confidence") or workflow_plan.get("trust_level") or "low").strip()

        lines = [
            "1. Matter Understood",
            str(workflow_plan.get("user_goal") or output_contract.get("legal_issue") or "Legal matter requiring professional review.").strip(),
            "",
            "2. Confirmed Facts",
        ]
        lines.extend([f"- {item}" for item in confirmed_facts] or ["- Confirmed facts remain limited to the currently available materials."])
        if inferred_facts:
            lines.append("- Inferred facts (not fully confirmed):")
            lines.extend(f"  - {item}" for item in inferred_facts[:4])

        lines.extend(
            [
                "",
                "3. Legal Issue",
                str(output_contract.get("legal_issue") or "The legal issue requires confirmation against the full factual record.").strip(),
                "",
                "4. Relevant Legal Basis",
            ]
        )
        lines.extend(source_lines[:6] or ["- Retrieved legal basis remains limited or incomplete."])

        lines.extend(
            [
                "",
                "5. Rule Summary",
                str(rule_payload.get("governing_rule") or "Rule synthesis remains provisional and source-limited.").strip(),
                "",
                "6. Preliminary Application",
                str(application_payload.get("preliminary_application") or "Preliminary application remains cautious because the factual record is incomplete.").strip(),
                "",
                "7. Missing Facts / Uncertainty",
            ]
        )
        lines.extend(missing_items[:8] or ["- Missing facts and evidentiary gaps should be resolved before adopting a firm legal position."])
        lines.append(f"- Verification status: {verification_status}")
        lines.append(f"- Confidence: {confidence}")

        lines.extend(["", "8. Counter-Analysis"])
        lines.extend(counter_lines[:8] or ["- Alternative interpretations may remain open depending on disputed facts or narrower source readings."])

        lines.extend(["", "9. Practical Next Steps"])
        lines.extend([f"- {item}" for item in next_steps_payload.get("next_actions") or []][:8] or ["- Continue lawyer review and request the missing materials that would reduce uncertainty."])

        lines.extend(
            [
                "",
                "10. Lawyer Review Note",
                cls.LAWYER_REVIEW_TEMPLATE,
                "",
                "11. Position Strength",
                f"- Score: {position_strength.get('score', 0)}",
                f"- Label: {position_strength.get('label', 'weak')}",
                f"- Reason: {position_strength.get('reason') or 'Strength remains provisional and review-dependent.'}",
                "",
                "12. Recommended Strategy",
                f"- Type: {strategy.get('type') or 'gather_evidence'}",
                f"- Risk level: {strategy.get('risk_level') or 'medium'}",
                f"- Reason: {strategy.get('reason') or 'Strategy requires lawyer review and may change with additional facts.'}",
                "",
                "13. Evidence Strength",
            ]
        )
        lines.extend(evidence_lines or ["- Evidence strength remains mixed and should be reviewed article by article."])

        lines.extend(["", "14. Contradictions"])
        lines.extend(contradiction_lines or ["- No major contradiction was surfaced beyond routine uncertainty signals."])

        lines.extend(
            [
                "",
                "15. Client Risk Summary",
                f"- Financial risk: {client_risk_summary.get('financial_risk') or 'Financial exposure remains preliminary.'}",
                f"- Legal risk: {client_risk_summary.get('legal_risk') or 'Legal exposure remains preliminary.'}",
                f"- Urgency: {client_risk_summary.get('urgency') or 'medium'}",
                f"- Summary: {client_risk_summary.get('summary') or 'Client risk consequences remain subject to lawyer review.'}",
            ]
        )
        return "\n".join(lines).strip()


class LegalWorkflowAgentPack:
    def __init__(self) -> None:
        self.fact_extraction_agent = FactExtractionAgent()
        self.retrieval_agent = RetrievalAgent()
        self.rule_synthesis_agent = RuleSynthesisAgent()
        self.application_agent = ApplicationAgent()
        self.missing_facts_agent = MissingFactsAgent()
        self.counter_analysis_agent = CounterAnalysisAgent()
        self.contradiction_agent = ContradictionAgent()
        self.verifier_agent = VerifierAgent()
        self.position_strength_agent = PositionStrengthAgent()
        self.strategy_agent = StrategyAgent()
        self.timeline_impact_agent = TimelineImpactAgent()
        self.client_risk_agent = ClientRiskAgent()
        self.memo_drafting_agent = MemoDraftingAgent()
        self.client_explanation_agent = ClientExplanationAgent()
        self.drafting_agent = DraftingAgent()
        self.next_steps_agent = NextStepsAgent()
        self.feedback_loop_agent = FeedbackLoopAgent()

    def run(
        self,
        *,
        workflow_plan: dict[str, Any],
        output_contract: dict[str, Any],
        case_context: dict[str, Any],
        result: dict[str, Any],
    ) -> dict[str, Any]:
        fact_result = self.fact_extraction_agent.extract(
            workflow_plan=workflow_plan,
            output_contract=output_contract,
            case_context=case_context,
        )
        retrieval_result = self.retrieval_agent.retrieve(
            workflow_plan=workflow_plan,
            output_contract=output_contract,
            result=result,
        )
        rule_result = self.rule_synthesis_agent.synthesize(
            workflow_plan=workflow_plan,
            output_contract=output_contract,
            retrieval_payload=retrieval_result.payload,
        )
        application_result = self.application_agent.apply(
            output_contract=output_contract,
            fact_payload=fact_result.payload,
        )
        missing_result = self.missing_facts_agent.identify(
            output_contract=output_contract,
            workflow_plan=workflow_plan,
        )
        counter_result = self.counter_analysis_agent.challenge(
            output_contract=output_contract,
            fact_payload=fact_result.payload,
        )
        verification_result = self.verifier_agent.verify(
            workflow_plan=workflow_plan,
            output_contract=output_contract,
            retrieval_payload=retrieval_result.payload,
            rule_payload=rule_result.payload,
            application_payload=application_result.payload,
            counter_payload=counter_result.payload,
        )
        contradiction_result = self.contradiction_agent.detect(
            output_contract=output_contract,
            fact_payload=fact_result.payload,
            verification_payload=verification_result.payload,
        )
        position_result = self.position_strength_agent.score(
            fact_payload=fact_result.payload,
            verification_payload=verification_result.payload,
            contradiction_payload=contradiction_result.payload,
            counter_payload=counter_result.payload,
        )
        timeline_result = self.timeline_impact_agent.analyze(
            fact_payload=fact_result.payload,
        )
        strategy_result = self.strategy_agent.recommend(
            workflow_plan=workflow_plan,
            output_contract=output_contract,
            position_payload=position_result.payload,
            verification_payload=verification_result.payload,
            contradiction_payload=contradiction_result.payload,
            timeline_payload=timeline_result.payload,
        )
        client_risk_result = self.client_risk_agent.summarize(
            workflow_plan=workflow_plan,
            output_contract=output_contract,
            position_payload=position_result.payload,
            strategy_payload=strategy_result.payload,
            timeline_payload=timeline_result.payload,
        )
        next_steps_result = self.next_steps_agent.propose(
            output_contract=output_contract,
            workflow_plan=workflow_plan,
            verification_payload=verification_result.payload,
            strategy_payload=strategy_result.payload,
        )
        memo_result = self.memo_drafting_agent.draft(
            output_contract=output_contract,
            retrieval_payload=retrieval_result.payload,
            rule_payload=rule_result.payload,
            application_payload=application_result.payload,
            missing_payload=missing_result.payload,
            counter_payload=counter_result.payload,
            next_steps_payload=next_steps_result.payload,
        )
        client_explanation_result = self.client_explanation_agent.explain(
            output_contract=output_contract,
            next_steps_payload=next_steps_result.payload,
            client_risk_payload=client_risk_result.payload,
        )
        drafting_result = self.drafting_agent.draft_text(
            workflow_plan=workflow_plan,
            output_contract=output_contract,
            missing_payload=missing_result.payload,
        )
        feedback_loop_result = self.feedback_loop_agent.prepare()
        composed_answer = FinalLegalOutputComposer.compose(
            workflow_plan=workflow_plan,
            output_contract=output_contract,
            fact_payload=fact_result.payload,
            retrieval_payload=retrieval_result.payload,
            rule_payload=rule_result.payload,
            application_payload=application_result.payload,
            missing_payload=missing_result.payload,
            counter_payload=counter_result.payload,
            verification_payload=verification_result.payload,
            next_steps_payload=next_steps_result.payload,
            position_payload=position_result.payload,
            strategy_payload=strategy_result.payload,
            contradiction_payload=contradiction_result.payload,
            timeline_payload=timeline_result.payload,
            client_risk_payload=client_risk_result.payload,
        )

        return {
            "workflow_template": str(workflow_plan.get("workflow_template") or "").strip() or "structured_legal_analysis",
            "agent_sequence": workflow_plan.get("agent_sequence") or [],
            "fact_extraction": fact_result.payload,
            "retrieval": retrieval_result.payload,
            "rule_synthesis": rule_result.payload,
            "application": application_result.payload,
            "missing_facts": missing_result.payload,
            "counter_analysis": counter_result.payload,
            "contradiction_analysis": contradiction_result.payload,
            "verification": verification_result.payload,
            "verification_status": verification_result.payload.get("verification_status"),
            "evidence_strength": verification_result.payload.get("evidence_strength"),
            "contradictions": contradiction_result.payload.get("contradictions"),
            "position_strength": position_result.payload.get("position_strength"),
            "recommended_strategy": strategy_result.payload.get("recommended_strategy"),
            "strategy": strategy_result.payload.get("recommended_strategy"),
            "timeline_legal_impact": timeline_result.payload.get("timeline_legal_impact"),
            "client_risk_summary": client_risk_result.payload.get("client_risk_summary"),
            "memo_drafting": memo_result.payload,
            "client_explanation": client_explanation_result.payload,
            "drafting": drafting_result.payload,
            "next_steps": next_steps_result.payload,
            "feedback_loop": feedback_loop_result.payload.get("feedback_loop"),
            "final_output_composer": {
                "answer": composed_answer,
                "lawyer_review_note_template": FinalLegalOutputComposer.LAWYER_REVIEW_TEMPLATE,
            },
            "agent_prompts": {
                "fact_extraction_agent": FactExtractionAgent.PROMPT,
                "retrieval_agent": RetrievalAgent.PROMPT,
                "rule_synthesis_agent": RuleSynthesisAgent.PROMPT,
                "application_agent": ApplicationAgent.PROMPT,
                "missing_facts_agent": MissingFactsAgent.PROMPT,
                "counter_analysis_agent": CounterAnalysisAgent.PROMPT,
                "contradiction_agent": ContradictionAgent.PROMPT,
                "verifier_agent": VerifierAgent.PROMPT,
                "position_strength_agent": PositionStrengthAgent.PROMPT,
                "strategy_agent": StrategyAgent.PROMPT,
                "timeline_impact_agent": TimelineImpactAgent.PROMPT,
                "client_risk_agent": ClientRiskAgent.PROMPT,
                "memo_drafting_agent": MemoDraftingAgent.PROMPT,
                "client_explanation_agent": ClientExplanationAgent.PROMPT,
                "drafting_agent": DraftingAgent.PROMPT,
                "next_steps_agent": NextStepsAgent.PROMPT,
                "feedback_loop_agent": FeedbackLoopAgent.PROMPT,
                "final_legal_output_composer": FinalLegalOutputComposer.PROMPT,
            },
        }


legal_workflow_agent_pack = LegalWorkflowAgentPack()
