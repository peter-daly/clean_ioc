"""Build reports, graph rendering, and stable compiler manifests."""

from __future__ import annotations

import ast
import hashlib
import inspect
import json
import textwrap
from dataclasses import dataclass, field, replace
from enum import Enum
from html import escape
from types import MappingProxyType
from typing import Any, Callable, Iterable, Iterator, Mapping, TypeAlias, TypeVar, get_args, get_origin, overload

from .components import (
    Component,
    ComponentActivation,
    ComponentFilter,
    ComponentKind,
    RuntimeOwnerKind,
    default_component_filter,
)


class IssueSeverity(str, Enum):
    """Severity assigned to a compiler finding."""

    error = "error"
    warning = "warning"


@dataclass(frozen=True, slots=True)
class SourceLocation:
    """Best-effort, privacy-safe source location for a composition definition."""

    module: str | None
    symbol: str | None
    path: str | None
    line: int | None

    def to_dict(self) -> dict[str, object]:
        return {
            "module": self.module,
            "symbol": self.symbol,
            "path": self.path,
            "line": self.line,
        }


@dataclass(frozen=True, slots=True)
class DefinitionOrigin:
    """Where and in which composition layer a definition was declared."""

    kind: str
    location: SourceLocation | None
    layer: str
    bundle_path: tuple[str, ...]
    definition_id: str | None
    assembly: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "kind": self.kind,
            "location": None if self.location is None else self.location.to_dict(),
            "layer": self.layer,
            "bundle_path": list(self.bundle_path),
            "definition_id": self.definition_id,
            "assembly": self.assembly,
        }


class DecisionOutcome(str, Enum):
    """Outcome of considering one definition for a compiled selection."""

    selected = "selected"
    rejected = "rejected"
    included = "included"


@dataclass(frozen=True, slots=True)
class CandidateDecision:
    """One recorded compiler decision, with no configured or runtime values."""

    component_id: str
    outcome: DecisionOutcome
    reason_codes: tuple[str, ...]
    reason: str
    origin: DefinitionOrigin

    def to_dict(self) -> dict[str, object]:
        return {
            "component_id": self.component_id,
            "outcome": self.outcome.value,
            "reason_codes": list(self.reason_codes),
            "reason": self.reason,
            "origin": self.origin.to_dict(),
        }


@dataclass(frozen=True, slots=True)
class CompilationExplanation:
    """Immutable explanation of one root or occurrence-level compiler choice."""

    subject: str
    path: tuple[str, ...]
    selected: tuple[CandidateDecision, ...]
    rejected: tuple[CandidateDecision, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "subject": self.subject,
            "path": list(self.path),
            "selected": [decision.to_dict() for decision in self.selected],
            "rejected": [decision.to_dict() for decision in self.rejected],
        }

    def to_json(self, *, indent: int | None = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, sort_keys=True)

    def to_text(self) -> str:
        lines = [f"Explain {self.subject}"]
        if self.path:
            lines.append(f"Path: {'/'.join(self.path)}")

        def add_group(label: str, decisions: tuple[CandidateDecision, ...]) -> None:
            lines.append(f"{label}:")
            if not decisions:
                lines.append("- none")
                return
            for decision in decisions:
                codes = ", ".join(decision.reason_codes)
                origin = decision.origin
                location = origin.location
                declared = origin.kind
                if location is not None and location.path is not None:
                    suffix = f":{location.line}" if location.line is not None else ""
                    declared = f"{declared} at {location.path}{suffix}"
                if origin.bundle_path:
                    declared = f"{declared} via {' > '.join(origin.bundle_path)}"
                if origin.assembly is not None:
                    declared = f"{declared} in assembly {origin.assembly}"
                lines.append(
                    f"- {decision.component_id} [{decision.outcome.value}; {codes}]: "
                    f"{decision.reason} ({declared}, {origin.layer})"
                )

        add_group("Selected", self.selected)
        add_group("Rejected", self.rejected)
        return "\n".join(lines)

    def __str__(self) -> str:
        return self.to_text()


@dataclass(frozen=True, slots=True)
class _CandidateRecord:
    """Private compiler-to-tooling record used to answer root queries."""

    component: Component
    decision: CandidateDecision
    eligible: bool


@dataclass(frozen=True, slots=True)
class BuildIssue:
    """One structured compiler error or warning."""

    code: str
    severity: IssueSeverity
    message: str
    root: str | None = None
    path: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "severity": self.severity.value,
            "message": self.message,
            "root": self.root,
            "path": list(self.path),
        }

    def __str__(self) -> str:
        location = " -> ".join(self.path)
        suffix = f" ({location})" if location else ""
        return f"[{self.code}] {self.message}{suffix}"


