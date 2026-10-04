"""Reusable validation-rule factories and bundles for compiled graph policies."""

from __future__ import annotations

import inspect
from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass, replace
from functools import wraps
from typing import Any, TypeAlias, cast, get_origin

from typing_extensions import TypeForm

from .components import Component, ComponentBuilder, ComponentFilter, ComponentKind, Lifespan, ValidationRuleMode
from .generic_utils import constructor_type
from .metadata import Tag
from .tooling import BuildIssue, GraphVisit, ValidationContext, ValidationRule, qualified_name
from .type_aliases import normalize_type_alias

__all__ = [
    "Layer",
    "PolicyPack",
    "PolicyPackEntry",
    "capability_boundary",
    "forbid_dependency",
    "forbid_runtime_access",
    "layering",
    "require_decorator",
    "require_lifespan",
    "require_tags",
]

PolicyPackEntry: TypeAlias = ValidationRule | tuple[ValidationRule, ValidationRuleMode]

_IMPLEMENTATION_KINDS = frozenset(
    (ComponentKind.registration, ComponentKind.decorator, ComponentKind.pre_configuration)
)
_TRANSPARENT_KINDS = frozenset(
    (
        ComponentKind.collection,
        ComponentKind.provider,
        ComponentKind.managed_provider,
        ComponentKind.provider_map,
        ComponentKind.per_call_handle,
    )
)
_LIFESPANS = frozenset(("transient", "per_resolution", "scoped", "singleton"))


def _validate_callback(callback: Any, *, predicate: bool = False) -> None:
    if not callable(callback):
        message = "A policy requires a callable component filter" if predicate else "A pack requires callable rules"
        raise TypeError(message)
    targets = (callback, getattr(callback, "__call__", None))
    checks = (inspect.iscoroutinefunction, inspect.isasyncgenfunction)
    if predicate:
        checks = (*checks, inspect.isgeneratorfunction)
    if any(check(target) for target in targets for check in checks):
        message = (
            "Policy filters must be synchronous predicates" if predicate else "Validation rules must be synchronous"
        )
        raise TypeError(message)


def _matches(predicate: ComponentFilter, component: Component) -> bool:
    result = predicate(component)
    if inspect.iscoroutine(result):
        result.close()
    if not isinstance(result, bool):
        raise TypeError("A policy component filter must return a bool")
    return result


def _validate_mode(mode: ValidationRuleMode) -> None:
    if mode not in ("build", "validation"):
        raise ValueError("mode must be 'build' or 'validation'")


def _compiled_decorator_type(component: Component) -> Any:
    implementation = normalize_type_alias(component.implementation)
    if isinstance(implementation, type):
        # Open-generic compilation creates a runtime subclass of the exact
        # closed decorator alias. Inspect its captured alias, never its name.
        return normalize_type_alias(vars(implementation).get("__clean_ioc_decorator_type__", implementation))
    if get_origin(implementation) is not None:
        return implementation
    return component.implementation_type


def _packed_rule(name: str, rule: ValidationRule) -> ValidationRule:
    @wraps(rule)
    def wrapped(context: ValidationContext) -> Iterable[BuildIssue]:
        issues = rule(context)
        if inspect.iscoroutine(issues):
            issues.close()
            raise TypeError("Validation rules must be synchronous")
        return (
            replace(issue, message=f"Policy pack {name!r}: {issue.message}") if isinstance(issue, BuildIssue) else issue
            for issue in issues
        )

    return wrapped


