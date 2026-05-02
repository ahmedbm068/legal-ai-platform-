from __future__ import annotations

import argparse
import csv
import json
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Sequence

import joblib
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix, f1_score
from sklearn.model_selection import train_test_split
from sklearn.naive_bayes import MultinomialNB
from sklearn.pipeline import Pipeline
from sklearn.svm import LinearSVC


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATA_DIR = PROJECT_ROOT / "docs" / "ml" / "data" / "supervised"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "docs" / "ml" / "models" / "supervised"
RANDOM_STATE = 42


@dataclass(frozen=True)
class TaskConfig:
    name: str
    source_file: str
    text_columns: Sequence[str]
    label_column: str
    description: str


TASKS: Sequence[TaskConfig] = (
    TaskConfig(
        name="document_type_classifier",
        source_file="document_type_examples.csv",
        text_columns=("text",),
        label_column="label",
        description="Predict legal document type from document text.",
    ),
    TaskConfig(
        name="claim_evidence_verifier",
        source_file="claim_evidence_examples.csv",
        text_columns=("claim", "evidence"),
        label_column="label",
        description="Classify whether an evidence snippet supports, contradicts, or is insufficient for a claim.",
    ),
    TaskConfig(
        name="case_risk_triage",
        source_file="case_risk_examples.csv",
        text_columns=("case_summary",),
        label_column="label",
        description="Predict low, medium, or high legal case risk from case facts.",
    ),
)


def build_models() -> Dict[str, Pipeline]:
    return {
        "multinomial_nb": Pipeline(
            steps=[
                ("tfidf", TfidfVectorizer(ngram_range=(1, 2), min_df=1, max_features=5000)),
                ("model", MultinomialNB()),
            ]
        ),
        "logistic_regression": Pipeline(
            steps=[
                ("tfidf", TfidfVectorizer(ngram_range=(1, 2), min_df=1, max_features=5000)),
                (
                    "model",
                    LogisticRegression(
                        max_iter=1000,
                        class_weight="balanced",
                        random_state=RANDOM_STATE,
                    ),
                ),
            ]
        ),
        "linear_svm": Pipeline(
            steps=[
                ("tfidf", TfidfVectorizer(ngram_range=(1, 2), min_df=1, max_features=5000)),
                ("model", LinearSVC(class_weight="balanced", random_state=RANDOM_STATE)),
            ]
        ),
        "char_linear_svm": Pipeline(
            steps=[
                (
                    "tfidf",
                    TfidfVectorizer(
                        analyzer="char_wb",
                        ngram_range=(3, 5),
                        min_df=1,
                        max_features=8000,
                    ),
                ),
                ("model", LinearSVC(class_weight="balanced", random_state=RANDOM_STATE)),
            ]
        ),
    }


def load_rows(path: Path) -> List[dict]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def join_text(row: dict, columns: Sequence[str]) -> str:
    parts = []
    for column in columns:
        value = (row.get(column) or "").strip()
        if value:
            parts.append(f"{column}: {value}")
    return "\n".join(parts)


def task_text(row: dict, task: TaskConfig) -> str:
    text = join_text(row, task.text_columns)
    if task.name == "claim_evidence_verifier":
        text = f"{text}\nfeatures: {' '.join(claim_evidence_feature_tokens(row))}"
    if task.name == "case_risk_triage":
        text = f"{text}\nfeatures: {' '.join(case_risk_feature_tokens(row))}"
    return text


def claim_evidence_feature_tokens(row: dict) -> List[str]:
    claim = (row.get("claim") or "").lower()
    evidence = (row.get("evidence") or "").lower()
    claim_tokens = content_tokens(claim)
    evidence_tokens = content_tokens(evidence)
    overlap = len(claim_tokens & evidence_tokens) / max(len(claim_tokens), 1)

    features = []
    if overlap >= 0.45:
        features.append("lexical_overlap_high")
    elif overlap >= 0.2:
        features.append("lexical_overlap_medium")
    else:
        features.append("lexical_overlap_low")

    gap_cues = [
        "does not mention",
        "does not discuss",
        "no matching",
        "no witness",
        "no metadata",
        "no applicable",
        "no delivery",
        "contains no",
        "gives no",
        "but no",
        "but contains no",
    ]
    contradiction_cues = [
        "denies",
        "outstanding balance",
        "requires cure within",
        "asks for damages",
        "admitted the evidence",
        "applies during",
        "signed by both",
        "signature blocks completed",
        "conflicting",
        "not fully paid",
    ]

    if any(cue in evidence for cue in gap_cues):
        features.append("evidence_gap_cue")
    if any(cue in evidence for cue in contradiction_cues):
        features.append("evidence_contradiction_cue")
    if any(cue in claim for cue in ["no ", "not ", "fully paid", "withdraw", "only after"]):
        features.append("claim_absence_or_exclusivity_cue")
    if any(cue in evidence for cue in ["states", "says", "lists", "allows", "orders"]):
        features.append("direct_statement_cue")
    return features