@dataclass(frozen=True, slots=True)
class BuildReport:
    """Immutable result of validating and compiling a component plan."""

    issues: tuple[BuildIssue, ...] = ()
    checked_roots: int = 0

    @property
    def errors(self) -> tuple[BuildIssue, ...]:
        return tuple(issue for issue in self.issues if issue.severity is IssueSeverity.error)

    @property
    def warnings(self) -> tuple[BuildIssue, ...]:
        return tuple(issue for issue in self.issues if issue.severity is IssueSeverity.warning)

    @property
    def is_valid(self) -> bool:
        return not self.errors

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "valid": self.is_valid,
            "checked_roots": self.checked_roots,
            "issues": [issue.to_dict() for issue in self.issues],
        }

    def to_json(self, *, indent: int | None = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, sort_keys=True)

    def to_text(self) -> str:
        if self.is_valid:
            noun = "root" if self.checked_roots == 1 else "roots"
            heading = f"Container is valid ({self.checked_roots} {noun} checked)."
        else:
            count = len(self.errors)
            noun = "error" if count == 1 else "errors"
            heading = f"Container build failed with {count} {noun}."
        if not self.issues:
            return heading
        return "\n".join((heading, *(f"- {issue}" for issue in self.issues)))

    def __str__(self) -> str:
        return self.to_text()


@dataclass(frozen=True, slots=True)
class OwnershipRecord:
    """One redacted ownership proof for a compiled component occurrence."""

    component: Component
    path: tuple[str, ...]
    cache_owner: RuntimeOwnerKind
    cleanup_owner: RuntimeOwnerKind
    owner_component: Component | None
    reason: str

    def to_dict(self) -> dict[str, Any]:
        owner = self.owner_component
        return {
            "path": list(self.path),
            "service": qualified_name(self.component.service_type),
            "assembly": self.component.assembly,
            "implementation": _implementation_name(self.component),
            "kind": self.component.kind.value,
            "lifespan": self.component.lifespan,
            "cache_owner": self.cache_owner.value,
            "cleanup_owner": self.cleanup_owner.value,
            "owner_component": (
                None
                if owner is None
                else {
                    "service": qualified_name(owner.service_type),
                    "implementation": _implementation_name(owner),
                    "kind": owner.kind.value,
                }
            ),
            "reason": self.reason,
        }


@dataclass(frozen=True, slots=True)
class OwnershipReport:
    """Frozen, value-free proof of the owners selected by compilation."""

    records: tuple[OwnershipRecord, ...]
    issues: tuple[BuildIssue, ...] = ()

    @property
    def is_valid(self) -> bool:
        return not any(issue.severity is IssueSeverity.error for issue in self.issues)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "valid": self.is_valid,
            "records": [record.to_dict() for record in self.records],
            "issues": [issue.to_dict() for issue in self.issues],
        }

    def to_json(self, *, indent: int | None = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, sort_keys=True)

    def to_text(self) -> str:
        lines = [
            f"Ownership is {'valid' if self.is_valid else 'invalid'} "
            f"({len(self.records)} compiled occurrence{'s' if len(self.records) != 1 else ''})."
        ]
        for record in self.records:
            owner = record.cleanup_owner.value
            if record.owner_component is not None:
                owner = f"{owner} via {qualified_name(record.owner_component.service_type)}"
            area = record.component.assembly or "root"
            lines.append(
                f"- {' -> '.join(record.path)} [assembly={area}]: "
                f"cache={record.cache_owner.value}, cleanup={owner}; {record.reason}"
            )
        lines.extend(f"- {issue}" for issue in self.issues)
        return "\n".join(lines)

    def __str__(self) -> str:
        return self.to_text()


ValidationRule: TypeAlias = Callable[["ValidationContext"], Iterable[BuildIssue]]


@dataclass(frozen=True, slots=True)
class TypeAst:
    """Source and parsed class definition for one inspectable Python type."""

    filename: str
    first_line: int
    source: str
    node: ast.ClassDef


def qualified_name(value: Any) -> str:
    """Return a deterministic display identity without using object reprs."""

    if value is None or value is type(None):
        return "None"
    if isinstance(value, TypeVar):
        return f"TypeVar({value.__name__})"
    origin = get_origin(value)
    arguments = get_args(value)
    if origin is not None:
        rendered = ", ".join(qualified_name(argument) for argument in arguments)
        return f"{qualified_name(origin)}[{rendered}]"
    module = getattr(value, "__module__", None)
    qualname = getattr(value, "__qualname__", None) or getattr(value, "__name__", None)
    if qualname is not None:
        return qualname if module in (None, "builtins") else f"{module}.{qualname}"
    text = str(value).replace("typing.", "")
    if " at 0x" not in text:
        return text
    value_type = type(value)
    return f"{value_type.__module__}.{value_type.__qualname__}"


