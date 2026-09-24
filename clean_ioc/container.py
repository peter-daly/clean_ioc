"""Build-time composition and graph-free runtime for Clean IoC."""

from __future__ import annotations

import asyncio
import concurrent.futures
import copy
import importlib
import inspect
import logging
import os
import pkgutil
import re
import threading
import types
import typing
from collections import defaultdict, deque
from collections.abc import Callable, Hashable, Iterable, Iterator, Mapping
from contextvars import ContextVar
from dataclasses import dataclass, field, replace
from typing import Any, TypeVar, cast, get_args, get_origin, overload
from uuid import UUID, uuid4, uuid5

from typetoolbox.generics import GenericTypeMap, get_generic_mapping
from typing_extensions import TypeAliasType, TypeForm

from . import _legacy as legacy
from . import registration_patterns as patterns
from ._decorator_templates import (
    DecoratorTemplate,
    RegistrationInfo,
    _DecoratorTemplateDefinition,
    _GeneratedDecoratorDefinition,
    _TemplateExpansion,
    _TemplateSourceSelection,
)
from ._legacy_configuration import default_parameter_value_factory
from ._service_targets import _select_service_target, _ServiceTarget
from .arguments import (
    INJECT,
    REMOVE,
    ParameterContext,
    _DerivedArgument,
    _FixedArgument,
    _SelectArgument,
)
from .boundaries import Boundary, BoundaryAlias, Expose, Use
from .components import (
    BundleRunScope,
    Component,
    ComponentActivation,
    ComponentBuilder,
    ComponentFilter,
    ComponentKind,
    Lifespan,
    RuntimeOwnerKind,
    ValidationRuleMode,
    _ComponentDraft,
    _ComponentGraph,
    _undecorated_component_view,
    all_components,
    default_component_filter,
    normalize_implementation_type,
)
from .generic_utils import (
    _bind_typevar_identities,
    _project_service_type,
    _resolve_typevar_identities,
    _typevar_identities,
    constructor_type,
)
from .generic_utils import resolve_typevar_bindings as _resolve_factory_typevars
from .provider_maps import ProviderMapGroup
from .providers import AsyncProvider, Provider
from .service_groups import DerivedServices, ServiceGroup
from .tooling import (
    BuildIssue,
    BuildReport,
    CandidateDecision,
    CompilationAttempt,
    CompilationExplanation,
    CompiledGraph,
    DecisionOutcome,
    DefinitionOrigin,
    GenericBindingExplanation,
    GraphRoot,
    IssueSeverity,
    ParameterExplanation,
    PartialEdge,
    PartialGraph,
    PartialNode,
    PartialState,
    SourceLocation,
    ValidationContext,
    ValidationRule,
    _CandidateRecord,
    _issue_path_name,
    qualified_name,
)
from .type_aliases import TypeAliasNormalizationError, alias_label, is_new_type, normalize_type_alias

TService = TypeVar("TService")
K = TypeVar("K")

logger = logging.getLogger(__name__)

_EMPTY_BUILD_ARGS: Mapping[str, Any] = types.MappingProxyType({})
_EXPANDING_TEMPLATE_OWNERS: ContextVar[frozenset[str]] = ContextVar("template_expansion_owners", default=frozenset())
_PACKAGE_DIRECTORY = os.path.dirname(os.path.abspath(__file__))


def _composition_type(value: Any) -> Any:
    """Canonicalize an available alias while retaining unresolved declarations for build."""

    try:
        return normalize_type_alias(value)
    except TypeAliasNormalizationError:
        return value


def _group_type_has_unresolved(annotation: Any) -> bool:
    if isinstance(annotation, TypeVar) or annotation is Any:
        return True
    if isinstance(annotation, (list, tuple)):
        return any(_group_type_has_unresolved(item) for item in annotation)
    return any(_group_type_has_unresolved(item) for item in get_args(annotation))


def _known_group_type_conflict(projected: Any, contract: Any) -> bool:
    """Reject concrete conflicts while leaving TypeVar constraints for M03."""
    if isinstance(projected, TypeVar) or isinstance(contract, TypeVar) or projected is Any or contract is Any:
        return False
    if projected == contract:
        return False
    if isinstance(projected, (list, tuple)) or isinstance(contract, (list, tuple)):
        if type(projected) is not type(contract) or len(projected) != len(contract):
            return True
        return any(_known_group_type_conflict(actual, required) for actual, required in zip(projected, contract))
    projected_origin, contract_origin = get_origin(projected), get_origin(contract)
    union_origins = (typing.Union, types.UnionType)
    if projected_origin in union_origins or contract_origin in union_origins:
        if _group_type_has_unresolved(projected) or _group_type_has_unresolved(contract):
            projected_members = get_args(projected) if projected_origin in union_origins else (projected,)
            contract_members = get_args(contract) if contract_origin in union_origins else (contract,)
            return any(
                all(_known_group_type_conflict(member, candidate) for candidate in contract_members)
                for member in projected_members
            ) or any(
                all(_known_group_type_conflict(candidate, member) for candidate in projected_members)
                for member in contract_members
            )
    if contract_origin is None:
        return (projected_origin or projected) != contract
    if projected_origin != contract_origin:
        return True
    projected_args, contract_args = get_args(projected), get_args(contract)
    if not contract_args:
        return False if contract_origin is not None else projected != contract
    if len(projected_args) != len(contract_args):
        return True
    return any(_known_group_type_conflict(actual, required) for actual, required in zip(projected_args, contract_args))


def _validate_service_groups(service_type: Any, groups: Iterable[ServiceGroup]) -> None:
    for group in groups:
        contract = _composition_type(group.service_type)
        if isinstance(contract, TypeAliasType):
            # An unresolved forward alias is checked after build-time normalization.
            continue
        try:
            projected = _project_service_type(service_type, contract)
        except TypeAliasNormalizationError:
            continue
        except ValueError as error:
            raise TypeError(
                f"Registration service {qualified_name(service_type)} has conflicting projections for "
                f"service group {group.name!r} targeting {qualified_name(contract)}"
            ) from error
        if projected is None or _known_group_type_conflict(projected, contract):
            raise TypeError(
                f"Registration service {qualified_name(service_type)} is incompatible with "
                f"service group {group.name!r} targeting {qualified_name(contract)}"
            )


def _materialize_service_groups(groups: Iterable[ServiceGroup]) -> frozenset[ServiceGroup]:
    unique: dict[ServiceGroup, None] = {}
    for group in groups:
        if not isinstance(group, ServiceGroup):
            raise TypeError("groups must contain ServiceGroup instances")
        unique[group] = None
    return frozenset(unique)


def _source_location() -> SourceLocation | None:
    """Find the first caller outside Clean IoC without retaining a frame."""

    frame = inspect.currentframe()
    try:
        frame = None if frame is None else frame.f_back
        while frame is not None:
            filename = frame.f_code.co_filename
            if filename and not filename.startswith("<"):
                absolute = os.path.abspath(filename)
                try:
                    in_package = os.path.commonpath((absolute, _PACKAGE_DIRECTORY)) == _PACKAGE_DIRECTORY
                except ValueError:
                    in_package = False
                if not in_package:
                    try:
                        path = os.path.relpath(absolute, os.getcwd())
                    except (OSError, ValueError):
                        path = os.path.basename(absolute)
                    if os.path.isabs(path):
                        path = os.path.basename(path)
                    path = path.replace(os.sep, "/")
                    module = frame.f_globals.get("__name__")
                    symbol = getattr(frame.f_code, "co_qualname", frame.f_code.co_name)
                    return SourceLocation(
                        module=module if isinstance(module, str) else None,
                        symbol=symbol if isinstance(symbol, str) else None,
                        path=path,
                        line=frame.f_lineno,
                    )
            frame = frame.f_back
    finally:
        del frame
    return None


def _filter_description(filter: ComponentFilter) -> str:
    description = getattr(filter, "__clean_ioc_description__", None)
    if isinstance(description, str) and description:
        return description
    name = getattr(filter, "__qualname__", None) or getattr(filter, "__name__", None)
    if not isinstance(name, str) or name == "<lambda>":
        return "<anonymous-filter>"
    module = getattr(filter, "__module__", None)
    return name if module in (None, "builtins") else f"{module}.{name}"


def _synthetic_origin() -> DefinitionOrigin:
    return DefinitionOrigin("synthetic", None, "root", (), None)


_LEGACY_LIFESPANS: dict[Lifespan, legacy.Lifespan] = {
    "transient": legacy.Lifespan.transient,
    "per_resolution": legacy.Lifespan.per_resolution,
    "scoped": legacy.Lifespan.scoped,
    "singleton": legacy.Lifespan.singleton,
}


def _legacy_lifespan(lifespan: Lifespan) -> legacy.Lifespan:
    try:
        return _LEGACY_LIFESPANS[lifespan]
    except (KeyError, TypeError) as error:
        allowed = ", ".join(repr(value) for value in _LEGACY_LIFESPANS)
        raise ValueError(f"lifespan must be one of {allowed}; got {lifespan!r}") from error


def _component_lifespan(lifespan: legacy.Lifespan) -> Lifespan:
    return lifespan.name


def _normalize_build_args(build_args: Mapping[str, Any] | None) -> Mapping[str, Any]:
    if build_args is None:
        return _EMPTY_BUILD_ARGS
    if not isinstance(build_args, Mapping):
        raise TypeError("build_args must be a mapping with string keys")
    values = dict(build_args)
    invalid_keys = [key for key in values if not isinstance(key, str)]
    if invalid_keys:
        rendered = ", ".join(repr(key) for key in invalid_keys)
        raise TypeError(f"build_args keys must be strings; got {rendered}")
    if not values:
        return _EMPTY_BUILD_ARGS
    return types.MappingProxyType(values)


def _merge_build_args(
    inherited: Mapping[str, Any],
    overrides: Mapping[str, Any] | None,
) -> Mapping[str, Any]:
    normalized = _normalize_build_args(overrides)
    if not normalized:
        return inherited
    values = dict(inherited)
    values.update(normalized)
    return types.MappingProxyType(values)


def _arguments_to_dependency_config(
    arguments: Mapping[str, Any] | None,
    *,
    allow_remove: bool = False,
) -> legacy.DependencyConfig:
    """Adapt V2 argument policies to the private signature parser."""

    configured: legacy.DependencyConfig = {}
    for name, argument in (arguments or {}).items():
        if argument is REMOVE:
            if not allow_remove:
                raise ValueError("REMOVE is only valid when patching arguments")
            configured[name] = legacy.RemoveDependencySetting
        elif isinstance(argument, _SelectArgument):
            configured[name] = legacy.DependencySettings(
                value_factory=cast(Any, argument),
                filter=argument.filter,
            )
        elif isinstance(argument, _DerivedArgument):
            configured[name] = legacy.DependencySettings(value_factory=cast(Any, argument))
        else:
            configured[name] = legacy.DependencySettings(value_factory=cast(Any, _FixedArgument(argument)))
    return configured


def _validate_dependency_names(
    implementation: Any,
    dependencies: Mapping[str, legacy.Dependency],
) -> None:
    """Reject configured names that activation cannot pass to the callable."""

    try:
        parameters = inspect.signature(constructor_type(implementation) or implementation).parameters
    except (TypeError, ValueError):
        return
    if any(parameter.kind is inspect.Parameter.VAR_KEYWORD for parameter in parameters.values()):
        return
    unknown = sorted(set(dependencies) - set(parameters))
    if unknown:
        names = ", ".join(repr(name) for name in unknown)
        raise ContainerBuildError(
            f"{qualified_name(implementation)} has no argument named {names}",
            code="invalid-argument",
        )


class BuilderAlreadyBuiltError(RuntimeError):
    pass


class ContainerBuildError(RuntimeError):
    """Raised when a component plan cannot be compiled."""

    def __init__(
        self,
        message: str | None = None,
        *,
        report: BuildReport | None = None,
        code: str | None = None,
        path: tuple[str, ...] = (),
        explanations: tuple[CompilationExplanation, ...] = (),
        partial_graph: PartialGraph | None = None,
    ):
        self.report = report
        self.code = code
        self.path = path
        self.explanations = explanations
        self.partial_graph = partial_graph
        super().__init__(message or (report.to_text() if report is not None else "Container build failed"))


class CannotResolveError(LookupError):
    """Raised when no compiled root matches a resolution request."""

    def __init__(self, service_type: Any):
        self.service_type = service_type
        super().__init__(f"No compiled component matches {service_type!r}")


class UndeclaredScopeSlotError(ContainerBuildError):
    pass


class ScopeProvisionError(RuntimeError):
    pass


class ScopeClosedError(RuntimeError):
    """Raised when an operation targets a scope whose ownership boundary is closed."""


class ProviderScopeClosedError(ScopeClosedError):
    """Raised when a provider is called after its bound scope has closed."""


class ResolutionContext:
    """Resolve an already-compiled component inside the current object graph."""

    __slots__ = ("_context", "_requests")

    def __init__(
        self,
        context: _RuntimeResolutionContext,
        requests: tuple[_CompiledResolutionRequest, ...] = (),
    ) -> None:
        self._context = context
        self._requests = requests

    def _request(self, service_type: Any, filter: ComponentFilter) -> _CompiledResolutionRequest | None:
        for item in self._requests:
            if item.request.service_type == service_type and item.request.filter is filter:
                return item
        canonical_type = normalize_type_alias(service_type)
        if canonical_type is service_type:
            return None
        return next(
            (
                item
                for item in self._requests
                if item.request.service_type == canonical_type and item.request.filter is filter
            ),
            None,
        )

    def resolve(
        self,
        service_type: TypeForm[TService],
        filter: ComponentFilter = default_component_filter,
    ) -> TService:
        self._context.ensure_active()
        request = self._request(service_type, filter)
        if request is not None:
            return cast(TService, request.step.resolve(self._context))
        return cast(TService, self._context.resolve_root(service_type, filter))

    async def resolve_async(
        self,
        service_type: TypeForm[TService],
        filter: ComponentFilter = default_component_filter,
    ) -> TService:
        self._context.ensure_active()
        request = self._request(service_type, filter)
        if request is not None:
            return cast(TService, await request.step.resolve_async(self._context))
        return cast(TService, await self._context.resolve_root_async(service_type, filter))


_RESOLUTION_REQUESTS_ATTRIBUTE = "__clean_ioc_resolution_requests__"
_ACTIVATION_LOCAL_CONTEXT_ATTRIBUTE = "__clean_ioc_activation_local_resolution_context__"


@dataclass(frozen=True, slots=True)
class _ResolutionRequest:
    service_type: Any
    filter: ComponentFilter
    resolve_async: bool


@dataclass(frozen=True, slots=True)
class _EntryPoint:
    service_type: Any
    filter: ComponentFilter
    origin: DefinitionOrigin


@dataclass(frozen=True, slots=True)
class _DecoratorDefinition:
    id: str
    service_type: Any
    decorator_type: Any
    decorated_arg: str | None
    arguments: Mapping[str, Any]
    position: int
    order: int
    when: ComponentFilter
    name: str | None
    tags: tuple[legacy.Tag, ...]
    origin: DefinitionOrigin


@dataclass(frozen=True, slots=True)
class _PreConfigurationDefinition:
    id: str
    service_types: tuple[Any, ...]
    configuration_fn: Callable[..., Any]
    arguments: Mapping[str, Any]
    order: int
    when: ComponentFilter
    continue_on_failure: bool
    origin: DefinitionOrigin


@dataclass(frozen=True, slots=True)
class _ValidationRuleDefinition:
    rule: ValidationRule
    mode: ValidationRuleMode
    origin: DefinitionOrigin


@dataclass(frozen=True, slots=True)
class _ProviderMapDefinition:
    key: Callable[[Component], Hashable] | None
    component_filter: ComponentFilter
    group: ProviderMapGroup[Any, Any] | None = None


def _provider_map_factory() -> None:
    """Registration marker; the compiler replaces activation with a map step."""

    raise RuntimeError("Provider maps require a compiled activation step")


class _DecoratorUnset:
    __slots__ = ()

    def __repr__(self) -> str:
        return "UNCHANGED"


_DECORATOR_UNSET = _DecoratorUnset()


@dataclass(frozen=True, slots=True)
class _Layer:
    registry: legacy._Registry
    internal_ids: frozenset[str]
    owner_token: str
    registration_when: dict[str, ComponentFilter]
    registration_origins: dict[str, DefinitionOrigin]
    factory_ids: frozenset[str]
    factory_specializations: dict[str, object]
    decorators: tuple[_DecoratorDefinition, ...]
    removed_decorator_ids: frozenset[str]
    pre_configurations: tuple[_PreConfigurationDefinition, ...]
    pre_configuration_states: dict[str, _PreConfigurationState]
    slots: frozenset[tuple[Any, str | None]]
    slot_origins: dict[tuple[Any, str | None], DefinitionOrigin]
    entrypoints: tuple[_EntryPoint, ...]
    validation_rules: tuple[_ValidationRuleDefinition, ...]
    provider_maps: Mapping[str, _ProviderMapDefinition]
    contributions: Mapping[str, Mapping[ProviderMapGroup[Any, Any], Hashable]]
    service_groups: Mapping[str, frozenset[ServiceGroup]]
    pattern_ids: tuple[str, ...]
    ensured_import_modules: tuple[str, ...]
    decorator_templates: tuple[_DecoratorTemplateDefinition, ...] = ()
    removed_template_ids: frozenset[str] = frozenset()
    instance_implementation_types: Mapping[str, Any] = field(default_factory=lambda: types.MappingProxyType({}))


@dataclass(frozen=True, slots=True)
class _VisibilityTarget:
    source: str | None
    service_type: Any
    registration_id: str | None
    name: str | None
    tags: tuple[legacy.Tag, ...]
    source_service_type: Any | None = None
    source_name: str | None = None
    source_tags: tuple[legacy.Tag, ...] = ()
    slot: bool = False


@dataclass(frozen=True, slots=True)
class _BoundaryBlueprint:
    name: str
    layer: _Layer
    uses: tuple[Use, ...]
    exposes: tuple[Expose, ...]
    root_layer_offset: int = 0
    resolved_uses: tuple[_VisibilityTarget, ...] = ()
    resolved_exposes: tuple[_VisibilityTarget, ...] = ()


@dataclass(frozen=True, slots=True)
class _Blueprint:
    layers: tuple[_Layer, ...]
    boundaries: tuple[_BoundaryBlueprint, ...] = ()
    generated_decorators: tuple[_GeneratedDecoratorDefinition, ...] = ()
    template_selections: tuple[_TemplateSourceSelection, ...] = ()

    @property
    def slots(self) -> frozenset[tuple[Any, str | None]]:
        return frozenset(slot for layer in self.layers for slot in layer.slots)

    @property
    def entrypoints(self) -> tuple[_EntryPoint, ...]:
        return tuple(entrypoint for layer in self.layers for entrypoint in layer.entrypoints)

    @property
    def validation_rules(self) -> tuple[_ValidationRuleDefinition, ...]:
        root = tuple(rule for layer in reversed(self.layers) for rule in layer.validation_rules)
        local = tuple(rule for boundary in self.boundaries for rule in boundary.layer.validation_rules)
        return (*root, *local)

    def boundary(self, name: str) -> _BoundaryBlueprint | None:
        return next((boundary for boundary in self.boundaries if boundary.name == name), None)

    def registration_area(self, layer: _Layer) -> str | None:
        return next((boundary.name for boundary in self.boundaries if boundary.layer is layer), None)

    def _root_layers_for(self, boundary: _BoundaryBlueprint) -> tuple[_Layer, ...]:
        return self.layers[boundary.root_layer_offset :]

    @staticmethod
    def _registrations_in(layers: Iterable[_Layer], service_type: Any) -> list[tuple[legacy._Registration, _Layer]]:
        found: list[tuple[legacy._Registration, _Layer]] = []
        seen: set[str] = set()
        for layer in layers:
            for registration in layer.registry.get_registrations(service_type):
                if registration.id in layer.internal_ids or registration.id in seen:
                    continue
                seen.add(registration.id)
                found.append((registration, layer))
        return found

    def local_registrations(self, area: str | None, service_type: Any) -> list[tuple[legacy._Registration, _Layer]]:
        layers: tuple[_Layer, ...]
        if area is None:
            layers = self.layers
        else:
            boundary = self.boundary(area)
            layers = () if boundary is None else (boundary.layer,)
        return self._registrations_in(layers, service_type)

    def registrations(self, service_type: Any, area: str | None = None) -> list[tuple[legacy._Registration, _Layer]]:
        found = self.local_registrations(area, service_type)
        seen = {registration.id for registration, _ in found}
        found.extend(
            (registration, layer)
            for registration, layer, _ in self.visible_registrations(service_type, area)
            if registration.id not in seen
        )
        return found

    def visible_registrations(
        self, service_type: Any, area: str | None = None
    ) -> list[tuple[legacy._Registration, _Layer, _VisibilityTarget]]:
        visible_targets: Iterable[_VisibilityTarget]
        if area is None:
            visible_targets = (
                target
                for boundary in self.boundaries
                for target in boundary.resolved_exposes
                if target.registration_id is not None and _public_service_matches(target.service_type, service_type)
            )
        else:
            boundary = self.boundary(area)
            visible_targets = (
                ()
                if boundary is None
                else (
                    target
                    for target in boundary.resolved_uses
                    if not target.slot
                    and target.registration_id is not None
                    and _public_service_matches(target.service_type, service_type)
                )
            )
        found: list[tuple[legacy._Registration, _Layer, _VisibilityTarget]] = []
        for target in visible_targets:
            component_id = cast(str, target.registration_id)
            candidate = self.registration_definition(component_id)
            if candidate is not None:
                found.append((*candidate, target))
        return found

    def registration_definition(self, component_id: str) -> tuple[legacy._Registration, _Layer] | None:
        for layer in (*self.layers, *(boundary.layer for boundary in self.boundaries)):
            for registrations in layer.registry._registrations.values():
                for registration in registrations:
                    if registration.id == component_id and registration.id not in layer.internal_ids:
                        return registration, layer
        return None

    def visibility_targets(
        self, area: str | None, component_id: str, service_type: Any
    ) -> tuple[_VisibilityTarget, ...]:
        targets: Iterable[_VisibilityTarget]
        if area is None:
            targets = (target for boundary in self.boundaries for target in boundary.resolved_exposes)
        else:
            boundary = self.boundary(area)
            targets = () if boundary is None else boundary.resolved_uses
        return tuple(
            target
            for target in targets
            if not target.slot
            and target.registration_id == component_id
            and _public_service_matches(target.service_type, service_type)
        )

    def visibility_reason(self, area: str | None, component_id: str, layer: _Layer) -> tuple[str, str]:
        definition_area = self.registration_area(layer)
        if definition_area == area:
            if area is None:
                return "", "The registration is visible in root composition"
            return "selected-local", "The registration is defined in the current composition area"
        if area is None:
            return "selected-exposure", f"The component is exposed by boundary {definition_area!r}"
        return "selected-use", f"Boundary {area!r} explicitly uses the component from {definition_area or 'root'!r}"

    def registration_origin(self, registration_id: str, layer: _Layer) -> DefinitionOrigin:
        return layer.registration_origins.get(registration_id, _synthetic_origin())

    def slot_definitions(
        self, service_type: Any, area: str | None = None
    ) -> tuple[tuple[Any, str | None, DefinitionOrigin], ...]:
        found: list[tuple[Any, str | None, DefinitionOrigin]] = []
        seen: set[tuple[Any, str | None]] = set()
        layers = self.layers if area is None else ()
        for layer in layers:
            for slot, origin in layer.slot_origins.items():
                if slot in seen or slot[0] != service_type:
                    continue
                seen.add(slot)
                found.append((slot[0], slot[1], origin))
        if area is not None:
            boundary = self.boundary(area)
            if boundary is None:
                return tuple(found)
            for target in boundary.resolved_uses:
                if not target.slot or target.service_type != service_type:
                    continue
                source_layers = self._root_layers_for(boundary)
                for layer in source_layers:
                    slot = (target.service_type, target.name)
                    origin = layer.slot_origins.get(slot)
                    if origin is not None and slot not in seen:
                        seen.add(slot)
                        found.append((slot[0], slot[1], origin))
        return tuple(found)

    def decorators(self, service_type: Any, area: str | None = None) -> list[tuple[_DecoratorDefinition, _Layer]]:
        found: list[tuple[_DecoratorDefinition, _Layer, int]] = []
        removed: set[str] = set()
        seen: set[str] = set()
        layers = (
            self.layers
            if area is None
            else (() if self.boundary(area) is None else (cast(_BoundaryBlueprint, self.boundary(area)).layer,))
        )
        for layer_index, layer in enumerate(layers):
            removed.update(layer.removed_decorator_ids)
            for decorator in layer.decorators:
                if decorator.id in removed or decorator.id in seen:
                    continue
                if not _decorator_service_matches(decorator.service_type, service_type):
                    continue
                seen.add(decorator.id)
                found.append((decorator, layer, layer_index))

        # Runtime activation proceeds from the core outwards. Higher positions
        # therefore appear later, while equal positions retain declaration order
        # from outside to inside by activating newer definitions first.
        found.sort(key=lambda item: (item[0].position, item[2], -item[0].order))
        return [(decorator, layer) for decorator, layer, _ in found]

    def decorator_definition(self, service_type: Any, decorator_id: str) -> _DecoratorDefinition | None:
        return next(
            (definition for definition, _ in self.decorators(service_type, None) if definition.id == decorator_id),
            None,
        )

    def pre_configurations(
        self, service_type: Any, area: str | None = None
    ) -> list[tuple[_PreConfigurationDefinition, _Layer]]:
        layers = (
            self.layers
            if area is None
            else (() if self.boundary(area) is None else (cast(_BoundaryBlueprint, self.boundary(area)).layer,))
        )
        return [
            (configuration, layer)
            # Parent builders existed before their overlays, so initializer
            # declaration order proceeds from the root layer outwards.
            for layer in reversed(layers)
            for configuration in sorted(layer.pre_configurations, key=lambda item: item.order)
            if any(_decorator_service_matches(target, service_type) for target in configuration.service_types)
        ]

    def service_types(self, area: str | None = None) -> tuple[Any, ...]:
        values: list[Any] = []
        layers = (
            self.layers
            if area is None
            else (() if self.boundary(area) is None else (cast(_BoundaryBlueprint, self.boundary(area)).layer,))
        )
        for layer in layers:
            for service_type, registrations in layer.registry._registrations.items():
                if any(registration.id not in layer.internal_ids for registration in registrations):
                    values.append(service_type)
        return tuple(dict.fromkeys(values))

    def root_service_types(self) -> tuple[Any, ...]:
        values = list(self.service_types(None))
        values.extend(target.service_type for boundary in self.boundaries for target in boundary.resolved_exposes)
        values.extend(
            (_collection_request(entrypoint.service_type) or (None, entrypoint.service_type))[1]
            for entrypoint in self.entrypoints
        )
        values.extend(
            (_collection_request(entrypoint.service_type) or (None, entrypoint.service_type))[1]
            for boundary in self.boundaries
            for entrypoint in boundary.layer.entrypoints
        )
        return tuple(dict.fromkeys(values))


def _clone_registry(source: legacy._Registry) -> legacy._Registry:
    """Clone registry containers while retaining immutable composition objects."""

    target = legacy._Registry()
    target._registrations = defaultdict(
        deque,
        {service_type: deque(registrations) for service_type, registrations in source._registrations.items()},
    )
    target._decorators = defaultdict(legacy._DecoratorStore)
    for service_type, decorators in source._decorators.items():
        store = legacy._DecoratorStore()
        store._decorators = list(decorators._decorators)
        store.next_index = decorators.next_index
        target._decorators[service_type] = store
    return target


def _normalize_dependency_aliases(dependencies: dict[str, legacy.Dependency]) -> None:
    for dependency in dependencies.values():
        dependency.service_type = normalize_type_alias(dependency.service_type)
        origin = get_origin(dependency.service_type)
        dependency.generic_collection_type = dependency.GENERIC_COLLECTION_MAPPINGS.get(origin)


def _normalize_layer_aliases(layer: _Layer) -> _Layer:
    registry = _clone_registry(layer.registry)
    normalized_registrations: dict[Any, deque[legacy._Registration]] = defaultdict(deque)
    registration_copies: dict[int, legacy._Registration] = {}
    for key, registrations in layer.registry._registrations.items():
        canonical_key = normalize_type_alias(key)
        for source_registration in registrations:
            registration = registration_copies.get(id(source_registration))
            if registration is None:
                registration = copy.copy(source_registration)
                registration.dependencies = {
                    name: copy.copy(dependency) for name, dependency in source_registration.dependencies.items()
                }
                registration_copies[id(source_registration)] = registration
                canonical_service = normalize_type_alias(registration.service_type)
                if registration.id in layer.pattern_ids:
                    try:
                        patterns.validate_pattern(canonical_service)
                        if get_origin(canonical_service) in legacy.Dependency.GENERIC_COLLECTION_MAPPINGS or get_origin(
                            canonical_service
                        ) in (Provider, AsyncProvider):
                            raise patterns.PatternError(
                                "Synthetic collection and provider requests cannot be outer registration patterns"
                            )
                        annotations = (
                            *(normalize_type_alias(dep.service_type) for dep in registration.dependencies.values()),
                            _factory_result_annotation(registration.implementation),
                        )
                        patterns.factory_bindings(canonical_service, canonical_service, annotations)
                        if any(_unsupported_factory_type_parameters(annotation) for annotation in annotations):
                            raise patterns.PatternError("Pattern factories support TypeVar parameters only")
                    except patterns.PatternError as error:
                        raise ContainerBuildError(
                            str(error), code=error.code, path=(qualified_name(canonical_service),)
                        ) from error
                if registration.id in layer.provider_maps:
                    key_type, provider_type = get_args(canonical_service)
                    target_type = get_args(provider_type)[0]
                    if (
                        _typevars_in(canonical_service)
                        or getattr(key_type, "__parameters__", ())
                        or getattr(target_type, "__parameters__", ())
                        or registration.lifespan != legacy.Lifespan.transient
                        or registration.dependencies
                    ):
                        raise ContainerBuildError(
                            "Provider maps require closed key and target types, "
                            "transient lifespan, and no argument overrides",
                            code="provider-map-invalid-declaration",
                            path=(qualified_name(canonical_service),),
                        )
                canonical_implementation = normalize_type_alias(registration.implementation)
                if canonical_implementation is not registration.implementation:
                    settings = {name: dependency.settings for name, dependency in registration.dependencies.items()}
                    registration.implementation = canonical_implementation
                    registration.activator_class = registry._get_activator_class(canonical_implementation)
                    registration.dependencies = legacy._set_up_dependencies(canonical_implementation, settings)
                registration.service_type = canonical_service
                registration._generic_mapping = None
                _normalize_dependency_aliases(registration.dependencies)
                try:
                    _validate_service_groups(canonical_service, layer.service_groups.get(registration.id, ()))
                except TypeError as error:
                    raise ContainerBuildError(
                        str(error),
                        code="service-group-incompatible",
                        path=(qualified_name(canonical_service),),
                    ) from error
            normalized_registrations[canonical_key].append(registration)
    registry._registrations = defaultdict(deque, normalized_registrations)
    slots = frozenset((normalize_type_alias(service_type), name) for service_type, name in layer.slots)
    slot_origins = {
        (normalize_type_alias(service_type), name): origin
        for (service_type, name), origin in layer.slot_origins.items()
    }
    return replace(
        layer,
        registry=registry,
        factory_specializations={
            component_id: normalize_type_alias(value) for component_id, value in layer.factory_specializations.items()
        },
        decorators=tuple(
            replace(
                definition,
                service_type=normalize_type_alias(definition.service_type),
                decorator_type=normalize_type_alias(definition.decorator_type),
            )
            for definition in layer.decorators
        ),
        decorator_templates=tuple(
            replace(definition, for_each=normalize_type_alias(definition.for_each))
            for definition in layer.decorator_templates
        ),
        pre_configurations=tuple(
            replace(
                definition,
                service_types=tuple(normalize_type_alias(value) for value in definition.service_types),
            )
            for definition in layer.pre_configurations
        ),
        slots=slots,
        slot_origins=slot_origins,
        entrypoints=tuple(
            replace(entrypoint, service_type=normalize_type_alias(entrypoint.service_type))
            for entrypoint in layer.entrypoints
        ),
    )


def _normalize_blueprint_aliases(blueprint: _Blueprint) -> _Blueprint:
    layers = tuple(_normalize_layer_aliases(layer) for layer in blueprint.layers)
    boundaries = tuple(
        replace(
            boundary,
            layer=_normalize_layer_aliases(boundary.layer),
            uses=tuple(replace(use, service_type=normalize_type_alias(use.service_type)) for use in boundary.uses),
            exposes=tuple(
                replace(
                    expose,
                    service_type=normalize_type_alias(expose.service_type),
                    alias=(
                        expose.alias
                        if not isinstance(expose.alias, BoundaryAlias)
                        else replace(expose.alias, service_type=normalize_type_alias(expose.alias.service_type))
                    ),
                )
                for expose in boundary.exposes
            ),
        )
        for boundary in blueprint.boundaries
    )
    return replace(blueprint, layers=layers, boundaries=boundaries)


def _blueprint_alias_errors(blueprint: _Blueprint) -> tuple[TypeAliasNormalizationError, ...]:
    errors: list[TypeAliasNormalizationError] = []
    values: list[Any] = []
    layers = (*blueprint.layers, *(boundary.layer for boundary in blueprint.boundaries))
    for layer in layers:
        values.extend(layer.registry._registrations)
        for registrations in layer.registry._registrations.values():
            for registration in registrations:
                values.extend((registration.service_type, registration.implementation))
                values.extend(dependency.service_type for dependency in registration.dependencies.values())
        values.extend(layer.factory_specializations.values())
        values.extend(group.service_type for groups in layer.service_groups.values() for group in groups)
        for definition in layer.decorators:
            values.extend((definition.service_type, definition.decorator_type))
        values.extend(definition.for_each for definition in layer.decorator_templates)
        for definition in layer.pre_configurations:
            values.extend(definition.service_types)
        values.extend(service_type for service_type, _ in layer.slots)
        values.extend(entrypoint.service_type for entrypoint in layer.entrypoints)
    for boundary in blueprint.boundaries:
        values.extend(use.service_type for use in boundary.uses)
        values.extend(expose.service_type for expose in boundary.exposes)
        values.extend(
            expose.alias.service_type for expose in boundary.exposes if isinstance(expose.alias, BoundaryAlias)
        )
    for value in values:
        try:
            normalize_type_alias(value)
        except TypeAliasNormalizationError as error:
            errors.append(error)
    unique = {(error.code, alias_label(error.alias)): error for error in errors}
    return tuple(unique.values())


def _alias_error_report(errors: Iterable[TypeAliasNormalizationError]) -> BuildReport:
    return BuildReport(
        tuple(
            BuildIssue(
                code=error.code,
                severity=IssueSeverity.error,
                message=f"Type alias normalization failed [{error.code}].",
                root=None,
                path=(alias_label(error.alias),),
            )
            for error in errors
        ),
        checked_roots=0,
    )


_BOUNDARY_NAME = re.compile(r"^[a-z][a-z0-9_-]*$")
_UNCHANGED_COMPONENT_NAME = object()


def _service_definition_matches(definition: Any, request: Any) -> bool:
    if definition == request:
        return True
    request_origin = get_origin(request)
    if request_origin is None:
        return False
    if definition == request_origin:
        return True
    return get_origin(definition) == request_origin and bool(_typevars_in(definition))


def _public_service_matches(definition: Any, request: Any) -> bool:
    """Match a public contract structurally rather than by generic origin alone."""

    if definition == request:
        return True
    request_origin = get_origin(request)
    if request_origin is not None and definition == request_origin:
        return True
    if not patterns.variables(definition):
        return False
    try:
        return patterns.match(definition, request) is not None
    except patterns.PatternError:
        return False


def _tag_sort_key(tag: legacy.Tag) -> tuple[str, bool, str]:
    return (tag.name, tag.value is not None, tag.value or "")


def _exposure_target(
    boundary: str,
    exposure: Expose,
    registration: legacy._Registration,
) -> _VisibilityTarget:
    alias = exposure.alias
    public_tags = tuple(registration.tags) if alias is None else tuple(alias.tags)
    return _VisibilityTarget(
        boundary,
        exposure.service_type if alias is None else alias.service_type,
        registration.id,
        registration.name if alias is None else alias.name,
        public_tags,
        source_service_type=exposure.service_type,
        source_name=registration.name,
        source_tags=tuple(registration.tags),
    )


def _source_request_for_visibility(target: _VisibilityTarget, public_request: Any) -> Any:
    """Map a closed public alias request back onto its source declaration."""

    source = target.source_service_type
    if source is None or target.service_type == public_request:
        return source or public_request
    public_variables = patterns.variables(target.service_type)
    if not public_variables:
        return source
    bindings = patterns.match(target.service_type, public_request)
    if bindings is None:
        raise ContainerBuildError(
            "A boundary alias cannot map the public request onto its source service",
            code="boundary-alias-incompatible",
            path=(qualified_name(target.service_type), qualified_name(public_request)),
        )
    by_name = {variable.__name__: value for variable, value in bindings.items()}
    source_variables = patterns.variables(source)
    if len(source_variables) == len(public_variables):
        for source_variable, public_variable in zip(source_variables, public_variables, strict=True):
            by_name.setdefault(source_variable.__name__, bindings[public_variable])
    resolved = _resolve_factory_typevars(source, by_name)
    if _typevars_in(resolved):
        raise ContainerBuildError(
            "A boundary alias leaves source service TypeVars unresolved",
            code="boundary-alias-incompatible",
            path=(qualified_name(target.service_type), qualified_name(source)),
        )
    return resolved


