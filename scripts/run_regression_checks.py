from __future__ import annotations

import argparse
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


def run_step(name: str, command: list[str], *, cwd: str | None = None) -> int:
    print(f"\n[{name}] {' '.join(command)}")
    completed = subprocess.run(command, cwd=cwd, check=False)
    if completed.returncode != 0:
        print(f"[{name}] FAILED with exit code {completed.returncode}")
    else:
        print(f"[{name}] PASSED")
    return completed.returncode


def main() -> int:
    parser = argparse.ArgumentParser(description="Run backend regression checks (compile + smoke + eval).")
    parser.add_argument("--skip-compile", action="store_true", help="Skip Python compile checks.")
    parser.add_argument("--skip-smoke", action="store_true", help="Skip full smoke test.")
    parser.add_argument("--skip-evals", action="store_true", help="Skip agent eval suite.")
    parser.add_argument("--smoke-port", type=int, default=8021, help="Port for full smoke test.")
    parser.add_argument("--eval-base-url", default="http://127.0.0.1:8000", help="Base URL for eval checks.")
    parser.add_argument("--eval-suite", default="scripts/evals/default_eval_suite.json", help="Eval suite path.")
    parser.add_argument("--eval-min-pass-rate", type=float, default=0.9, help="Required eval pass rate.")
    args = parser.parse_args()

    failures = 0
    started = datetime.now(timezone.utc)
    print(f"Regression run started at {started.isoformat()}Z")

    if not args.skip_compile:
        compile_command = [
            sys.executable,
            "-m",
            "py_compile",
            "backend/main.py",
            "backend/api/rag.py",
            "backend/services/ai/copilot_service.py",
            "backend/services/ai/agent_workflow_service.py",
            "backend/services/ai/agents/case_reasoning_agent.py",
            "backend/services/ai/agents/retrieval_agent.py",
            "scripts/run_agent_evals.py",
            "scripts/generate_feedback_report.py",
            "scripts/generate_advancement_log.py",
        ]
        failures += int(run_step("compile", compile_command) != 0)

    if not args.skip_smoke:
        smoke_command = [sys.executable, "scripts/full_smoke_test.py", "--port", str(args.smoke_port)]
        failures += int(run_step("smoke", smoke_command) != 0)

    if not args.skip_evals:
        eval_command = [
            sys.executable,
            "scripts/run_agent_evals.py",
            "--base-url",
            args.eval_base_url,
            "--suite",
            args.eval_suite,
            "--min-pass-rate",
            str(args.eval_min_pass_rate),
        ]
        failures += int(run_step("agent-evals", eval_command) != 0)

    finished = datetime.now(timezone.utc)
    print(f"\nRegression run finished at {finished.isoformat()}Z")
    print(f"Total failing sections: {failures}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