@dataclass(frozen=True, slots=True)
class GraphRoot:
    """One compiled root occurrence and the request that selects it."""

    requested_type: Any
    component: Component
    area: str | None = None

    @property
    def assembly(self) -> str | None:
        return self.component.assembly


def _issue_path_name(component: Component) -> str:
    if component.kind in (ComponentKind.decorator, ComponentKind.pre_configuration):
        return qualified_name(component.implementation)
    return qualified_name(component.service_type)


@dataclass(frozen=True, slots=True)
class GraphVisit:
    """One occurrence and its path while walking a compiled graph."""

    root: GraphRoot
    components: tuple[Component, ...]

    def __post_init__(self) -> None:
        if not self.components:
            raise ValueError("A graph visit requires at least one component")

    @property
    def component(self) -> Component:
        return self.components[-1]

    @property
    def root_name(self) -> str:
        return qualified_name(self.root.requested_type)

    @property
    def assembly(self) -> str | None:
        """The defining assembly of the visited occurrence."""

        return self.component.assembly

    @property
    def path(self) -> tuple[str, ...]:
        return tuple(_issue_path_name(component) for component in self.components)

    def issue(
        self,
        code: str,
        message: str,
        *,
        severity: IssueSeverity = IssueSeverity.error,
    ) -> BuildIssue:
        """Create a structured issue located at this graph occurrence."""

        return BuildIssue(
            code=code,
            severity=severity,
            message=message,
            root=self.root_name,
            path=self.path,
        )


def _implementation_name(component: Component) -> str:
    if component.activation in (ComponentActivation.instance, ComponentActivation.supplied):
        return qualified_name(component.implementation_type)
    return qualified_name(component.implementation)


def _component_description(component: Component) -> str:
    service = qualified_name(component.service_type)
    implementation = _implementation_name(component)
    target = service if implementation == service else f"{service} -> {implementation}"
    details = [component.kind.value, component.activation.value, component.lifespan]
    if component.name is not None:
        details.append(f'name="{component.name}"')
    if component.position is not None:
        details.append(f"position={component.position}")
    if component.requires_async:
        details.append("async")
    if component.manages_cleanup:
        details.append("cleanup")
    if component.provider_mode is not None:
        details.append(f"provider={component.provider_mode}")
    if component.assembly is not None:
        details.append(f"assembly={component.assembly}")
    return f"{target} [{', '.join(details)}]"


def _dependency_relationship(component: Component) -> str:
    parent = component.parent
    boundary = ""
    if parent is not None and parent.assembly != component.assembly:
        source = component.assembly or "root"
        boundary = f" via boundary:{source}"
    if component.parent is not None and component.parent.kind is ComponentKind.provider:
        return f"provides on demand{boundary}"
    if component.argument is None:
        return f"depends on{boundary}"
    return f"depends on: {component.argument}{boundary}"


_DECORATOR_RELATIONSHIP = "decorated by"
_PRE_CONFIGURATION_RELATIONSHIP = "pre-configured by"


def _node_dict(
    component: Component,
    path: str,
    order: int,
    owner_paths: dict[int, str],
) -> dict[str, Any]:
    owner_paths[component.occurrence_id] = path
    metadata: dict[str, Any] = {
        "path": path,
        "order": order,
        "argument": component.argument,
        "assembly": component.assembly,
        "source_assembly": (
            component.assembly
            if component.parent is not None and component.parent.assembly != component.assembly
            else None
        ),
        "service": qualified_name(component.service_type),
        "implementation": _implementation_name(component),
        "implementation_type": qualified_name(component.implementation_type),
        "kind": component.kind.value,
        "activation": component.activation.value,
        "lifespan": component.lifespan,
        "name": component.name,
        "position": component.position,
        "tags": [
            {"name": tag.name, "value": tag.value}
            for tag in sorted(component.tags, key=lambda item: (item.name, item.value or ""))
        ],
        "requires_async": component.requires_async,
        "manages_cleanup": component.manages_cleanup,
        "cache_owner": component.cache_owner.value,
        "cleanup_owner": component.cleanup_owner.value,
        "owner_path": (
            None if component.owner_occurrence_id is None else owner_paths.get(component.owner_occurrence_id)
        ),
    }
    if component.kind is ComponentKind.provider:
        metadata["provider_mode"] = component.provider_mode
        metadata["deferred_target"] = (
            qualified_name(component.dependencies[0].service_type) if component.dependencies else None
        )
    metadata["dependencies"] = [
        _node_dict(
            child,
            f"{path}/dependency:{child.argument or index}:{index}",
            index,
            owner_paths,
        )
        for index, child in enumerate(component.dependencies)
    ]
    metadata["decorators"] = [
        _node_dict(decorator, f"{path}/decorator:{index}", index, owner_paths)
        for index, decorator in enumerate(component.decorators)
    ]
    metadata["pre_configurations"] = [
        _node_dict(configuration, f"{path}/pre_configuration:{index}", index, owner_paths)
        for index, configuration in enumerate(component.pre_configurations)
    ]
    return metadata


