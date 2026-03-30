from __future__ import annotations

import argparse
import subprocess
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path


ZERO_SHA = "0" * 40


def run_git(args: list[str]) -> str:
    result = subprocess.run(
        ["git", *args],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {result.stderr.strip()}")
    return result.stdout.strip()


def is_valid_commit(sha: str) -> bool:
    if not sha or sha == ZERO_SHA:
        return False
    result = subprocess.run(
        ["git", "cat-file", "-e", f"{sha}^{{commit}}"],
        check=False,
        capture_output=True,
        text=True,
    )
    return result.returncode == 0


def collect_commits(before: str, after: str, fallback_count: int = 20) -> list[dict[str, str]]:
    log_rows: list[dict[str, str]] = []

    if is_valid_commit(before) and is_valid_commit(after):
        output = run_git(
            [
                "log",
                "--reverse",
                "--pretty=format:%H%x09%s%x09%an%x09%ad",
                "--date=iso",
                f"{before}..{after}",
            ]
        )
        if output.strip():
            for line in output.splitlines():
                parts = line.split("\t", 3)
                if len(parts) == 4:
                    log_rows.append(
                        {
                            "sha": parts[0],
                            "subject": parts[1],
                            "author": parts[2],
                            "date": parts[3],
                        }
                    )
            return log_rows

    target = after if is_valid_commit(after) else "HEAD"
    fallback = run_git(
        [
            "log",
            "--reverse",
            f"--max-count={fallback_count}",
            "--pretty=format:%H%x09%s%x09%an%x09%ad",
            "--date=iso",
            target,
        ]
    )
    for line in fallback.splitlines():
        parts = line.split("\t", 3)
        if len(parts) == 4:
            log_rows.append(
                {
                    "sha": parts[0],
                    "subject": parts[1],
                    "author": parts[2],
                    "date": parts[3],
                }
            )
    return log_rows


def collect_files_for_commit(sha: str) -> list[str]:
    output = run_git(["diff-tree", "--root", "--no-commit-id", "--name-only", "-r", sha])
    files: list[str] = []
    for line in output.splitlines():
        value = line.strip()
        if value:
            files.append(value.replace("\\", "/"))
    return files


def write_advancement_file(
    *,
    output_dir: Path,
    branch: str,
    before: str,
    after: str,
    commits: list[dict[str, str]],
) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H-%M-%S")
    after_short = (after[:7] if after and after != ZERO_SHA else "head")
    output_path = output_dir / f"{timestamp}_push_{after_short}.md"

    all_files: list[str] = []
    for commit in commits:
        all_files.extend(collect_files_for_commit(commit["sha"]))

    unique_files = sorted(set(all_files))
    area_counter: Counter[str] = Counter()
    for path in unique_files:
        area = path.split("/", 1)[0] if "/" in path else "(root)"
        area_counter[area] += 1

    lines: list[str] = [
        f"# Advancement Log - {timestamp} UTC",
        "",
        "## Push Context",
        f"- Branch: `{branch}`",
        f"- Before: `{before or 'unknown'}`",
        f"- After: `{after or 'HEAD'}`",
        f"- Commits captured: `{len(commits)}`",
        f"- Unique files touched: `{len(unique_files)}`",
        "",
        "## What We Did In This Push",
    ]

    if commits:
        for commit in commits:
            lines.append(f"- `{commit['sha'][:7]}` {commit['subject']} ({commit['author']})")
    else:
        lines.append("- No commits were found for the provided push range.")

    lines.extend(
        [
            "",
            "## Changed Areas",
        ]
    )
    if area_counter:
        for area, count in area_counter.most_common():
            lines.append(f"- `{area}`: {count} file(s)")
    else:
        lines.append("- No changed files detected.")

    lines.extend(
        [
            "",
            "## Files Changed",
        ]
    )
    if unique_files:
        for path in unique_files[:200]:
            lines.append(f"- `{path}`")
        if len(unique_files) > 200:
            lines.append(f"- ... plus {len(unique_files) - 200} more file(s)")
    else:
        lines.append("- No files detected.")

    output_path.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")
    return output_path


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate an advancement markdown log for a git push range.")
    parser.add_argument("--before", default="", help="Commit SHA before push")
    parser.add_argument("--after", default="HEAD", help="Commit SHA after push")
    parser.add_argument("--branch", default="unknown", help="Branch name")
    parser.add_argument("--output-dir", default="advancement", help="Output directory for logs")
    args = parser.parse_args()

    try:
        commits = collect_commits(before=args.before.strip(), after=args.after.strip())
        output_path = write_advancement_file(
            output_dir=Path(args.output_dir),
            branch=args.branch.strip() or "unknown",
            before=args.before.strip(),
            after=args.after.strip(),
            commits=commits,
        )
        print(f"Generated advancement log: {output_path}")
        return 0
    except Exception as exc:
        print(f"Failed to generate advancement log: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
