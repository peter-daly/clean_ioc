"""Build-time composition and graph-free runtime for Clean IoC."""

from __future__ import annotations

import asyncio
import concurrent.futures
import inspect
import logging
import threading
import types
import typing
from collections import defaultdict, deque
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field, replace
from typing import Any, TypeVar, cast, get_args, get_origin
from uuid import UUID, uuid4, uuid5

from typetoolbox.generics import GenericTypeMap, get_generic_mapping

from . import _legacy as legacy
from ._legacy_configuration import default_parameter_value_factory
from .arguments import (
    INJECT,
    REMOVE,
    ParameterContext,
    _DerivedArgument,
    _FixedArgument,
    _SelectArgument,
)
from .components import (
    Component,
    ComponentActivation,
    ComponentBuilder,
    ComponentFilter,
    ComponentKind,
    Lifespan,
    _ComponentDraft,
    _ComponentGraph,
    all_components,
    default_component_filter,
    normalize_implementation_type,
)
from .tooling import (
    BuildIssue,
    BuildReport,
    CompiledGraph,
    GraphRoot,
    IssueSeverity,
    qualified_name,
)

TService = TypeVar("TService")

logger = logging.getLogger(__name__)

_EMPTY_BUILD_ARGS: Mapping[str, Any] = types.MappingProxyType({})


_LEGACY_LIFESPANS: dict[Lifespan, legacy.Lifespan] = {
    "transient": legacy.Lifespan.transient,
    "once_per_graph": legacy.Lifespan.once_per_graph,
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
        parameters = inspect.signature(implementation).parameters
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
    ):
        self.report = report
        self.code = code
        self.path = path
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
        return next(
            (
                item
                for item in self._requests
                if item.request.service_type == service_type and item.request.filter is filter
            ),
            None,
        )

    def resolve(
        self,
        service_type: type[TService],
        filter: ComponentFilter = default_component_filter,
    ) -> TService:
        request = self._request(service_type, filter)
        if request is not None:
            return cast(TService, request.step.resolve(self._context))
        return cast(TService, self._context.resolve_root(service_type, filter))

    async def resolve_async(
        self,
        service_type: type[TService],
        filter: ComponentFilter = default_component_filter,
    ) -> TService:
        request = self._request(service_type, filter)
        if request is not None:
            return cast(TService, await request.step.resolve_async(self._context))
        return cast(TService, await self._context.resolve_root_async(service_type, filter))


_RESOLUTION_REQUESTS_ATTRIBUTE = "__clean_ioc_resolution_requests__"


@dataclass(frozen=True, slots=True)
class _ResolutionRequest:
    service_type: Any
    filter: ComponentFilter
    resolve_async: bool


@dataclass(frozen=True, slots=True)
class _EntryPoint:
    service_type: Any
    filter: ComponentFilter


@dataclass(frozen=True, slots=True)
class _DecoratorDefinition:
    id: str
    service_type: Any
    decorator_type: type | Callable[..., Any]
    decorated_arg: str | None
    arguments: Mapping[str, Any]
    position: int
    order: int
    when: ComponentFilter
    name: str | None
    tags: tuple[legacy.Tag, ...]


@dataclass(frozen=True, slots=True)
class _PreConfigurationDefinition:
    id: str
    service_types: tuple[Any, ...]
    configuration_fn: Callable[..., Any]
    arguments: Mapping[str, Any]
    order: int
    when: ComponentFilter
    continue_on_failure: bool


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
    factory_ids: frozenset[str]
    factory_specializations: dict[str, object]
    decorators: tuple[_DecoratorDefinition, ...]
    removed_decorator_ids: frozenset[str]
    pre_configurations: tuple[_PreConfigurationDefinition, ...]
    pre_configuration_states: dict[str, _PreConfigurationState]
    slots: frozenset[tuple[Any, str | None]]
    entrypoints: tuple[_EntryPoint, ...]


