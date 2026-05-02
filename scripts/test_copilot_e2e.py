"""
End-to-end test script for the Copilot API.

Usage:
    python scripts/test_copilot_e2e.py

Configuration (override via environment variables or edit the block below):
    E2E_BASE_URL   — FastAPI base URL  (default: http://127.0.0.1:8000)
    E2E_EMAIL      — login email
    E2E_PASSWORD   — login password
    E2E_TOKEN      — paste a Bearer token directly to skip login
    E2E_CASE_ID    — case ID to use for agent/legal-search tests (default: 29)

All tests hit the real running backend.  No mocking.
"""

from __future__ import annotations

import os
import sys
import time
from typing import Any, Dict, Optional

import requests

# ─── Configuration ────────────────────────────────────────────────────────────

BASE_URL: str = os.environ.get("E2E_BASE_URL", "http://127.0.0.1:8000").rstrip("/")
EMAIL: str    = os.environ.get("E2E_EMAIL", "ahmed@example.com")
PASSWORD: str = os.environ.get("E2E_PASSWORD", "12345678")
TOKEN: str    = os.environ.get("E2E_TOKEN", "")        # skip login if set
CASE_ID: int  = int(os.environ.get("E2E_CASE_ID", "29"))

COPILOT_URL = f"{BASE_URL}/ai/copilot"
LOGIN_URL   = f"{BASE_URL}/auth/login"

# ─── ANSI colours ─────────────────────────────────────────────────────────────

GREEN  = "\033[92m"
RED    = "\033[91m"
YELLOW = "\033[93m"
CYAN   = "\033[96m"
RESET  = "\033[0m"
BOLD   = "\033[1m"

def _green(s: str) -> str:  return f"{GREEN}{s}{RESET}"
def _red(s: str) -> str:    return f"{RED}{s}{RESET}"
def _cyan(s: str) -> str:   return f"{CYAN}{s}{RESET}"
def _bold(s: str) -> str:   return f"{BOLD}{s}{RESET}"


# ─── Pre-test memory flush ─────────────────────────────────────────────────────

def _flush_test_memory() -> None:
    """Delete the test user's CaseMemoryEntry rows so accumulated conversation
    history from previous test runs does not contaminate the current suite.
    Only runs if the backend package is importable (same Python env as server).
    """
    try:
        import sys as _sys
        # Add workspace root to path if needed
        _ws = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        if _ws not in _sys.path:
            _sys.path.insert(0, _ws)
        from backend.database.database import SessionLocal  # type: ignore
        from backend.models.user import User  # type: ignore
        from backend.models.case_memory_entry import CaseMemoryEntry  # type: ignore
        db = SessionLocal()
        try:
            user = db.query(User).filter(User.email == EMAIL).first()
            if user:
                deleted = db.query(CaseMemoryEntry).filter(
                    CaseMemoryEntry.user_id == user.id
                ).delete(synchronize_session=False)
                db.commit()
                print(f"  [memory flush] Cleared {deleted} memory entries for {EMAIL}")
            else:
                print(f"  [memory flush] User {EMAIL!r} not found — skipping flush")
        finally:
            db.close()
    except Exception as exc:
        # Non-fatal — continue with tests even if flush fails
        print(f"  [memory flush] Skipped ({type(exc).__name__}: {exc})")



# ─── Auth ─────────────────────────────────────────────────────────────────────

def get_token() -> str:
    """Return a valid JWT token, either from env or by logging in."""
    if TOKEN:
        print(f"  {YELLOW}Using pre-set token from E2E_TOKEN env var.{RESET}")
        return TOKEN

    print(f"  Logging in as {EMAIL} …")
    try:
        r = requests.post(
            LOGIN_URL,
            json={"email": EMAIL, "password": PASSWORD},
            timeout=15,
        )
    except requests.ConnectionError:
        print(_red(f"\n  [FATAL] Cannot connect to {BASE_URL}. Is uvicorn running?\n"))
        sys.exit(1)

    if r.status_code != 200:
        print(_red(f"  [FATAL] Login failed — HTTP {r.status_code}: {r.text[:300]}"))
        sys.exit(1)

    token = r.json().get("access_token", "")
    if not token:
        print(_red("  [FATAL] Login response has no access_token."))
        sys.exit(1)

    print(f"  {_green('Login OK')}  (token length: {len(token)})")
    return token


# ─── Copilot caller ───────────────────────────────────────────────────────────