def _boundary_component(
    registration: legacy._Registration,
    *,
    service_type: Any,
    build_args: Mapping[str, Any],
    boundary: str | None,
    name: str | None | object = _UNCHANGED_COMPONENT_NAME,
    tags: tuple[legacy.Tag, ...] | None = None,
) -> Component:
    """Create metadata-only input for an Expose/Use selection predicate."""

    graph = _ComponentGraph()
    component = graph.add(
        _ComponentDraft(
            id=registration.id,
            occurrence_id=1,
            service_type=service_type,
            implementation=registration.implementation,
            implementation_type=normalize_implementation_type(registration.implementation, service_type),
            lifespan=_component_lifespan(registration.lifespan),
            name=registration.name if name is _UNCHANGED_COMPONENT_NAME else cast(str | None, name),
            tags=tuple(registration.tags) if tags is None else tags,
            build_args=build_args,
            kind=ComponentKind.registration,
            activation=_registration_activation(registration),
            boundary=boundary,
        )
    )
    graph.freeze()
    return component


def _compiled_boundary_component(
    blueprint: _Blueprint,
    registration: legacy._Registration,
    layer: _Layer,
    *,
    service_type: Any,
    build_args: Mapping[str, Any],
    name: str | None | object = _UNCHANGED_COMPONENT_NAME,
    tags: tuple[legacy.Tag, ...] | None = None,
    public_service_type: Any | None = None,
) -> Component:
    """Compile one metadata occurrence so structural filters see its subtree."""

    compiler = _Compiler(blueprint, build_args=build_args)
    compiler._area = blueprint.registration_area(layer)
    if registration.id in layer.pattern_ids:
        registration = compiler._specialize_factory(registration, layer, service_type)
    component, _ = compiler._compile_registration(
        registration,
        layer,
        parent=None,
        argument=None,
        requested_service_type=service_type,
        origin=blueprint.registration_origin(registration.id, layer),
    )
    if name is not _UNCHANGED_COMPONENT_NAME:
        cast(_ComponentDraft, compiler.graph.record(component.occurrence_id)).name = cast(str | None, name)
    if tags is not None:
        cast(_ComponentDraft, compiler.graph.record(component.occurrence_id)).tags = tags
    if public_service_type is not None:
        cast(_ComponentDraft, compiler.graph.record(component.occurrence_id)).service_type = public_service_type
    compiler.graph.freeze()
    return component


def _boundary_registrations(
    blueprint: _Blueprint,
    layers: tuple[_Layer, ...],
    service_type: Any,
) -> list[tuple[legacy._Registration, _Layer]]:
    candidates = blueprint._registrations_in(layers, service_type)
    if not candidates:
        available = []
        if any(layer.pattern_ids for layer in layers):
            available = [
                candidate
                for layer in layers
                for component_id in reversed(layer.pattern_ids)
                if (candidate := blueprint.registration_definition(component_id)) is not None
                and get_origin(candidate[0].service_type) == get_origin(service_type)
            ]
        candidates = _winning_patterns(available, service_type)
    if not candidates and get_origin(service_type) is not None:
        candidates = blueprint._registrations_in(layers, get_origin(service_type))
    return candidates


def _winning_patterns(
    available: list[tuple[legacy._Registration, _Layer]], service_type: Any
) -> list[tuple[legacy._Registration, _Layer]]:
    if not available:
        return []
    try:
        patterns.validate_structure(service_type, symbolic=False)
        matching = [item for item in available if patterns.match(item[0].service_type, service_type) is not None]
        winners = [
            item
            for item in matching
            if not any(patterns.more_specific(other[0].service_type, item[0].service_type) for other in matching)
        ]
        if winners and any(
            patterns.match(winners[0][0].service_type, item[0].service_type) is None
            or patterns.match(item[0].service_type, winners[0][0].service_type) is None
            for item in winners[1:]
        ):
            raise patterns.PatternError(
                "Incomparable registration patterns match the same closed request", "pattern-ambiguous"
            )
        return winners
    except patterns.PatternError as error:
        raise ContainerBuildError(str(error), code=error.code, path=(qualified_name(service_type),)) from error


def _select_boundary_registrations(
    blueprint: _Blueprint,
    layers: tuple[_Layer, ...],
    service_type: Any,
    filter: ComponentFilter,
    *,
    build_args: Mapping[str, Any],
    boundary: str | None,
    code: str,
) -> list[tuple[legacy._Registration, _Layer]]:
    selected: list[tuple[legacy._Registration, _Layer]] = []
    for registration, layer in _boundary_registrations(blueprint, layers, service_type):
        try:
            component = _compiled_boundary_component(
                blueprint,
                registration,
                layer,
                service_type=service_type,
                build_args=build_args,
            )
        except ContainerBuildError:
            # Whole-container compilation reports invalid candidate subtrees with
            # their complete decision history. Metadata-only selection here
            # keeps boundary validation from masking that better diagnostic.
            component = _boundary_component(
                registration,
                service_type=service_type,
                build_args=build_args,
                boundary=blueprint.registration_area(layer),
            )
        try:
            matched = filter(component)
        except Exception as error:
            raise ContainerBuildError(
                f"Boundary filter {_filter_description(filter)} raised {type(error).__name__}",
                code=code,
                path=((boundary,) if boundary is not None else ()),
            ) from error
        if matched:
            selected.append((registration, layer))
    return selected


def _boundary_cycle(boundaries: tuple[_BoundaryBlueprint, ...]) -> tuple[str, ...] | None:
    graph = {
        boundary.name: tuple(use.source for use in boundary.uses if use.source is not None) for boundary in boundaries
    }
    visited: set[str] = set()
    active: list[str] = []

    def visit(name: str) -> tuple[str, ...] | None:
        if name in active:
            index = active.index(name)
            return (*active[index:], name)
        if name in visited:
            return None
        active.append(name)
        for dependency in graph.get(name, ()):
            cycle = visit(dependency)
            if cycle is not None:
                return cycle
        active.pop()
        visited.add(name)
        return None

    for name in graph:
        cycle = visit(name)
        if cycle is not None:
            return cycle
    return None


def _prepare_boundary_visibility(
    blueprint: _Blueprint,
    *,
    build_args: Mapping[str, Any],
) -> _Blueprint:
    """Validate and resolve every visibility declaration before plan compilation."""

    if not blueprint.boundaries:
        return blueprint
    names: set[str] = set()
    for boundary in blueprint.boundaries:
        if not isinstance(boundary.name, str) or boundary.name == "root" or not _BOUNDARY_NAME.fullmatch(boundary.name):
            raise ContainerBuildError(
                f"Invalid boundary name {boundary.name!r}; use ^[a-z][a-z0-9_-]*$ and do not use 'root'",
                code="boundary-invalid-name",
                path=(str(boundary.name),),
            )
        if boundary.name in names:
            code = "overlay-boundary-reopened" if boundary.root_layer_offset else "boundary-duplicate-name"
            raise ContainerBuildError(
                f"Boundary {boundary.name!r} is already installed and cannot be reopened",
                code=code,
                path=(boundary.name,),
            )
        names.add(boundary.name)
        if boundary.layer.slots:
            raise ContainerBuildError(
                f"Boundary {boundary.name!r} declares a private scope slot; private slots are not supported",
                code="boundary-scope-slot-unsupported",
                path=(boundary.name,),
            )
        if not all(isinstance(item, Expose) for item in boundary.exposes):
            raise TypeError("Boundary exposes must contain Expose declarations")
        if not all(isinstance(item, Use) for item in boundary.uses):
            raise TypeError("Boundary uses must contain Use declarations")
        if any(
            exposure.alias is not None and not isinstance(exposure.alias, BoundaryAlias)
            for exposure in boundary.exposes
        ):
            raise TypeError("Expose alias must be a BoundaryAlias or None")
        if any(
            exposure.alias is not None and exposure.alias.name is not None and not isinstance(exposure.alias.name, str)
            for exposure in boundary.exposes
        ):
            raise TypeError("BoundaryAlias name must be a string or None")
        if any(
            exposure.alias is not None
            and (
                not isinstance(exposure.alias.tags, tuple)
                or not all(isinstance(tag, legacy.Tag) for tag in exposure.alias.tags)
            )
            for exposure in boundary.exposes
        ):
            raise TypeError("BoundaryAlias tags must be a tuple of Tag values")
        for exposure in boundary.exposes:
            if exposure.alias is None:
                continue
            source_variables = patterns.variables(exposure.service_type)
            public_variables = patterns.variables(exposure.alias.service_type)
            if len(source_variables) != len(public_variables):
                raise ContainerBuildError(
                    "BoundaryAlias generic variables must map one-to-one between source and public services",
                    code="boundary-alias-incompatible",
                    path=(
                        boundary.name,
                        qualified_name(exposure.service_type),
                        qualified_name(exposure.alias.service_type),
                    ),
                )
    blueprint = replace(
        blueprint,
        boundaries=tuple(sorted(blueprint.boundaries, key=lambda item: item.name)),
    )
    cycle = _boundary_cycle(blueprint.boundaries)
    if cycle is not None:
        raise ContainerBuildError(
            f"Boundary use cycle: {' -> '.join(cycle)}",
            code="boundary-use-cycle",
            path=cycle,
        )

    # Give structural boundary filters a complete, conservative visibility
    # view. The exact one-component selections below replace these candidates
    # before normal compilation, so provisional visibility never reaches a
    # runtime plan.
    provisional_exposures: list[_BoundaryBlueprint] = []
    for boundary in blueprint.boundaries:
        targets = tuple(
            _exposure_target(boundary.name, exposure, registration)
            for exposure in boundary.exposes
            for registration, _ in _boundary_registrations(blueprint, (boundary.layer,), exposure.service_type)
        )
        provisional_exposures.append(replace(boundary, resolved_exposes=targets))
    blueprint = replace(blueprint, boundaries=tuple(provisional_exposures))

    provisional_uses: list[_BoundaryBlueprint] = []
    for boundary in blueprint.boundaries:
        targets: list[_VisibilityTarget] = []
        for use in boundary.uses:
            if use.source is None:
                source_layers = blueprint._root_layers_for(boundary)
                targets.extend(
                    _VisibilityTarget(
                        None,
                        use.service_type,
                        registration.id,
                        registration.name,
                        tuple(registration.tags),
                    )
                    for registration, _ in _boundary_registrations(blueprint, source_layers, use.service_type)
                )
                targets.extend(
                    _VisibilityTarget(None, slot_type, None, name, (), slot=True)
                    for layer in source_layers
                    for slot_type, name in layer.slots
                    if slot_type == use.service_type
                )
            else:
                source = blueprint.boundary(use.source)
                if source is not None:
                    targets.extend(
                        replace(target, source=source.name)
                        for target in source.resolved_exposes
                        if _public_service_matches(target.service_type, use.service_type)
                    )
        provisional_uses.append(replace(boundary, resolved_uses=tuple(targets)))
    blueprint = replace(blueprint, boundaries=tuple(provisional_uses))

    resolved: list[_BoundaryBlueprint] = []
    # Exposures are local-only, so all can be resolved before any Use.
    for boundary in blueprint.boundaries:
        targets: list[_VisibilityTarget] = []
        public_identities: set[tuple[Any, str | None, tuple[legacy.Tag, ...]]] = set()
        for exposure in boundary.exposes:
            matches = _select_boundary_registrations(
                blueprint,
                (boundary.layer,),
                exposure.service_type,
                exposure.filter,
                build_args=build_args,
                boundary=boundary.name,
                code="boundary-expose-not-found",
            )
            if not matches:
                # A matching import is a prohibited re-export rather than an absent local definition.
                imported = any(
                    _service_definition_matches(use.service_type, exposure.service_type) for use in boundary.uses
                )
                raise ContainerBuildError(
                    (
                        f"Boundary {boundary.name!r} cannot re-export used {exposure.service_type!r}"
                        if imported
                        else (
                            f"Boundary {boundary.name!r} exposes {exposure.service_type!r}, "
                            "but no local component matches"
                        )
                    ),
                    code=("boundary-reexport-unsupported" if imported else "boundary-expose-not-found"),
                    path=(boundary.name, qualified_name(exposure.service_type)),
                )
            if len(matches) != 1:
                raise ContainerBuildError(
                    f"Boundary {boundary.name!r} exposure for {exposure.service_type!r} "
                    f"matches {len(matches)} components",
                    code="boundary-expose-ambiguous",
                    path=(boundary.name, qualified_name(exposure.service_type)),
                )
            registration, _ = matches[0]
            target = _exposure_target(boundary.name, exposure, registration)
            public_identity = (
                target.service_type,
                target.name,
                tuple(sorted(target.tags, key=_tag_sort_key)),
            )
            if public_identity in public_identities:
                raise ContainerBuildError(
                    f"Boundary {boundary.name!r} declares the same public exposure identity more than once",
                    code="boundary-expose-ambiguous",
                    path=(boundary.name, qualified_name(target.service_type)),
                )
            public_identities.add(public_identity)
            targets.append(target)
        resolved.append(replace(boundary, resolved_exposes=tuple(targets)))
    blueprint = replace(blueprint, boundaries=tuple(resolved))

    completed: list[_BoundaryBlueprint] = []
    for boundary in blueprint.boundaries:
        targets: list[_VisibilityTarget] = []
        selected_keys: set[tuple[Any, ...]] = set()
        for use in boundary.uses:
            if use.source is None:
                source_layers = blueprint._root_layers_for(boundary)
                matches = _select_boundary_registrations(
                    blueprint,
                    source_layers,
                    use.service_type,
                    use.filter,
                    build_args=build_args,
                    boundary=boundary.name,
                    code="boundary-use-not-found",
                )
                slot_matches: list[tuple[Any, str | None]] = []
                for layer in source_layers:
                    for slot_type, name in layer.slots:
                        if slot_type != use.service_type:
                            continue
                        slot_component = _ComponentGraph()
                        component = slot_component.add(
                            _ComponentDraft(
                                id=f"slot:{slot_type!r}:{name}",
                                occurrence_id=1,
                                service_type=slot_type,
                                implementation=_ProvidedStep,
                                implementation_type=_ProvidedStep,
                                lifespan="scoped",
                                name=name,
                                tags=(),
                                build_args=build_args,
                                kind=ComponentKind.scope_slot,
                                activation=ComponentActivation.supplied,
                            )
                        )
                        if use.filter(component):
                            slot_matches.append((slot_type, name))
                if len(matches) + len(slot_matches) == 0:
                    raise ContainerBuildError(
                        f"Boundary {boundary.name!r} uses root {use.service_type!r}, but no root component matches",
                        code="boundary-use-not-found",
                        path=(boundary.name, "root", qualified_name(use.service_type)),
                    )
                if len(matches) + len(slot_matches) != 1:
                    raise ContainerBuildError(
                        f"Boundary {boundary.name!r} use of root {use.service_type!r} matches multiple components",
                        code="boundary-use-ambiguous",
                        path=(boundary.name, "root", qualified_name(use.service_type)),
                    )
                if matches:
                    registration, _ = matches[0]
                    target = _VisibilityTarget(
                        None, use.service_type, registration.id, registration.name, tuple(registration.tags)
                    )
                else:
                    slot_type, name = slot_matches[0]
                    target = _VisibilityTarget(None, slot_type, None, name, (), slot=True)
            else:
                source = blueprint.boundary(use.source)
                if source is None or source.root_layer_offset < boundary.root_layer_offset:
                    raise ContainerBuildError(
                        f"Boundary {boundary.name!r} uses unknown source boundary {use.source!r}",
                        code="boundary-use-source-not-found",
                        path=(boundary.name, use.source),
                    )
                exposure_targets = [
                    target
                    for target in source.resolved_exposes
                    if _public_service_matches(target.service_type, use.service_type)
                ]
                selected: list[_VisibilityTarget] = []
                for target in exposure_targets:
                    definition = blueprint.registration_definition(cast(str, target.registration_id))
                    if definition is None:
                        continue
                    registration, layer = definition
                    try:
                        source_request = _source_request_for_visibility(target, use.service_type)
                        component = _compiled_boundary_component(
                            blueprint,
                            registration,
                            layer,
                            service_type=source_request,
                            build_args=build_args,
                            name=target.name,
                            tags=target.tags,
                            public_service_type=use.service_type,
                        )
                    except ContainerBuildError:
                        component = _boundary_component(
                            registration,
                            service_type=use.service_type,
                            build_args=build_args,
                            boundary=blueprint.registration_area(layer),
                            name=target.name,
                            tags=target.tags,
                        )
                    if use.filter(component):
                        selected.append(target)
                if not selected:
                    local_private = bool(_boundary_registrations(blueprint, (source.layer,), use.service_type))
                    message = (
                        f"Boundary {source.name!r} has matching private components; expose one before "
                        f"boundary {boundary.name!r} can use it"
                        if local_private
                        else (
                            f"Boundary {boundary.name!r} use of {use.service_type!r} "
                            f"from {source.name!r} was not found"
                        )
                    )
                    raise ContainerBuildError(
                        message,
                        code="boundary-use-not-found",
                        path=(boundary.name, source.name, qualified_name(use.service_type)),
                    )
                if len(selected) != 1:
                    raise ContainerBuildError(
                        f"Boundary {boundary.name!r} use of {use.service_type!r} from {source.name!r} is ambiguous",
                        code="boundary-use-ambiguous",
                        path=(boundary.name, source.name, qualified_name(use.service_type)),
                    )
                selected_target = selected[0]
                target = replace(selected_target, source=source.name)
            key = (
                target.source,
                target.registration_id or target.name,
                target.service_type,
                target.name,
                target.tags,
                target.slot,
            )
            if key in selected_keys:
                raise ContainerBuildError(
                    f"Boundary {boundary.name!r} uses the same component more than once",
                    code="boundary-use-ambiguous",
                    path=(boundary.name, qualified_name(use.service_type)),
                )
            selected_keys.add(key)
            targets.append(target)
        completed.append(replace(boundary, resolved_uses=tuple(targets)))
    blueprint = replace(blueprint, boundaries=tuple(completed))

    for area, layers in (
        (None, blueprint.layers),
        *((boundary.name, (boundary.layer,)) for boundary in blueprint.boundaries),
    ):
        for layer in layers:
            decorated_types = tuple(decorator.service_type for decorator in layer.decorators)
            configured_types = tuple(
                target for configuration in layer.pre_configurations for target in configuration.service_types
            )
            for target_type in (*decorated_types, *configured_types):
                local_match = any(
                    _decorator_service_matches(target_type, service_type)
                    for service_type in blueprint.service_types(area)
                )
                if local_match:
                    continue
                visible_targets = (
                    (target for boundary in blueprint.boundaries for target in boundary.resolved_exposes)
                    if area is None
                    else (
                        target
                        for target in cast(_BoundaryBlueprint, blueprint.boundary(area)).resolved_uses
                        if not target.slot
                    )
                )
                if any(_decorator_service_matches(target_type, target.service_type) for target in visible_targets):
                    label = "root" if area is None else f"boundary {area!r}"
                    raise ContainerBuildError(
                        f"A decorator or pre-configuration in {label} targets only a component across a boundary",
                        code="boundary-cross-boundary-decoration",
                        path=(("root",) if area is None else (area, qualified_name(target_type))),
                    )
    return blueprint


_NO_TYPEVAR_DEFAULT = object()


def _runtime_type_key(value: Any) -> tuple[Any, ...]:
    """Return a process-stable structural key for a closed runtime type."""

    origin = get_origin(value)
    if origin is not None:
        return ("generic", id(origin), tuple(_runtime_type_key(argument) for argument in get_args(value)))
    if isinstance(value, TypeVar):
        return ("typevar", id(value))
    if isinstance(value, (list, tuple)):
        return ("sequence", type(value).__name__, tuple(_runtime_type_key(item) for item in value))
    if value is None or isinstance(value, (bool, bytes, int, str)):
        return ("literal", type(value).__module__, type(value).__qualname__, repr(value))
    return ("object", id(value))


def _decorator_service_matches(rule_service_type: Any, service_type: Any) -> bool:
    if rule_service_type == service_type:
        return True
    service_origin = get_origin(service_type)
    if service_origin is None:
        return False
    if rule_service_type == service_origin:
        return True
    return get_origin(rule_service_type) == service_origin and bool(_typevars_in(rule_service_type))


def _specialized_component_id(component_id: str, service_type: Any) -> str:
    """Derive the same closed-template ID in every compiler in this process."""

    try:
        namespace = UUID(component_id)
    except ValueError:
        namespace = UUID(int=0)
    return str(uuid5(namespace, repr((component_id, _runtime_type_key(service_type)))))


def _typevars_in(annotation: Any) -> tuple[TypeVar, ...]:
    found: dict[str, TypeVar] = {}

    def visit(value: Any) -> None:
        if isinstance(value, TypeVar):
            found.setdefault(value.__name__, value)
            return
        if isinstance(value, (list, tuple)):
            for item in value:
                visit(item)
            return
        for item in get_args(value):
            visit(item)

    visit(annotation)
    return tuple(found.values())


def _unsupported_factory_type_parameters(annotation: Any) -> tuple[str, ...]:
    parameter_types = tuple(
        cast(type, parameter_type)
        for parameter_type in (getattr(typing, "ParamSpec", None), getattr(typing, "TypeVarTuple", None))
        if parameter_type is not None
    )
    found: set[str] = set()

    def visit(value: Any) -> None:
        parameter = value if isinstance(value, parameter_types) else get_origin(value)
        if isinstance(parameter, parameter_types):
            found.add(f"{type(parameter).__name__} {parameter.__name__}")
            return
        if isinstance(value, (list, tuple)):
            for item in value:
                visit(item)
            return
        for item in get_args(value):
            visit(item)

    visit(annotation)
    return tuple(sorted(found))


def _merge_factory_binding(
    bindings: dict[str, Any],
    typevar: TypeVar,
    value: Any,
    *,
    factory: Callable[..., Any],
    service_type: Any,
) -> None:
    value = _resolve_factory_typevars(value, bindings)
    if isinstance(value, TypeVar) and value.__name__ == typevar.__name__:
        return
    name = typevar.__name__
    existing = bindings.get(name, _NO_TYPEVAR_DEFAULT)
    if existing is _NO_TYPEVAR_DEFAULT:
        bindings[name] = value
        return
    existing = _resolve_factory_typevars(existing, bindings, resolving=frozenset({name}))
    if existing != value:
        raise ContainerBuildError(
            f"Conflicting TypeVar {name!r} for factory {qualified_name(factory)} while compiling "
            f"{qualified_name(service_type)}: incompatible resolved bindings"
        )


def _infer_factory_bindings(
    pattern: Any,
    concrete: Any,
    bindings: dict[str, Any],
    typevars: dict[str, TypeVar],
    *,
    factory: Callable[..., Any],
    service_type: Any,
) -> None:
    if isinstance(pattern, TypeVar):
        if pattern.__name__ in typevars:
            _merge_factory_binding(
                bindings,
                pattern,
                concrete,
                factory=factory,
                service_type=service_type,
            )
        return
    pattern_origin = get_origin(pattern)
    concrete_origin = get_origin(concrete)
    pattern_arguments = get_args(pattern)
    concrete_arguments = get_args(concrete)
    if pattern_origin is None or concrete_origin is None or pattern_origin != concrete_origin:
        return
    if len(pattern_arguments) != len(concrete_arguments):
        return
    for pattern_argument, concrete_argument in zip(pattern_arguments, concrete_arguments, strict=True):
        _infer_factory_bindings(
            pattern_argument,
            concrete_argument,
            bindings,
            typevars,
            factory=factory,
            service_type=service_type,
        )


def _factory_result_annotation(factory: Callable[..., Any]) -> Any:
    try:
        annotation = typing.get_type_hints(factory).get("return", inspect.Signature.empty)
    except (NameError, TypeError):
        annotation = inspect.signature(factory).return_annotation
    if annotation is not inspect.Signature.empty:
        annotation = normalize_type_alias(annotation)
    target = inspect.unwrap(factory)
    if inspect.isgeneratorfunction(target) or inspect.isasyncgenfunction(target):
        arguments = get_args(annotation)
        annotation = arguments[0] if arguments else inspect.Signature.empty
    return annotation


def _specialized_factory_dependencies(
    registration: legacy._Registration,
    service_type: Any,
    explicit_specialization: object | None,
) -> tuple[dict[str, legacy.Dependency], tuple[tuple[str, Any, Any], ...]]:
    factory = cast(Callable[..., Any], registration.implementation)
    result_annotation = _factory_result_annotation(factory)
    annotations = (
        *(dependency.service_type for dependency in registration.dependencies.values()),
        result_annotation,
    )
    unsupported = sorted(
        {item for annotation in annotations for item in _unsupported_factory_type_parameters(annotation)}
    )
    if unsupported:
        names = ", ".join(unsupported)
        raise ContainerBuildError(
            f"Unsupported generic factory type parameter(s) {names} for factory {qualified_name(factory)}; "
            "only TypeVar is supported"
        )
    typevars = {item.__name__: item for annotation in annotations for item in _typevars_in(annotation)}
    if not typevars:
        return registration.dependencies, ()

    bindings: dict[str, Any] = {}
    service_mapping = GenericTypeMap(service_type)
    for name, typevar in typevars.items():
        mapped = service_mapping.get(name, _NO_TYPEVAR_DEFAULT)
        if mapped is not _NO_TYPEVAR_DEFAULT:
            _merge_factory_binding(
                bindings,
                typevar,
                mapped,
                factory=factory,
                service_type=service_type,
            )

    if result_annotation is not inspect.Signature.empty:
        _infer_factory_bindings(
            result_annotation,
            service_type,
            bindings,
            typevars,
            factory=factory,
            service_type=service_type,
        )

    if explicit_specialization is not None:
        try:
            explicit_mapping = get_generic_mapping(explicit_specialization)
        except (TypeError, ValueError) as error:
            raise ContainerBuildError(
                f"Invalid factory_specialization for factory {qualified_name(factory)}"
            ) from error
        for name, typevar in typevars.items():
            mapped = explicit_mapping.get(name, _NO_TYPEVAR_DEFAULT)
            if mapped is not _NO_TYPEVAR_DEFAULT:
                _merge_factory_binding(
                    bindings,
                    typevar,
                    mapped,
                    factory=factory,
                    service_type=service_type,
                )

    no_default = getattr(typing, "NoDefault", _NO_TYPEVAR_DEFAULT)
    for name, typevar in typevars.items():
        if name in bindings:
            continue
        default = getattr(typevar, "__default__", _NO_TYPEVAR_DEFAULT)
        if default is _NO_TYPEVAR_DEFAULT or default is no_default:
            continue
        _merge_factory_binding(
            bindings,
            typevar,
            _resolve_factory_typevars(default, bindings),
            factory=factory,
            service_type=service_type,
        )

    unresolved = sorted(
        name for name, typevar in typevars.items() if _typevars_in(_resolve_factory_typevars(typevar, bindings))
    )
    if unresolved:
        names = ", ".join(unresolved)
        raise ContainerBuildError(
            f"Unable to resolve TypeVar(s) {names} for factory {qualified_name(factory)} while compiling "
            f"{qualified_name(service_type)}; "
            "register a closed generic service or pass factory_specialization="
        )

    dependencies: dict[str, legacy.Dependency] = {}
    annotations: list[tuple[str, Any, Any]] = []
    for name, dependency in registration.dependencies.items():
        before = dependency.declared_service_type
        after = _resolve_factory_typevars(dependency.service_type, bindings)
        specialized = legacy.Dependency(
            name=dependency.name,
            parent_implementation=factory,
            service_type=after,
            settings=dependency.settings,
            default_value=dependency.default_value,
        )
        specialized.declared_service_type = _resolve_factory_typevars(dependency.declared_service_type, bindings)
        dependencies[name] = specialized
        annotations.append((name, before, after))
    return dependencies, tuple(annotations)


def _index_registration(registry: legacy._Registry, registration: legacy._Registration) -> None:
    registry._registrations[registration.service_type].appendleft(registration)
    registry._registrations[cast(type, registration.implementation)].appendleft(registration)


def _create_discovered_registration(
    *,
    service_type: Any,
    implementation_type: type,
    lifespan: legacy.Lifespan,
    name: str | None,
    tags: tuple[legacy.Tag, ...],
) -> legacy._Registration:
    registry = legacy._Registry()
    component_id = registry.register_implementation(
        service_type=service_type,
        implementation=implementation_type,
        lifespan=lifespan,
        name=name,
        dependency_config={},
        tags=tags,
        parent_node_filter=legacy.default_parent_node_filter,
    )
    return next(
        registration for registration in registry.get_registrations(service_type) if registration.id == component_id
    )


def _unique_subclasses(base_type: type, filter: Callable[[type], bool]) -> tuple[type, ...]:
    found: list[type] = []
    seen: set[int] = set()
    for subclass in legacy.get_subclasses(base_type, filter=filter):
        identity = id(subclass)
        if identity in seen:
            continue
        seen.add(identity)
        found.append(subclass)
    return tuple(found)


def _module_imports(value: str | Iterable[str]) -> tuple[str, ...]:
    modules = (value,) if isinstance(value, str) else tuple(value)
    if any(not isinstance(module, str) or not module for module in modules):
        raise TypeError("ensure_import_modules must be a module name or an iterable of module names")
    return tuple(dict.fromkeys(modules))


def _ensure_discovery_imports(rules: Iterable[_RegistrationDiscovery]) -> tuple[str, ...]:
    ensured: list[str] = []
    seen: set[str] = set()
    traversed_packages: set[str] = set()

    def ensure(module_name: str) -> types.ModuleType:
        module = importlib.import_module(module_name)
        if module.__name__ not in seen:
            seen.add(module.__name__)
            ensured.append(module.__name__)
        return module

    for rule in rules:
        for module_name in rule.ensure_import_modules:
            module = ensure(module_name)
            if not rule.include_children or module.__name__ in traversed_packages:
                continue
            traversed_packages.add(module.__name__)
            package_path = getattr(module, "__path__", None)
            if package_path is None:
                continue
            child_names = sorted(
                module_info.name for module_info in pkgutil.walk_packages(package_path, prefix=f"{module.__name__}.")
            )
            for child_name in child_names:
                ensure(child_name)
    return tuple(ensured)


@dataclass(slots=True)
class _RegistrationDiscovery:
    base_type: type
    generic: bool
    fallback_type: type | None
    ensure_import_modules: tuple[str, ...]
    include_children: bool
    lifespan: legacy.Lifespan
    subclass_type_filter: Callable[[type], bool]
    name: str | None
    tags: tuple[legacy.Tag, ...]
    when: ComponentFilter
    groups: frozenset[ServiceGroup]
    origin: DefinitionOrigin
    registrations: dict[int, tuple[type, legacy._Registration]] = field(default_factory=dict)
    fallback_registration: legacy._Registration | None = None

    def _filter(self, subclass: type) -> bool:
        if inspect.isabstract(subclass) or not self.subclass_type_filter(subclass):
            return False
        return not self.generic or not subclass.__name__.startswith("__DecoratedGeneric__")

    def _registration_for(self, subclass: type, service_type: Any) -> legacy._Registration:
        cached = self.registrations.get(id(subclass))
        if cached is not None and cached[0] is subclass:
            return cached[1]
        registration = _create_discovered_registration(
            service_type=service_type,
            implementation_type=subclass,
            lifespan=self.lifespan,
            name=self.name,
            tags=self.tags,
        )
        self.registrations[id(subclass)] = (subclass, registration)
        return registration

    def materialize(
        self,
        registry: legacy._Registry,
        registration_when: dict[str, ComponentFilter],
        registration_origins: dict[str, DefinitionOrigin],
        service_groups: dict[str, frozenset[ServiceGroup]],
    ) -> None:
        candidates: list[tuple[type, Any]] = []
        for subclass in _unique_subclasses(self.base_type, self._filter):
            service_type: Any = self.base_type
            if self.generic:
                service_type = legacy.Container._get_target_generic_base(self.base_type, subclass)
                if service_type is None:
                    continue
            _validate_service_groups(service_type, self.groups)
            candidates.append((subclass, service_type))
        if self.generic and self.fallback_type is not None:
            _validate_service_groups(self.base_type, self.groups)
        for subclass, service_type in candidates:
            registration = self._registration_for(subclass, service_type)
            _index_registration(registry, registration)
            registration_when[registration.id] = self.when
            service_groups[registration.id] = self.groups
            registration_origins[registration.id] = replace(
                self.origin,
                definition_id=registration.id,
            )

        if self.generic and self.fallback_type is not None:
            if self.fallback_registration is None:
                self.fallback_registration = _create_discovered_registration(
                    service_type=self.base_type,
                    implementation_type=self.fallback_type,
                    lifespan=self.lifespan,
                    name=self.name,
                    tags=self.tags,
                )
            _index_registration(registry, self.fallback_registration)
            registration_when[self.fallback_registration.id] = self.when
            service_groups[self.fallback_registration.id] = self.groups
            registration_origins[self.fallback_registration.id] = replace(
                self.origin,
                definition_id=self.fallback_registration.id,
            )

    def find_registration(self, service_type: Any, component_id: str) -> legacy._Registration | None:
        candidates = (item[1] for item in self.registrations.values())
        for registration in candidates:
            if registration.service_type == service_type and registration.id == component_id:
                return registration
        fallback = self.fallback_registration
        if fallback is not None and fallback.service_type == service_type and fallback.id == component_id:
            return fallback
        return None


@dataclass(frozen=True, slots=True)
class _CompiledDependency:
    name: str
    step: _Step


class _Step:
    sync_supported = True

    def resolve(self, context: _RuntimeResolutionContext) -> Any:
        raise NotImplementedError

    async def resolve_async(self, context: _RuntimeResolutionContext) -> Any:
        raise NotImplementedError


@dataclass(frozen=True, slots=True)
class _CleanupOwnerDescriptor:
    """Private executable owner selected by compilation."""

    kind: RuntimeOwnerKind
    owner_token: str | None = None


_NO_CLEANUP_OWNER = _CleanupOwnerDescriptor(RuntimeOwnerKind.none)
_SCOPE_CLEANUP_OWNER = _CleanupOwnerDescriptor(RuntimeOwnerKind.scope)


@dataclass(frozen=True, slots=True)
class _ActivationContext:
    """Bind one immutable cleanup decision to one user-code activation."""

    runtime: _RuntimeResolutionContext
    cleanup_owner: _CleanupOwnerDescriptor

    def add_finalizer(self, lifespan: legacy.Lifespan, finalizer: Callable[..., Any]) -> None:
        del lifespan
        self.runtime.add_finalizer(self.cleanup_owner, finalizer)


@dataclass(frozen=True, slots=True)
class _CompiledResolutionRequest:
    request: _ResolutionRequest
    step: _Step
    component: Component


_CACHE_MISS = object()
_EMPTY_DEPENDENCIES: dict[str, Any] = {}
_RUNTIME_ID_LOCK = threading.Lock()


@dataclass(frozen=True, slots=True)
class _ValueStep(_Step):
    value: Any

    def resolve(self, context: _RuntimeResolutionContext) -> Any:
        return self.value

    async def resolve_async(self, context: _RuntimeResolutionContext) -> Any:
        return self.value


@dataclass(frozen=True, slots=True)
class _ProvidedStep(_Step):
    service_type: Any
    name: str | None

    def resolve(self, context: _RuntimeResolutionContext) -> Any:
        return context.scope._find_provision(self.service_type, self.name)

    async def resolve_async(self, context: _RuntimeResolutionContext) -> Any:
        return self.resolve(context)


@dataclass(frozen=True, slots=True)
class _ScopeStep(_Step):
    requested_type: Any
    resolution_requests: tuple[_CompiledResolutionRequest, ...] = ()

    def resolve(self, context: _RuntimeResolutionContext) -> Any:
        if self.requested_type is Container:
            return context.scope.container
        if self.requested_type in (ResolutionContext, legacy.CurrentGraph):
            return ResolutionContext(context, self.resolution_requests)
        return context.scope

    async def resolve_async(self, context: _RuntimeResolutionContext) -> Any:
        return self.resolve(context)


@dataclass(frozen=True, slots=True)
class _CollectionStep(_Step):
    collection_type: type
    members: tuple[_Step, ...]
    sync_supported: bool

    def resolve(self, context: _RuntimeResolutionContext) -> Any:
        return self.collection_type(member.resolve(context) for member in self.members)

    async def resolve_async(self, context: _RuntimeResolutionContext) -> Any:
        values = await asyncio.gather(*(member.resolve_async(context) for member in self.members))
        return self.collection_type(values)


class _FrozenProvider:
    """Private runtime implementation of :class:`Provider`."""

    __slots__ = ("_scope", "_step")

    def __init__(self, scope: Scope, step: _Step) -> None:
        self._scope = scope
        self._step = step

    def __call__(self) -> Any:
        try:
            self._scope._ensure_open()
        except ScopeClosedError as error:
            raise ProviderScopeClosedError("The provider's bound scope is closed") from error
        context = _RuntimeResolutionContext(self._scope)
        try:
            if not self._step.sync_supported:
                raise RuntimeError("The provider target requires AsyncProvider")
            return self._step.resolve(context)
        finally:
            context.finish()


class _FrozenAsyncProvider:
    """Private runtime implementation of :class:`AsyncProvider`."""

    __slots__ = ("_scope", "_step")

    def __init__(self, scope: Scope, step: _Step) -> None:
        self._scope = scope
        self._step = step

    async def __call__(self) -> Any:
        try:
            self._scope._ensure_open()
        except ScopeClosedError as error:
            raise ProviderScopeClosedError("The provider's bound scope is closed") from error
        context = _RuntimeResolutionContext(self._scope)
        try:
            return await self._step.resolve_async(context)
        finally:
            context.finish()


