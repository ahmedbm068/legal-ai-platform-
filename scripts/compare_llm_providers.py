from __future__ import annotations

import argparse
import json
import math
import os
import subprocess
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_SUITE_PATH = Path("scripts/evals/default_eval_suite.json")
DEFAULT_OUTPUT_ROOT = Path("advancement/evals/provider_compare")
DEFAULT_GROQ_BASE_URL = "https://api.groq.com/openai/v1"
DEFAULT_CANDIDATE_BASE_URL = "https://openrouter.ai/api/v1"


@dataclass
class ProviderRun:
    name: str
    model: str
    base_url: str
    pass_rate: float
    passed: int
    total: int
    average_duration_ms: float
    p95_duration_ms: float
    report_json_path: str


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


def _load_eval_report(report_path: Path) -> tuple[int, int, float, list[float]]:
    payload = json.loads(report_path.read_text(encoding="utf-8"))
    passed = int(payload.get("passed") or 0)
    total = int(payload.get("total") or 0)
    pass_rate = float(payload.get("pass_rate") or 0.0)
    durations = [
        float(item.get("duration_ms") or 0.0)
        for item in payload.get("results", [])
        if isinstance(item, dict)
    ]
    return passed, total, pass_rate, durations


def _find_latest_report_json(output_dir: Path) -> Path:
    candidates = sorted(
        output_dir.glob("agent_eval_report_*.json"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    if not candidates:
        raise RuntimeError(f"No eval JSON report found under {output_dir}")
    return candidates[0]


def _run_eval(
    *,
    project_root: Path,
    python_executable: str,
    output_dir: Path,
    suite_path: Path,
    port: int,
    limit: int,
    ids: str,
    env_overrides: dict[str, str],
) -> ProviderRun:
    output_dir.mkdir(parents=True, exist_ok=True)

    command = [
        python_executable,
        "scripts/run_agent_evals.py",
        "--suite",
        str(suite_path),
        "--output-dir",
        str(output_dir),
        "--spawn-server",
        "--port",
        str(port),
        "--min-pass-rate",
        "0",
        "--python-executable",
        python_executable,
    ]
    if limit > 0:
        command.extend(["--limit", str(limit)])
    if ids.strip():
        command.extend(["--ids", ids.strip()])

    run_env = os.environ.copy()
    run_env.update(env_overrides)
    # Benchmark runs should be self-contained and not depend on external invite token flows.
    run_env.setdefault("STAFF_INVITE_ONLY", "false")

    result = subprocess.run(
        command,
        cwd=project_root,
        env=run_env,
        text=True,
        capture_output=True,
    )
    if result.returncode != 0:
        stderr = (result.stderr or "").strip()
        stdout = (result.stdout or "").strip()
        raise RuntimeError(
            "run_agent_evals failed.\n"
            f"Command: {' '.join(command)}\n"
            f"STDOUT:\n{stdout}\n\nSTDERR:\n{stderr}"
        )

    report_path = _find_latest_report_json(output_dir)
    passed, total, pass_rate, durations = _load_eval_report(report_path)

    return ProviderRun(
        name=env_overrides["PROVIDER_COMPARE_NAME"],
        model=env_overrides["LLM_MODEL"],
        base_url=env_overrides["LLM_BASE_URL"],
        pass_rate=pass_rate,
        passed=passed,
        total=total,
        average_duration_ms=_average(durations),
        p95_duration_ms=_p95(durations),
        report_json_path=str(report_path),
    )


def _pick_winner(groq: ProviderRun, candidate: ProviderRun) -> tuple[str, str]:
    if candidate.pass_rate > groq.pass_rate:
        return candidate.name, "Higher pass rate"
    if groq.pass_rate > candidate.pass_rate:
        return groq.name, "Higher pass rate"

    if candidate.average_duration_ms < groq.average_duration_ms:
        return candidate.name, "Same pass rate, lower average latency"
    if groq.average_duration_ms < candidate.average_duration_ms:
        return groq.name, "Same pass rate, lower average latency"

    return "tie", "Pass rate and average latency are effectively equal"


def _write_comparison_report(output_root: Path, payload: dict[str, Any]) -> tuple[Path, Path]:
    output_root.mkdir(parents=True, exist_ok=True)
    stamp = utc_stamp()
    json_path = output_root / f"provider_compare_{stamp}.json"
    md_path = output_root / f"provider_compare_{stamp}.md"

    json_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    providers = payload.get("providers", [])
    lines = [
        f"# Provider Comparison ({stamp} UTC)",
        "",
        f"- Suite: `{payload.get('suite_path')}`",
        f"- Limit: `{payload.get('limit')}`",
        f"- Winner: `{payload.get('winner')}` ({payload.get('winner_reason')})",
        "",
        "## Runs",
        "",
        "| Provider | Model | Base URL | Passed/Total | Pass Rate | Avg Latency (ms) | P95 Latency (ms) |",
        "|---|---|---|---:|---:|---:|---:|",
    ]

    for item in providers:
        if not isinstance(item, dict):
            continue
        lines.append(
            "| "
            f"{item.get('name')} | "
            f"{item.get('model')} | "
            f"{item.get('base_url')} | "
            f"{item.get('passed')}/{item.get('total')} | "
            f"{float(item.get('pass_rate') or 0.0):.2%} | "
            f"{float(item.get('average_duration_ms') or 0.0):.1f} | "
            f"{float(item.get('p95_duration_ms') or 0.0):.1f} |"
        )

    lines.append("")
    lines.append("## Raw Eval Reports")
    lines.append("")
    for item in providers:
        if not isinstance(item, dict):
            continue
        lines.append(f"- {item.get('name')}: `{item.get('report_json_path')}`")

    md_path.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")
    return json_path, md_path


def _resolve_candidate_key(args: argparse.Namespace) -> str:
    if args.candidate_api_key and args.candidate_api_key.strip():
        return args.candidate_api_key.strip()

    env_value = os.getenv(args.candidate_api_key_env, "").strip()
    return env_value


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Compare Groq vs alternate OpenAI-compatible provider using the existing agent eval suite."
    )
    parser.add_argument("--suite", default=str(DEFAULT_SUITE_PATH), help="Path to eval suite JSON")
    parser.add_argument("--output-root", default=str(DEFAULT_OUTPUT_ROOT), help="Directory for comparison reports")
    parser.add_argument("--limit", type=int, default=12, help="Run first N eval rows (0 = all)")
    parser.add_argument("--ids", default="", help="Comma-separated eval ids to run")
    parser.add_argument("--python-executable", default=sys.executable, help="Python executable")

    parser.add_argument("--grok-name", default="grok", help="Display name for Groq run")
    parser.add_argument("--grok-base-url", default=DEFAULT_GROQ_BASE_URL, help="Groq base URL")
    parser.add_argument("--grok-model", default="llama-3.3-70b-versatile", help="Groq model")
    parser.add_argument("--grok-port", type=int, default=8041, help="Port for Groq eval server")

    parser.add_argument("--candidate-name", default="candidate", help="Display name for alternate provider run")
    parser.add_argument("--candidate-base-url", default=DEFAULT_CANDIDATE_BASE_URL, help="Alternate provider base URL")
    parser.add_argument("--candidate-model", default="openai/gpt-4o-mini", help="Alternate provider model")
    parser.add_argument("--candidate-port", type=int, default=8042, help="Port for alternate provider eval server")
    parser.add_argument("--candidate-api-key", default="", help="Alternate provider API key")
    parser.add_argument(
        "--candidate-api-key-env",
        default="OPENAI_API_KEY",
        help="Environment variable to read alternate key from if --candidate-api-key is omitted",
    )

    args = parser.parse_args()

    candidate_key = _resolve_candidate_key(args)
    if not candidate_key:
        print(
            "Missing alternate provider key. Provide --candidate-api-key or set "
            f"{args.candidate_api_key_env} before running.",
            file=sys.stderr,
        )
        return 1

    project_root = Path(__file__).resolve().parents[1]
    suite_path = Path(args.suite)
    if not suite_path.is_absolute():
        suite_path = project_root / suite_path
    if not suite_path.exists():
        print(f"Eval suite not found: {suite_path}", file=sys.stderr)
        return 1

    output_root = Path(args.output_root)
    if not output_root.is_absolute():
        output_root = project_root / output_root

    try:
        groq_run = _run_eval(
            project_root=project_root,
            python_executable=args.python_executable,
            output_dir=output_root / "grok",
            suite_path=suite_path,
            port=args.grok_port,
            limit=args.limit,
            ids=args.ids,
            env_overrides={
                "PROVIDER_COMPARE_NAME": args.grok_name,
                "LLM_BASE_URL": args.grok_base_url,
                "LLM_MODEL": args.grok_model,
                "SUMMARY_AGENT_MODEL": args.grok_model,
                "OPENAI_API_KEY": "",
            },
        )

        candidate_run = _run_eval(
            project_root=project_root,
            python_executable=args.python_executable,
            output_dir=output_root / "candidate",
            suite_path=suite_path,
            port=args.candidate_port,
            limit=args.limit,
            ids=args.ids,
            env_overrides={
                "PROVIDER_COMPARE_NAME": args.candidate_name,
                "LLM_BASE_URL": args.candidate_base_url,
                "LLM_MODEL": args.candidate_model,
                "SUMMARY_AGENT_MODEL": args.candidate_model,
                "OPENAI_API_KEY": candidate_key,
                "GROQ_API_KEY": "",
            },
        )
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        return 1

    winner, winner_reason = _pick_winner(groq_run, candidate_run)
    payload = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "suite_path": str(suite_path),
        "limit": args.limit,
        "ids": args.ids,
        "winner": winner,
        "winner_reason": winner_reason,
        "providers": [asdict(groq_run), asdict(candidate_run)],
    }

    json_path, md_path = _write_comparison_report(output_root, payload)

    print(f"Winner: {winner} ({winner_reason})")
    print(f"Comparison JSON: {json_path}")
    print(f"Comparison Markdown: {md_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
