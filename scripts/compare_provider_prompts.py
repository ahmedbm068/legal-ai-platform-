from __future__ import annotations

import argparse
import json
import math
import os
import re
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from openai import OpenAI


DEFAULT_OUTPUT_ROOT = Path("advancement/evals/provider_compare")
DEFAULT_GROQ_BASE_URL = "https://api.groq.com/openai/v1"
DEFAULT_GROQ_MODEL = "llama-3.3-70b-versatile"
DEFAULT_CANDIDATE_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai"
DEFAULT_CANDIDATE_MODEL = "gemini-2.5-flash"


@dataclass
class PromptSpec:
    id: str
    prompt: str
    required_patterns: list[str]
    min_chars: int = 120


@dataclass
class PromptRunResult:
    prompt_id: str
    success: bool
    score: float
    latency_ms: float
    output_preview: str
    error: str | None


@dataclass
class ProviderSummary:
    name: str
    model: str
    base_url: str
    total_runs: int
    passed_runs: int
    pass_rate: float
    average_score: float
    average_latency_ms: float
    p95_latency_ms: float
    total_prompt_errors: int
    total_tokens: int
    run_results: list[PromptRunResult]


def utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")


def _p95(values: list[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, math.ceil(0.95 * len(ordered)) - 1))
    return float(ordered[index])


def _average(values: list[float]) -> float:
    if not values:
        return 0.0
    return float(sum(values) / len(values))


def _preview(value: str, max_chars: int = 260) -> str:
    compact = re.sub(r"\s+", " ", (value or "")).strip()
    if len(compact) <= max_chars:
        return compact
    return f"{compact[: max_chars - 1].rstrip()}..."


def _load_dotenv_map(dotenv_path: Path) -> dict[str, str]:
    env_map: dict[str, str] = {}
    if not dotenv_path.exists():
        return env_map

    for raw_line in dotenv_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        env_map[key.strip()] = value.strip()
    return env_map


def _resolve_value(cli_value: str, env_name: str, dotenv_map: dict[str, str]) -> str:
    if cli_value.strip():
        return cli_value.strip()

    env_value = os.getenv(env_name, "").strip()
    if env_value:
        return env_value

    return dotenv_map.get(env_name, "").strip()


def _build_default_headers(base_url: str, dotenv_map: dict[str, str]) -> dict[str, str]:
    normalized = (base_url or "").strip().lower()
    if "openrouter.ai" not in normalized:
        return {}

    headers: dict[str, str] = {}
    site_url = os.getenv("OPENROUTER_SITE_URL", "").strip() or dotenv_map.get("OPENROUTER_SITE_URL", "").strip()
    app_name = os.getenv("OPENROUTER_APP_NAME", "").strip() or dotenv_map.get("OPENROUTER_APP_NAME", "").strip()

    if site_url:
        headers["HTTP-Referer"] = site_url
    if app_name:
        headers["X-Title"] = app_name

    return headers


