from __future__ import annotations

import argparse
import json
import random
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests


DEFAULT_BASE_URL = "http://127.0.0.1:8000"
DEFAULT_SUITE_PATH = Path("scripts/evals/default_eval_suite.json")
DEFAULT_OUTPUT_DIR = Path("advancement/evals")


@dataclass
class AssertionResult:
    name: str
    passed: bool
    detail: str


@dataclass
class EvalResult:
    id: str
    prompt: str
    passed: bool
    status_code: int
    parsed_intent: str
    confidence: str
    duration_ms: float
    assertions: list[AssertionResult]
    answer_preview: str
    citation_coverage: float = 0.0
    hallucination_rate: float = 1.0
    trust_contract_valid: bool = False


CONFIDENCE_ORDER = {"low": 1, "medium": 2, "high": 3}


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def utc_stamp() -> str:
    return now_utc().strftime("%Y%m%d_%H%M%S")


def wait_for_health(base_url: str, timeout_seconds: int = 120) -> bool:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        try:
            response = requests.get(f"{base_url}/health", timeout=2)
            if response.status_code == 200:
                return True
        except Exception:
            pass
        time.sleep(0.5)
    return False


def _escape_pdf_text(value: str) -> str:
    return value.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def build_simple_pdf(text: str) -> bytes:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        lines = ["Empty content."]

    content_parts = [
        "BT",
        "/F1 11 Tf",
        "50 760 Td",
    ]
    for line in lines[:44]:
        content_parts.append(f"({_escape_pdf_text(line[:120])}) Tj")
        content_parts.append("0 -14 Td")
    content_parts.append("ET")
    content_stream = ("\n".join(content_parts) + "\n").encode("latin-1", errors="ignore")

    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        f"<< /Length {len(content_stream)} >>\nstream\n".encode("ascii") + content_stream + b"endstream",
    ]

    pdf = b"%PDF-1.4\n"
    offsets: list[int] = [0]
    for idx, obj in enumerate(objects, start=1):
        offsets.append(len(pdf))
        pdf += f"{idx} 0 obj\n".encode("ascii") + obj + b"\nendobj\n"

    xref_start = len(pdf)
    pdf += f"xref\n0 {len(objects) + 1}\n".encode("ascii")
    pdf += b"0000000000 65535 f \n"
    for offset in offsets[1:]:
        pdf += f"{offset:010d} 00000 n \n".encode("ascii")
    pdf += f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref_start}\n%%EOF".encode("ascii")
    return pdf


def request_json(
    session: requests.Session,
    method: str,
    url: str,
    *,
    token: str | None = None,
    payload: dict[str, Any] | None = None,
    files: dict[str, Any] | None = None,
    timeout_seconds: int = 90,
) -> tuple[int, Any, str]:
    headers: dict[str, str] = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    response = session.request(
        method=method.upper(),
        url=url,
        json=payload if files is None else None,
        files=files,
        headers=headers,
        timeout=timeout_seconds,
    )

    raw_text = response.text
    try:
        parsed = response.json()
    except Exception:
        parsed = {}
    return response.status_code, parsed, raw_text


def register_eval_user(session: requests.Session, base_url: str, password: str) -> tuple[str, str]:
    email = f"eval_{random.randint(100000, 999999)}@example.com"
    status_code, payload, raw_text = request_json(
        session,
        "POST",
        f"{base_url}/auth/register",
        payload={
            "name": "Eval User",
            "email": email,
            "password": password,
            "tenant_name": "EvalTenant",
            "role": "lawyer",
        },
    )
    if status_code not in (200, 201):
        raise RuntimeError(f"register failed: {status_code} {payload or raw_text}")
    return email, password


