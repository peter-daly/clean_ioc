"""Static analysis reports over a compiled Clean IoC graph."""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict, deque
from dataclasses import dataclass, field
from enum import Enum
from html import escape
from itertools import pairwise
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, Iterable, Literal, Mapping, Sequence

from .components import Component, ComponentActivation, ComponentKind, RuntimeOwnerKind
from .tooling import GraphRoot, qualified_name
from .type_aliases import normalize_type_alias

if TYPE_CHECKING:
    from .tooling import CompiledGraph

RelationshipKind = Literal[
    "dependency",
    "decorator",
    "pre_configuration",
    "deferred_target",
    "declared_resolution",
]
RelationshipPhase = Literal["eager", "deferred"]
ImpactMatch = Literal["occurrence", "registration"]


class ActivationScenario(str, Enum):
    cold = "cold"
    warm_singletons = "warm_singletons"
    warm_scope = "warm_scope"


class GraphSelectionError(ValueError):
    """Raised when a graph analysis selector is missing or ambiguous."""


@dataclass(frozen=True, slots=True)
class GraphReference:
    """A graph-local occurrence reference with a deterministic semantic path."""

    component: Component = field(compare=False, repr=False)
    path: str
    root: str
    phase: RelationshipPhase = "eager"

    @property
    def service(self) -> str:
        return qualified_name(self.component.service_type)

    def to_dict(self) -> dict[str, object]:
        return {
            "path": self.path,
            "root": self.root,
            "phase": self.phase,
            "service": self.service,
            "implementation": _implementation_name(self.component),
            "kind": self.component.kind.value,
            "lifespan": self.component.lifespan,
            "name": self.component.name,
            "boundary": self.component.boundary,
        }


@dataclass(frozen=True, slots=True)
class GraphRelationship:
    """A parent-to-child relationship captured from frozen component metadata."""

    parent: GraphReference
    child: GraphReference
    kind: RelationshipKind
    order: int
    argument: str | None = None
    phase: RelationshipPhase = "eager"

    def to_dict(self) -> dict[str, object]:
        return {
            "parent": self.parent.to_dict(),
            "child": self.child.to_dict(),
            "kind": self.kind,
            "order": self.order,
            "argument": self.argument,
            "phase": self.phase,
        }


@dataclass(frozen=True, slots=True)
class GraphIndex:
    """Immutable reverse index for one compiled graph."""

    references_by_occurrence: Mapping[int, tuple[GraphReference, ...]]
    occurrences_by_registration: Mapping[str, tuple[int, ...]]
    incoming: Mapping[int, tuple[GraphRelationship, ...]]
    outgoing: Mapping[int, tuple[GraphRelationship, ...]]
    root_membership: Mapping[int, tuple[GraphReference, ...]]

    def primary_reference(self, component: Component) -> GraphReference:
        references = self.references_by_occurrence.get(component.occurrence_id, ())
        if not references:
            raise GraphSelectionError("analysis-path-not-found: component is not in this graph")
        return references[0]

    def references_for(self, occurrence_id: int) -> tuple[GraphReference, ...]:
        return self.references_by_occurrence.get(occurrence_id, ())


@dataclass(frozen=True, slots=True)
class ImpactRoot:
    requested_type: str
    path: str
    witness_path: tuple[GraphReference, ...]
    deferred: bool
    boundary: str | None

    @property
    def service(self) -> str:
        """Compatibility alias for graph-reference-shaped root consumers."""

        return self.requested_type

    def to_dict(self) -> dict[str, object]:
        return {
            "requested_type": self.requested_type,
            "path": self.path,
            "witness_path": [reference.to_dict() for reference in self.witness_path],
            "deferred": self.deferred,
            "boundary": self.boundary,
        }


@dataclass(frozen=True, slots=True)
class DependencyImpact:
    """Reverse dependency summary for selected graph targets."""

    selected_targets: tuple[GraphReference, ...]
    direct_consumers: tuple[GraphRelationship, ...]
    affected_roots: tuple[ImpactRoot, ...]
    affected_entrypoints: tuple[ImpactRoot, ...]
    include_deferred: bool

    @property
    def witness_paths(self) -> Mapping[str, tuple[str, ...]]:
        """Return deterministic semantic witness paths keyed by affected root."""

        return MappingProxyType(
            {root.path: tuple(reference.path for reference in root.witness_path) for root in self.affected_roots}
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "selected_targets": [reference.to_dict() for reference in self.selected_targets],
            "direct_consumers": [relationship.to_dict() for relationship in self.direct_consumers],
            "affected_roots": [root.to_dict() for root in self.affected_roots],
            "affected_entrypoints": [root.to_dict() for root in self.affected_entrypoints],
            "include_deferred": self.include_deferred,
        }

    def to_json(self, *, indent: int | None = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, sort_keys=True)

    def to_text(self) -> str:
        lines = ["Dependency impact"]
        lines.append("Selected targets:")
        lines.extend(f"- {reference.service} at {reference.path}" for reference in self.selected_targets)
        lines.append("Direct consumers:")
        if self.direct_consumers:
            lines.extend(
                f"- {relationship.parent.service} at {relationship.parent.path} "
                f"[{relationship.kind}, {relationship.phase}]"
                for relationship in self.direct_consumers
            )
        else:
            lines.append("- none")
        lines.append("Affected roots:")
        if self.affected_roots:
            lines.extend(
                f"- {root.requested_type} at {root.path}" f"{' [deferred]' if root.deferred else ''}"
                for root in self.affected_roots
            )
        else:
            lines.append("- none")
        lines.append("Affected entry points:")
        if self.affected_entrypoints:
            lines.extend(
                f"- {root.requested_type} at {root.path}" f"{' [deferred]' if root.deferred else ''}"
                for root in self.affected_entrypoints
            )
        else:
            lines.append("- none")
        return "\n".join(lines)

    def to_mermaid(self) -> str:
        lines = ["flowchart TD"]
        ids: dict[str, str] = {}

        def node(reference: GraphReference, css_class: str) -> str:
            if reference.path not in ids:
                ids[reference.path] = f"n{len(ids)}"
                label = escape(f"{reference.service}\\n{reference.path}", quote=True)
                lines.append(f'    {ids[reference.path]}["{label}"]')
                lines.append(f"    class {ids[reference.path]} {css_class}")
            return ids[reference.path]

        for target in self.selected_targets:
            node(target, "target")
        for relationship in self.direct_consumers:
            parent = node(relationship.parent, "consumer")
            child = node(relationship.child, "target")
            edge = "deferred" if relationship.phase == "deferred" else relationship.kind
            lines.append(f"    {parent} -->|{edge}| {child}")
        lines.append("    classDef target fill:#fff4bf,stroke:#8f6b00,color:#111")
        lines.append("    classDef consumer fill:#dff3ff,stroke:#1f6f8b,color:#111")
        return "\n".join(lines)

    def __str__(self) -> str:
        return self.to_text()