@dataclass(frozen=True, slots=True)
class _ProviderStep(_Step):
    mode: str
    target: _Step
    bound_owner_token: str | None = None
    sync_supported: bool = True

    def _bound_scope(self, context: _RuntimeResolutionContext) -> Scope:
        if self.bound_owner_token is None:
            return context.scope
        owner = context.scope._owners[self.bound_owner_token]
        if not isinstance(owner, Scope):
            raise RuntimeError("A provider singleton owner must also be a scope")
        return owner

    def resolve(self, context: _RuntimeResolutionContext) -> Any:
        scope = self._bound_scope(context)
        if self.mode == "sync":
            return _FrozenProvider(scope, self.target)
        return _FrozenAsyncProvider(scope, self.target)

    async def resolve_async(self, context: _RuntimeResolutionContext) -> Any:
        return self.resolve(context)


@dataclass(frozen=True, slots=True)
class _PreConfigurationOutcome:
    error: BaseException | None = None


@dataclass(slots=True)
class _PreConfigurationState:
    completed: bool = False
    in_flight: concurrent.futures.Future[_PreConfigurationOutcome] | None = None
    lock: threading.Lock = field(default_factory=threading.Lock)

    def begin(self) -> tuple[concurrent.futures.Future[_PreConfigurationOutcome] | None, bool]:
        with self.lock:
            if self.completed:
                return None, False
            if self.in_flight is not None:
                return self.in_flight, False
            future: concurrent.futures.Future[_PreConfigurationOutcome] = concurrent.futures.Future()
            self.in_flight = future
            return future, True

    def finish(
        self,
        future: concurrent.futures.Future[_PreConfigurationOutcome],
        *,
        completed: bool = False,
        error: BaseException | None = None,
    ) -> None:
        with self.lock:
            if self.in_flight is future:
                self.completed = completed
                self.in_flight = None
        future.set_result(_PreConfigurationOutcome(error))


@dataclass(slots=True)
class _CompiledPreConfiguration:
    definition: _PreConfigurationDefinition
    activator_class: type[legacy.Activator]
    dependencies: tuple[_CompiledDependency, ...]
    component: Component
    state: _PreConfigurationState
    owner_token: str
    cleanup_owner: _CleanupOwnerDescriptor
    sync_supported: bool

    def run(self, context: _RuntimeResolutionContext) -> None:
        future, builder = self.state.begin()
        if future is None:
            return
        if not builder:
            outcome = future.result()
            if outcome.error is not None:
                raise outcome.error
            return
        try:
            values = (
                {dependency.name: dependency.step.resolve(context) for dependency in self.dependencies}
                if self.dependencies
                else _EMPTY_DEPENDENCIES
            )
        except BaseException as error:
            self.state.finish(future, error=error)
            raise
        try:
            self.activator_class.activate(
                self.definition.configuration_fn,
                values,
                cast(Any, _ActivationContext(context, self.cleanup_owner)),
                legacy.Lifespan.singleton,
            )
        except Exception as error:
            if not self.definition.continue_on_failure:
                self.state.finish(future, error=error)
                raise
            logger.exception("Failed to run pre-configuration %r", self.definition.configuration_fn)
            self.state.finish(future, completed=True)
        except BaseException as error:
            self.state.finish(future, error=error)
            raise
        else:
            self.state.finish(future, completed=True)

    async def run_async(self, context: _RuntimeResolutionContext) -> None:
        future, builder = self.state.begin()
        if future is None:
            return
        if not builder:
            outcome = await asyncio.shield(asyncio.wrap_future(future))
            if outcome.error is not None:
                raise outcome.error
            return
        try:
            values = (
                {dependency.name: await dependency.step.resolve_async(context) for dependency in self.dependencies}
                if self.dependencies
                else _EMPTY_DEPENDENCIES
            )
        except BaseException as error:
            self.state.finish(future, error=error)
            raise
        try:
            await self.activator_class.activate_async(
                self.definition.configuration_fn,
                values,
                cast(Any, _ActivationContext(context, self.cleanup_owner)),
                legacy.Lifespan.singleton,
            )
        except Exception as error:
            if not self.definition.continue_on_failure:
                self.state.finish(future, error=error)
                raise
            logger.exception("Failed to run pre-configuration %r", self.definition.configuration_fn)
            self.state.finish(future, completed=True)
        except BaseException as error:
            self.state.finish(future, error=error)
            raise
        else:
            self.state.finish(future, completed=True)


@dataclass(frozen=True, slots=True)
class _DecoratorActivation:
    definition: _DecoratorDefinition
    implementation: type | Callable[..., Any]
    activator_class: type[legacy.Activator]
    decorated_arg: str
    dependencies: dict[str, legacy.Dependency]


def _decorated_dependency_matches(annotation: Any, service_type: Any) -> bool:
    annotation = normalize_type_alias(annotation)
    service_type = normalize_type_alias(service_type)
    if annotation == service_type:
        return True
    annotation_origin = get_origin(annotation)
    service_origin = get_origin(service_type)
    return annotation_origin is not None and annotation_origin == service_origin and bool(_typevars_in(annotation))


def _specialize_decorator_implementation(
    decorator_type: Any,
    bindings: dict[str, Any],
) -> Any:
    if not isinstance(decorator_type, type):
        return decorator_type
    parameters = tuple(getattr(decorator_type, "__parameters__", ()))
    if not parameters:
        return decorator_type
    arguments = tuple(_resolve_factory_typevars(parameter, bindings) for parameter in parameters)
    unresolved = [
        parameter.__name__ for parameter, value in zip(parameters, arguments, strict=True) if _typevars_in(value)
    ]
    if unresolved:
        raise ContainerBuildError(f"Unable to resolve decorator TypeVar(s) {', '.join(unresolved)}")
    specialization = cast(Any, decorator_type)[arguments[0] if len(arguments) == 1 else arguments]
    return legacy.create_generic_decorator_type(specialization)


def _decorator_result_matches_service(result_type: Any, service_type: Any) -> bool:
    if result_type is not inspect.Signature.empty:
        result_type = normalize_type_alias(result_type)
    service_type = normalize_type_alias(service_type)
    if result_type in (Any, inspect.Signature.empty) or result_type == service_type:
        return True
    result_origin = get_origin(result_type) or result_type
    service_origin = get_origin(service_type) or service_type
    if not isinstance(result_origin, type) or not isinstance(service_origin, type):
        return False
    try:
        return issubclass(result_origin, service_origin)
    except TypeError:
        return False


def _materialize_decorator(
    definition: _DecoratorDefinition,
    service_type: Any,
    implementation_type: type,
) -> _DecoratorActivation:
    label = qualified_name(definition.decorator_type)
    source: type | Callable[..., Any] = definition.decorator_type
    if isinstance(source, type) and GenericTypeMap(source).is_mapping_generic():
        projected = legacy.try_to_map_generic_args_to_specialization(source, implementation_type)
        if GenericTypeMap(projected).is_mapping_specialized():
            source = legacy.create_generic_decorator_type(cast(type, projected))
    try:
        dependencies = legacy._set_up_dependencies(
            source,
            cast(Any, _arguments_to_dependency_config(definition.arguments)),
        )
        _validate_dependency_names(source, dependencies)
    except Exception as error:
        raise ContainerBuildError(
            f"Decorator {label} has an invalid signature: {error}",
            code="invalid-decorator",
        ) from error

    if definition.decorated_arg is not None:
        if definition.decorated_arg not in dependencies:
            raise ContainerBuildError(
                f"Decorator {label} has no argument named {definition.decorated_arg!r}",
                code="invalid-decorator",
            )
        decorated_arg = definition.decorated_arg
    else:
        candidates = [
            name
            for name, dependency in dependencies.items()
            if _decorated_dependency_matches(dependency.service_type, service_type)
        ]
        if not candidates:
            raise ContainerBuildError(
                f"Decorator {label} has no argument for {qualified_name(service_type)}; set decorated_arg= explicitly",
                code="invalid-decorator",
            )
        if len(candidates) > 1:
            names = ", ".join(candidates)
            raise ContainerBuildError(
                f"Decorator {label} has multiple arguments for {qualified_name(service_type)} ({names}); "
                "set decorated_arg= explicitly",
                code="invalid-decorator",
            )
        decorated_arg = candidates[0]

    decorated_dependency = dependencies.pop(decorated_arg)
    annotations = tuple(dependency.service_type for dependency in (decorated_dependency, *dependencies.values()))
    typevars = {item.__name__: item for annotation in annotations for item in _typevars_in(annotation)}
    bindings: dict[str, Any] = {}
    try:
        _infer_factory_bindings(
            decorated_dependency.service_type,
            service_type,
            bindings,
            typevars,
            factory=definition.decorator_type,
            service_type=service_type,
        )
    except ContainerBuildError as error:
        raise ContainerBuildError(
            f"Decorator {label} has conflicting generic bindings for {qualified_name(service_type)}: {error}",
            code="invalid-decorator",
        ) from error

    no_default = getattr(typing, "NoDefault", _NO_TYPEVAR_DEFAULT)
    for name, typevar in typevars.items():
        if name in bindings:
            continue
        default = getattr(typevar, "__default__", _NO_TYPEVAR_DEFAULT)
        if default is _NO_TYPEVAR_DEFAULT or default is no_default:
            continue
        _merge_factory_binding(
            bindings,
            typevar,
            _resolve_factory_typevars(default, bindings),
            factory=source,
            service_type=service_type,
        )

    unresolved = sorted(
        name for name, typevar in typevars.items() if _typevars_in(_resolve_factory_typevars(typevar, bindings))
    )
    if unresolved:
        raise ContainerBuildError(
            f"Decorator {label} cannot resolve TypeVar(s) {', '.join(unresolved)} for "
            f"{qualified_name(service_type)}",
            code="invalid-decorator",
        )

    try:
        implementation = _specialize_decorator_implementation(source, bindings)
    except (ContainerBuildError, TypeError) as error:
        raise ContainerBuildError(
            f"Decorator {label} cannot be specialized for {qualified_name(service_type)}: {error}",
            code="invalid-decorator",
        ) from error

    if not isinstance(source, type):
        result_type = _resolve_factory_typevars(_factory_result_annotation(source), bindings)
        if not _decorator_result_matches_service(result_type, service_type):
            raise ContainerBuildError(
                f"Decorator {label} returns {qualified_name(result_type)}, which is not compatible with "
                f"{qualified_name(service_type)}",
                code="invalid-decorator",
            )

    specialized_dependencies = {
        name: legacy.Dependency(
            name=dependency.name,
            parent_implementation=implementation,
            service_type=_resolve_factory_typevars(dependency.service_type, bindings),
            settings=dependency.settings,
            default_value=dependency.default_value,
        )
        for name, dependency in dependencies.items()
    }
    return _DecoratorActivation(
        definition=definition,
        implementation=implementation,
        activator_class=legacy._Registry._get_activator_class(implementation),
        decorated_arg=decorated_arg,
        dependencies=specialized_dependencies,
    )


def _materialize_generated_decorator(definition: _DecoratorDefinition) -> _DecoratorActivation:
    """Bind the decorated contract independently of source specialization.

    Read original signature annotations before legacy Dependency's name-based
    generic inference. Only this generated path uses identity-keyed substitution;
    ordinary decorators retain their established materialization behavior.
    """
    source = definition.decorator_type
    origin = constructor_type(source)
    signature_source = origin or source
    label = qualified_name(source)
    try:
        infos = legacy._get_arg_info(signature_source)
        settings = _arguments_to_dependency_config(definition.arguments)
        # Dependency performs legacy inference for a class parent. A neutral
        # callable retains the exact annotation until our identity binding below.
        dependencies = {
            name: legacy.Dependency(
                name,
                _materialize_generated_decorator,
                info.arg_type,
                settings.get(name, legacy.DependencySettings()),
                info.default_value,
            )
            for name, info in infos.items()
        }
        for name in settings.keys() - dependencies.keys():
            dependencies[name] = legacy.Dependency(
                name,
                _materialize_generated_decorator,
                Any,
                settings[name],
                legacy.EMPTY,
            )
        _validate_dependency_names(signature_source, dependencies)
        source_bindings: dict[TypeVar, Any] = {}
        if origin is not None:
            for base in origin.__mro__:
                parameters = getattr(base, "__parameters__", ())
                if not parameters:
                    continue
                projection = _project_service_type(source, base)
                if projection is not None:
                    source_bindings.update(zip(parameters, get_args(projection)))
        annotations = {
            name: _resolve_typevar_identities(dependency.service_type, source_bindings)
            for name, dependency in dependencies.items()
        }
        decorated_arg = definition.decorated_arg
        if decorated_arg is None:
            candidates = [
                name
                for name, annotation in annotations.items()
                if _bind_typevar_identities(annotation, definition.service_type) is not None
            ]
            if len(candidates) != 1:
                raise ValueError("Expected one decorated argument; set decorated_arg= explicitly")
            decorated_arg = candidates[0]
        if decorated_arg not in dependencies:
            raise ValueError(f"No argument named {decorated_arg!r}")
        bindings = _bind_typevar_identities(annotations[decorated_arg], definition.service_type)
        if bindings is None:
            raise ValueError("Decorated argument conflicts with the projected target contract")
        no_default = getattr(typing, "NoDefault", _NO_TYPEVAR_DEFAULT)
        for annotation in annotations.values():
            for variable in _typevar_identities(annotation):
                if variable in bindings:
                    continue
                default = getattr(variable, "__default__", _NO_TYPEVAR_DEFAULT)
                if default is not _NO_TYPEVAR_DEFAULT and default is not no_default:
                    bindings[variable] = _resolve_typevar_identities(default, bindings)
        resolved = {name: _resolve_typevar_identities(annotation, bindings) for name, annotation in annotations.items()}
        unresolved = {variable for annotation in resolved.values() for variable in _typevar_identities(annotation)}
        if unresolved:
            raise ValueError(f"Unresolved decorator TypeVar(s): {', '.join(sorted(v.__name__ for v in unresolved))}")
        implementation = signature_source
        if origin is not None:
            parameters = getattr(origin, "__parameters__", ())
            if parameters:
                arguments = tuple(
                    _resolve_typevar_identities(_resolve_typevar_identities(parameter, source_bindings), bindings)
                    for parameter in parameters
                )
                if any(_typevar_identities(argument) for argument in arguments):
                    raise ValueError("Unresolved decorator implementation parameters")
                alias = cast(Any, origin)[arguments[0] if len(arguments) == 1 else arguments]
                implementation = legacy.create_generic_decorator_type(alias)
        else:
            result_type = _resolve_typevar_identities(_factory_result_annotation(source), bindings)
            if result_type not in (Any, inspect.Signature.empty):
                result_projection = _project_service_type(result_type, definition.service_type)
                if (
                    result_projection is None
                    or _typevar_identities(result_projection)
                    or _bind_typevar_identities(result_projection, definition.service_type) is None
                ):
                    raise ValueError("Decorator result is incompatible with the projected target contract")
        dependencies.pop(decorated_arg)
        specialized = {}
        for name, dependency in dependencies.items():
            item = legacy.Dependency(
                name,
                _materialize_generated_decorator,
                resolved[name],
                dependency.settings,
                dependency.default_value,
            )
            item.parent_implementation = implementation
            item.declared_service_type = dependency.declared_service_type
            specialized[name] = item
        return _DecoratorActivation(
            definition,
            implementation,
            legacy._Registry._get_activator_class(implementation),
            decorated_arg,
            specialized,
        )
    except Exception as error:
        raise ContainerBuildError(
            f"Decorator {label} cannot satisfy {qualified_name(definition.service_type)}: {error}",
            code="invalid-decorator",
        ) from error


@dataclass(frozen=True, slots=True)
class _CompiledDecorator:
    source: _DecoratorActivation
    dependencies: tuple[_CompiledDependency, ...]
    component: Component
    cleanup_owner: _CleanupOwnerDescriptor
    sync_supported: bool

    def decorate(self, value: Any, context: _RuntimeResolutionContext, lifespan: legacy.Lifespan) -> Any:
        dependencies = {dependency.name: dependency.step.resolve(context) for dependency in self.dependencies}
        dependencies[self.source.decorated_arg] = value
        return self.source.activator_class.activate(
            self.source.implementation,
            dependencies,
            cast(Any, _ActivationContext(context, self.cleanup_owner)),
            lifespan,
        )

    async def decorate_async(
        self,
        value: Any,
        context: _RuntimeResolutionContext,
        lifespan: legacy.Lifespan,
    ) -> Any:
        dependencies = {
            dependency.name: await dependency.step.resolve_async(context) for dependency in self.dependencies
        }
        dependencies[self.source.decorated_arg] = value
        return await self.source.activator_class.activate_async(
            self.source.implementation,
            dependencies,
            cast(Any, _ActivationContext(context, self.cleanup_owner)),
            lifespan,
        )


@dataclass(frozen=True, slots=True)
class _RegistrationStep(_Step):
    registration: legacy._Registration
    source_service_type: Any
    owner_token: str
    component: Component
    dependencies: tuple[_CompiledDependency, ...]
    pre_configurations: tuple[_CompiledPreConfiguration, ...]
    decorators: tuple[_CompiledDecorator, ...]
    cleanup_owner: _CleanupOwnerDescriptor
    sync_supported: bool

    def _activate(self, context: _RuntimeResolutionContext) -> Any:
        for configuration in self.pre_configurations:
            configuration.run(context)
        values = (
            {dependency.name: dependency.step.resolve(context) for dependency in self.dependencies}
            if self.dependencies
            else _EMPTY_DEPENDENCIES
        )
        instance = self.registration.activator_class.activate(
            self.registration.implementation,
            values,
            cast(Any, _ActivationContext(context, self.cleanup_owner)),
            self.registration.lifespan,
        )
        for decorator in self.decorators:
            instance = decorator.decorate(instance, context, self.registration.lifespan)
        return instance

    async def _activate_async(self, context: _RuntimeResolutionContext) -> Any:
        for configuration in self.pre_configurations:
            await configuration.run_async(context)
        values = (
            {dependency.name: await dependency.step.resolve_async(context) for dependency in self.dependencies}
            if self.dependencies
            else _EMPTY_DEPENDENCIES
        )
        instance = await self.registration.activator_class.activate_async(
            self.registration.implementation,
            values,
            cast(Any, _ActivationContext(context, self.cleanup_owner)),
            self.registration.lifespan,
        )
        for decorator in self.decorators:
            instance = await decorator.decorate_async(instance, context, self.registration.lifespan)
        return instance

    def resolve(self, context: _RuntimeResolutionContext) -> Any:
        raise NotImplementedError

    async def resolve_async(self, context: _RuntimeResolutionContext) -> Any:
        raise NotImplementedError


class _TransientRegistrationStep(_RegistrationStep):
    __slots__ = ()

    def resolve(self, context: _RuntimeResolutionContext) -> Any:
        context.assert_allowed(self)
        context.registration_stack.append(self)
        try:
            return self._activate(context)
        finally:
            context.registration_stack.pop()

    async def resolve_async(self, context: _RuntimeResolutionContext) -> Any:
        context.assert_allowed(self)
        context.registration_stack.append(self)
        try:
            return await self._activate_async(context)
        finally:
            context.registration_stack.pop()


class _FrozenProviderMap(Mapping):
    """Share frozen key topology, keeping scope-bound handles local to acquisition."""

    __slots__ = ("_indices", "_providers")

    def __init__(self, indices: Mapping[Hashable, int], providers: tuple[Any, ...]) -> None:
        self._indices = indices
        self._providers = providers

    def __getitem__(self, key: Hashable) -> Any:
        return self._providers[self._indices[key]]

    def __iter__(self) -> Iterator[Hashable]:
        return iter(self._indices)

    def __len__(self) -> int:
        return len(self._indices)


@dataclass(frozen=True, slots=True)
class _ProviderMapStep(_TransientRegistrationStep):
    key_indices: Mapping[Hashable, int] = field(kw_only=True)

    def _activate(self, context: _RuntimeResolutionContext) -> Any:
        for configuration in self.pre_configurations:
            configuration.run(context)
        instance = _FrozenProviderMap(
            self.key_indices, tuple(dependency.step.resolve(context) for dependency in self.dependencies)
        )
        for decorator in self.decorators:
            instance = decorator.decorate(instance, context, self.registration.lifespan)
        return instance

    async def _activate_async(self, context: _RuntimeResolutionContext) -> Any:
        for configuration in self.pre_configurations:
            await configuration.run_async(context)
        instance = _FrozenProviderMap(
            self.key_indices, tuple(dependency.step.resolve(context) for dependency in self.dependencies)
        )
        for decorator in self.decorators:
            instance = await decorator.decorate_async(instance, context, self.registration.lifespan)
        return instance


class _PerResolutionRegistrationStep(_RegistrationStep):
    __slots__ = ()

    def resolve(self, context: _RuntimeResolutionContext) -> Any:
        key = self.registration.id
        value = context.resolution_cache.get(key, _CACHE_MISS)
        if value is not _CACHE_MISS:
            return value
        context.assert_allowed(self)
        context.registration_stack.append(self)
        try:
            value = self._activate(context)
            context.resolution_cache[key] = value
            return value
        finally:
            context.registration_stack.pop()

    async def resolve_async(self, context: _RuntimeResolutionContext) -> Any:
        key = self.registration.id
        value = context.resolution_cache.get(key, _CACHE_MISS)
        if value is not _CACHE_MISS:
            return value
        context.assert_allowed(self)
        context.registration_stack.append(self)
        try:
            value = await self._activate_async(context)
            context.resolution_cache[key] = value
            return value
        finally:
            context.registration_stack.pop()


class _ScopedRegistrationStep(_RegistrationStep):
    __slots__ = ()

    def resolve(self, context: _RuntimeResolutionContext) -> Any:
        key = self.registration.id
        found, value = context.scope._find_scoped(key)
        if found:
            return value
        future, builder = context.scope._coordinator.begin(key)
        if not builder:
            outcome = future.result()
            if outcome.error is not None:
                raise outcome.error
            found, value = context.scope._find_scoped(key)
            if not found:
                raise RuntimeError(f"Component {key} completed without a cached value")
            return value
        try:
            context.assert_allowed(self)
            context.registration_stack.append(self)
            try:
                value = self._activate(context)
                context.scope._scoped[key] = value
            finally:
                context.registration_stack.pop()
        except BaseException as error:
            context.scope._coordinator.finish(key, future, error)
            raise
        context.scope._coordinator.finish(key, future)
        return value

    async def resolve_async(self, context: _RuntimeResolutionContext) -> Any:
        key = self.registration.id
        found, value = context.scope._find_scoped(key)
        if found:
            return value
        future, builder = context.scope._coordinator.begin(key)
        if not builder:
            outcome = await asyncio.shield(asyncio.wrap_future(future))
            if outcome.error is not None:
                raise outcome.error
            found, value = context.scope._find_scoped(key)
            if not found:
                raise RuntimeError(f"Component {key} completed without a cached value")
            return value
        try:
            context.assert_allowed(self)
            context.registration_stack.append(self)
            try:
                value = await self._activate_async(context)
                context.scope._scoped[key] = value
            finally:
                context.registration_stack.pop()
        except BaseException as error:
            context.scope._coordinator.finish(key, future, error)
            raise
        context.scope._coordinator.finish(key, future)
        return value


class _SingletonRegistrationStep(_RegistrationStep):
    __slots__ = ()

    def resolve(self, context: _RuntimeResolutionContext) -> Any:
        key = self.registration.id
        owner = context.scope._owners[self.owner_token]
        owner._ensure_owner_open()
        value = owner._singletons.get(key, _CACHE_MISS)
        if value is not _CACHE_MISS:
            return value
        future, builder = owner._coordinator.begin(key)
        if not builder:
            outcome = future.result()
            if outcome.error is not None:
                raise outcome.error
            value = owner._singletons.get(key, _CACHE_MISS)
            if value is _CACHE_MISS:
                raise RuntimeError(f"Component {key} completed without a cached value")
            return value
        try:
            context.assert_allowed(self)
            context.registration_stack.append(self)
            try:
                value = self._activate(context)
                owner._singletons[key] = value
            finally:
                context.registration_stack.pop()
        except BaseException as error:
            owner._coordinator.finish(key, future, error)
            raise
        owner._coordinator.finish(key, future)
        return value

    async def resolve_async(self, context: _RuntimeResolutionContext) -> Any:
        key = self.registration.id
        owner = context.scope._owners[self.owner_token]
        owner._ensure_owner_open()
        value = owner._singletons.get(key, _CACHE_MISS)
        if value is not _CACHE_MISS:
            return value
        future, builder = owner._coordinator.begin(key)
        if not builder:
            outcome = await asyncio.shield(asyncio.wrap_future(future))
            if outcome.error is not None:
                raise outcome.error
            value = owner._singletons.get(key, _CACHE_MISS)
            if value is _CACHE_MISS:
                raise RuntimeError(f"Component {key} completed without a cached value")
            return value
        try:
            context.assert_allowed(self)
            context.registration_stack.append(self)
            try:
                value = await self._activate_async(context)
                owner._singletons[key] = value
            finally:
                context.registration_stack.pop()
        except BaseException as error:
            owner._coordinator.finish(key, future, error)
            raise
        owner._coordinator.finish(key, future)
        return value


_REGISTRATION_STEP_TYPES: dict[legacy.Lifespan, type[_RegistrationStep]] = {
    legacy.Lifespan.transient: _TransientRegistrationStep,
    legacy.Lifespan.per_resolution: _PerResolutionRegistrationStep,
    legacy.Lifespan.scoped: _ScopedRegistrationStep,
    legacy.Lifespan.singleton: _SingletonRegistrationStep,
}


@dataclass(frozen=True, slots=True)
class _RootPlan:
    component: Component
    step: _Step


@dataclass(frozen=True, slots=True)
class _PlanSet:
    graph: _ComponentGraph
    roots: dict[Any, tuple[_RootPlan, ...]]
    default_roots: dict[Any, _RootPlan]
    default_root_groups: dict[Any, tuple[_RootPlan, ...]]
    blueprint: _Blueprint
    build_args: Mapping[str, Any]
    compiled_graph: CompiledGraph | None = None
    build_report: BuildReport = field(default_factory=BuildReport)
    compiler_issues: tuple[BuildIssue, ...] = ()
    root_candidates: Mapping[Any, tuple[_CandidateRecord, ...]] = field(default_factory=dict)
    occurrence_explanations: Mapping[int, CompilationExplanation] = field(default_factory=dict)
    parameter_explanations: Mapping[int, Mapping[str, ParameterExplanation]] = field(default_factory=dict)
    generic_explanations: Mapping[int, GenericBindingExplanation] = field(default_factory=dict)
    occurrence_layers: Mapping[int, str] = field(default_factory=dict)
    provider_roots: Mapping[Any, tuple[_RootPlan, ...]] = field(default_factory=dict)
    architecture_roots: tuple[tuple[str | None, Any, _RootPlan], ...] = ()
    area_root_candidates: Mapping[str, Mapping[Any, tuple[_CandidateRecord, ...]]] = field(default_factory=dict)


def _requires_async(activator_class: type, implementation: Any) -> bool:
    if activator_class in (legacy.AsyncFactoryActivator, legacy.AsyncGeneratorActivator):
        return True
    wrapped = getattr(implementation, "__wrapped__", None)
    return wrapped is not None and (inspect.iscoroutinefunction(wrapped) or inspect.isasyncgenfunction(wrapped))


def _registration_activation(registration: legacy._Registration) -> ComponentActivation:
    if registration.is_instance:
        return ComponentActivation.instance
    if constructor_type(registration.implementation) is not None:
        return ComponentActivation.constructor
    return ComponentActivation.factory


def _callable_activation(implementation: Any) -> ComponentActivation:
    return (
        ComponentActivation.constructor if constructor_type(implementation) is not None else ComponentActivation.factory
    )


def _manages_cleanup(activator_class: type, implementation: Any) -> bool:
    if activator_class in (legacy.GeneratorActivator, legacy.AsyncGeneratorActivator):
        return True
    wrapped = getattr(implementation, "__wrapped__", None)
    return wrapped is not None and (inspect.isgeneratorfunction(wrapped) or inspect.isasyncgenfunction(wrapped))


def _provider_request(annotation: Any) -> tuple[typing.Literal["sync", "async"], Any | None] | None:
    """Return a provider's invocation mode and target without accepting lookalikes."""

    origin = get_origin(annotation)
    provider_type = annotation if origin is None else origin
    if provider_type not in (Provider, AsyncProvider):
        return None
    arguments = get_args(annotation)
    target = arguments[0] if len(arguments) == 1 else None
    return ("sync" if provider_type is Provider else "async"), target


def _provider_target_collection(target: Any) -> tuple[type, Any] | None:
    origin = get_origin(target)
    arguments = get_args(target)
    if origin not in (list, tuple, set) or not arguments:
        return None
    if origin is tuple and (len(arguments) != 2 or arguments[1] is not Ellipsis):
        return None
    if origin in (list, set) and len(arguments) != 1:
        return None
    return origin, arguments[0]


@dataclass(frozen=True, slots=True)
class _CompilerFrame:
    label: Any
    lifespan: legacy.Lifespan
    owner_token: str
    kind: ComponentKind
    component: Component


@dataclass(frozen=True, slots=True)
class _CompiledCandidate:
    component: Component
    step: _Step
    origin: DefinitionOrigin
    eligible: bool
    reason_codes: tuple[str, ...]
    reason: str
    source_registration_id: str | None = None
    source_layer: _Layer | None = None


def _frame_description(frame: _CompilerFrame) -> str:
    label = qualified_name(frame.label)
    if frame.kind is ComponentKind.pre_configuration:
        return f"Pre-configuration {label}"
    owner = "Singleton" if frame.lifespan == legacy.Lifespan.singleton else "Scoped"
    return f"{owner} {label}"


