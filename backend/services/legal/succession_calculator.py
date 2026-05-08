"""Tunisian succession entitlement calculator.

Pure-Python deterministic rules engine over the Code de Statut Personnel
(CSP) inheritance articles 85–152. The calculator is intentionally
self-contained: no DB, no LLM, no I/O beyond the citation lookup that
fetches short article summaries from
``backend/services/legal/csp_article_lookup.py``.

Approach (Sunni / Maliki rules as codified in the CSP):

1. **Identify heirs** — spouse, descendants (sons/daughters), parents,
   siblings (full / paternal / uterine).
2. **Apply hajb (exclusion)** — a son blocks all siblings, the father
   blocks all siblings, etc.
3. **Apply fardh (Quranic shares)** — fixed fractions for spouse,
   parents, daughters-only, uterine siblings. The mother's share has
   special edge cases (1/6 vs 1/3 vs 1/3-of-residue).
4. **Apply asaba (residuary)** — sons and daughters together absorb the
   residue with the 2:1 ratio. Father becomes asaba in the absence of
   male descendants. Full / paternal brothers can be asaba.
5. **Apply ʿawl** — when fardh sum > 1, scale all shares proportionally.
6. **Apply radd** — when fardh sum < 1 and no asaba, the residue is
   returned proportionally to fardh heirs (excluding the spouse).

All arithmetic uses ``fractions.Fraction`` so 1/3 + 1/6 + 1/2 == 1
exactly. The computation is deterministic; the same input always
produces the same output.

Run ``python -m backend.services.legal.succession_calculator`` to
execute the bundled self-tests. A non-zero exit code means a regression
— wire this into CI so the calculator can never silently regress.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from fractions import Fraction
from typing import Literal

from backend.services.legal.csp_article_lookup import CitationRef, lookup_many


SpouseKind = Literal["husband", "wife", "none"]


@dataclass(frozen=True)
class SuccessionInput:
    spouse_kind: SpouseKind
    sons: int = 0
    daughters: int = 0
    father_alive: bool = False
    mother_alive: bool = False
    full_brothers: int = 0
    full_sisters: int = 0
    paternal_brothers: int = 0
    paternal_sisters: int = 0
    maternal_siblings: int = 0
    estate_value_tnd: float | None = None


@dataclass
class HeirShare:
    heir: str
    share_fraction: Fraction
    share_percent: float
    share_amount_tnd: float | None
    article_refs: list[str]
    reasoning: str


@dataclass
class SuccessionResult:
    heirs: list[HeirShare]
    total_distributed: Fraction
    radd_applied: bool
    awl_applied: bool
    notes: list[str] = field(default_factory=list)
    citations: list[CitationRef] = field(default_factory=list)


# ──────────────────────────────────────────────────────────────────────────
# Internal — share book-keeping
# ──────────────────────────────────────────────────────────────────────────


@dataclass
class _Slot:
    """One pre-finalisation share (split into N heirs equally) before %, $."""
    heir_template: str         # e.g. "son" — split into "son_1", "son_2", ...
    count: int                 # how many heirs share this slot equally
    share_fraction: Fraction   # total fraction the slot owns
    article_refs: list[str]
    reasoning: str
    is_fardh: bool             # True if Quranic share, False if asaba/radd
    excluded_from_radd: bool = False  # spouse is fardh but excluded from radd


def _compute(inp: SuccessionInput) -> tuple[list[_Slot], list[str], bool, bool]:
    """Return (slots, notes, awl_applied, radd_applied)."""
    notes: list[str] = []
    has_male_descendant = inp.sons > 0
    has_descendant = has_male_descendant or inp.daughters > 0
    # Hajb: a son blocks all siblings; the father also blocks siblings.
    siblings_blocked = has_male_descendant or inp.father_alive

    fardh_slots: list[_Slot] = []
    asaba_slots: list[_Slot] = []

    # ── Spouse (Arts 88–90) ─────────────────────────────────────────────
    if inp.spouse_kind == "husband":
        share = Fraction(1, 4) if has_descendant else Fraction(1, 2)
        fardh_slots.append(_Slot(
            "husband", 1, share, ["Art. 88", "Art. 89"],
            f"Husband: {share} ({'with' if has_descendant else 'without'} descendant heir).",
            is_fardh=True, excluded_from_radd=True,
        ))
    elif inp.spouse_kind == "wife":
        share = Fraction(1, 8) if has_descendant else Fraction(1, 4)
        fardh_slots.append(_Slot(
            "wife", 1, share, ["Art. 88", "Art. 90"],
            f"Wife: {share} ({'with' if has_descendant else 'without'} descendant heir).",
            is_fardh=True, excluded_from_radd=True,
        ))

    # ── Parents (Arts 91–92) ────────────────────────────────────────────
    # Mother's share has classical edge cases:
    #   - with descendant heir OR ≥2 siblings: 1/6
    #   - else: 1/3
    # The "ʿumariyyatān" (1/3 of residue) edge case applies when only the
    # spouse + both parents are alive: she takes 1/3 of what remains
    # after the spouse's fardh. We model this explicitly.
    siblings_total = (
        inp.full_brothers + inp.full_sisters
        + inp.paternal_brothers + inp.paternal_sisters
        + inp.maternal_siblings
    )
    is_umariyya = (
        not has_descendant
        and inp.father_alive
        and inp.mother_alive
        and inp.spouse_kind in ("husband", "wife")
        and siblings_total == 0
        and inp.sons == 0 and inp.daughters == 0
    )
    if inp.mother_alive:
        if is_umariyya:
            spouse_share = (
                Fraction(1, 2) if inp.spouse_kind == "husband" else Fraction(1, 4)
            )
            mother_share = (Fraction(1) - spouse_share) * Fraction(1, 3)
            fardh_slots.append(_Slot(
                "mother", 1, mother_share,
                ["Art. 92"],
                f"Mother: 1/3 of residue (ʿumariyyatān edge case) = {mother_share}.",
                is_fardh=True,
            ))
            notes.append("ʿumariyyatān: mother takes 1/3 of the residue after the spouse's share.")
        elif has_descendant or siblings_total >= 2:
            fardh_slots.append(_Slot(
                "mother", 1, Fraction(1, 6),
                ["Art. 92"],
                "Mother: 1/6 (descendant heir or ≥2 siblings present).",
                is_fardh=True,
            ))
        else:
            fardh_slots.append(_Slot(
                "mother", 1, Fraction(1, 3),
                ["Art. 92"],
                "Mother: 1/3 (no descendant heir and <2 siblings).",
                is_fardh=True,
            ))

    if inp.father_alive:
        if has_male_descendant:
            # 1/6 fardh, no asaba role.
            fardh_slots.append(_Slot(
                "father", 1, Fraction(1, 6),
                ["Art. 91"],
                "Father: 1/6 fardh (male descendant present).",
                is_fardh=True,
            ))
        elif has_descendant:
            # daughters only → father gets 1/6 + asaba on residue.
            fardh_slots.append(_Slot(
                "father", 1, Fraction(1, 6),
                ["Art. 91"],
                "Father: 1/6 fardh + agnatic residue (daughters but no son).",
                is_fardh=True,
            ))
            # Father also takes any agnatic residue. We mark a placeholder
            # asaba slot keyed to "father" with priority 0 — resolution
            # happens after fardh sum is known.
            asaba_slots.append(_Slot(
                "father", 1, Fraction(0), ["Art. 91", "Art. 110"],
                "Father takes the agnatic residue.",
                is_fardh=False,
            ))
        else:
            # No descendant: father is pure asaba.
            asaba_slots.append(_Slot(
                "father", 1, Fraction(0), ["Art. 91", "Art. 110"],
                "Father is asaba (no descendant).",
                is_fardh=False,
            ))

    # ── Daughters / sons (Arts 99–100) ──────────────────────────────────
    if inp.sons > 0:
        # Sons + daughters share asaba with 2:1 ratio.
        total_units = 2 * inp.sons + inp.daughters
        # Reserve a single asaba "slot" pseudo-heir; we'll split when
        # finalising. For accounting we represent it as one slot whose
        # fraction is 0 (residue) and a special marker.
        asaba_slots.append(_Slot(
            heir_template="__sons_and_daughters__",
            count=total_units,
            share_fraction=Fraction(0),
            article_refs=["Art. 100"],
            reasoning="Sons and daughters: agnatic residue, 2:1 ratio.",
            is_fardh=False,
        ))
    elif inp.daughters > 0:
        if inp.daughters == 1:
            fardh_slots.append(_Slot(
                "daughter", 1, Fraction(1, 2),
                ["Art. 99"],
                "Single daughter: 1/2 fardh.",
                is_fardh=True,
            ))
        else:
            fardh_slots.append(_Slot(
                "daughter", inp.daughters, Fraction(2, 3),
                ["Art. 99"],
                f"{inp.daughters} daughters: 2/3 fardh, equal split.",
                is_fardh=True,
            ))

    # ── Siblings (Arts 101, 113, 140) ──────────────────────────────────
    if not siblings_blocked:
        if inp.maternal_siblings > 0:
            # Uterine siblings: 1/6 if one, 1/3 if ≥2, equal split.
            share = Fraction(1, 6) if inp.maternal_siblings == 1 else Fraction(1, 3)
            fardh_slots.append(_Slot(
                "maternal_sibling", inp.maternal_siblings, share,
                ["Art. 140"],
                f"{inp.maternal_siblings} uterine sibling(s): {share} equal split.",
                is_fardh=True,
            ))
        # Full siblings only matter when there is no son and no father.
        if inp.full_brothers > 0 or inp.full_sisters > 0:
            if inp.full_brothers > 0:
                # asaba: 2:1 between brothers and sisters.
                total_units = 2 * inp.full_brothers + inp.full_sisters
                asaba_slots.append(_Slot(
                    "__full_siblings__", total_units, Fraction(0),
                    ["Art. 110"],
                    "Full siblings: agnatic residue, 2:1 ratio (brothers : sisters).",
                    is_fardh=False,
                ))
            else:
                # Sisters only — fardh.
                if inp.full_sisters == 1:
                    fardh_slots.append(_Slot(
                        "full_sister", 1, Fraction(1, 2),
                        ["Art. 101"],
                        "Single full sister: 1/2 fardh.",
                        is_fardh=True,
                    ))
                else:
                    fardh_slots.append(_Slot(
                        "full_sister", inp.full_sisters, Fraction(2, 3),
                        ["Art. 101"],
                        f"{inp.full_sisters} full sisters: 2/3 fardh, equal split.",
                        is_fardh=True,
                    ))
        elif inp.paternal_brothers > 0 or inp.paternal_sisters > 0:
            # Paternal-only siblings — same scheme as full siblings.
            if inp.paternal_brothers > 0:
                total_units = 2 * inp.paternal_brothers + inp.paternal_sisters
                asaba_slots.append(_Slot(
                    "__paternal_siblings__", total_units, Fraction(0),
                    ["Art. 110"],
                    "Paternal siblings: agnatic residue, 2:1 ratio.",
                    is_fardh=False,
                ))
            else:
                if inp.paternal_sisters == 1:
                    fardh_slots.append(_Slot(
                        "paternal_sister", 1, Fraction(1, 2),
                        ["Art. 101"],
                        "Single paternal sister: 1/2 fardh.",
                        is_fardh=True,
                    ))
                else:
                    fardh_slots.append(_Slot(
                        "paternal_sister", inp.paternal_sisters, Fraction(2, 3),
                        ["Art. 101"],
                        f"{inp.paternal_sisters} paternal sisters: 2/3 fardh, equal split.",
                        is_fardh=True,
                    ))

    # ── Awl: scale fardh down when sum > 1 ──────────────────────────────
    fardh_sum = sum((s.share_fraction for s in fardh_slots), Fraction(0))
    awl_applied = False
    if fardh_sum > 1:
        awl_applied = True
        scale = Fraction(1) / fardh_sum
        for s in fardh_slots:
            s.share_fraction = s.share_fraction * scale
            s.reasoning += f" [ʿawl scale {scale}]"
            s.article_refs.append("Art. 120")
        notes.append(f"ʿawl applied: fardh sum was {fardh_sum}, scaled by {scale}.")
        fardh_sum = Fraction(1)

    # ── Asaba: distribute the residue ───────────────────────────────────
    residue = Fraction(1) - fardh_sum
    if asaba_slots and residue > 0:
        # Father has priority over collateral asaba; sons/daughters and
        # full siblings are mutually exclusive in our input space (sons
        # block siblings via `siblings_blocked`).
        father_slot = next(
            (s for s in asaba_slots if s.heir_template == "father"), None
        )
        if father_slot is not None:
            other_asaba = [s for s in asaba_slots if s is not father_slot]
            # Father takes the entire residue when no descendants exist.
            # When daughters exist, father already took 1/6 fardh — the
            # remaining residue (after daughters' fardh) goes to him.
            if not other_asaba:
                father_slot.share_fraction = residue
                father_slot.reasoning = "Father: agnatic residue."
            else:
                # Should not occur with the inputs we model (sons block
                # siblings; siblings only become asaba when no father).
                share_each = residue / Fraction(len(asaba_slots))
                for s in asaba_slots:
                    s.share_fraction = share_each
                    s.reasoning += f" [share {share_each}]"
        else:
            primary = asaba_slots[0]
            primary.share_fraction = residue
            primary.reasoning = (
                f"{primary.reasoning.split(':')[0].strip()}: residue {residue}."
            )

    # ── Radd: when fardh < 1 and no asaba, return residue to fardh ──────
    radd_applied = False
    if not asaba_slots and fardh_sum < 1:
        radd_eligible = [s for s in fardh_slots if not s.excluded_from_radd]
        if radd_eligible:
            radd_total = sum(
                (s.share_fraction for s in radd_eligible), Fraction(0)
            )
            if radd_total > 0:
                residue = Fraction(1) - fardh_sum
                for s in radd_eligible:
                    extra = residue * (s.share_fraction / radd_total)
                    s.share_fraction = s.share_fraction + extra
                    s.reasoning += f" [radd +{extra}]"
                    s.article_refs.append("Art. 130")
                radd_applied = True
                notes.append(
                    f"Radd applied: residue {residue} returned to fardh heirs "
                    "(spouse excluded)."
                )

    # ── Drop zero slots and build the final list ───────────────────────
    final_slots: list[_Slot] = [
        s for s in (fardh_slots + asaba_slots) if s.share_fraction > 0
    ]
    return final_slots, notes, awl_applied, radd_applied


# ──────────────────────────────────────────────────────────────────────────
# Public API
# ──────────────────────────────────────────────────────────────────────────


def compute(inp: SuccessionInput) -> SuccessionResult:
    """Compute heir shares for a Tunisian succession scenario."""
    slots, notes, awl_applied, radd_applied = _compute(inp)
    estate = (
        float(inp.estate_value_tnd) if inp.estate_value_tnd is not None else None
    )
    heirs: list[HeirShare] = []
    seen_articles: list[str] = []

    for slot in slots:
        for art in slot.article_refs:
            if art not in seen_articles:
                seen_articles.append(art)

        if slot.heir_template == "__sons_and_daughters__":
            unit = slot.share_fraction / Fraction(slot.count)
            for i in range(1, inp.sons + 1):
                share = unit * 2
                heirs.append(_make_heir(
                    name=f"son_{i}", share=share, estate=estate,
                    refs=slot.article_refs, reasoning=slot.reasoning + " (son share = 2 units)",
                ))
            for i in range(1, inp.daughters + 1):
                share = unit
                heirs.append(_make_heir(
                    name=f"daughter_{i}", share=share, estate=estate,
                    refs=slot.article_refs, reasoning=slot.reasoning + " (daughter share = 1 unit)",
                ))
            continue

        if slot.heir_template == "__full_siblings__":
            unit = slot.share_fraction / Fraction(slot.count)
            for i in range(1, inp.full_brothers + 1):
                share = unit * 2
                heirs.append(_make_heir(
                    name=f"full_brother_{i}", share=share, estate=estate,
                    refs=slot.article_refs, reasoning=slot.reasoning,
                ))
            for i in range(1, inp.full_sisters + 1):
                share = unit
                heirs.append(_make_heir(
                    name=f"full_sister_{i}", share=share, estate=estate,
                    refs=slot.article_refs, reasoning=slot.reasoning,
                ))
            continue

        if slot.heir_template == "__paternal_siblings__":
            unit = slot.share_fraction / Fraction(slot.count)
            for i in range(1, inp.paternal_brothers + 1):
                share = unit * 2
                heirs.append(_make_heir(
                    name=f"paternal_brother_{i}", share=share, estate=estate,
                    refs=slot.article_refs, reasoning=slot.reasoning,
                ))
            for i in range(1, inp.paternal_sisters + 1):
                share = unit
                heirs.append(_make_heir(
                    name=f"paternal_sister_{i}", share=share, estate=estate,
                    refs=slot.article_refs, reasoning=slot.reasoning,
                ))
            continue

        # Per-heir slot (1 person) or split across N siblings of the same kind.
        if slot.count == 1:
            heirs.append(_make_heir(
                name=slot.heir_template, share=slot.share_fraction,
                estate=estate, refs=slot.article_refs, reasoning=slot.reasoning,
            ))
        else:
            unit = slot.share_fraction / Fraction(slot.count)
            for i in range(1, slot.count + 1):
                heirs.append(_make_heir(
                    name=f"{slot.heir_template}_{i}", share=unit,
                    estate=estate, refs=slot.article_refs, reasoning=slot.reasoning,
                ))

    # Merge any heir that appears in multiple slots (e.g. father takes a
    # 1/6 fardh AND an agnatic residue when daughters are present). We
    # preserve the first occurrence's reasoning and concatenate refs.
    merged: list[HeirShare] = []
    by_name: dict[str, int] = {}
    for h in heirs:
        if h.heir in by_name:
            existing = merged[by_name[h.heir]]
            existing.share_fraction = existing.share_fraction + h.share_fraction
            existing.share_percent = round(float(existing.share_fraction) * 100.0, 6)
            if estate is not None:
                existing.share_amount_tnd = round(estate * float(existing.share_fraction), 2)
            for ref in h.article_refs:
                if ref not in existing.article_refs:
                    existing.article_refs.append(ref)
            existing.reasoning = f"{existing.reasoning} + {h.reasoning}"
        else:
            by_name[h.heir] = len(merged)
            merged.append(h)
    heirs = merged

    total = sum((h.share_fraction for h in heirs), Fraction(0))
    if not heirs:
        notes.append("No legal heirs identified — estate escheats to the State (Art. 152).")
        seen_articles.append("Art. 152")

    citations = lookup_many(seen_articles)
    return SuccessionResult(
        heirs=heirs,
        total_distributed=total,
        radd_applied=radd_applied,
        awl_applied=awl_applied,
        notes=notes,
        citations=citations,
    )


def _make_heir(
    *, name: str, share: Fraction, estate: float | None,
    refs: list[str], reasoning: str,
) -> HeirShare:
    pct = float(share) * 100.0
    amount = (estate * float(share)) if estate is not None else None
    return HeirShare(
        heir=name,
        share_fraction=share,
        share_percent=round(pct, 6),
        share_amount_tnd=(round(amount, 2) if amount is not None else None),
        article_refs=list(refs),
        reasoning=reasoning,
    )


# ──────────────────────────────────────────────────────────────────────────
# Self-tests — run with: python -m backend.services.legal.succession_calculator
# ──────────────────────────────────────────────────────────────────────────


def _shares_by_heir(result: SuccessionResult) -> dict[str, Fraction]:
    return {h.heir: h.share_fraction for h in result.heirs}


def _run_self_tests() -> int:
    failures: list[str] = []

    def check(name: str, got: dict[str, Fraction], expected: dict[str, Fraction]):
        if got == expected:
            print(f"  [OK] {name}")
            return
        diff: list[str] = []
        for k in sorted(set(got) | set(expected)):
            g = got.get(k)
            e = expected.get(k)
            if g != e:
                diff.append(f"    {k}: expected {e}, got {g}")
        failures.append(f"[FAIL] {name}\n" + "\n".join(diff))
        print(f"  [FAIL] {name}")

    print("Running CSP succession calculator self-tests...\n")

    # 1. Husband + 2 sons + 1 daughter (estate 120 000 TND)
    r = compute(SuccessionInput(spouse_kind="wife", sons=2, daughters=1, estate_value_tnd=120000))
    # Wife 1/8, residue 7/8 distributed 2:2:1 → unit = (7/8)/5 = 7/40
    # Sons 14/40 each = 7/20; daughter 7/40
    check(
        "1. Wife + 2 sons + 1 daughter",
        _shares_by_heir(r),
        {
            "wife": Fraction(1, 8),
            "son_1": Fraction(7, 20),
            "son_2": Fraction(7, 20),
            "daughter_1": Fraction(7, 40),
        },
    )

    # 2. Wife + 1 daughter + father + mother
    # Wife 1/8, mother 1/6, father 1/6 + asaba, daughter 1/2 → fardh sum 1/8+1/6+1/6+1/2 = 23/24
    # Father gets the 1/24 residue.
    r = compute(SuccessionInput(
        spouse_kind="wife", sons=0, daughters=1,
        father_alive=True, mother_alive=True,
    ))
    check(
        "2. Wife + 1 daughter + father + mother",
        _shares_by_heir(r),
        {
            "wife": Fraction(1, 8),
            "mother": Fraction(1, 6),
            "father": Fraction(1, 6) + Fraction(1, 24),
            "daughter": Fraction(1, 2),
        },
    )

    # 3. Husband + father + mother (ʿumariyyatān)
    # Husband 1/2, mother 1/3 of (1 - 1/2) = 1/6, father takes residue = 1/3.
    r = compute(SuccessionInput(
        spouse_kind="husband", father_alive=True, mother_alive=True,
    ))
    check(
        "3. Husband + father + mother (ʿumariyyatān)",
        _shares_by_heir(r),
        {
            "husband": Fraction(1, 2),
            "mother": Fraction(1, 6),
            "father": Fraction(1, 3),
        },
    )

    # 4. Single daughter (radd)
    # Daughter 1/2 fardh + radd of 1/2 → 1.
    r = compute(SuccessionInput(spouse_kind="none", daughters=1))
    check(
        "4. Single daughter (radd to 1)",
        _shares_by_heir(r),
        {"daughter": Fraction(1)},
    )
    assert r.radd_applied is True, "radd flag must be True"

    # 5. Husband + 2 full sisters (ʿawl)
    # Husband 1/2 + sisters 2/3 = 7/6 → ʿawl scale 6/7
    # Husband: (1/2)*(6/7) = 3/7; sisters share (2/3)*(6/7)=4/7 split 2 ways = 2/7 each.
    r = compute(SuccessionInput(spouse_kind="husband", full_sisters=2))
    check(
        "5. Husband + 2 full sisters (ʿawl)",
        _shares_by_heir(r),
        {
            "husband": Fraction(3, 7),
            "full_sister_1": Fraction(2, 7),
            "full_sister_2": Fraction(2, 7),
        },
    )
    assert r.awl_applied is True, "ʿawl flag must be True"

    # 6. Wife + 2 daughters (radd, spouse excluded)
    # Wife 1/8 (excluded from radd); 2 daughters 2/3 fardh.
    # Fardh sum = 1/8 + 2/3 = 19/24. Residue 5/24 returned to daughters
    # proportionally: each daughter +5/48 → daughter share = 1/3 + 5/48 = 21/48 = 7/16.
    r = compute(SuccessionInput(spouse_kind="wife", daughters=2))
    check(
        "6. Wife + 2 daughters (radd, wife excluded)",
        _shares_by_heir(r),
        {
            "wife": Fraction(1, 8),
            "daughter_1": Fraction(7, 16),
            "daughter_2": Fraction(7, 16),
        },
    )
    assert r.radd_applied is True

    # 7. All-male: 3 sons (no spouse, no parents)
    r = compute(SuccessionInput(spouse_kind="none", sons=3))
    check(
        "7. 3 sons only",
        _shares_by_heir(r),
        {
            "son_1": Fraction(1, 3),
            "son_2": Fraction(1, 3),
            "son_3": Fraction(1, 3),
        },
    )

    # 8. No heirs at all → empty result with State note.
    r = compute(SuccessionInput(spouse_kind="none"))
    if r.heirs:
        failures.append(f"[FAIL] 8. No heirs — expected empty, got {len(r.heirs)} heirs")
        print("  [FAIL] 8. No heirs case")
    else:
        print("  [OK] 8. No heirs (estate escheats to State)")

    print()
    if failures:
        print(f"[FAIL] {len(failures)} test(s) failed:\n")
        for f in failures:
            print(f)
        return 1
    print("[OK] all 8 cases passed")
    return 0


if __name__ == "__main__":
    sys.exit(_run_self_tests())


__all__ = [
    "SuccessionInput",
    "SuccessionResult",
    "HeirShare",
    "compute",
]