def _default_prompt_suite() -> list[PromptSpec]:
    return [
        PromptSpec(
            id="summary_brief",
            prompt=(
                "You are assisting on a commercial contract dispute. "
                "Write a concise case brief with exactly these headings: Summary, Key Risks, Next Steps."
            ),
            required_patterns=[
                r"(?im)^\s*#*\s*summary\b[:\s]*",
                r"(?im)^\s*#*\s*key risks\b[:\s]*",
                r"(?im)^\s*#*\s*next steps\b[:\s]*",
            ]
        ),
        PromptSpec(
            id="timeline_extraction",
            prompt=(
                "From the facts below, build a timeline of at least three events with date and event text. "
                "Facts: Contract signed 2025-01-04; Notice of breach sent 2025-02-11; Payment default on 2025-03-01; "
                "Settlement offer on 2025-03-15."
            ),
            required_patterns=[r"(?m)^1\.\s", r"2025-01-04|2025-02-11|2025-03-01|2025-03-15"]
        ),
        PromptSpec(
            id="client_email",
            prompt=(
                "Draft a short client email update with headings Subject and Next Steps. "
                "Tone should be calm and practical."
            ),
            required_patterns=[
                r"(?im)^\s*#*\s*subject\b[:\s]*",
                r"(?im)^\s*#*\s*next steps\b[:\s]*",
            ]
        ),
        PromptSpec(
            id="evidence_gaps",
            prompt=(
                "List the top evidence gaps for a wrongful termination case. "
                "Use headings: Key Gaps and Recommended Collection Plan."
            ),
            required_patterns=[
                r"(?im)^\s*#*\s*key gaps\b[:\s]*",
                r"(?im)^\s*#*\s*recommended collection plan\b[:\s]*",
            ]
        ),
        PromptSpec(
            id="risk_matrix",
            prompt=(
                "Provide a simple risk matrix with three bullets in the format: risk - impact - mitigation."
            ),
            required_patterns=[r"(?im)^\s*[-*]\s+[^\n]+\s-\s[^\n]+\s-\s[^\n]+"]
        ),
        PromptSpec(
            id="legal_answer",
            prompt=(
                "Answer this: Can an employer terminate without notice under Tunisian labor law? "
                "Use headings Answer and Caveats, and avoid definitive legal advice."
            ),
            required_patterns=[
                r"(?im)^\s*#*\s*answer\b[:\s]*",
                r"(?im)^\s*#*\s*caveats\b[:\s]*",
            ]
        ),
    ]


def _score_output(spec: PromptSpec, output: str) -> tuple[float, bool]:
    cleaned = (output or "").strip()
    length_pass = len(cleaned) >= spec.min_chars
    pattern_hits = sum(1 for pattern in spec.required_patterns if re.search(pattern, cleaned))

    max_score_units = 1 + len(spec.required_patterns)
    earned = (1 if length_pass else 0) + pattern_hits
    score = earned / max_score_units if max_score_units else 0.0

    success = length_pass and pattern_hits == len(spec.required_patterns)
    return score, success


def _run_provider_suite(
    *,
    provider_name: str,
    api_key: str,
    base_url: str,
    model: str,
    prompt_specs: list[PromptSpec],
    runs_per_prompt: int,
    temperature: float,
    timeout_seconds: int,
    dotenv_map: dict[str, str],
) -> ProviderSummary:
    client_kwargs: dict[str, Any] = {
        "api_key": api_key,
        "timeout": timeout_seconds,
        "max_retries": 1,
    }
    if base_url:
        client_kwargs["base_url"] = base_url

    headers = _build_default_headers(base_url, dotenv_map)
    if headers:
        client_kwargs["default_headers"] = headers

    client = OpenAI(**client_kwargs)

    run_results: list[PromptRunResult] = []
    latencies: list[float] = []
    scores: list[float] = []
    passed = 0
    errors = 0
    total_tokens = 0

    for spec in prompt_specs:
        for _ in range(max(1, runs_per_prompt)):
            start = time.perf_counter()
            try:
                response = client.chat.completions.create(
                    model=model,
                    messages=[{"role": "user", "content": spec.prompt}],
                    temperature=temperature,
                )
                latency_ms = (time.perf_counter() - start) * 1000.0
                content = (
                    response.choices[0].message.content
                    if response and response.choices and response.choices[0].message
                    else ""
                ) or ""
                usage = getattr(response, "usage", None)
                if usage is not None:
                    total_tokens += int(getattr(usage, "total_tokens", 0) or 0)

                score, success = _score_output(spec, content)
                if success:
                    passed += 1
                scores.append(score)
                latencies.append(latency_ms)
                run_results.append(
                    PromptRunResult(
                        prompt_id=spec.id,
                        success=success,
                        score=score,
                        latency_ms=latency_ms,
                        output_preview=_preview(content),
                        error=None,
                    )
                )
            except Exception as exc:
                latency_ms = (time.perf_counter() - start) * 1000.0
                errors += 1
                latencies.append(latency_ms)
                run_results.append(
                    PromptRunResult(
                        prompt_id=spec.id,
                        success=False,
                        score=0.0,
                        latency_ms=latency_ms,
                        output_preview="",
                        error=str(exc),
                    )
                )

    total_runs = len(run_results)
    pass_rate = (passed / total_runs) if total_runs else 0.0

    return ProviderSummary(
        name=provider_name,
        model=model,
        base_url=base_url,
        total_runs=total_runs,
        passed_runs=passed,
        pass_rate=pass_rate,
        average_score=_average(scores),
        average_latency_ms=_average(latencies),
        p95_latency_ms=_p95(latencies),
        total_prompt_errors=errors,
        total_tokens=total_tokens,
        run_results=run_results,
    )