class _Compiler:
    def __init__(
        self,
        blueprint: _Blueprint,
        *,
        build_args: Mapping[str, Any] = _EMPTY_BUILD_ARGS,
        anchored_singletons: dict[tuple[str, tuple[Any, ...]], _RegistrationStep] | None = None,
        anchored_pre_configurations: dict[str, _CompiledPreConfiguration] | None = None,
        anchored_owner_tokens: frozenset[str] = frozenset(),
        inherited_parameter_explanations: Mapping[int, Mapping[str, ParameterExplanation]] = types.MappingProxyType({}),
        inherited_generic_explanations: Mapping[int, GenericBindingExplanation] = types.MappingProxyType({}),
    ):
        self.blueprint = blueprint
        self.build_args = build_args
        self._source_inspection = False
        self.graph = _ComponentGraph()
        self._next_occurrence = 1
        self._stack: list[legacy._Registration] = []
        self._frames: list[_CompilerFrame] = []
        self._specialized_factories: dict[tuple[str, tuple[Any, ...]], legacy._Registration] = {}
        self._patterns: dict[Any, list[tuple[legacy._Registration, _Layer]]] = {}
        for layer in (*blueprint.layers, *(boundary.layer for boundary in blueprint.boundaries)):
            for component_id in reversed(layer.pattern_ids):
                candidate = blueprint.registration_definition(component_id)
                if candidate is not None:
                    self._patterns.setdefault(get_origin(candidate[0].service_type), []).append(candidate)
        self._pattern_sources: dict[str, str] = {}
        self._specialized_service_groups: dict[str, frozenset[ServiceGroup]] = {}
        self._specialized_registration_sources: dict[str, legacy._Registration] = {}
        self._pattern_requests: dict[Any, None] = {}
        self._compiled_pre_configurations: dict[str, _CompiledPreConfiguration] = {}
        self._compiling_pre_configurations: set[str] = set()
        self._anchored_singletons = anchored_singletons or {}
        self._anchored_pre_configurations = anchored_pre_configurations or {}
        self._anchored_owner_tokens = anchored_owner_tokens
        self._inherited_parameter_explanations = inherited_parameter_explanations
        self._inherited_generic_explanations = inherited_generic_explanations
        self._area: str | None = None
        self.issues: list[BuildIssue] = []
        self.root_candidates: dict[Any, tuple[_CandidateRecord, ...]] = {}
        self.occurrence_explanations: dict[int, CompilationExplanation] = {}
        self.parameter_explanations: dict[int, dict[str, ParameterExplanation]] = {}
        self.generic_explanations: dict[int, GenericBindingExplanation] = {}
        self._factory_pattern_bindings: dict[str, tuple[tuple[str, str], ...]] = {}
        self._specialized_dependency_annotations: dict[str, tuple[tuple[str, Any, Any], ...]] = {}
        self.origins: dict[int, DefinitionOrigin] = {}
        self.decision_history: list[CompilationExplanation] = []
        # This is diagnostic-only evidence.  It never participates in steps or graph freezing.
        self._partial_edges: list[tuple[int, str, str, int | None]] = []
        self._partial_back_references: set[int] = set()
        self._partial_declaration_edges: list[tuple[int | None, str, str, str, bool]] = []
        # Candidate results are captured at the point a predicate or structural
        # compile actually completes.  Absence means not examined, not rejected.
        self._partial_candidates: list[tuple[str, str, PartialState, str | None]] = []
        self._partial_candidate_labels: dict[str, str] = {}
        self._partial_truncated = False

    def _record_partial_candidate(self, item: tuple[str, str, PartialState, str | None]) -> None:
        if len(self._partial_candidates) >= 500:
            self._partial_truncated = True
            return
        self._partial_candidates.append(item)

    def _record_partial_edge(self, item: tuple[int, str, str, int | None]) -> int | None:
        if len(self._partial_edges) >= 500:
            self._partial_truncated = True
            return None
        self._partial_edges.append(item)
        return len(self._partial_edges) - 1

    def _record_partial_declaration_edge(self, item: tuple[int | None, str, str, str, bool]) -> None:
        if len(self._partial_declaration_edges) >= 500:
            self._partial_truncated = True
            return
        self._partial_declaration_edges.append(item)

    def partial_attempt(self, error: BaseException, *, root: str | None = None) -> CompilationAttempt:
        """Copy only safe structural draft data while it is still available."""
        limit = 500
        records = self.graph._records if self.graph._records is not None else self.graph._drafts
        drafts = sorted(records.values(), key=lambda draft: draft.occurrence_id)
        truncated = (
            len(drafts) > limit
            or len(self._partial_edges) > limit
            or len(self._partial_candidates) > limit
            or self._partial_truncated
        )
        drafts = drafts[:limit]
        node_items = [
            PartialNode(
                str(draft.occurrence_id),
                _issue_path_name(cast(Component, draft)),
                PartialState.complete,
                draft.kind.value,
                draft.lifespan,
            )
            for draft in drafts
        ]
        # Validation rules describe semantic paths, while a partial graph uses
        # attempt-local occurrence ids.  Retain the full ancestry for every
        # captured occurrence so an issue for a shared service cannot be
        # attached to the first node with the same leaf label.
        drafts_by_occurrence = {draft.occurrence_id: draft for draft in drafts}
        traversal_parents: dict[int, list[int]] = defaultdict(list)
        for draft in drafts:
            if draft.parent_id is not None and draft.kind not in (
                ComponentKind.decorator,
                ComponentKind.pre_configuration,
            ):
                traversal_parents[draft.occurrence_id].append(draft.parent_id)
            # Decorators and pre-configurations deliberately retain their own
            # compilation parent, but GraphVisit presents them under the
            # component that owns the pipeline.  Use that same traversal edge
            # for validation paths rather than their draft allocation parent.
            for child_id in (*draft.pre_configuration_ids, *draft.decorator_ids):
                traversal_parents[child_id].append(draft.occurrence_id)
        semantic_paths: dict[int, tuple[tuple[str, ...], ...]] = {}

        def semantic_paths_for(
            occurrence_id: int, ancestors: frozenset[int] = frozenset()
        ) -> tuple[tuple[str, ...], ...]:
            if occurrence_id in ancestors or occurrence_id not in drafts_by_occurrence:
                return ()
            cached = semantic_paths.get(occurrence_id)
            if cached is not None:
                return cached
            draft = drafts_by_occurrence[occurrence_id]
            parents = tuple(dict.fromkeys(traversal_parents.get(occurrence_id, ())))
            label = _issue_path_name(cast(Component, draft))
            if not parents:
                result = ((label,),)
            else:
                result = tuple(
                    dict.fromkeys(
                        (*parent_path, label)
                        for parent_id in parents
                        for parent_path in semantic_paths_for(parent_id, ancestors | frozenset({occurrence_id}))
                    )
                )
            semantic_paths[occurrence_id] = result
            return result

        path_index: dict[tuple[str, ...], list[str]] = {}
        for draft in drafts:
            for path in semantic_paths_for(draft.occurrence_id):
                path_index.setdefault(path, []).append(str(draft.occurrence_id))
        code = (
            error.report.errors[0].code
            if isinstance(error, ContainerBuildError) and error.report is not None and error.report.errors
            else _build_error_code(error)
        )
        edges: list[PartialEdge] = []
        edges_by_source = list(self._partial_edges[:limit])
        # A completed graph has frozen dependency ids but no mutable edge log.
        if not edges_by_source:
            for draft in drafts:
                edges_by_source.extend((draft.occurrence_id, "dependency", "", child) for child in draft.dependency_ids)
        # Draft metadata carries non-parameter structural links too.  These are
        # descriptive edges only and never turn into executable steps.
        for draft in drafts:
            if draft.parent_id is not None:
                edges_by_source.append(
                    (draft.parent_id, "contains", qualified_name(draft.service_type), draft.occurrence_id)
                )
            if draft.decorated_id is not None:
                edges_by_source.append((draft.occurrence_id, "decorates", "", draft.decorated_id))
            edges_by_source.extend((draft.occurrence_id, "decorator", "", child) for child in draft.decorator_ids)
            edges_by_source.extend(
                (draft.occurrence_id, "pre-configuration", "", child) for child in draft.pre_configuration_ids
            )
        for edge_index, (source, label, requested, target) in enumerate(edges_by_source[:limit]):
            state = PartialState.complete if target is not None else PartialState.failed
            target_id = None if target is None else str(target)
            if target_id is None:
                target_id = next((node.id for node in reversed(node_items) if node.label == requested), None)
            if target_id is None:
                if len(node_items) < limit:
                    target_id = f"missing_{source}_{label}"
                    node_items.append(PartialNode(target_id, requested, PartialState.failed))
                else:
                    # Keep the observed failed edge but never exceed the
                    # documented node budget merely to invent its endpoint.
                    truncated = True
            back_reference = edge_index in self._partial_back_references
            edges.append(
                PartialEdge(
                    str(source),
                    target_id,
                    label,
                    PartialState.failed if back_reference else state,
                    code if back_reference else (None if target is not None else code),
                    back_reference=back_reference,
                )
            )
        if isinstance(error, ContainerBuildError) and error.report is not None:
            # Rule and finalization findings are linked to the matching
            # structural occurrence when they provide a path; otherwise the
            # declaration edge retains the issue without inventing a node.
            for issue in error.report.errors:
                if len(edges) >= limit:
                    truncated = True
                    break
                requested_path = issue.path
                if issue.root is not None and (not requested_path or requested_path[0] != issue.root):
                    requested_path = (issue.root, *requested_path)
                matches = path_index.get(requested_path, ()) if requested_path else ()
                target = matches[0] if len(matches) == 1 else None
                if target is None:
                    if len(node_items) >= limit:
                        truncated = True
                        break
                    if len(matches) > 1:
                        issue_location = "ambiguous target"
                    else:
                        issue_location = "unanchored"
                    target = f"issue_{len(node_items)}"
                    node_items.append(
                        PartialNode(
                            target,
                            f"Issue [{issue.code}] ({issue_location})",
                            PartialState.failed,
                            "issue",
                            issue_code=issue.code,
                        )
                    )
                edges.append(PartialEdge(None, target, "issue", PartialState.failed, issue.code))
        for source, label, target_label, issue_code, back_reference in self._partial_declaration_edges[:limit]:
            if len(node_items) >= limit or len(edges) >= limit:
                truncated = True
                break
            target = f"declaration_{len(node_items)}"
            node_items.append(
                PartialNode(target, target_label, PartialState.failed, "declaration", issue_code=issue_code)
            )
            edges.append(
                PartialEdge(
                    None if source is None else str(source),
                    target,
                    label,
                    PartialState.failed,
                    issue_code,
                    back_reference=back_reference,
                )
            )
        # A draft which still owns an unresolved edge did not complete
        # structural compilation.  Do not describe it as complete merely
        # because allocation happened before descent.
        failed_sources = {
            edge.source for edge in edges if edge.state is PartialState.failed and edge.source is not None
        }
        node_items = [
            replace(node, state=PartialState.failed, issue_code=node.issue_code or code)
            if node.id in failed_sources and node.state is PartialState.complete
            else node
            for node in node_items
        ]
        seen_candidates: set[tuple[str, str]] = set()
        candidates = list(self._partial_candidates)
        for explanation in self.decision_history:
            for decision in (*explanation.selected, *explanation.rejected):
                state = (
                    PartialState.complete if decision.outcome is not DecisionOutcome.rejected else PartialState.rejected
                )
                candidates.append(
                    (
                        explanation.subject,
                        decision.component_id,
                        state,
                        decision.reason_codes[0] if decision.reason_codes else None,
                    )
                )
        failed_keys = {
            (subject, candidate) for subject, candidate, state, _ in candidates if state is PartialState.failed
        }
        for subject, candidate, state, issue_code in candidates[:limit]:
            occurrence = next((draft for draft in drafts if draft.id == candidate), None)
            required_nodes = 1 if occurrence is not None else 2
            if len(node_items) + required_nodes > limit or len(edges) >= limit:
                truncated = True
                break
            key = (subject, candidate)
            if key in seen_candidates or (key in failed_keys and state is not PartialState.failed):
                continue
            seen_candidates.add(key)
            # Registration ids are UUIDs and must not leak into a stable public
            # artifact.  The attempt-local ordinal is deterministic because
            # compiler decisions are retained in evaluation order.
            node_id = f"candidate_{len(node_items)}"
            implementation = (
                qualified_name(occurrence.implementation)
                if occurrence is not None
                else self._partial_candidate_labels.get(candidate, subject)
            )
            node_items.append(
                PartialNode(
                    node_id,
                    f"Candidate {len(seen_candidates)}: {implementation}",
                    state,
                    "candidate",
                    issue_code=issue_code,
                    declaration_ref=f"declaration:{len(seen_candidates)}:{subject}",
                    occurrence_ref=None if occurrence is None else str(occurrence.occurrence_id),
                )
            )
            if occurrence is None:
                declaration_id = f"candidate_declaration_{len(node_items)}"
                node_items.append(
                    PartialNode(
                        declaration_id,
                        f"Declaration for {implementation}",
                        PartialState.not_examined,
                        "declaration",
                        declaration_ref=f"declaration:{len(seen_candidates)}:{subject}",
                    )
                )
                edges.append(PartialEdge(declaration_id, node_id, "candidate", state, issue_code))
            else:
                edges.append(PartialEdge(str(occurrence.occurrence_id), node_id, "candidate", state, issue_code))
        # A failure before allocation remains explicit rather than inventing a component.
        if not node_items or not edges:
            path = error.path if isinstance(error, ContainerBuildError) else ()
            edges.append(PartialEdge(None, None, " -> ".join(path) or "declaration", PartialState.failed, code))
        if root is None and isinstance(error, ContainerBuildError) and error.path:
            root = error.path[0]
        path = error.path if isinstance(error, ContainerBuildError) else ()
        witness_total = len(path)
        witness_omitted = 0
        if len(path) > 32:
            omitted = len(path) - 32
            witness_omitted = omitted
            path = (*path[:16], f"… {omitted} path segments omitted", *path[-16:])
            truncated = True
        return CompilationAttempt(
            root,
            tuple(node_items),
            tuple(edges),
            code,
            truncated,
            path,
            witness_total=witness_total,
            witness_omitted=witness_omitted,
        )

    def partial_success_attempt(self, *, root: str) -> CompilationAttempt:
        """Record a retry which compiled successfully without merging it with failures."""
        attempt = self.partial_attempt(ContainerBuildError(code="retry-succeeded"), root=root)
        return replace(attempt, succeeded=True)

    def _current_path(self, *tail: Any) -> tuple[str, ...]:
        return tuple(qualified_name(value) for value in (*(frame.label for frame in self._frames), *tail))

    def _visibility_error(self, service_type: Any) -> ContainerBuildError | None:
        visible = {registration.id for registration, _ in self.blueprint.registrations(service_type, self._area)}
        hidden: list[str] = []
        hidden_definitions: list[tuple[legacy._Registration, _Layer, str]] = []

        def local(area: str | None) -> list[tuple[legacy._Registration, _Layer]]:
            found = self.blueprint.local_registrations(area, service_type)
            if not found and self._patterns:
                found = [
                    item
                    for item in self._patterns.get(get_origin(service_type), ())
                    if self.blueprint.registration_area(item[1]) == area
                    and patterns.match(item[0].service_type, service_type) is not None
                ]
            if not found and get_origin(service_type) is not None:
                found = self.blueprint.local_registrations(area, get_origin(service_type))
            return found

        root_hidden = [(registration, layer) for registration, layer in local(None) if registration.id not in visible]
        if root_hidden and self._area is not None:
            hidden.append("root")
            hidden_definitions.extend((registration, layer, "rejected-not-used") for registration, layer in root_hidden)
        for boundary in self.blueprint.boundaries:
            if boundary.name == self._area:
                continue
            private = [
                (registration, layer) for registration, layer in local(boundary.name) if registration.id not in visible
            ]
            if private:
                hidden.append(boundary.name)
                exposed_ids = {target.registration_id for target in boundary.resolved_exposes}
                hidden_definitions.extend(
                    (
                        registration,
                        layer,
                        "rejected-not-used" if registration.id in exposed_ids else "rejected-not-exposed",
                    )
                    for registration, layer in private
                )
        if not hidden:
            return None
        rejected = tuple(
            CandidateDecision(
                registration.id,
                DecisionOutcome.rejected,
                (reason_code,),
                (
                    "The component is exposed but the consuming boundary did not declare a matching Use"
                    if reason_code == "rejected-not-used"
                    else "The component is private because its defining boundary did not expose it"
                ),
                self.blueprint.registration_origin(registration.id, layer),
            )
            for registration, layer, reason_code in hidden_definitions
        )
        if rejected:
            self.decision_history.append(
                CompilationExplanation(
                    subject=qualified_name(service_type),
                    path=self._current_path(service_type),
                    selected=(),
                    rejected=rejected,
                )
            )
        sources = ", ".join(repr(item) for item in hidden)
        suggestion = (
            "add Use.root(...)"
            if hidden == ["root"]
            else "add an Expose declaration in the defining boundary and a matching Use declaration"
        )
        overlay_root = self._area is None and any(
            self.origins.get(frame.component.occurrence_id, _synthetic_origin()).layer == "overlay"
            for frame in self._frames
        )
        return ContainerBuildError(
            f"Matching component for {service_type!r} is private in {sources}; {suggestion}",
            code=("overlay-boundary-private-component" if overlay_root else "boundary-private-component"),
            path=self._current_path(service_type),
        )

    def _retention_frames(self) -> tuple[_CompilerFrame, ...]:
        """Return frames participating in eager retention validation.

        A provider is a deferred boundary: its target is validated internally,
        but is not retained by frames above the provider handle.
        """

        boundary = next(
            (
                index
                for index in range(len(self._frames) - 1, -1, -1)
                if self._frames[index].kind is ComponentKind.provider
            ),
            -1,
        )
        return tuple(self._frames[boundary + 1 :])

    def _validate_captive_lifespan(
        self,
        label: Any,
        lifespan: legacy.Lifespan,
        *,
        is_instance: bool = False,
    ) -> None:
        retention_frames = self._retention_frames()
        singleton = next(
            (item for item in reversed(retention_frames) if item.lifespan == legacy.Lifespan.singleton),
            None,
        )
        if singleton is not None and lifespan == legacy.Lifespan.scoped and not is_instance:
            raise ContainerBuildError(
                f"{_frame_description(singleton)} cannot retain scoped {label}",
                code="captive-dependency",
                path=self._current_path(label),
            )
        long_lived = next(
            (
                item
                for item in reversed(retention_frames)
                if item.lifespan in (legacy.Lifespan.scoped, legacy.Lifespan.singleton)
            ),
            None,
        )
        if long_lived is not None and lifespan == legacy.Lifespan.per_resolution:
            raise ContainerBuildError(
                f"{_frame_description(long_lived)} cannot retain per-resolution {label}",
                code="captive-dependency",
                path=self._current_path(label),
            )

    def _validate_runtime_context_dependency(self, service_type: Any, parent: Component) -> Lifespan:
        if service_type in (ResolutionContext, legacy.CurrentGraph):
            if bool(getattr(parent.implementation, _ACTIVATION_LOCAL_CONTEXT_ATTRIBUTE, False)):
                return "transient"
            long_lived = next(
                (
                    item
                    for item in reversed(self._retention_frames())
                    if item.lifespan in (legacy.Lifespan.scoped, legacy.Lifespan.singleton)
                ),
                None,
            )
            if long_lived is not None:
                raise ContainerBuildError(
                    f"{_frame_description(long_lived)} cannot retain per-resolution " f"{qualified_name(service_type)}",
                    code="captive-resolution-context",
                    path=self._current_path(service_type),
                )
            return "per_resolution"
        if service_type in (Scope, legacy.Scope, legacy.Resolver, legacy.ScopeCreator):
            singleton = next(
                (item for item in reversed(self._retention_frames()) if item.lifespan == legacy.Lifespan.singleton),
                None,
            )
            if singleton is not None:
                raise ContainerBuildError(
                    f"{_frame_description(singleton)} cannot retain runtime scope {qualified_name(service_type)}",
                    code="captive-runtime-scope",
                    path=self._current_path(service_type),
                )
            return "scoped"
        if service_type is Container:
            return "singleton"
        return "transient"

    def _compiled_ownership(
        self,
        lifespan: Lifespan,
        kind: ComponentKind,
        manages_cleanup: bool,
    ) -> tuple[RuntimeOwnerKind, RuntimeOwnerKind, int | None, str]:
        if kind in (ComponentKind.scope_slot, ComponentKind.value):
            return (
                RuntimeOwnerKind.supplied,
                RuntimeOwnerKind.none,
                None,
                "The value is supplied and Clean IoC does not finalize it",
            )
        if kind is ComponentKind.runtime_context:
            cache_owner = {
                "per_resolution": RuntimeOwnerKind.resolution,
                "scoped": RuntimeOwnerKind.scope,
                "singleton": RuntimeOwnerKind.singleton,
            }.get(lifespan, RuntimeOwnerKind.none)
            return cache_owner, RuntimeOwnerKind.none, None, "The runtime supplies this context without cleanup"
        if kind is ComponentKind.collection:
            return RuntimeOwnerKind.none, RuntimeOwnerKind.none, None, "The collection is local to its activation edge"
        if kind is ComponentKind.provider:
            return (
                RuntimeOwnerKind.none,
                RuntimeOwnerKind.none,
                None,
                "The frozen provider handle is bound to a scope and owns no cleanup",
            )

        cache_owner = {
            "per_resolution": RuntimeOwnerKind.resolution,
            "scoped": RuntimeOwnerKind.scope,
            "singleton": RuntimeOwnerKind.singleton,
        }.get(lifespan, RuntimeOwnerKind.none)
        if lifespan == "singleton":
            inherited = (
                self._frames[-1].component.occurrence_id if kind is ComponentKind.decorator and self._frames else None
            )
            reason = (
                "The decorator inherits the decorated singleton owner"
                if inherited is not None
                else "The singleton is finalized by its declaring owner"
            )
            return cache_owner, RuntimeOwnerKind.singleton, inherited, reason
        if lifespan == "scoped":
            return cache_owner, RuntimeOwnerKind.scope, None, "The scoped instance closes with the resolving scope"
        if lifespan == "per_resolution":
            cleanup = RuntimeOwnerKind.scope if manages_cleanup else RuntimeOwnerKind.none
            reason = (
                "The resolution caches the instance and the resolving scope owns its cleanup"
                if manages_cleanup
                else "The resolution caches the instance and no cleanup is required"
            )
            return cache_owner, cleanup, None, reason
        if not manages_cleanup:
            return cache_owner, RuntimeOwnerKind.none, None, "The transient instance does not manage cleanup"
        singleton = next(
            (frame for frame in reversed(self._retention_frames()) if frame.lifespan == legacy.Lifespan.singleton),
            None,
        )
        if singleton is not None:
            return (
                cache_owner,
                RuntimeOwnerKind.singleton,
                singleton.component.occurrence_id,
                "Cleanup is promoted to the nearest retaining singleton owner",
            )
        return (
            cache_owner,
            RuntimeOwnerKind.scope,
            None,
            "The resolving scope owns cleanup for this transient resource",
        )

    def _cleanup_descriptor(
        self,
        component: Component,
        *,
        declaring_owner_token: str,
    ) -> _CleanupOwnerDescriptor:
        if component.cleanup_owner is RuntimeOwnerKind.none:
            return _NO_CLEANUP_OWNER
        if component.cleanup_owner is RuntimeOwnerKind.scope:
            return _SCOPE_CLEANUP_OWNER
        if component.cleanup_owner is RuntimeOwnerKind.singleton:
            owner_id = component.owner_occurrence_id
            if owner_id is not None:
                frame = next(
                    (item for item in reversed(self._frames) if item.component.occurrence_id == owner_id),
                    None,
                )
                if frame is None:
                    raise ContainerBuildError(
                        "Compiled cleanup ownership does not match the activation path",
                        code="cleanup-owner-conflict",
                        path=self._current_path(component.service_type),
                    )
                declaring_owner_token = frame.owner_token
            return _CleanupOwnerDescriptor(RuntimeOwnerKind.singleton, declaring_owner_token)
        raise ContainerBuildError(
            f"No executable cleanup owner exists for {qualified_name(component.service_type)}",
            code="unsafe-cleanup-owner",
            path=self._current_path(component.service_type),
        )

    def _compile_source_core(self, registration_id: str, requested_service_type: Any) -> Component:
        """Inspect one exact definition in a disposable, undecorated graph.

        The caller supplies a normalized, visibility-prepared blueprint and an
        already-visible source ID. A source's own contextual condition belongs
        to its eventual injection occurrence, not this parentless metadata view.
        Dependency conditions are still evaluated by the ordinary compiler.
        No activation steps from this compiler may be published as runtime plans.
        """
        if self._source_inspection or self.graph._drafts or self.graph._records is not None:
            raise RuntimeError("Source inspection requires a fresh compiler")
        self._source_inspection = True
        candidate = self.blueprint.registration_definition(registration_id)
        if candidate is None:
            raise KeyError(registration_id)
        source, layer = candidate
        requested_service_type = normalize_type_alias(requested_service_type)
        if requested_service_type != source.service_type or getattr(requested_service_type, "__parameters__", ()):
            raise ValueError("Source inspection requires the definition's exact closed service key")
        self._area = self.blueprint.registration_area(layer)
        registration = self._specialize_factory(source, layer, requested_service_type)
        component, _ = self._compile_registration(
            registration,
            layer,
            parent=None,
            argument=None,
            requested_service_type=requested_service_type,
            origin=self.blueprint.registration_origin(source.id, layer),
        )
        # An anchored singleton can carry an exported alias in its frozen view.
        # Source filtering always observes the definition-side contract/metadata.
        draft = cast(_ComponentDraft, self.graph.record(component.occurrence_id))
        draft.service_type = requested_service_type
        draft.name = registration.name
        draft.tags = tuple(registration.tags)
        draft.argument = None
        implementation_type = _source_registration_info(source, layer).implementation_type
        if implementation_type is not None:
            # Only the inspection root gains known instance/factory type evidence.
            # Ordinary component normalization and anchored activation stay intact.
            draft.implementation_type = constructor_type(implementation_type) or draft.implementation_type
        self.graph.freeze()
        return component

    def compile(
        self,
        service_types: Iterable[Any] | None = None,
        *,
        area: str | None = None,
        include_boundaries: bool = True,
    ) -> _PlanSet:
        if self._source_inspection:
            raise RuntimeError("Source inspection cannot publish runtime plans")
        self._area = area
        roots: dict[Any, tuple[_RootPlan, ...]] = {}
        architecture_roots: list[tuple[str | None, Any, _RootPlan]] = []
        area_records: dict[str, dict[Any, tuple[_CandidateRecord, ...]]] = {}
        selected_service_types = list(
            tuple(service_types)
            if service_types is not None
            else (self.blueprint.root_service_types() if area is None else self.blueprint.service_types(area))
        )
        if self._patterns and service_types is None and area is None:
            declared = set(self.blueprint.service_types()) | {
                target.service_type for boundary in self.blueprint.boundaries for target in boundary.resolved_exposes
            }
            selected_service_types = [
                service_type
                for service_type in selected_service_types
                if service_type in declared or get_origin(service_type) not in self._patterns
            ]
        for service_type in selected_service_types:
            # Open generic registrations are reusable activation templates, not
            # directly resolvable roots. Closed occurrences compile on demand
            # from the concrete services discovered by the builder.
            if getattr(service_type, "__parameters__", ()):
                continue
            candidates = self._compile_candidates(service_type, parent=None, argument=None)
            eligible = tuple(candidate for candidate in candidates if candidate.eligible)
            roots[service_type] = tuple(
                _RootPlan(component=candidate.component, step=candidate.step) for candidate in eligible
            )
            architecture_roots.extend((area, service_type, plan) for plan in roots[service_type])
            records = tuple(
                _CandidateRecord(
                    component=candidate.component,
                    decision=CandidateDecision(
                        component_id=candidate.component.id,
                        outcome=(DecisionOutcome.selected if candidate.eligible else DecisionOutcome.rejected),
                        reason_codes=candidate.reason_codes,
                        reason=candidate.reason,
                        origin=candidate.origin,
                    ),
                    eligible=candidate.eligible,
                )
                for candidate in candidates
            )
            if area is None:
                self.root_candidates[service_type] = records
            else:
                area_records.setdefault(area, {})[service_type] = records
            if records:
                self.decision_history.append(
                    CompilationExplanation(
                        subject=qualified_name(service_type),
                        path=(qualified_name(service_type),),
                        selected=tuple(record.decision for record in records if record.eligible),
                        rejected=tuple(record.decision for record in records if not record.eligible),
                    )
                )
            for candidate in eligible:
                selected = CandidateDecision(
                    component_id=candidate.component.id,
                    outcome=DecisionOutcome.selected,
                    reason_codes=candidate.reason_codes,
                    reason=candidate.reason,
                    origin=candidate.origin,
                )
                self.occurrence_explanations.setdefault(
                    candidate.component.occurrence_id,
                    CompilationExplanation(
                        subject=qualified_name(service_type),
                        path=(qualified_name(service_type),),
                        selected=(selected,),
                        rejected=tuple(record.decision for record in records if not record.eligible),
                    ),
                )
            if area is None:
                selected_service_types.extend(
                    request for request in self._pattern_requests if request not in selected_service_types
                )
        provider_roots = self._compile_provider_roots(roots)
        entrypoint_requests = (
            self.blueprint.entrypoints
            if area is None
            else (
                ()
                if self.blueprint.boundary(area) is None
                else cast(_BoundaryBlueprint, self.blueprint.boundary(area)).layer.entrypoints
            )
        )
        for entrypoint in entrypoint_requests:
            provider = _provider_request(entrypoint.service_type)
            if provider is None:
                continue
            self._validate_provider_target(entrypoint.service_type, provider[1])
            plans = provider_roots.get(entrypoint.service_type, ())
            if not plans:
                raise ContainerBuildError(
                    f"No component satisfies deferred root {provider[1]!r}",
                    code="provider-missing-component",
                    path=(qualified_name(entrypoint.service_type),),
                )
            roots[entrypoint.service_type] = plans
            architecture_roots.extend((area, entrypoint.service_type, plan) for plan in plans)

        if service_types is None and area is None and include_boundaries:
            for boundary in self.blueprint.boundaries:
                self._area = boundary.name
                local_records: dict[Any, tuple[_CandidateRecord, ...]] = {}
                local_service_types = self.blueprint.service_types(boundary.name)
                entrypoint_types = tuple(
                    (_collection_request(entrypoint.service_type) or (None, entrypoint.service_type))[1]
                    for entrypoint in boundary.layer.entrypoints
                )
                for service_type in dict.fromkeys((*local_service_types, *entrypoint_types)):
                    if getattr(service_type, "__parameters__", ()):
                        continue
                    candidates = self._compile_candidates(service_type, parent=None, argument=None)
                    eligible = tuple(candidate for candidate in candidates if candidate.eligible)
                    plans = tuple(
                        _RootPlan(component=candidate.component, step=candidate.step) for candidate in eligible
                    )
                    architecture_roots.extend(
                        (boundary.name, service_type, plan)
                        for plan in plans
                        if plan.component.boundary == boundary.name
                    )
                    local_records[service_type] = tuple(
                        _CandidateRecord(
                            component=candidate.component,
                            decision=CandidateDecision(
                                component_id=candidate.component.id,
                                outcome=(DecisionOutcome.selected if candidate.eligible else DecisionOutcome.rejected),
                                reason_codes=candidate.reason_codes,
                                reason=candidate.reason,
                                origin=candidate.origin,
                            ),
                            eligible=candidate.eligible,
                        )
                        for candidate in candidates
                    )
                area_records[boundary.name] = local_records
            self._area = None
        self.graph.freeze()
        default_root_groups = {
            service_type: tuple(plan for plan in plans if plan.component.name is None)
            for service_type, plans in roots.items()
        }
        return _PlanSet(
            graph=self.graph,
            roots=roots,
            default_roots={service_type: plans[0] for service_type, plans in default_root_groups.items() if plans},
            default_root_groups=default_root_groups,
            blueprint=self.blueprint,
            build_args=self.build_args,
            compiler_issues=tuple(self.issues),
            root_candidates=types.MappingProxyType(dict(self.root_candidates)),
            occurrence_explanations=types.MappingProxyType(dict(self.occurrence_explanations)),
            parameter_explanations=types.MappingProxyType(
                {
                    occurrence: types.MappingProxyType(dict(records))
                    for occurrence, records in self.parameter_explanations.items()
                }
            ),
            generic_explanations=types.MappingProxyType(dict(self.generic_explanations)),
            occurrence_layers=types.MappingProxyType(
                {occurrence: origin.layer for occurrence, origin in self.origins.items()}
            ),
            provider_roots=types.MappingProxyType(provider_roots),
            architecture_roots=tuple(architecture_roots),
            area_root_candidates=types.MappingProxyType(
                {name: types.MappingProxyType(records) for name, records in area_records.items()}
            ),
        )

    def _provider_root_component(
        self,
        annotation: Any,
        mode: typing.Literal["sync", "async"],
        target_component: Component,
        target_step: _Step,
    ) -> _RootPlan:
        provider, draft = self._draft(
            component_id=f"provider-root:{qualified_name(annotation)}:{target_component.id}",
            service_type=annotation,
            implementation=Provider if mode == "sync" else AsyncProvider,
            lifespan="transient",
            name=target_component.name,
            tags=target_component.tags,
            kind=ComponentKind.provider,
            activation=ComponentActivation.deferred,
            parent=None,
            provider_mode=mode,
            origin=self.origins.get(target_component.occurrence_id),
        )
        cloned_target = self._clone_component_tree(target_component, parent=provider)
        draft.dependency_ids = (cloned_target.occurrence_id,)
        explanation = self.occurrence_explanations.get(target_component.occurrence_id)
        if explanation is not None:
            self.occurrence_explanations[provider.occurrence_id] = replace(
                explanation,
                subject=qualified_name(annotation),
            )
        return _RootPlan(provider, _ProviderStep(mode, target_step))

    def _provider_collection_root(
        self,
        annotation: Any,
        mode: typing.Literal["sync", "async"],
        collection_type: type,
        target_type: Any,
        targets: tuple[_RootPlan, ...],
    ) -> _RootPlan:
        provider, provider_draft = self._draft(
            component_id=f"provider-root:{qualified_name(annotation)}",
            service_type=annotation,
            implementation=Provider if mode == "sync" else AsyncProvider,
            lifespan="transient",
            name=None,
            tags=(),
            kind=ComponentKind.provider,
            activation=ComponentActivation.deferred,
            parent=None,
            provider_mode=mode,
            origin=_synthetic_origin(),
        )
        target_request = get_args(annotation)[0]
        collection, collection_draft = self._draft(
            component_id=f"provider-root-collection:{qualified_name(annotation)}",
            service_type=target_request,
            implementation=collection_type,
            lifespan="transient",
            name=None,
            tags=(),
            kind=ComponentKind.collection,
            activation=ComponentActivation.collection,
            parent=provider,
            origin=_synthetic_origin(),
        )
        members = tuple(self._clone_component_tree(plan.component, parent=collection) for plan in targets)
        collection_draft.dependency_ids = tuple(member.occurrence_id for member in members)
        provider_draft.dependency_ids = (collection.occurrence_id,)
        target_steps = tuple(plan.step for plan in targets)
        step = _CollectionStep(
            collection_type,
            target_steps,
            all(target.sync_supported for target in target_steps),
        )
        self._record_component_decision(
            provider,
            subject=qualified_name(annotation),
            code="included-collection",
            reason=f"The deferred collection target {qualified_name(target_type)} was frozen at build time",
        )
        return _RootPlan(provider, _ProviderStep(mode, step))

    def _compile_provider_roots(
        self,
        roots: Mapping[Any, tuple[_RootPlan, ...]],
    ) -> dict[Any, tuple[_RootPlan, ...]]:
        provider_roots: dict[Any, tuple[_RootPlan, ...]] = {}
        for service_type, target_plans in tuple(roots.items()):
            if _provider_request(service_type) is not None or _collection_request(service_type) is not None:
                continue
            base_records = self.root_candidates.get(service_type, ())
            origins = {record.component.occurrence_id: record.decision.origin for record in base_records}
            for provider_type, mode in ((Provider, "sync"), (AsyncProvider, "async")):
                annotation = provider_type[service_type]
                plans = tuple(
                    self._provider_root_component(annotation, mode, plan.component, plan.step) for plan in target_plans
                )
                provider_roots[annotation] = plans
                records: list[_CandidateRecord] = []
                for plan, target in zip(plans, target_plans, strict=True):
                    origin = origins.get(target.component.occurrence_id, _synthetic_origin())
                    records.append(
                        _CandidateRecord(
                            plan.component,
                            CandidateDecision(
                                plan.component.id,
                                DecisionOutcome.selected,
                                ("provider-target-frozen",),
                                "The provider target plan was selected and frozen during compilation",
                                origin,
                            ),
                            True,
                        )
                    )
                self.root_candidates[annotation] = tuple(records)

                unnamed_targets = tuple(plan for plan in target_plans if plan.component.name is None)
                for collection_type in (list, tuple, set):
                    collection_target = (
                        tuple[service_type, ...] if collection_type is tuple else collection_type[service_type]
                    )
                    collection_annotation = provider_type[collection_target]
                    collection_plan = self._provider_collection_root(
                        collection_annotation,
                        mode,
                        collection_type,
                        service_type,
                        unnamed_targets,
                    )
                    provider_roots[collection_annotation] = (collection_plan,)
                    self.root_candidates[collection_annotation] = (
                        _CandidateRecord(
                            collection_plan.component,
                            CandidateDecision(
                                collection_plan.component.id,
                                DecisionOutcome.selected,
                                ("included-collection", "provider-target-frozen"),
                                "The provider collection membership was selected and frozen during compilation",
                                _synthetic_origin(),
                            ),
                            True,
                        ),
                    )
        return provider_roots

    def _specialize_factory(
        self,
        registration: legacy._Registration,
        layer: _Layer,
        requested_service_type: Any,
    ) -> legacy._Registration:
        if registration.id not in layer.factory_ids:
            return registration
        key = (registration.id, _runtime_type_key(requested_service_type))
        cached = self._specialized_factories.get(key)
        if cached is not None:
            return cached

        is_pattern = registration.id in layer.pattern_ids
        dependency_annotations: tuple[tuple[str, Any, Any], ...] = ()
        if is_pattern:
            pattern_stack = [item for item in self._stack if item.id in self._pattern_sources]
            active = [item for item in pattern_stack if self._pattern_sources[item.id] == registration.id]
            if (
                len(active) >= 16 and patterns.size(requested_service_type) >= patterns.size(active[-1].service_type)
            ) or (
                len(pattern_stack) >= 32
                and patterns.size(requested_service_type) >= patterns.size(pattern_stack[-1].service_type)
            ):
                raise ContainerBuildError(
                    "Registration pattern specialization keeps expanding; non-shrinking paths are limited to "
                    "16 active specializations of one template or 32 across all templates",
                    code="pattern-non-terminating-expansion",
                    path=self._current_path(requested_service_type),
                )
            factory = cast(Callable[..., Any], registration.implementation)
            result_annotation = _factory_result_annotation(factory)
            annotations = (
                *(dependency.service_type for dependency in registration.dependencies.values()),
                result_annotation,
            )
            try:
                bindings = patterns.factory_bindings(registration.service_type, requested_service_type, annotations)
                if result_annotation is not inspect.Signature.empty:
                    result = _resolve_factory_typevars(result_annotation, bindings)
                    if not patterns.equivalent(result, requested_service_type):
                        raise patterns.PatternError(
                            "Factory result annotation conflicts with its closed pattern service",
                            "pattern-incompatible-binding",
                        )
                if any(_unsupported_factory_type_parameters(annotation) for annotation in annotations):
                    raise patterns.PatternError("Pattern factories support TypeVar parameters only")
                dependencies = {}
                for name, dependency in registration.dependencies.items():
                    before = dependency.declared_service_type
                    after = _resolve_factory_typevars(dependency.service_type, bindings)
                    specialized_dependency = legacy.Dependency(
                        name=dependency.name,
                        parent_implementation=factory,
                        service_type=after,
                        settings=dependency.settings,
                        default_value=dependency.default_value,
                    )
                    specialized_dependency.declared_service_type = _resolve_factory_typevars(
                        dependency.declared_service_type, bindings
                    )
                    dependencies[name] = specialized_dependency
                    dependency_annotations += ((name, before, after),)
            except patterns.PatternError as error:
                raise ContainerBuildError(
                    str(error), code=error.code, path=self._current_path(requested_service_type)
                ) from error
        else:
            dependencies, dependency_annotations = _specialized_factory_dependencies(
                registration,
                requested_service_type,
                layer.factory_specializations.get(registration.id),
            )
        is_open_specialization = registration.service_type != requested_service_type
        if not is_open_specialization and dependencies is registration.dependencies:
            return registration

        specialized = legacy._Registration(
            activator_class=registration.activator_class,
            service_type=requested_service_type,
            implementation=registration.implementation,
            lifespan=registration.lifespan,
            name=registration.name,
            parent_node_filter=registration.parent_node_filter,
            tags=registration.tags,
        )
        specialized.id = (
            _specialized_component_id(registration.id, requested_service_type)
            if is_open_specialization
            else registration.id
        )
        specialized.declared_service_type = registration.declared_service_type
        specialized.dependencies = dependencies
        if dependency_annotations:
            self._specialized_dependency_annotations[specialized.id] = dependency_annotations
        if is_pattern:
            # Pattern bindings are a separate scope from service bindings.
            # Number duplicate names deterministically instead of implying they
            # are one TypeVar merely because their display names match.
            seen: dict[str, int] = {}
            rendered: list[tuple[str, str]] = []
            for binding_key, value in sorted(
                bindings.items(),
                key=lambda item: (
                    item[0] if isinstance(item[0], str) else getattr(item[0], "__name__", ""),
                    qualified_name(item[1]),
                ),
            ):
                name = binding_key if isinstance(binding_key, str) else getattr(binding_key, "__name__", "TypeVar")
                seen[name] = seen.get(name, 0) + 1
                rendered_name = name if isinstance(binding_key, str) else f"{name}#{seen[name]}"
                rendered.append((rendered_name, qualified_name(value)))
            self._factory_pattern_bindings[specialized.id] = tuple(rendered)
        self._specialized_registration_sources[specialized.id] = registration
        self._specialized_factories[key] = specialized
        self._specialized_service_groups[specialized.id] = layer.service_groups.get(registration.id, frozenset())
        if is_pattern:
            self._pattern_sources[specialized.id] = registration.id
        return specialized

    def _service_groups_for(self, registration: legacy._Registration, layer: _Layer) -> frozenset[ServiceGroup]:
        """Resolve membership for either a definition or its specialized copy."""
        return self._specialized_service_groups.get(
            registration.id,
            layer.service_groups.get(registration.id, frozenset()),
        )

    def _select_service_target(
        self,
        selector: ServiceGroup | DerivedServices,
        registration: legacy._Registration,
        layer: _Layer,
        requested_service_type: Any,
    ) -> _ServiceTarget | None:
        """Project an already visible concrete candidate, preserving definition identity."""
        source = self._specialized_registration_sources.get(registration.id, registration)
        try:
            return _select_service_target(
                selector,
                registration_id=source.id,
                registered_service_type=source.service_type,
                requested_service_type=requested_service_type,
                groups=self._service_groups_for(registration, layer),
            )
        except (TypeError, ValueError) as error:
            label = (
                f"service group {selector.name!r}"
                if isinstance(selector, ServiceGroup)
                else f"derived services {selector.service_type!r}"
            )
            raise ContainerBuildError(
                f"Registration {source.id} for {qualified_name(requested_service_type)} "
                f"cannot satisfy {label}: {error}",
                code="service-group-incompatible"
                if isinstance(selector, ServiceGroup)
                else "service-target-projection",
                path=self._current_path(requested_service_type),
            ) from error

    def _select_service_targets(
        self,
        selector: ServiceGroup | DerivedServices,
        candidates: Iterable[tuple[legacy._Registration, _Layer, Any]],
    ) -> tuple[_ServiceTarget, ...]:
        """Select a finite, already visible candidate stream in its existing order.

        Repeated views of one definition/request/owner produce one target. This
        does not discover requests or collapse distinct registrations of a class.
        """
        selected: list[_ServiceTarget] = []
        seen: set[tuple[str, tuple[Any, ...], str]] = set()
        for registration, layer, request in candidates:
            target = self._select_service_target(selector, registration, layer, request)
            if target is None:
                continue
            key = (target.registration_id, _runtime_type_key(normalize_type_alias(request)), layer.owner_token)
            if key not in seen:
                seen.add(key)
                selected.append(target)
        return tuple(selected)

    def _pattern_candidates(
        self, service_type: Any, registrations: list[tuple[legacy._Registration, _Layer]]
    ) -> tuple[list[tuple[legacy._Registration, _Layer]], list[_CompiledCandidate]]:
        available = [
            item
            for item in self._patterns.get(get_origin(service_type), ())
            if self.blueprint.registration_area(item[1]) == self._area
            or any(item[0].id == registration.id for registration, _ in registrations)
        ]
        exact = [item for item in registrations if item[0].id not in item[1].pattern_ids]
        try:
            winners = exact or _winning_patterns(available, service_type)
        except ContainerBuildError as error:
            self.decision_history.append(
                CompilationExplanation(
                    subject=qualified_name(service_type),
                    path=self._current_path(service_type),
                    selected=(),
                    rejected=tuple(
                        CandidateDecision(
                            registration.id,
                            DecisionOutcome.rejected,
                            (error.code or "pattern-invalid",),
                            "The structural templates cannot select a unique supported specialization",
                            self.blueprint.registration_origin(registration.id, layer),
                        )
                        for registration, layer in available
                    ),
                )
            )
            raise ContainerBuildError(str(error), code=error.code, path=self._current_path(service_type)) from error
        selected_ids = {registration.id for registration, _ in winners}
        rejected = []
        for registration, layer in available:
            if registration.id in selected_ids:
                continue
            if exact:
                code, reason = "pattern-shadowed-by-exact", "An exact closed registration takes precedence"
            elif patterns.match(registration.service_type, service_type) is None:
                code, reason = "pattern-mismatch", "The template structure or TypeVar domain does not match"
            else:
                code, reason = "pattern-less-specific", "A structurally more specific template takes precedence"
            rejected.append(
                _CompiledCandidate(
                    _boundary_component(
                        registration,
                        service_type=service_type,
                        build_args=self.build_args,
                        boundary=self.blueprint.registration_area(layer),
                    ),
                    _ValueStep(None),
                    self.blueprint.registration_origin(registration.id, layer),
                    False,
                    (code,),
                    reason,
                )
            )
        if winners and not exact and self._area is None:
            self._pattern_requests[service_type] = None
        return winners, rejected

    def _draft(
        self,
        *,
        component_id: str,
        service_type: Any,
        implementation: Any,
        lifespan: Lifespan,
        name: str | None,
        tags: Iterable[legacy.Tag],
        kind: ComponentKind,
        activation: ComponentActivation,
        parent: Component | None,
        argument: str | None = None,
        requires_async: bool = False,
        manages_cleanup: bool = False,
        position: int | None = None,
        provider_mode: typing.Literal["sync", "async"] | None = None,
        build_args: Mapping[str, Any] | None = None,
        origin: DefinitionOrigin | None = None,
        declared_service_type: Any | None = None,
    ) -> tuple[Component, _ComponentDraft]:
        occurrence = self._next_occurrence
        self._next_occurrence += 1
        cache_owner, cleanup_owner, owner_id, ownership_reason = self._compiled_ownership(
            lifespan,
            kind,
            manages_cleanup,
        )
        draft = _ComponentDraft(
            id=component_id,
            occurrence_id=occurrence,
            service_type=service_type,
            implementation=implementation,
            implementation_type=normalize_implementation_type(implementation, service_type),
            lifespan=lifespan,
            name=name,
            tags=tuple(tags),
            build_args=self.build_args if build_args is None else build_args,
            kind=kind,
            activation=activation,
            requires_async=requires_async,
            manages_cleanup=manages_cleanup,
            cache_owner=cache_owner,
            cleanup_owner=cleanup_owner,
            owner_id=owner_id,
            ownership_reason=ownership_reason,
            provider_mode=provider_mode,
            position=position,
            parent_id=None if parent is None else parent.occurrence_id,
            argument=argument,
            boundary=(origin.boundary if origin is not None else self._area),
            declared_service_type=declared_service_type,
        )
        component = self.graph.add(draft)
        self.origins[occurrence] = origin or _synthetic_origin()
        return component, draft

    def _compile_candidates(
        self,
        service_type: Any,
        parent: Component | None,
        argument: str | None,
        *,
        deferred_mode: typing.Literal["sync", "async"] | None = None,
        provider_map_group: ProviderMapGroup[Any, Any] | None = None,
    ) -> list[_CompiledCandidate]:
        service_type = normalize_type_alias(service_type)
        local_registrations = self.blueprint.local_registrations(self._area, service_type)
        visible_registrations = self.blueprint.visible_registrations(service_type, self._area)
        candidates: list[_CompiledCandidate] = []
        if self._patterns:
            local_registrations, candidates = self._pattern_candidates(service_type, local_registrations)
        registrations: list[tuple[legacy._Registration, _Layer, _VisibilityTarget | None]] = [
            *((registration, layer, None) for registration, layer in local_registrations),
            *visible_registrations,
        ]
        if not registrations and get_origin(service_type) is not None:
            registrations = [
                (registration, layer, None)
                for registration, layer in self.blueprint.local_registrations(self._area, get_origin(service_type))
            ]
        if provider_map_group is not None:
            registrations = [
                (registration, layer, visibility_target)
                for registration, layer, visibility_target in registrations
                if provider_map_group in layer.contributions.get(registration.id, {})
            ]
        for registration_index, (source_registration, layer, visibility_target) in enumerate(registrations):
            origin = self.blueprint.registration_origin(source_registration.id, layer)
            consumer_area = self._area
            definition_area = self.blueprint.registration_area(layer)
            source_service_type = (
                service_type
                if visibility_target is None
                else _source_request_for_visibility(visibility_target, service_type)
            )
            if visibility_target is not None and (
                source_registration.id in layer.pattern_ids or patterns.variables(visibility_target.service_type)
            ):
                self._pattern_requests[service_type] = None
            self._partial_candidate_labels[source_registration.id] = qualified_name(source_registration.implementation)
            try:
                registration = self._specialize_factory(source_registration, layer, source_service_type)
            except ContainerBuildError as error:
                self._record_partial_candidate(
                    (
                        qualified_name(service_type),
                        source_registration.id,
                        PartialState.failed,
                        error.code or "generic-specialization",
                    )
                )
                for pending, _, _ in registrations[registration_index + 1 :]:
                    self._partial_candidate_labels[pending.id] = qualified_name(pending.implementation)
                    self._record_partial_candidate(
                        (qualified_name(service_type), pending.id, PartialState.not_examined, None)
                    )
                self.decision_history.append(
                    CompilationExplanation(
                        subject=qualified_name(service_type),
                        path=self._current_path(service_type),
                        selected=(),
                        rejected=(
                            CandidateDecision(
                                source_registration.id,
                                DecisionOutcome.rejected,
                                ("rejected-generic-binding",),
                                "The registration could not be specialized for the requested generic binding",
                                origin,
                            ),
                        ),
                    )
                )
                raise ContainerBuildError(
                    str(error),
                    code=error.code or "generic-specialization",
                    path=error.path or self._current_path(service_type),
                ) from error
            candidate_parent = parent
            if deferred_mode is not None:
                candidate_parent, _ = self._draft(
                    component_id=f"provider-map-entry:{parent.id if parent else ''}:{source_registration.id}",
                    service_type=(Provider if deferred_mode == "sync" else AsyncProvider)[service_type],
                    implementation=Provider if deferred_mode == "sync" else AsyncProvider,
                    lifespan="transient",
                    name=None,
                    tags=(),
                    kind=ComponentKind.provider,
                    activation=ComponentActivation.deferred,
                    parent=parent,
                    provider_mode=deferred_mode,
                    origin=self.origins.get(parent.occurrence_id) if parent else None,
                )
                self._frames.append(
                    _CompilerFrame(
                        candidate_parent.service_type,
                        legacy.Lifespan.transient,
                        layer.owner_token,
                        ComponentKind.provider,
                        candidate_parent,
                    )
                )
            try:
                self._area = definition_area
                component, step = self._compile_registration(
                    registration,
                    layer,
                    parent=candidate_parent,
                    argument=argument,
                    requested_service_type=source_service_type,
                    origin=origin,
                )
            except ContainerBuildError as error:
                # The structural compilation failed before its `when` predicate
                # could run; diagnostic output must not call it rejected.
                self._record_partial_candidate(
                    (
                        qualified_name(service_type),
                        registration.id,
                        PartialState.failed,
                        error.code or _build_error_code(error),
                    )
                )
                for pending, _, _ in registrations[registration_index + 1 :]:
                    self._partial_candidate_labels[pending.id] = qualified_name(pending.implementation)
                    self._record_partial_candidate(
                        (qualified_name(service_type), pending.id, PartialState.not_examined, None)
                    )
                if (
                    error.code == "overlay-singleton"
                    and registration.lifespan == legacy.Lifespan.singleton
                    and layer.owner_token in self._anchored_owner_tokens
                ):
                    self.decision_history.append(
                        CompilationExplanation(
                            subject=qualified_name(service_type),
                            path=self._current_path(service_type),
                            selected=(),
                            rejected=(
                                CandidateDecision(
                                    registration.id,
                                    DecisionOutcome.rejected,
                                    ("rejected-overlay-visibility",),
                                    "The parent singleton has no visible frozen specialization in this overlay",
                                    origin,
                                ),
                            ),
                        )
                    )
                raise
            finally:
                self._area = consumer_area
                if deferred_mode is not None:
                    self._frames.pop()
            predicate = layer.registration_when.get(source_registration.id)
            component_record = cast(_ComponentDraft, self.graph.record(component.occurrence_id))
            if visibility_target is not None:
                # An anchored plan may already carry its parent's public view.
                # Definition-side eligibility always observes the source view.
                component_record.service_type = source_service_type
                component_record.name = registration.name
                component_record.tags = tuple(registration.tags)
            original_parent_id = component_record.parent_id
            if definition_area != consumer_area:
                # The component keeps its real graph parent, but contextual
                # predicates are evaluated at the defining side of a boundary.
                # A consumer cannot make a source registration eligible merely
                # by being its caller.
                component_record.parent_id = None
            try:
                registration_matches = predicate is None or predicate(component)
            except Exception as error:
                self._record_partial_candidate(
                    (qualified_name(service_type), registration.id, PartialState.failed, "filter-evaluation-failed")
                )
                failed = CandidateDecision(
                    component.id,
                    DecisionOutcome.rejected,
                    ("rejected-filter",),
                    f"Registration filter {_filter_description(cast(ComponentFilter, predicate))} "
                    f"raised {type(error).__name__}",
                    origin,
                )
                self.decision_history.append(
                    CompilationExplanation(
                        subject=qualified_name(service_type),
                        path=self._current_path(service_type),
                        selected=(),
                        rejected=(failed,),
                    )
                )
                component_record.parent_id = original_parent_id
                raise
            try:
                if not registration_matches:
                    self._record_partial_candidate(
                        (qualified_name(service_type), registration.id, PartialState.rejected, "rejected-filter")
                    )
                    candidates.append(
                        _CompiledCandidate(
                            component,
                            step,
                            origin,
                            False,
                            ("rejected-filter",),
                            f"Registration filter {_filter_description(predicate)} returned false",
                        )
                    )
                    continue
                if registration.parent_node_filter is not legacy.default_parent_node_filter:
                    if component.parent is None or not registration.parent_node_filter(cast(Any, component.parent)):
                        self._record_partial_candidate(
                            (qualified_name(service_type), registration.id, PartialState.rejected, "rejected-filter")
                        )
                        candidates.append(
                            _CompiledCandidate(
                                component,
                                step,
                                origin,
                                False,
                                ("rejected-filter",),
                                "The contextual parent filter returned false",
                            )
                        )
                        continue
            finally:
                component_record.parent_id = original_parent_id
                if visibility_target is not None:
                    component_record.service_type = service_type
                    component_record.name = visibility_target.name
                    component_record.tags = visibility_target.tags
            boundary_code, boundary_reason = self.blueprint.visibility_reason(
                consumer_area, source_registration.id, layer
            )
            codes: list[str] = ["registration-eligible"]
            if source_registration.id in layer.pattern_ids:
                codes.append("selected-registration-pattern")
            if boundary_code:
                codes.append(boundary_code)
            reasons = [boundary_reason, "the contextual filter matched"]
            if source_registration.service_type != source_service_type and (
                get_origin(source_service_type) is not None
                or bool(getattr(source_registration.service_type, "__parameters__", ()))
            ):
                codes.append("specialized-generic")
                reasons.append(
                    f"specialized {qualified_name(source_registration.service_type)} "
                    f"for {qualified_name(source_service_type)}"
                )
            if registration.lifespan == legacy.Lifespan.singleton and layer.owner_token in self._anchored_owner_tokens:
                codes.append("anchored-parent-singleton")
                reasons.append("the occurrence retains its frozen parent singleton plan")
            candidates.append(
                _CompiledCandidate(
                    component,
                    step,
                    origin,
                    True,
                    tuple(codes),
                    "; ".join(reasons),
                    source_registration.id,
                    layer,
                )
            )
        return candidates

    def _select_candidates(
        self,
        candidates: Iterable[_CompiledCandidate],
        filter: ComponentFilter,
        *,
        service_type: Any,
        subject: str,
        collection: bool = False,
        explanation_component: Component | None = None,
    ) -> list[_CompiledCandidate]:
        """Apply a selection filter once and retain its safe outcome."""

        considered = tuple(candidates)
        selected_candidates: list[_CompiledCandidate] = []
        selected: list[CandidateDecision] = []
        rejected: list[CandidateDecision] = []
        description = _filter_description(filter)
        default_selection = description.endswith("default_component_filter")
        for candidate_index, candidate in enumerate(considered):
            if not candidate.eligible:
                rejected.append(
                    CandidateDecision(
                        candidate.component.id,
                        DecisionOutcome.rejected,
                        candidate.reason_codes,
                        candidate.reason,
                        candidate.origin,
                    )
                )
                continue
            try:
                matched = filter(candidate.component)
            except Exception as error:
                self._partial_candidate_labels[candidate.component.id] = qualified_name(
                    candidate.component.implementation
                )
                self._record_partial_candidate(
                    (subject, candidate.component.id, PartialState.failed, "filter-evaluation-failed")
                )
                for pending in considered[candidate_index + 1 :]:
                    self._partial_candidate_labels[pending.component.id] = qualified_name(
                        pending.component.implementation
                    )
                    self._record_partial_candidate((subject, pending.component.id, PartialState.not_examined, None))
                rejected.append(
                    CandidateDecision(
                        candidate.component.id,
                        DecisionOutcome.rejected,
                        ("rejected-filter",),
                        f"The filter {description} raised {type(error).__name__}",
                        candidate.origin,
                    )
                )
                self.decision_history.append(
                    CompilationExplanation(
                        subject=subject,
                        path=self._current_path(service_type),
                        selected=tuple(selected),
                        rejected=tuple(rejected),
                    )
                )
                raise
            if matched:
                selected_candidates.append(candidate)
                selection_code = (
                    "included-collection"
                    if collection
                    else ("selected-default" if default_selection else "selected-explicit-filter")
                )
                extra_codes = tuple(code for code in candidate.reason_codes if code != "registration-eligible")
                selected.append(
                    CandidateDecision(
                        candidate.component.id,
                        DecisionOutcome.included if collection else DecisionOutcome.selected,
                        (selection_code, *extra_codes),
                        (
                            f"The component was included because {description} returned true"
                            if collection
                            else f"The component was selected because {description} returned true"
                        ),
                        candidate.origin,
                    )
                )
            else:
                rejection_code = "rejected-name" if default_selection else "rejected-filter"
                rejected.append(
                    CandidateDecision(
                        candidate.component.id,
                        DecisionOutcome.rejected,
                        (rejection_code,),
                        f"The component was rejected because {description} returned false",
                        candidate.origin,
                    )
                )
        explanation = CompilationExplanation(
            subject=subject,
            path=self._current_path(service_type),
            selected=tuple(selected),
            rejected=tuple(rejected),
        )
        self.decision_history.append(explanation)
        for candidate in selected_candidates:
            self.occurrence_explanations[candidate.component.occurrence_id] = explanation
        if explanation_component is not None:
            self.occurrence_explanations[explanation_component.occurrence_id] = explanation
        return selected_candidates

    def _record_component_decision(
        self,
        component: Component,
        *,
        subject: str,
        code: str,
        reason: str,
        origin: DefinitionOrigin | None = None,
    ) -> None:
        selected = CandidateDecision(
            component.id,
            DecisionOutcome.selected,
            (code,),
            reason,
            origin or self.origins.get(component.occurrence_id, _synthetic_origin()),
        )
        explanation = CompilationExplanation(
            subject=subject,
            path=self._current_path(component.service_type),
            selected=(selected,),
            rejected=(),
        )
        self.occurrence_explanations[component.occurrence_id] = explanation
        self.decision_history.append(explanation)

    def _dependency_alias_result(
        self,
        result: tuple[_Step, Component | None],
        declared_type: Any,
        canonical_type: Any,
    ) -> tuple[_Step, Component | None]:
        component = result[1]
        if component is None or declared_type == canonical_type:
            return result
        explanation = self.occurrence_explanations.get(component.occurrence_id)
        if explanation is not None:
            updated = replace(
                explanation,
                subject=(
                    f"{explanation.subject} " f"({qualified_name(declared_type)} -> {qualified_name(canonical_type)})"
                ),
            )
            self.occurrence_explanations[component.occurrence_id] = updated
            for index in range(len(self.decision_history) - 1, -1, -1):
                if self.decision_history[index] is explanation:
                    self.decision_history[index] = updated
                    break
        return result

    def _compile_registration(
        self,
        registration: legacy._Registration,
        layer: _Layer,
        *,
        parent: Component | None,
        argument: str | None,
        requested_service_type: Any,
        origin: DefinitionOrigin,
    ) -> tuple[Component, _RegistrationStep]:
        # Deferred membership constraints become enforceable only for the actual
        # concrete request (constructors, factories and patterns share this seam).
        groups = self._service_groups_for(registration, layer)
        for group in sorted(groups, key=lambda item: (item.name, qualified_name(item.service_type))):
            self._select_service_target(group, registration, layer, requested_service_type)
        map_definition = layer.provider_maps.get(registration.id)
        _validate_dependency_names(registration.implementation, registration.dependencies)
        if registration.lifespan == legacy.Lifespan.singleton and layer.owner_token in self._anchored_owner_tokens:
            anchored = self._anchored_singletons.get((registration.id, _runtime_type_key(requested_service_type)))
            if anchored is None:
                raise ContainerBuildError(
                    f"Parent-owned singleton {requested_service_type!r} has no frozen parent specialization; "
                    "override the singleton in the scope builder",
                    code="overlay-singleton",
                    path=self._current_path(requested_service_type),
                )
            return self._clone_component_tree(anchored.component, parent=parent, argument=argument), anchored
        if registration in self._stack:
            for index in range(len(self._partial_edges) - 1, -1, -1):
                _, _, requested, target = self._partial_edges[index]
                if target is None and requested == qualified_name(registration.service_type):
                    self._partial_back_references.add(index)
                    break
            path = " -> ".join(qualified_name(item.service_type) for item in (*self._stack, registration))
            raise ContainerBuildError(
                f"Circular component dependency: {path}",
                code="circular-dependency",
                path=self._current_path(registration.service_type),
            )
        self._validate_captive_lifespan(
            registration.service_type,
            registration.lifespan,
            is_instance=registration.is_instance,
        )
        anchored_owner = next(
            (
                item
                for item in reversed(self._retention_frames())
                if item.lifespan == legacy.Lifespan.singleton and item.owner_token in self._anchored_owner_tokens
            ),
            None,
        )
        if (
            anchored_owner is not None
            and registration.lifespan == legacy.Lifespan.singleton
            and layer.owner_token != anchored_owner.owner_token
        ):
            raise ContainerBuildError(
                f"{_frame_description(anchored_owner)} cannot retain overlay-owned singleton "
                f"{registration.service_type}",
                code="captive-dependency",
                path=self._current_path(registration.service_type),
            )

        component, draft = self._draft(
            component_id=registration.id,
            service_type=requested_service_type,
            implementation=registration.implementation if map_definition is None else Mapping,
            lifespan=_component_lifespan(registration.lifespan),
            name=registration.name,
            tags=registration.tags,
            kind=ComponentKind.registration if map_definition is None else ComponentKind.provider_map,
            activation=_registration_activation(registration)
            if map_definition is None
            else ComponentActivation.collection,
            parent=parent,
            argument=argument,
            requires_async=_requires_async(registration.activator_class, registration.implementation),
            manages_cleanup=_manages_cleanup(registration.activator_class, registration.implementation),
            origin=origin,
            declared_service_type=registration.declared_service_type,
        )
        self._stack.append(registration)
        self._frames.append(
            _CompilerFrame(
                label=requested_service_type,
                lifespan=registration.lifespan,
                owner_token=layer.owner_token,
                kind=ComponentKind.registration,
                component=component,
            )
        )
        try:
            key_indices: Mapping[Hashable, int] = {}
            if map_definition is None:
                dependencies = self._compile_dependencies(registration.dependencies, component)
                self._record_generic_explanation(component, registration.dependencies)
            else:
                dependencies, key_indices = self._compile_provider_map(map_definition, component, draft)
            resolution_requests = self._compile_resolution_requests(registration.implementation, component)
            draft.dependency_ids += tuple(item.component.occurrence_id for item in resolution_requests)
            dependencies = self._bind_resolution_requests(
                registration.implementation,
                dependencies,
                resolution_requests,
            )
            configurations = self._compile_pre_configurations(component)
            draft.pre_configuration_ids = tuple(item.component.occurrence_id for item in configurations)
            decorators = self._compile_decorators(registration, layer, component)
            # Component inspection presents the final pipeline outside-to-inside,
            # while runtime activation retains the core-to-outside order.
            draft.decorator_ids = tuple(item.component.occurrence_id for item in reversed(decorators))
            step_type = _REGISTRATION_STEP_TYPES[registration.lifespan] if map_definition is None else _ProviderMapStep
            step = step_type(
                registration=registration,
                source_service_type=requested_service_type,
                owner_token=layer.owner_token,
                component=component,
                dependencies=dependencies,
                pre_configurations=configurations,
                decorators=decorators,
                cleanup_owner=self._cleanup_descriptor(
                    component,
                    declaring_owner_token=layer.owner_token,
                ),
                sync_supported=(
                    not _requires_async(registration.activator_class, registration.implementation)
                    and all(dependency.step.sync_supported for dependency in dependencies)
                    and all(item.sync_supported for item in configurations)
                    and all(item.sync_supported for item in decorators)
                ),
                **({} if map_definition is None else {"key_indices": key_indices}),
            )
            return component, step
        finally:
            self._frames.pop()
            self._stack.pop()

    def _compile_provider_map(
        self, definition: _ProviderMapDefinition, component: Component, draft: _ComponentDraft
    ) -> tuple[tuple[_CompiledDependency, ...], Mapping[Hashable, int]]:
        _, provider_type = get_args(component.service_type)
        mode, target = cast(tuple[typing.Literal["sync", "async"], Any], _provider_request(provider_type))
        collection, target = self._validate_provider_target(provider_type, target)
        if collection is not None:
            raise ContainerBuildError(
                "Provider map targets must be individual closed service types",
                code="provider-invalid-target",
                path=self._current_path(),
            )
        callback = definition.key
        if definition.group is None:
            try:
                valid_callback = callable(callback) and not any(
                    inspect.iscoroutinefunction(value) or inspect.isasyncgenfunction(value)
                    for value in (callback, getattr(callback, "__call__", None))
                )
            except Exception:
                valid_callback = False
            if not valid_callback:
                raise ContainerBuildError(
                    "Provider map key must be a synchronous callable",
                    code="provider-map-invalid-key",
                    path=self._current_path(),
                )
        capturing_singleton = next(
            (frame for frame in reversed(self._retention_frames()) if frame.lifespan == legacy.Lifespan.singleton),
            None,
        )
        candidates = self._compile_candidates(
            target,
            component,
            None,
            deferred_mode=mode,
            provider_map_group=definition.group,
        )
        candidates = self._select_candidates(
            candidates,
            definition.component_filter,
            service_type=target,
            subject="Provider map target selection",
            collection=True,
            explanation_component=component,
        )
        indices: dict[Hashable, int] = {}
        dependencies: list[_CompiledDependency] = []
        child_ids: list[int] = []
        for index, candidate in enumerate(candidates):
            target_component = candidate.component
            provider = cast(Component, target_component.parent)
            provider_draft = cast(_ComponentDraft, self.graph.record(provider.occurrence_id))
            provider_draft.dependency_ids = (target_component.occurrence_id,)
            if mode == "sync" and not candidate.step.sync_supported:
                raise ContainerBuildError(
                    "Synchronous provider map target requires AsyncProvider",
                    code="provider-requires-async",
                    path=self._current_path(target),
                )
            if capturing_singleton is not None:
                forbidden = self._provider_forbidden_path(target_component)
                if forbidden is not None:
                    raise ContainerBuildError(
                        "Singleton cannot retain a provider map whose target reaches scoped state",
                        code="provider-captive-scope",
                        path=self._current_path(*(item.service_type for item in forbidden)),
                    )
            path = self._current_path(target)
            if definition.group is not None:
                if candidate.source_layer is None or candidate.source_registration_id is None:
                    raise RuntimeError("Provider-map contribution source was not retained during compilation")
                key = candidate.source_layer.contributions[candidate.source_registration_id][definition.group]
            else:
                try:
                    key = cast(Callable[[Component], Hashable], callback)(target_component)
                except Exception:
                    raise ContainerBuildError(
                        "Provider map key evaluation failed", code="provider-map-key-evaluation", path=path
                    ) from None
            if inspect.isawaitable(key) or inspect.isasyncgen(key):
                try:
                    if inspect.iscoroutine(key):
                        key.close()
                except Exception:  # noqa: S110
                    # Invalid async results remain a safe, structured error even
                    # when closing a started coroutine runs a failing finalizer.
                    pass
                raise ContainerBuildError(
                    "Provider map key callback returned an asynchronous result",
                    code="provider-map-invalid-key",
                    path=path,
                )
            try:
                hash(key)
            except TypeError:
                raise ContainerBuildError(
                    "Provider map key is unhashable",
                    code="provider-map-unhashable-key",
                    path=path,
                ) from None
            except Exception:
                raise ContainerBuildError(
                    "Provider map key hashing failed", code="provider-map-key-evaluation", path=path
                ) from None
            try:
                before = len(indices)
                existing_index = indices.setdefault(key, index)
            except Exception:
                raise ContainerBuildError(
                    "Provider map key hashing or equality failed", code="provider-map-key-evaluation", path=path
                ) from None
            if len(indices) == before:
                raise ContainerBuildError(
                    f"Provider map entries {existing_index} and {index} produced duplicate keys",
                    code="provider-map-duplicate-key",
                    path=path,
                ) from None
            provider_step = _ProviderStep(
                mode, candidate.step, None if capturing_singleton is None else capturing_singleton.owner_token
            )
            dependencies.append(_CompiledDependency(str(index), provider_step))
            child_ids.append(provider.occurrence_id)
            self.occurrence_explanations[provider.occurrence_id] = CompilationExplanation(
                subject=qualified_name(provider.service_type),
                path=path,
                selected=(
                    CandidateDecision(
                        target_component.id,
                        DecisionOutcome.selected,
                        ("provider-target-frozen",),
                        "The provider map entry target was selected and frozen during compilation",
                        candidate.origin,
                    ),
                ),
                rejected=(),
            )
        draft.dependency_ids = tuple(child_ids)
        draft.provider_mode = mode
        return tuple(dependencies), types.MappingProxyType(indices)

    def _clone_component_tree(
        self,
        source: Component,
        *,
        parent: Component | None,
        argument: str | None = None,
        mapped: dict[int, Component] | None = None,
    ) -> Component:
        """Copy frozen metadata while retaining the parent's activation step."""

        mapping = mapped if mapped is not None else {}
        component, draft = self._draft(
            component_id=source.id,
            service_type=source.service_type,
            implementation=source.implementation,
            lifespan=source.lifespan,
            name=source.name,
            tags=source.tags,
            kind=source.kind,
            activation=source.activation,
            parent=parent,
            argument=source.argument if argument is None else argument,
            requires_async=source.requires_async,
            manages_cleanup=source.manages_cleanup,
            position=source.position,
            provider_mode=source.provider_mode,
            build_args=source.build_args,
            origin=self.origins.get(source.occurrence_id),
            declared_service_type=source.declared_service_type,
        )
        draft.implementation_type = source.implementation_type
        draft.boundary = source.boundary
        draft.cache_owner = source.cache_owner
        draft.cleanup_owner = source.cleanup_owner
        draft.ownership_reason = source.ownership_reason
        if source.owner_occurrence_id is not None:
            cloned_owner = mapping.get(source.owner_occurrence_id)
            if cloned_owner is None:
                raise ContainerBuildError(
                    "Anchored activation metadata has an owner outside its cloned path",
                    code="cleanup-owner-conflict",
                    path=self._current_path(source.service_type),
                )
            draft.owner_id = cloned_owner.occurrence_id
        mapping[source.occurrence_id] = component
        explanation = self.occurrence_explanations.get(source.occurrence_id)
        if explanation is not None:
            self.occurrence_explanations[component.occurrence_id] = explanation
        parameters = self.parameter_explanations.get(source.occurrence_id) or (
            self._inherited_parameter_explanations.get(source.occurrence_id)
        )
        if parameters is not None:
            self.parameter_explanations[component.occurrence_id] = dict(parameters)
        generic = self.generic_explanations.get(source.occurrence_id) or self._inherited_generic_explanations.get(
            source.occurrence_id
        )
        if generic is not None:
            self.generic_explanations[component.occurrence_id] = generic

        dependencies = tuple(
            self._clone_component_tree(child, parent=component, mapped=mapping) for child in source.dependencies
        )
        draft.dependency_ids = tuple(child.occurrence_id for child in dependencies)
        configurations = tuple(
            self._clone_component_tree(child, parent=component, mapped=mapping) for child in source.pre_configurations
        )
        draft.pre_configuration_ids = tuple(child.occurrence_id for child in configurations)
        decorators = tuple(
            self._clone_component_tree(child, parent=parent, mapped=mapping)
            for child in (() if self._source_inspection else source.decorators)
        )
        draft.decorator_ids = tuple(child.occurrence_id for child in decorators)
        for source_decorator, decorator in zip(
            () if self._source_inspection else source.decorators, decorators, strict=True
        ):
            decorated = source_decorator.decorated
            if decorated is not None and decorated.occurrence_id in mapping:
                decorator_draft = cast(_ComponentDraft, self.graph.record(decorator.occurrence_id))
                decorator_draft.decorated_id = mapping[decorated.occurrence_id].occurrence_id
        if parameters is not None:
            self.parameter_explanations[component.occurrence_id] = {
                name: replace(
                    record,
                    selected_components=tuple(
                        str(mapping[int(item)].occurrence_id) if item.isdigit() and int(item) in mapping else item
                        for item in record.selected_components
                    ),
                )
                for name, record in parameters.items()
            }
        return component

    def _compile_dependencies(
        self,
        dependencies: dict[str, legacy.Dependency],
        parent: Component,
    ) -> tuple[_CompiledDependency, ...]:
        compiled: list[_CompiledDependency] = []
        child_ids: list[int] = []
        for name, dependency in dependencies.items():
            # Record the requested edge before descent.  If descent fails the incomplete
            # edge is retained solely by the diagnostic snapshot, never by a plan.
            edge_index = self._record_partial_edge(
                (parent.occurrence_id, name, qualified_name(dependency.service_type), None)
            )
            step, child = self._compile_dependency(dependency, parent)
            if edge_index is not None:
                self._partial_edges[edge_index] = (
                    parent.occurrence_id,
                    name,
                    qualified_name(dependency.service_type),
                    None if child is None else child.occurrence_id,
                )
            self._record_parameter_explanation(parent, dependency, child)
            compiled.append(_CompiledDependency(name, step))
            if child is not None:
                child_ids.append(child.occurrence_id)
        record = cast(_ComponentDraft, self.graph.record(parent.occurrence_id))
        record.dependency_ids = tuple(child_ids)
        return tuple(compiled)

    def _record_parameter_explanation(
        self, parent: Component, dependency: legacy.Dependency, child: Component | None
    ) -> None:
        """Store post-compilation facts without inspecting policy closures or values."""
        policy = dependency.settings.value_factory
        if isinstance(policy, _FixedArgument):
            policy_kind = "fixed"
        elif isinstance(policy, _DerivedArgument):
            policy_kind = policy.policy_kind
        elif isinstance(policy, _SelectArgument):
            policy_kind = policy.policy_kind
        elif dependency.default_value is legacy.EMPTY:
            policy_kind = "implicit_injection"
        else:
            policy_kind = "python_default"
        category = "component_edge"
        if child is not None:
            category = {
                ComponentKind.value: "fixed_value",
                ComponentKind.scope_slot: "slot",
                ComponentKind.collection: "collection",
                ComponentKind.provider: "provider",
                ComponentKind.runtime_context: "runtime_context",
            }.get(child.kind, "component_edge")
        record = ParameterExplanation(
            owner=qualified_name(parent.implementation),
            parameter=dependency.name,
            declared_annotation=qualified_name(dependency.declared_service_type),
            canonical_annotation=qualified_name(dependency.service_type),
            has_default=dependency.default_value is not legacy.EMPTY,
            policy_kind=policy_kind,
            evaluation_phase="compilation" if category == "fixed_value" else "runtime",
            result_category=category,
            result_type=qualified_name(dependency.service_type),
            # Occurrence IDs are private compiler evidence until finalization,
            # when they become deterministic semantic graph paths.
            selected_components=() if child is None else (str(child.occurrence_id),),
            provenance=self.origins.get(parent.occurrence_id),
        )
        self.parameter_explanations.setdefault(parent.occurrence_id, {})[dependency.name] = record

    def _record_generic_explanation(self, component: Component, dependencies: Mapping[str, legacy.Dependency]) -> None:
        mapping = tuple(
            sorted(
                ((str(key), qualified_name(value)) for key, value in component.generic_mapping.items()),
                key=lambda item: item[0],
            )
        )
        substitutions = tuple(
            sorted(
                (
                    (name, qualified_name(dependency.declared_service_type), qualified_name(dependency.service_type))
                    for name, dependency in dependencies.items()
                    if dependency.declared_service_type != dependency.service_type
                ),
                key=lambda item: item[0],
            )
        )
        specialized_annotations = self._specialized_dependency_annotations.get(component.id)
        if specialized_annotations is not None:
            substitutions = tuple(
                (name, qualified_name(before), qualified_name(after)) for name, before, after in specialized_annotations
            )
        if not mapping and not substitutions and component.declared_service_type == component.service_type:
            return
        pattern_bindings = self._factory_pattern_bindings.get(component.id, ())
        self.generic_explanations[component.occurrence_id] = GenericBindingExplanation(
            requested_service=qualified_name(component.service_type),
            template_identity=qualified_name(component.declared_service_type),
            selected_tier=(
                "structural_pattern"
                if pattern_bindings
                else "specialized"
                if component.declared_service_type != component.service_type
                else "exact"
            ),
            service_bindings=mapping,
            factory_pattern_bindings=pattern_bindings,
            dependency_annotations=substitutions,
        )

    def _compile_resolution_requests(
        self,
        implementation: Any,
        parent: Component,
    ) -> tuple[_CompiledResolutionRequest, ...]:
        requests = cast(
            tuple[_ResolutionRequest, ...],
            getattr(implementation, _RESOLUTION_REQUESTS_ATTRIBUTE, ()),
        )
        compiled: list[_CompiledResolutionRequest] = []
        for index, request in enumerate(requests):
            request = replace(request, service_type=normalize_type_alias(request.service_type))
            candidates = self._compile_candidates(request.service_type, parent=None, argument=None)
            candidates = self._select_candidates(
                candidates,
                request.filter,
                service_type=request.service_type,
                subject=f"{qualified_name(implementation)} compiled resolution request",
            )
            if not candidates:
                raise ContainerBuildError(
                    f"Factory {qualified_name(implementation)} requests {request.service_type!r}, "
                    "but no compiled root matches",
                    code="missing-component",
                    path=self._current_path(request.service_type),
                )
            if len(candidates) > 1:
                path = self._current_path(request.service_type)
                self.issues.append(
                    BuildIssue(
                        code="ambiguous-selection",
                        severity=IssueSeverity.warning,
                        message=(
                            f"Factory {qualified_name(implementation)} requests {request.service_type!r}, "
                            f"which matches {len(candidates)} components; the first is selected"
                        ),
                        root=path[0] if path else None,
                        path=path,
                    )
                )
            component, step = candidates[0].component, candidates[0].step
            if not request.resolve_async and not step.sync_supported:
                raise ContainerBuildError(
                    f"Synchronous factory {qualified_name(implementation)} cannot resolve async "
                    f"component {request.service_type!r}",
                    code="async-required",
                    path=self._current_path(request.service_type),
                )
            argument = "resolution" if len(requests) == 1 else f"resolution[{index}]"
            compiled.append(
                _CompiledResolutionRequest(
                    request,
                    step,
                    self._clone_component_tree(component, parent=parent, argument=argument),
                )
            )
        return tuple(compiled)

    def _bind_resolution_requests(
        self,
        implementation: Any,
        dependencies: tuple[_CompiledDependency, ...],
        requests: tuple[_CompiledResolutionRequest, ...],
    ) -> tuple[_CompiledDependency, ...]:
        if not requests:
            return dependencies
        found_context = False
        bound: list[_CompiledDependency] = []
        for dependency in dependencies:
            step = dependency.step
            if isinstance(step, _ScopeStep) and step.requested_type is ResolutionContext:
                found_context = True
                step = replace(step, resolution_requests=requests)
            bound.append(_CompiledDependency(dependency.name, step))
        if not found_context:
            raise ContainerBuildError(
                f"Factory {qualified_name(implementation)} declares compiled resolution requests "
                "but does not inject ResolutionContext",
                code="invalid-factory",
                path=self._current_path(implementation),
            )
        return tuple(bound)

    @staticmethod
    def _provider_forbidden_path(component: Component) -> tuple[Component, ...] | None:
        forbidden_contexts = {
            Scope,
            ResolutionContext,
            legacy.Scope,
            legacy.Resolver,
            legacy.ScopeCreator,
            legacy.CurrentGraph,
        }

        def visit(current: Component, path: tuple[Component, ...]) -> tuple[Component, ...] | None:
            current_path = (*path, current)
            if (
                current.lifespan == "scoped"
                or current.kind is ComponentKind.scope_slot
                or (current.kind is ComponentKind.runtime_context and current.service_type in forbidden_contexts)
            ):
                return current_path
            for child in current.dependencies:
                found = visit(child, current_path)
                if found is not None:
                    return found
            for child in current.pre_configurations:
                found = visit(child, current_path)
                if found is not None:
                    return found
            for child in current.decorators:
                found = visit(child, current_path)
                if found is not None:
                    return found
            return None

        return visit(component, ())

    def _validate_provider_target(self, annotation: Any, target: Any | None) -> tuple[type | None, Any]:
        if target is None:
            raise ContainerBuildError(
                f"Provider annotation {annotation!r} requires exactly one target type",
                code="provider-invalid-target",
                path=self._current_path(annotation),
            )
        if _provider_request(target) is not None:
            raise ContainerBuildError(
                f"Nested provider target {target!r} is not supported",
                code="provider-invalid-target",
                path=self._current_path(annotation, target),
            )
        collection = _provider_target_collection(target)
        origin = get_origin(target)
        if (origin in (list, tuple, set) or _collection_request(target) is not None) and collection is None:
            raise ContainerBuildError(
                f"Provider collection target {target!r} must be list[T], tuple[T, ...], or set[T]",
                code="provider-invalid-target",
                path=self._current_path(annotation, target),
            )
        element_type = target if collection is None else collection[1]
        if (
            _provider_request(element_type) is not None
            or _collection_request(element_type) is not None
            or _typevars_in(element_type)
            or bool(getattr(element_type, "__parameters__", ()))
        ):
            raise ContainerBuildError(
                f"Provider target {target!r} must be a closed, non-provider service type",
                code="provider-invalid-target",
                path=self._current_path(annotation, target),
            )
        return (None if collection is None else collection[0]), element_type

    def _compile_provider_dependency(
        self,
        dependency: legacy.Dependency,
        parent: Component,
        mode: typing.Literal["sync", "async"],
        target: Any | None,
    ) -> tuple[_Step, Component]:
        collection_type, element_type = self._validate_provider_target(dependency.service_type, target)
        capturing_singleton = next(
            (frame for frame in reversed(self._retention_frames()) if frame.lifespan == legacy.Lifespan.singleton),
            None,
        )
        owner_token = (
            capturing_singleton.owner_token
            if capturing_singleton is not None
            else (self._frames[-1].owner_token if self._frames else self.blueprint.layers[0].owner_token)
        )
        provider, provider_draft = self._draft(
            component_id=f"provider:{parent.occurrence_id}:{dependency.name}",
            service_type=dependency.service_type,
            implementation=Provider if mode == "sync" else AsyncProvider,
            lifespan="transient",
            name=None,
            tags=(),
            kind=ComponentKind.provider,
            activation=ComponentActivation.deferred,
            parent=parent,
            argument=dependency.name,
            provider_mode=mode,
            origin=self.origins.get(parent.occurrence_id),
        )
        self._frames.append(
            _CompilerFrame(
                label=dependency.service_type,
                lifespan=legacy.Lifespan.transient,
                owner_token=owner_token,
                kind=ComponentKind.provider,
                component=provider,
            )
        )
        try:
            if collection_type is not None:
                collection, collection_draft = self._draft(
                    component_id=f"provider-collection:{provider.occurrence_id}",
                    service_type=target,
                    implementation=collection_type,
                    lifespan="transient",
                    name=None,
                    tags=(),
                    kind=ComponentKind.collection,
                    activation=ComponentActivation.collection,
                    parent=provider,
                    origin=self.origins.get(parent.occurrence_id),
                )
                candidates = self._compile_candidates(element_type, collection, dependency.name)
                candidates = self._select_candidates(
                    candidates,
                    dependency.settings.filter,
                    service_type=element_type,
                    subject=(
                        f"Deferred collection argument {dependency.name!r} of "
                        f"{qualified_name(parent.implementation)}"
                    ),
                    collection=True,
                    explanation_component=collection,
                )
                collection_draft.dependency_ids = tuple(candidate.component.occurrence_id for candidate in candidates)
                member_steps = tuple(candidate.step for candidate in candidates)
                target_step: _Step = _CollectionStep(
                    collection_type,
                    member_steps,
                    all(step.sync_supported for step in member_steps),
                )
                target_component = collection
                explanation = self.occurrence_explanations.get(collection.occurrence_id)
                if explanation is not None:
                    self.occurrence_explanations[provider.occurrence_id] = explanation
            else:
                candidates = self._compile_candidates(element_type, provider, dependency.name)
                candidates = self._select_candidates(
                    candidates,
                    dependency.settings.filter,
                    service_type=element_type,
                    subject=(f"Deferred argument {dependency.name!r} of " f"{qualified_name(parent.implementation)}"),
                    explanation_component=provider,
                )
                if not candidates:
                    slot = self._matching_slot(
                        element_type,
                        dependency.settings.filter,
                        provider,
                        dependency.name,
                    )
                    if slot is None:
                        raise ContainerBuildError(
                            f"No component satisfies deferred target {element_type!r}",
                            code="provider-missing-component",
                            path=self._current_path(element_type),
                        )
                    name, target_component = slot
                    target_step = _ProvidedStep(element_type, name)
                else:
                    if len(candidates) > 1:
                        raise ContainerBuildError(
                            f"Deferred target {element_type!r} matches {len(candidates)} components",
                            code="provider-ambiguous-component",
                            path=self._current_path(element_type),
                        )
                    target_component = candidates[0].component
                    target_step = candidates[0].step

            provider_draft.dependency_ids = (target_component.occurrence_id,)
            if mode == "sync" and not target_step.sync_supported:
                raise ContainerBuildError(
                    f"Synchronous Provider target {target!r} requires asynchronous resolution; "
                    f"use AsyncProvider[{qualified_name(target)}]",
                    code="provider-requires-async",
                    path=self._current_path(target),
                )
            if capturing_singleton is not None:
                forbidden = self._provider_forbidden_path(target_component)
                if forbidden is not None:
                    forbidden_target = forbidden[-1]
                    raise ContainerBuildError(
                        f"{_frame_description(capturing_singleton)} cannot retain a provider whose target "
                        f"reaches scoped state {qualified_name(forbidden_target.service_type)}",
                        code="provider-captive-scope",
                        path=self._current_path(
                            *(component.service_type for component in forbidden),
                        ),
                    )
            return (
                _ProviderStep(
                    mode,
                    target_step,
                    None if capturing_singleton is None else capturing_singleton.owner_token,
                ),
                provider,
            )
        finally:
            self._frames.pop()

    def _compile_dependency(
        self,
        dependency: legacy.Dependency,
        parent: Component,
    ) -> tuple[_Step, Component | None]:
        declared_type = dependency.declared_service_type
        dependency.service_type = normalize_type_alias(dependency.service_type)
        dependency.generic_collection_type = dependency.GENERIC_COLLECTION_MAPPINGS.get(
            get_origin(dependency.service_type)
        )
        policy = dependency.settings.value_factory
        provider = _provider_request(dependency.service_type)
        if provider is not None:
            valid_policy = isinstance(policy, _SelectArgument) or (
                policy is default_parameter_value_factory and dependency.default_value is legacy.EMPTY
            )
            if not valid_policy:
                raise ContainerBuildError(
                    f"Argument {dependency.name!r} of {qualified_name(parent.implementation)} applies a "
                    "value-producing policy to a typed provider",
                    code="provider-invalid-argument-policy",
                    path=self._current_path(dependency.service_type),
                )
            return self._dependency_alias_result(
                self._compile_provider_dependency(dependency, parent, *provider),
                declared_type,
                dependency.service_type,
            )
        policy_code = "argument-default"
        if isinstance(policy, _FixedArgument):
            value = policy.value
            policy_code = "argument-fixed"
        elif isinstance(policy, _DerivedArgument):
            policy_code = "argument-derived"
            has_default = dependency.default_value is not legacy.EMPTY
            context = ParameterContext(
                name=dependency.name,
                annotation=dependency.service_type,
                component=parent,
                default=dependency.default_value if has_default else None,
                has_default=has_default,
            )
            try:
                value = policy.function(context)
            except Exception as error:
                detail = type(error).__name__
                if policy.policy_kind == "generic_argument" and policy.generic_key is not None:
                    binding = policy.generic_key if isinstance(policy.generic_key, str) else policy.generic_key.__name__
                    detail = f"generic binding {binding} unavailable ({detail})"
                raise ContainerBuildError(
                    f"Could not derive argument {dependency.name!r} for "
                    f"{qualified_name(parent.implementation)}: {detail}",
                    code="invalid-derived-argument",
                    path=self._current_path(dependency.service_type),
                ) from error
        elif isinstance(policy, _SelectArgument):
            value = INJECT
            policy_code = "argument-select"
        elif policy is default_parameter_value_factory:
            value = dependency.default_value
        else:
            raise ContainerBuildError(
                f"Unsupported argument policy for {dependency.name!r} of {qualified_name(parent.implementation)}",
                code="invalid-argument",
                path=self._current_path(dependency.service_type),
            )

        if value is not legacy.EMPTY and value is not INJECT:
            component, _ = self._draft(
                component_id=f"value:{parent.occurrence_id}:{dependency.name}",
                service_type=dependency.service_type,
                implementation=type(value),
                lifespan="transient",
                name=None,
                tags=(),
                kind=ComponentKind.value,
                activation=ComponentActivation.supplied,
                parent=parent,
                argument=dependency.name,
                origin=self.origins.get(parent.occurrence_id),
            )
            self._record_component_decision(
                component,
                subject=f"Argument {dependency.name!r} of {qualified_name(parent.implementation)}",
                code=policy_code,
                reason="The argument policy compiled a fixed value; its value is redacted",
                origin=self.origins.get(parent.occurrence_id),
            )
            return self._dependency_alias_result(
                (_ValueStep(value), component),
                declared_type,
                dependency.service_type,
            )

        if (
            not isinstance(parent.implementation, type)
            and constructor_type(parent.implementation) is not None
            and (unresolved := _typevars_in(dependency.service_type))
        ):
            names = ", ".join(variable.__name__ for variable in unresolved)
            raise ContainerBuildError(
                f"Unable to resolve constructor TypeVar(s) {names} in {dependency.service_type!r} "
                f"for argument {dependency.name!r} of {qualified_name(parent.implementation)}",
                code="invalid-generic-specialization",
                path=self._current_path(dependency.service_type),
            )

        if dependency.service_type in (
            Scope,
            Container,
            ResolutionContext,
            legacy.Scope,
            legacy.Resolver,
            legacy.ScopeCreator,
            legacy.CurrentGraph,
        ):
            effective_lifespan = self._validate_runtime_context_dependency(dependency.service_type, parent)
            component, _ = self._draft(
                component_id=f"context:{parent.occurrence_id}:{dependency.name}",
                service_type=dependency.service_type,
                implementation=dependency.service_type,
                lifespan=effective_lifespan,
                name=None,
                tags=(),
                kind=ComponentKind.runtime_context,
                activation=ComponentActivation.context,
                parent=parent,
                argument=dependency.name,
                origin=self.origins.get(parent.occurrence_id),
            )
            self._record_component_decision(
                component,
                subject=f"Argument {dependency.name!r} of {qualified_name(parent.implementation)}",
                code="runtime-context",
                reason="The annotation selects a frozen runtime context edge",
            )
            return self._dependency_alias_result(
                (_ScopeStep(dependency.service_type), component),
                declared_type,
                dependency.service_type,
            )

        if dependency.generic_collection_type:
            element_type = get_args(dependency.service_type)[0]
            collection, collection_draft = self._draft(
                component_id=f"collection:{parent.occurrence_id}:{dependency.name}",
                service_type=dependency.service_type,
                implementation=dependency.generic_collection_type,
                lifespan="transient",
                name=None,
                tags=(),
                kind=ComponentKind.collection,
                activation=ComponentActivation.collection,
                parent=parent,
                argument=dependency.name,
                origin=self.origins.get(parent.occurrence_id),
            )
            candidates = self._compile_candidates(element_type, collection, dependency.name)
            candidates = self._select_candidates(
                candidates,
                dependency.settings.filter,
                service_type=element_type,
                subject=f"Collection argument {dependency.name!r} of {qualified_name(parent.implementation)}",
                collection=True,
                explanation_component=collection,
            )
            collection_draft.dependency_ids = tuple(candidate.component.occurrence_id for candidate in candidates)
            member_steps = tuple(candidate.step for candidate in candidates)
            return self._dependency_alias_result(
                (
                    _CollectionStep(
                        dependency.generic_collection_type,
                        member_steps,
                        all(step.sync_supported for step in member_steps),
                    ),
                    collection,
                ),
                declared_type,
                dependency.service_type,
            )

        candidates = self._compile_candidates(dependency.service_type, parent, dependency.name)
        candidates = self._select_candidates(
            candidates,
            dependency.settings.filter,
            service_type=dependency.service_type,
            subject=f"Argument {dependency.name!r} of {qualified_name(parent.implementation)}",
        )
        if candidates:
            if len(candidates) > 1:
                path = self._current_path(dependency.service_type)
                self.issues.append(
                    BuildIssue(
                        code="ambiguous-selection",
                        severity=IssueSeverity.warning,
                        message=(
                            f"Argument {dependency.name!r} matches {len(candidates)} components; "
                            "the first is selected"
                        ),
                        root=path[0] if path else None,
                        path=path,
                    )
                )
            return self._dependency_alias_result(
                (candidates[0].step, candidates[0].component),
                declared_type,
                dependency.service_type,
            )

        slot = self._matching_slot(dependency.service_type, dependency.settings.filter, parent, dependency.name)
        if slot is not None:
            name, component = slot
            return self._dependency_alias_result(
                (_ProvidedStep(dependency.service_type, name), component),
                declared_type,
                dependency.service_type,
            )
        visibility_error = self._visibility_error(dependency.service_type)
        if visibility_error is not None:
            raise visibility_error
        raise ContainerBuildError(
            f"No component for {qualified_name(dependency.service_type)}, argument {dependency.name!r} of "
            f"{qualified_name(parent.implementation)}"
            + (f" (declared as {qualified_name(declared_type)})" if declared_type != dependency.service_type else ""),
            code="missing-component",
            path=self._current_path(dependency.service_type),
        )

    def _matching_slot(
        self,
        service_type: Any,
        filter: ComponentFilter,
        parent: Component,
        argument: str,
    ) -> tuple[str | None, Component] | None:
        for slot_type, name, origin in self.blueprint.slot_definitions(service_type, self._area):
            component, _ = self._draft(
                component_id=f"slot:{slot_type!r}:{name}",
                service_type=slot_type,
                implementation=_ProvidedStep,
                lifespan="scoped",
                name=name,
                tags=(),
                kind=ComponentKind.scope_slot,
                activation=ComponentActivation.supplied,
                parent=parent,
                argument=argument,
                origin=origin,
            )
            if filter(component):
                singleton = next(
                    (item for item in reversed(self._retention_frames()) if item.lifespan == legacy.Lifespan.singleton),
                    None,
                )
                if singleton is not None:
                    raise ContainerBuildError(
                        f"{_frame_description(singleton)} cannot retain scoped value from scope slot "
                        f"{qualified_name(slot_type)}",
                        code="captive-runtime-scope",
                        path=self._current_path(slot_type),
                    )
                self._record_component_decision(
                    component,
                    subject=f"Scope slot for argument {argument!r}",
                    code="selected-explicit-filter",
                    reason=f"The declared scope slot matched {_filter_description(filter)}",
                    origin=origin,
                )
                return name, component
        return None

    def _compile_pre_configurations(
        self,
        parent: Component,
    ) -> tuple[_CompiledPreConfiguration, ...]:
        items: list[_CompiledPreConfiguration] = []
        decisions: list[CandidateDecision] = []
        definitions = self.blueprint.pre_configurations(parent.service_type, self._area)
        applicability: list[tuple[_PreConfigurationDefinition, _Layer, bool]] = []
        for definition_index, (definition, layer) in enumerate(definitions):
            try:
                matched = definition.when(parent)
            except Exception as error:
                subject = f"Pre-configurations for {qualified_name(parent.service_type)}"
                self._partial_candidate_labels[definition.id] = qualified_name(definition.configuration_fn)
                self._record_partial_candidate(
                    (subject, definition.id, PartialState.failed, "pre-configuration-filter-failed")
                )
                for pending, _ in definitions[definition_index + 1 :]:
                    self._partial_candidate_labels[pending.id] = qualified_name(pending.configuration_fn)
                    self._record_partial_candidate((subject, pending.id, PartialState.not_examined, None))
                decisions.append(
                    CandidateDecision(
                        definition.id,
                        DecisionOutcome.rejected,
                        ("pre-configuration-filter-rejected",),
                        (
                            f"Pre-configuration filter {_filter_description(definition.when)} "
                            f"raised {type(error).__name__}"
                        ),
                        definition.origin,
                    )
                )
                self.decision_history.append(
                    CompilationExplanation(
                        subject=f"Pre-configurations for {qualified_name(parent.service_type)}",
                        path=self._current_path(parent.service_type),
                        selected=tuple(
                            decision for decision in decisions if decision.outcome is DecisionOutcome.selected
                        ),
                        rejected=tuple(
                            decision for decision in decisions if decision.outcome is DecisionOutcome.rejected
                        ),
                    )
                )
                raise
            applicability.append((definition, layer, matched))
            decisions.append(
                CandidateDecision(
                    definition.id,
                    DecisionOutcome.selected if matched else DecisionOutcome.rejected,
                    ("pre-configuration-filter-matched" if matched else "pre-configuration-filter-rejected",),
                    (
                        f"Pre-configuration filter {_filter_description(definition.when)} returned "
                        f"{'true' if matched else 'false'}"
                    ),
                    definition.origin,
                )
            )
        for definition, layer, matched in applicability:
            if not matched:
                continue
            self._record_partial_declaration_edge(
                (
                    parent.occurrence_id,
                    "pre-configuration",
                    qualified_name(definition.configuration_fn),
                    "pre-configuration-pending",
                    False,
                )
            )
            existing = self._compiled_pre_configurations.get(definition.id)
            if existing is not None:
                items.append(existing)
                self._partial_declaration_edges = [
                    edge
                    for edge in self._partial_declaration_edges
                    if not (
                        edge[0] == parent.occurrence_id
                        and edge[1] == "pre-configuration"
                        and edge[2] == qualified_name(definition.configuration_fn)
                        and edge[3] == "pre-configuration-pending"
                    )
                ]
                continue
            if layer.owner_token in self._anchored_owner_tokens:
                anchored = self._anchored_pre_configurations.get(definition.id)
                if anchored is None:
                    raise ContainerBuildError(
                        f"Parent-owned pre-configuration {qualified_name(definition.configuration_fn)} "
                        "has no frozen parent plan; declare it in the scope builder",
                        code="overlay-pre-configuration",
                        path=self._current_path(definition.configuration_fn),
                    )
                compiled = replace(
                    anchored,
                    component=self._clone_component_tree(anchored.component, parent=None),
                )
                self.origins[compiled.component.occurrence_id] = definition.origin
                self._compiled_pre_configurations[definition.id] = compiled
                items.append(compiled)
                continue
            if definition.id in self._compiling_pre_configurations:
                self._record_partial_declaration_edge(
                    (
                        parent.occurrence_id,
                        "pre-configuration",
                        qualified_name(definition.configuration_fn),
                        "circular-dependency",
                        True,
                    )
                )
                raise ContainerBuildError(
                    f"Circular pre-configuration trigger for {qualified_name(definition.configuration_fn)}",
                    code="circular-dependency",
                    path=self._current_path(definition.configuration_fn),
                )
            try:
                dependencies = legacy._set_up_dependencies(
                    definition.configuration_fn,
                    cast(Any, _arguments_to_dependency_config(definition.arguments)),
                )
                _validate_dependency_names(definition.configuration_fn, dependencies)
            except Exception as error:
                raise ContainerBuildError(
                    f"Pre-configuration {qualified_name(definition.configuration_fn)} has an invalid signature: "
                    f"{error}",
                    code="invalid-pre-configuration",
                    path=self._current_path(definition.configuration_fn),
                ) from error
            activator_class = legacy._Registry._get_activator_class(definition.configuration_fn)
            component, _ = self._draft(
                component_id=definition.id,
                service_type=definition.service_types[0],
                implementation=definition.configuration_fn,
                lifespan="singleton",
                name=None,
                tags=(),
                kind=ComponentKind.pre_configuration,
                activation=_callable_activation(definition.configuration_fn),
                parent=None,
                requires_async=_requires_async(activator_class, definition.configuration_fn),
                manages_cleanup=_manages_cleanup(activator_class, definition.configuration_fn),
                origin=definition.origin,
            )
            self._compiling_pre_configurations.add(definition.id)
            self._frames.append(
                _CompilerFrame(
                    label=definition.configuration_fn,
                    lifespan=legacy.Lifespan.singleton,
                    owner_token=layer.owner_token,
                    kind=ComponentKind.pre_configuration,
                    component=component,
                )
            )
            try:
                compiled_dependencies = self._compile_dependencies(dependencies, component)
                self._record_generic_explanation(component, dependencies)
            finally:
                self._frames.pop()
                self._compiling_pre_configurations.remove(definition.id)
            state = layer.pre_configuration_states.setdefault(definition.id, _PreConfigurationState())
            compiled = _CompiledPreConfiguration(
                definition=definition,
                activator_class=activator_class,
                dependencies=compiled_dependencies,
                component=component,
                state=state,
                owner_token=layer.owner_token,
                cleanup_owner=self._cleanup_descriptor(
                    component,
                    declaring_owner_token=layer.owner_token,
                ),
                sync_supported=(
                    not _requires_async(activator_class, definition.configuration_fn)
                    and all(dependency.step.sync_supported for dependency in compiled_dependencies)
                ),
            )
            self._compiled_pre_configurations[definition.id] = compiled
            items.append(compiled)
            self._partial_declaration_edges = [
                edge
                for edge in self._partial_declaration_edges
                if not (
                    edge[0] == parent.occurrence_id
                    and edge[1] == "pre-configuration"
                    and edge[2] == qualified_name(definition.configuration_fn)
                    and edge[3] == "pre-configuration-pending"
                )
            ]
        explanation = CompilationExplanation(
            subject=f"Pre-configurations for {qualified_name(parent.service_type)}",
            path=self._current_path(parent.service_type),
            selected=tuple(decision for decision in decisions if decision.outcome is DecisionOutcome.selected),
            rejected=tuple(decision for decision in decisions if decision.outcome is DecisionOutcome.rejected),
        )
        if decisions:
            self.decision_history.append(explanation)
        for item in items:
            self.occurrence_explanations[item.component.occurrence_id] = explanation
        return tuple(items)

    def _compile_decorators(
        self,
        registration: legacy._Registration,
        layer: _Layer,
        core: Component,
    ) -> tuple[_CompiledDecorator, ...]:
        if self._source_inspection:
            return ()
        # Applicability is deliberately evaluated against the completed,
        # undecorated core subtree before any decorator dependencies are added.
        selected: list[_DecoratorDefinition] = []
        decisions: list[CandidateDecision] = []
        definitions = self.blueprint.decorators(core.service_type, self._area)
        generated: dict[str, tuple[_GeneratedDecoratorDefinition, _ServiceTarget]] = {}
        area_layers = self.blueprint.layers if self._area is None else (layer,)
        for candidate in self.blueprint.generated_decorators:
            if candidate.declaration_area != self._area:
                continue
            target = self._select_service_target(
                candidate.specification.services, registration, layer, core.service_type
            )
            if target is None:
                continue
            declaration_layer = next(
                (item for item in area_layers if item.owner_token == candidate.declaration_owner_token), None
            )
            if declaration_layer is None:
                continue
            specification = candidate.specification
            definition = _DecoratorDefinition(
                candidate.id,
                target.projected_contract,
                specification.decorator_type,
                specification.decorated_arg,
                specification.arguments or {},
                specification.position,
                candidate.order,
                specification.when,
                specification.name,
                tuple(specification.tags),
                candidate.declaration.origin,
            )
            definitions.append((definition, declaration_layer))
            generated[candidate.id] = candidate, target
        definitions.sort(
            key=lambda item: (
                item[0].position,
                next(index for index, value in enumerate(area_layers) if value is item[1]),
                -item[0].order,
                -generated[item[0].id][0].source_order if item[0].id in generated else 0,
            )
        )
        target_view = _undecorated_component_view(core) if generated else None
        for decorator_index, (decorator, _) in enumerate(definitions):
            try:
                matched = decorator.when(cast(Component, target_view) if decorator.id in generated else core)
            except Exception as error:
                subject = f"Decorators for {qualified_name(core.service_type)}"
                self._partial_candidate_labels[decorator.id] = qualified_name(decorator.decorator_type)
                self._record_partial_candidate((subject, decorator.id, PartialState.failed, "decorator-filter-failed"))
                for pending, _ in definitions[decorator_index + 1 :]:
                    self._partial_candidate_labels[pending.id] = qualified_name(pending.decorator_type)
                    self._record_partial_candidate((subject, pending.id, PartialState.not_examined, None))
                decisions.append(
                    CandidateDecision(
                        decorator.id,
                        DecisionOutcome.rejected,
                        ("decorator-filter-rejected",),
                        f"Decorator filter {_filter_description(decorator.when)} raised {type(error).__name__}",
                        decorator.origin,
                    )
                )
                self.decision_history.append(
                    CompilationExplanation(
                        subject=f"Decorators for {qualified_name(core.service_type)}",
                        path=self._current_path(core.service_type),
                        selected=tuple(
                            decision for decision in decisions if decision.outcome is DecisionOutcome.selected
                        ),
                        rejected=tuple(
                            decision for decision in decisions if decision.outcome is DecisionOutcome.rejected
                        ),
                    )
                )
                raise
            decisions.append(
                CandidateDecision(
                    decorator.id,
                    DecisionOutcome.selected if matched else DecisionOutcome.rejected,
                    ("decorator-filter-matched" if matched else "decorator-filter-rejected",),
                    (
                        f"Decorator filter {_filter_description(decorator.when)} returned "
                        f"{'true' if matched else 'false'}"
                    ),
                    decorator.origin,
                )
            )
            if matched:
                selected.append(decorator)

        items: list[_CompiledDecorator] = []
        decorated: Component = core
        for definition in selected:
            try:
                decorator = (
                    _materialize_generated_decorator(definition)
                    if definition.id in generated
                    else _materialize_decorator(definition, core.service_type, core.implementation_type)
                )
            except ContainerBuildError as error:
                self._record_partial_declaration_edge(
                    (
                        core.occurrence_id,
                        "decorator",
                        qualified_name(definition.decorator_type),
                        "invalid-decorator",
                        False,
                    )
                )
                raise ContainerBuildError(
                    str(error),
                    code="invalid-decorator",
                    path=(
                        *self._current_path(core.service_type),
                        *(
                            (generated[definition.id][0].declaration.id, generated[definition.id][0].source.id)
                            if definition.id in generated
                            else ()
                        ),
                    ),
                ) from error
            component, draft = self._draft(
                component_id=definition.id,
                service_type=core.service_type,
                implementation=decorator.implementation,
                lifespan=_component_lifespan(registration.lifespan),
                name=definition.name,
                tags=definition.tags,
                kind=ComponentKind.decorator,
                activation=_callable_activation(decorator.implementation),
                parent=core.parent,
                requires_async=_requires_async(decorator.activator_class, decorator.implementation),
                manages_cleanup=_manages_cleanup(decorator.activator_class, decorator.implementation),
                position=definition.position,
                origin=definition.origin,
            )
            draft.decorated_id = decorated.occurrence_id
            if draft.cleanup_owner is RuntimeOwnerKind.none and decorated.cleanup_owner is not RuntimeOwnerKind.none:
                draft.cleanup_owner = decorated.cleanup_owner
                draft.owner_id = decorated.owner_occurrence_id
                draft.ownership_reason = "The decorator inherits the effective cleanup owner of the decorated pipeline"
            owner_token = self._frames[-1].owner_token
            self._frames.append(
                _CompilerFrame(
                    label=decorator.implementation,
                    lifespan=registration.lifespan,
                    owner_token=owner_token,
                    kind=ComponentKind.decorator,
                    component=component,
                )
            )
            try:
                dependencies = self._compile_dependencies(decorator.dependencies, component)
                self._record_generic_explanation(component, decorator.dependencies)
            except ContainerBuildError as error:
                if definition.id not in generated:
                    raise
                candidate, target = generated[definition.id]
                raise ContainerBuildError(
                    f"Template {candidate.declaration.id} source {candidate.source.id}: {error}",
                    code=error.code,
                    path=(*error.path, candidate.declaration.id, candidate.source.id, target.registration_id),
                ) from error
            finally:
                self._frames.pop()
            items.append(
                _CompiledDecorator(
                    decorator,
                    dependencies,
                    component,
                    self._cleanup_descriptor(
                        component,
                        declaring_owner_token=owner_token,
                    ),
                    not _requires_async(decorator.activator_class, decorator.implementation)
                    and all(dependency.step.sync_supported for dependency in dependencies),
                )
            )
            decorated = component
        explanation = CompilationExplanation(
            subject=f"Decorators for {qualified_name(core.service_type)}",
            path=self._current_path(core.service_type),
            selected=tuple(decision for decision in decisions if decision.outcome is DecisionOutcome.selected),
            rejected=tuple(decision for decision in decisions if decision.outcome is DecisionOutcome.rejected),
        )
        if decisions:
            self.decision_history.append(explanation)
        for item in items:
            self.occurrence_explanations[item.component.occurrence_id] = explanation
        return tuple(items)