def content_tokens(text: str) -> set:
    stopwords = {
        "a",
        "an",
        "and",
        "are",
        "as",
        "by",
        "for",
        "from",
        "in",
        "is",
        "it",
        "of",
        "on",
        "or",
        "that",
        "the",
        "this",
        "to",
        "with",
    }
    return {token for token in re.findall(r"[a-z0-9]+", text) if token not in stopwords and len(token) > 2}


def case_risk_feature_tokens(row: dict) -> List[str]:
    summary = (row.get("case_summary") or "").lower()
    features = []

    low_cues = [
        "routine",
        "complete",
        "no dispute",
        "no active conflict",
        "minor",
        "agreed",
        "favorable",
        "no violation",
        "ordinary",
    ]
    medium_cues = [
        "partial",
        "partially",
        "ambiguous",
        "next week",
        "communicating",
        "moderate",
        "incomplete",
        "active",
        "can still be met",
    ]
    high_cues = [
        "expired",
        "passed",
        "urgent",
        "missing",
        "fraud",
        "eviction",
        "major damages",
        "contradict",
        "threatens",
        "tomorrow",
        "this week",
        "collapsed",
    ]

    if any(cue in summary for cue in low_cues):
        features.append("low_risk_cue")
    if any(cue in summary for cue in medium_cues):
        features.append("medium_risk_cue")
    if any(cue in summary for cue in high_cues):
        features.append("high_risk_cue")
    if any(cue in summary for cue in ["deadline", "hearing", "limitation period", "court filing"]):
        features.append("procedure_pressure_cue")
    if any(cue in summary for cue in ["missing", "incomplete", "contradictory", "contradict"]):
        features.append("evidence_quality_cue")
    return features


def validate_dataset(task: TaskConfig, rows: Sequence[dict]) -> None:
    if not rows:
        raise ValueError(f"{task.name}: dataset is empty")

    missing_columns = [
        column
        for column in [*task.text_columns, task.label_column]
        if column not in rows[0]
    ]
    if missing_columns:
        raise ValueError(f"{task.name}: missing columns {missing_columns}")

    labels = [(row.get(task.label_column) or "").strip() for row in rows]
    empty_labels = [index for index, label in enumerate(labels, start=2) if not label]
    if empty_labels:
        raise ValueError(f"{task.name}: empty labels on CSV rows {empty_labels[:5]}")

    label_counts = Counter(labels)
    too_small = {label: count for label, count in label_counts.items() if count < 2}
    if too_small:
        raise ValueError(f"{task.name}: each label needs at least 2 examples, got {too_small}")


def split_dataset(texts: Sequence[str], labels: Sequence[str]):
    label_counts = Counter(labels)
    class_count = len(label_counts)
    minimum_test_ratio = class_count / max(len(labels), 1)
    test_size = max(0.2, minimum_test_ratio)
    return train_test_split(
        list(texts),
        list(labels),
        test_size=test_size,
        random_state=RANDOM_STATE,
        stratify=list(labels),
    )