@dataclass(frozen=True, slots=True)
class GraphSlice:
    """Bounded collection of concrete paths between graph occurrences."""

    paths: tuple[tuple[GraphReference, ...], ...]
    truncated: bool
    limit: int

    @property
    def max_paths(self) -> int:
        return self.limit

    @property
    def returned_paths(self) -> int:
        return len(self.paths)

    def to_dict(self) -> dict[str, object]:
        return {
            "paths": [[reference.to_dict() for reference in path] for path in self.paths],
            "truncated": self.truncated,
            "limit": self.limit,
            "returned": len(self.paths),
        }

    def to_json(self, *, indent: int | None = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, sort_keys=True)

    def to_text(self) -> str:
        lines = [f"Graph slice ({len(self.paths)} path{'s' if len(self.paths) != 1 else ''})"]
        if self.truncated:
            lines[0] += f" [truncated at {self.limit}]"
        if not self.paths:
            lines.append("- none")
        for path in self.paths:
            lines.append("- " + " -> ".join(reference.service for reference in path))
        return "\n".join(lines)

    def to_mermaid(self) -> str:
        references = {reference.path: reference for path in self.paths for reference in path}
        ids = {path: f"n{index}" for index, path in enumerate(sorted(references))}
        lines = ["flowchart TD"]
        for path, node_id in ids.items():
            reference = references[path]
            label = escape(f"{reference.service}\\n{path}", quote=True)
            lines.append(f'    {node_id}["{label}"]')
        seen_edges: set[tuple[str, str]] = set()
        for path in self.paths:
            for parent, child in pairwise(path):
                edge = (parent.path, child.path)
                if edge in seen_edges:
                    continue
                seen_edges.add(edge)
                arrow = "-.->" if child.phase == "deferred" else "-->"
                lines.append(f"    {ids[parent.path]} {arrow} {ids[child.path]}")
        return "\n".join(lines)


@dataclass(frozen=True, slots=True)
class SharedDependency:
    """A dependency selected by two roots."""

    key: str
    first_paths: tuple[GraphReference, ...]
    second_paths: tuple[GraphReference, ...]

    def to_dict(self) -> dict[str, object]:
        sample = (self.first_paths or self.second_paths)[0]
        return {
            "service": sample.service,
            "kind": sample.component.kind.value,
            "lifespan": sample.component.lifespan,
            "first_paths": [reference.to_dict() for reference in self.first_paths],
            "second_paths": [reference.to_dict() for reference in self.second_paths],
        }


@dataclass(frozen=True, slots=True)
class SharingGroup:
    """Static cache-sharing eligibility for a set of graph occurrences."""

    reference: str
    service: str
    implementation: str
    cache_category: str
    lifespan: str
    occurrence_paths: tuple[str, ...]
    conditions: tuple[str, ...]
    boundary: str | None
    declaring_owner: str = ""
    activation: str = ""

    @property
    def paths(self) -> tuple[str, ...]:
        return self.occurrence_paths

    def to_dict(self) -> dict[str, object]:
        return {
            "reference": self.reference,
            "service": self.service,
            "implementation": self.implementation,
            "cache_category": self.cache_category,
            "lifespan": self.lifespan,
            "occurrence_paths": list(self.occurrence_paths),
            "conditions": list(self.conditions),
            "boundary": self.boundary,
            "declaring_owner": self.declaring_owner,
            "activation": self.activation,
        }


class ContextualCacheCertainty(str, Enum):
    """What the compiler can establish about competing cached plans."""

    different = "different"
    equivalent_structure = "equivalent-structure"
    unknown_values = "unknown-values"


@dataclass(frozen=True, slots=True)
class ContextualCacheFinding:
    """Conservative note about occurrences that can initialize one cache group."""

    group_reference: str
    certainty: ContextualCacheCertainty
    message: str
    evidence_paths: tuple[str, ...]
    differing_fields: tuple[str, ...] = ()

    @property
    def group(self) -> str:
        return self.group_reference

    @property
    def paths(self) -> tuple[str, ...]:
        return self.evidence_paths

    def to_dict(self) -> dict[str, object]:
        return {
            "group_reference": self.group_reference,
            "certainty": self.certainty.value,
            "message": self.message,
            "evidence_paths": list(self.evidence_paths),
            "differing_fields": list(self.differing_fields),
        }


@dataclass(frozen=True, slots=True)
class SharingReport:
    groups: tuple[SharingGroup, ...]
    findings: tuple[ContextualCacheFinding, ...] = ()

    def to_dict(self) -> dict[str, object]:
        return {
            "groups": [group.to_dict() for group in self.groups],
            "findings": [finding.to_dict() for finding in self.findings],
        }

    def to_json(self, *, indent: int | None = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, sort_keys=True)

    def for_path(self, path: str) -> SharingReport:
        groups = tuple(group for group in self.groups if path in group.occurrence_paths)
        if not groups:
            raise ValueError(f"sharing-path-not-found: {path!r} is not in this sharing report")
        references = {group.reference for group in groups}
        return SharingReport(
            groups,
            tuple(finding for finding in self.findings if finding.group_reference in references),
        )

    def to_text(self) -> str:
        lines = [f"Sharing report ({len(self.groups)} group{'s' if len(self.groups) != 1 else ''})"]
        for group in self.groups:
            lines.append(f"- {group.service} [{group.cache_category}; {group.reference}]")
            lines.extend(f"  condition: {condition}" for condition in group.conditions)
            lines.extend(f"  occurrence: {path}" for path in group.occurrence_paths)
        if self.findings:
            lines.append("Findings:")
            lines.extend(f"- {finding.group_reference}: {finding.message}" for finding in self.findings)
        return "\n".join(lines)

    def to_mermaid(self) -> str:
        lines = ["flowchart TD"]
        for index, group in enumerate(self.groups):
            group_id = f"g{index}"
            label = escape(f"{group.service}\\n{group.cache_category}", quote=True)
            lines.append(f'    {group_id}["{label}"]')
            for path_index, path in enumerate(group.occurrence_paths):
                occurrence_id = f"g{index}o{path_index}"
                lines.append(f'    {occurrence_id}["{escape(path, quote=True)}"]')
                lines.append(f"    {occurrence_id} --> {group_id}")
        return "\n".join(lines)

    def __str__(self) -> str:
        return self.to_text()