@dataclass(frozen=True, slots=True, init=False)
class PolicyPack:
    """Install a frozen list of rules, optionally choosing a mode per rule.

    Plain rules use ``mode`` (``"build"`` by default). Entries of the form
    ``(rule, "validation")`` or ``(rule, "build")`` override that default.
    Arbitrary custom validation callbacks are accepted alongside policy helpers.
    """

    name: str
    rules: tuple[tuple[ValidationRule, ValidationRuleMode], ...]
    mode: ValidationRuleMode

    def __init__(
        self,
        name: str,
        rules: Iterable[PolicyPackEntry],
        *,
        mode: ValidationRuleMode = "build",
    ) -> None:
        if not isinstance(name, str) or not name.strip():
            raise ValueError("A policy pack requires a nonempty name")
        _validate_mode(mode)
        entries: list[tuple[ValidationRule, ValidationRuleMode]] = []
        for entry in rules:
            if isinstance(entry, tuple):
                if len(entry) != 2:
                    raise TypeError("A policy pack entry must be a rule or a (rule, mode) pair")
                rule, rule_mode = cast(tuple[ValidationRule, ValidationRuleMode], entry)
            else:
                rule, rule_mode = entry, mode
            _validate_callback(rule)
            _validate_mode(rule_mode)
            entries.append((rule, rule_mode))
        object.__setattr__(self, "name", name)
        object.__setattr__(self, "rules", tuple(entries))
        object.__setattr__(self, "mode", mode)

    def __call__(self, builder: ComponentBuilder) -> None:
        for rule, mode in self.rules:
            builder.add_validation_rule(_packed_rule(self.name, rule), mode=mode)