@dataclass(frozen=True, slots=True)
class _Outcome:
    error: BaseException | None = None


class _Coordinator:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._in_flight: dict[str, concurrent.futures.Future[_Outcome]] = {}

    def begin(self, key: str) -> tuple[concurrent.futures.Future[_Outcome], bool]:
        with self._lock:
            if key in self._in_flight:
                return self._in_flight[key], False
            future: concurrent.futures.Future[_Outcome] = concurrent.futures.Future()
            self._in_flight[key] = future
            return future, True

    def finish(
        self,
        key: str,
        future: concurrent.futures.Future[_Outcome],
        error: BaseException | None = None,
    ) -> None:
        with self._lock:
            if self._in_flight.get(key) is future:
                del self._in_flight[key]
        future.set_result(_Outcome(error))


class _RuntimeOwner:
    def __init__(self) -> None:
        self._singletons: dict[str, Any] = {}
        self._coordinator = _Coordinator()
        self._finalizers: deque[Callable[..., Any]] = deque()
        self._closed = False
        self._close_lock = threading.Lock()

    def _ensure_owner_open(self) -> None:
        if self._closed:
            raise ScopeClosedError("The runtime ownership boundary is closed")

    def _add_finalizer(self, finalizer: Callable[..., Any]) -> None:
        with self._close_lock:
            self._ensure_owner_open()
            self._finalizers.appendleft(finalizer)

    @staticmethod
    def _raise_cleanup_failures(failures: list[BaseException]) -> None:
        if not failures:
            return
        if len(failures) == 1:
            raise failures[0]
        if all(isinstance(error, Exception) for error in failures):
            raise ExceptionGroup("Multiple resource finalizers failed", cast(list[Exception], failures))
        raise BaseExceptionGroup("Multiple resource finalizers failed", failures)

    def _begin_close(self) -> tuple[Callable[..., Any], ...]:
        with self._close_lock:
            if self._closed:
                return ()
            self._closed = True
            finalizers = tuple(self._finalizers)
            self._finalizers.clear()
            return finalizers

    def _close(self) -> None:
        failures: list[BaseException] = []
        for finalizer in self._begin_close():
            try:
                result = finalizer()
                if inspect.isawaitable(result):
                    close = getattr(result, "close", None)
                    if callable(close):
                        close()
                    raise RuntimeError("Async finalizer requires async context management")
            except BaseException as error:
                failures.append(error)
        self._raise_cleanup_failures(failures)

    async def _close_async(self) -> None:
        failures: list[BaseException] = []
        for finalizer in self._begin_close():
            try:
                result = finalizer()
                if inspect.isawaitable(result):
                    await result
            except BaseException as error:
                failures.append(error)
        self._raise_cleanup_failures(failures)