def _pick_winner(a: ProviderSummary, b: ProviderSummary) -> tuple[str, str]:
    if b.pass_rate > a.pass_rate:
        return b.name, "Higher prompt pass rate"
    if a.pass_rate > b.pass_rate:
        return a.name, "Higher prompt pass rate"

    if b.average_score > a.average_score:
        return b.name, "Higher average structural quality score"
    if a.average_score > b.average_score:
        return a.name, "Higher average structural quality score"

    if b.average_latency_ms < a.average_latency_ms:
        return b.name, "Same quality score with lower latency"
    if a.average_latency_ms < b.average_latency_ms:
        return a.name, "Same quality score with lower latency"

    return "tie", "Overall metrics are effectively equal"


def _write_report(
    *,
    output_root: Path,
    args: argparse.Namespace,
    provider_a: ProviderSummary,
    provider_b: ProviderSummary,
    winner: str,
    winner_reason: str,
) -> tuple[Path, Path]:
    output_root.mkdir(parents=True, exist_ok=True)
    stamp = utc_stamp()
    json_path = output_root / f"provider_prompt_compare_{stamp}.json"
    md_path = output_root / f"provider_prompt_compare_{stamp}.md"

    payload = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "runs_per_prompt": args.runs_per_prompt,
        "temperature": args.temperature,
        "winner": winner,
        "winner_reason": winner_reason,
        "providers": [
            {
                **asdict(provider_a),
                "run_results": [asdict(item) for item in provider_a.run_results],
            },
            {
                **asdict(provider_b),
                "run_results": [asdict(item) for item in provider_b.run_results],
            },
        ],
    }

    json_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    lines = [
        f"# Provider Prompt Comparison ({stamp} UTC)",
        "",
        f"- Winner: `{winner}` ({winner_reason})",
        f"- Runs per prompt: `{args.runs_per_prompt}`",
        f"- Temperature: `{args.temperature}`",
        "",
        "## Summary",
        "",
        "| Provider | Model | Passed/Total | Pass Rate | Avg Score | Avg Latency (ms) | P95 Latency (ms) | Errors | Tokens |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|",
    ]

    for provider in [provider_a, provider_b]:
        lines.append(
            "| "
            f"{provider.name} | "
            f"{provider.model} | "
            f"{provider.passed_runs}/{provider.total_runs} | "
            f"{provider.pass_rate:.2%} | "
            f"{provider.average_score:.3f} | "
            f"{provider.average_latency_ms:.1f} | "
            f"{provider.p95_latency_ms:.1f} | "
            f"{provider.total_prompt_errors} | "
            f"{provider.total_tokens} |"
        )

    lines.extend([
        "",
        "## Sample Outputs",
        "",
    ])

    for provider in [provider_a, provider_b]:
        lines.append(f"### {provider.name}")
        for item in provider.run_results[:6]:
            status = "PASS" if item.success else "FAIL"
            lines.append(f"- [{status}] {item.prompt_id}: `{item.output_preview or item.error or ''}`")
        lines.append("")

    md_path.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")
    return json_path, md_path


