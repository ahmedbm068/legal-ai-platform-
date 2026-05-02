from __future__ import annotations

import argparse
import json
from pathlib import Path

import joblib

from train_supervised_legal_models import DEFAULT_OUTPUT_DIR, TASKS, task_text


TASK_BY_NAME = {task.name: task for task in TASKS}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a saved supervised legal model.")
    parser.add_argument(
        "--model",
        choices=sorted(TASK_BY_NAME),
        required=True,
        help="Model artifact folder name.",
    )
    parser.add_argument("--text", help="Text input for document_type_classifier or case_risk_triage.")
    parser.add_argument("--claim", help="Claim text for claim_evidence_verifier.")
    parser.add_argument("--evidence", help="Evidence text for claim_evidence_verifier.")
    parser.add_argument("--artifact-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    return parser.parse_args()


def row_from_args(args: argparse.Namespace) -> dict:
    if args.model == "claim_evidence_verifier":
        if not args.claim or not args.evidence:
            raise SystemExit("--claim and --evidence are required for claim_evidence_verifier")
        return {"claim": args.claim, "evidence": args.evidence}

    if not args.text:
        raise SystemExit("--text is required for this model")

    if args.model == "document_type_classifier":
        return {"text": args.text}
    if args.model == "case_risk_triage":
        return {"case_summary": args.text}
    raise SystemExit(f"Unsupported model: {args.model}")


def main() -> None:
    args = parse_args()
    task = TASK_BY_NAME[args.model]
    model_path = args.artifact_dir / args.model / "model.joblib"
    if not model_path.exists():
        raise SystemExit(f"Missing model artifact: {model_path}")

    model = joblib.load(model_path)
    features = task_text(row_from_args(args), task)
    prediction = model.predict([features])[0]
    print(json.dumps({"model": args.model, "prediction": prediction}, indent=2))


if __name__ == "__main__":
    main()