@dataclass(frozen=True, slots=True)
class _Blueprint:
    layers: tuple[_Layer, ...]

    @property
    def slots(self) -> frozenset[tuple[Any, str | None]]:
        return frozenset(slot for layer in self.layers for slot in layer.slots)

    @property
    def entrypoints(self) -> tuple[_EntryPoint, ...]:
        return tuple(entrypoint for layer in self.layers for entrypoint in layer.entrypoints)

    def registrations(self, service_type: Any) -> list[tuple[legacy._Registration, _Layer]]:
        found: list[tuple[legacy._Registration, _Layer]] = []
        seen: set[str] = set()
        for layer in self.layers:
            for registration in layer.registry.get_registrations(service_type):
                if registration.id in layer.internal_ids or registration.id in seen:
                    continue
                seen.add(registration.id)
                found.append((registration, layer))
        return found

    def decorators(self, service_type: Any) -> list[tuple[_DecoratorDefinition, _Layer]]:
        found: list[tuple[_DecoratorDefinition, _Layer, int]] = []
        removed: set[str] = set()
        seen: set[str] = set()
        for layer_index, layer in enumerate(self.layers):
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
            (definition for definition, _ in self.decorators(service_type) if definition.id == decorator_id),
            None,
        )

    def pre_configurations(self, service_type: Any) -> list[tuple[_PreConfigurationDefinition, _Layer]]:
        return [
            (configuration, layer)
            # Parent builders existed before their overlays, so initializer
            # declaration order proceeds from the root layer outwards.
            for layer in reversed(self.layers)
            for configuration in sorted(layer.pre_configurations, key=lambda item: item.order)
            if any(_decorator_service_matches(target, service_type) for target in configuration.service_types)
        ]

    def service_types(self) -> tuple[Any, ...]:
        values: list[Any] = []
        for layer in self.layers:
            for service_type, registrations in layer.registry._registrations.items():
                if any(registration.id not in layer.internal_ids for registration in registrations):
                    values.append(service_type)
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


def _rebuild_type(annotation: Any, arguments: tuple[Any, ...]) -> Any:
    if not arguments:
        return annotation
    if isinstance(annotation, types.UnionType):
        result = arguments[0]
        for argument in arguments[1:]:
            result = result | argument
        return result
    copy_with = getattr(annotation, "copy_with", None)
    if callable(copy_with):
        return copy_with(arguments)
    target = get_origin(annotation) or annotation
    try:
        return target[arguments[0] if len(arguments) == 1 else arguments]
    except TypeError:
        return annotation


def _resolve_factory_typevars(
    annotation: Any,
    bindings: dict[str, Any],
    *,
    resolving: frozenset[str] = frozenset(),
) -> Any:
    if isinstance(annotation, TypeVar):
        name = annotation.__name__
        resolved = bindings.get(name, annotation)
        if resolved is annotation or name in resolving:
            return annotation
        return _resolve_factory_typevars(resolved, bindings, resolving=resolving | {name})
    if isinstance(annotation, list):
        return [_resolve_factory_typevars(item, bindings, resolving=resolving) for item in annotation]
    if isinstance(annotation, tuple):
        return tuple(_resolve_factory_typevars(item, bindings, resolving=resolving) for item in annotation)
    arguments = get_args(annotation)
    if not arguments:
        return annotation
    resolved_arguments = tuple(
        _resolve_factory_typevars(argument, bindings, resolving=resolving) for argument in arguments
    )
    return _rebuild_type(annotation, resolved_arguments)


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
    target = inspect.unwrap(factory)
    if inspect.isgeneratorfunction(target) or inspect.isasyncgenfunction(target):
        arguments = get_args(annotation)
        return arguments[0] if arguments else inspect.Signature.empty
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
        dependencies[name] = legacy.Dependency(
            name=dependency.name,
            parent_implementation=factory,
            service_type=_resolve_factory_typevars(dependency.service_type, bindings),
            settings=dependency.settings,
            default_value=dependency.default_value,
        )
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
            context.singleton_owner_stack.append(self.owner_token)
            try:
                self.activator_class.activate(
                    self.definition.configuration_fn,
                    values,
                    cast(Any, context),
                    legacy.Lifespan.singleton,
                )
            finally:
                context.singleton_owner_stack.pop()
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
            context.singleton_owner_stack.append(self.owner_token)
            try:
                await self.activator_class.activate_async(
                    self.definition.configuration_fn,
                    values,
                    cast(Any, context),
                    legacy.Lifespan.singleton,
                )
            finally:
                context.singleton_owner_stack.pop()
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
    if annotation == service_type:
        return True
    annotation_origin = get_origin(annotation)
    service_origin = get_origin(service_type)
    return annotation_origin is not None and annotation_origin == service_origin and bool(_typevars_in(annotation))