@dataclass(frozen=True, slots=True)
class ActivationObligation:
    kind: str
    phase: RelationshipPhase
    path: str
    service: str
    message: str
    async_required: bool = False
    cache_owner: str | None = None
    cleanup_owner: str | None = None

    @property
    def component(self) -> str:
        return self.service

    @property
    def description(self) -> str:
        return self.message

    def to_dict(self) -> dict[str, object]:
        return {
            "kind": self.kind,
            "phase": self.phase,
            "path": self.path,
            "service": self.service,
            "message": self.message,
            "component": self.component,
            "description": self.description,
            "async_required": self.async_required,
            "cache_owner": self.cache_owner,
            "cleanup_owner": self.cleanup_owner,
        }


@dataclass(frozen=True, slots=True)
class ExecutionRelationship:
    parent_path: str
    child_path: str
    kind: RelationshipKind
    phase: RelationshipPhase
    order: int
    ordering: str = ""

    @property
    def source(self) -> str:
        return self.parent_path

    @property
    def target(self) -> str:
        return self.child_path

    def to_dict(self) -> dict[str, object]:
        return {
            "parent_path": self.parent_path,
            "child_path": self.child_path,
            "kind": self.kind,
            "phase": self.phase,
            "order": self.order,
            "ordering": self.ordering,
        }


@dataclass(frozen=True, slots=True)
class ActivationReport:
    selected_root: GraphReference
    scenario: ActivationScenario
    scenario_assumptions: tuple[str, ...]
    immediate_obligations: tuple[ActivationObligation, ...]
    deferred_obligations: tuple[ActivationObligation, ...]
    execution_relationships: tuple[ExecutionRelationship, ...]
    cache_skips: tuple[str, ...]
    unknown_runtime_work: tuple[str, ...]
    async_causes: tuple[ActivationObligation, ...] = ()
    potential_acquisitions: tuple[ActivationObligation, ...] = ()
    cleanup_owners: tuple[ActivationObligation, ...] = ()

    @property
    def root(self) -> str:
        return self.selected_root.service

    @property
    def root_path(self) -> str:
        return self.selected_root.path

    @property
    def assumptions(self) -> tuple[str, ...]:
        return self.scenario_assumptions

    def to_dict(self) -> dict[str, object]:
        return {
            "selected_root": self.selected_root.to_dict(),
            "root": self.root,
            "root_path": self.root_path,
            "scenario": self.scenario.value,
            "assumptions": list(self.assumptions),
            "scenario_assumptions": list(self.scenario_assumptions),
            "immediate_obligations": [item.to_dict() for item in self.immediate_obligations],
            "deferred_obligations": [item.to_dict() for item in self.deferred_obligations],
            "execution_relationships": [item.to_dict() for item in self.execution_relationships],
            "cache_skips": list(self.cache_skips),
            "unknown_runtime_work": list(self.unknown_runtime_work),
            "async_causes": [item.to_dict() for item in self.async_causes],
            "potential_acquisitions": [item.to_dict() for item in self.potential_acquisitions],
            "cleanup_owners": [item.to_dict() for item in self.cleanup_owners],
        }

    def to_json(self, *, indent: int | None = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, sort_keys=True)

    def to_text(self) -> str:
        lines = [f"Activation report for {self.selected_root.service}", f"Scenario: {self.scenario.value}"]
        lines.extend(f"- assumes {assumption}" for assumption in self.scenario_assumptions)
        lines.append("Immediate obligations:")
        lines.extend(_obligation_lines(self.immediate_obligations))
        lines.append("Deferred obligations:")
        lines.extend(_obligation_lines(self.deferred_obligations))
        for title, obligations in (
            ("Async causes", self.async_causes),
            ("Potential acquisitions", self.potential_acquisitions),
            ("Cleanup owners", self.cleanup_owners),
        ):
            lines.append(f"{title}:")
            lines.extend(_obligation_lines(obligations))
        if self.cache_skips:
            lines.append("Hypothetical cache hits:")
            lines.extend(f"- {path}" for path in self.cache_skips)
        if self.unknown_runtime_work:
            lines.append("Unknown runtime work:")
            lines.extend(f"- {item}" for item in self.unknown_runtime_work)
        return "\n".join(lines)

    def to_mermaid(self) -> str:
        lines = ["flowchart TD"]
        paths = {self.selected_root.path}
        for relationship in self.execution_relationships:
            paths.add(relationship.parent_path)
            paths.add(relationship.child_path)
        ids = {path: f"n{index}" for index, path in enumerate(sorted(paths))}
        for path, node_id in ids.items():
            lines.append(f'    {node_id}["{escape(path, quote=True)}"]')
        for relationship in self.execution_relationships:
            label = "deferred" if relationship.phase == "deferred" else relationship.kind
            lines.append(f"    {ids[relationship.parent_path]} -->|{label}| {ids[relationship.child_path]}")
        return "\n".join(lines)

    def __str__(self) -> str:
        return self.to_text()