def train_task(task: TaskConfig, data_dir: Path, output_dir: Path) -> dict:
    dataset_path = data_dir / task.source_file
    rows = load_rows(dataset_path)
    validate_dataset(task, rows)

    texts = [task_text(row, task) for row in rows]
    labels = [(row[task.label_column] or "").strip() for row in rows]
    x_train, x_test, y_train, y_test = split_dataset(texts, labels)

    task_output_dir = output_dir / task.name
    task_output_dir.mkdir(parents=True, exist_ok=True)

    model_results = {}
    trained_models = {}
    sorted_labels = sorted(set(labels))

    for model_name, pipeline in build_models().items():
        pipeline.fit(x_train, y_train)
        predictions = pipeline.predict(x_test)
        model_results[model_name] = {
            "accuracy": round(accuracy_score(y_test, predictions), 4),
            "macro_f1": round(f1_score(y_test, predictions, average="macro"), 4),
            "weighted_f1": round(f1_score(y_test, predictions, average="weighted"), 4),
            "classification_report": classification_report(
                y_test,
                predictions,
                labels=sorted_labels,
                output_dict=True,
                zero_division=0,
            ),
            "confusion_matrix": {
                "labels": sorted_labels,
                "matrix": confusion_matrix(y_test, predictions, labels=sorted_labels).tolist(),
            },
        }
        trained_models[model_name] = pipeline

    best_model_name = max(
        model_results,
        key=lambda name: (model_results[name]["macro_f1"], model_results[name]["accuracy"]),
    )
    best_model = trained_models[best_model_name]
    best_predictions = best_model.predict(x_test)

    joblib.dump(best_model, task_output_dir / "model.joblib")
    write_predictions(task_output_dir / "predictions.csv", x_test, y_test, best_predictions)

    metrics = {
        "task": task.name,
        "description": task.description,
        "dataset": str(dataset_path.relative_to(PROJECT_ROOT)),
        "rows": len(rows),
        "train_rows": len(x_train),
        "test_rows": len(x_test),
        "label_distribution": dict(sorted(Counter(labels).items())),
        "candidate_models": model_results,
        "best_model": best_model_name,
        "best_metrics": {
            "accuracy": model_results[best_model_name]["accuracy"],
            "macro_f1": model_results[best_model_name]["macro_f1"],
            "weighted_f1": model_results[best_model_name]["weighted_f1"],
        },
    }
    (task_output_dir / "metrics.json").write_text(
        json.dumps(metrics, indent=2),
        encoding="utf-8",
    )
    (task_output_dir / "README.md").write_text(render_task_readme(metrics), encoding="utf-8")
    return metrics


def write_predictions(path: Path, texts: Iterable[str], labels: Iterable[str], predictions: Iterable[str]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["text", "label", "prediction", "correct"])
        writer.writeheader()
        for text, label, prediction in zip(texts, labels, predictions):
            writer.writerow(
                {
                    "text": text.replace("\r\n", "\n"),
                    "label": label,
                    "prediction": prediction,
                    "correct": str(label == prediction).lower(),
                }
            )


def render_task_readme(metrics: dict) -> str:
    rows = [
        "# Supervised Model Artifact",
        "",
        f"Task: `{metrics['task']}`",
        "",
        metrics["description"],
        "",
        "## Best Model",
        "",
        f"- Algorithm: `{metrics['best_model']}`",
        f"- Accuracy: `{metrics['best_metrics']['accuracy']}`",
        f"- Macro F1: `{metrics['best_metrics']['macro_f1']}`",
        f"- Weighted F1: `{metrics['best_metrics']['weighted_f1']}`",
        "",
        "## Files",
        "",
        "- `model.joblib`: trained scikit-learn pipeline.",
        "- `metrics.json`: full train/test metrics for every candidate algorithm.",
        "- `predictions.csv`: held-out predictions for error analysis.",
        "",
        "Re-run from the repository root:",
        "",
        "```bash",
        ".\\.venv\\Scripts\\python.exe scripts\\train_supervised_legal_models.py",
        "```",
        "",
    ]
    return "\n".join(rows)


def render_summary(metrics_by_task: Sequence[dict]) -> str:
    lines = [
        "# Supervised Legal Models Summary",
        "",
        "These artifacts are trained from local labeled CSV files with classical ML models.",
        "",
        "| Task | Best algorithm | Accuracy | Macro F1 | Rows |",
        "|---|---:|---:|---:|---:|",
    ]
    for metrics in metrics_by_task:
        lines.append(
            "| {task} | {model} | {accuracy} | {macro_f1} | {rows} |".format(
                task=metrics["task"],
                model=metrics["best_model"],
                accuracy=metrics["best_metrics"]["accuracy"],
                macro_f1=metrics["best_metrics"]["macro_f1"],
                rows=metrics["rows"],
            )
        )
    lines.extend(
        [
            "",
            "Artifacts are intentionally small so they can be retrained quickly during demos or class discussion.",
            "",
        ]
    )
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Train local supervised legal ML models.")
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    metrics_by_task = [train_task(task, args.data_dir, args.output_dir) for task in TASKS]
    (args.output_dir / "README.md").write_text(render_summary(metrics_by_task), encoding="utf-8")

    for metrics in metrics_by_task:
        best = metrics["best_metrics"]
        print(
            f"{metrics['task']}: {metrics['best_model']} "
            f"accuracy={best['accuracy']} macro_f1={best['macro_f1']}"
        )


if __name__ == "__main__":
    main()
