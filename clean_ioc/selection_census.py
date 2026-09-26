"""Bounded, value-free summaries of recorded compiler selection decisions."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Mapping

from .tooling import DecisionOutcome, SourceLocation, qualified_name

if TYPE_CHECKING:
    from .tooling import CompilationExplanation, CompiledGraph


_EXAMPLE_LIMIT = 8
_RAW_UUID = re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b")


@dataclass(frozen=True, slots=True)
class DefinitionReference:
    """A declaration ordinal; ``_identity`` is never exported."""

    reference: str
    kind: str
    service: str
    implementation: str | None
    name: str | None
    layer: str
    boundary: str | None
    source: str | None = None
    template: str | None = None
    location: SourceLocation | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "reference": self.reference,
            "kind": self.kind,
            "service": self.service,
            "implementation": self.implementation,
            "name": self.name,
            "layer": self.layer,
            "boundary": self.boundary,
            "source": self.source,
            "template": self.template,
            "location": None if self.location is None else self.location.to_dict(),
        }


@dataclass(frozen=True, slots=True)
class SelectionUse:
    """One recorded outcome for one request, without raw registration IDs."""

    path: str
    relationship: str
    phase: str
    outcome: str
    reason_codes: tuple[str, ...]
    requested_service: str
    selected_tier: str | None = None
    area: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "path": self.path,
            "relationship": self.relationship,
            "phase": self.phase,
            "outcome": self.outcome,
            "reason_codes": list(self.reason_codes),
            "requested_service": self.requested_service,
            "selected_tier": self.selected_tier,
            "area": self.area,
        }


@dataclass(frozen=True, slots=True)
class DefinitionCensus:
    definition: DefinitionReference
    root_requests: int
    root_collection_inclusions: int
    dependency_requests: int
    deferred_target_uses: int
    collection_inclusions: int
    applicable_decorators: int
    applicable_pre_configurations: int
    template_source_matches: int
    template_source_rejections: int
    eligible_not_selected: int
    rejected_requests: int
    precedence_exclusions: int
    visibility_exclusions: int
    not_applicable_requests: int
    failed_requests: int
    not_examined_requests: int
    attempt_selected: int
    attempt_rejected: int
    rejection_reasons: tuple[tuple[str, int], ...]
    closed_specializations: tuple[str, ...]
    recorded_requests: int
    examples: tuple[SelectionUse, ...]
    omitted_examples: int

    def to_dict(self) -> dict[str, object]:
        return {
            "definition": self.definition.to_dict(),
            "root_requests": self.root_requests,
            "root_collection_inclusions": self.root_collection_inclusions,
            "dependency_requests": self.dependency_requests,
            "deferred_target_uses": self.deferred_target_uses,
            "collection_inclusions": self.collection_inclusions,
            "applicable_decorators": self.applicable_decorators,
            "applicable_pre_configurations": self.applicable_pre_configurations,
            "template_source_matches": self.template_source_matches,
            "template_source_rejections": self.template_source_rejections,
            "eligible_not_selected": self.eligible_not_selected,
            "rejected_requests": self.rejected_requests,
            "precedence_exclusions": self.precedence_exclusions,
            "visibility_exclusions": self.visibility_exclusions,
            "not_applicable_requests": self.not_applicable_requests,
            "failed_requests": self.failed_requests,
            "not_examined_requests": self.not_examined_requests,
            "attempt_selected": self.attempt_selected,
            "attempt_rejected": self.attempt_rejected,
            "rejection_reasons": dict(self.rejection_reasons),
            "closed_specializations": list(self.closed_specializations),
            "recorded_requests": self.recorded_requests,
            "evidence": "no recorded request" if self.recorded_requests == 0 else "recorded requests",
            "examples": [item.to_dict() for item in self.examples],
            "omitted_examples": self.omitted_examples,
        }


@dataclass(frozen=True, slots=True)
class SelectionCensus:
    definitions: tuple[DefinitionCensus, ...]
    view: str
    analyzed_roots: tuple[str, ...]
    include_deferred: bool
    complete: bool
    evidence_limit: int = _EXAMPLE_LIMIT
    capture_limit: int | None = None
    capture_truncated: bool = False
    limitation: str = (
        "Recorded compiler decisions in this view only; runtime requests and other build inputs are unknown."
    )

    def to_dict(self) -> dict[str, object]:
        return {
            "view": self.view,
            "analyzed_roots": list(self.analyzed_roots),
            "include_deferred": self.include_deferred,
            "complete": self.complete,
            "totals_exact": self.complete,
            "evidence_limit_per_definition": self.evidence_limit,
            "capture_limit": self.capture_limit,
            "capture_truncated": self.capture_truncated,
            "limitation": self.limitation,
            "definitions": [item.to_dict() for item in self.definitions],
        }

    def to_json(self, *, indent: int | None = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, sort_keys=True)

    def to_text(self) -> str:
        lines = [
            f"Selection census — {self.view}; {'including' if self.include_deferred else 'excluding'} deferred targets",
            f"Completeness: {'complete for recorded view' if self.complete else 'partial failed build'}",
            f"Capture: {'truncated' if self.capture_truncated else 'not truncated'}",
            f"Analyzed roots: {', '.join(self.analyzed_roots) or 'none'}",
            self.limitation,
        ]
        for item in self.definitions:
            definition = item.definition
            label = (
                f"{definition.service} → {definition.implementation}"
                if definition.implementation
                else definition.service
            )
            area = f"; boundary={definition.boundary}" if definition.boundary is not None else ""
            lines.append(f"\n{definition.reference} {label} [{definition.kind}; {definition.layer}{area}]")
            if definition.source is not None:
                lines.append(f"  Source: {definition.source}")
            if definition.template is not None:
                lines.append(f"  Template: {definition.template}")
            if item.recorded_requests == 0:
                lines.append("  No recorded request in this view")
            else:
                if self.complete:
                    lines.append(
                        f"  Selected by {item.dependency_requests} distinct dependency requests; "
                        f"{item.deferred_target_uses} deferred target uses; "
                        f"{item.collection_inclusions} dependency collection inclusions; "
                        f"{item.root_requests} root selections; "
                        f"{item.root_collection_inclusions} root collection inclusions"
                    )
                else:
                    lines.append(
                        f"  Primary attempt: {item.attempt_selected} recorded selected outcomes; "
                        f"{item.attempt_rejected} recorded rejected outcomes (lower bounds)"
                    )
                if self.complete and not (
                    item.dependency_requests
                    or item.deferred_target_uses
                    or item.root_collection_inclusions
                    or item.collection_inclusions
                    or item.root_requests
                    or item.applicable_decorators
                    or item.applicable_pre_configurations
                    or item.template_source_matches
                ):
                    lines.append("  Not selected in this view")
                if item.applicable_decorators or item.applicable_pre_configurations:
                    lines.append(
                        f"  Applicable decorators: {item.applicable_decorators}; "
                        f"pre-configurations: {item.applicable_pre_configurations}"
                    )
                if item.template_source_matches or item.template_source_rejections:
                    lines.append(
                        f"  Template sources matched: {item.template_source_matches}; "
                        f"rejected: {item.template_source_rejections}"
                    )
                if item.eligible_not_selected:
                    lines.append(f"  Eligible but not selected: {item.eligible_not_selected}")
                if item.rejected_requests:
                    reasons = ", ".join(f"{key}={count}" for key, count in item.rejection_reasons)
                    lines.append(f"  Rejected in {item.rejected_requests} requests: {reasons}")
                if item.precedence_exclusions or item.visibility_exclusions or item.not_applicable_requests:
                    lines.append(
                        f"  Excluded by precedence: {item.precedence_exclusions}; "
                        f"visibility: {item.visibility_exclusions}; "
                        f"not applicable: {item.not_applicable_requests}"
                    )
                if item.failed_requests:
                    lines.append(f"  Failed before a selection outcome in {item.failed_requests} recorded attempts")
                if item.not_examined_requests:
                    lines.append(f"  Not examined in {item.not_examined_requests} recorded attempts")
            if item.closed_specializations:
                lines.append(f"  Closed specializations: {', '.join(item.closed_specializations)}")
            for use in item.examples:
                area = f" [boundary={use.area}]" if use.area is not None else ""
                lines.append(f"  - {use.outcome} {use.relationship} ({use.phase}) at {use.path}{area}")
            if item.omitted_examples:
                lines.append(f"  … {item.omitted_examples} further recorded outcomes")
        return "\n".join(lines)


def _source_id(raw_id: str, sources: dict[str, str]) -> str:
    previous = None
    while raw_id in sources and raw_id != previous:
        previous = raw_id
        raw_id = sources[raw_id]
    return raw_id


def _aggregate(
    definitions: tuple[DefinitionReference, ...],
    observations: list[tuple[str, SelectionUse, str | None]],
    sources: dict[str, str],
    identities: Mapping[str, str],
    *,
    view: str,
    roots: tuple[str, ...],
    include_deferred: bool,
    complete: bool,
) -> SelectionCensus:
    buckets: dict[str, list[tuple[SelectionUse, str | None]]] = {item.reference: [] for item in definitions}
    for raw_id, use, specialization in observations:
        reference = identities.get(_source_id(raw_id, sources))
        if reference in buckets:
            buckets[reference].append((use, specialization))
    summaries: list[DefinitionCensus] = []
    for definition in definitions:
        records = buckets[definition.reference]
        counts = {
            kind: sum(use.outcome == kind for use, _ in records)
            for kind in (
                "root-selected",
                "root-collection-included",
                "dependency-selected",
                "deferred-target",
                "collection-included",
                "decorator-applicable",
                "pre-configuration-applicable",
                "template-source-matched",
                "template-source-rejected",
                "eligible-not-selected",
                "rejected",
                "excluded-by-precedence",
                "excluded-by-visibility",
                "not-applicable",
                "attempt-failed",
                "attempt-not-examined",
                "attempt-selected",
                "attempt-rejected",
            )
        }
        reasons: dict[str, int] = {}
        for use, _ in records:
            if use.outcome == "rejected":
                for code in use.reason_codes:
                    reasons[code] = reasons.get(code, 0) + 1
        specializations = (
            tuple(sorted({value for _, value in records if value and value != definition.service}))
            if definition.kind == "registration-pattern" or "TypeVar(" in definition.service
            else ()
        )
        summaries.append(
            DefinitionCensus(
                definition,
                counts["root-selected"],
                counts["root-collection-included"],
                counts["dependency-selected"],
                counts["deferred-target"],
                counts["collection-included"],
                counts["decorator-applicable"],
                counts["pre-configuration-applicable"],
                counts["template-source-matched"],
                counts["template-source-rejected"],
                counts["eligible-not-selected"],
                counts["rejected"],
                counts["excluded-by-precedence"],
                counts["excluded-by-visibility"],
                counts["not-applicable"],
                counts["attempt-failed"],
                counts["attempt-not-examined"],
                counts["attempt-selected"],
                counts["attempt-rejected"],
                tuple(sorted(reasons.items())),
                specializations,
                len(records),
                tuple(use for use, _ in records[:_EXAMPLE_LIMIT]),
                max(0, len(records) - _EXAMPLE_LIMIT),
            )
        )
    limitation = (
        "Primary failed attempt only; selection totals are lower bounds and unexamined outcomes are unknown. "
        "Diagnostic retries are not merged."
        if not complete
        else "Recorded compiler decisions in this view only; runtime requests and other build inputs are unknown."
    )
    return SelectionCensus(tuple(summaries), view, roots, include_deferred, complete, limitation=limitation)


def selection_census(
    graph: CompiledGraph, *, all_roots: bool = False, include_deferred: bool = True
) -> SelectionCensus:
    """Read frozen explanations and graph paths; no selection callback is run."""

    from .components import ComponentKind
    from .container import _collection_request

    roots = graph._selected_roots(all_roots)
    view = "all_roots" if all_roots or not graph.entrypoints else "entrypoints"
    selected_paths = graph._component_paths(all_roots=all_roots)
    root_paths = (path for path in selected_paths if "/" not in path)
    area_by_root_path = {path: root.area for root, path in zip(roots, root_paths, strict=True)}
    index = graph.analysis_index()
    phase_by_path = {ref.path: ref.phase for refs in index.references_by_occurrence.values() for ref in refs}
    relationship_by_path = {
        item.child.path: item.kind for relationships in index.incoming.values() for item in relationships
    }
    sources = dict(graph._census_sources)
    observations: list[tuple[str, SelectionUse, str | None]] = []
    seen: set[int] = set()
    for path, component in selected_paths.items():
        if "/" not in path:
            continue
        if component.kind in (ComponentKind.provider, ComponentKind.per_call_handle):
            continue
        phase = phase_by_path.get(path, "eager")
        area = area_by_root_path.get(path.split("/", 1)[0])
        if phase == "deferred" and not include_deferred:
            continue
        explanation = graph._occurrence_explanations.get(component.occurrence_id)
        if explanation is None:
            if relationship_by_path.get(path) == "deferred_target":
                observations.append(
                    (
                        component.id,
                        SelectionUse(
                            path,
                            "deferred_target",
                            phase,
                            "deferred-target",
                            ("frozen-deferred-target",),
                            qualified_name(component.service_type),
                            area=area,
                        ),
                        qualified_name(component.service_type),
                    )
                )
            continue
        if id(explanation) in seen:
            continue
        seen.add(id(explanation))
        relationship = (
            "collection"
            if component.kind is ComponentKind.collection
            else "decorator"
            if component.kind is ComponentKind.decorator
            else "pre-configuration"
            if component.kind is ComponentKind.pre_configuration
            else relationship_by_path.get(path, "dependency")
        )
        _record_explanation(
            observations,
            explanation,
            path,
            relationship,
            phase,
            sources,
            selected_service=(
                None if component.kind is ComponentKind.collection else qualified_name(component.service_type)
            ),
            selected_tier=(
                None
                if component.occurrence_id not in graph._generic_explanations
                else graph._generic_explanations[component.occurrence_id].selected_tier
            ),
            area=area,
        )
    for path, component in selected_paths.items():
        if component.occurrence_id not in graph._decorator_explanations:
            continue
        phase = phase_by_path.get(path, "eager")
        if phase == "deferred" and not include_deferred:
            continue
        explanation = graph._decorator_explanations[component.occurrence_id]
        if id(explanation) not in seen:
            seen.add(id(explanation))
            _record_explanation(
                observations,
                explanation,
                path,
                "decorator",
                phase,
                sources,
                area=area_by_root_path.get(path.split("/", 1)[0]),
            )
    for root in roots:
        component = root.component
        root_path = next(
            (
                path
                for path, item in selected_paths.items()
                if item.occurrence_id == component.occurrence_id and "/" not in path
            ),
            None,
        )
        if root_path is None:
            continue
        source_component = (
            component.dependencies[0]
            if component.kind is ComponentKind.provider
            and component.dependencies
            and component.dependencies[0].kind is not ComponentKind.collection
            else component
        )
        source = _source_id(source_component.id, sources)
        outcome = "root-collection-included" if _collection_request(root.requested_type) else "root-selected"
        observations.append(
            (
                source,
                SelectionUse(
                    root_path,
                    "root",
                    "eager",
                    outcome,
                    (outcome,),
                    qualified_name(root.requested_type),
                    area=root.area,
                ),
                qualified_name(source_component.service_type),
            )
        )
    if graph.entrypoints and not all_roots:
        for boundary, explanation in graph._census_root_selections:
            request_path = "/".join(explanation.path)
            if boundary is not None:
                request_path = f"boundary:{boundary}/{request_path}"
            for decision in explanation.selected[1:]:
                if decision.outcome is DecisionOutcome.included:
                    continue
                observations.append(
                    (
                        decision.component_id,
                        SelectionUse(
                            request_path,
                            "root",
                            "eager",
                            "eligible-not-selected",
                            (*decision.reason_codes, "first-eligible-wins"),
                            explanation.subject,
                            area=boundary,
                        ),
                        None,
                    )
                )
            for decision in explanation.rejected:
                observations.append(
                    (
                        decision.component_id,
                        SelectionUse(
                            request_path,
                            "root",
                            "eager",
                            _rejection_outcome(decision.reason_codes),
                            decision.reason_codes,
                            explanation.subject,
                            area=boundary,
                        ),
                        None,
                    )
                )
    else:
        for service_type, records in graph._root_candidates.items():
            for record in records:
                if record.eligible or record.component.kind is ComponentKind.provider:
                    continue
                observations.append(
                    (
                        record.component.id,
                        SelectionUse(
                            f"root:{qualified_name(service_type)}",
                            "root",
                            "eager",
                            _rejection_outcome(record.decision.reason_codes),
                            record.decision.reason_codes,
                            qualified_name(service_type),
                        ),
                        None,
                    )
                )
    for decision in graph._template_source_decisions:
        observations.append(
            (
                decision.template_id,
                SelectionUse(
                    f"template-source:{decision.source_service}",
                    "template-source",
                    "composition",
                    "template-source-matched" if decision.selected else "template-source-rejected",
                    ("template-source-filter-matched" if decision.selected else "template-source-filter-rejected",),
                    decision.source_service,
                ),
                None,
            )
        )
    labels = tuple(
        dict.fromkeys(
            qualified_name(root.requested_type)
            if root.area is None
            else f"boundary:{root.area}:{qualified_name(root.requested_type)}"
            for root in roots
        )
    )
    return _aggregate(
        graph._census_definitions,
        observations,
        sources,
        graph._census_ids,
        view=view,
        roots=labels,
        include_deferred=include_deferred,
        complete=True,
    )


def _record_explanation(
    observations: list[tuple[str, SelectionUse, str | None]],
    explanation: CompilationExplanation,
    path: str,
    relationship: str,
    phase: str,
    sources: dict[str, str],
    selected_service: str | None = None,
    selected_tier: str | None = None,
    area: str | None = None,
) -> None:
    selected = explanation.selected
    for index, decision in enumerate((*selected, *explanation.rejected)):
        raw_id = _source_id(decision.component_id, sources)
        if decision.outcome is DecisionOutcome.rejected:
            outcome = _rejection_outcome(decision.reason_codes)
        elif decision.outcome is DecisionOutcome.included:
            outcome = "collection-included"
        elif relationship == "decorator":
            outcome = "decorator-applicable"
        elif relationship == "pre-configuration":
            outcome = "pre-configuration-applicable"
        elif relationship == "deferred_target":
            outcome = "deferred-target"
        elif index > 0:
            outcome = "eligible-not-selected"
        else:
            outcome = "dependency-selected"
        observations.append(
            (
                raw_id,
                SelectionUse(
                    path,
                    relationship,
                    phase,
                    outcome,
                    (
                        (*decision.reason_codes, "first-eligible-wins")
                        if outcome == "eligible-not-selected"
                        else decision.reason_codes
                    ),
                    explanation.subject,
                    selected_tier if index == 0 else None,
                    area,
                ),
                selected_service
                if index == 0 and outcome in ("dependency-selected", "deferred-target", "collection-included")
                else None,
            )
        )


def _rejection_outcome(codes: tuple[str, ...]) -> str:
    if any(code in ("pattern-shadowed-by-exact", "pattern-less-specific") for code in codes):
        return "excluded-by-precedence"
    if "rejected-overlay-visibility" in codes:
        return "excluded-by-visibility"
    if "pattern-mismatch" in codes or "template-target-not-selected" in codes:
        return "not-applicable"
    return "rejected"


def failed_selection_census(error: Any) -> SelectionCensus:
    """Report only primary-attempt decisions already attached to a build error."""

    observations: list[tuple[str, SelectionUse, str | None]] = []
    sources = dict(error._census_sources)
    references = error._census_ids

    def safe_path(path: tuple[str, ...]) -> str:
        return "/".join(_RAW_UUID.sub(lambda match: references.get(match.group(), "definition"), part) for part in path)

    for explanation in error.explanations:
        path = safe_path(explanation.path)
        for decision in (*explanation.selected, *explanation.rejected):
            outcome = "attempt-selected" if decision.outcome is not DecisionOutcome.rejected else "attempt-rejected"
            observations.append(
                (
                    decision.component_id,
                    SelectionUse(
                        path, "failed-attempt", "unknown", outcome, decision.reason_codes, explanation.subject
                    ),
                    None,
                )
            )
    for subject, raw_id, state, code in error._census_attempts:
        if state.value not in ("failed", "not-examined"):
            continue
        observations.append(
            (
                raw_id,
                SelectionUse(
                    subject,
                    "failed-attempt",
                    "unknown",
                    f"attempt-{state.value}",
                    () if code is None else (code,),
                    subject,
                ),
                None,
            )
        )
    report = _aggregate(
        error._census_definitions,
        observations,
        sources,
        references,
        view="failed_primary_attempt",
        roots=tuple(label for _, label in error.entry_points or ()),
        include_deferred=True,
        complete=False,
    )
    from dataclasses import replace

    return replace(
        report,
        capture_limit=500,
        capture_truncated=bool(
            error.partial_graph and error.partial_graph.attempts and error.partial_graph.attempts[0].truncated
        ),
    )
