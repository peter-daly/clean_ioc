"""Activation-free reverse dependency analysis for compiled graphs.

This module deliberately indexes compiled occurrences rather than registrations:
one registration can appear at several places in a plan, and a semantic path is
the stable public identity used in reports.
"""

from __future__ import annotations

import json
from collections import defaultdict, deque
from dataclasses import dataclass
from typing import Any, Iterable, Mapping

from .components import Component, ComponentKind
from .type_aliases import normalize_type_alias


@dataclass(frozen=True, slots=True)
class GraphReference:
    """A graph-local occurrence at one deterministic semantic path."""

    path: str
    occurrence_id: int
    registration_id: str
    service: str
    implementation: str
    name: str | None
    boundary: str | None
    _component: Component

    @property
    def component(self) -> Component:
        """The frozen component occurrence represented by this reference."""

        return self._component

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "service": self.service,
            "implementation": self.implementation,
            "name": self.name,
            "boundary": self.boundary,
        }


@dataclass(frozen=True, slots=True)
class GraphRelationship:
    """One explicit compiled parent-to-child relationship."""

    parent: GraphReference
    child: GraphReference
    kind: str
    argument: str | None
    order: int
    deferred: bool = False
    source_boundary: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "parent": self.parent.path,
            "child": self.child.path,
            "kind": self.kind,
            "argument": self.argument,
            "order": self.order,
            "deferred": self.deferred,
            "source_boundary": self.source_boundary,
        }


@dataclass(frozen=True, slots=True)
class DependencyImpact:
    """A bounded, deterministic reverse-dependency summary."""

    targets: tuple[GraphReference, ...]
    direct_consumers: tuple[GraphRelationship, ...]
    affected_roots: tuple[GraphReference, ...]
    affected_entrypoints: tuple[GraphReference, ...]
    witness_paths: Mapping[str, tuple[str, ...]]
    include_deferred: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "targets": [item.to_dict() for item in self.targets],
            "direct_consumers": [item.to_dict() for item in self.direct_consumers],
            "affected_roots": [item.to_dict() for item in self.affected_roots],
            "affected_entrypoints": [item.to_dict() for item in self.affected_entrypoints],
            "witness_paths": {key: list(value) for key, value in sorted(self.witness_paths.items())},
            "include_deferred": self.include_deferred,
        }

    def to_json(self, *, indent: int | None = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, sort_keys=True)

    def to_text(self) -> str:
        lines = ["Impact analysis:"]
        lines.extend(f"  Target: {item.path}" for item in self.targets)
        lines.append("  Direct consumers:")
        lines.extend(f"    {item.parent.service} ({item.kind})" for item in self.direct_consumers)
        lines.append("  Affected roots:")
        lines.extend(f"    {item.path}" for item in self.affected_roots)
        if self.affected_entrypoints:
            lines.append("  Affected entry points:")
            lines.extend(f"    {item.path}" for item in self.affected_entrypoints)
        return "\n".join(lines)


@dataclass(frozen=True, slots=True)
class GraphSlice:
    """A bounded projection of compiled facts, with honest truncation state."""

    nodes: tuple[GraphReference, ...]
    relationships: tuple[GraphRelationship, ...]
    max_paths: int
    returned_paths: int
    truncated: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "nodes": [item.to_dict() for item in self.nodes],
            "relationships": [item.to_dict() for item in self.relationships],
            "max_paths": self.max_paths,
            "returned_paths": self.returned_paths,
            "truncated": self.truncated,
        }

    def to_json(self, *, indent: int | None = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, sort_keys=True)

    def to_mermaid(self) -> str:
        from html import escape

        ids = {item.path: f"n{index}" for index, item in enumerate(self.nodes)}
        lines = ["flowchart TD"]
        for item in self.nodes:
            label = escape(f"{item.service}\\n{item.path}", quote=True)
            lines.append(f'    {ids[item.path]}["{label}"]')
        for edge in self.relationships:
            label = edge.kind + (" (deferred)" if edge.deferred else "")
            lines.append(f"    {ids[edge.parent.path]} -->|{label}| {ids[edge.child.path]}")
        return "\n".join(lines)