def _specialize_decorator_implementation(
    decorator_type: type | Callable[..., Any],
    bindings: dict[str, Any],
) -> type | Callable[..., Any]:
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
    sync_supported: bool

    def decorate(self, value: Any, context: _RuntimeResolutionContext, lifespan: legacy.Lifespan) -> Any:
        dependencies = {dependency.name: dependency.step.resolve(context) for dependency in self.dependencies}
        dependencies[self.source.decorated_arg] = value
        return self.source.activator_class.activate(
            self.source.implementation,
            dependencies,
            cast(Any, context),
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
            cast(Any, context),
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
            cast(Any, context),
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
            cast(Any, context),
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


class _OncePerGraphRegistrationStep(_RegistrationStep):
    __slots__ = ()

    def resolve(self, context: _RuntimeResolutionContext) -> Any:
        key = self.registration.id
        value = context.once_cache.get(key, _CACHE_MISS)
        if value is not _CACHE_MISS:
            return value
        context.assert_allowed(self)
        context.registration_stack.append(self)
        try:
            value = self._activate(context)
            context.once_cache[key] = value
            return value
        finally:
            context.registration_stack.pop()

    async def resolve_async(self, context: _RuntimeResolutionContext) -> Any:
        key = self.registration.id
        value = context.once_cache.get(key, _CACHE_MISS)
        if value is not _CACHE_MISS:
            return value
        context.assert_allowed(self)
        context.registration_stack.append(self)
        try:
            value = await self._activate_async(context)
            context.once_cache[key] = value
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
    legacy.Lifespan.once_per_graph: _OncePerGraphRegistrationStep,
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


def _requires_async(activator_class: type, implementation: Any) -> bool:
    if activator_class in (legacy.AsyncFactoryActivator, legacy.AsyncGeneratorActivator):
        return True
    wrapped = getattr(implementation, "__wrapped__", None)
    return wrapped is not None and (inspect.iscoroutinefunction(wrapped) or inspect.isasyncgenfunction(wrapped))


def _registration_activation(registration: legacy._Registration) -> ComponentActivation:
    if registration.is_instance:
        return ComponentActivation.instance
    if isinstance(registration.implementation, type):
        return ComponentActivation.constructor
    return ComponentActivation.factory


def _callable_activation(implementation: Any) -> ComponentActivation:
    return ComponentActivation.constructor if isinstance(implementation, type) else ComponentActivation.factory


def _manages_cleanup(activator_class: type, implementation: Any) -> bool:
    if activator_class in (legacy.GeneratorActivator, legacy.AsyncGeneratorActivator):
        return True
    wrapped = getattr(implementation, "__wrapped__", None)
    return wrapped is not None and (inspect.isgeneratorfunction(wrapped) or inspect.isasyncgenfunction(wrapped))


@dataclass(frozen=True, slots=True)
class _CompilerFrame:
    label: Any
    lifespan: legacy.Lifespan
    owner_token: str
    kind: ComponentKind


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
        self._compiled_pre_configurations: dict[str, _CompiledPreConfiguration] = {}
        self._compiling_pre_configurations: set[str] = set()
        self._anchored_singletons = anchored_singletons or {}
        self._anchored_pre_configurations = anchored_pre_configurations or {}
        self._anchored_owner_tokens = anchored_owner_tokens
        self.issues: list[BuildIssue] = []

    def _current_path(self, *tail: Any) -> tuple[str, ...]:
        return tuple(qualified_name(value) for value in (*(frame.label for frame in self._frames), *tail))

    def _validate_captive_lifespan(
        self,
        label: Any,
        lifespan: legacy.Lifespan,
        *,
        is_instance: bool = False,
    ) -> None:
        singleton = next((item for item in reversed(self._frames) if item.lifespan == legacy.Lifespan.singleton), None)
        if singleton is not None and lifespan == legacy.Lifespan.scoped and not is_instance:
            raise ContainerBuildError(
                f"{_frame_description(singleton)} cannot retain scoped {label}",
                code="captive-dependency",
                path=self._current_path(label),
            )
        long_lived = next(
            (
                item
                for item in reversed(self._frames)
                if item.lifespan in (legacy.Lifespan.scoped, legacy.Lifespan.singleton)
            ),
            None,
        )
        if long_lived is not None and lifespan == legacy.Lifespan.once_per_graph:
            raise ContainerBuildError(
                f"{_frame_description(long_lived)} cannot retain once-per-graph {label}",
                code="captive-dependency",
                path=self._current_path(label),
            )

    def compile(self, service_types: Iterable[Any] | None = None) -> _PlanSet:
        roots: dict[Any, tuple[_RootPlan, ...]] = {}
        for service_type in service_types or self.blueprint.service_types():
            # Open generic registrations are reusable activation templates, not
            # directly resolvable roots. Closed occurrences compile on demand
            # from the concrete services discovered by the builder.
            if getattr(service_type, "__parameters__", ()):
                continue
            candidates = self._compile_candidates(service_type, parent=None, argument=None)
            roots[service_type] = tuple(_RootPlan(component=component, step=step) for component, step in candidates)
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
        )

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
        specialized.dependencies = dependencies
        self._specialized_factories[key] = specialized
        return specialized

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
        build_args: Mapping[str, Any] | None = None,
    ) -> tuple[Component, _ComponentDraft]:
        occurrence = self._next_occurrence
        self._next_occurrence += 1
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
            position=position,
            parent_id=None if parent is None else parent.occurrence_id,
            argument=argument,
        )
        return self.graph.add(draft), draft

    def _compile_candidates(
        self,
        service_type: Any,
        parent: Component | None,
        argument: str | None,
    ) -> list[tuple[Component, _RegistrationStep]]:
        registrations = self.blueprint.registrations(service_type)
        if not registrations and get_origin(service_type) is not None:
            registrations = self.blueprint.registrations(get_origin(service_type))
        candidates: list[tuple[Component, _RegistrationStep]] = []
        for source_registration, layer in registrations:
            try:
                registration = self._specialize_factory(source_registration, layer, service_type)
            except ContainerBuildError as error:
                raise ContainerBuildError(
                    str(error),
                    code=error.code or "generic-specialization",
                    path=error.path or self._current_path(service_type),
                ) from error
            component, step = self._compile_registration(
                registration,
                layer,
                parent=parent,
                argument=argument,
                requested_service_type=service_type,
            )
            predicate = layer.registration_when.get(source_registration.id)
            if predicate is not None and not predicate(component):
                continue
            if registration.parent_node_filter is not legacy.default_parent_node_filter:
                if component.parent is None or not registration.parent_node_filter(cast(Any, component.parent)):
                    continue
            candidates.append((component, step))
        return candidates

    def _compile_registration(
        self,
        registration: legacy._Registration,
        layer: _Layer,
        *,
        parent: Component | None,
        argument: str | None,
        requested_service_type: Any,
    ) -> tuple[Component, _RegistrationStep]:
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
                for item in reversed(self._frames)
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
            implementation=registration.implementation,
            lifespan=_component_lifespan(registration.lifespan),
            name=registration.name,
            tags=registration.tags,
            kind=ComponentKind.registration,
            activation=_registration_activation(registration),
            parent=parent,
            argument=argument,
            requires_async=_requires_async(registration.activator_class, registration.implementation),
            manages_cleanup=_manages_cleanup(registration.activator_class, registration.implementation),
        )
        self._stack.append(registration)
        self._frames.append(
            _CompilerFrame(
                label=requested_service_type,
                lifespan=registration.lifespan,
                owner_token=layer.owner_token,
                kind=ComponentKind.registration,
            )
        )
        try:
            dependencies = self._compile_dependencies(registration.dependencies, component)
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
            step = _REGISTRATION_STEP_TYPES[registration.lifespan](
                registration=registration,
                owner_token=layer.owner_token,
                component=component,
                dependencies=dependencies,
                pre_configurations=configurations,
                decorators=decorators,
                sync_supported=(
                    not _requires_async(registration.activator_class, registration.implementation)
                    and all(dependency.step.sync_supported for dependency in dependencies)
                    and all(item.sync_supported for item in configurations)
                    and all(item.sync_supported for item in decorators)
                ),
            )
            return component, step
        finally:
            self._frames.pop()
            self._stack.pop()

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
            build_args=source.build_args,
        )
        draft.implementation_type = source.implementation_type
        mapping[source.occurrence_id] = component

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
            candidates = self._compile_candidates(request.service_type, parent=None, argument=None)
            candidates = [item for item in candidates if request.filter(item[0])]
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
            component, step = candidates[0]
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

    def _compile_dependency(
        self,
        dependency: legacy.Dependency,
        parent: Component,
    ) -> tuple[_Step, Component | None]:
        policy = dependency.settings.value_factory
        if isinstance(policy, _FixedArgument):
            value = policy.value
        elif isinstance(policy, _DerivedArgument):
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
            )
            return _ValueStep(value), component

        if dependency.service_type in (
            Scope,
            Container,
            ResolutionContext,
            legacy.Scope,
            legacy.Resolver,
            legacy.ScopeCreator,
            legacy.CurrentGraph,
        ):
            component, _ = self._draft(
                component_id=f"context:{parent.occurrence_id}:{dependency.name}",
                service_type=dependency.service_type,
                implementation=dependency.service_type,
                lifespan="transient",
                name=None,
                tags=(),
                kind=ComponentKind.runtime_context,
                activation=ComponentActivation.context,
                parent=parent,
                argument=dependency.name,
            )
            return _ScopeStep(dependency.service_type), component

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
            )
            candidates = self._compile_candidates(element_type, collection, dependency.name)
            candidates = [item for item in candidates if dependency.settings.filter(item[0])]
            collection_draft.dependency_ids = tuple(component.occurrence_id for component, _ in candidates)
            member_steps = tuple(step for _, step in candidates)
            return (
                _CollectionStep(
                    dependency.generic_collection_type,
                    member_steps,
                    all(step.sync_supported for step in member_steps),
                ),
                collection,
            )

        candidates = self._compile_candidates(dependency.service_type, parent, dependency.name)
        candidates = [item for item in candidates if dependency.settings.filter(item[0])]
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
            component, step = candidates[0]
            return step, component

        slot = self._matching_slot(dependency.service_type, dependency.settings.filter, parent, dependency.name)
        if slot is not None:
            name, component = slot
            return _ProvidedStep(dependency.service_type, name), component
        raise ContainerBuildError(
            f"No component for {dependency.service_type!r}, argument {dependency.name!r} of {parent.implementation!r}",
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
        for slot_type, name in self.blueprint.slots:
            if slot_type != service_type:
                continue
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
            )
            if filter(component):
                self._validate_captive_lifespan(slot_type, legacy.Lifespan.scoped)
                return name, component
        return None

    def _compile_pre_configurations(
        self,
        parent: Component,
    ) -> tuple[_CompiledPreConfiguration, ...]:
        items: list[_CompiledPreConfiguration] = []
        for definition, layer in self.blueprint.pre_configurations(parent.service_type):
            if not definition.when(parent):
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
            )
            self._compiling_pre_configurations.add(definition.id)
            self._frames.append(
                _CompilerFrame(
                    label=definition.configuration_fn,
                    lifespan=legacy.Lifespan.singleton,
                    owner_token=layer.owner_token,
                    kind=ComponentKind.pre_configuration,
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
                sync_supported=(
                    not _requires_async(activator_class, definition.configuration_fn)
                    and all(dependency.step.sync_supported for dependency in compiled_dependencies)
                ),
            )
            self._compiled_pre_configurations[definition.id] = compiled
            items.append(compiled)
        return tuple(items)

    def _compile_decorators(
        self,
        registration: legacy._Registration,
        core: Component,
    ) -> tuple[_CompiledDecorator, ...]:
        # Applicability is deliberately evaluated against the completed,
        # undecorated core subtree before any decorator dependencies are added.
        selected: list[_DecoratorDefinition] = []
        for decorator, _ in self.blueprint.decorators(core.service_type):
            if not decorator.when(core):
                continue
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
            )
            draft.decorated_id = decorated.occurrence_id
            dependencies = self._compile_dependencies(decorator.dependencies, component)
            items.append(
                _CompiledDecorator(
                    decorator,
                    dependencies,
                    component,
                    not _requires_async(decorator.activator_class, decorator.implementation)
                    and all(dependency.step.sync_supported for dependency in dependencies),
                )
            )
            decorated = component
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

    def _close(self) -> None:
        if self._closed:
            return
        for finalizer in self._finalizers:
            result = finalizer()
            if inspect.isawaitable(result):
                raise RuntimeError("Async finalizer requires async context management")
        self._closed = True

    async def _close_async(self) -> None:
        if self._closed:
            return
        for finalizer in self._finalizers:
            result = finalizer()
            if inspect.isawaitable(result):
                await result
        self._closed = True