def graph_index(graph: CompiledGraph) -> GraphIndex:
    """Build a deterministic reverse index for ``graph`` from frozen components."""

    cached = getattr(graph, "_analysis_index_cache", None)
    if isinstance(cached, GraphIndex):
        return cached

    references: dict[int, list[GraphReference]] = defaultdict(list)
    root_membership: dict[int, list[GraphReference]] = defaultdict(list)
    by_registration: dict[str, set[int]] = defaultdict(set)
    incoming: dict[int, list[GraphRelationship]] = defaultdict(list)
    outgoing: dict[int, list[GraphRelationship]] = defaultdict(list)
    all_paths = graph._component_paths(all_roots=True)
    component_by_path = dict(sorted(all_paths.items()))
    path_by_occurrence = {component.occurrence_id: path for path, component in component_by_path.items()}

    def reference(component: Component, path: str, root_path: str, phase: RelationshipPhase) -> GraphReference:
        item = GraphReference(component, path, root_path, phase)
        references[component.occurrence_id].append(item)
        root_membership[component.occurrence_id].append(item)
        by_registration[component.id].add(component.occurrence_id)
        return item

    def visit(
        component: Component,
        path: str,
        root_path: str,
        phase: RelationshipPhase,
        parent_ref: GraphReference | None = None,
        edge_kind: RelationshipKind | None = None,
        edge_order: int = 0,
    ) -> None:
        current = reference(component, path, root_path, phase)
        if parent_ref is not None and edge_kind is not None:
            provider_target = (
                parent_ref.component.kind
                in (
                    ComponentKind.provider,
                    ComponentKind.per_call_handle,
                )
                and edge_kind == "dependency"
            )
            relationship_phase = "deferred" if provider_target else phase
            relationship = GraphRelationship(
                parent_ref,
                current,
                "deferred_target" if provider_target else edge_kind,
                edge_order,
                component.argument,
                relationship_phase,
            )
            incoming[component.occurrence_id].append(relationship)
            outgoing[parent_ref.component.occurrence_id].append(relationship)
        for index, child in enumerate(component.dependencies):
            provider_target = component.kind in (ComponentKind.provider, ComponentKind.per_call_handle)
            declared_resolution = child.argument is not None and child.argument.startswith("resolution")
            child_phase = "deferred" if provider_target or declared_resolution else phase
            child_kind: RelationshipKind = "declared_resolution" if declared_resolution else "dependency"
            visit(
                child,
                f"{path}/dependency:{child.argument or index}:{index}",
                root_path,
                child_phase,
                current,
                child_kind,
                index,
            )
        for index, child in enumerate(component.pre_configurations):
            visit(
                child,
                f"{path}/pre_configuration:{index}",
                root_path,
                phase,
                current,
                "pre_configuration",
                index,
            )
        for index, child in enumerate(component.decorators):
            visit(child, f"{path}/decorator:{index}", root_path, phase, current, "decorator", index)

    for path, component in component_by_path.items():
        if "/" in path:
            continue
        visit(component, path, path, "eager")

    frozen = GraphIndex(
        references_by_occurrence=MappingProxyType(
            {key: tuple(sorted(value, key=lambda item: item.path)) for key, value in references.items()}
        ),
        occurrences_by_registration=MappingProxyType(
            {
                key: tuple(sorted(value, key=lambda item: path_by_occurrence.get(item, "")))
                for key, value in by_registration.items()
            }
        ),
        incoming=MappingProxyType({key: tuple(value) for key, value in incoming.items()}),
        outgoing=MappingProxyType({key: tuple(value) for key, value in outgoing.items()}),
        root_membership=MappingProxyType(
            {
                key: tuple(sorted(value, key=lambda item: (item.root, item.path)))
                for key, value in root_membership.items()
            }
        ),
    )
    object.__setattr__(graph, "_analysis_index_cache", frozen)
    return frozen


def dependency_impact(
    graph: CompiledGraph,
    target: Any,
    *,
    match: ImpactMatch = "registration",
    name: str | None = None,
    include_deferred: bool = False,
) -> DependencyImpact:
    index = graph_index(graph)
    selected = _select_occurrences(graph, index, target, match=match, name=name)
    selected_refs = tuple(
        reference
        for occurrence_id in selected
        for reference in index.references_for(occurrence_id)
        if include_deferred or reference.phase == "eager"
    )
    direct = tuple(
        relationship
        for occurrence_id in selected
        for relationship in index.incoming.get(occurrence_id, ())
        if include_deferred or relationship.phase == "eager"
    )
    reached = _reverse_reachable(index, selected, include_deferred=include_deferred)
    roots = _impact_roots(graph.roots, index, reached, set(selected), include_deferred=include_deferred)
    entrypoints = _impact_roots(graph.entrypoints, index, reached, set(selected), include_deferred=include_deferred)
    return DependencyImpact(
        tuple(sorted(selected_refs, key=lambda item: item.path)),
        tuple(sorted(direct, key=lambda item: (item.parent.path, item.child.path))),
        roots,
        entrypoints,
        include_deferred,
    )


def paths_between(
    graph: CompiledGraph,
    root: Any,
    dependency: Any,
    *,
    match: ImpactMatch = "registration",
    include_deferred: bool = True,
    max_paths: int = 100,
) -> GraphSlice:
    if max_paths < 1:
        raise ValueError("impact-invalid-path-limit: max_paths must be at least 1")
    index = graph_index(graph)
    roots = _select_occurrences(graph, index, root, match="occurrence")
    dependency_match: ImpactMatch = "occurrence" if isinstance(dependency, Component) else match
    targets = set(_select_occurrences(graph, index, dependency, match=dependency_match))
    paths: list[tuple[GraphReference, ...]] = []
    truncated = False

    for root_id in roots:
        for start in index.references_for(root_id):
            stack: list[tuple[GraphReference, tuple[GraphReference, ...]]] = [(start, (start,))]
            while stack:
                current, path = stack.pop()
                if current.component.occurrence_id in targets:
                    paths.append(path)
                    if len(paths) > max_paths:
                        return GraphSlice(tuple(paths[:max_paths]), True, max_paths)
                    continue
                for relationship in reversed(index.outgoing.get(current.component.occurrence_id, ())):
                    if relationship.parent.path != current.path:
                        continue
                    if not include_deferred and relationship.phase == "deferred":
                        continue
                    if any(item.component.occurrence_id == relationship.child.component.occurrence_id for item in path):
                        continue
                    stack.append((relationship.child, (*path, relationship.child)))
    return GraphSlice(tuple(paths), truncated, max_paths)