class GraphIndex:
    """Lazy immutable index over one ``CompiledGraph``'s frozen plan trees."""

    def __init__(self, graph: Any) -> None:
        # Importing tooling here avoids a module-import cycle while reusing its
        # canonical qualified-name renderer for all public paths and labels.
        from .tooling import qualified_name

        self.references: dict[str, GraphReference] = {}
        self.occurrences: dict[int, list[GraphReference]] = defaultdict(list)
        self.registrations: dict[str, list[GraphReference]] = defaultdict(list)
        self.outgoing: dict[str, list[GraphRelationship]] = defaultdict(list)
        self.incoming: dict[str, list[GraphRelationship]] = defaultdict(list)
        self.root_paths: set[str] = set()
        self.entrypoint_paths: set[str] = set()

        selected_entrypoints = {root.component.occurrence_id for root in graph.entrypoints}
        counters: dict[tuple[str, str | None], int] = defaultdict(int)
        for root in graph.roots:
            requested = qualified_name(root.requested_type)
            selector = (requested, root.component.name)
            candidate = counters[selector]
            counters[selector] += 1
            name = root.component.name or "default"
            path = f"root:{requested}:{name}:{candidate}"
            self.root_paths.add(path)
            if root.component.occurrence_id in selected_entrypoints:
                self.entrypoint_paths.add(path)
            self._visit(root.component, path, None, None, 0, qualified_name)

        for values in (
            *self.occurrences.values(),
            *self.registrations.values(),
            *self.outgoing.values(),
            *self.incoming.values(),
        ):
            values.sort(
                key=lambda item: item.path if isinstance(item, GraphReference) else (item.parent.path, item.child.path)
            )

    def _reference(self, component: Component, path: str, qualified_name: Any) -> GraphReference:
        reference = GraphReference(
            path=path,
            occurrence_id=component.occurrence_id,
            registration_id=component.id,
            service=qualified_name(component.service_type),
            implementation=qualified_name(component.implementation_type),
            name=component.name,
            boundary=component.boundary,
            _component=component,
        )
        self.references[path] = reference
        self.occurrences[component.occurrence_id].append(reference)
        self.registrations[component.id].append(reference)
        return reference

    def _visit(
        self,
        component: Component,
        path: str,
        parent: GraphReference | None,
        relationship: tuple[str, str | None, bool] | None,
        order: int,
        qualified_name: Any,
    ) -> None:
        reference = self._reference(component, path, qualified_name)
        if parent is not None and relationship is not None:
            kind, argument, deferred = relationship
            edge = GraphRelationship(
                parent,
                reference,
                kind,
                argument,
                order,
                deferred,
                reference.boundary if parent.boundary != reference.boundary else None,
            )
            self.outgoing[parent.path].append(edge)
            self.incoming[reference.path].append(edge)
        for index, child in enumerate(component.dependencies):
            deferred = component.kind is ComponentKind.provider
            kind = "deferred_target" if deferred else "dependency"
            self._visit(
                child,
                f"{path}/dependency:{child.argument or index}:{index}",
                reference,
                (kind, child.argument, deferred),
                index,
                qualified_name,
            )
        for index, child in enumerate(component.pre_configurations):
            self._visit(
                child,
                f"{path}/pre_configuration:{index}",
                reference,
                ("pre_configuration", child.argument, False),
                index,
                qualified_name,
            )
        for index, child in enumerate(component.decorators):
            self._visit(
                child,
                f"{path}/decorator:{index}",
                reference,
                ("decorator", child.argument, False),
                index,
                qualified_name,
            )

    def select(self, subject: Any, *, match: str, name: str | None = None) -> tuple[GraphReference, ...]:
        if match not in ("occurrence", "registration"):
            raise ValueError("impact-invalid-match: expected 'occurrence' or 'registration'")
        if isinstance(subject, GraphReference):
            candidates = [subject]
        elif isinstance(subject, Component):
            candidates = list(self.occurrences.get(subject.occurrence_id, ()))
        else:
            normalized = normalize_type_alias(subject)
            candidates = [
                reference
                for reference in self.references.values()
                if reference.component.service_type == normalized
                or reference.component.declared_service_type == normalized
            ]
        if name is not None:
            candidates = [item for item in candidates if item.name == name]
        if not candidates:
            raise ValueError("impact-target-not-found: target is not in the compiled graph")
        if match == "occurrence":
            occurrences = {item.occurrence_id for item in candidates}
            if len(occurrences) != 1:
                raise ValueError("impact-ambiguous-target: select an exact occurrence path")
            return tuple(candidates)
        registrations = {item.registration_id for item in candidates}
        if len(registrations) != 1:
            raise ValueError("impact-ambiguous-target: select a name or exact occurrence path")
        return tuple(candidates)

    def dependents(
        self, subject: Any, *, match: str = "occurrence", name: str | None = None, include_deferred: bool = False
    ) -> DependencyImpact:
        targets = self.select(subject, match=match, name=name)
        target_paths = {item.path for item in targets}
        direct = tuple(
            edge
            for path in sorted(target_paths)
            for edge in self.incoming.get(path, ())
            if include_deferred or not edge.deferred
        )
        seen = set(target_paths)
        queue: deque[tuple[str, tuple[str, ...]]] = deque((path, (path,)) for path in sorted(target_paths))
        witnesses: dict[str, tuple[str, ...]] = {}
        roots: set[str] = set()
        while queue:
            child, path = queue.popleft()
            if child in self.root_paths:
                roots.add(child)
                witnesses.setdefault(child, tuple(reversed(path)))
            for edge in self.incoming.get(child, ()):
                if edge.deferred and not include_deferred:
                    continue
                parent = edge.parent.path
                if parent not in seen:
                    seen.add(parent)
                    queue.append((parent, (*path, parent)))
        root_refs = tuple(self.references[path] for path in sorted(roots))
        entrypoints = tuple(item for item in root_refs if item.path in self.entrypoint_paths)
        return DependencyImpact(targets, direct, root_refs, entrypoints, witnesses, include_deferred)

    def paths_between(
        self, root: Any, dependency: Any, *, max_paths: int = 100, include_deferred: bool = True
    ) -> GraphSlice:
        if max_paths < 1:
            raise ValueError("impact-invalid-path-limit: max_paths must be at least 1")
        roots = self.select(root, match="occurrence")
        targets = {item.path for item in self.select(dependency, match="occurrence")}
        found: list[tuple[GraphRelationship, ...]] = []
        truncated = False
        for root_ref in roots:
            stack: list[tuple[str, tuple[GraphRelationship, ...], frozenset[str]]] = [
                (root_ref.path, (), frozenset((root_ref.path,)))
            ]
            while stack:
                current, edges, seen = stack.pop()
                if current in targets:
                    if len(found) == max_paths:
                        truncated = True
                        continue
                    found.append(edges)
                    continue
                for edge in reversed(self.outgoing.get(current, ())):
                    if (include_deferred or not edge.deferred) and edge.child.path not in seen:
                        stack.append((edge.child.path, (*edges, edge), seen | frozenset((edge.child.path,))))
        relationships = tuple(dict.fromkeys(edge for path in found for edge in path))
        nodes = {item.path: item for edge in relationships for item in (edge.parent, edge.child)}
        nodes.update({item.path: item for item in roots})
        return GraphSlice(tuple(nodes[path] for path in sorted(nodes)), relationships, max_paths, len(found), truncated)

    def shared_dependencies(
        self, first: Any, second: Any, *, match: str = "registration", include_deferred: bool = True
    ) -> tuple[GraphReference, ...]:
        first_refs = self.select(first, match="occurrence")
        second_refs = self.select(second, match="occurrence")

        def reachable(starts: Iterable[GraphReference]) -> dict[str, GraphReference]:
            seen: dict[str, GraphReference] = {}
            queue = deque(item.path for item in starts)
            while queue:
                path = queue.popleft()
                if path in seen:
                    continue
                seen[path] = self.references[path]
                queue.extend(
                    edge.child.path for edge in self.outgoing.get(path, ()) if include_deferred or not edge.deferred
                )
            return seen

        left, right = reachable(first_refs), reachable(second_refs)
        if match == "occurrence":
            return tuple(left[path] for path in sorted(left.keys() & right.keys()))
        left_ids = {item.registration_id for item in left.values()}
        right_ids = {item.registration_id for item in right.values()}
        return tuple(
            next(item for item in left.values() if item.registration_id == registration)
            for registration in sorted(left_ids & right_ids)
        )