def call_copilot(
    token: str,
    message: str,
    mode: str = "default",
    agent_mode: bool = False,
    workspace_case_id: Optional[int] = None,
    reasoning_level: str = "medium",
) -> tuple[Optional[Dict[str, Any]], float, Optional[str]]:
    """
    Call POST /ai/copilot.

    Returns:
        (response_dict_or_None, elapsed_ms, error_string_or_None)
    """
    payload = {
        "message": message,
        "mode": mode,
        "agent_mode": agent_mode,
        "reasoning_level": reasoning_level,
        "top_k": 5,
        "use_external_research": False,  # keep tests deterministic
    }
    if workspace_case_id is not None:
        payload["workspace_case_id"] = workspace_case_id

    headers = {"Authorization": f"Bearer {token}"}

    t0 = time.perf_counter()
    try:
        r = requests.post(COPILOT_URL, json=payload, headers=headers, timeout=120)
        elapsed = (time.perf_counter() - t0) * 1000
    except requests.Timeout:
        return None, 0.0, "Request timed out after 120 s"
    except requests.ConnectionError as e:
        return None, 0.0, f"Connection error: {e}"

    if r.status_code != 200:
        return None, elapsed, f"HTTP {r.status_code}: {r.text[:400]}"

    try:
        data = r.json()
    except Exception as e:
        return None, elapsed, f"JSON decode error: {e}"

    return data, elapsed, None


# ─── Test runner ──────────────────────────────────────────────────────────────

_results: list[tuple[str, bool, str]] = []   # (name, passed, detail)


def _run(
    name: str,
    token: str,
    message: str,
    *,
    mode: str = "default",
    agent_mode: bool = False,
    workspace_case_id: Optional[int] = None,
    reasoning_level: str = "medium",
    extra_checks=None,  # callable(data) -> list[str]  (list of failure reasons)
) -> None:
    print(f"\n  {_bold(name)}")
    print(f"    message: \"{message[:80]}\"")

    data, elapsed_ms, err = call_copilot(
        token, message,
        mode=mode,
        agent_mode=agent_mode,
        workspace_case_id=workspace_case_id,
        reasoning_level=reasoning_level,
    )

    failures: list[str] = []

    if err:
        failures.append(err)
    else:
        # ── Universal assertions ──────────────────────────────────────────────
        if not isinstance(data, dict):
            failures.append("Response is not a JSON object")
        else:
            if "answer" not in data:
                failures.append("Missing field: answer")
            elif not str(data.get("answer", "")).strip():
                failures.append("Field 'answer' is empty")

            if "confidence" not in data:
                failures.append("Missing field: confidence")
            elif data["confidence"] not in {"high", "medium", "low"}:
                failures.append(f"Invalid confidence value: {data['confidence']!r}")

            # ── Extra test-specific assertions ────────────────────────────────
            if extra_checks and data:
                failures.extend(extra_checks(data))

    passed = len(failures) == 0
    _results.append((name, passed, "; ".join(failures) if failures else ""))

    if passed:
        answer_snippet = str(data.get("answer", ""))[:120].replace("\n", " ") if data else ""
        print(f"    {_green('[PASS]')}  ({elapsed_ms:.0f} ms)")
        if answer_snippet:
            print(f"    answer snippet: \"{_cyan(answer_snippet)}\"")
        # Print new quality fields if present
        if data:
            if data.get("grounding"):
                print(f"    grounding:      {data['grounding']}")
            if data.get("confidence_reason"):
                print(f"    conf. reason:   {data['confidence_reason'][:100]}")
            if data.get("ai_insight"):
                ai = data["ai_insight"]
                print(f"    grounding_type: {ai.get('grounding_type')}")
                print(f"    lawyer_note:    {str(ai.get('lawyer_note',''))[:100]}")
    else:
        print(f"    {_red('[FAIL]')}")
        for f in failures:
            print(f"      → {f}")


# ─── Individual test definitions ──────────────────────────────────────────────

def _check_agent(data: Dict[str, Any]) -> list[str]:
    issues = []
    answer = str(data.get("answer", ""))
    # Structured answer should not be a raw huge text blob
    if len(answer) > 3000 and "\n" not in answer:
        issues.append(
            f"Answer looks like a raw document dump "
            f"({len(answer)} chars, no line breaks)"
        )
    # grounding should exist
    grounding = (
        data.get("grounding")
        or (data.get("ai_insight") or {}).get("grounding_type")
    )
    if not grounding:
        issues.append("Missing grounding / grounding_type in response or ai_insight")
    elif grounding not in {
        "Case-grounded", "Partial", "Not grounded",
        "Fallback (context-based)", "General",
    }:
        issues.append(f"Unexpected grounding value: {grounding!r}")
    return issues


def _check_drafting(data: Dict[str, Any]) -> list[str]:
    issues = []
    answer = str(data.get("answer", ""))
    draft = data.get("draft_document") or {}
    structured = data.get("structured_result") or {}

    has_subject = (
        "subject" in structured
        or "subject" in draft
        or "Subject:" in answer
        or "SUBJECT:" in answer
    )
    has_body = len(answer) > 30  # any non-trivial text is a body

    if not has_subject:
        issues.append(
            "No subject field found in answer/draft_document/structured_result"
        )
    if not has_body:
        issues.append("Draft body is too short or empty")

    # open_editor flag
    if not data.get("open_editor"):
        issues.append("open_editor is False or missing for a drafting request")

    return issues