def shared_dependencies(
    graph: CompiledGraph,
    first_root: Any,
    second_root: Any,
    *,
    match: ImpactMatch = "registration",
    include_deferred: bool = True,
) -> tuple[SharedDependency, ...]:
    index = graph_index(graph)
    first = _descendant_references(
        index,
        _select_occurrences(graph, index, first_root, match="occurrence"),
        include_deferred,
    )
    second = _descendant_references(
        index,
        _select_occurrences(graph, index, second_root, match="occurrence"),
        include_deferred,
    )

    def key(reference: GraphReference) -> str:
        return reference.component.id if match == "registration" else str(reference.component.occurrence_id)

    first_by_key: dict[str, list[GraphReference]] = defaultdict(list)
    second_by_key: dict[str, list[GraphReference]] = defaultdict(list)
    for reference in first:
        first_by_key[key(reference)].append(reference)
    for reference in second:
        second_by_key[key(reference)].append(reference)
    return tuple(
        SharedDependency(
            item,
            tuple(sorted(first_by_key[item], key=lambda reference: reference.path)),
            tuple(sorted(second_by_key[item], key=lambda reference: reference.path)),
        )
        for item in sorted(first_by_key.keys() & second_by_key.keys())
    )


def sharing_report(graph: CompiledGraph, target: Any | None = None) -> SharingReport:
    index = graph_index(graph)
    target_ids = None if target is None else set(_select_occurrences(graph, index, target, match="registration"))
    grouped: dict[tuple[str, RuntimeOwnerKind, str, str], list[GraphReference]] = defaultdict(list)
    for occurrence_id, references in index.references_by_occurrence.items():
        component = references[0].component
        if component.kind not in (
            ComponentKind.registration,
            ComponentKind.provider_map,
            ComponentKind.per_call_handle,
        ):
            continue
        if (
            target_ids is not None
            and occurrence_id not in target_ids
            and component.id not in {index.references_for(item)[0].component.id for item in target_ids}
        ):
            continue
        layer = graph._occurrence_layers.get(component.occurrence_id, "root")
        for item in references:
            per_call_boundary = (
                item.path.split("/dependency:per_call_target:0", 1)[0]
                if "/dependency:per_call_target:0" in item.path
                and component.cache_owner not in (RuntimeOwnerKind.singleton, RuntimeOwnerKind.supplied)
                else ""
            )
            key = (component.id, component.cache_owner, layer, per_call_boundary)
            grouped[key].append(item)

    groups: list[SharingGroup] = []
    findings: list[ContextualCacheFinding] = []
    for index_number, (key, references) in enumerate(
        sorted(grouped.items(), key=lambda item: min(reference.path for reference in item[1])),
        start=1,
    ):
        unique_paths = tuple(sorted({reference.path for reference in references}))
        sample = references[0].component
        _, cache_owner, layer, per_call_boundary = key
        reference = f"sharing:{cache_owner.value}:{index_number}"
        groups.append(
            SharingGroup(
                reference=reference,
                service=qualified_name(sample.service_type),
                implementation=_implementation_name(sample),
                cache_category=_cache_category(sample),
                lifespan=sample.lifespan,
                occurrence_paths=unique_paths,
                conditions=_sharing_conditions(sample, per_call_target=bool(per_call_boundary)),
                boundary=sample.boundary,
                declaring_owner=_sharing_owner_label(cache_owner, layer, sample.boundary),
                activation=sample.activation.value,
            )
        )
        occurrence_components = _unique_components(reference_item.component for reference_item in references)
        cached_owners = (RuntimeOwnerKind.singleton, RuntimeOwnerKind.scope, RuntimeOwnerKind.resolution)
        if len(occurrence_components) > 1 and sample.cache_owner in cached_owners:
            certainty, differing_fields = _compare_occurrence_structure(occurrence_components)
            findings.append(
                ContextualCacheFinding(
                    group_reference=reference,
                    certainty=certainty,
                    message=(
                        "Multiple occurrence plans can initialize this cache group; "
                        "the first successful activation supplies later cache hits."
                    ),
                    evidence_paths=unique_paths,
                    differing_fields=differing_fields,
                )
            )
    return SharingReport(tuple(groups), tuple(findings))