def _collection_request(service_type: Any) -> tuple[type, Any] | None:
    if isinstance(service_type, type):
        return None
    origin = get_origin(service_type)
    collection_type = legacy.Dependency.GENERIC_COLLECTION_MAPPINGS.get(origin)
    arguments = get_args(service_type)
    if collection_type is None or not arguments:
        return None
    return collection_type, arguments[0]


def _provider_selection_component(component: Component) -> Component:
    """Expose the frozen target to filters, not the synthetic provider handle."""

    if component.kind is not ComponentKind.provider or not component.dependencies:
        return component
    target = component.dependencies[0]
    return target if target.kind is not ComponentKind.collection else component


def _iter_registration_steps(step: _Step) -> Iterable[_RegistrationStep]:
    if isinstance(step, _RegistrationStep):
        yield step
        for dependency in step.dependencies:
            yield from _iter_registration_steps(dependency.step)
        for configuration in step.pre_configurations:
            for dependency in configuration.dependencies:
                yield from _iter_registration_steps(dependency.step)
        for decorator in step.decorators:
            for dependency in decorator.dependencies:
                yield from _iter_registration_steps(dependency.step)
        return
    if isinstance(step, _CollectionStep):
        for member in step.members:
            yield from _iter_registration_steps(member)
        return
    if isinstance(step, _ProviderStep):
        yield from _iter_registration_steps(step.target)


def _anchored_singletons(
    plan: _PlanSet,
) -> dict[tuple[str, tuple[Any, ...]], _RegistrationStep]:
    anchored: dict[tuple[str, tuple[Any, ...]], _RegistrationStep] = {}
    all_plans = tuple(root for _, _, root in plan.architecture_roots) or tuple(
        root for plans in plan.roots.values() for root in plans
    )
    for root in all_plans:
        for step in _iter_registration_steps(root.step):
            if step.registration.lifespan == legacy.Lifespan.singleton:
                anchored.setdefault(
                    (step.registration.id, _runtime_type_key(step.source_service_type)),
                    step,
                )
    return anchored


def _anchored_pre_configurations(plan: _PlanSet) -> dict[str, _CompiledPreConfiguration]:
    anchored: dict[str, _CompiledPreConfiguration] = {}
    all_plans = tuple(root for _, _, root in plan.architecture_roots) or tuple(
        root for plans in plan.roots.values() for root in plans
    )
    for root in all_plans:
        for step in _iter_registration_steps(root.step):
            for configuration in step.pre_configurations:
                anchored.setdefault(configuration.definition.id, configuration)
    return anchored


def _graph_roots(plan: _PlanSet) -> tuple[GraphRoot, ...]:
    if plan.architecture_roots:
        return tuple(
            GraphRoot(service_type, root.component, area) for area, service_type, root in plan.architecture_roots
        )
    return tuple(
        GraphRoot(service_type, root.component) for service_type, roots in plan.roots.items() for root in roots
    )


def _component_tree(component: Component) -> Iterable[Component]:
    yield component
    for child in component.dependencies:
        yield from _component_tree(child)
    for configuration in component.pre_configurations:
        yield from _component_tree(configuration)
    for decorator in component.decorators:
        yield from _component_tree(decorator)


def _valid_build_issue(issue: Any) -> bool:
    return (
        isinstance(issue, BuildIssue)
        and isinstance(issue.code, str)
        and bool(issue.code.strip())
        and isinstance(issue.severity, IssueSeverity)
        and isinstance(issue.message, str)
        and bool(issue.message.strip())
        and (issue.root is None or (isinstance(issue.root, str) and bool(issue.root.strip())))
        and isinstance(issue.path, tuple)
        and all(isinstance(item, str) and bool(item.strip()) for item in issue.path)
    )


def _validation_rule_issues(rule: ValidationRule, context: ValidationContext) -> Iterable[BuildIssue]:
    try:
        result = rule(context)
        if inspect.iscoroutine(result):
            result.close()
            raise TypeError("returned an awaitable; validation rules must be synchronous")
        iterator = iter(result)
        while True:
            try:
                issue = next(iterator)
            except StopIteration:
                break
            if not _valid_build_issue(issue):
                raise TypeError("yielded a malformed BuildIssue")
            yield issue
    except Exception as error:
        yield BuildIssue(
            code="validation-rule-error",
            severity=IssueSeverity.error,
            message=(f"Validation rule {qualified_name(rule)} failed: " f"{type(error).__name__}: {error}"),
        )


