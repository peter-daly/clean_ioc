"""Value-free reports derived from a frozen compiled component graph."""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import Enum


class ContextualCacheCertainty(str, Enum):
    """What the compiler can establish about cached occurrence plans."""

    different = "different"
    equivalent_structure = "equivalent-structure"
    unknown_values = "unknown-values"


@dataclass(frozen=True, slots=True)
class SharingGroup:
    """Occurrences eligible to use one effective runtime cache entry.

    ``reference`` and ``paths`` are graph-local semantic references.  They are
    deliberately not registration IDs, runtime cache keys, or owner tokens.
    """

    reference: str
    paths: tuple[str, ...]
    cache_category: str
    declaring_owner: str
    service: str
    conditions: str
    activation: str

    def to_dict(self) -> dict[str, object]:
        return {
            "reference": self.reference,
            "paths": list(self.paths),
            "cache_category": self.cache_category,
            "declaring_owner": self.declaring_owner,
            "service": self.service,
            "conditions": self.conditions,
            "activation": self.activation,
        }


@dataclass(frozen=True, slots=True)
class ContextualCacheFinding:
    """A conservative comparison of plans which can initialize one cache."""

    group: str
    paths: tuple[str, ...]
    differing_fields: tuple[str, ...]
    evidence_paths: tuple[str, ...]
    certainty: ContextualCacheCertainty

    def to_dict(self) -> dict[str, object]:
        return {
            "group": self.group,
            "paths": list(self.paths),
            "differing_fields": list(self.differing_fields),
            "evidence_paths": list(self.evidence_paths),
            "certainty": self.certainty.value,
        }


@dataclass(frozen=True, slots=True)
class SharingReport:
    """Static cache-sharing eligibility; it never observes runtime objects."""

    groups: tuple[SharingGroup, ...]
    findings: tuple[ContextualCacheFinding, ...] = ()

    def to_dict(self) -> dict[str, object]:
        return {
            "groups": [group.to_dict() for group in self.groups],
            "contextual_cache_findings": [finding.to_dict() for finding in self.findings],
        }

    def to_json(self, *, indent: int | None = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, sort_keys=True)

    def for_path(self, path: str) -> "SharingReport":
        """Return only groups containing one exact current graph path."""

        groups = tuple(group for group in self.groups if path in group.paths)
        if not groups:
            raise ValueError(f"sharing-path-not-found: {path!r} is not in this sharing report")
        references = {group.reference for group in groups}
        return SharingReport(groups, tuple(finding for finding in self.findings if finding.group in references))

    def to_text(self) -> str:
        lines = [f"Sharing eligibility ({len(self.groups)} group{'s' if len(self.groups) != 1 else ''})."]
        for group in self.groups:
            noun = "occurrence" if len(group.paths) == 1 else "occurrences"
            lines.append(
                f"- {group.reference}: {group.service} [{group.cache_category}; {group.declaring_owner}] "
                f"— {len(group.paths)} {noun}; {group.conditions}"
            )
            lines.extend(f"  - {path}" for path in group.paths)
        for finding in self.findings:
            fields = ", ".join(finding.differing_fields) or "no proven structural difference"
            lines.append(f"- {finding.group}: {finding.certainty.value}; {fields}")
        return "\n".join(lines)

    def to_mermaid(self) -> str:
        lines = ["flowchart TD"]
        for number, group in enumerate(self.groups):
            group_id = f"g{number}"
            label = f"{group.reference}: {group.service} ({group.cache_category})".replace('"', "'")
            lines.append(f'    {group_id}["{label}"]')
            for path_number, path in enumerate(group.paths):
                path_id = f"p{number}_{path_number}"
                lines.append(f'    {path_id}["{path.replace(chr(34), chr(39))}"]')
                lines.append(f"    {path_id} --> {group_id}")
        return "\n".join(lines)

    def __str__(self) -> str:
        return self.to_text()