def _collection_request(service_type: Any) -> tuple[type, Any] | None:
    if isinstance(service_type, type):
        return None
    origin = get_origin(service_type)
    collection_type = legacy.Dependency.GENERIC_COLLECTION_MAPPINGS.get(origin)
    arguments = get_args(service_type)
    if collection_type is None or not arguments:
        return None
    return collection_type, arguments[0]


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


def _anchored_singletons(
    plan: _PlanSet,
) -> dict[tuple[str, tuple[Any, ...]], _RegistrationStep]:
    anchored: dict[tuple[str, tuple[Any, ...]], _RegistrationStep] = {}
    for plans in plan.roots.values():
        for root in plans:
            for step in _iter_registration_steps(root.step):
                if step.registration.lifespan == legacy.Lifespan.singleton:
                    anchored.setdefault(
                        (step.registration.id, _runtime_type_key(step.component.service_type)),
                        step,
                    )
    return anchored


def _anchored_pre_configurations(plan: _PlanSet) -> dict[str, _CompiledPreConfiguration]:
    anchored: dict[str, _CompiledPreConfiguration] = {}
    for plans in plan.roots.values():
        for root in plans:
            for step in _iter_registration_steps(root.step):
                for configuration in step.pre_configurations:
                    anchored.setdefault(configuration.definition.id, configuration)
    return anchored