def login(session: requests.Session, base_url: str, email: str, password: str) -> str:
    status_code, payload, raw_text = request_json(
        session,
        "POST",
        f"{base_url}/auth/login",
        payload={"email": email, "password": password},
    )
    if status_code != 200:
        raise RuntimeError(f"login failed: {status_code} {payload or raw_text}")
    token = str(payload.get("access_token") or "").strip()
    if not token:
        raise RuntimeError("login response did not include an access_token")
    return token


def bootstrap_eval_case(session: requests.Session, base_url: str, token: str) -> int:
    status_code, client_payload, raw_text = request_json(
        session,
        "POST",
        f"{base_url}/clients/",
        token=token,
        payload={"name": "Eval Client", "email": f"client_{random.randint(1000, 9999)}@example.com"},
    )
    if status_code not in (200, 201):
        raise RuntimeError(f"create client failed: {status_code} {client_payload or raw_text}")
    client_id = int(client_payload["id"])

    case_title = f"Eval Case {random.randint(1000, 9999)}"
    status_code, case_payload, raw_text = request_json(
        session,
        "POST",
        f"{base_url}/cases/",
        token=token,
        payload={
            "title": case_title,
            "description": "Synthetic case for automated AI eval checks.",
            "status": "open",
            "client_id": client_id,
            "jurisdiction_country": "tunisia",
        },
    )
    if status_code not in (200, 201):
        raise RuntimeError(f"create case failed: {status_code} {case_payload or raw_text}")
    case_id = int(case_payload["id"])

    doc_1_text = """
Master Service Agreement between Atlas Retail Group SARL and Nova Logistics Tunisia SARL.
Effective date: January 12, 2026. Go-live date: February 1, 2026.
Payment terms are net 30 from invoice date. Late payment interest is 1.5% per month.
Termination rights are triggered by material breach and repeated SLA failure.
"""
    doc_2_text = """
Notice of breach and payment dispute.
Atlas states Nova missed SLA targets in February and March 2026.
Notice date: March 29, 2026. Corrective action report due by April 3, 2026.
Nova disputes material breach characterization and proposes corrective steps.
"""

    uploads = [
        ("eval_contract.pdf", doc_1_text),
        ("eval_notice.pdf", doc_2_text),
    ]
    for filename, text in uploads:
        pdf_bytes = build_simple_pdf(text)
        files = {"file": (filename, pdf_bytes, "application/pdf")}
        status_code, payload, raw_text = request_json(
            session,
            "POST",
            f"{base_url}/documents/upload?case_id={case_id}",
            token=token,
            files=files,
            timeout_seconds=360,
        )
        if status_code not in (200, 201):
            raise RuntimeError(f"upload {filename} failed: {status_code} {payload or raw_text}")

    wait_deadline = time.time() + 180
    while time.time() < wait_deadline:
        status_code, payload, raw_text = request_json(
            session,
            "GET",
            f"{base_url}/documents/case/{case_id}",
            token=token,
            timeout_seconds=30,
        )
        if status_code != 200:
            raise RuntimeError(f"list case documents failed: {status_code} {payload or raw_text}")
        items = payload if isinstance(payload, list) else []
        if items and all(str(item.get("processing_status") or "") == "processed" for item in items):
            return case_id
        time.sleep(1.0)

    raise RuntimeError("documents did not reach processing_status=processed in time")


def render_templates(value: Any, context: dict[str, str]) -> Any:
    if isinstance(value, str):
        rendered = value
        for key, item in context.items():
            rendered = rendered.replace(f"{{{{{key}}}}}", item)
        return rendered
    if isinstance(value, list):
        return [render_templates(item, context) for item in value]
    if isinstance(value, dict):
        return {key: render_templates(item, context) for key, item in value.items()}
    return value


def count_bullets(text: str) -> int:
    return sum(1 for line in (text or "").splitlines() if line.strip().startswith("- "))