def _check_legal_search(data: Dict[str, Any]) -> list[str]:
    issues = []
    sources = data.get("sources") or []

    # If sources are present, check for pure-spam: article-only sources that
    # ALL have score == 0 and no snippet content — these were never filtered.
    # Sources with keyword overlap (already passed the assembly filter) are fine.
    if sources and isinstance(sources[0], dict):
        zero_score_articles = [
            s for s in sources
            if isinstance(s, dict)
            and bool(re.search(r"\bart(?:icle)?\.?\s*\d+", str(s.get("filename", "")), re.I))
            and float(s.get("score", 1.0)) == 0.0
            and not str(s.get("snippet", "")).strip()
        ]
        if len(zero_score_articles) == len(sources):
            issues.append(
                "All sources are zero-score article refs with no snippet — "
                "assembly service filter did not remove them"
            )

    # If no sources, a safety note should explain why
    if not sources:
        has_safety = bool(
            data.get("legal_sources_note")
            or (data.get("ai_insight") or {}).get("legal_sources_note")
            or (data.get("structured_result") or {}).get("legal_sources_note")
        )
        if not has_safety:
            issues.append(
                "No sources returned but no legal_sources_note safety message provided"
            )

    # lawyer note must exist
    lawyer_note = (
        data.get("ai_insight") or {}
    ).get("lawyer_note")
    if not lawyer_note:
        issues.append("Missing lawyer_note in ai_insight block")

    # If the answer itself signals insufficient grounding, grounding must NOT be Case-grounded
    answer = str(data.get("answer", "")).lower()
    _insufficient_phrases = (
        "not enough grounded evidence",
        "insufficient grounded evidence",
        "no reliable legal provisions",
        "could not be confidently identified",
        "not grounded in",
    )
    if any(phrase in answer for phrase in _insufficient_phrases):
        grounding = data.get("grounding") or (data.get("ai_insight") or {}).get("grounding_type") or ""
        if grounding in {"Case-grounded"}:
            issues.append(
                f"Answer signals insufficient grounding but grounding={grounding!r}; "
                "must be Partial or Not grounded"
            )
        gt = (data.get("ai_insight") or {}).get("grounding_type", "")
        if gt in {"Case-grounded"}:
            issues.append(
                f"Answer signals insufficient grounding but grounding_type={gt!r}; "
                "must not be Case-grounded"
            )

    return issues


# ─── Main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    import re  # used in _check_legal_search closure; import here for clarity

    print(_bold("\n══════════════════════════════════════════════"))
    print(_bold("  Copilot End-to-End Test Suite"))
    print(_bold(f"  Target: {BASE_URL}"))
    print(_bold(f"  Case ID under test: {CASE_ID}"))
    print(_bold("══════════════════════════════════════════════"))

    # ── Pre-test: flush accumulated conversation memory ───────────────────────
    print("\n[PRE-FLIGHT]")
    _flush_test_memory()

    # ── Authenticate ──────────────────────────────────────────────────────────
    print("\n[AUTH]")
    token = get_token()

    # ── Test 1: Chat Mode ──────────────────────────────────────────────────────
    _run(
        "Test 1 — Chat Mode",
        token,
        "hello",
        mode="default",
        agent_mode=False,
    )

    # ── Test 2: Agent Mode — ask_case ─────────────────────────────────────────
    _run(
        f"Test 2 — Agent Mode (ask_case, case #{CASE_ID})",
        token,
        f"what are the main facts in case #{CASE_ID}?",
        mode="default",
        agent_mode=True,
        workspace_case_id=CASE_ID,
        extra_checks=_check_agent,
    )

    # ── Test 3: Drafting ──────────────────────────────────────────────────────
    _run(
        f"Test 3 — Drafting (case #{CASE_ID})",
        token,
        f"draft an email to my client saying the meeting is postponed for case #{CASE_ID}",
        mode="default",
        agent_mode=False,
        workspace_case_id=CASE_ID,
        extra_checks=_check_drafting,
    )

    # ── Test 4: Legal Search Mode ─────────────────────────────────────────────
    _run(
        f"Test 4 — Legal Search Mode (case #{CASE_ID})",
        token,
        f"what are the legal risks in case #{CASE_ID}?",
        mode="legal_search",
        agent_mode=False,
        workspace_case_id=CASE_ID,
        extra_checks=_check_legal_search,
    )

    # ── Summary ───────────────────────────────────────────────────────────────
    total  = len(_results)
    passed = sum(1 for _, ok, _ in _results if ok)
    failed = total - passed

    print(_bold("\n══════════════════════════════════════════════"))
    print(_bold("  Results"))
    print(_bold("══════════════════════════════════════════════"))
    for name, ok, detail in _results:
        label = _green("[PASS]") if ok else _red("[FAIL]")
        line  = f"  {label}  {name}"
        if not ok:
            line += f"\n         → {detail}"
        print(line)

    print(_bold("──────────────────────────────────────────────"))
    colour = GREEN if failed == 0 else RED
    print(f"  {colour}{passed}/{total} tests passed{RESET}")
    print(_bold("══════════════════════════════════════════════\n"))

    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    import re  # noqa: F811 — also imported inside main for closure capture
    main()
