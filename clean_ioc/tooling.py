"""Build reports, graph rendering, and stable compiler manifests."""

from __future__ import annotations

import ast
import hashlib
import inspect
import json
import textwrap
from dataclasses import dataclass, field
from enum import Enum
from html import escape
from types import MappingProxyType
from typing import Any, Callable, Iterable, Iterator, Mapping, TypeAlias, TypeVar, get_args, get_origin

from .components import Component, ComponentActivation, ComponentKind


class IssueSeverity(str, Enum):
    """Severity assigned to a compiler finding."""

    error = "error"
    warning = "warning"


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
    return f"{target} [{', '.join(details)}]"


def _dependency_relationship(component: Component) -> str:
    if component.argument is None:
        return "depends on"
    return f"depends on: {component.argument}"


_DECORATOR_RELATIONSHIP = "decorated by"
_PRE_CONFIGURATION_RELATIONSHIP = "pre-configured by"


def _node_dict(component: Component, path: str, order: int) -> dict[str, Any]:
    metadata: dict[str, Any] = {
        "path": path,
        "order": order,
        "argument": component.argument,
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
    }
    metadata["dependencies"] = [
        _node_dict(
            child,
            f"{path}/dependency:{child.argument or index}:{index}",
            index,
        )
        for index, child in enumerate(component.dependencies)
    ]
    metadata["decorators"] = [
        _node_dict(decorator, f"{path}/decorator:{index}", index)
        for index, decorator in enumerate(component.decorators)
    ]
    metadata["pre_configurations"] = [
        _node_dict(configuration, f"{path}/pre_configuration:{index}", index)
        for index, configuration in enumerate(component.pre_configurations)
    ]
    return metadata


@dataclass(frozen=True, slots=True)
class GraphChange:
    """One manifest node whose semantic metadata changed."""

    path: str
    before: dict[str, Any]
    after: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {"path": self.path, "before": self.before, "after": self.after}


@dataclass(frozen=True, slots=True)
class GraphDiff:
    """Semantic differences between two graph manifests."""

    added: tuple[str, ...] = ()
    removed: tuple[str, ...] = ()
    changed: tuple[GraphChange, ...] = ()

    @property
    def is_empty(self) -> bool:
        return not (self.added or self.removed or self.changed)

    def to_dict(self) -> dict[str, Any]:
        return {
            "same": self.is_empty,
            "added": list(self.added),
            "removed": list(self.removed),
            "changed": [change.to_dict() for change in self.changed],
        }

    def to_json(self, *, indent: int | None = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, sort_keys=True)

    def to_text(self) -> str:
        if self.is_empty:
            return "Dependency graph is unchanged."
        lines = ["Dependency graph changed:"]
        lines.extend(f"+ {path}" for path in self.added)
        lines.extend(f"- {path}" for path in self.removed)
        lines.extend(f"~ {change.path}" for change in self.changed)
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
        if self.data.get("schema_version") != 1:
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
        return GraphDiff(
            added=tuple(sorted(current_paths - baseline_paths)),
            removed=tuple(sorted(baseline_paths - current_paths)),
            changed=tuple(
                GraphChange(path, baseline_nodes[path], current_nodes[path])
                for path in sorted(shared)
                if baseline_nodes[path] != current_nodes[path]
            ),
        )


@dataclass(frozen=True, slots=True)
class CompiledGraph:
    """Read-only view and renderer for compiled root component plans."""

    roots: tuple[GraphRoot, ...]
    entrypoints: tuple[GraphRoot, ...] = ()
    build_args: Mapping[str, Any] = field(default_factory=lambda: MappingProxyType({}), compare=False, repr=False)
    _manifest_cache: dict[bool, GraphManifest] = field(default_factory=dict, compare=False, repr=False)

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
        for order, root in enumerate(selected):
            requested = qualified_name(root.requested_type)
            selector = (requested, root.component.name)
            candidate = counters.get(selector, 0)
            counters[selector] = candidate + 1
            name = root.component.name or "default"
            path = f"root:{requested}:{name}:{candidate}"
            node = _node_dict(root.component, path, order)
            node["requested_type"] = requested
            roots.append(node)
        manifest = GraphManifest(
            {
                "schema_version": 1,
                "view": "all_roots" if all_roots or not self.entrypoints else "entrypoints",
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
    _type_asts: dict[type, TypeAst | None] = field(default_factory=dict, init=False, compare=False, repr=False)

    def type_ast(self, implementation_type: type) -> TypeAst | None:
        """Return a cached AST for an inspectable Python class definition."""

        if not isinstance(implementation_type, type):
            raise TypeError("type_ast() requires a type")
        if implementation_type not in self._type_asts:
            self._type_asts[implementation_type] = _type_ast(implementation_type)
        return self._type_asts[implementation_type]