def activation_report(
    graph: CompiledGraph,
    target: Any,
    *,
    scenario: str | ActivationScenario = "cold",
) -> ActivationReport:
    try:
        selected_scenario = ActivationScenario(scenario)
    except ValueError as error:
        choices = ", ".join(item.value for item in ActivationScenario)
        raise ValueError(f"activation-invalid-scenario: choose one of {choices}") from error
    index = graph_index(graph)
    root_id = _select_root_occurrence(graph, index, target)
    root_ref = index.primary_reference(_component_for_occurrence(index, root_id))
    assumptions = _scenario_assumptions(selected_scenario)
    immediate: list[ActivationObligation] = []
    deferred: list[ActivationObligation] = []
    async_causes: list[ActivationObligation] = []
    acquisitions: list[ActivationObligation] = []
    cleanup: list[ActivationObligation] = []
    relationships: list[ExecutionRelationship] = []
    cache_skips: list[str] = []
    unknown: list[str] = []

    def obligation(
        component: Component,
        path: str,
        phase: RelationshipPhase,
        kind: str,
        message: str,
    ) -> ActivationObligation:
        return ActivationObligation(
            kind=kind,
            phase=phase,
            path=path,
            service=qualified_name(component.service_type),
            message=message,
            async_required=component.requires_async,
            cache_owner=component.cache_owner.value,
            cleanup_owner=component.cleanup_owner.value,
        )

    def visit(component: Component, path: str, phase: RelationshipPhase, *, per_call_target: bool = False) -> None:
        phase_obligations = immediate if phase == "eager" else deferred
        if component.kind is ComponentKind.per_call_handle:
            phase_obligations.append(
                obligation(
                    component,
                    path,
                    phase,
                    "per_call_handle",
                    "Acquire a handle; each method invocation activates its target in a fresh scope",
                )
            )
            for order, child in enumerate(component.dependencies):
                child_path = f"{path}/dependency:{child.argument or order}:{order}"
                relationships.append(
                    ExecutionRelationship(
                        path, child_path, "deferred_target", "deferred", order, "on method invocation"
                    )
                )
                visit(child, child_path, "deferred", per_call_target=True)
            return
        if component.kind is ComponentKind.provider:
            phase_obligations.append(
                obligation(
                    component,
                    path,
                    phase,
                    "provider",
                    "Acquire a provider handle; invoking its target is deferred",
                )
            )
            for order, child in enumerate(component.dependencies):
                child_path = f"{path}/dependency:{child.argument or order}:{order}"
                relationships.append(
                    ExecutionRelationship(path, child_path, "deferred_target", "deferred", order, "on demand")
                )
                visit(child, child_path, "deferred", per_call_target=per_call_target)
            return

        if component.kind is ComponentKind.scope_slot:
            phase_obligations.append(
                obligation(
                    component,
                    path,
                    phase,
                    "scope_slot",
                    "A matching value must be supplied by the active scope",
                )
            )
            return

        if component.kind is ComponentKind.runtime_context:
            phase_obligations.append(
                obligation(
                    component,
                    path,
                    phase,
                    "runtime_context",
                    "Runtime context is supplied by the resolver",
                )
            )
            unknown.append(f"{path}: runtime context can perform declared or unrestricted resolution at runtime")

        if component.requires_async:
            async_obligation = obligation(
                component,
                path,
                phase,
                "async_requirement",
                "This compiled operation requires asynchronous activation",
            )
            phase_obligations.append(async_obligation)
            async_causes.append(async_obligation)

        if component.kind is ComponentKind.pre_configuration:
            phase_obligations.append(
                obligation(
                    component,
                    path,
                    phase,
                    "initializer",
                    "Pre-configuration runs before core activation on first use",
                )
            )

        skipped = _scenario_skips(component, selected_scenario) and not (
            per_call_target
            and selected_scenario is ActivationScenario.warm_scope
            and component.cache_owner is RuntimeOwnerKind.scope
        )
        if component.activation in (ComponentActivation.constructor, ComponentActivation.factory) and not skipped:
            acquisitions.append(
                obligation(
                    component,
                    path,
                    phase,
                    "construction",
                    "May construct or invoke the registered factory",
                )
            )

        if component.manages_cleanup:
            cleanup_obligation = obligation(
                component,
                path,
                phase,
                "resource",
                "Cleanup is retained by the compiled cleanup owner",
            )
            phase_obligations.append(cleanup_obligation)
            cleanup.append(cleanup_obligation)

        if skipped:
            cache_skips.append(path)
            return

        for order, configuration in enumerate(component.pre_configurations):
            child_path = f"{path}/pre_configuration:{order}"
            relationships.append(
                ExecutionRelationship(
                    path,
                    child_path,
                    "pre_configuration",
                    phase,
                    order,
                    "before core activation",
                )
            )
            visit(configuration, child_path, phase, per_call_target=per_call_target)

        for order, child in enumerate(component.dependencies):
            child_path = f"{path}/dependency:{child.argument or order}:{order}"
            declared_resolution = child.argument is not None and child.argument.startswith("resolution")
            child_phase: RelationshipPhase = "deferred" if declared_resolution else phase
            kind: RelationshipKind = "declared_resolution" if declared_resolution else "dependency"
            ordering = (
                "on explicit runtime request"
                if declared_resolution
                else "potentially concurrent collection member"
                if component.kind is ComponentKind.collection
                else "before core activation"
            )
            relationships.append(ExecutionRelationship(path, child_path, kind, child_phase, order, ordering))
            visit(child, child_path, child_phase, per_call_target=per_call_target)

        for order, decorator in enumerate(component.decorators):
            child_path = f"{path}/decorator:{order}"
            relationships.append(
                ExecutionRelationship(path, child_path, "decorator", phase, order, "after core activation")
            )
            visit(decorator, child_path, phase, per_call_target=per_call_target)

    visit(root_ref.component, root_ref.path, "eager")

    return ActivationReport(
        selected_root=root_ref,
        scenario=selected_scenario,
        scenario_assumptions=assumptions,
        immediate_obligations=tuple(immediate),
        deferred_obligations=tuple(deferred),
        execution_relationships=tuple(relationships),
        cache_skips=tuple(dict.fromkeys(cache_skips)),
        unknown_runtime_work=tuple(dict.fromkeys(unknown)),
        async_causes=tuple(async_causes),
        potential_acquisitions=tuple(acquisitions),
        cleanup_owners=tuple(cleanup),
    )


def _implementation_name(component: Component) -> str:
    if component.activation in (ComponentActivation.instance, ComponentActivation.supplied):
        return qualified_name(component.implementation_type)
    return qualified_name(component.implementation)


def _obligation_lines(obligations: Sequence[ActivationObligation]) -> list[str]:
    if not obligations:
        return ["- none"]
    return [f"- {item.kind}: {item.message} at {item.path}" for item in obligations]


def _select_occurrences(
    graph: CompiledGraph,
    index: GraphIndex,
    target: Any,
    *,
    match: ImpactMatch,
    name: str | None = None,
) -> tuple[int, ...]:
    if match not in ("occurrence", "registration"):
        raise ValueError("match must be 'occurrence' or 'registration'")
    if isinstance(target, Component):
        reference = index.primary_reference(target)
        if match == "occurrence":
            return (reference.component.occurrence_id,)
        return index.occurrences_by_registration.get(reference.component.id, (reference.component.occurrence_id,))
    service_type = normalize_type_alias(target)
    matches = tuple(
        sorted(
            {
                reference.component.occurrence_id
                for references in index.references_by_occurrence.values()
                for reference in references[:1]
                if reference.component.service_type == service_type
                and (name is None or reference.component.name == name)
            },
            key=lambda occurrence_id: index.references_for(occurrence_id)[0].path,
        )
    )
    if not matches:
        raise GraphSelectionError(f"analysis-service-not-found: {qualified_name(service_type)} is not in the graph")
    if match == "occurrence" and len(matches) > 1:
        raise GraphSelectionError(
            f"analysis-ambiguous-occurrence: {qualified_name(service_type)} "
            f"matches {len(matches)} occurrences; use --path"
        )
    if match == "registration":
        registration_ids = {index.references_for(occurrence_id)[0].component.id for occurrence_id in matches}
        if len(registration_ids) > 1:
            raise GraphSelectionError(
                f"analysis-ambiguous-registration: {qualified_name(service_type)} "
                f"matches {len(registration_ids)} registrations"
            )
        registration_id = next(iter(registration_ids))
        return index.occurrences_by_registration.get(registration_id, matches)
    return matches


