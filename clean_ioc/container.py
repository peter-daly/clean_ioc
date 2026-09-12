"""Build-time composition and graph-free runtime for Clean IoC."""

from __future__ import annotations

import asyncio
import concurrent.futures
import copy
import inspect
import logging
import os
import re
import threading
import types
import typing
from collections import defaultdict, deque
from collections.abc import Callable, Hashable, Iterable, Iterator, Mapping
from dataclasses import dataclass, field, replace
from typing import Any, TypeVar, cast, get_args, get_origin
from uuid import UUID, uuid4, uuid5

from typetoolbox.generics import GenericTypeMap, get_generic_mapping
from typing_extensions import TypeForm

from . import _legacy as legacy
from . import registration_patterns as patterns
from ._legacy_configuration import default_parameter_value_factory
from .arguments import (
    INJECT,
    REMOVE,
    ParameterContext,
    _DerivedArgument,
    _FixedArgument,
    _SelectArgument,
)
from .boundaries import Boundary, Expose, Use
from .components import (
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
    all_components,
    default_component_filter,
    normalize_implementation_type,
)
from .generic_utils import constructor_type
from .generic_utils import resolve_typevar_bindings as _resolve_factory_typevars
from .providers import AsyncProvider, Provider
from .tooling import (
    BuildIssue,
    BuildReport,
    CandidateDecision,
    CompilationExplanation,
    CompiledGraph,
    DecisionOutcome,
    DefinitionOrigin,
    GraphRoot,
    IssueSeverity,
    SourceLocation,
    ValidationContext,
    ValidationRule,
    _CandidateRecord,
    qualified_name,
)
from .type_aliases import TypeAliasNormalizationError, alias_label, is_new_type, normalize_type_alias

TService = TypeVar("TService")

logger = logging.getLogger(__name__)

_EMPTY_BUILD_ARGS: Mapping[str, Any] = types.MappingProxyType({})
_PACKAGE_DIRECTORY = os.path.dirname(os.path.abspath(__file__))


def _composition_type(value: Any) -> Any:
    """Canonicalize an available alias while retaining unresolved declarations for build."""

    try:
        return normalize_type_alias(value)
    except TypeAliasNormalizationError:
        return value


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
    ):
        self.report = report
        self.code = code
        self.path = path
        self.explanations = explanations
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
    key: Callable[[Component], Hashable]
    component_filter: ComponentFilter


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
    pattern_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class _VisibilityTarget:
    source: str | None
    service_type: Any
    registration_id: str | None
    name: str | None
    tags: tuple[legacy.Tag, ...]
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
        visible_ids: list[str] = []
        if area is None:
            visible_ids.extend(
                target.registration_id
                for boundary in self.boundaries
                for target in boundary.resolved_exposes
                if target.registration_id is not None and _service_definition_matches(target.service_type, service_type)
            )
        else:
            boundary = self.boundary(area)
            if boundary is not None:
                visible_ids.extend(
                    target.registration_id
                    for target in boundary.resolved_uses
                    if not target.slot
                    and target.registration_id is not None
                    and _service_definition_matches(target.service_type, service_type)
                )
        seen = {registration.id for registration, _ in found}
        for component_id in visible_ids:
            if component_id in seen:
                continue
            candidate = self.registration_definition(component_id)
            if candidate is not None:
                found.append(candidate)
                seen.add(component_id)
        return found

    def registration_definition(self, component_id: str) -> tuple[legacy._Registration, _Layer] | None:
        for layer in (*self.layers, *(boundary.layer for boundary in self.boundaries)):
            for registrations in layer.registry._registrations.values():
                for registration in registrations:
                    if registration.id == component_id and registration.id not in layer.internal_ids:
                        return registration, layer
        return None

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
                replace(expose, service_type=normalize_type_alias(expose.service_type)) for expose in boundary.exposes
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
        for definition in layer.decorators:
            values.extend((definition.service_type, definition.decorator_type))
        for definition in layer.pre_configurations:
            values.extend(definition.service_types)
        values.extend(service_type for service_type, _ in layer.slots)
        values.extend(entrypoint.service_type for entrypoint in layer.entrypoints)
    for boundary in blueprint.boundaries:
        values.extend(use.service_type for use in boundary.uses)
        values.extend(expose.service_type for expose in boundary.exposes)
    for value in values:
        try:
            normalize_type_alias(value)
        except TypeAliasNormalizationError as error:
            errors.append(error)
    unique = {(error.code, str(error)): error for error in errors}
    return tuple(unique.values())