MANDATORY_TRUST_SECTIONS = {
    "Issue Identification",
    "Applicable Rule / Law",
    "Application to Facts",
    "Evidence Mapping",
    "Uncertainty / Missing Information",
    "Counter-Arguments / Alternative Interpretations",
    "Risk Assessment (per party)",
    "Recommended Next Steps",
}


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _trust_panel_from_payload(payload: dict[str, Any]) -> dict[str, Any]:
    direct = payload.get("trust_panel")
    if isinstance(direct, dict):
        return direct
    structured = payload.get("structured_result")
    if isinstance(structured, dict) and isinstance(structured.get("trust_panel"), dict):
        return structured["trust_panel"]
    return {}


def _trust_validation_from_payload(payload: dict[str, Any]) -> dict[str, Any]:
    structured = payload.get("structured_result")
    if isinstance(structured, dict) and isinstance(structured.get("trust_validation"), dict):
        return structured["trust_validation"]
    return {}


def evaluate_prompt(
    session: requests.Session,
    base_url: str,
    token: str,
    spec: dict[str, Any],
    context: dict[str, str],
) -> EvalResult:
    rendered_spec = render_templates(spec, context)
    prompt = str(rendered_spec.get("prompt") or "").strip()
    if not prompt:
        return EvalResult(
            id=str(spec.get("id") or "missing_id"),
            prompt="",
            passed=False,
            status_code=0,
            parsed_intent="",
            confidence="",
            duration_ms=0.0,
            assertions=[AssertionResult(name="prompt_present", passed=False, detail="prompt is missing in suite row")],
            answer_preview="",
            trust_contract_valid=False,
        )

    started = time.perf_counter()
    status_code, payload, raw_text = request_json(
        session,
        "POST",
        f"{base_url}/ai/copilot",
        token=token,
        payload={
            "message": prompt,
            "top_k": int(rendered_spec.get("top_k") or 5),
            "use_external_research": bool(rendered_spec.get("use_external_research", False)),
            "conversation_history": rendered_spec.get("conversation_history") or [],
        },
        timeout_seconds=240,
    )
    duration_ms = (time.perf_counter() - started) * 1000.0

    assertions: list[AssertionResult] = []
    if status_code != 200:
        assertions.append(
            AssertionResult(
                name="status_code",
                passed=False,
                detail=f"expected 200, got {status_code}",
            )
        )
        preview = (raw_text or "")[:240]
        return EvalResult(
            id=str(rendered_spec.get("id") or "unknown"),
            prompt=prompt,
            passed=False,
            status_code=status_code,
            parsed_intent="",
            confidence="",
            duration_ms=duration_ms,
            assertions=assertions,
            answer_preview=preview,
            trust_contract_valid=False,
        )

    answer = str(payload.get("answer") or "").strip()
    intent = str(payload.get("parsed_intent") or "").strip()
    confidence = str(payload.get("confidence") or "").strip()
    trust_panel = _trust_panel_from_payload(payload)
    trust_validation = _trust_validation_from_payload(payload)
    trust_metrics = trust_panel.get("metrics") if isinstance(trust_panel.get("metrics"), dict) else {}
    citation_coverage = _as_float(trust_metrics.get("citation_coverage"))
    hallucination_rate = _as_float(trust_metrics.get("hallucination_rate"), default=1.0)
    trust_contract_valid = bool(trust_validation.get("is_valid")) if trust_validation else bool(trust_panel)

    require_trust_contract = bool(rendered_spec.get("require_trust_contract", True))
    if require_trust_contract:
        sections = trust_panel.get("legal_reasoning_sections") if isinstance(trust_panel, dict) else []
        present_sections = {
            str(item.get("title") or "").strip()
            for item in sections
            if isinstance(item, dict)
        } if isinstance(sections, list) else set()
        missing_sections = sorted(MANDATORY_TRUST_SECTIONS.difference(present_sections))
        assertions.append(
            AssertionResult(
                name="trust_contract_present",
                passed=bool(trust_panel) and trust_contract_valid,
                detail="trust_panel must exist and pass output-contract validation",
            )
        )
        assertions.append(
            AssertionResult(
                name="mandatory_trust_sections",
                passed=not missing_sections,
                detail="missing=" + (", ".join(missing_sections) if missing_sections else "none"),
            )
        )

    expected_intent = str(rendered_spec.get("expected_intent") or "").strip()
    if expected_intent:
        assertions.append(
            AssertionResult(
                name="intent_match",
                passed=(intent == expected_intent),
                detail=f"expected {expected_intent}, got {intent}",
            )
        )

    expected_target_type = str(rendered_spec.get("expected_target_type") or "").strip()
    if expected_target_type:
        got_target_type = str(payload.get("target_type") or "").strip()
        assertions.append(
            AssertionResult(
                name="target_type_match",
                passed=(got_target_type == expected_target_type),
                detail=f"expected {expected_target_type}, got {got_target_type or 'none'}",
            )
        )

    expected_scope = str(rendered_spec.get("expected_scope") or "").strip()
    if expected_scope:
        got_scope = str(payload.get("scope") or "").strip()
        assertions.append(
            AssertionResult(
                name="scope_match",
                passed=(got_scope == expected_scope),
                detail=f"expected {expected_scope}, got {got_scope or 'none'}",
            )
        )

    for needle in rendered_spec.get("required_substrings", []) or []:
        needle_text = str(needle)
        assertions.append(
            AssertionResult(
                name=f"contains:{needle_text}",
                passed=needle_text.lower() in answer.lower(),
                detail=f"must contain '{needle_text}'",
            )
        )

    for needle in rendered_spec.get("forbidden_substrings", []) or []:
        needle_text = str(needle)
        assertions.append(
            AssertionResult(
                name=f"not_contains:{needle_text}",
                passed=needle_text.lower() not in answer.lower(),
                detail=f"must not contain '{needle_text}'",
            )
        )

    max_bullets = rendered_spec.get("max_bullets")
    if max_bullets is not None:
        bullet_count = count_bullets(answer)
        assertions.append(
            AssertionResult(
                name="max_bullets",
                passed=bullet_count <= int(max_bullets),
                detail=f"bullets={bullet_count}, max={int(max_bullets)}",
            )
        )

    max_chars = rendered_spec.get("max_answer_chars")
    if max_chars is not None:
        assertions.append(
            AssertionResult(
                name="max_answer_chars",
                passed=len(answer) <= int(max_chars),
                detail=f"chars={len(answer)}, max={int(max_chars)}",
            )
        )

    min_confidence = str(rendered_spec.get("min_confidence") or "").strip().lower()
    if min_confidence:
        expected_level = CONFIDENCE_ORDER.get(min_confidence, 0)
        got_level = CONFIDENCE_ORDER.get(confidence.lower(), 0)
        assertions.append(
            AssertionResult(
                name="min_confidence",
                passed=got_level >= expected_level and expected_level > 0,
                detail=f"expected >= {min_confidence}, got {confidence or 'n/a'}",
            )
        )

    passed = all(assertion.passed for assertion in assertions) if assertions else True
    preview = answer[:320]
    return EvalResult(
        id=str(rendered_spec.get("id") or "unknown"),
        prompt=prompt,
        passed=passed,
        status_code=status_code,
        parsed_intent=intent,
        confidence=confidence,
        duration_ms=duration_ms,
        assertions=assertions,
        answer_preview=preview,
        citation_coverage=round(citation_coverage, 4),
        hallucination_rate=round(hallucination_rate, 4),
        trust_contract_valid=trust_contract_valid,
    )