def _graph_roots(plan: _PlanSet) -> tuple[GraphRoot, ...]:
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
    for service_type in blueprint.service_types():
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
            ).compile((service_type,))
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


def _finalize_plan(plan: _PlanSet) -> _PlanSet:
    all_roots = _graph_roots(plan)
    entrypoints: list[GraphRoot] = []
    issues: list[BuildIssue] = list(plan.compiler_issues)

    for request in plan.blueprint.entrypoints:
        collection = _collection_request(request.service_type)
        if collection is not None:
            _, element_type = collection
            matches = [
                GraphRoot(request.service_type, root.component)
                for root in plan.roots.get(element_type, ())
                if request.filter(root.component)
            ]
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

        matches = [
            GraphRoot(request.service_type, root.component)
            for root in plan.roots.get(request.service_type, ())
            if request.filter(root.component)
        ]
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
        if len(matches) > 1:
            issues.append(
                BuildIssue(
                    code="ambiguous-selection",
                    severity=IssueSeverity.warning,
                    message=f"Marked entry point {root_name} matches {len(matches)} roots; the first is selected",
                    root=root_name,
                    path=(root_name,),
                )
            )
        entrypoints.append(matches[0])

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

    deduplicated = tuple(dict.fromkeys(issues))
    report = BuildReport(deduplicated, checked_roots=len(all_roots))
    if not report.is_valid:
        raise ContainerBuildError(report=report)
    compiled_graph = CompiledGraph(
        roots=all_roots,
        build_args=plan.build_args,
        entrypoints=tuple(entrypoints),
    )
    return replace(plan, compiled_graph=compiled_graph, build_report=report)