def _alias_error_report(errors: Iterable[TypeAliasNormalizationError]) -> BuildReport:
    return BuildReport(
        tuple(
            BuildIssue(
                code=error.code,
                severity=IssueSeverity.error,
                message=str(error),
                root=None,
                path=(alias_label(error.alias),),
            )
            for error in errors
        ),
        checked_roots=0,
    )


_BOUNDARY_NAME = re.compile(r"^[a-z][a-z0-9_-]*$")


def _service_definition_matches(definition: Any, request: Any) -> bool:
    if definition == request:
        return True
    request_origin = get_origin(request)
    if request_origin is None:
        return False
    if definition == request_origin:
        return True
    return get_origin(definition) == request_origin and bool(_typevars_in(definition))


def _boundary_component(
    registration: legacy._Registration,
    *,
    service_type: Any,
    build_args: Mapping[str, Any],
    boundary: str | None,
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
            name=registration.name,
            tags=tuple(registration.tags),
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
        for declaration in (*boundary.exposes, *boundary.uses):
            if patterns.variables(declaration.service_type) and any(
                candidate is not None and get_origin(candidate[0].service_type) == get_origin(declaration.service_type)
                for layer in (*blueprint.layers, *(item.layer for item in blueprint.boundaries))
                for component_id in layer.pattern_ids
                for candidate in (blueprint.registration_definition(component_id),)
            ):
                raise ContainerBuildError(
                    "Structural templates cross Boundaries only through explicitly closed Expose/Use declarations",
                    code="pattern-unsupported-exposure",
                    path=(boundary.name, qualified_name(declaration.service_type)),
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
            _VisibilityTarget(
                boundary.name,
                exposure.service_type,
                registration.id,
                registration.name,
                tuple(registration.tags),
            )
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
                        replace(target, source=source.name, service_type=use.service_type)
                        for target in source.resolved_exposes
                        if _service_definition_matches(target.service_type, use.service_type)
                    )
        provisional_uses.append(replace(boundary, resolved_uses=tuple(targets)))
    blueprint = replace(blueprint, boundaries=tuple(provisional_uses))

    resolved: list[_BoundaryBlueprint] = []
    # Exposures are local-only, so all can be resolved before any Use.
    for boundary in blueprint.boundaries:
        targets: list[_VisibilityTarget] = []
        selected_ids: set[str] = set()
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
            if registration.id in selected_ids:
                raise ContainerBuildError(
                    f"Boundary {boundary.name!r} exposes the same component more than once",
                    code="boundary-expose-ambiguous",
                    path=(boundary.name, qualified_name(exposure.service_type)),
                )
            selected_ids.add(registration.id)
            targets.append(
                _VisibilityTarget(
                    boundary.name,
                    exposure.service_type,
                    registration.id,
                    registration.name,
                    tuple(registration.tags),
                )
            )
        resolved.append(replace(boundary, resolved_exposes=tuple(targets)))
    blueprint = replace(blueprint, boundaries=tuple(resolved))

    completed: list[_BoundaryBlueprint] = []
    for boundary in blueprint.boundaries:
        targets: list[_VisibilityTarget] = []
        selected_keys: set[tuple[str | None, str | None, bool]] = set()
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
                    if _service_definition_matches(target.service_type, use.service_type)
                ]
                selected: list[_VisibilityTarget] = []
                for target in exposure_targets:
                    definition = blueprint.registration_definition(cast(str, target.registration_id))
                    if definition is None:
                        continue
                    registration, layer = definition
                    try:
                        component = _compiled_boundary_component(
                            blueprint,
                            registration,
                            layer,
                            service_type=use.service_type,
                            build_args=build_args,
                        )
                    except ContainerBuildError:
                        component = _boundary_component(
                            registration,
                            service_type=use.service_type,
                            build_args=build_args,
                            boundary=blueprint.registration_area(layer),
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
                target = replace(selected_target, source=source.name, service_type=use.service_type)
            key = (target.source, target.registration_id or target.name, target.slot)
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
            f"Conflicting TypeVar {name!r} for factory {factory!r} while compiling "
            f"{service_type!r}: {existing!r} != {value!r}"
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
) -> dict[str, legacy.Dependency]:
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
            f"Unsupported generic factory type parameter(s) {names} for factory {factory!r}; "
            "only TypeVar is supported"
        )
    typevars = {item.__name__: item for annotation in annotations for item in _typevars_in(annotation)}
    if not typevars:
        return registration.dependencies

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
                f"Invalid factory_specialization {explicit_specialization!r} for factory {factory!r}"
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
            f"Unable to resolve TypeVar(s) {names} for factory {factory!r} while compiling {service_type!r}; "
            "register a closed generic service or pass factory_specialization="
        )

    dependencies: dict[str, legacy.Dependency] = {}
    for name, dependency in registration.dependencies.items():
        specialized = legacy.Dependency(
            name=dependency.name,
            parent_implementation=factory,
            service_type=_resolve_factory_typevars(dependency.service_type, bindings),
            settings=dependency.settings,
            default_value=dependency.default_value,
        )
        specialized.declared_service_type = _resolve_factory_typevars(dependency.declared_service_type, bindings)
        dependencies[name] = specialized
    return dependencies


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