def write_reports(
    *,
    output_dir: Path,
    base_url: str,
    case_id: int,
    results: list[EvalResult],
    suite_path: Path,
) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = utc_stamp()
    json_path = output_dir / f"agent_eval_report_{stamp}.json"
    md_path = output_dir / f"agent_eval_report_{stamp}.md"

    passed_count = sum(1 for item in results if item.passed)
    total = len(results)
    pass_rate = (passed_count / total) if total else 0.0

    payload = {
        "generated_at_utc": now_utc().isoformat(),
        "base_url": base_url,
        "case_id": case_id,
        "suite_path": str(suite_path),
        "total": total,
        "passed": passed_count,
        "failed": total - passed_count,
        "pass_rate": round(pass_rate, 4),
        "trust_quality": {
            "average_citation_coverage": round(
                sum(item.citation_coverage for item in results) / total if total else 0.0,
                4,
            ),
            "average_hallucination_rate": round(
                sum(item.hallucination_rate for item in results) / total if total else 1.0,
                4,
            ),
            "trust_contract_valid_count": sum(1 for item in results if item.trust_contract_valid),
        },
        "results": [
            {
                **asdict(result),
                "assertions": [asdict(assertion) for assertion in result.assertions],
            }
            for result in results
        ],
    }
    json_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    lines: list[str] = [
        f"# Agent Eval Report ({stamp} UTC)",
        "",
        f"- Base URL: `{base_url}`",
        f"- Case ID: `{case_id}`",
        f"- Suite: `{suite_path}`",
        f"- Passed: `{passed_count}/{total}` ({pass_rate:.1%})",
        f"- Avg citation coverage: `{(sum(item.citation_coverage for item in results) / total if total else 0.0):.1%}`",
        f"- Avg hallucination rate: `{(sum(item.hallucination_rate for item in results) / total if total else 1.0):.1%}`",
        "",
        "## Results",
        "",
    ]
    for result in results:
        lines.append(f"### {result.id} - {'PASS' if result.passed else 'FAIL'}")
        lines.append(f"- Prompt: `{result.prompt}`")
        lines.append(f"- Intent: `{result.parsed_intent or 'n/a'}`")
        lines.append(f"- Confidence: `{result.confidence or 'n/a'}`")
        lines.append(f"- Citation coverage: `{result.citation_coverage:.1%}`")
        lines.append(f"- Hallucination rate: `{result.hallucination_rate:.1%}`")
        lines.append(f"- Trust contract valid: `{result.trust_contract_valid}`")
        lines.append(f"- Duration: `{result.duration_ms:.1f} ms`")
        for assertion in result.assertions:
            marker = "PASS" if assertion.passed else "FAIL"
            lines.append(f"- [{marker}] {assertion.name}: {assertion.detail}")
        lines.append(f"- Answer preview: `{result.answer_preview}`")
        lines.append("")
    md_path.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")

    return json_path, md_path


