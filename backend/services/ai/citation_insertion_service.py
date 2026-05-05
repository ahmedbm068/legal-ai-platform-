"""Phase A2 — Citation insertion service.

Pure deterministic helper that handles "insert citation" commands inside a
draft body. The lawyer types or clicks a marker like ``[cite:doc:7]`` or
``[cite:source:3]`` and the service replaces it with a fully formatted
citation drawn from the supplied ``sources`` / ``citations`` lists.

No LLM. No DB. No IO. The contract is:

    insert_citation(body, marker_kind, ref_id, sources, citations)
        → { body: str, inserted: bool, label: str | None, reason: str }

A second helper ``parse_inline_markers`` resolves every marker already
present in a body in one pass — useful when the lawyer pastes a draft that
already contains markers from the outline phase.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Iterable, Mapping


# ``[cite:doc:7]`` → kind=doc, ref=7
# ``[cite:source:3]`` → kind=source, ref=3
# ``[cite:7]`` (legacy short form) → kind=source, ref=7
_MARKER_PATTERN = re.compile(
    r"\[cite:(?:(?P<kind>doc|source|citation):)?(?P<ref>\d{1,4})\]",
    re.IGNORECASE,
)

VALID_KINDS = frozenset({"doc", "source", "citation"})


@dataclass(frozen=True)
class CitationInsertion:
    body: str
    inserted: bool
    label: str | None
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "body": self.body,
            "inserted": self.inserted,
            "label": self.label,
            "reason": self.reason,
        }


class CitationInsertionService:
    """Stateless. See module docstring."""

    def insert_citation(
        self,
        *,
        body: str,
        marker_kind: str,
        ref_id: int,
        sources: Iterable[Mapping[str, Any]] | None = None,
        citations: Iterable[Mapping[str, Any]] | None = None,
        position: int | None = None,
    ) -> CitationInsertion:
        """Resolve a single marker to a formatted citation and inject it.

        If ``position`` is supplied, the resolved citation is inserted at
        that offset. Otherwise, the first occurrence of the matching
        marker token in ``body`` is replaced.
        """

        normalized_kind = (marker_kind or "").strip().lower()
        if normalized_kind not in VALID_KINDS:
            return CitationInsertion(
                body=body,
                inserted=False,
                label=None,
                reason=f"Unknown citation kind: {marker_kind!r}",
            )

        if not isinstance(ref_id, int) or ref_id < 0:
            return CitationInsertion(
                body=body,
                inserted=False,
                label=None,
                reason="ref_id must be a non-negative integer",
            )

        label = self._resolve_label(
            kind=normalized_kind,
            ref_id=ref_id,
            sources=list(sources or []),
            citations=list(citations or []),
        )
        if label is None:
            return CitationInsertion(
                body=body,
                inserted=False,
                label=None,
                reason=f"No matching {normalized_kind} for ref_id={ref_id}",
            )

        formatted = f" [{label}]"

        if position is not None:
            if not isinstance(position, int) or position < 0 or position > len(body):
                return CitationInsertion(
                    body=body,
                    inserted=False,
                    label=label,
                    reason="position out of bounds",
                )
            new_body = body[:position] + formatted + body[position:]
            return CitationInsertion(
                body=new_body,
                inserted=True,
                label=label,
                reason="inserted at position",
            )

        marker_token = f"[cite:{normalized_kind}:{ref_id}]"
        if marker_token in body:
            new_body = body.replace(marker_token, f"[{label}]", 1)
            return CitationInsertion(
                body=new_body,
                inserted=True,
                label=label,
                reason="marker token replaced",
            )

        # Fall back to legacy short marker ``[cite:N]`` only for source kind.
        if normalized_kind in {"source", "citation"}:
            short_token = f"[cite:{ref_id}]"
            if short_token in body:
                new_body = body.replace(short_token, f"[{label}]", 1)
                return CitationInsertion(
                    body=new_body,
                    inserted=True,
                    label=label,
                    reason="legacy short marker replaced",
                )

        # No marker present and no explicit position → append at end.
        new_body = (body.rstrip() + formatted).strip()
        return CitationInsertion(
            body=new_body,
            inserted=True,
            label=label,
            reason="appended at end (no marker found)",
        )

    def parse_inline_markers(
        self,
        *,
        body: str,
        sources: Iterable[Mapping[str, Any]] | None = None,
        citations: Iterable[Mapping[str, Any]] | None = None,
    ) -> CitationInsertion:
        """Resolve every ``[cite:*]`` marker in ``body`` in one pass.

        Unresolvable markers are left untouched (so the lawyer can see what
        failed); the ``reason`` field reports the count of substitutions.
        """

        sources_list = list(sources or [])
        citations_list = list(citations or [])
        substitutions = 0
        unresolved = 0

        def _replace(match: re.Match[str]) -> str:
            nonlocal substitutions, unresolved
            kind_raw = match.group("kind") or "source"
            kind = kind_raw.lower()
            if kind not in VALID_KINDS:
                unresolved += 1
                return match.group(0)
            try:
                ref_id = int(match.group("ref"))
            except (TypeError, ValueError):
                unresolved += 1
                return match.group(0)
            label = self._resolve_label(
                kind=kind,
                ref_id=ref_id,
                sources=sources_list,
                citations=citations_list,
            )
            if label is None:
                unresolved += 1
                return match.group(0)
            substitutions += 1
            return f"[{label}]"

        new_body = _MARKER_PATTERN.sub(_replace, body)
        reason = f"substituted={substitutions} unresolved={unresolved}"
        inserted = substitutions > 0
        return CitationInsertion(
            body=new_body,
            inserted=inserted,
            label=None,
            reason=reason,
        )

    # ──────────────────────────────────────────────────────────────────────
    # Resolution
    # ──────────────────────────────────────────────────────────────────────

    @staticmethod
    def _resolve_label(
        *,
        kind: str,
        ref_id: int,
        sources: list[Mapping[str, Any]],
        citations: list[Mapping[str, Any]],
    ) -> str | None:
        if kind == "doc":
            for item in sources:
                if not isinstance(item, Mapping):
                    continue
                doc_id = item.get("document_id")
                if isinstance(doc_id, int) and doc_id == ref_id:
                    name = (
                        item.get("filename")
                        or item.get("title")
                        or item.get("source_label")
                        or f"Document {ref_id}"
                    )
                    return f"Doc: {str(name).strip()}"
            return None

        # source / citation
        pool: list[Mapping[str, Any]]
        if kind == "citation":
            pool = citations
        else:  # source
            pool = citations if citations else sources

        if 1 <= ref_id <= len(pool):
            item = pool[ref_id - 1]
            if isinstance(item, Mapping):
                label = (
                    item.get("source_label")
                    or item.get("label")
                    or item.get("title")
                    or item.get("filename")
                    or f"Source {ref_id}"
                )
                return str(label).strip() or f"Source {ref_id}"
        return None


citation_insertion_service = CitationInsertionService()


__all__ = [
    "CitationInsertion",
    "CitationInsertionService",
    "citation_insertion_service",
    "VALID_KINDS",
]