def _compile_with_report(
    blueprint: _Blueprint,
    *,
    build_args: Mapping[str, Any] = _EMPTY_BUILD_ARGS,
    anchored_singleton_steps: dict[tuple[str, tuple[Any, ...]], _RegistrationStep] | None = None,
    anchored_pre_configuration_steps: dict[str, _CompiledPreConfiguration] | None = None,
    anchored_owner_tokens: frozenset[str] = frozenset(),
) -> _PlanSet:
    try:
        plan = _Compiler(
            blueprint,
            build_args=build_args,
            anchored_singletons=anchored_singleton_steps,
            anchored_pre_configurations=anchored_pre_configuration_steps,
            anchored_owner_tokens=anchored_owner_tokens,
        ).compile()
        return _finalize_plan(plan)
    except ContainerBuildError as error:
        if error.report is not None:
            raise
        report = _error_report(
            blueprint,
            error,
            build_args=build_args,
            anchored_singleton_steps=anchored_singleton_steps,
            anchored_pre_configuration_steps=anchored_pre_configuration_steps,
            anchored_owner_tokens=anchored_owner_tokens,
        )
        raise ContainerBuildError(report=report) from error
    except Exception as error:
        report = _error_report(
            blueprint,
            error,
            build_args=build_args,
            anchored_singleton_steps=anchored_singleton_steps,
            anchored_pre_configuration_steps=anchored_pre_configuration_steps,
            anchored_owner_tokens=anchored_owner_tokens,
        )
        raise ContainerBuildError(report=report) from error


