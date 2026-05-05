#!/usr/bin/env python3
"""
Freeze (or re-freeze) AI prompt files into PROMPT_LOCK.json.

Usage:
    python scripts/freeze_prompts.py

Run this after any intentional change to a prompt .md file. The script:
  1. Computes SHA-256 for each listed prompt file
  2. Bumps the patch version (unless --major or --minor is passed)
  3. Writes updated PROMPT_LOCK.json

Flags:
  --major   bump major version (x.0.0)
  --minor   bump minor version (a.x.0)
  --patch   bump patch version (default)
  --dry-run  print what would change without writing
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
LOCK_FILE = REPO_ROOT / "backend" / "services" / "ai" / "agents" / "PROMPT_LOCK.json"
AGENTS_DIR = REPO_ROOT / "backend" / "services" / "ai" / "agents"

TRACKED_PROMPTS = [
    "chronology_prompt.md",
    "summarization_prompt.md",
]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def bump_version(current: str, kind: str) -> str:
    parts = current.split(".")
    if len(parts) != 3:
        return "1.0.0"
    major, minor, patch = int(parts[0]), int(parts[1]), int(parts[2])
    if kind == "major":
        return f"{major + 1}.0.0"
    if kind == "minor":
        return f"{major}.{minor + 1}.0"
    return f"{major}.{minor}.{patch + 1}"


def main() -> None:
    parser = argparse.ArgumentParser(description="Freeze prompt files into PROMPT_LOCK.json")
    bump_group = parser.add_mutually_exclusive_group()
    bump_group.add_argument("--major", action="store_true")
    bump_group.add_argument("--minor", action="store_true")
    bump_group.add_argument("--patch", action="store_true", default=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    bump_kind = "major" if args.major else ("minor" if args.minor else "patch")

    existing: dict = {}
    if LOCK_FILE.exists():
        existing = json.loads(LOCK_FILE.read_text(encoding="utf-8"))

    now_iso = datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    today = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")

    prompts_out: dict = {}
    changed = False

    for filename in TRACKED_PROMPTS:
        path = AGENTS_DIR / filename
        if not path.exists():
            print(f"  MISSING  {filename}")
            continue

        new_hash = sha256(path)
        old_meta = (existing.get("prompts") or {}).get(filename, {})
        old_hash = (old_meta.get("sha256") or "").upper()
        old_version = old_meta.get("version", "0.0.0")
        new_version = bump_version(old_version, bump_kind) if new_hash != old_hash else old_version

        if new_hash != old_hash:
            changed = True
            status = f"CHANGED  {old_hash[:12]}... → {new_hash[:12]}... v{old_version} → v{new_version}"
        else:
            status = f"UNCHANGED {new_hash[:12]}... v{new_version}"

        print(f"  {status}  {filename}")

        prompts_out[filename] = {
            "version": new_version,
            "sha256": new_hash,
            "frozen_at": today,
            "description": old_meta.get("description", ""),
            "status": "frozen",
        }

    if not changed:
        print("\nNo prompt files changed — lock file not updated.")
        return

    lock_out = {
        "schema_version": "1",
        "frozen_at": now_iso,
        "sprint": existing.get("sprint", "week1"),
        "frozen_by": "freeze_prompts.py",
        "prompts": prompts_out,
        "policy": existing.get("policy", {
            "change_requires": "new version bump + re-lock",
            "eval_gate": "must pass \u2265 80% of default_eval_suite before lock bump",
            "review_required_by": "sprint_owner",
        }),
    }

    if args.dry_run:
        print("\nDry run \u2014 would write:")
        print(json.dumps(lock_out, indent=4))
    else:
        LOCK_FILE.write_text(json.dumps(lock_out, indent=4) + "\n", encoding="utf-8")
        print(f"\nWrote {LOCK_FILE.relative_to(REPO_ROOT)}")


if __name__ == "__main__":
    main()