def main() -> int:
    parser = argparse.ArgumentParser(description="Compare two LLM providers on a legal prompt quality mini-suite.")
    parser.add_argument("--output-root", default=str(DEFAULT_OUTPUT_ROOT), help="Directory for comparison outputs")
    parser.add_argument("--runs-per-prompt", type=int, default=1, help="Number of runs per prompt per provider")
    parser.add_argument("--temperature", type=float, default=0.2, help="Sampling temperature")
    parser.add_argument("--timeout-seconds", type=int, default=60, help="Client timeout")

    parser.add_argument("--provider-a-name", default="grok", help="Provider A display name")
    parser.add_argument("--provider-a-api-key", default="", help="Provider A API key")
    parser.add_argument("--provider-a-api-key-env", default="GROQ_API_KEY", help="Provider A API key env var")
    parser.add_argument("--provider-a-base-url", default="", help="Provider A base URL")
    parser.add_argument("--provider-a-base-url-env", default="GROQ_BASE_URL", help="Provider A base URL env var")
    parser.add_argument("--provider-a-model", default=DEFAULT_GROQ_MODEL, help="Provider A model")

    parser.add_argument("--provider-b-name", default="candidate", help="Provider B display name")
    parser.add_argument("--provider-b-api-key", default="", help="Provider B API key")
    parser.add_argument("--provider-b-api-key-env", default="OPENAI_API_KEY", help="Provider B API key env var")
    parser.add_argument("--provider-b-base-url", default=DEFAULT_CANDIDATE_BASE_URL, help="Provider B base URL")
    parser.add_argument("--provider-b-base-url-env", default="LLM_BASE_URL", help="Provider B base URL env var")
    parser.add_argument("--provider-b-model", default=DEFAULT_CANDIDATE_MODEL, help="Provider B model")

    args = parser.parse_args()

    project_root = Path(__file__).resolve().parents[1]
    dotenv_map = _load_dotenv_map(project_root / ".env")

    provider_a_api_key = _resolve_value(args.provider_a_api_key, args.provider_a_api_key_env, dotenv_map)
    provider_a_base_url = _resolve_value(args.provider_a_base_url, args.provider_a_base_url_env, dotenv_map) or DEFAULT_GROQ_BASE_URL
    provider_b_api_key = _resolve_value(args.provider_b_api_key, args.provider_b_api_key_env, dotenv_map)
    provider_b_base_url = _resolve_value(args.provider_b_base_url, args.provider_b_base_url_env, dotenv_map) or DEFAULT_CANDIDATE_BASE_URL

    if not provider_a_api_key:
        print(f"Provider A API key missing. Set {args.provider_a_api_key_env} or pass --provider-a-api-key.")
        return 1
    if not provider_b_api_key:
        print(f"Provider B API key missing. Set {args.provider_b_api_key_env} or pass --provider-b-api-key.")
        return 1

    prompt_specs = _default_prompt_suite()

    provider_a = _run_provider_suite(
        provider_name=args.provider_a_name,
        api_key=provider_a_api_key,
        base_url=provider_a_base_url,
        model=args.provider_a_model,
        prompt_specs=prompt_specs,
        runs_per_prompt=args.runs_per_prompt,
        temperature=args.temperature,
        timeout_seconds=args.timeout_seconds,
        dotenv_map=dotenv_map,
    )

    provider_b = _run_provider_suite(
        provider_name=args.provider_b_name,
        api_key=provider_b_api_key,
        base_url=provider_b_base_url,
        model=args.provider_b_model,
        prompt_specs=prompt_specs,
        runs_per_prompt=args.runs_per_prompt,
        temperature=args.temperature,
        timeout_seconds=args.timeout_seconds,
        dotenv_map=dotenv_map,
    )

    winner, winner_reason = _pick_winner(provider_a, provider_b)

    output_root = Path(args.output_root)
    if not output_root.is_absolute():
        output_root = project_root / output_root

    json_path, md_path = _write_report(
        output_root=output_root,
        args=args,
        provider_a=provider_a,
        provider_b=provider_b,
        winner=winner,
        winner_reason=winner_reason,
    )

    print(f"Winner: {winner} ({winner_reason})")
    print(f"Comparison JSON: {json_path}")
    print(f"Comparison Markdown: {md_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