class _RuntimeResolutionContext:
    __slots__ = ("once_cache", "registration_stack", "scope", "singleton_owner_stack")

    def __init__(self, scope: Scope):
        self.scope = scope
        self.once_cache: dict[str, Any] = {}
        self.registration_stack: list[_RegistrationStep] = []
        self.singleton_owner_stack: list[str] = []

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

    def add_finalizer(self, lifespan: legacy.Lifespan, finalizer: Callable[..., Any]) -> None:
        step = self.registration_stack[-1] if self.registration_stack else None
        owner_token = self.singleton_owner_stack[-1] if self.singleton_owner_stack else None
        if lifespan == legacy.Lifespan.singleton and owner_token is not None:
            self.scope._owners[owner_token]._finalizers.appendleft(finalizer)
        elif lifespan == legacy.Lifespan.singleton and step is not None:
            self.scope._owners[step.owner_token]._finalizers.appendleft(finalizer)
        else:
            self.scope._finalizers.appendleft(finalizer)


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

    @property
    def build_args(self) -> Mapping[str, Any]:
        """Immutable user inputs supplied for this plan's compilation."""

        return self._plan.build_args

    def has_component(self, service_type: Any, filter: ComponentFilter = default_component_filter) -> bool:
        """Return whether the frozen plan contains a matching root component."""

        return any(filter(plan.component) for plan in self._plan.roots.get(service_type, ()))

    def has_scope_slot(self, service_type: Any, name: str | None = None) -> bool:
        """Return whether this runtime can accept the supplied scope value."""

        return (service_type, name) in self._plan.blueprint.slots

    def has_provision(self, service_type: Any, name: str | None = None) -> bool:
        """Return whether this scope or one of its parents supplied a slot value."""

        key = (service_type, name)
        if key in self._provisions:
            return True
        return self.parent is not None and self.parent.has_provision(service_type, name)

    def _select_root(self, service_type: Any, filter: ComponentFilter) -> _RootPlan:
        self._resolution_started = True
        if filter is default_component_filter:
            plan = self._plan.default_roots.get(service_type)
            if plan is not None:
                return plan
        else:
            for plan in self._plan.roots.get(service_type, ()):
                if filter(plan.component):
                    return plan
        if (service_type, None) in self._plan.blueprint.slots:
            raise ScopeProvisionError(f"Scope slot {service_type!r} has no provided value")
        raise CannotResolveError(service_type)

    def _select_roots(self, service_type: Any, filter: ComponentFilter) -> tuple[_RootPlan, ...]:
        self._resolution_started = True
        if filter is default_component_filter:
            return self._plan.default_root_groups.get(service_type, ())
        return tuple(plan for plan in self._plan.roots.get(service_type, ()) if filter(plan.component))

    def resolve(
        self,
        service_type: type[TService],
        filter: ComponentFilter = default_component_filter,
    ) -> TService:
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
            return cast(TService, plan.step.resolve(_RuntimeResolutionContext(self)))
        return cast(TService, _RuntimeResolutionContext(self).resolve_root(service_type, filter))

    async def resolve_async(
        self,
        service_type: type[TService],
        filter: ComponentFilter = default_component_filter,
    ) -> TService:
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
            return cast(TService, await plan.step.resolve_async(_RuntimeResolutionContext(self)))
        return cast(TService, await _RuntimeResolutionContext(self).resolve_root_async(service_type, filter))

    def provide(self, service_type: type[TService], value: TService, name: str | None = None) -> Scope:
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
        return Scope(
            self._plan,
            container=self.container,
            parent=self,
            owners=self._owners,
        )

    def new_scope_builder(self) -> ScopeBuilder:
        return ScopeBuilder(self)

    def __enter__(self) -> Scope:
        return self

    def __exit__(self, *_: Any) -> None:
        self._close()

    async def __aenter__(self) -> Scope:
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
        return Scope(
            self._plan,
            container=self,
            parent=self,
            owners=cast(dict[str, _RuntimeOwner], self._owners),
        )