def _select_root_occurrence(graph: CompiledGraph, index: GraphIndex, target: Any) -> int:
    if isinstance(target, Component):
        occurrence_id = target.occurrence_id
        if not any(root.component.occurrence_id == occurrence_id for root in graph.roots):
            raise GraphSelectionError("activation-target-not-root: activation reports require a compiled root")
        return occurrence_id
    service_type = normalize_type_alias(target)
    matches = [
        root
        for root in graph.roots
        if root.requested_type == service_type or root.component.service_type == service_type
        if root.component.name is None
    ]
    if not matches:
        raise GraphSelectionError(
            f"activation-service-not-found: {qualified_name(service_type)} is not an unambiguous compiled root"
        )
    if len(matches) > 1:
        raise GraphSelectionError(
            f"activation-ambiguous-root: {qualified_name(service_type)} matches {len(matches)} roots; use --path"
        )
    return matches[0].component.occurrence_id


def _component_for_occurrence(index: GraphIndex, occurrence_id: int) -> Component:
    references = index.references_for(occurrence_id)
    if not references:
        raise GraphSelectionError("analysis-path-not-found: component is not in this graph")
    return references[0].component


def _reverse_reachable(index: GraphIndex, selected: Iterable[int], *, include_deferred: bool) -> set[int]:
    reached = set(selected)
    queue = deque(selected)
    while queue:
        current = queue.popleft()
        for relationship in index.incoming.get(current, ()):
            if not include_deferred and relationship.phase == "deferred":
                continue
            parent_id = relationship.parent.component.occurrence_id
            if parent_id in reached:
                continue
            reached.add(parent_id)
            queue.append(parent_id)
    return reached


def _impact_roots(
    roots: Iterable[GraphRoot],
    index: GraphIndex,
    reached: set[int],
    selected: set[int],
    *,
    include_deferred: bool,
) -> tuple[ImpactRoot, ...]:
    output: list[ImpactRoot] = []
    seen: set[int] = set()
    for root in roots:
        occurrence_id = root.component.occurrence_id
        if occurrence_id not in reached or occurrence_id in seen:
            continue
        seen.add(occurrence_id)
        reference = index.primary_reference(root.component)
        witness = _witness_path(index, reference, selected, include_deferred=include_deferred)
        if not witness:
            continue
        output.append(
            ImpactRoot(
                qualified_name(root.requested_type),
                reference.path,
                witness,
                any(item.phase == "deferred" for item in witness),
                root.boundary,
            )
        )
    return tuple(sorted(output, key=lambda item: item.path))


def _witness_path(
    index: GraphIndex,
    start: GraphReference,
    selected: set[int],
    *,
    include_deferred: bool,
) -> tuple[GraphReference, ...]:
    queue: deque[tuple[GraphReference, tuple[GraphReference, ...]]] = deque([(start, (start,))])
    seen_paths: set[str] = set()
    while queue:
        current, path = queue.popleft()
        if current.path in seen_paths:
            continue
        seen_paths.add(current.path)
        if current.component.occurrence_id in selected:
            return path
        for relationship in index.outgoing.get(current.component.occurrence_id, ()):
            if relationship.parent.path != current.path:
                continue
            if not include_deferred and relationship.phase == "deferred":
                continue
            queue.append((relationship.child, (*path, relationship.child)))
    return ()


def _descendant_references(
    index: GraphIndex,
    roots: Iterable[int],
    include_deferred: bool,
) -> tuple[GraphReference, ...]:
    output: list[GraphReference] = []
    for root_id in roots:
        for start in index.references_for(root_id):
            queue: deque[GraphReference] = deque([start])
            seen_paths: set[str] = set()
            while queue:
                current = queue.popleft()
                if current.path in seen_paths:
                    continue
                seen_paths.add(current.path)
                output.append(current)
                for relationship in index.outgoing.get(current.component.occurrence_id, ()):
                    if relationship.parent.path == current.path and (include_deferred or relationship.phase == "eager"):
                        queue.append(relationship.child)
    return tuple(output)


def _sharing_key(component: Component) -> tuple[object, ...]:
    if component.cache_owner is RuntimeOwnerKind.none:
        return ("activation", component.occurrence_id)
    if component.cache_owner is RuntimeOwnerKind.singleton:
        return ("singleton", component.id, component.owner_occurrence_id)
    if component.cache_owner is RuntimeOwnerKind.scope:
        return ("scope", component.id)
    if component.cache_owner is RuntimeOwnerKind.resolution:
        return ("resolution", component.id)
    if component.cache_owner is RuntimeOwnerKind.supplied:
        return ("supplied", component.id)
    return (component.cache_owner.value, component.id, component.occurrence_id)


def _public_group_reference(index: int, paths: tuple[str, ...]) -> str:
    payload = "|".join(paths).encode()
    return f"group:{index}:{hashlib.sha256(payload).hexdigest()[:10]}"


def _cache_category(component: Component) -> str:
    if component.kind is ComponentKind.per_call_handle:
        return "deferred per-call handle"
    if component.cache_owner is RuntimeOwnerKind.none:
        return "uncached activation"
    if component.cache_owner is RuntimeOwnerKind.resolution:
        return "per-resolution cache"
    if component.cache_owner is RuntimeOwnerKind.scope:
        return "scope cache"
    if component.cache_owner is RuntimeOwnerKind.singleton:
        return "singleton owner cache"
    if component.cache_owner is RuntimeOwnerKind.supplied:
        return "supplied identity"
    return component.cache_owner.value