@dataclass(slots=True)
class _RegistrationDiscovery:
    base_type: type
    generic: bool
    fallback_type: type | None
    lifespan: legacy.Lifespan
    subclass_type_filter: Callable[[type], bool]
    name: str | None
    tags: tuple[legacy.Tag, ...]
    when: ComponentFilter
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
    ) -> None:
        for subclass in _unique_subclasses(self.base_type, self._filter):
            service_type: Any = self.base_type
            if self.generic:
                service_type = legacy.Container._get_target_generic_base(self.base_type, subclass)
                if service_type is None:
                    continue
            registration = self._registration_for(subclass, service_type)
            _index_registration(registry, registration)
            registration_when[registration.id] = self.when
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
    ):
        self.blueprint = blueprint
        self.build_args = build_args
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
        self._pattern_requests: dict[Any, None] = {}
        self._compiled_pre_configurations: dict[str, _CompiledPreConfiguration] = {}
        self._compiling_pre_configurations: set[str] = set()
        self._anchored_singletons = anchored_singletons or {}
        self._anchored_pre_configurations = anchored_pre_configurations or {}
        self._anchored_owner_tokens = anchored_owner_tokens
        self._area: str | None = None
        self.issues: list[BuildIssue] = []
        self.root_candidates: dict[Any, tuple[_CandidateRecord, ...]] = {}
        self.occurrence_explanations: dict[int, CompilationExplanation] = {}
        self.origins: dict[int, DefinitionOrigin] = {}
        self.decision_history: list[CompilationExplanation] = []

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

    def compile(
        self,
        service_types: Iterable[Any] | None = None,
        *,
        area: str | None = None,
        include_boundaries: bool = True,
    ) -> _PlanSet:
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
            if self._patterns and area is None:
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
                    specialized_dependency = legacy.Dependency(
                        name=dependency.name,
                        parent_implementation=factory,
                        service_type=_resolve_factory_typevars(dependency.service_type, bindings),
                        settings=dependency.settings,
                        default_value=dependency.default_value,
                    )
                    specialized_dependency.declared_service_type = _resolve_factory_typevars(
                        dependency.declared_service_type, bindings
                    )
                    dependencies[name] = specialized_dependency
            except patterns.PatternError as error:
                raise ContainerBuildError(
                    str(error), code=error.code, path=self._current_path(requested_service_type)
                ) from error
        else:
            dependencies = _specialized_factory_dependencies(
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
        self._specialized_factories[key] = specialized
        if is_pattern:
            self._pattern_sources[specialized.id] = registration.id
        return specialized

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
    ) -> list[_CompiledCandidate]:
        service_type = normalize_type_alias(service_type)
        registrations = self.blueprint.registrations(service_type, self._area)
        candidates: list[_CompiledCandidate] = []
        if self._patterns:
            registrations, candidates = self._pattern_candidates(service_type, registrations)
        if not registrations and get_origin(service_type) is not None:
            registrations = self.blueprint.registrations(get_origin(service_type), self._area)
        for source_registration, layer in registrations:
            origin = self.blueprint.registration_origin(source_registration.id, layer)
            try:
                registration = self._specialize_factory(source_registration, layer, service_type)
            except ContainerBuildError as error:
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
            consumer_area = self._area
            definition_area = self.blueprint.registration_area(layer)
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
                    requested_service_type=service_type,
                    origin=origin,
                )
            except ContainerBuildError as error:
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
            boundary_code, boundary_reason = self.blueprint.visibility_reason(
                consumer_area, source_registration.id, layer
            )
            codes: list[str] = ["registration-eligible"]
            if source_registration.id in layer.pattern_ids:
                codes.append("selected-registration-pattern")
            if boundary_code:
                codes.append(boundary_code)
            reasons = [boundary_reason, "the contextual filter matched"]
            if source_registration.service_type != service_type and (
                get_origin(service_type) is not None
                or bool(getattr(source_registration.service_type, "__parameters__", ()))
            ):
                codes.append("specialized-generic")
                reasons.append(
                    f"specialized {qualified_name(source_registration.service_type)} "
                    f"for {qualified_name(service_type)}"
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
        for candidate in considered:
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
            path = " -> ".join(str(item.service_type) for item in (*self._stack, registration))
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
            decorators = self._compile_decorators(registration, component)
            # Component inspection presents the final pipeline outside-to-inside,
            # while runtime activation retains the core-to-outside order.
            draft.decorator_ids = tuple(item.component.occurrence_id for item in reversed(decorators))
            step_type = _REGISTRATION_STEP_TYPES[registration.lifespan] if map_definition is None else _ProviderMapStep
            step = step_type(
                registration=registration,
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
        candidates = self._compile_candidates(target, component, None, deferred_mode=mode)
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
            try:
                key = callback(target_component)
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

        dependencies = tuple(
            self._clone_component_tree(child, parent=component, mapped=mapping) for child in source.dependencies
        )
        draft.dependency_ids = tuple(child.occurrence_id for child in dependencies)
        configurations = tuple(
            self._clone_component_tree(child, parent=component, mapped=mapping) for child in source.pre_configurations
        )
        draft.pre_configuration_ids = tuple(child.occurrence_id for child in configurations)
        decorators = tuple(
            self._clone_component_tree(child, parent=parent, mapped=mapping) for child in source.decorators
        )
        draft.decorator_ids = tuple(child.occurrence_id for child in decorators)
        for source_decorator, decorator in zip(source.decorators, decorators, strict=True):
            decorated = source_decorator.decorated
            if decorated is not None and decorated.occurrence_id in mapping:
                decorator_draft = cast(_ComponentDraft, self.graph.record(decorator.occurrence_id))
                decorator_draft.decorated_id = mapping[decorated.occurrence_id].occurrence_id
        return component

    def _compile_dependencies(
        self,
        dependencies: dict[str, legacy.Dependency],
        parent: Component,
    ) -> tuple[_CompiledDependency, ...]:
        compiled: list[_CompiledDependency] = []
        child_ids: list[int] = []
        for name, dependency in dependencies.items():
            step, child = self._compile_dependency(dependency, parent)
            compiled.append(_CompiledDependency(name, step))
            if child is not None:
                child_ids.append(child.occurrence_id)
        record = cast(_ComponentDraft, self.graph.record(parent.occurrence_id))
        record.dependency_ids = tuple(child_ids)
        return tuple(compiled)

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
                raise ContainerBuildError(
                    f"Could not derive argument {dependency.name!r} for "
                    f"{qualified_name(parent.implementation)}: {error}",
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
            f"No component for {dependency.service_type!r}, argument {dependency.name!r} of {parent.implementation!r}"
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
        for definition, layer in definitions:
            try:
                matched = definition.when(parent)
            except Exception as error:
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
            existing = self._compiled_pre_configurations.get(definition.id)
            if existing is not None:
                items.append(existing)
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
        core: Component,
    ) -> tuple[_CompiledDecorator, ...]:
        # Applicability is deliberately evaluated against the completed,
        # undecorated core subtree before any decorator dependencies are added.
        selected: list[_DecoratorDefinition] = []
        decisions: list[CandidateDecision] = []
        for decorator, _ in self.blueprint.decorators(core.service_type, self._area):
            try:
                matched = decorator.when(core)
            except Exception as error:
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
                decorator = _materialize_decorator(definition, core.service_type, core.implementation_type)
            except ContainerBuildError as error:
                raise ContainerBuildError(
                    str(error),
                    code="invalid-decorator",
                    path=self._current_path(core.service_type),
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
                    (step.registration.id, _runtime_type_key(step.component.service_type)),
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
    message = str(error).lower()
    if "no component" in message:
        return "missing-component"
    if "circular" in message:
        return "circular-dependency"
    if "cannot retain scoped" in message:
        return "captive-dependency"
    if "typevar" in message or "generic" in message or "specialization" in message:
        return "generic-specialization"
    if "decorator" in message:
        return "invalid-decorator"
    if "parent-owned singleton" in message:
        return "overlay-singleton"
    return "compile-error"


def _error_report(
    blueprint: _Blueprint,
    original: BaseException,
    *,
    build_args: Mapping[str, Any] = _EMPTY_BUILD_ARGS,
    anchored_singleton_steps: dict[tuple[str, tuple[Any, ...]], _RegistrationStep] | None = None,
    anchored_pre_configuration_steps: dict[str, _CompiledPreConfiguration] | None = None,
    anchored_owner_tokens: frozenset[str] = frozenset(),
) -> BuildReport:
    issues: list[BuildIssue] = []
    seen: set[tuple[str, str, str]] = set()
    checked = 0
    areas = (
        (None, blueprint.root_service_types()),
        *((boundary.name, blueprint.service_types(boundary.name)) for boundary in blueprint.boundaries),
    )
    for area, service_types in areas:
        for service_type in service_types:
            if getattr(service_type, "__parameters__", ()):
                continue
            checked += 1
            try:
                _Compiler(
                    blueprint,
                    build_args=build_args,
                    anchored_singletons=anchored_singleton_steps,
                    anchored_pre_configurations=anchored_pre_configuration_steps,
                    anchored_owner_tokens=anchored_owner_tokens,
                ).compile((service_type,), area=area, include_boundaries=False)
            except Exception as error:
                root = qualified_name(service_type)
                code = _build_error_code(error)
                key = (code, root, str(error))
                if key in seen:
                    continue
                seen.add(key)
                issues.append(
                    BuildIssue(
                        code=code,
                        severity=IssueSeverity.error,
                        message=str(error),
                        root=root,
                        path=(error.path if isinstance(error, ContainerBuildError) and error.path else (root,)),
                    )
                )
    if not issues:
        message = str(original)
        issues.append(
            BuildIssue(
                code=_build_error_code(original),
                severity=IssueSeverity.error,
                message=message,
            )
        )
    return BuildReport(tuple(issues), checked_roots=checked)


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
                    "tags": [
                        {"name": tag.name, "value": tag.value}
                        for tag in sorted(target.tags, key=lambda item: (item.name, item.value or ""))
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
                    "tags": [
                        {"name": tag.name, "value": tag.value}
                        for tag in sorted(target.tags, key=lambda item: (item.name, item.value or ""))
                    ],
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
        _occurrence_layers=types.MappingProxyType(dict(plan.occurrence_layers)),
    )
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


def _compile_with_report(
    blueprint: _Blueprint,
    *,
    build_args: Mapping[str, Any] = _EMPTY_BUILD_ARGS,
    anchored_singleton_steps: dict[tuple[str, tuple[Any, ...]], _RegistrationStep] | None = None,
    anchored_pre_configuration_steps: dict[str, _CompiledPreConfiguration] | None = None,
    anchored_owner_tokens: frozenset[str] = frozenset(),
) -> _PlanSet:
    alias_errors = _blueprint_alias_errors(blueprint)
    if alias_errors:
        raise ContainerBuildError(report=_alias_error_report(alias_errors))
    try:
        blueprint = _normalize_blueprint_aliases(blueprint)
        blueprint = _prepare_boundary_visibility(blueprint, build_args=build_args)
    except TypeAliasNormalizationError as error:
        raise ContainerBuildError(report=_alias_error_report((error,))) from error
    except ContainerBuildError as error:
        issue = BuildIssue(
            code=error.code or "compile-error",
            severity=IssueSeverity.error,
            message=str(error),
            root=(error.path[0] if error.path else None),
            path=error.path,
        )
        raise ContainerBuildError(report=BuildReport((issue,), checked_roots=0)) from error
    compiler = _Compiler(
        blueprint,
        build_args=build_args,
        anchored_singletons=anchored_singleton_steps,
        anchored_pre_configurations=anchored_pre_configuration_steps,
        anchored_owner_tokens=anchored_owner_tokens,
    )
    try:
        plan = compiler.compile()
        return _finalize_plan(plan)
    except ContainerBuildError as error:
        if error.report is not None:
            raise ContainerBuildError(
                report=error.report,
                explanations=tuple(compiler.decision_history),
            ) from error
        report = _error_report(
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
        ) from error
    except Exception as error:
        report = _error_report(
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
        self._boundary_name = boundary_name
        self._composition_layer = composition_layer
        self._registration_when: dict[str, ComponentFilter] = {}
        self._registration_origins: dict[str, DefinitionOrigin] = {}
        self._factory_ids: set[str] = set()
        self._factory_specializations: dict[str, object] = {}
        self._provider_maps: dict[str, _ProviderMapDefinition] = {}
        self._pattern_ids: list[str] = []
        self._decorators: list[_DecoratorDefinition] = []
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
        if self._built:
            raise BuilderAlreadyBuiltError("Builders are single-use after a successful build")

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

        discovered = legacy._Registry()
        for rule in self._registration_discoveries:
            rule.materialize(discovered, registration_when, registration_origins)
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
            pattern_ids=tuple(self._pattern_ids),
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
        private.apply_bundle(boundary.root_bundle)
        self._boundaries.append(
            _BoundaryBlueprint(
                name=boundary.name,
                layer=private._layer(),
                uses=tuple(boundary.uses),
                exposes=tuple(boundary.exposes),
            )
        )

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
    ) -> str:
        """Declare a structural factory template specialized only during build."""
        if not callable(factory):
            raise TypeError("register_pattern requires a callable factory")
        component_id = self.register(
            service_type, factory=factory, lifespan=lifespan, name=name, arguments=arguments, tags=tags, when=when
        )
        self._pattern_ids.append(component_id)
        self._registration_origins[component_id] = self._definition_origin("registration-pattern", component_id)
        return component_id

    def register_provider_map(
        self,
        service_type: TypeForm[Any],
        *,
        key: Callable[[Component], Hashable],
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
        provider_type = AsyncProvider if asynchronous else Provider
        annotation: Any = types.GenericAlias(Mapping, (key_type, provider_type[service_type]))
        component_id = self.register(annotation, factory=_provider_map_factory, lifespan="transient", name=name)
        self._factory_ids.discard(component_id)
        self._provider_maps[component_id] = _ProviderMapDefinition(key, component_filter)
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
        lifespan: Lifespan = "per_resolution",
        subclass_type_filter: Callable[[type], bool] = legacy.always_true,
        name: str | None = None,
        tags: Iterable[legacy.Tag] | None = None,
        when: ComponentFilter = all_components,
    ) -> None:
        """Queue concrete subclass discovery for the next successful build."""

        self._assert_mutable()
        self._registration_discoveries.append(
            _RegistrationDiscovery(
                base_type=base_type,
                generic=False,
                fallback_type=None,
                lifespan=_legacy_lifespan(lifespan),
                subclass_type_filter=subclass_type_filter,
                name=name,
                tags=tuple(tags or ()),
                when=when,
                origin=self._definition_origin("registration", None),
            )
        )

    def register_generic_subclasses(
        self,
        generic_service_type: type,
        *,
        fallback_type: type | None = None,
        lifespan: Lifespan = "per_resolution",
        subclass_type_filter: Callable[[type], bool] = legacy.always_true,
        name: str | None = None,
        tags: Iterable[legacy.Tag] | None = None,
        when: ComponentFilter = all_components,
    ) -> None:
        """Queue closed-generic subclass discovery for the build snapshot."""

        self._assert_mutable()
        self._registration_discoveries.append(
            _RegistrationDiscovery(
                base_type=generic_service_type,
                generic=True,
                fallback_type=fallback_type,
                lifespan=_legacy_lifespan(lifespan),
                subclass_type_filter=subclass_type_filter,
                name=name,
                tags=tuple(tags or ()),
                when=when,
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
        plan = _Compiler(
            _prepare_boundary_visibility(
                blueprint,
                build_args=self._effective_build_args(build_args),
            ),
            build_args=self._effective_build_args(build_args),
        ).compile()
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