class _BuilderBase:
    def __init__(self, *, owner_token: str | None = None) -> None:
        self.id = str(uuid4())
        self._composition = legacy.Container()
        self._internal_ids = frozenset(
            registration.id
            for registrations in self._composition._registry._registrations.values()
            for registration in registrations
        )
        self._owner_token = owner_token or str(uuid4())
        self._registration_when: dict[str, ComponentFilter] = {}
        self._factory_ids: set[str] = set()
        self._factory_specializations: dict[str, object] = {}
        self._decorators: list[_DecoratorDefinition] = []
        self._removed_decorator_ids: set[str] = set()
        self._next_decorator_order = 0
        self._pre_configurations: list[_PreConfigurationDefinition] = []
        self._pre_configuration_states: dict[str, _PreConfigurationState] = {}
        self._next_pre_configuration_order = 0
        self._registration_discoveries: list[_RegistrationDiscovery] = []
        self._slots: set[tuple[Any, str | None]] = set()
        self._entrypoints: list[_EntryPoint] = []
        self._built = False

    def _assert_mutable(self) -> None:
        if self._built:
            raise BuilderAlreadyBuiltError("Builders are single-use after a successful build")

    def _effective_build_args(self, build_args: Mapping[str, Any] | None) -> Mapping[str, Any]:
        parent = getattr(self, "_parent", None)
        if parent is None:
            return _normalize_build_args(build_args)
        return _merge_build_args(parent.build_args, build_args)

    def _layer(self) -> _Layer:
        registry = _clone_registry(self._composition._registry)
        registration_when = dict(self._registration_when)

        discovered = legacy._Registry()
        for rule in self._registration_discoveries:
            rule.materialize(discovered, registration_when)
        for service_type, registrations in discovered._registrations.items():
            # Explicit composition always precedes convention-based discovery.
            registry._registrations[service_type].extend(registrations)

        return _Layer(
            registry=registry,
            internal_ids=self._internal_ids,
            owner_token=self._owner_token,
            registration_when=registration_when,
            factory_ids=frozenset(self._factory_ids),
            factory_specializations=dict(self._factory_specializations),
            decorators=tuple(self._decorators),
            removed_decorator_ids=frozenset(self._removed_decorator_ids),
            pre_configurations=tuple(self._pre_configurations),
            pre_configuration_states=dict(self._pre_configuration_states),
            slots=frozenset(self._slots),
            entrypoints=tuple(self._entrypoints),
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
        service_type: type[TService],
        implementation_type: type[TService] | None = None,
        *,
        factory: Callable[..., Any] | None = None,
        factory_specialization: object | None = None,
        instance: TService | None = None,
        lifespan: Lifespan = "once_per_graph",
        name: str | None = None,
        arguments: Mapping[str, Any] | None = None,
        tags: Iterable[legacy.Tag] | None = None,
        when: ComponentFilter = all_components,
    ) -> str:
        self._assert_mutable()
        if factory_specialization is not None and factory is None:
            raise ValueError("factory_specialization requires factory=")
        component_id = self._composition.register(
            service_type,
            implementation_type,
            factory=factory,
            instance=instance,
            lifespan=_legacy_lifespan(lifespan),
            name=name,
            dependency_config=_arguments_to_dependency_config(arguments),
            tags=tags,
            parent_node_filter=legacy.default_parent_node_filter,
        )
        self._registration_when[component_id] = when
        if factory is not None:
            self._factory_ids.add(component_id)
            if factory_specialization is not None:
                self._factory_specializations[component_id] = factory_specialization
        return component_id

    def patch_component(
        self,
        service_type: type,
        component_id: str,
        *,
        arguments: Mapping[str, Any] | None = None,
        lifespan: Lifespan | None = None,
        tags: Iterable[legacy.Tag] | None = None,
    ) -> None:
        self._assert_mutable()
        try:
            self._composition.patch_registration(
                service_type,
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

        registration = next(
            (
                candidate
                for rule in self._registration_discoveries
                if (candidate := rule.find_registration(service_type, component_id)) is not None
            ),
            None,
        )
        if registration is None:
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
        decorator_type: type | Callable,
        *,
        when: ComponentFilter = all_components,
        decorated_arg: str | None = None,
        arguments: Mapping[str, Any] | None = None,
        position: int = 0,
        name: str | None = None,
        tags: Iterable[legacy.Tag] | None = None,
    ) -> str:
        self._assert_mutable()
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
            )
        )
        return decorator_id

    def _find_decorator_definition(
        self,
        service_type: Any,
        decorator_id: str,
    ) -> _DecoratorDefinition | None:
        own = next(
            (
                definition
                for definition in reversed(self._decorators)
                if definition.id == decorator_id and definition.service_type == service_type
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
        if self._find_decorator_definition(service_type, decorator_id) is None:
            raise KeyError(f"No decorator found for {service_type} with ID {decorator_id}")
        self._decorators = [definition for definition in self._decorators if definition.id != decorator_id]
        self._removed_decorator_ids.add(decorator_id)

    def pre_configure(
        self,
        service_type: type | Iterable[type],
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
        service_types = tuple(dict.fromkeys(service_types))
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
            )
        )
        self._pre_configuration_states[definition_id] = _PreConfigurationState()
        return definition_id

    def declare_scope_slot(self, service_type: type, name: str | None = None) -> _BuilderBase:
        self._assert_mutable()
        self._slots.add((service_type, name))
        return self

    def mark_entrypoint(
        self,
        service_type: Any,
        *,
        filter: ComponentFilter = default_component_filter,
    ) -> _BuilderBase:
        """Mark a public resolution request for graph and reachability tooling."""

        self._assert_mutable()
        self._entrypoints.append(_EntryPoint(service_type, filter))
        return self

    def register_subclasses(
        self,
        base_type: type,
        *,
        lifespan: Lifespan = "once_per_graph",
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
            )
        )

    def register_generic_subclasses(
        self,
        generic_service_type: type,
        *,
        fallback_type: type | None = None,
        lifespan: Lifespan = "once_per_graph",
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
            )
        )

    def apply_bundle(self, bundle: Callable[[ComponentBuilder], None]) -> None:
        self._assert_mutable()
        bundle(self)

    def _preview_components(
        self,
        service_type: Any,
        build_args: Mapping[str, Any] | None = None,
    ) -> tuple[Component, ...]:
        self._assert_mutable()
        plan = _Compiler(
            _Blueprint((self._layer(),)),
            build_args=self._effective_build_args(build_args),
        ).compile()
        return tuple(item.component for item in plan.roots.get(service_type, ()))

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

    def build(self, *, build_args: Mapping[str, Any] | None = None) -> Container:
        self._assert_mutable()
        plan = _compile_with_report(
            _Blueprint((self._layer(),)),
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

    def build(self, *, build_args: Mapping[str, Any] | None = None) -> Scope:
        self._assert_mutable()
        blueprint = _Blueprint((self._layer(), *self._parent._plan.blueprint.layers))
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