@dataclass(frozen=True, slots=True)
class Layer:
    """Match implementation modules using exact package prefixes.

    ``my_app.domain`` matches that module and its submodules, but not
    ``my_app.domain_extra``. The longest matching prefix wins across layers.
    """

    name: str
    module_prefixes: tuple[str, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name.strip():
            raise ValueError("A layer requires a nonempty name")
        if isinstance(self.module_prefixes, str):
            raise TypeError("module_prefixes must be an iterable of module names")
        prefixes = tuple(self.module_prefixes)
        if not prefixes or any(
            not isinstance(prefix, str) or not all(part.isidentifier() for part in prefix.split("."))
            for prefix in prefixes
        ):
            raise ValueError("A layer requires nonempty dotted module prefixes")
        object.__setattr__(self, "module_prefixes", prefixes)


def layering(
    *,
    layers: Iterable[Layer],
    allowed_dependencies: Mapping[str, Iterable[str]],
    require_match: bool = False,
) -> ValidationRule:
    """Check direct implementation-layer edges, including synthetic bridges.

    This checks compiled implementations, not Python imports or interface
    ownership. An unmatched implementation is ignored unless ``require_match``
    is true; an omitted source layer in the dependency map allows no edges.
    """

    frozen_layers = tuple(layers)
    if not frozen_layers or any(not isinstance(layer, Layer) for layer in frozen_layers):
        raise ValueError("layers must contain at least one Layer")
    names = {layer.name for layer in frozen_layers}
    if len(names) != len(frozen_layers):
        raise ValueError("Layer names must be unique")
    prefixes = [prefix for layer in frozen_layers for prefix in layer.module_prefixes]
    if len(set(prefixes)) != len(prefixes):
        raise ValueError("Module prefixes must be unique across layers")
    allowed: dict[str, frozenset[str]] = {}
    for name, dependencies in allowed_dependencies.items():
        if isinstance(dependencies, str):
            raise TypeError("Allowed dependencies must be an iterable of layer names")
        targets = frozenset(dependencies)
        if name not in names or not targets <= names:
            raise ValueError("Allowed dependencies must refer to declared layer names")
        allowed[name] = targets

    def layer_of(component: Component) -> str | None:
        if component.kind is ComponentKind.decorator:
            implementation = _compiled_decorator_type(component)
        elif component.kind is ComponentKind.pre_configuration:
            implementation = component.implementation
        else:
            implementation = component.implementation_type
        module = (get_origin(implementation) or implementation).__module__
        matches = (
            (len(prefix), layer.name)
            for layer in frozen_layers
            for prefix in layer.module_prefixes
            if module == prefix or module.startswith(f"{prefix}.")
        )
        match = max(matches, default=None)
        return None if match is None else match[1]

    def rule(context: ValidationContext) -> Iterable[BuildIssue]:
        for visit in context.graph.walk():
            component = visit.component
            if component.kind not in _IMPLEMENTATION_KINDS:
                continue
            target_layer = layer_of(component)
            if target_layer is None:
                if require_match:
                    yield visit.issue("policy-unmatched-layer", "The implementation does not match a declared layer")
                continue
            parent = next(
                (ancestor for ancestor in reversed(visit.components[:-1]) if ancestor.kind not in _TRANSPARENT_KINDS),
                None,
            )
            if parent is None or parent.kind not in _IMPLEMENTATION_KINDS:
                continue
            source_layer = layer_of(parent)
            if source_layer is not None and target_layer not in allowed.get(source_layer, frozenset()):
                yield visit.issue(
                    "policy-layer-violation",
                    f"Layer {source_layer!r} cannot depend on layer {target_layer!r}",
                )

    return rule


def _forbidden_paths(
    context: ValidationContext,
    source: ComponentFilter,
    target: ComponentFilter,
    *,
    transitive: bool,
) -> Iterator[GraphVisit]:
    # Keep one shortest witness for each source path, preserving source walk order.
    selected: dict[tuple[int, ...], tuple[int, GraphVisit] | None] = {}
    source_matches: dict[int, bool] = {}
    target_matches: dict[int, bool] = {}
    for visit in context.graph.walk():
        component = visit.component
        source_match = source_matches.get(component.occurrence_id)
        if source_match is None:
            source_match = _matches(source, component)
            source_matches[component.occurrence_id] = source_match
        if source_match:
            selected.setdefault((id(visit.root), *(item.occurrence_id for item in visit.components)), None)
        target_match = target_matches.get(component.occurrence_id)
        if target_match is None:
            target_match = _matches(target, component)
            target_matches[component.occurrence_id] = target_match
        if not target_match:
            continue
        for index in range(len(visit.components) - 2, -1, -1):
            ancestor = visit.components[index]
            key = (id(visit.root), *(item.occurrence_id for item in visit.components[: index + 1]))
            if key in selected:
                distance = len(visit.components) - index - 1
                previous = selected[key]
                if previous is None or distance < previous[0]:
                    selected[key] = (distance, visit)
            if not transitive and ancestor.kind not in _TRANSPARENT_KINDS:
                break
    for witness in selected.values():
        if witness is not None:
            yield witness[1]


def forbid_dependency(
    source: ComponentFilter,
    target: ComponentFilter,
    *,
    transitive: bool = False,
) -> ValidationRule:
    """Reject direct or transitive dependencies, once per source occurrence.

    Collections, providers, provider maps, and per-call handles are transparent
    to direct checks. Transitive checks report the shortest matching path.
    """

    _validate_callback(source, predicate=True)
    _validate_callback(target, predicate=True)

    def rule(context: ValidationContext) -> Iterable[BuildIssue]:
        for visit in _forbidden_paths(context, source, target, transitive=transitive):
            yield visit.issue("policy-forbidden-dependency", "The component has a forbidden dependency")

    return rule


def require_decorator(
    target: ComponentFilter,
    *,
    decorator_type: TypeForm[Any],
    count: int = 1,
) -> ValidationRule:
    """Require an exact compiled decorator type/count on matching registrations."""

    _validate_callback(target, predicate=True)
    if not isinstance(count, int) or isinstance(count, bool) or count < 0:
        raise ValueError("Decorator count must be a nonnegative integer")
    expected = normalize_type_alias(decorator_type)
    if constructor_type(expected) is None:
        raise TypeError("decorator_type must be a class or a parameterized class")

    def rule(context: ValidationContext) -> Iterable[BuildIssue]:
        for visit in context.graph.walk():
            component = visit.component
            if component.kind is not ComponentKind.registration or not _matches(target, component):
                continue
            actual = sum(_compiled_decorator_type(decorator) == expected for decorator in component.decorators)
            if actual != count:
                yield visit.issue(
                    "policy-missing-decorator" if actual == 0 and count > 0 else "policy-decorator-count",
                    f"Expected {count} decorator(s) of type {qualified_name(expected)}; found {actual}",
                )

    return rule


def require_lifespan(target: ComponentFilter, *allowed: Lifespan) -> ValidationRule:
    """Constrain the public lifespan of every matching component occurrence."""

    _validate_callback(target, predicate=True)
    if not allowed or any(lifespan not in _LIFESPANS for lifespan in allowed):
        raise ValueError("Supply at least one public lifespan: transient, per_resolution, scoped, or singleton")
    lifespans = frozenset(allowed)

    def rule(context: ValidationContext) -> Iterable[BuildIssue]:
        for visit in context.graph.walk():
            component = visit.component
            if _matches(target, component) and component.lifespan not in lifespans:
                yield visit.issue(
                    "policy-invalid-lifespan",
                    f"Lifespan {component.lifespan!r} is not allowed; expected one of {', '.join(sorted(lifespans))}",
                )

    return rule


def forbid_runtime_access(target: ComponentFilter) -> ValidationRule:
    """Reject Scope (including Container) and ResolutionContext dependencies."""

    from .container import ResolutionContext, Scope

    _validate_callback(target, predicate=True)

    def runtime_context(component: Component) -> bool:
        return (
            component.kind is ComponentKind.runtime_context
            and isinstance(component.service_type, type)
            and issubclass(component.service_type, (Scope, ResolutionContext))
        )

    def rule(context: ValidationContext) -> Iterable[BuildIssue]:
        for visit in _forbidden_paths(context, target, runtime_context, transitive=True):
            yield visit.issue("policy-runtime-access", "The component depends on Scope or ResolutionContext")

    return rule


def require_tags(target: ComponentFilter, *tags: Tag) -> ValidationRule:
    """Require exact metadata pairs, including an exact None tag value."""

    _validate_callback(target, predicate=True)
    if not tags or any(not isinstance(tag, Tag) for tag in tags):
        raise ValueError("Supply at least one Tag")
    required = tuple(dict.fromkeys(tags))

    def rule(context: ValidationContext) -> Iterable[BuildIssue]:
        for visit in context.graph.walk():
            component = visit.component
            if not _matches(target, component):
                continue
            missing = tuple(tag for tag in required if tag not in component.tags)
            if missing:
                names = ", ".join(tag.name for tag in missing)
                yield visit.issue("policy-missing-tag", f"Missing required exact tag pairs for: {names}")

    return rule


def capability_boundary(entrypoints: ComponentFilter, *, allow: Iterable[str]) -> ValidationRule:
    """Check declared capability tags beneath matching marked entry points.

    Without entry-point markers, all compiled roots are eligible. Only explicit
    Tag("capability", value) metadata is checked; effects are never inferred.
    """

    _validate_callback(entrypoints, predicate=True)
    if isinstance(allow, str):
        raise TypeError("allow must be an iterable of capability names")
    allowed = frozenset(allow)
    if any(not isinstance(value, str) or not value for value in allowed):
        raise ValueError("Capabilities must be nonempty strings")

    def rule(context: ValidationContext) -> Iterable[BuildIssue]:
        roots = context.graph.entrypoints or context.graph.roots
        for root in roots:
            if not _matches(entrypoints, root.component):
                continue
            forbidden = {
                tag.value
                for component in (root.component, *root.component.descendants())
                for tag in component.tags
                if tag.name == "capability" and tag.value is not None and tag.value not in allowed
            }
            if forbidden:
                yield GraphVisit(root, (root.component,)).issue(
                    "policy-capability-violation",
                    f"Entry point has forbidden declared capabilities: {', '.join(sorted(forbidden))}",
                )

    return rule