@dataclass(frozen=True, slots=True)
class GraphChange:
    """One manifest node whose semantic metadata changed."""

    path: str
    before: dict[str, Any]
    after: dict[str, Any]
    category: str = "component-changed"
    risk: str = "unknown"

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "before": self.before,
            "after": self.after,
            "category": self.category,
            "risk": self.risk,
        }


@dataclass(frozen=True, slots=True)
class GraphDiff:
    """Semantic differences between two graph manifests."""

    added: tuple[str, ...] = ()
    removed: tuple[str, ...] = ()
    changed: tuple[GraphChange, ...] = ()
    semantic_changes: tuple[GraphChange, ...] = ()

    @property
    def is_empty(self) -> bool:
        return not (self.added or self.removed or self.changed or self.semantic_changes)

    def to_dict(self) -> dict[str, Any]:
        return {
            "same": self.is_empty,
            "added": list(self.added),
            "removed": list(self.removed),
            "changed": [change.to_dict() for change in self.changed],
            "semantic_changes": [change.to_dict() for change in self.semantic_changes],
        }

    def to_json(self, *, indent: int | None = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, sort_keys=True)

    def to_text(self) -> str:
        if self.is_empty:
            return "Dependency graph is unchanged."
        lines = ["Dependency graph changed:"]
        lines.extend(f"+ {path}" for path in self.added)
        lines.extend(f"- {path}" for path in self.removed)
        lines.extend(
            (
                f"~ {change.path}"
                if change.category == "component-changed"
                else f"! {change.category} [{change.risk}] {change.path}"
            )
            for change in self.changed
        )
        return "\n".join(lines)

    def __str__(self) -> str:
        return self.to_text()


