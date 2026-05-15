"""Smoke test for the legal-search pipeline.

Exercises classifier -> local retrieval -> NLI faithfulness on a handful of
real questions and prints pass/fail. Run after any change to retrieval,
the corpus, or the NLI service.

Usage:
    python scripts/smoke_test_legal_search.py
"""

from __future__ import annotations

import os
import sys
import io
import time
from pathlib import Path
from typing import Any, Dict, List

# Ensure the project root is on sys.path so ``backend.*`` resolves.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# Force UTF-8 stdout so French/Arabic don't crash the Windows console.
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

os.environ.setdefault("SECRET_KEY", "test")
os.environ.setdefault("JWT_SECRET", "test")
os.environ.setdefault("OPENAI_API_KEY", "test")


def fmt(ok: bool) -> str:
    return "PASS" if ok else "FAIL"


def run() -> int:
    from backend.services.ai.legal_search_mode_service import LegalSearchModeService
    from backend.services.ai.nli_faithfulness_service import nli_faithfulness_service

    # Force a fresh corpus load.
    LegalSearchModeService._local_legal_codes_corpus_cache = None
    svc = LegalSearchModeService()

    failures: List[str] = []

    # ── 1. Corpus integrity ──────────────────────────────────────────────────
    corpus = LegalSearchModeService._load_local_legal_codes_corpus()
    tunisia = corpus.get("tunisia", [])
    families = {e.get("code_family") for e in tunisia}
    counts = {f: sum(1 for e in tunisia if e.get("code_family") == f) for f in families}
    print(f"\n[1/4] Corpus: {len(tunisia)} Tunisia entries -> {counts}")
    if counts.get("code_personnel_status", 0) < 200:
        failures.append("code_personnel_status has fewer than 200 entries")
    if counts.get("code_civil", 0) < 300:
        failures.append("code_civil has fewer than 300 entries")
    # Spot-check Article 18 is in the CSP and mentions polygamie
    art18 = next(
        (e for e in tunisia
         if e.get("article") == "Article 18"
         and e.get("code_family") == "code_personnel_status"),
        None,
    )
    if not art18:
        failures.append("CSP Article 18 not found")
    elif "polygamie" not in (art18.get("summary") or "").lower():
        failures.append("CSP Article 18 missing 'polygamie' in summary")
    else:
        print("       Article 18 present, mentions polygamie. OK.")

    # ── 2. Domain classifier routes queries correctly ────────────────────────
    print("\n[2/4] Domain classifier routing:")
    classifier_cases = [
        ("La polygamie est-elle autorisée en droit tunisien ?", "code_personnel_status"),
        ("Conditions de validité du mariage en droit tunisien", "code_personnel_status"),
        ("Quelle est la part successorale de l'épouse survivante ?", "code_personnel_status"),
        ("Quel est le délai de prescription en matière contractuelle ?", "code_civil"),
        ("Reconnaissance d'un jugement étranger en Tunisie", "code_international_prive"),
    ]
    for query, expected in classifier_cases:
        topic = svc.domain_classifier.classify(
            query=query, case_focus_terms=[], internal_results=[],
            code_scope=svc.DEFAULT_CODE_SCOPE, country="tunisia", case=None,
        )
        actual = (topic.get("code_families") or ["?"])[0]
        ok = actual == expected
        print(f"   {fmt(ok)} expected={expected:25s} got={actual:25s}  | {query[:55]}")
        if not ok:
            failures.append(f"classifier: {query[:40]!r} -> {actual} (expected {expected})")

    # ── 3. Retrieval surfaces the right article ──────────────────────────────
    print("\n[3/4] Retrieval surfaces the expected article:")
    retrieval_cases = [
        # (query, expected_article, expected_family)
        ("La polygamie est-elle autorisée en droit tunisien ?", "Article 18", "code_personnel_status"),
        ("Conditions de validité du mariage en droit tunisien", "Article 3", "code_personnel_status"),
    ]
    for query, expected_article, expected_family in retrieval_cases:
        topic = svc.domain_classifier.classify(
            query=query, case_focus_terms=[], internal_results=[],
            code_scope=svc.DEFAULT_CODE_SCOPE, country="tunisia", case=None,
        )
        results = svc._retrieve_local_legal_code_sources(
            country="tunisia", query=query, case_focus_terms=[],
            top_k=6, preferred_code_families=topic.get("code_families"),
        )
        top6_refs = [(r.get("code_family"), r.get("reference")) for r in results[:6]]
        in_top6 = any(
            ref == expected_article and fam == expected_family
            for fam, ref in top6_refs
        )
        strong_hits = sum(1 for r in results if float(r.get("score", 0)) >= 41.0)
        short_circuit = strong_hits >= 3
        ok = in_top6 and short_circuit
        marker = fmt(ok)
        print(f"   {marker} top6 contains {expected_family}/{expected_article}: {in_top6}, "
              f"short-circuit (>=3 strong hits): {short_circuit} ({strong_hits} hits)")
        print(f"        top6: {top6_refs}")
        if not ok:
            failures.append(f"retrieval: {query[:40]!r} -> missing {expected_article} or no short-circuit")

    # ── 4. NLI is available and produces real scores ─────────────────────────
    print("\n[4/4] NLI faithfulness service:")
    available = nli_faithfulness_service.is_available()
    print(f"   service available: {available}")
    if not available:
        failures.append("NLI service is not available")
    else:
        t0 = time.time()
        sources = [
            {"snippet": "Article 18. La polygamie est interdite. Quiconque, étant engagé dans les liens du mariage, en aura contracté un autre avant la dissolution du précédent, sera passible d'un emprisonnement d'un an."}
        ]
        answer = "En droit tunisien, la polygamie est interdite. L'article 18 du Code du Statut Personnel sanctionne cette interdiction par une peine d'emprisonnement."
        report = nli_faithfulness_service.score(answer=answer, sources=sources)
        elapsed = time.time() - t0
        score = float(report.score)
        print(f"   scored {len(report.claims)} claim(s) in {elapsed:.1f}s -> score={score:.2f} label={report.label}")
        if score < 0.40:
            failures.append(f"NLI score is suspiciously low ({score:.2f}) — model may be misconfigured")
        if report.skipped_reason:
            failures.append(f"NLI returned skipped_reason={report.skipped_reason}")

    # ── Summary ──────────────────────────────────────────────────────────────
    print("\n" + "=" * 70)
    if failures:
        print(f"FAILED — {len(failures)} issue(s):")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("ALL CHECKS PASSED ✔")
    return 0


if __name__ == "__main__":
    sys.exit(run())