def _run_validation_rules(
    graph: CompiledGraph,
    definitions: Iterable[_ValidationRuleDefinition],
) -> tuple[BuildIssue, ...]:
    selected = tuple(definitions)
    if not selected:
        return ()
    issues: list[BuildIssue] = []
    contexts: dict[str | None, ValidationContext] = {}
    for definition in selected:
        boundary = definition.origin.boundary
        context = contexts.get(boundary)
        if context is None:
            visible_graph = graph
            if boundary is not None:
                local_roots = tuple(root for root in graph.roots if root.area == boundary)
                local_entrypoints = tuple(root for root in graph.entrypoints if root.area == boundary)
                visible_graph = replace(
                    graph,
                    roots=local_roots,
                    entrypoints=local_entrypoints,
                    _manifest_cache={},
                    _ownership_report_cache=[],
                    _analysis_index_cache=None,
                )
            context = ValidationContext(visible_graph, boundary=boundary)
            contexts[boundary] = context
        issues.extend(_validation_rule_issues(definition.rule, context))
    return tuple(issues)


def _build_error_code(error: BaseException) -> str:
    if isinstance(error, ContainerBuildError) and error.code is not None:
        return error.code
    # Exceptions from user filters, derivations, and factories may implement a
    # hostile __str__/__repr__.  Error classification must never execute it.
    return "compile-error"


def _safe_error_message(error: BaseException) -> str:
    """Return a stable message without inspecting arbitrary exception text."""
    if isinstance(error, ContainerBuildError) and error.args and isinstance(error.args[0], str):
        return error.args[0]
    return f"Compilation failed [{_build_error_code(error)}]."


def _error_report(
    blueprint: _Blueprint,
    original: BaseException,
    *,
    build_args: Mapping[str, Any] = _EMPTY_BUILD_ARGS,
    anchored_singleton_steps: dict[tuple[str, tuple[Any, ...]], _RegistrationStep] | None = None,
    anchored_pre_configuration_steps: dict[str, _CompiledPreConfiguration] | None = None,
    anchored_owner_tokens: frozenset[str] = frozenset(),
) -> tuple[BuildReport, tuple[CompilationAttempt, ...], tuple[int, int]]:
    issues: list[BuildIssue] = []
    attempts: list[CompilationAttempt] = []
    seen: set[tuple[str, str, tuple[str, ...]]] = set()
    checked = 0
    attempt_limit = 100
    total_attempts = 0
    areas = (
        (None, blueprint.root_service_types()),
        *((boundary.name, blueprint.service_types(boundary.name)) for boundary in blueprint.boundaries),
    )
    for area, service_types in areas:
        for service_type in service_types:
            if getattr(service_type, "__parameters__", ()):
                continue
            checked += 1
            total_attempts += 1
            compiler = _Compiler(
                blueprint,
                build_args=build_args,
                anchored_singletons=anchored_singleton_steps,
                anchored_pre_configurations=anchored_pre_configuration_steps,
                anchored_owner_tokens=anchored_owner_tokens,
            )
            try:
                compiler.compile((service_type,), area=area, include_boundaries=False)
                if len(attempts) < attempt_limit:
                    attempts.append(compiler.partial_success_attempt(root=qualified_name(service_type)))
            except Exception as error:
                root = qualified_name(service_type)
                if len(attempts) < attempt_limit:
                    attempts.append(compiler.partial_attempt(error, root=root))
                code = _build_error_code(error)
                path = error.path if isinstance(error, ContainerBuildError) and error.path else (root,)
                key = (code, root, path)
                if key in seen:
                    continue
                seen.add(key)
                issues.append(
                    BuildIssue(
                        code=code,
                        severity=IssueSeverity.error,
                        message=_safe_error_message(error),
                        root=root,
                        path=path,
                    )
                )
    if not issues:
        issues.append(
            BuildIssue(
                code=_build_error_code(original),
                severity=IssueSeverity.error,
                message=_safe_error_message(original),
            )
        )
    return (
        BuildReport(tuple(issues), checked_roots=checked),
        tuple(attempts),
        (total_attempts, total_attempts - len(attempts)),
    )


def _recorded_root_selection(
    plan: _PlanSet,
    service_type: Any,
    filter: ComponentFilter,
    *,
    collection: bool,
    records: tuple[_CandidateRecord, ...] | None = None,
) -> tuple[CompilationExplanation, tuple[_CandidateRecord, ...]]:
    records = plan.root_candidates.get(service_type, ()) if records is None else records
    selected_records: list[_CandidateRecord] = []
    selected: list[CandidateDecision] = []
    rejected: list[CandidateDecision] = []
    description = _filter_description(filter)
    default_selection = filter is default_component_filter or description.endswith("default_component_filter")
    for record in records:
        if not record.eligible:
            rejected.append(record.decision)
            continue
        matched = filter(_provider_selection_component(record.component))
        if matched:
            selected_records.append(record)
            code = (
                "included-collection"
                if collection
                else ("selected-default" if default_selection else "selected-explicit-filter")
            )
            extra_codes = tuple(code for code in record.decision.reason_codes if code != "registration-eligible")
            selected.append(
                CandidateDecision(
                    record.component.id,
                    DecisionOutcome.included if collection else DecisionOutcome.selected,
                    (code, *extra_codes),
                    f"The entry-point filter {description} returned true",
                    record.decision.origin,
                )
            )
        else:
            rejected.append(
                CandidateDecision(
                    record.component.id,
                    DecisionOutcome.rejected,
                    ("rejected-name" if default_selection else "rejected-filter",),
                    f"The entry-point filter {description} returned false",
                    record.decision.origin,
                )
            )
    return (
        CompilationExplanation(
            subject=qualified_name(service_type),
            path=(qualified_name(service_type),),
            selected=tuple(selected),
            rejected=tuple(rejected),
        ),
        tuple(selected_records),
    )


def _finalize_plan(plan: _PlanSet) -> _PlanSet:
    all_roots = _graph_roots(plan)
    entrypoints: list[GraphRoot] = []
    issues: list[BuildIssue] = list(plan.compiler_issues)
    known_root_selections: dict[tuple[Any, int], CompilationExplanation] = {}

    for request in plan.blueprint.entrypoints:
        collection = _collection_request(request.service_type)
        if collection is not None:
            _, element_type = collection
            explanation, selected_records = _recorded_root_selection(
                plan,
                element_type,
                request.filter,
                collection=True,
            )
            known_root_selections[(element_type, id(request.filter))] = explanation
            matches = [GraphRoot(request.service_type, record.component, None) for record in selected_records]
            if not matches:
                root_name = qualified_name(request.service_type)
                issues.append(
                    BuildIssue(
                        code="missing-entrypoint",
                        severity=IssueSeverity.error,
                        message=f"Marked entry point {root_name} has no matching compiled root",
                        root=root_name,
                        path=(root_name,),
                    )
                )
                continue
            entrypoints.extend(matches)
            continue

        explanation, selected_records = _recorded_root_selection(
            plan,
            request.service_type,
            request.filter,
            collection=False,
        )
        known_root_selections[(request.service_type, id(request.filter))] = explanation
        matches = [GraphRoot(request.service_type, record.component, None) for record in selected_records]
        root_name = qualified_name(request.service_type)
        if not matches:
            issues.append(
                BuildIssue(
                    code="missing-entrypoint",
                    severity=IssueSeverity.error,
                    message=f"Marked entry point {root_name} has no matching compiled root",
                    root=root_name,
                    path=(root_name,),
                )
            )
            continue
        provider = _provider_request(request.service_type)
        if len(matches) > 1:
            issues.append(
                BuildIssue(
                    code=("provider-ambiguous-component" if provider is not None else "ambiguous-selection"),
                    severity=(IssueSeverity.error if provider is not None else IssueSeverity.warning),
                    message=(
                        f"Marked provider entry point {root_name} matches {len(matches)} targets"
                        if provider is not None
                        else f"Marked entry point {root_name} matches {len(matches)} roots; the first is selected"
                    ),
                    root=root_name,
                    path=(root_name,),
                )
            )
        if provider is not None and provider[0] == "sync":
            selected_id = matches[0].component.id
            selected_plan = next(
                candidate for candidate in plan.roots[request.service_type] if candidate.component.id == selected_id
            )
            if isinstance(selected_plan.step, _ProviderStep) and not selected_plan.step.target.sync_supported:
                issues.append(
                    BuildIssue(
                        code="provider-requires-async",
                        severity=IssueSeverity.error,
                        message=(
                            f"Synchronous provider entry point {root_name} targets a component that "
                            "requires asynchronous resolution"
                        ),
                        root=root_name,
                        path=(root_name, qualified_name(provider[1])),
                    )
                )
        entrypoints.append(matches[0])

    for boundary in plan.blueprint.boundaries:
        exposed_ids = {
            target.registration_id for target in boundary.resolved_exposes if target.registration_id is not None
        }
        area_records = plan.area_root_candidates.get(boundary.name, {})
        for request in boundary.layer.entrypoints:
            collection = _collection_request(request.service_type)
            candidate_type = request.service_type if collection is None else collection[1]
            explanation, selected_records = _recorded_root_selection(
                plan,
                candidate_type,
                request.filter,
                collection=collection is not None,
                records=area_records.get(candidate_type, ()),
            )
            known_root_selections[(candidate_type, id(request.filter))] = explanation
            selected_local = tuple(record for record in selected_records if record.component.boundary == boundary.name)
            if len(selected_local) != len(selected_records):
                issues.append(
                    BuildIssue(
                        code="boundary-entrypoint-not-local",
                        severity=IssueSeverity.error,
                        message=(
                            f"Boundary {boundary.name!r} entry point {qualified_name(request.service_type)} "
                            "selects a component admitted through Use"
                        ),
                        root=qualified_name(request.service_type),
                        path=(boundary.name, qualified_name(request.service_type)),
                    )
                )
                continue
            if not selected_local:
                issues.append(
                    BuildIssue(
                        code="boundary-entrypoint-not-local",
                        severity=IssueSeverity.error,
                        message=(
                            f"Boundary {boundary.name!r} entry point {qualified_name(request.service_type)} "
                            "does not select one local component"
                        ),
                        root=qualified_name(request.service_type),
                        path=(boundary.name, qualified_name(request.service_type)),
                    )
                )
                continue
            if any(record.component.id not in exposed_ids for record in selected_local):
                issues.append(
                    BuildIssue(
                        code="boundary-entrypoint-not-exposed",
                        severity=IssueSeverity.error,
                        message=(
                            f"Boundary {boundary.name!r} entry point {qualified_name(request.service_type)} "
                            "must also be declared with Expose"
                        ),
                        root=qualified_name(request.service_type),
                        path=(boundary.name, qualified_name(request.service_type)),
                    )
                )
                continue
            if collection is None and len(selected_local) > 1:
                issues.append(
                    BuildIssue(
                        code="ambiguous-selection",
                        severity=IssueSeverity.warning,
                        message=(
                            f"Boundary {boundary.name!r} entry point {qualified_name(request.service_type)} "
                            f"matches {len(selected_local)} local components; the first is selected"
                        ),
                        root=qualified_name(request.service_type),
                        path=(boundary.name, qualified_name(request.service_type)),
                    )
                )
                selected_local = selected_local[:1]
            entrypoints.extend(
                GraphRoot(request.service_type, record.component, boundary.name) for record in selected_local
            )

    if entrypoints:
        reachable_ids = {
            component.id
            for root in entrypoints
            for component in _component_tree(root.component)
            if component.kind is ComponentKind.registration
        }
        reported: set[str] = set()
        for root in all_roots:
            component = root.component
            if component.kind is not ComponentKind.registration:
                continue
            if component.id in reachable_ids or component.id in reported:
                continue
            reported.add(component.id)
            issues.append(
                BuildIssue(
                    code="unreachable-component",
                    severity=IssueSeverity.warning,
                    message=(
                        f"{qualified_name(component.service_type)} -> "
                        f"{qualified_name(component.implementation_type)} is not reachable from a marked entry point"
                    ),
                    root=qualified_name(root.requested_type),
                )
            )

    boundary_contracts = tuple(
        {
            "name": boundary.name,
            "exposures": [
                {
                    "service": qualified_name(target.service_type),
                    "name": target.name,
                    "tags": [{"name": tag.name, "value": tag.value} for tag in sorted(target.tags, key=_tag_sort_key)],
                    "source_service": qualified_name(target.source_service_type),
                    "source_name": target.source_name,
                    "source_tags": [
                        {"name": tag.name, "value": tag.value} for tag in sorted(target.source_tags, key=_tag_sort_key)
                    ],
                }
                for target in sorted(
                    boundary.resolved_exposes,
                    key=lambda item: (qualified_name(item.service_type), item.name or ""),
                )
            ],
            "uses": [
                {
                    "source": target.source or "root",
                    "service": qualified_name(target.service_type),
                    "name": target.name,
                    "tags": [{"name": tag.name, "value": tag.value} for tag in sorted(target.tags, key=_tag_sort_key)],
                    "scope_slot": target.slot,
                }
                for target in sorted(
                    boundary.resolved_uses,
                    key=lambda item: (item.source or "", qualified_name(item.service_type), item.name or ""),
                )
            ],
        }
        for boundary in sorted(plan.blueprint.boundaries, key=lambda item: item.name)
    )
    compiled_graph = CompiledGraph(
        roots=all_roots,
        build_args=plan.build_args,
        entrypoints=tuple(entrypoints),
        boundaries=boundary_contracts,
        _root_candidates=types.MappingProxyType(dict(plan.root_candidates)),
        _known_root_selections=types.MappingProxyType(known_root_selections),
        _occurrence_explanations=types.MappingProxyType(dict(plan.occurrence_explanations)),
        _parameter_explanations=types.MappingProxyType(dict(plan.parameter_explanations)),
        _generic_explanations=types.MappingProxyType(dict(plan.generic_explanations)),
        _occurrence_layers=types.MappingProxyType(dict(plan.occurrence_layers)),
    )
    occurrence_paths = {
        str(component.occurrence_id): path
        for path, component in compiled_graph._component_paths(all_roots=True).items()
    }
    parameter_explanations = types.MappingProxyType(
        {
            occurrence: types.MappingProxyType(
                {
                    name: replace(
                        record,
                        selected_components=tuple(
                            occurrence_paths.get(item, item) for item in record.selected_components
                        ),
                    )
                    for name, record in records.items()
                }
            )
            for occurrence, records in plan.parameter_explanations.items()
        }
    )
    compiled_graph = replace(compiled_graph, _parameter_explanations=parameter_explanations)
    compiled_graph.ownership_report()
    built_in_issues = tuple(dict.fromkeys(issues))
    build_rule_issues = _run_validation_rules(
        compiled_graph,
        (definition for definition in plan.blueprint.validation_rules if definition.mode == "build"),
    )

    deduplicated = tuple(dict.fromkeys((*built_in_issues, *build_rule_issues)))
    report = BuildReport(deduplicated, checked_roots=len(all_roots))
    if not report.is_valid:
        raise ContainerBuildError(report=report)
    return replace(
        plan,
        compiled_graph=compiled_graph,
        build_report=report,
    )


def _template_definitions(blueprint: _Blueprint) -> tuple[tuple[_DecoratorTemplateDefinition, _Layer, str | None], ...]:
    found: list[tuple[_DecoratorTemplateDefinition, _Layer, str | None]] = []
    seen: set[str] = set()
    removed: set[str] = set()
    for layer in blueprint.layers:
        removed.update(layer.removed_template_ids)
        for definition in sorted(layer.decorator_templates, key=lambda item: item.order):
            if definition.id not in seen and definition.id not in removed:
                found.append((definition, layer, None))
                seen.add(definition.id)
    for boundary in blueprint.boundaries:
        for definition in sorted(boundary.layer.decorator_templates, key=lambda item: item.order):
            if definition.id not in boundary.layer.removed_template_ids:
                found.append((definition, boundary.layer, boundary.name))
    return tuple(found)


def _source_registration_info(registration: legacy._Registration, layer: _Layer) -> RegistrationInfo:
    implementation = layer.instance_implementation_types.get(registration.id)
    if implementation is None and constructor_type(registration.implementation) is not None:
        implementation = registration.implementation
    elif implementation is None and not registration.is_instance:
        annotation = _factory_result_annotation(registration.implementation)
        if (
            annotation is not inspect.Signature.empty
            and annotation is not Any
            and constructor_type(annotation) is not None
        ):
            implementation = annotation
    return RegistrationInfo(
        id=registration.id,
        service_type=registration.service_type,
        implementation_type=implementation,
        name=registration.name,
        tags=tuple(registration.tags),
    )


def _static_instance_implementation_type(instance: Any) -> Any:
    """Read only genuine stored generic aliases, without invoking user attributes."""
    implementation_type = type(instance)
    alias = inspect.getattr_static(instance, "__orig_class__", None)
    # Inspect arbitrary metadata only after checking its concrete runtime type:
    # even isinstance/get_origin can consult an object's custom __class__.
    alias_type = type(alias)
    if alias_type is types.GenericAlias or alias_type is type(typing.List[int]):
        if get_origin(alias) is implementation_type:
            return alias
    return implementation_type


def _template_sources(blueprint: _Blueprint, key: Any, area: str | None) -> list[tuple[legacy._Registration, _Layer]]:
    visible = blueprint.registrations(key, area)
    # Lookup order is newest-first; decorator source order is declaration order.
    # Preserve layer/visibility precedence, then use the snapshot's insertion
    # ordered origins (explicit declarations followed by discovery materialization).
    layer_order: dict[int, int] = {}
    declaration_order: dict[int, dict[str, int]] = {}
    for _, layer in visible:
        if id(layer) not in layer_order:
            layer_order[id(layer)] = len(layer_order)
            declaration_order[id(layer)] = {key: index for index, key in enumerate(layer.registration_origins)}
    return sorted(
        visible,
        key=lambda item: (
            layer_order[id(item[1])],
            declaration_order[id(item[1])].get(item[0].id, len(declaration_order[id(item[1])])),
        ),
    )


def _expand_decorator_templates(
    blueprint: _Blueprint,
    *,
    build_args: Mapping[str, Any] = _EMPTY_BUILD_ARGS,
    anchored_singleton_steps: dict[tuple[str, tuple[Any, ...]], _RegistrationStep] | None = None,
    anchored_pre_configuration_steps: dict[str, _CompiledPreConfiguration] | None = None,
    anchored_owner_tokens: frozenset[str] = frozenset(),
    inherited_parameter_explanations: Mapping[int, Mapping[str, ParameterExplanation]] = types.MappingProxyType({}),
    inherited_generic_explanations: Mapping[int, GenericBindingExplanation] = types.MappingProxyType({}),
) -> _TemplateExpansion:
    """Expand a normalized, visibility-prepared snapshot once, without target activation.

    Call outside diagnostic root retries. Every source gets a disposable compiler;
    neither its steps nor generated candidates are appended to original layers.
    """
    owners = frozenset(layer.owner_token for layer in (*blueprint.layers, *(b.layer for b in blueprint.boundaries)))
    active = _EXPANDING_TEMPLATE_OWNERS.get()
    if owners & active:
        raise ContainerBuildError(
            "Template expansion cannot reenter its composition", code="template-expansion-reentry"
        )
    token = _EXPANDING_TEMPLATE_OWNERS.set(active | owners)
    candidates: list[_GeneratedDecoratorDefinition] = []
    selections: list[_TemplateSourceSelection] = []
    try:
        for definition, declaration_layer, area in _template_definitions(blueprint):
            key = definition.for_each
            if getattr(key, "__parameters__", ()) or _typevars_in(key):
                raise ContainerBuildError(
                    "Decorator templates require an exact closed source service key",
                    code="template-source-open-generic",
                    path=(definition.id, qualified_name(key)),
                )
            seen: set[str] = set()
            source_order = 0
            for registration, layer in _template_sources(blueprint, key, area):
                if registration.id in seen:
                    continue
                # An implementation lookup key is not a source service declaration.
                # Explicit boundary aliases still retain the original source key.
                if registration.service_type != key and not blueprint.visibility_targets(area, registration.id, key):
                    continue
                if getattr(registration.service_type, "__parameters__", ()) or _typevars_in(registration.service_type):
                    continue
                seen.add(registration.id)
                source_area = blueprint.registration_area(layer)
                try:
                    core = _Compiler(
                        blueprint,
                        build_args=build_args,
                        anchored_singletons=anchored_singleton_steps,
                        anchored_pre_configurations=anchored_pre_configuration_steps,
                        anchored_owner_tokens=anchored_owner_tokens,
                        inherited_parameter_explanations=inherited_parameter_explanations,
                        inherited_generic_explanations=inherited_generic_explanations,
                    )._compile_source_core(registration.id, registration.service_type)
                    selected = bool(definition.source_filter(core))
                    source = _source_registration_info(registration, layer)
                    generated_id = None
                    if selected:
                        specification = definition.template(source)
                        if not isinstance(specification, DecoratorTemplate):
                            if inspect.iscoroutine(specification):
                                specification.close()
                            raise TypeError("Template factories must return a DecoratorTemplate synchronously")
                        generated_id = str(uuid5(UUID(definition.id), registration.id))
                        candidates.append(
                            _GeneratedDecoratorDefinition(
                                id=generated_id,
                                declaration=definition,
                                source=source,
                                specification=specification,
                                source_order=source_order,
                                declaration_area=area,
                                declaration_owner_token=declaration_layer.owner_token,
                                source_area=source_area,
                                source_owner_token=layer.owner_token,
                            )
                        )
                    selections.append(
                        _TemplateSourceSelection(
                            template_id=definition.id,
                            source=source,
                            component=core,
                            selected=selected,
                            source_order=source_order,
                            declaration_area=area,
                            source_area=source_area,
                            generated_id=generated_id,
                        )
                    )
                except Exception as error:
                    code = error.code if isinstance(error, ContainerBuildError) and error.code else "template-expansion"
                    path = error.path if isinstance(error, ContainerBuildError) else ()
                    raise ContainerBuildError(
                        f"Template {definition.id} source {registration.id}: {_safe_error_message(error)}",
                        code=code,
                        path=(definition.id, registration.id, *path),
                    ) from error
                source_order += 1
        return _TemplateExpansion(blueprint, tuple(candidates), tuple(selections), build_args)
    finally:
        _EXPANDING_TEMPLATE_OWNERS.reset(token)


def _check_template_boundary_visibility(
    initial_prepared: _Blueprint,
    expanded_normalized: _Blueprint,
    *,
    build_args: Mapping[str, Any] = _EMPTY_BUILD_ARGS,
    candidates: tuple[_GeneratedDecoratorDefinition, ...] = (),
) -> _Blueprint:
    """One consistency check; the caller must supply complete generated semantics.

    The expanded snapshot includes actual group/derived candidates so structural
    boundary filters see the same generated semantics as runtime compilation.
    """
    provenance = tuple(f"{item.declaration.id}:{item.source.id}" for item in candidates)
    try:
        checked = _prepare_boundary_visibility(expanded_normalized, build_args=build_args)
    except Exception as error:
        path = error.path if isinstance(error, ContainerBuildError) else ()
        raise ContainerBuildError(
            f"Template expansion invalidated boundary visibility: {_safe_error_message(error)}",
            code="template-visibility-cycle",
            path=(*path, *provenance),
        ) from error
    initial = {boundary.name: boundary for boundary in initial_prepared.boundaries}
    changed = tuple(
        boundary.name
        for boundary in checked.boundaries
        if boundary.name not in initial
        or (boundary.resolved_uses, boundary.resolved_exposes)
        != (initial[boundary.name].resolved_uses, initial[boundary.name].resolved_exposes)
    )
    missing = tuple(name for name in initial if checked.boundary(name) is None)
    if changed or missing:
        raise ContainerBuildError(
            "Template expansion changed boundary visibility",
            code="template-visibility-cycle",
            path=(*changed, *missing, *provenance),
        )
    # Preserve the agreed visibility with the expanded layers, not stale layers
    # from the initial prepared snapshot.
    return replace(
        expanded_normalized,
        boundaries=tuple(
            replace(
                boundary,
                resolved_uses=initial[boundary.name].resolved_uses,
                resolved_exposes=initial[boundary.name].resolved_exposes,
            )
            for boundary in checked.boundaries
        ),
    )


def _compile_with_report(
    blueprint: _Blueprint,
    *,
    build_args: Mapping[str, Any] = _EMPTY_BUILD_ARGS,
    preview: bool = False,
    anchored_singleton_steps: dict[tuple[str, tuple[Any, ...]], _RegistrationStep] | None = None,
    anchored_pre_configuration_steps: dict[str, _CompiledPreConfiguration] | None = None,
    anchored_owner_tokens: frozenset[str] = frozenset(),
    inherited_parameter_explanations: Mapping[int, Mapping[str, ParameterExplanation]] = types.MappingProxyType({}),
    inherited_generic_explanations: Mapping[int, GenericBindingExplanation] = types.MappingProxyType({}),
) -> _PlanSet:
    alias_errors = _blueprint_alias_errors(blueprint)
    if alias_errors:
        report = _alias_error_report(alias_errors)
        raise ContainerBuildError(
            report=report,
            partial_graph=PartialGraph(
                (CompilationAttempt(None, issue_code=report.errors[0].code, witness_path=report.errors[0].path),)
            ),
        )
    try:
        blueprint = _normalize_blueprint_aliases(blueprint)
        blueprint = _prepare_boundary_visibility(blueprint, build_args=build_args)
        expansion = _expand_decorator_templates(
            blueprint,
            build_args=build_args,
            anchored_singleton_steps=anchored_singleton_steps,
            anchored_pre_configuration_steps=anchored_pre_configuration_steps,
            anchored_owner_tokens=anchored_owner_tokens,
            inherited_parameter_explanations=inherited_parameter_explanations,
            inherited_generic_explanations=inherited_generic_explanations,
        )
        expanded = replace(
            blueprint, generated_decorators=expansion.candidates, template_selections=expansion.selections
        )
        blueprint = (
            _check_template_boundary_visibility(
                blueprint,
                _normalize_blueprint_aliases(expanded),
                build_args=build_args,
                candidates=expansion.candidates,
            )
            if expansion.candidates
            else expanded
        )
    except TypeAliasNormalizationError as error:
        report = _alias_error_report((error,))
        raise ContainerBuildError(
            report=report,
            partial_graph=PartialGraph(
                (CompilationAttempt(None, issue_code=report.errors[0].code, witness_path=report.errors[0].path),)
            ),
        ) from error
    except ContainerBuildError as error:
        issue = BuildIssue(
            code=error.code or "compile-error",
            severity=IssueSeverity.error,
            message=_safe_error_message(error),
            root=(error.path[0] if error.path else None),
            path=error.path,
        )
        report = BuildReport((issue,), checked_roots=0)
        raise ContainerBuildError(
            report=report,
            partial_graph=PartialGraph((CompilationAttempt(None, issue_code=issue.code, witness_path=issue.path),)),
        ) from error
    compiler = _Compiler(
        blueprint,
        build_args=build_args,
        anchored_singletons=anchored_singleton_steps,
        anchored_pre_configurations=anchored_pre_configuration_steps,
        anchored_owner_tokens=anchored_owner_tokens,
        inherited_parameter_explanations=inherited_parameter_explanations,
        inherited_generic_explanations=inherited_generic_explanations,
    )
    try:
        plan = compiler.compile()
        return plan if preview else _finalize_plan(plan)
    except ContainerBuildError as error:
        if error.report is not None:
            raise ContainerBuildError(
                report=error.report,
                explanations=tuple(compiler.decision_history),
                partial_graph=PartialGraph((compiler.partial_attempt(error),)),
            ) from error
        report, retries, retry_counts = _error_report(
            blueprint,
            error,
            build_args=build_args,
            anchored_singleton_steps=anchored_singleton_steps,
            anchored_pre_configuration_steps=anchored_pre_configuration_steps,
            anchored_owner_tokens=anchored_owner_tokens,
        )
        raise ContainerBuildError(
            report=report,
            explanations=tuple(compiler.decision_history),
            partial_graph=PartialGraph(
                (compiler.partial_attempt(error), *retries),
                inconsistent_retries=any(attempt.succeeded for attempt in retries),
                truncated=retry_counts[1] > 0,
                total_attempts=1 + retry_counts[0],
                omitted_attempts=retry_counts[1],
                retained_attempts=1 + len(retries),
                total_roots=retry_counts[0],
                retained_roots=len(retries),
                omitted_roots=retry_counts[1],
            ),
        ) from error
    except Exception as error:
        report, retries, retry_counts = _error_report(
            blueprint,
            error,
            build_args=build_args,
            anchored_singleton_steps=anchored_singleton_steps,
            anchored_pre_configuration_steps=anchored_pre_configuration_steps,
            anchored_owner_tokens=anchored_owner_tokens,
        )
        raise ContainerBuildError(
            report=report,
            explanations=tuple(compiler.decision_history),
            partial_graph=PartialGraph(
                (compiler.partial_attempt(error), *retries),
                inconsistent_retries=any(attempt.succeeded for attempt in retries),
                truncated=retry_counts[1] > 0,
                total_attempts=1 + retry_counts[0],
                omitted_attempts=retry_counts[1],
                retained_attempts=1 + len(retries),
                total_roots=retry_counts[0],
                retained_roots=len(retries),
                omitted_roots=retry_counts[1],
            ),
        ) from error


class _RuntimeResolutionContext:
    __slots__ = ("active", "resolution_cache", "registration_stack", "scope")

    def __init__(self, scope: Scope):
        self.scope = scope
        self.active = True
        self.resolution_cache: dict[str, Any] = {}
        self.registration_stack: list[_RegistrationStep] = []

    def ensure_active(self) -> None:
        self.scope._ensure_open()
        if not self.active:
            raise ScopeClosedError("This resolution context is no longer active")

    def finish(self) -> None:
        self.active = False
        self.resolution_cache.clear()

    def resolve_root(self, service_type: Any, filter: ComponentFilter) -> Any:
        collection = _collection_request(service_type)
        if collection is not None:
            collection_type, element_type = collection
            plans = self.scope._select_roots(element_type, filter)
            if not all(plan.step.sync_supported for plan in plans):
                raise RuntimeError(f"{service_type!r} requires resolve_async()")
            return collection_type(plan.step.resolve(self) for plan in plans)
        plan = self.scope._select_root(service_type, filter)
        if not plan.step.sync_supported:
            raise RuntimeError(f"{service_type!r} requires resolve_async()")
        return plan.step.resolve(self)

    async def resolve_root_async(self, service_type: Any, filter: ComponentFilter) -> Any:
        collection = _collection_request(service_type)
        if collection is not None:
            collection_type, element_type = collection
            plans = self.scope._select_roots(element_type, filter)
            values = await asyncio.gather(*(plan.step.resolve_async(self) for plan in plans))
            return collection_type(values)
        return await self.scope._select_root(service_type, filter).step.resolve_async(self)

    def assert_allowed(self, step: _RegistrationStep) -> None:
        registration = step.registration
        for active in self.registration_stack:
            if active.registration is registration:
                raise RuntimeError(f"Circular component activation for {registration.service_type!r}")

    def add_finalizer(
        self,
        owner: _CleanupOwnerDescriptor,
        finalizer: Callable[..., Any],
    ) -> None:
        if owner.kind is RuntimeOwnerKind.scope:
            self.scope._add_finalizer(finalizer)
            return
        if owner.kind is RuntimeOwnerKind.singleton and owner.owner_token is not None:
            self.scope._owners[owner.owner_token]._add_finalizer(finalizer)
            return
        raise RuntimeError("unsafe-cleanup-owner: compiled activation has no cleanup owner")


class Scope(_RuntimeOwner):
    """An immutable runtime scope backed by a compiled component plan."""

    def __init__(
        self,
        plan: _PlanSet,
        *,
        container: Container,
        parent: Scope | None,
        owners: dict[str, _RuntimeOwner],
        owned_token: str | None = None,
        inherit_scoped: bool = True,
    ) -> None:
        super().__init__()
        self._id: str | None = None
        self._plan = plan
        self.container = container
        self.parent = parent
        self._owners = dict(owners)
        if owned_token is not None:
            self._owners[owned_token] = self
        self._owned_token = owned_token
        self._inherit_scoped = inherit_scoped
        self._scoped: dict[str, Any] = {}
        self._provisions: dict[tuple[Any, str | None], Any] = {}
        self._resolution_started = False

    def _ensure_open(self) -> None:
        if self._closed:
            raise ScopeClosedError("This scope is closed")

    @property
    def id(self) -> str:
        identifier = self._id
        if identifier is None:
            with _RUNTIME_ID_LOCK:
                identifier = self._id
                if identifier is None:
                    identifier = str(uuid4())
                    self._id = identifier
        return identifier

    @property
    def components(self) -> tuple[Component, ...]:
        return tuple(plan.component for plans in self._plan.roots.values() for plan in plans)

    @property
    def graph(self) -> CompiledGraph:
        graph = self._plan.compiled_graph
        if graph is None:
            raise RuntimeError("Compiled graph metadata is unavailable")
        return graph

    @property
    def build_report(self) -> BuildReport:
        return self._plan.build_report

    def validation_report(self) -> BuildReport:
        """Return build findings plus a fresh run of validate-only rules."""

        validation_rule_issues = _run_validation_rules(
            self.graph,
            (definition for definition in self._plan.blueprint.validation_rules if definition.mode == "validation"),
        )
        return BuildReport(
            tuple(dict.fromkeys((*self.build_report.issues, *validation_rule_issues))),
            checked_roots=self.build_report.checked_roots,
        )

    @property
    def build_args(self) -> Mapping[str, Any]:
        """Immutable user inputs supplied for this plan's compilation."""

        return self._plan.build_args

    @property
    def ensured_import_modules(self) -> tuple[str, ...]:
        """Concrete module names explicitly imported for subclass discovery."""

        layers = (
            *self._plan.blueprint.layers,
            *(boundary.layer for boundary in self._plan.blueprint.boundaries),
        )
        return tuple(dict.fromkeys(module_name for layer in layers for module_name in layer.ensured_import_modules))

    def has_component(self, service_type: Any, filter: ComponentFilter = default_component_filter) -> bool:
        """Return whether the frozen plan contains a matching root component."""

        plans = self._plan.roots.get(service_type)
        if plans is None:
            plans = self._plan.provider_roots.get(service_type)
        if plans is None:
            canonical_type = normalize_type_alias(service_type)
            if canonical_type is service_type:
                return False
            return self.has_component(canonical_type, filter)
        return any(filter(_provider_selection_component(plan.component)) for plan in plans)

    def has_scope_slot(self, service_type: Any, name: str | None = None) -> bool:
        """Return whether this runtime can accept the supplied scope value."""

        slots = self._plan.blueprint.slots
        return (service_type, name) in slots or (normalize_type_alias(service_type), name) in slots

    def has_provision(self, service_type: Any, name: str | None = None) -> bool:
        """Return whether this scope or one of its parents supplied a slot value."""

        key = (service_type, name)
        if key not in self._plan.blueprint.slots:
            key = (normalize_type_alias(service_type), name)
        scope: Scope | None = self
        while scope is not None:
            if key in scope._provisions:
                return True
            scope = scope.parent
        return False

    def _select_root(self, service_type: Any, filter: ComponentFilter) -> _RootPlan:
        self._ensure_open()
        if filter is default_component_filter:
            plan = self._plan.default_roots.get(service_type)
            if plan is not None:
                self._resolution_started = True
                return plan

        # The plan's keys are already canonical. Normalize only unknown spellings,
        # never a known key whose candidates were rejected by the caller's filter.
        plans = self._plan.roots.get(service_type)
        if plans is None:
            plans = self._plan.provider_roots.get(service_type)
        if plans is None and (service_type, None) not in self._plan.blueprint.slots:
            canonical_type = normalize_type_alias(service_type)
            if canonical_type is not service_type:
                return self._select_root(canonical_type, filter)

        self._resolution_started = True
        if plans is not None and filter is default_component_filter:
            plan = next((candidate for candidate in plans if candidate.component.name is None), None)
            if plan is not None:
                return plan
        elif plans is not None:
            for plan in plans:
                if filter(_provider_selection_component(plan.component)):
                    return plan
        if (service_type, None) in self._plan.blueprint.slots:
            raise ScopeProvisionError(f"Scope slot {service_type!r} has no provided value")
        raise CannotResolveError(service_type)

    def _select_roots(self, service_type: Any, filter: ComponentFilter) -> tuple[_RootPlan, ...]:
        self._ensure_open()
        if filter is default_component_filter:
            plans = self._plan.default_root_groups.get(service_type)
            if plans is not None:
                self._resolution_started = True
                return plans
            # Default collection selection does not synthesize groups of providers.
            if service_type in self._plan.provider_roots:
                self._resolution_started = True
                return ()
        else:
            plans = self._plan.roots.get(service_type)
            if plans is None:
                plans = self._plan.provider_roots.get(service_type)
            if plans is not None:
                self._resolution_started = True
                return tuple(plan for plan in plans if filter(_provider_selection_component(plan.component)))
        if (service_type, None) not in self._plan.blueprint.slots:
            canonical_type = normalize_type_alias(service_type)
            if canonical_type is not service_type:
                return self._select_roots(canonical_type, filter)
        self._resolution_started = True
        return ()

    def resolve(
        self,
        service_type: TypeForm[TService],
        filter: ComponentFilter = default_component_filter,
    ) -> TService:
        self._ensure_open()
        if isinstance(service_type, type) and filter is default_component_filter:
            self._resolution_started = True
            plan = self._plan.default_roots.get(service_type)
            if plan is None:
                if (service_type, None) in self._plan.blueprint.slots:
                    raise ScopeProvisionError(f"Scope slot {service_type!r} has no provided value")
                raise CannotResolveError(service_type)
            if not plan.step.sync_supported:
                raise RuntimeError(f"{service_type!r} requires resolve_async()")
            if isinstance(plan.step, _SingletonRegistrationStep):
                owner = self._owners[plan.step.owner_token]
                value = owner._singletons.get(plan.step.registration.id, _CACHE_MISS)
                if value is not _CACHE_MISS:
                    return cast(TService, value)
            elif isinstance(plan.step, _ScopedRegistrationStep):
                found, value = self._find_scoped(plan.step.registration.id)
                if found:
                    return cast(TService, value)
            context = _RuntimeResolutionContext(self)
            try:
                return cast(TService, plan.step.resolve(context))
            finally:
                context.finish()
        context = _RuntimeResolutionContext(self)
        try:
            return cast(TService, context.resolve_root(service_type, filter))
        finally:
            context.finish()

    async def resolve_async(
        self,
        service_type: TypeForm[TService],
        filter: ComponentFilter = default_component_filter,
    ) -> TService:
        self._ensure_open()
        if isinstance(service_type, type) and filter is default_component_filter:
            self._resolution_started = True
            plan = self._plan.default_roots.get(service_type)
            if plan is None:
                if (service_type, None) in self._plan.blueprint.slots:
                    raise ScopeProvisionError(f"Scope slot {service_type!r} has no provided value")
                raise CannotResolveError(service_type)
            if isinstance(plan.step, _SingletonRegistrationStep):
                owner = self._owners[plan.step.owner_token]
                value = owner._singletons.get(plan.step.registration.id, _CACHE_MISS)
                if value is not _CACHE_MISS:
                    return cast(TService, value)
            elif isinstance(plan.step, _ScopedRegistrationStep):
                found, value = self._find_scoped(plan.step.registration.id)
                if found:
                    return cast(TService, value)
            context = _RuntimeResolutionContext(self)
            try:
                return cast(TService, await plan.step.resolve_async(context))
            finally:
                context.finish()
        context = _RuntimeResolutionContext(self)
        try:
            return cast(TService, await context.resolve_root_async(service_type, filter))
        finally:
            context.finish()

    def provide(self, service_type: TypeForm[TService], value: TService, name: str | None = None) -> Scope:
        self._ensure_open()
        key = (service_type, name)
        if key not in self._plan.blueprint.slots:
            service_type = normalize_type_alias(service_type)
            key = (service_type, name)
        if key not in self._plan.blueprint.slots:
            raise UndeclaredScopeSlotError(f"No scope slot declared for {service_type!r} named {name!r}")
        if self._resolution_started:
            raise ScopeProvisionError("Scope provisions are locked after resolution begins")
        if key in self._provisions:
            raise ScopeProvisionError(f"Scope slot {service_type!r} named {name!r} was already provided")
        self._provisions[key] = value
        return self

    def _find_provision(self, service_type: Any, name: str | None) -> Any:
        key = (service_type, name)
        if key in self._provisions:
            return self._provisions[key]
        if self.parent is not None:
            return self.parent._find_provision(service_type, name)
        raise ScopeProvisionError(f"Scope slot {service_type!r} named {name!r} has no provided value")

    def _find_scoped(self, component_id: str) -> tuple[bool, Any]:
        if component_id in self._scoped:
            return True, self._scoped[component_id]
        if self._inherit_scoped and self.parent is not None:
            return self.parent._find_scoped(component_id)
        return False, None

    def new_scope(self) -> Scope:
        self._ensure_open()
        return Scope(
            self._plan,
            container=self.container,
            parent=self,
            owners=self._owners,
        )

    def new_scope_builder(self) -> ScopeBuilder:
        self._ensure_open()
        return ScopeBuilder(self)

    def __enter__(self) -> Scope:
        self._ensure_open()
        return self

    def __exit__(self, *_: Any) -> None:
        self._close()

    async def __aenter__(self) -> Scope:
        self._ensure_open()
        return self

    async def __aexit__(self, *_: Any) -> None:
        await self._close_async()