def load_suite(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError("eval suite must be a JSON list")
    rows = [item for item in payload if isinstance(item, dict)]
    if not rows:
        raise ValueError("eval suite is empty")
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description="Run backend agent quality evaluations.")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help="API base url (default: http://127.0.0.1:8000)")
    parser.add_argument("--suite", default=str(DEFAULT_SUITE_PATH), help="Path to JSON eval suite")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR), help="Directory for eval report outputs")
    parser.add_argument("--case-id", type=int, default=None, help="Use an existing case id instead of creating synthetic data")
    parser.add_argument("--token", default=None, help="Use an existing bearer token")
    parser.add_argument("--email", default=None, help="Login email (required with --case-id when --token is not set)")
    parser.add_argument("--password", default="EvalPass!123", help="Login password (default: EvalPass!123)")
    parser.add_argument("--min-pass-rate", type=float, default=0.9, help="Fail if pass rate is below this value")
    parser.add_argument("--min-citation-coverage", type=float, default=0.95, help="Fail if average citation coverage is below this value")
    parser.add_argument("--max-hallucination-rate", type=float, default=0.05, help="Fail if average hallucination rate is above this value")
    parser.add_argument("--limit", type=int, default=0, help="Run only the first N eval rows (0 = all).")
    parser.add_argument("--ids", default="", help="Comma-separated eval ids to run.")
    parser.add_argument("--spawn-server", action="store_true", help="Spawn uvicorn for the run")
    parser.add_argument("--port", type=int, default=8031, help="Port for --spawn-server mode")
    parser.add_argument("--python-executable", default=sys.executable, help="Python executable for --spawn-server mode")
    args = parser.parse_args()

    suite_path = Path(args.suite)
    output_dir = Path(args.output_dir)
    suite_rows = load_suite(suite_path)
    if args.ids.strip():
        selected_ids = {item.strip() for item in args.ids.split(",") if item.strip()}
        suite_rows = [row for row in suite_rows if str(row.get("id") or "").strip() in selected_ids]
    if args.limit and args.limit > 0:
        suite_rows = suite_rows[: args.limit]
    if not suite_rows:
        print("No eval rows selected after applying filters (--ids/--limit).", file=sys.stderr)
        return 1

    base_url = args.base_url.rstrip("/")
    server_proc: subprocess.Popen[bytes] | None = None
    if args.spawn_server:
        base_url = f"http://127.0.0.1:{args.port}"
        server_proc = subprocess.Popen(
            [
                args.python_executable,
                "-m",
                "uvicorn",
                "backend.main:app",
                "--host",
                "127.0.0.1",
                "--port",
                str(args.port),
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        if not wait_for_health(base_url):
            print("Server did not become healthy in time.", file=sys.stderr)
            return 1

    session = requests.Session()
    try:
        token = args.token
        case_id = args.case_id

        if not token and case_id is not None:
            if not args.email:
                print("--email is required when using --case-id without --token", file=sys.stderr)
                return 1
            token = login(session, base_url, args.email, args.password)

        if case_id is None:
            email, password = register_eval_user(session, base_url, args.password)
            token = login(session, base_url, email, password)
            case_id = bootstrap_eval_case(session, base_url, token)

        assert token is not None
        assert case_id is not None
        context = {"case_id": str(case_id)}

        results = [
            evaluate_prompt(
                session=session,
                base_url=base_url,
                token=token,
                spec=row,
                context=context,
            )
            for row in suite_rows
        ]

        json_path, md_path = write_reports(
            output_dir=output_dir,
            base_url=base_url,
            case_id=case_id,
            results=results,
            suite_path=suite_path,
        )

        passed = sum(1 for row in results if row.passed)
        total = len(results)
        pass_rate = (passed / total) if total else 0.0
        avg_citation_coverage = (sum(row.citation_coverage for row in results) / total) if total else 0.0
        avg_hallucination_rate = (sum(row.hallucination_rate for row in results) / total) if total else 1.0
        print(f"Eval results: {passed}/{total} passed ({pass_rate:.1%})")
        print(f"Average citation coverage: {avg_citation_coverage:.1%}")
        print(f"Average hallucination rate: {avg_hallucination_rate:.1%}")
        print(f"JSON report: {json_path}")
        print(f"Markdown report: {md_path}")

        gate_failed = False
        if pass_rate < float(args.min_pass_rate):
            print(
                f"Pass rate {pass_rate:.1%} is below required threshold {float(args.min_pass_rate):.1%}",
                file=sys.stderr,
            )
            gate_failed = True
        if avg_citation_coverage < float(args.min_citation_coverage):
            print(
                f"Citation coverage {avg_citation_coverage:.1%} is below required threshold "
                f"{float(args.min_citation_coverage):.1%}",
                file=sys.stderr,
            )
            gate_failed = True
        if avg_hallucination_rate > float(args.max_hallucination_rate):
            print(
                f"Hallucination rate {avg_hallucination_rate:.1%} is above allowed threshold "
                f"{float(args.max_hallucination_rate):.1%}",
                file=sys.stderr,
            )
            gate_failed = True
        return 1 if gate_failed else 0
    finally:
        if server_proc is not None:
            server_proc.terminate()
            try:
                server_proc.wait(timeout=10)
            except Exception:
                server_proc.kill()


if __name__ == "__main__":
    sys.exit(main())