def _flatten_nodes(roots: Iterable[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    flattened: dict[str, dict[str, Any]] = {}

    def visit(node: dict[str, Any]) -> None:
        children = {key: node.get(key, []) for key in ("dependencies", "decorators", "pre_configurations")}
        flattened[node["path"]] = {
            key: value for key, value in node.items() if key not in ("dependencies", "decorators", "pre_configurations")
        }
        for values in children.values():
            for child in values:
                visit(child)

    for root in roots:
        visit(root)
    return flattened


@dataclass(frozen=True, slots=True)
class GraphManifest:
    """Versioned and deterministic serialized component graph."""

    data: dict[str, Any]

    def __post_init__(self) -> None:
        if self.data.get("schema_version") not in (1, 2, 3):
            raise ValueError(f"Unsupported graph manifest schema {self.data.get('schema_version')!r}")

    @property
    def fingerprint(self) -> str:
        payload = json.dumps(self.data, separators=(",", ":"), sort_keys=True).encode()
        return hashlib.sha256(payload).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        return json.loads(json.dumps(self.data))

    def to_json(self, *, indent: int | None = 2) -> str:
        return json.dumps(self.data, indent=indent, sort_keys=True)

    @classmethod
    def from_json(cls, value: str) -> GraphManifest:
        data = json.loads(value)
        if not isinstance(data, dict):
            raise ValueError("A graph manifest must be a JSON object")
        return cls(data)

    def diff(self, baseline: GraphManifest) -> GraphDiff:
        current_nodes = _flatten_nodes(self.data.get("roots", ()))
        baseline_nodes = _flatten_nodes(baseline.data.get("roots", ()))
        current_paths = set(current_nodes)
        baseline_paths = set(baseline_nodes)
        shared = current_paths & baseline_paths
        semantic: list[GraphChange] = []
        current_schema = self.data.get("schema_version")
        baseline_schema = baseline.data.get("schema_version")
        if current_schema in (1, 2) or baseline_schema in (1, 2):
            if self.data.get("assemblies") or baseline.data.get("assemblies"):
                semantic.append(
                    GraphChange(
                        "assemblies",
                        {"schema_version": baseline_schema},
                        {"schema_version": current_schema},
                        "assembly-classification-unknown",
                        "unknown",
                    )
                )
        else:
            current_assemblies = {item["name"]: item for item in self.data.get("assemblies", ()) if "name" in item}
            baseline_assemblies = {item["name"]: item for item in baseline.data.get("assemblies", ()) if "name" in item}
            for name in sorted(current_assemblies.keys() - baseline_assemblies.keys()):
                item = current_assemblies[name]
                risk = "low" if not item.get("uses") and not item.get("exposures") else "medium"
                semantic.append(GraphChange(f"assembly:{name}", {}, item, "assembly-added", risk))
            for name in sorted(baseline_assemblies.keys() - current_assemblies.keys()):
                semantic.append(
                    GraphChange(f"assembly:{name}", baseline_assemblies[name], {}, "assembly-removed", "high")
                )
            for name in sorted(current_assemblies.keys() & baseline_assemblies.keys()):
                current = current_assemblies[name]
                previous = baseline_assemblies[name]
                current_uses = {json.dumps(item, sort_keys=True) for item in current.get("uses", ())}
                previous_uses = {json.dumps(item, sort_keys=True) for item in previous.get("uses", ())}
                for value in sorted(current_uses - previous_uses):
                    semantic.append(
                        GraphChange(
                            f"assembly:{name}:use",
                            {},
                            json.loads(value),
                            "assembly-use-added",
                            "high",
                        )
                    )
                for value in sorted(previous_uses - current_uses):
                    semantic.append(
                        GraphChange(
                            f"assembly:{name}:use",
                            json.loads(value),
                            {},
                            "assembly-use-removed",
                            "high",
                        )
                    )
                current_exposures = {json.dumps(item, sort_keys=True) for item in current.get("exposures", ())}
                previous_exposures = {json.dumps(item, sort_keys=True) for item in previous.get("exposures", ())}
                for value in sorted(current_exposures - previous_exposures):
                    semantic.append(
                        GraphChange(
                            f"assembly:{name}:exposure",
                            {},
                            json.loads(value),
                            "assembly-exposure-added",
                            "medium",
                        )
                    )
                for value in sorted(previous_exposures - current_exposures):
                    semantic.append(
                        GraphChange(
                            f"assembly:{name}:exposure",
                            json.loads(value),
                            {},
                            "assembly-exposure-removed",
                            "high",
                        )
                    )
            for path in sorted(shared):
                before_assembly = baseline_nodes[path].get("assembly")
                after_assembly = current_nodes[path].get("assembly")
                if before_assembly != after_assembly:
                    semantic.append(
                        GraphChange(
                            path,
                            {"assembly": before_assembly},
                            {"assembly": after_assembly},
                            "assembly-component-moved",
                            "high",
                        )
                    )

            def boundary_bypasses(data: dict[str, Any]) -> dict[str, dict[str, Any]]:
                contracts = {item["name"]: item for item in data.get("assemblies", ()) if "name" in item}
                bypasses: dict[str, dict[str, Any]] = {}

                def identity(node: dict[str, Any]) -> tuple[Any, Any, str]:
                    tags = json.dumps(node.get("tags", ()), sort_keys=True)
                    return node.get("service"), node.get("name"), tags

                def declared(item: dict[str, Any], node: dict[str, Any]) -> bool:
                    service, name, tags = identity(node)
                    return (
                        item.get("service") == service
                        and item.get("name") == name
                        and json.dumps(item.get("tags", ()), sort_keys=True) == tags
                    )

                def visit(node: dict[str, Any], consumer: str | None) -> None:
                    source = node.get("assembly")
                    if consumer != source and consumer is not None:
                        uses = contracts.get(consumer, {}).get("uses", ())
                        expected_source = source or "root"
                        if not any(item.get("source") == expected_source and declared(item, node) for item in uses):
                            bypasses[node.get("path", "unknown")] = node
                    elif consumer is None and source is not None:
                        exposures = contracts.get(source, {}).get("exposures", ())
                        if not any(declared(item, node) for item in exposures):
                            bypasses[node.get("path", "unknown")] = node
                    for key in ("dependencies", "decorators", "pre_configurations"):
                        for child in node.get(key, ()):
                            visit(child, source)

                for root in data.get("roots", ()):
                    # A graph root is a visibility projection, not a dependency
                    # edge; validate crossings below that root only.
                    for key in ("dependencies", "decorators", "pre_configurations"):
                        for child in root.get(key, ()):
                            visit(child, root.get("assembly"))
                return bypasses

            current_bypasses = boundary_bypasses(self.data)
            baseline_bypasses = boundary_bypasses(baseline.data)
            for path in sorted(current_bypasses.keys() - baseline_bypasses.keys()):
                semantic.append(
                    GraphChange(
                        path,
                        {},
                        current_bypasses[path],
                        "assembly-boundary-bypassed",
                        "critical",
                    )
                )

        node_changes = tuple(
            GraphChange(path, baseline_nodes[path], current_nodes[path])
            for path in sorted(shared)
            if baseline_nodes[path] != current_nodes[path]
        )
        return GraphDiff(
            added=tuple(sorted(current_paths - baseline_paths)),
            removed=tuple(sorted(baseline_paths - current_paths)),
            changed=(*node_changes, *semantic),
            semantic_changes=tuple(semantic),
        )


@dataclass(frozen=True, slots=True)
class CompiledGraph:
    """Read-only view and renderer for compiled root component plans."""

    roots: tuple[GraphRoot, ...]
    entrypoints: tuple[GraphRoot, ...] = ()
    assemblies: tuple[dict[str, Any], ...] = ()
    build_args: Mapping[str, Any] = field(default_factory=lambda: MappingProxyType({}), compare=False, repr=False)
    _root_candidates: Mapping[Any, tuple[_CandidateRecord, ...]] = field(
        default_factory=lambda: MappingProxyType({}), compare=False, repr=False
    )
    _known_root_selections: Mapping[tuple[Any, int], CompilationExplanation] = field(
        default_factory=lambda: MappingProxyType({}), compare=False, repr=False
    )
    _occurrence_explanations: Mapping[int, CompilationExplanation] = field(
        default_factory=lambda: MappingProxyType({}), compare=False, repr=False
    )
    _manifest_cache: dict[bool, GraphManifest] = field(default_factory=dict, compare=False, repr=False)
    _ownership_report_cache: list[OwnershipReport] = field(default_factory=list, compare=False, repr=False)

    def ownership_report(self) -> OwnershipReport:
        """Return the immutable ownership proof compiled for every graph occurrence."""

        if self._ownership_report_cache:
            return self._ownership_report_cache[0]
        components = {visit.component.occurrence_id: visit.component for visit in self.walk()}
        report = OwnershipReport(
            tuple(
                OwnershipRecord(
                    component=visit.component,
                    path=visit.path,
                    cache_owner=visit.component.cache_owner,
                    cleanup_owner=visit.component.cleanup_owner,
                    owner_component=components.get(visit.component.owner_occurrence_id),
                    reason=visit.component.ownership_reason,
                )
                for visit in self.walk()
            ),
            (),
        )
        self._ownership_report_cache.append(report)
        return report

    def _component_paths(self, *, all_roots: bool) -> dict[str, Component]:
        counters: dict[tuple[str, str | None], int] = {}
        paths: dict[str, Component] = {}

        def visit(component: Component, path: str) -> None:
            paths[path] = component
            for index, child in enumerate(component.dependencies):
                visit(child, f"{path}/dependency:{child.argument or index}:{index}")
            for index, decorator in enumerate(component.decorators):
                visit(decorator, f"{path}/decorator:{index}")
            for index, configuration in enumerate(component.pre_configurations):
                visit(configuration, f"{path}/pre_configuration:{index}")

        for root in self._selected_roots(all_roots):
            requested = qualified_name(root.requested_type)
            selector = (requested, root.component.name)
            candidate = counters.get(selector, 0)
            counters[selector] = candidate + 1
            name = root.component.name or "default"
            visit(root.component, f"root:{requested}:{name}:{candidate}")
        return paths

    def component_at_path(self, path: str, *, all_roots: bool = False) -> Component:
        """Return the occurrence identified by a current manifest path."""

        if not isinstance(path, str) or not path:
            raise ValueError("explain-path-not-found: a non-empty manifest path is required")
        component = self._component_paths(all_roots=all_roots).get(path)
        if component is None:
            raise ValueError(f"explain-path-not-found: {path!r} is not in the current graph manifest")
        return component

    def _path_for_component(self, component: Component) -> tuple[str, ...]:
        if self.roots and component._graph is not self.roots[0].component._graph:
            raise ValueError("explain-path-not-found: the component belongs to a different compiled graph")
        for all_roots in (False, True):
            for path, candidate in self._component_paths(all_roots=all_roots).items():
                if candidate.occurrence_id == component.occurrence_id:
                    return tuple(path.split("/"))
        raise ValueError("explain-path-not-found: the component does not belong to this compiled graph")

    @staticmethod
    def _decision(
        record: _CandidateRecord,
        outcome: DecisionOutcome,
        code: str,
        reason: str,
    ) -> CandidateDecision:
        extra_codes = tuple(item for item in record.decision.reason_codes if item != "registration-eligible")
        return CandidateDecision(
            component_id=record.decision.component_id,
            outcome=outcome,
            reason_codes=(code, *extra_codes),
            reason=f"{reason}; {record.decision.reason}" if extra_codes else reason,
            origin=record.decision.origin,
        )

    def _root_explanation(
        self,
        service_type: Any,
        filter: ComponentFilter,
    ) -> CompilationExplanation:
        collection_type = get_origin(service_type)
        collection_arguments = get_args(service_type)
        is_collection = collection_type in (list, tuple, set) and bool(collection_arguments)
        candidate_type = collection_arguments[0] if is_collection else service_type
        records = self._root_candidates.get(candidate_type)
        if records is None:
            raise ValueError(f"explain-service-not-found: {qualified_name(service_type)} is not a compiled root")

        selected: list[CandidateDecision] = []
        rejected: list[CandidateDecision] = []
        if filter is default_component_filter:
            for record in records:
                if not record.eligible:
                    rejected.append(record.decision)
                elif record.component.name is None:
                    outcome = DecisionOutcome.included if is_collection else DecisionOutcome.selected
                    code = "included-collection" if is_collection else "selected-default"
                    reason = (
                        "The unnamed component is included in the collection"
                        if is_collection
                        else "The component is eligible for default selection"
                    )
                    selected.append(self._decision(record, outcome, code, reason))
                else:
                    rejected.append(
                        self._decision(
                            record,
                            DecisionOutcome.rejected,
                            "rejected-name",
                            "The named component is not eligible for the default request",
                        )
                    )
        else:
            known = self._known_root_selections.get((candidate_type, id(filter)))
            if known is None:
                selector = getattr(filter, "__clean_ioc_selector__", None)
                if isinstance(selector, tuple) and len(selector) == 2 and selector[0] == "name":
                    expected_name = selector[1]
                    for record in records:
                        if not record.eligible:
                            rejected.append(record.decision)
                        elif record.component.name == expected_name:
                            outcome = DecisionOutcome.included if is_collection else DecisionOutcome.selected
                            code = "included-collection" if is_collection else "selected-explicit-filter"
                            selected.append(
                                self._decision(
                                    record,
                                    outcome,
                                    code,
                                    f"The component name matches {expected_name!r}",
                                )
                            )
                        else:
                            rejected.append(
                                self._decision(
                                    record,
                                    DecisionOutcome.rejected,
                                    "rejected-name",
                                    f"The component name does not match {expected_name!r}",
                                )
                            )
                else:
                    raise ValueError("explain-selection-not-recorded: this filter was not evaluated during compilation")
            else:
                selected.extend(known.selected)
                rejected.extend(known.rejected)

        if not selected and not is_collection:
            raise ValueError(f"explain-service-not-found: no compiled root matches {qualified_name(service_type)}")
        if not is_collection and len(selected) > 1:
            raise ValueError(f"explain-ambiguous-root: {qualified_name(service_type)} matches {len(selected)} roots")
        path: tuple[str, ...] = ()
        if selected:
            selected_id = selected[0].component_id
            component = next(
                (record.component for record in records if record.decision.component_id == selected_id),
                None,
            )
            if component is not None:
                try:
                    path = self._path_for_component(component)
                except ValueError:
                    if component.kind is not ComponentKind.provider:
                        raise
                    path = (f"root:{qualified_name(service_type)}",)
        return CompilationExplanation(
            subject=qualified_name(service_type),
            path=path,
            selected=tuple(selected),
            rejected=tuple(rejected),
        )

    @overload
    def explain(
        self,
        subject: Component,
        *,
        filter: ComponentFilter = default_component_filter,
    ) -> CompilationExplanation: ...

    @overload
    def explain(
        self,
        subject: Any,
        *,
        filter: ComponentFilter = default_component_filter,
    ) -> CompilationExplanation: ...

    def explain(
        self,
        subject: Any,
        *,
        filter: ComponentFilter = default_component_filter,
    ) -> CompilationExplanation:
        """Explain a frozen root selection or one exact compiled occurrence.

        Filters are never invoked here. Arbitrary root filters must already have
        been evaluated by a marked entry point; exact-name filters carry a safe
        declarative selector.
        """

        if isinstance(subject, Component):
            path = self._path_for_component(subject)
            explanation = self._occurrence_explanations.get(subject.occurrence_id)
            if explanation is None:
                raise ValueError("explain-path-not-found: no compiler decision exists for this occurrence")
            return replace(explanation, path=path)
        if not callable(filter):
            raise TypeError("filter must be callable")
        return self._root_explanation(subject, filter)

    def walk(self) -> Iterator[GraphVisit]:
        """Walk every compiled occurrence in deterministic depth-first order."""

        def visit(root: GraphRoot, component: Component, ancestors: tuple[Component, ...]) -> Iterator[GraphVisit]:
            components = (*ancestors, component)
            yield GraphVisit(root=root, components=components)
            for child in component.dependencies:
                yield from visit(root, child, components)
            for configuration in component.pre_configurations:
                yield from visit(root, configuration, components)
            for decorator in component.decorators:
                yield from visit(root, decorator, components)

        for root in self.roots:
            yield from visit(root, root.component, ())

    def _selected_roots(self, all_roots: bool) -> tuple[GraphRoot, ...]:
        if all_roots or not self.entrypoints:
            return self.roots
        return self.entrypoints

    def manifest(self, *, all_roots: bool = False) -> GraphManifest:
        cached = self._manifest_cache.get(all_roots)
        if cached is not None:
            return cached
        selected = self._selected_roots(all_roots)
        counters: dict[tuple[str, str | None], int] = {}
        roots: list[dict[str, Any]] = []
        owner_paths: dict[int, str] = {}
        for order, root in enumerate(selected):
            requested = qualified_name(root.requested_type)
            selector = (requested, root.component.name)
            candidate = counters.get(selector, 0)
            counters[selector] = candidate + 1
            name = root.component.name or "default"
            path = f"root:{requested}:{name}:{candidate}"
            node = _node_dict(root.component, path, order, owner_paths)
            node["requested_type"] = requested
            roots.append(node)
        manifest = GraphManifest(
            {
                "schema_version": 3,
                "view": "all_roots" if all_roots or not self.entrypoints else "entrypoints",
                "assemblies": [dict(assembly) for assembly in self.assemblies],
                "roots": roots,
            }
        )
        self._manifest_cache[all_roots] = manifest
        return manifest

    to_manifest = manifest

    def to_text(self, *, all_roots: bool = False) -> str:
        lines: list[str] = []

        def visit(component: Component, depth: int, relation: str | None = None) -> None:
            prefix = "   " * depth
            branch = "└─ " if depth else ""
            label = f"{relation} → " if relation else ""
            lines.append(f"{prefix}{branch}{label}{_component_description(component)}")
            for child in component.dependencies:
                visit(child, depth + 1, _dependency_relationship(child))
            for configuration in component.pre_configurations:
                visit(configuration, depth + 1, _PRE_CONFIGURATION_RELATIONSHIP)
            for decorator in component.decorators:
                visit(decorator, depth + 1, _DECORATOR_RELATIONSHIP)

        for index, root in enumerate(self._selected_roots(all_roots)):
            if index:
                lines.append("")
            lines.append(f"Resolve {qualified_name(root.requested_type)}")
            visit(root.component, 1)
        return "\n".join(lines)

    def to_mermaid(self, *, all_roots: bool = False) -> str:
        lines = ["flowchart TD"]
        next_id = 0

        def visit(component: Component, parent_id: str | None = None, edge: str | None = None) -> None:
            nonlocal next_id
            node_id = f"n{next_id}"
            next_id += 1
            label = escape(_component_description(component), quote=True).replace("\n", " ")
            lines.append(f'    {node_id}["{label}"]')
            if parent_id is not None:
                edge_label = f"|{escape(edge, quote=True)}|" if edge else ""
                lines.append(f"    {parent_id} -->{edge_label} {node_id}")
            for child in component.dependencies:
                visit(child, node_id, _dependency_relationship(child))
            for configuration in component.pre_configurations:
                visit(configuration, node_id, _PRE_CONFIGURATION_RELATIONSHIP)
            for decorator in component.decorators:
                visit(decorator, node_id, _DECORATOR_RELATIONSHIP)

        for root in self._selected_roots(all_roots):
            visit(root.component)
        return "\n".join(lines)


def _type_ast(implementation_type: type) -> TypeAst | None:
    try:
        lines, first_line = inspect.getsourcelines(implementation_type)
        filename = inspect.getsourcefile(implementation_type)
    except (OSError, TypeError):
        return None
    if filename is None:
        return None

    source = textwrap.dedent("".join(lines))
    try:
        tree = ast.parse(source, filename=filename)
    except (SyntaxError, ValueError):
        return None
    node = next(
        (
            candidate
            for candidate in tree.body
            if isinstance(candidate, ast.ClassDef) and candidate.name == implementation_type.__name__
        ),
        None,
    )
    if node is None:
        return None
    ast.increment_lineno(node, first_line - 1)
    return TypeAst(
        filename=filename,
        first_line=first_line,
        source=source,
        node=node,
    )


@dataclass(frozen=True, slots=True)
class ValidationContext:
    """Ephemeral helpers shared by every custom rule in one build."""

    graph: CompiledGraph
    assembly: str | None = None
    _type_asts: dict[type, TypeAst | None] = field(default_factory=dict, init=False, compare=False, repr=False)

    def type_ast(self, implementation_type: type) -> TypeAst | None:
        """Return a cached AST for an inspectable Python class definition."""

        if not isinstance(implementation_type, type):
            raise TypeError("type_ast() requires a type")
        if implementation_type not in self._type_asts:
            self._type_asts[implementation_type] = _type_ast(implementation_type)
        return self._type_asts[implementation_type]