def _sharing_owner_label(cache_owner: RuntimeOwnerKind, layer: str, boundary: str | None) -> str:
    if cache_owner is RuntimeOwnerKind.singleton:
        area = f"boundary:{boundary}" if boundary is not None else layer
        return f"declaring singleton owner ({area})"
    if cache_owner is RuntimeOwnerKind.scope:
        return "active effective scope cache"
    if cache_owner is RuntimeOwnerKind.resolution:
        return "one resolution context"
    if cache_owner is RuntimeOwnerKind.supplied:
        return "supplied identity"
    return "no container cache"


def _sharing_conditions(component: Component, *, per_call_target: bool = False) -> tuple[str, ...]:
    if component.kind is ComponentKind.per_call_handle:
        return ("Acquiring the handle does not activate the target; each method call starts a fresh scope.",)
    if per_call_target and component.cache_owner is RuntimeOwnerKind.scope:
        return ("Shares within one method invocation only; each call starts a fresh scoped cache.",)
    if component.activation is ComponentActivation.instance:
        return (
            "This registration supplies an application-owned identity; cache eligibility does not prove that "
            "Clean IoC constructed it.",
        )
    if component.cache_owner is RuntimeOwnerKind.none:
        return ("No container cache is used; each executed edge activates independently.",)
    if component.cache_owner is RuntimeOwnerKind.resolution:
        return ("Shares within one resolution context only; provider invocations start separate contexts.",)
    if component.cache_owner is RuntimeOwnerKind.scope:
        return ("Shares through the active scope cache, including already inherited scoped values.",)
    if component.cache_owner is RuntimeOwnerKind.singleton:
        return ("Shares through the declaring singleton owner for this container or overlay build.",)
    if component.cache_owner is RuntimeOwnerKind.supplied:
        return ("The runtime supplies the value identity; no constructor execution is implied.",)
    return ("Sharing follows the compiled owner category.",)


def _reference_sort_key(reference: GraphReference) -> tuple[str, str]:
    return (reference.service, reference.path)


def _unique_components(components: Iterable[Component]) -> tuple[Component, ...]:
    by_id: dict[int, Component] = {}
    for component in components:
        by_id.setdefault(component.occurrence_id, component)
    return tuple(by_id[key] for key in sorted(by_id))


def _compare_occurrence_structure(
    components: tuple[Component, ...],
) -> tuple[ContextualCacheCertainty, tuple[str, ...]]:
    baseline = components[0]
    fields: list[str] = []
    if any(
        tuple(child.id for child in component.dependencies) != tuple(child.id for child in baseline.dependencies)
        for component in components[1:]
    ):
        fields.append("selected_dependencies")
    if any(
        tuple((child.id, child.position) for child in component.decorators)
        != tuple((child.id, child.position) for child in baseline.decorators)
        for component in components[1:]
    ):
        fields.append("decorator_order")
    if any(
        tuple(child.id for child in component.pre_configurations)
        != tuple(child.id for child in baseline.pre_configurations)
        for component in components[1:]
    ):
        fields.append("pre_configuration_order")
    if any(
        (component.cache_owner, component.cleanup_owner, component.owner_occurrence_id)
        != (baseline.cache_owner, baseline.cleanup_owner, baseline.owner_occurrence_id)
        for component in components[1:]
    ):
        fields.append("ownership_structure")
    if not fields:
        return ContextualCacheCertainty.equivalent_structure, ()
    if any(child.kind is ComponentKind.value for component in components for child in component.dependencies):
        return ContextualCacheCertainty.unknown_values, tuple(fields)
    return ContextualCacheCertainty.different, tuple(fields)


def _structure_signature(component: Component) -> tuple[object, ...]:
    return (
        tuple((child.argument, child.id, child.kind.value, child.lifespan) for child in component.dependencies),
        tuple((child.id, child.position) for child in component.decorators),
        tuple(child.id for child in component.pre_configurations),
        component.cache_owner.value,
        component.cleanup_owner.value,
    )


def _scenario_assumptions(scenario: ActivationScenario) -> tuple[str, ...]:
    base = ("Static analysis only; runtime cache and provision state are not inspected.",)
    if scenario is ActivationScenario.cold:
        return (
            *base,
            "relevant caches are empty",
            "shared pre-configurations have not completed",
            "no inherited scoped values are assumed",
        )
    if scenario is ActivationScenario.warm_singletons:
        return (
            *base,
            "relevant singleton caches and shared pre-configurations are complete",
            "scoped and per-resolution caches remain cold",
        )
    return (
        *base,
        "relevant singleton and scoped caches are populated",
        "per-resolution caches remain cold",
        "deferred provider calls are not assumed to happen",
    )


def _scenario_skips(component: Component, scenario: ActivationScenario) -> bool:
    if scenario is ActivationScenario.warm_singletons and component.cache_owner is RuntimeOwnerKind.singleton:
        return True
    if scenario is ActivationScenario.warm_scope and component.cache_owner in (
        RuntimeOwnerKind.singleton,
        RuntimeOwnerKind.scope,
    ):
        return True
    return False


def _collect_obligation(
    reference: GraphReference,
    obligations: list[ActivationObligation],
    unknown: list[str],
) -> None:
    component = reference.component
    if component.kind is ComponentKind.scope_slot:
        obligations.append(
            ActivationObligation(
                "scope_slot",
                reference.phase,
                reference.path,
                reference.service,
                "runtime scope value must be provided",
            )
        )
    if component.requires_async:
        obligations.append(
            ActivationObligation(
                "async_requirement",
                reference.phase,
                reference.path,
                reference.service,
                "this compiled operation requires asynchronous activation",
            )
        )
    if component.kind is ComponentKind.pre_configuration:
        obligations.append(
            ActivationObligation(
                "initializer",
                reference.phase,
                reference.path,
                reference.service,
                "pre-configuration runs before core activation on first use",
            )
        )
    if component.manages_cleanup:
        obligations.append(
            ActivationObligation(
                "resource",
                reference.phase,
                reference.path,
                reference.service,
                f"cleanup is owned by {component.cleanup_owner.value}",
            )
        )
    if component.kind is ComponentKind.runtime_context:
        obligations.append(
            ActivationObligation(
                "runtime_context",
                reference.phase,
                reference.path,
                reference.service,
                "runtime context edge is supplied by the resolver",
            )
        )
        unknown.append(f"{reference.path}: ResolutionContext may perform declared runtime requests")