class Container(Scope):
    """The immutable root runtime and owner of root singletons."""

    def __init__(self, plan: _PlanSet, root_owner_token: str):
        _RuntimeOwner.__init__(self)
        self._id: str | None = None
        self._plan = plan
        self.container = self
        self.parent = None
        self._owners = {root_owner_token: self}
        self._owned_token = root_owner_token
        self._inherit_scoped = False
        self._scoped = {}
        self._provisions = {}
        self._resolution_started = False

    def new_scope(self) -> Scope:
        self._ensure_open()
        return Scope(
            self._plan,
            container=self,
            parent=self,
            owners=cast(dict[str, _RuntimeOwner], self._owners),
        )


class _BuilderBase:
    def __init__(
        self,
        *,
        owner_token: str | None = None,
        boundary_name: str | None = None,
        composition_layer: str | None = None,
    ) -> None:
        self.id = str(uuid4())
        self._composition = legacy.Container()
        self._internal_ids = frozenset(
            registration.id
            for registrations in self._composition._registry._registrations.values()
            for registration in registrations
        )
        self._owner_token = owner_token or str(uuid4())
        self._bundle_container_id = self._owner_token
        self._bundle_scope_id = self.id
        self._boundary_name = boundary_name
        self._composition_layer = composition_layer
        self._registration_when: dict[str, ComponentFilter] = {}
        self._registration_origins: dict[str, DefinitionOrigin] = {}
        self._factory_ids: set[str] = set()
        self._factory_specializations: dict[str, object] = {}
        self._provider_maps: dict[str, _ProviderMapDefinition] = {}
        self._contributions: dict[str, Mapping[ProviderMapGroup[Any, Any], Hashable]] = {}
        self._service_groups: dict[str, frozenset[ServiceGroup]] = {}
        self._pattern_ids: list[str] = []
        self._decorators: list[_DecoratorDefinition] = []
        self._decorator_templates: list[_DecoratorTemplateDefinition] = []
        self._removed_template_ids: set[str] = set()
        self._instance_implementation_types: dict[str, Any] = {}
        self._removed_decorator_ids: set[str] = set()
        self._next_decorator_order = 0
        self._pre_configurations: list[_PreConfigurationDefinition] = []
        self._pre_configuration_states: dict[str, _PreConfigurationState] = {}
        self._next_pre_configuration_order = 0
        self._registration_discoveries: list[_RegistrationDiscovery] = []
        self._slots: set[tuple[Any, str | None]] = set()
        self._slot_origins: dict[tuple[Any, str | None], DefinitionOrigin] = {}
        self._entrypoints: list[_EntryPoint] = []
        self._validation_rules: list[_ValidationRuleDefinition] = []
        self._bundle_stack: list[str] = []
        self._boundaries: list[_BoundaryBlueprint] = []
        self._built = False

    def _assert_mutable(self) -> None:
        if self._owner_token in _EXPANDING_TEMPLATE_OWNERS.get():
            raise ContainerBuildError(
                "Template expansion cannot mutate, build, or preview its composition",
                code="template-expansion-reentry",
            )
        if self._built:
            raise BuilderAlreadyBuiltError("Builders are single-use after a successful build")

    def bundle_run_key(self, per: BundleRunScope) -> str:
        if per == "boundary":
            return self.id
        if per == "scope":
            return self._bundle_scope_id
        if per == "container":
            return self._bundle_container_id
        raise ValueError("per must be 'boundary', 'scope', or 'container'")

    def _effective_build_args(self, build_args: Mapping[str, Any] | None) -> Mapping[str, Any]:
        parent = getattr(self, "_parent", None)
        if parent is None:
            return _normalize_build_args(build_args)
        return _merge_build_args(parent.build_args, build_args)

    def _definition_origin(self, kind: str, definition_id: str | None) -> DefinitionOrigin:
        return DefinitionOrigin(
            kind=kind,
            location=_source_location(),
            layer=self._composition_layer or ("overlay" if hasattr(self, "_parent") else "root"),
            bundle_path=tuple(self._bundle_stack),
            definition_id=definition_id,
            boundary=self._boundary_name,
        )

    def _layer(self) -> _Layer:
        registry = _clone_registry(self._composition._registry)
        registration_when = dict(self._registration_when)
        registration_origins = dict(self._registration_origins)
        service_groups = dict(self._service_groups)

        # Imports from every rule happen before any rule takes its live subclass
        # snapshot. This keeps declaration order from changing discovery results.
        ensured_import_modules = _ensure_discovery_imports(self._registration_discoveries)

        discovered = legacy._Registry()
        for rule in self._registration_discoveries:
            rule.materialize(discovered, registration_when, registration_origins, service_groups)
        for service_type, registrations in discovered._registrations.items():
            # Explicit composition always precedes convention-based discovery.
            registry._registrations[service_type].extend(registrations)

        return _Layer(
            registry=registry,
            internal_ids=self._internal_ids,
            owner_token=self._owner_token,
            registration_when=registration_when,
            registration_origins=registration_origins,
            factory_ids=frozenset(self._factory_ids),
            factory_specializations=dict(self._factory_specializations),
            decorators=tuple(self._decorators),
            removed_decorator_ids=frozenset(self._removed_decorator_ids),
            pre_configurations=tuple(self._pre_configurations),
            pre_configuration_states=dict(self._pre_configuration_states),
            slots=frozenset(self._slots),
            slot_origins=dict(self._slot_origins),
            entrypoints=tuple(self._entrypoints),
            validation_rules=tuple(self._validation_rules),
            provider_maps=types.MappingProxyType(dict(self._provider_maps)),
            contributions=types.MappingProxyType(dict(self._contributions)),
            service_groups=types.MappingProxyType(service_groups),
            pattern_ids=tuple(self._pattern_ids),
            ensured_import_modules=ensured_import_modules,
            decorator_templates=tuple(self._decorator_templates),
            removed_template_ids=frozenset(self._removed_template_ids),
            instance_implementation_types=types.MappingProxyType(dict(self._instance_implementation_types)),
        )

    def _install_boundary(self, boundary: Boundary) -> None:
        self._assert_mutable()
        if not isinstance(boundary, Boundary):
            raise TypeError("install_boundary() requires a Boundary")
        if not callable(boundary.root_bundle):
            raise TypeError("Boundary root_bundle must be callable")
        # Composition is transactional: only retain the private layer after the
        # entire ordinary bundle has applied successfully.
        private = _BoundaryBuilder(
            owner_token=self._owner_token,
            boundary_name=boundary.name,
            composition_layer="overlay" if hasattr(self, "_parent") else "root",
        )
        private._bundle_container_id = self._bundle_container_id
        private._bundle_scope_id = self._bundle_scope_id
        try:
            private.apply_bundle(boundary.root_bundle)
            blueprint = _BoundaryBlueprint(
                name=boundary.name,
                layer=private._layer(),
                uses=tuple(boundary.uses),
                exposes=tuple(boundary.exposes),
            )
        except BaseException:
            private._rollback_bundle_runs()
            raise
        self._boundaries.append(blueprint)

    def add_validation_rule(self, rule: ValidationRule, *, mode: ValidationRuleMode = "build") -> None:
        """Add a synchronous graph rule to the build or validation phase."""

        self._assert_mutable()
        if not callable(rule):
            raise TypeError("Validation rule must be callable")
        if mode not in ("build", "validation"):
            raise ValueError("mode must be 'build' or 'validation'")
        targets = (rule, getattr(rule, "__call__", None))
        if any(
            inspect.iscoroutinefunction(target) or inspect.isasyncgenfunction(target)
            for target in targets
            if target is not None
        ):
            raise TypeError("Validation rules must be synchronous")
        self._validation_rules.append(
            _ValidationRuleDefinition(
                rule,
                mode,
                self._definition_origin("validation-rule", None),
            )
        )

    def _new_decorator_order(self) -> int:
        value = self._next_decorator_order
        self._next_decorator_order += 1
        return value

    def _new_pre_configuration_order(self) -> int:
        value = self._next_pre_configuration_order
        self._next_pre_configuration_order += 1
        return value

    def register(
        self,
        service_type: TypeForm[TService],
        implementation_type: TypeForm[TService] | None = None,
        *,
        factory: Callable[..., Any] | None = None,
        factory_specialization: object | None = None,
        instance: TService | None = None,
        lifespan: Lifespan = "per_resolution",
        name: str | None = None,
        arguments: Mapping[str, Any] | None = None,
        tags: Iterable[legacy.Tag] | None = None,
        when: ComponentFilter = all_components,
        contributes: Mapping[ProviderMapGroup[Any, Any], Hashable] | None = None,
        groups: Iterable[ServiceGroup] = (),
    ) -> str:
        self._assert_mutable()
        declared_service_type = service_type
        service_type = _composition_type(service_type)
        if implementation_type is not None:
            implementation_type = _composition_type(implementation_type)
        if factory_specialization is not None:
            factory_specialization = _composition_type(factory_specialization)
        if factory_specialization is not None and factory is None:
            raise ValueError("factory_specialization requires factory=")
        service_groups = _materialize_service_groups(groups)
        _validate_service_groups(service_type, service_groups)
        normalized_contributions: dict[ProviderMapGroup[Any, Any], Hashable] | None = None
        if contributes is not None:
            if not isinstance(contributes, Mapping):
                raise TypeError("contributes must be a mapping of ProviderMapGroup to key")
            normalized_contributions = {}
            for group, contribution_key in contributes.items():
                if not isinstance(group, ProviderMapGroup):
                    raise TypeError("contributes keys must be ProviderMapGroup instances")
                group_service_type = _composition_type(group.service_type)
                if not _service_definition_matches(service_type, group_service_type):
                    raise TypeError(
                        f"Registration service {qualified_name(service_type)} is incompatible with "
                        f"provider map group {group.name!r} targeting {qualified_name(group_service_type)}"
                    )
                normalized_contributions[group] = contribution_key
        if is_new_type(service_type) and factory is None and instance is None and implementation_type is None:
            raise TypeError(
                f"NewType service {qualified_name(service_type)} requires a factory, instance or implementation type"
            )
        is_union = get_origin(service_type) in (typing.Union, types.UnionType)
        if is_union and factory is None and instance is None and implementation_type is None:
            raise TypeError(
                f"Union service {qualified_name(service_type)} requires a factory, instance or implementation type"
            )
        # Both legacy paths use the same constructor activator for classes, but
        # the factory path registers only the requested key, not the implementation.
        activation_factory = implementation_type if is_union and factory is None else factory
        instance_implementation_type = None if instance is None else _static_instance_implementation_type(instance)
        component_id = self._composition.register(
            cast(type[TService], service_type),
            implementation_type,
            factory=activation_factory,
            instance=instance,
            lifespan=_legacy_lifespan(lifespan),
            name=name,
            dependency_config=_arguments_to_dependency_config(arguments),
            tags=tags,
            parent_node_filter=legacy.default_parent_node_filter,
        )
        self._registration_when[component_id] = when
        if instance is not None:
            self._instance_implementation_types[component_id] = instance_implementation_type
        if normalized_contributions is not None:
            self._contributions[component_id] = types.MappingProxyType(normalized_contributions)
        self._service_groups[component_id] = service_groups
        self._registration_origins[component_id] = self._definition_origin("registration", component_id)
        for registrations in self._composition._registry._registrations.values():
            for registration in registrations:
                if registration.id == component_id:
                    registration.declared_service_type = declared_service_type
        if factory is not None:
            self._factory_ids.add(component_id)
            if factory_specialization is not None:
                self._factory_specializations[component_id] = factory_specialization
        return component_id

    def register_pattern(
        self,
        service_type: TypeForm[Any],
        *,
        factory: Callable[..., Any],
        lifespan: Lifespan = "per_resolution",
        name: str | None = None,
        arguments: Mapping[str, Any] | None = None,
        tags: Iterable[legacy.Tag] | None = None,
        when: ComponentFilter = all_components,
        groups: Iterable[ServiceGroup] = (),
    ) -> str:
        """Declare a structural factory template specialized only during build."""
        if not callable(factory):
            raise TypeError("register_pattern requires a callable factory")
        component_id = self.register(
            service_type,
            factory=factory,
            lifespan=lifespan,
            name=name,
            arguments=arguments,
            tags=tags,
            when=when,
            groups=groups,
        )
        self._pattern_ids.append(component_id)
        self._registration_origins[component_id] = self._definition_origin("registration-pattern", component_id)
        return component_id

    @overload
    def register_provider_map(
        self,
        service_type: ProviderMapGroup[K, TService],
        *,
        asynchronous: bool = False,
        component_filter: ComponentFilter = all_components,
        name: str | None = None,
    ) -> str: ...

    @overload
    def register_provider_map(
        self,
        service_type: TypeForm[Any],
        *,
        key: Callable[[Component], Hashable],
        key_type: TypeForm[Any] = str,
        asynchronous: bool = False,
        component_filter: ComponentFilter = all_components,
        name: str | None = None,
    ) -> str: ...

    def register_provider_map(
        self,
        service_type: TypeForm[Any] | ProviderMapGroup[Any, Any],
        *,
        key: Callable[[Component], Hashable] | None = None,
        key_type: TypeForm[Any] = str,
        asynchronous: bool = False,
        component_filter: ComponentFilter = all_components,
        name: str | None = None,
    ) -> str:
        """Declare a read-only map of frozen provider targets, keyed during build.

        ``key_type`` defaults to ``str``; supply it explicitly for other key types.
        ``asynchronous=True`` declares ``Mapping[K, AsyncProvider[T]]``.
        Keys must be pure synchronous results with stable hash/equality behavior.
        """

        self._assert_mutable()
        if not isinstance(asynchronous, bool):
            raise TypeError("asynchronous must be a bool")
        group = service_type if isinstance(service_type, ProviderMapGroup) else None
        if group is not None:
            if key is not None:
                raise TypeError("group-based provider maps receive keys from contributions, not key=")
            service_type = group.service_type
            key_type = group.key_type
        elif key is None:
            raise TypeError("register_provider_map requires key= unless given a ProviderMapGroup")
        provider_type = AsyncProvider if asynchronous else Provider
        annotation: Any = types.GenericAlias(Mapping, (key_type, provider_type[service_type]))
        component_id = self.register(annotation, factory=_provider_map_factory, lifespan="transient", name=name)
        self._factory_ids.discard(component_id)
        self._provider_maps[component_id] = _ProviderMapDefinition(key, component_filter, group)
        self._registration_origins[component_id] = self._definition_origin("provider-map", component_id)
        return component_id

    def patch_component(
        self,
        service_type: TypeForm[Any],
        component_id: str,
        *,
        arguments: Mapping[str, Any] | None = None,
        lifespan: Lifespan | None = None,
        tags: Iterable[legacy.Tag] | None = None,
    ) -> None:
        self._assert_mutable()
        service_type = _composition_type(service_type)
        try:
            self._composition.patch_registration(
                cast(type, service_type),
                component_id,
                dependency_config=(
                    None if arguments is None else _arguments_to_dependency_config(arguments, allow_remove=True)
                ),
                lifespan=None if lifespan is None else _legacy_lifespan(lifespan),
                tags=tags,
            )
            return
        except KeyError:
            pass

        declared_service_type = next(
            (
                candidate
                for candidate in self._composition._registry._registrations
                if _composition_type(candidate) == service_type
            ),
            None,
        )
        if declared_service_type is not None:
            self._composition.patch_registration(
                declared_service_type,
                component_id,
                dependency_config=(
                    None if arguments is None else _arguments_to_dependency_config(arguments, allow_remove=True)
                ),
                lifespan=None if lifespan is None else _legacy_lifespan(lifespan),
                tags=tags,
            )
            return

        registration = next(
            (
                candidate
                for rule in self._registration_discoveries
                if (candidate := rule.find_registration(service_type, component_id)) is not None
            ),
            None,
        )
        if registration is None:
            installed_private = next(
                (
                    boundary.name
                    for boundary in self._boundaries
                    if any(
                        candidate.id == component_id
                        for candidate, _ in _Blueprint((), tuple(self._boundaries)).local_registrations(
                            boundary.name, service_type
                        )
                    )
                ),
                None,
            )
            if installed_private is not None:
                raise ContainerBuildError(
                    f"Cannot patch private component {component_id!r} in boundary {installed_private!r}",
                    code=(
                        "overlay-boundary-private-component"
                        if hasattr(self, "_parent")
                        else "boundary-private-component"
                    ),
                    path=(installed_private, qualified_name(service_type)),
                )
            parent = getattr(self, "_parent", None)
            if parent is not None:
                private = next(
                    (
                        boundary.name
                        for boundary in parent._plan.blueprint.boundaries
                        if any(
                            candidate.id == component_id
                            for candidate, _ in parent._plan.blueprint.local_registrations(boundary.name, service_type)
                        )
                    ),
                    None,
                )
                if private is not None:
                    raise ContainerBuildError(
                        f"Overlay cannot patch private component {component_id!r} in boundary {private!r}",
                        code="overlay-boundary-private-component",
                        path=(private, qualified_name(service_type)),
                    )
            raise KeyError(f"No component found for {service_type} with ID {component_id}")
        registration.patch(
            dependency_config=(
                None if arguments is None else _arguments_to_dependency_config(arguments, allow_remove=True)
            ),
            lifespan=None if lifespan is None else _legacy_lifespan(lifespan),
            tags=tags,
        )

    def register_decorator_template(
        self,
        *,
        for_each: Any,
        template: Callable[[RegistrationInfo], DecoratorTemplate],
        source_filter: ComponentFilter = all_components,
    ) -> str:
        self._assert_mutable()
        if not callable(template) or inspect.iscoroutinefunction(template) or inspect.isasyncgenfunction(template):
            raise TypeError("template must be a synchronous callable")
        if not callable(source_filter):
            raise TypeError("source_filter must be callable")
        definition_id = str(uuid4())
        self._decorator_templates.append(
            _DecoratorTemplateDefinition(
                id=definition_id,
                for_each=_composition_type(for_each),
                template=template,
                source_filter=source_filter,
                order=self._new_decorator_order(),
                origin=self._definition_origin("decorator-template", definition_id),
            )
        )
        return definition_id

    def _find_decorator_template(self, template_id: str) -> _DecoratorTemplateDefinition | None:
        if template_id in self._removed_template_ids:
            return None
        own = next((item for item in self._decorator_templates if item.id == template_id), None)
        if own is not None:
            return own
        parent = getattr(self, "_parent", None)
        if parent is None:
            return None
        return next(
            (
                item
                for item, _, area in _template_definitions(parent._plan.blueprint)
                if item.id == template_id and area is None
            ),
            None,
        )

    def patch_decorator_template(
        self,
        template_id: str,
        *,
        for_each: Any = _DECORATOR_UNSET,
        template: Callable[[RegistrationInfo], DecoratorTemplate] | object = _DECORATOR_UNSET,
        source_filter: ComponentFilter | object = _DECORATOR_UNSET,
    ) -> None:
        self._assert_mutable()
        definition = self._find_decorator_template(template_id)
        if definition is None:
            raise KeyError(template_id)
        factory = definition.template if template is _DECORATOR_UNSET else template
        predicate = definition.source_filter if source_filter is _DECORATOR_UNSET else source_filter
        if not callable(factory) or inspect.iscoroutinefunction(factory) or inspect.isasyncgenfunction(factory):
            raise TypeError("template must be a synchronous callable")
        if not callable(predicate):
            raise TypeError("source_filter must be callable")
        patched = replace(
            definition,
            for_each=definition.for_each if for_each is _DECORATOR_UNSET else _composition_type(for_each),
            template=factory,
            source_filter=predicate,
        )
        self._decorator_templates = [item for item in self._decorator_templates if item.id != template_id]
        self._decorator_templates.append(patched)

    def remove_decorator_template(self, template_id: str) -> None:
        self._assert_mutable()
        if self._find_decorator_template(template_id) is None:
            raise KeyError(template_id)
        self._decorator_templates = [item for item in self._decorator_templates if item.id != template_id]
        self._removed_template_ids.add(template_id)

    _register_decorator_template = register_decorator_template
    _patch_decorator_template = patch_decorator_template
    _remove_decorator_template = remove_decorator_template

    def _expand_decorator_templates(self, *, build_args: Mapping[str, Any] | None = None) -> _TemplateExpansion:
        """Inspect source expansion independently of generated target compilation."""
        self._assert_mutable()
        parent = getattr(self, "_parent", None)
        inherited = (
            ()
            if parent is None
            else tuple(
                replace(boundary, root_layer_offset=boundary.root_layer_offset + 1)
                for boundary in parent._plan.blueprint.boundaries
            )
        )
        blueprint = _Blueprint(
            (self._layer(), *(() if parent is None else parent._plan.blueprint.layers)),
            (*self._boundaries, *inherited),
        )
        arguments = self._effective_build_args(build_args)
        prepared = _prepare_boundary_visibility(_normalize_blueprint_aliases(blueprint), build_args=arguments)
        return _expand_decorator_templates(
            prepared,
            build_args=arguments,
            anchored_singleton_steps=None if parent is None else _anchored_singletons(parent._plan),
            anchored_pre_configuration_steps=None if parent is None else _anchored_pre_configurations(parent._plan),
            anchored_owner_tokens=frozenset() if parent is None else frozenset(parent._owners),
            inherited_parameter_explanations=types.MappingProxyType({})
            if parent is None
            else parent._plan.parameter_explanations,
            inherited_generic_explanations=types.MappingProxyType({})
            if parent is None
            else parent._plan.generic_explanations,
        )

    def register_decorator(
        self,
        service_type: Any,
        decorator_type: TypeForm[Any] | Callable[..., Any],
        *,
        when: ComponentFilter = all_components,
        decorated_arg: str | None = None,
        arguments: Mapping[str, Any] | None = None,
        position: int = 0,
        name: str | None = None,
        tags: Iterable[legacy.Tag] | None = None,
    ) -> str:
        self._assert_mutable()
        service_type = _composition_type(service_type)
        decorator_type = _composition_type(decorator_type)
        decorator_id = str(uuid4())
        self._decorators.append(
            _DecoratorDefinition(
                id=decorator_id,
                service_type=service_type,
                decorator_type=decorator_type,
                decorated_arg=decorated_arg,
                arguments=types.MappingProxyType(dict(arguments or {})),
                position=position,
                order=self._new_decorator_order(),
                when=when,
                name=name,
                tags=tuple(tags or ()),
                origin=self._definition_origin("decorator", decorator_id),
            )
        )
        return decorator_id

    def _find_decorator_definition(
        self,
        service_type: Any,
        decorator_id: str,
    ) -> _DecoratorDefinition | None:
        service_type = _composition_type(service_type)
        own = next(
            (
                definition
                for definition in reversed(self._decorators)
                if definition.id == decorator_id and _composition_type(definition.service_type) == service_type
            ),
            None,
        )
        if own is not None:
            return own
        parent = getattr(self, "_parent", None)
        if parent is None:
            return None
        return parent._plan.blueprint.decorator_definition(service_type, decorator_id)

    def patch_decorator(
        self,
        service_type: Any,
        decorator_id: str,
        *,
        decorated_arg: str | None | object = _DECORATOR_UNSET,
        arguments: Mapping[str, Any] | None = None,
        position: int | object = _DECORATOR_UNSET,
        when: ComponentFilter | None = None,
        name: str | None | object = _DECORATOR_UNSET,
        tags: Iterable[legacy.Tag] | None = None,
    ) -> None:
        self._assert_mutable()
        service_type = _composition_type(service_type)
        definition = self._find_decorator_definition(service_type, decorator_id)
        if definition is None:
            raise KeyError(f"No decorator found for {service_type} with ID {decorator_id}")

        dependencies = dict(definition.arguments)
        if arguments is not None:
            for argument, setting in arguments.items():
                if setting is REMOVE:
                    dependencies.pop(argument, None)
                else:
                    dependencies[argument] = setting

        patched = replace(
            definition,
            decorated_arg=(
                definition.decorated_arg if decorated_arg is _DECORATOR_UNSET else cast(str | None, decorated_arg)
            ),
            arguments=types.MappingProxyType(dependencies),
            position=definition.position if position is _DECORATOR_UNSET else cast(int, position),
            when=definition.when if when is None else when,
            name=definition.name if name is _DECORATOR_UNSET else cast(str | None, name),
            tags=definition.tags if tags is None else tuple(tags),
        )
        for index, candidate in enumerate(self._decorators):
            if candidate.id == decorator_id:
                self._decorators[index] = patched
                break
        else:
            self._decorators.append(patched)
        self._removed_decorator_ids.discard(decorator_id)

    def remove_decorator(self, service_type: Any, decorator_id: str) -> None:
        self._assert_mutable()
        service_type = _composition_type(service_type)
        if self._find_decorator_definition(service_type, decorator_id) is None:
            raise KeyError(f"No decorator found for {service_type} with ID {decorator_id}")
        self._decorators = [definition for definition in self._decorators if definition.id != decorator_id]
        self._removed_decorator_ids.add(decorator_id)

    def pre_configure(
        self,
        service_type: TypeForm[Any] | Iterable[TypeForm[Any]],
        configuration_function: Callable[..., Any],
        *,
        when: ComponentFilter = all_components,
        arguments: Mapping[str, Any] | None = None,
        continue_on_failure: bool = False,
    ) -> str:
        self._assert_mutable()
        service_types = (
            tuple(service_type)
            if (
                isinstance(service_type, Iterable)
                and not isinstance(service_type, type)
                and get_origin(service_type) is None
            )
            else (service_type,)
        )
        service_types = tuple(dict.fromkeys(_composition_type(value) for value in service_types))
        if not service_types:
            raise ValueError("pre_configure() requires at least one service type")
        definition_id = str(uuid4())
        self._pre_configurations.append(
            _PreConfigurationDefinition(
                id=definition_id,
                service_types=service_types,
                configuration_fn=configuration_function,
                arguments=types.MappingProxyType(dict(arguments or {})),
                order=self._new_pre_configuration_order(),
                when=when,
                continue_on_failure=continue_on_failure,
                origin=self._definition_origin("pre-configuration", definition_id),
            )
        )
        self._pre_configuration_states[definition_id] = _PreConfigurationState()
        return definition_id

    def declare_scope_slot(self, service_type: TypeForm[Any], name: str | None = None) -> _BuilderBase:
        self._assert_mutable()
        service_type = _composition_type(service_type)
        slot = (service_type, name)
        self._slots.add(slot)
        self._slot_origins.setdefault(slot, self._definition_origin("scope-slot", None))
        return self

    def mark_entrypoint(
        self,
        service_type: Any,
        *,
        filter: ComponentFilter = default_component_filter,
    ) -> _BuilderBase:
        """Mark a public resolution request for graph and reachability tooling."""

        self._assert_mutable()
        service_type = _composition_type(service_type)
        self._entrypoints.append(
            _EntryPoint(
                service_type,
                filter,
                self._definition_origin("entrypoint", None),
            )
        )
        return self

    def register_subclasses(
        self,
        base_type: type,
        *,
        ensure_import_modules: str | Iterable[str] = (),
        include_children: bool = False,
        lifespan: Lifespan = "per_resolution",
        subclass_type_filter: Callable[[type], bool] = legacy.always_true,
        name: str | None = None,
        tags: Iterable[legacy.Tag] | None = None,
        when: ComponentFilter = all_components,
        groups: Iterable[ServiceGroup] = (),
    ) -> None:
        """Queue concrete subclass discovery for the next successful build.

        Declared module names are imported before any discovery rule takes its
        live subclass snapshot. ``include_children=True`` recursively imports
        discoverable children of declared packages.
        """

        self._assert_mutable()
        if not isinstance(include_children, bool):
            raise TypeError("include_children must be a bool")
        service_groups = _materialize_service_groups(groups)
        _validate_service_groups(base_type, service_groups)
        self._registration_discoveries.append(
            _RegistrationDiscovery(
                base_type=base_type,
                generic=False,
                fallback_type=None,
                ensure_import_modules=_module_imports(ensure_import_modules),
                include_children=include_children,
                lifespan=_legacy_lifespan(lifespan),
                subclass_type_filter=subclass_type_filter,
                name=name,
                tags=tuple(tags or ()),
                when=when,
                groups=service_groups,
                origin=self._definition_origin("registration", None),
            )
        )

    def register_generic_subclasses(
        self,
        generic_service_type: type,
        *,
        fallback_type: type | None = None,
        ensure_import_modules: str | Iterable[str] = (),
        include_children: bool = False,
        lifespan: Lifespan = "per_resolution",
        subclass_type_filter: Callable[[type], bool] = legacy.always_true,
        name: str | None = None,
        tags: Iterable[legacy.Tag] | None = None,
        when: ComponentFilter = all_components,
        groups: Iterable[ServiceGroup] = (),
    ) -> None:
        """Queue closed-generic subclass discovery for the build snapshot.

        Declared module names are imported before any discovery rule takes its
        live subclass snapshot. ``include_children=True`` recursively imports
        discoverable children of declared packages.
        """

        self._assert_mutable()
        if not isinstance(include_children, bool):
            raise TypeError("include_children must be a bool")
        service_groups = _materialize_service_groups(groups)
        _validate_service_groups(generic_service_type, service_groups)
        self._registration_discoveries.append(
            _RegistrationDiscovery(
                base_type=generic_service_type,
                generic=True,
                fallback_type=fallback_type,
                ensure_import_modules=_module_imports(ensure_import_modules),
                include_children=include_children,
                lifespan=_legacy_lifespan(lifespan),
                subclass_type_filter=subclass_type_filter,
                name=name,
                tags=tuple(tags or ()),
                when=when,
                groups=service_groups,
                origin=self._definition_origin("registration", None),
            )
        )

    def apply_bundle(self, bundle: Callable[[ComponentBuilder], None]) -> None:
        self._assert_mutable()
        self._bundle_stack.append(qualified_name(bundle))
        try:
            bundle(self)
        finally:
            self._bundle_stack.pop()

    def _preview_components(
        self,
        service_type: Any,
        build_args: Mapping[str, Any] | None = None,
    ) -> tuple[Component, ...]:
        self._assert_mutable()
        blueprint = _Blueprint((self._layer(),), tuple(self._boundaries))
        alias_errors = _blueprint_alias_errors(blueprint)
        if alias_errors:
            raise ContainerBuildError(report=_alias_error_report(alias_errors))
        try:
            service_type = normalize_type_alias(service_type)
            blueprint = _normalize_blueprint_aliases(blueprint)
        except TypeAliasNormalizationError as error:
            raise ContainerBuildError(report=_alias_error_report((error,))) from error
        plan = _compile_with_report(blueprint, build_args=self._effective_build_args(build_args), preview=True)
        roots = plan.roots.get(service_type, plan.provider_roots.get(service_type, ()))
        return tuple(item.component for item in roots)

    def has_component(
        self,
        service_type: Any,
        filter: ComponentFilter = default_component_filter,
        *,
        build_args: Mapping[str, Any] | None = None,
    ) -> bool:
        return any(filter(component) for component in self._preview_components(service_type, build_args))

    def get_component_ids(
        self,
        service_type: Any,
        *,
        filter: ComponentFilter = default_component_filter,
        build_args: Mapping[str, Any] | None = None,
    ) -> list[str]:
        components = [
            component for component in self._preview_components(service_type, build_args) if filter(component)
        ]
        return [component.id for component in components]

    def get_component_id(
        self,
        service_type: Any,
        *,
        filter: ComponentFilter = default_component_filter,
        build_args: Mapping[str, Any] | None = None,
    ) -> str | None:
        return next(
            iter(self.get_component_ids(service_type, filter=filter, build_args=build_args)),
            None,
        )


class ContainerBuilder(_BuilderBase):
    """Mutable root composition API. Call :meth:`build` exactly once."""

    def install_boundary(self, boundary: Boundary) -> None:
        """Install an isolated boundary blueprint for the next build."""

        self._install_boundary(boundary)

    def build(self, *, build_args: Mapping[str, Any] | None = None) -> Container:
        self._assert_mutable()
        plan = _compile_with_report(
            _Blueprint((self._layer(),), tuple(self._boundaries)),
            build_args=self._effective_build_args(build_args),
        )
        container = Container(plan, self._owner_token)
        self._built = True
        return container


class ScopeBuilder(_BuilderBase):
    """Compile a child scope with registrations layered over a runtime parent."""

    def __init__(self, parent: Scope):
        super().__init__()
        self._parent = parent
        self._bundle_container_id = parent.container._owned_token

    def install_boundary(self, boundary: Boundary) -> None:
        """Install a new overlay-owned boundary without reopening a parent."""

        self._install_boundary(boundary)

    def build(self, *, build_args: Mapping[str, Any] | None = None) -> Scope:
        self._assert_mutable()
        self._parent._ensure_open()
        inherited_boundaries = tuple(
            replace(boundary, root_layer_offset=boundary.root_layer_offset + 1)
            for boundary in self._parent._plan.blueprint.boundaries
        )
        blueprint = _Blueprint(
            (self._layer(), *self._parent._plan.blueprint.layers),
            (*self._boundaries, *inherited_boundaries),
        )
        plan = _compile_with_report(
            blueprint,
            build_args=self._effective_build_args(build_args),
            anchored_singleton_steps=_anchored_singletons(self._parent._plan),
            anchored_pre_configuration_steps=_anchored_pre_configurations(self._parent._plan),
            anchored_owner_tokens=frozenset(self._parent._owners),
            inherited_parameter_explanations=self._parent._plan.parameter_explanations,
            inherited_generic_explanations=self._parent._plan.generic_explanations,
        )
        scope = Scope(
            plan,
            container=self._parent.container,
            parent=self._parent,
            owners=self._parent._owners,
            owned_token=self._owner_token,
            inherit_scoped=False,
        )
        self._built = True
        return scope


class _BoundaryBuilder(_BuilderBase):
    """Private ComponentBuilder used while applying a Boundary root bundle."""

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._bundle_run_claims: list[tuple[set[tuple[BundleRunScope, str]], tuple[BundleRunScope, str]]] = []

    def _rollback_bundle_runs(self) -> None:
        for history, key in reversed(self._bundle_run_claims):
            history.discard(key)
