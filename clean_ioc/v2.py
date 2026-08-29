"""Build-time composition and graph-free runtime for Clean IoC 2."""

from __future__ import annotations

import asyncio
import concurrent.futures
import inspect
import threading
import types
import typing
from collections import defaultdict, deque
from collections.abc import Callable, Iterable
from contextlib import contextmanager
from dataclasses import dataclass, field, replace
from typing import Any, TypeVar, cast, get_args, get_origin
from uuid import UUID, uuid4, uuid5

from typetoolbox.generics import GenericTypeMap, get_generic_mapping

from . import core as legacy
from .components import (
    Component,
    ComponentActivation,
    ComponentFilter,
    ComponentKind,
    ComponentListModifier,
    _ComponentDraft,
    _ComponentGraph,
    all_components,
    default_component_filter,
    default_component_list_modifier,
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


class UndeclaredScopeSlotError(ContainerBuildError):
    pass


class ScopeProvisionError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class DependencyContext:
    """Static context for a parameter value provider."""

    name: str
    component: Component

    @property
    def service_type(self) -> Any:
        return self.component.service_type

    @property
    def implementation(self) -> Any:
        return self.component.implementation

    @property
    def parent(self) -> Component | None:
        return self.component.parent

    @property
    def decorated(self) -> Component | None:
        return self.component.decorated


class ResolutionContext:
    """Resolve an already-compiled component inside the current object graph."""

    __slots__ = ("_context",)

    def __init__(self, context: _RuntimeResolutionContext) -> None:
        self._context = context

    def resolve(
        self,
        service_type: type[TService],
        filter: ComponentFilter = default_component_filter,
    ) -> TService:
        return cast(TService, self._context.resolve_root(service_type, filter))

    async def resolve_async(
        self,
        service_type: type[TService],
        filter: ComponentFilter = default_component_filter,
    ) -> TService:
        return cast(TService, await self._context.resolve_root_async(service_type, filter))


@dataclass(frozen=True, slots=True)
class _EntryPoint:
    service_type: Any
    filter: ComponentFilter


@dataclass(frozen=True, slots=True)
class _Layer:
    registry: legacy._Registry
    internal_ids: frozenset[str]
    owner_token: str
    registration_when: dict[str, ComponentFilter]
    factory_ids: frozenset[str]
    factory_specializations: dict[str, object]
    decorator_when: dict[int, ComponentFilter]
    pre_configuration_when: dict[int, ComponentFilter]
    pre_configuration_states: dict[int, _PreConfigurationState]
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

    def decorators(self, service_type: Any) -> list[tuple[legacy.Decorator, _Layer]]:
        return [
            (decorator, layer) for layer in self.layers for decorator in layer.registry.get_decorators(service_type)
        ]

    def pre_configurations(self, service_type: Any) -> list[tuple[legacy.PreConfiguration, _Layer]]:
        return [
            (configuration, layer)
            for layer in self.layers
            for configuration in layer.registry.get_pre_configurations(service_type)
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
    target._pre_configurations = defaultdict(
        deque,
        {service_type: deque(configurations) for service_type, configurations in source._pre_configurations.items()},
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
    parent_node_filter: Callable[[Any], bool],
) -> legacy._Registration:
    registry = legacy._Registry()
    component_id = registry.register_implementation(
        service_type=service_type,
        implementation=implementation_type,
        lifespan=lifespan,
        name=name,
        dependency_config={},
        tags=tags,
        parent_node_filter=cast(Any, parent_node_filter),
    )
    return next(
        registration for registration in registry.get_registrations(service_type) if registration.id == component_id
    )


def _create_discovered_decorator(
    *,
    service_type: Any,
    decorator_type: type | Callable,
    registration_filter: ComponentFilter,
    decorator_node_filter: ComponentFilter,
    decorated_arg: str | None,
    dependency_config: legacy.DependencyConfig,
    position: int,
) -> legacy.Decorator:
    registry = legacy._Registry()
    registry.register_decorator(
        service_type=service_type,
        decorator_type=decorator_type,
        registration_filter=cast(Any, registration_filter),
        decorator_node_filter=cast(Any, decorator_node_filter),
        decorated_arg=decorated_arg,
        dependency_config=dependency_config,
        position=position,
    )
    return next(iter(registry.get_decorators(service_type)))


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
    parent_node_filter: Callable[[Any], bool]
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
            parent_node_filter=self.parent_node_filter,
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
                    parent_node_filter=self.parent_node_filter,
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


@dataclass(slots=True)
class _GenericDecoratorDiscovery:
    order: int
    generic_service_type: type
    generic_decorator_type: type
    subclass_type_filter: Callable[[type], bool]
    when: ComponentFilter
    decorated_arg: str | None
    dependency_config: legacy.DependencyConfig
    registration_filter: ComponentFilter
    decorator_node_filter: ComponentFilter
    position: int
    decorators: dict[Any, legacy.Decorator] = field(default_factory=dict)

    def _filter(self, subclass: type) -> bool:
        return (
            not inspect.isabstract(subclass)
            and not subclass.__name__.startswith("__DecoratedGeneric__")
            and self.subclass_type_filter(subclass)
        )

    def materialize(self) -> tuple[tuple[Any, legacy.Decorator], ...]:
        decorator_is_generic = GenericTypeMap(self.generic_decorator_type).is_mapping_generic()
        materialized: list[tuple[Any, legacy.Decorator]] = []
        processed: set[Any] = set()
        for subclass in _unique_subclasses(self.generic_service_type, self._filter):
            service_type = legacy.Container._get_target_generic_base(self.generic_service_type, subclass)
            if service_type is None or service_type in processed:
                continue
            processed.add(service_type)
            decorator = self.decorators.get(service_type)
            if decorator is None:
                decorator_type = self.generic_decorator_type
                if decorator_is_generic:
                    concrete = legacy.try_to_map_generic_args_to_specialization(
                        self.generic_decorator_type,
                        subclass,
                    )
                    decorator_type = legacy.create_generic_decorator_type(concrete)
                decorator = _create_discovered_decorator(
                    service_type=service_type,
                    decorator_type=decorator_type,
                    registration_filter=self.registration_filter,
                    decorator_node_filter=self.decorator_node_filter,
                    decorated_arg=self.decorated_arg,
                    dependency_config=self.dependency_config,
                    position=self.position,
                )
                self.decorators[service_type] = decorator
            materialized.append((service_type, decorator))
        return tuple(materialized)


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
class _DependencyContextStep(_Step):
    name: str
    component: Component

    def resolve(self, context: _RuntimeResolutionContext) -> DependencyContext:
        return DependencyContext(self.name, self.component)

    async def resolve_async(self, context: _RuntimeResolutionContext) -> DependencyContext:
        return self.resolve(context)


@dataclass(frozen=True, slots=True)
class _ScopeStep(_Step):
    requested_type: Any

    def resolve(self, context: _RuntimeResolutionContext) -> Any:
        if self.requested_type is Container:
            return context.scope.container
        if self.requested_type in (ResolutionContext, legacy.CurrentGraph):
            return ResolutionContext(context)
        return context.scope

    async def resolve_async(self, context: _RuntimeResolutionContext) -> Any:
        return self.resolve(context)


@dataclass(frozen=True, slots=True)
class _CollectionStep(_Step):
    collection_type: type
    members: tuple[_Step, ...]

    @property
    def sync_supported(self) -> bool:
        return all(member.sync_supported for member in self.members)

    def resolve(self, context: _RuntimeResolutionContext) -> Any:
        return self.collection_type(member.resolve(context) for member in self.members)

    async def resolve_async(self, context: _RuntimeResolutionContext) -> Any:
        values = await asyncio.gather(*(member.resolve_async(context) for member in self.members))
        return self.collection_type(values)


@dataclass(slots=True)
class _PreConfigurationState:
    has_run: bool = False
    lock: threading.Lock = field(default_factory=threading.Lock)


@dataclass(slots=True)
class _CompiledPreConfiguration:
    source: legacy.PreConfiguration
    dependencies: tuple[_CompiledDependency, ...]
    component: Component
    state: _PreConfigurationState

    @property
    def sync_supported(self) -> bool:
        return not _requires_async(self.source.activator_class, self.source.configuration_fn) and all(
            dependency.step.sync_supported for dependency in self.dependencies
        )

    def run(self, context: _RuntimeResolutionContext) -> None:
        with self.state.lock:
            if self.state.has_run:
                return
            values = {dependency.name: dependency.step.resolve(context) for dependency in self.dependencies}
            try:
                self.source.activator_class.activate(
                    self.source.configuration_fn,
                    values,
                    cast(Any, context),
                    legacy.Lifespan.singleton,
                )
            except Exception:
                if not self.source.continue_on_failure:
                    raise
            else:
                self.state.has_run = True

    async def run_async(self, context: _RuntimeResolutionContext) -> None:
        # Async builds are coordinated at their owning registration. This lock
        # only protects the cheap already-run check across sync/async callers.
        with self.state.lock:
            if self.state.has_run:
                return
        values = {dependency.name: await dependency.step.resolve_async(context) for dependency in self.dependencies}
        try:
            await self.source.activator_class.activate_async(
                self.source.configuration_fn,
                values,
                cast(Any, context),
                legacy.Lifespan.singleton,
            )
        except Exception:
            if not self.source.continue_on_failure:
                raise
        else:
            with self.state.lock:
                self.state.has_run = True


@dataclass(frozen=True, slots=True)
class _CompiledDecorator:
    source: legacy.Decorator
    dependencies: tuple[_CompiledDependency, ...]
    component: Component

    @property
    def sync_supported(self) -> bool:
        return not _requires_async(self.source.activator_class, self.source.decorator_type) and all(
            dependency.step.sync_supported for dependency in self.dependencies
        )

    def decorate(self, value: Any, context: _RuntimeResolutionContext, lifespan: legacy.Lifespan) -> Any:
        dependencies = {dependency.name: dependency.step.resolve(context) for dependency in self.dependencies}
        dependencies[self.source.decorated_arg] = value
        with context.enter_component(self.component):
            return self.source.activator_class.activate(
                self.source.decorator_type,
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
        with context.enter_component(self.component):
            return await self.source.activator_class.activate_async(
                self.source.decorator_type,
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

    @property
    def sync_supported(self) -> bool:
        return (
            not _requires_async(self.registration.activator_class, self.registration.implementation)
            and all(dependency.step.sync_supported for dependency in self.dependencies)
            and all(item.sync_supported for item in self.pre_configurations)
            and all(item.sync_supported for item in self.decorators)
        )

    def _activate(self, context: _RuntimeResolutionContext) -> Any:
        for configuration in self.pre_configurations:
            configuration.run(context)
        values = {dependency.name: dependency.step.resolve(context) for dependency in self.dependencies}
        with context.enter_component(self.component):
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
        values = {dependency.name: await dependency.step.resolve_async(context) for dependency in self.dependencies}
        with context.enter_component(self.component):
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
        cached, value = context.get_cached(self)
        if cached:
            return value
        future, builder = context.begin_build(self)
        if future is not None and not builder:
            outcome = future.result()
            if outcome.error is not None:
                raise outcome.error
            cached, value = context.get_cached(self)
            if not cached:
                raise RuntimeError(f"Component {self.registration.id} completed without a cached value")
            return value
        try:
            context.assert_allowed(self)
            with context.enter_registration(self):
                value = self._activate(context)
                context.cache(self, value)
        except BaseException as error:
            context.finish_build(self, future, error)
            raise
        context.finish_build(self, future)
        return value

    async def resolve_async(self, context: _RuntimeResolutionContext) -> Any:
        cached, value = context.get_cached(self)
        if cached:
            return value
        future, builder = context.begin_build(self)
        if future is not None and not builder:
            outcome = await asyncio.shield(asyncio.wrap_future(future))
            if outcome.error is not None:
                raise outcome.error
            cached, value = context.get_cached(self)
            if not cached:
                raise RuntimeError(f"Component {self.registration.id} completed without a cached value")
            return value
        try:
            context.assert_allowed(self)
            with context.enter_registration(self):
                value = await self._activate_async(context)
                context.cache(self, value)
        except BaseException as error:
            context.finish_build(self, future, error)
            raise
        context.finish_build(self, future)
        return value


@dataclass(frozen=True, slots=True)
class _RootPlan:
    component: Component
    step: _Step


@dataclass(frozen=True, slots=True)
class _PlanSet:
    graph: _ComponentGraph
    roots: dict[Any, tuple[_RootPlan, ...]]
    blueprint: _Blueprint
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


class _Compiler:
    def __init__(
        self,
        blueprint: _Blueprint,
        *,
        anchored_singletons: dict[tuple[str, tuple[Any, ...]], _RegistrationStep] | None = None,
        anchored_owner_tokens: frozenset[str] = frozenset(),
    ):
        self.blueprint = blueprint
        self.graph = _ComponentGraph()
        self._next_occurrence = 1
        self._stack: list[legacy._Registration] = []
        self._specialized_factories: dict[tuple[str, tuple[Any, ...]], legacy._Registration] = {}
        self._anchored_singletons = anchored_singletons or {}
        self._anchored_owner_tokens = anchored_owner_tokens
        self.issues: list[BuildIssue] = []

    def _current_path(self, *tail: Any) -> tuple[str, ...]:
        return tuple(
            qualified_name(value) for value in (*(registration.service_type for registration in self._stack), *tail)
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
        return _PlanSet(
            graph=self.graph,
            roots=roots,
            blueprint=self.blueprint,
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
        lifespan: legacy.Lifespan,
        name: str | None,
        tags: Iterable[legacy.Tag],
        kind: ComponentKind,
        activation: ComponentActivation,
        parent: Component | None,
        argument: str | None = None,
        requires_async: bool = False,
        manages_cleanup: bool = False,
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
            kind=kind,
            activation=activation,
            requires_async=requires_async,
            manages_cleanup=manages_cleanup,
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
        singleton = next((item for item in reversed(self._stack) if item.lifespan == legacy.Lifespan.singleton), None)
        if singleton is not None and registration.lifespan == legacy.Lifespan.scoped and not registration.is_instance:
            raise ContainerBuildError(
                f"Singleton {singleton.service_type} cannot retain scoped {registration.service_type}",
                code="captive-dependency",
                path=self._current_path(registration.service_type),
            )
        long_lived = next(
            (
                item
                for item in reversed(self._stack)
                if item.lifespan in (legacy.Lifespan.scoped, legacy.Lifespan.singleton)
            ),
            None,
        )
        if long_lived is not None and registration.lifespan == legacy.Lifespan.once_per_graph:
            owner = "Singleton" if long_lived.lifespan == legacy.Lifespan.singleton else "Scoped"
            raise ContainerBuildError(
                f"{owner} {long_lived.service_type} cannot retain once-per-graph {registration.service_type}",
                code="captive-dependency",
                path=self._current_path(registration.service_type),
            )

        component, draft = self._draft(
            component_id=registration.id,
            service_type=requested_service_type,
            implementation=registration.implementation,
            lifespan=registration.lifespan,
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
        try:
            dependencies = self._compile_dependencies(registration.dependencies, component)
            configurations = self._compile_pre_configurations(registration, component)
            draft.pre_configuration_ids = tuple(item.component.occurrence_id for item in configurations)
            decorators = self._compile_decorators(registration, component)
            draft.decorator_ids = tuple(item.component.occurrence_id for item in decorators)
            step = _RegistrationStep(
                registration=registration,
                owner_token=layer.owner_token,
                component=component,
                dependencies=dependencies,
                pre_configurations=configurations,
                decorators=decorators,
            )
            return component, step
        finally:
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

    def _compile_dependency(
        self,
        dependency: legacy.Dependency,
        parent: Component,
    ) -> tuple[_Step, Component | None]:
        dependency_context = DependencyContext(dependency.name, parent)
        value_factory = dependency.settings.value_factory
        if value_factory is legacy.default_parameter_value_factory:
            value = dependency.default_value
        else:
            # The provider itself remains runtime-only. Its fallback edge is
            # compiled below, so provider results do not alter the plan.
            value = legacy.EMPTY
        if value is not legacy.EMPTY:
            component, _ = self._draft(
                component_id=f"value:{parent.occurrence_id}:{dependency.name}",
                service_type=dependency.service_type,
                implementation=type(value),
                lifespan=legacy.Lifespan.transient,
                name=None,
                tags=(),
                kind=ComponentKind.value,
                activation=ComponentActivation.supplied,
                parent=parent,
                argument=dependency.name,
            )
            return _ValueStep(value), component

        if dependency.service_type in (DependencyContext, legacy.DependencyContext):
            component, _ = self._draft(
                component_id=f"context:{parent.occurrence_id}:{dependency.name}",
                service_type=dependency.service_type,
                implementation=DependencyContext,
                lifespan=legacy.Lifespan.transient,
                name=None,
                tags=(),
                kind=ComponentKind.runtime_context,
                activation=ComponentActivation.context,
                parent=parent,
                argument=dependency.name,
            )
            return _DependencyContextStep(dependency.name, parent), component
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
                lifespan=legacy.Lifespan.transient,
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
                lifespan=legacy.Lifespan.transient,
                name=None,
                tags=(),
                kind=ComponentKind.collection,
                activation=ComponentActivation.collection,
                parent=parent,
                argument=dependency.name,
            )
            candidates = self._compile_candidates(element_type, collection, dependency.name)
            candidates = [item for item in candidates if dependency.settings.filter(item[0])]
            components = cast(
                list[Component],
                dependency.settings.list_modifier([component for component, _ in candidates]),
            )
            selected_ids = {component.occurrence_id for component in components}
            selected = [(component, step) for component, step in candidates if component.occurrence_id in selected_ids]
            collection_draft.dependency_ids = tuple(component.occurrence_id for component, _ in selected)
            return _CollectionStep(dependency.generic_collection_type, tuple(step for _, step in selected)), collection

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
            if value_factory is not legacy.default_parameter_value_factory:
                provider, provider_draft = self._draft(
                    component_id=f"provider:{parent.occurrence_id}:{dependency.name}",
                    service_type=dependency.service_type,
                    implementation=value_factory,
                    lifespan=legacy.Lifespan.transient,
                    name=None,
                    tags=(),
                    kind=ComponentKind.value_provider,
                    activation=ComponentActivation.factory,
                    parent=parent,
                    argument=dependency.name,
                )
                provider_draft.dependency_ids = (component.occurrence_id,)
                return (
                    _ProviderStep(cast(Any, value_factory), dependency.default_value, dependency_context, step),
                    provider,
                )
            return step, component

        slot = self._matching_slot(dependency.service_type, dependency.settings.filter, parent, dependency.name)
        if slot is not None:
            name, component = slot
            return _ProvidedStep(dependency.service_type, name), component
        if value_factory is not legacy.default_parameter_value_factory:
            provider, _ = self._draft(
                component_id=f"provider:{parent.occurrence_id}:{dependency.name}",
                service_type=dependency.service_type,
                implementation=value_factory,
                lifespan=legacy.Lifespan.transient,
                name=None,
                tags=(),
                kind=ComponentKind.value_provider,
                activation=ComponentActivation.factory,
                parent=parent,
                argument=dependency.name,
            )
            return _ProviderStep(cast(Any, value_factory), dependency.default_value, dependency_context, None), provider
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
                lifespan=legacy.Lifespan.scoped,
                name=name,
                tags=(),
                kind=ComponentKind.scope_slot,
                activation=ComponentActivation.supplied,
                parent=parent,
                argument=argument,
            )
            if filter(component):
                return name, component
        return None

    def _compile_pre_configurations(
        self,
        registration: legacy._Registration,
        parent: Component,
    ) -> tuple[_CompiledPreConfiguration, ...]:
        items: list[_CompiledPreConfiguration] = []
        for configuration, layer in self.blueprint.pre_configurations(registration.service_type):
            if not configuration.registration_filter(cast(Any, parent)):
                continue
            when = layer.pre_configuration_when.get(id(configuration), all_components)
            if not when(parent):
                continue
            component, _ = self._draft(
                component_id=f"pre:{id(configuration)}",
                service_type=registration.service_type,
                implementation=configuration.configuration_fn,
                lifespan=legacy.Lifespan.singleton,
                name=None,
                tags=(),
                kind=ComponentKind.pre_configuration,
                activation=_callable_activation(configuration.configuration_fn),
                parent=parent,
                requires_async=_requires_async(configuration.activator_class, configuration.configuration_fn),
                manages_cleanup=_manages_cleanup(configuration.activator_class, configuration.configuration_fn),
            )
            dependencies = self._compile_dependencies(configuration.dependencies, component)
            state = layer.pre_configuration_states.setdefault(id(configuration), _PreConfigurationState())
            items.append(_CompiledPreConfiguration(configuration, dependencies, component, state))
        return tuple(items)

    def _compile_decorators(
        self,
        registration: legacy._Registration,
        core: Component,
    ) -> tuple[_CompiledDecorator, ...]:
        # Applicability is deliberately evaluated against the completed,
        # undecorated core subtree before any decorator dependencies are added.
        selected: list[tuple[legacy.Decorator, _Layer]] = []
        for decorator, layer in self.blueprint.decorators(registration.service_type):
            if not decorator.registration_filter(cast(Any, core)):
                continue
            if not decorator.decorated_node_filter(cast(Any, core)):
                continue
            if not layer.decorator_when.get(id(decorator), all_components)(core):
                continue
            selected.append((decorator, layer))

        items: list[_CompiledDecorator] = []
        decorated: Component = core
        for decorator, _ in selected:
            component, draft = self._draft(
                component_id=f"decorator:{id(decorator)}",
                service_type=registration.service_type,
                implementation=decorator.decorator_type,
                lifespan=registration.lifespan,
                name=registration.name,
                tags=registration.tags,
                kind=ComponentKind.decorator,
                activation=_callable_activation(decorator.decorator_type),
                parent=core.parent,
                requires_async=_requires_async(decorator.activator_class, decorator.decorator_type),
                manages_cleanup=_manages_cleanup(decorator.activator_class, decorator.decorator_type),
            )
            draft.decorated_id = decorated.occurrence_id
            dependencies = self._compile_dependencies(decorator.dependencies, component)
            items.append(_CompiledDecorator(decorator, dependencies, component))
            decorated = component
        return tuple(items)


@dataclass(frozen=True, slots=True)
class _ProviderStep(_Step):
    provider: Callable[[Any, DependencyContext], Any]
    default: Any
    dependency_context: DependencyContext
    fallback: _Step | None

    @property
    def sync_supported(self) -> bool:
        return self.fallback is None or self.fallback.sync_supported

    def resolve(self, context: _RuntimeResolutionContext) -> Any:
        value = self.provider(self.default, self.dependency_context)
        if value is not legacy.EMPTY:
            return value
        if self.fallback is None:
            raise ContainerBuildError(f"Value provider returned EMPTY for {self.dependency_context.name}")
        return self.fallback.resolve(context)

    async def resolve_async(self, context: _RuntimeResolutionContext) -> Any:
        value = self.provider(self.default, self.dependency_context)
        if value is not legacy.EMPTY:
            return value
        if self.fallback is None:
            raise ContainerBuildError(f"Value provider returned EMPTY for {self.dependency_context.name}")
        return await self.fallback.resolve_async(context)


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

    def _remember(
        self,
        registration: legacy._Registration,
        value: Any,
    ) -> None:
        self._singletons[registration.id] = value

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
    if isinstance(step, _ProviderStep) and step.fallback is not None:
        yield from _iter_registration_steps(step.fallback)


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
    anchored_singleton_steps: dict[tuple[str, tuple[Any, ...]], _RegistrationStep] | None = None,
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
                anchored_singletons=anchored_singleton_steps,
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
    compiled_graph = CompiledGraph(all_roots, tuple(entrypoints))
    return replace(plan, compiled_graph=compiled_graph, build_report=report)


def _compile_with_report(
    blueprint: _Blueprint,
    *,
    anchored_singleton_steps: dict[tuple[str, tuple[Any, ...]], _RegistrationStep] | None = None,
    anchored_owner_tokens: frozenset[str] = frozenset(),
) -> _PlanSet:
    try:
        plan = _Compiler(
            blueprint,
            anchored_singletons=anchored_singleton_steps,
            anchored_owner_tokens=anchored_owner_tokens,
        ).compile()
        return _finalize_plan(plan)
    except ContainerBuildError as error:
        if error.report is not None:
            raise
        report = _error_report(
            blueprint,
            error,
            anchored_singleton_steps=anchored_singleton_steps,
            anchored_owner_tokens=anchored_owner_tokens,
        )
        raise ContainerBuildError(report=report) from error
    except Exception as error:
        report = _error_report(
            blueprint,
            error,
            anchored_singleton_steps=anchored_singleton_steps,
            anchored_owner_tokens=anchored_owner_tokens,
        )
        raise ContainerBuildError(report=report) from error


class _RuntimeResolutionContext:
    def __init__(self, scope: Scope):
        self.scope = scope
        self.once_cache: dict[str, Any] = {}
        self.registration_stack: list[_RegistrationStep] = []
        self.component_stack: list[Component] = []

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
        if any(active.registration.id == step.registration.id for active in self.registration_stack):
            raise RuntimeError(f"Circular component activation for {step.registration.service_type!r}")

    @contextmanager
    def enter_registration(self, step: _RegistrationStep):
        self.registration_stack.append(step)
        try:
            yield
        finally:
            self.registration_stack.pop()

    @contextmanager
    def enter_component(self, component: Component):
        self.component_stack.append(component)
        try:
            yield
        finally:
            self.component_stack.pop()

    def _cache(self, step: _RegistrationStep) -> dict[str, Any] | None:
        lifespan = step.registration.lifespan
        if lifespan == legacy.Lifespan.transient:
            return None
        if lifespan == legacy.Lifespan.once_per_graph:
            return self.once_cache
        if lifespan == legacy.Lifespan.scoped:
            return self.scope._scoped
        return self.scope._owners[step.owner_token]._singletons

    def get_cached(self, step: _RegistrationStep) -> tuple[bool, Any]:
        if step.registration.lifespan == legacy.Lifespan.scoped:
            found, value = self.scope._find_scoped(step.registration.id)
            return found, value
        cache = self._cache(step)
        if cache is not None and step.registration.id in cache:
            return True, cache[step.registration.id]
        return False, None

    def cache(self, step: _RegistrationStep, value: Any) -> None:
        lifespan = step.registration.lifespan
        cache = self._cache(step)
        if cache is None:
            return
        if lifespan == legacy.Lifespan.singleton:
            self.scope._owners[step.owner_token]._remember(step.registration, value)
        elif lifespan == legacy.Lifespan.scoped:
            self.scope._remember_scoped(step.registration, value)
        else:
            cache[step.registration.id] = value

    def _coordinator(self, step: _RegistrationStep) -> _Coordinator | None:
        if step.registration.lifespan == legacy.Lifespan.singleton:
            return self.scope._owners[step.owner_token]._coordinator
        if step.registration.lifespan == legacy.Lifespan.scoped:
            return self.scope._coordinator
        return None

    def begin_build(self, step: _RegistrationStep) -> tuple[concurrent.futures.Future[_Outcome] | None, bool]:
        coordinator = self._coordinator(step)
        if coordinator is None:
            return None, True
        return coordinator.begin(step.registration.id)

    def finish_build(
        self,
        step: _RegistrationStep,
        future: concurrent.futures.Future[_Outcome] | None,
        error: BaseException | None = None,
    ) -> None:
        coordinator = self._coordinator(step)
        if coordinator is not None and future is not None:
            coordinator.finish(step.registration.id, future, error)

    def add_finalizer(self, lifespan: legacy.Lifespan, finalizer: Callable[..., Any]) -> None:
        step = self.registration_stack[-1] if self.registration_stack else None
        if lifespan == legacy.Lifespan.singleton and step is not None:
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
        self._id = str(uuid4())
        self._plan = plan
        self.container = container
        self.parent = parent
        self._owners = dict(owners)
        if owned_token is not None:
            self._owners[owned_token] = self
        self._owned_token = owned_token
        self._inherit_scoped = inherit_scoped
        self._scoped: dict[str, Any] = {}
        self._coordinator = _Coordinator()
        self._provisions: dict[tuple[Any, str | None], Any] = {}
        self._resolution_started = False

    @property
    def id(self) -> str:
        return self._id

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
        for plan in self._plan.roots.get(service_type, ()):
            if filter(plan.component):
                return plan
        if (service_type, None) in self._plan.blueprint.slots:
            raise ScopeProvisionError(f"Scope slot {service_type!r} has no provided value")
        raise legacy.CannotResolveError()

    def _select_roots(self, service_type: Any, filter: ComponentFilter) -> tuple[_RootPlan, ...]:
        self._resolution_started = True
        return tuple(plan for plan in self._plan.roots.get(service_type, ()) if filter(plan.component))

    def resolve(
        self,
        service_type: type[TService],
        filter: ComponentFilter = default_component_filter,
    ) -> TService:
        context = _RuntimeResolutionContext(self)
        return cast(TService, context.resolve_root(service_type, filter))

    async def resolve_async(
        self,
        service_type: type[TService],
        filter: ComponentFilter = default_component_filter,
    ) -> TService:
        context = _RuntimeResolutionContext(self)
        return cast(TService, await context.resolve_root_async(service_type, filter))

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

    def _remember_scoped(self, registration: legacy._Registration, value: Any) -> None:
        self._scoped[registration.id] = value

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
        self._id = str(uuid4())
        self._plan = plan
        self.container = self
        self.parent = None
        self._owners = {root_owner_token: self}
        self._owned_token = root_owner_token
        self._inherit_scoped = False
        self._scoped = {}
        self._coordinator = _Coordinator()
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
        self._decorator_when: dict[int, ComponentFilter] = {}
        self._decorator_orders: dict[int, int] = {}
        self._next_decorator_order = 0
        self._pre_configuration_when: dict[int, ComponentFilter] = {}
        self._pre_configuration_states: dict[int, _PreConfigurationState] = {}
        self._registration_discoveries: list[_RegistrationDiscovery] = []
        self._generic_decorator_discoveries: list[_GenericDecoratorDiscovery] = []
        self._slots: set[tuple[Any, str | None]] = set()
        self._entrypoints: list[_EntryPoint] = []
        self._built = False

    def _assert_mutable(self) -> None:
        if self._built:
            raise BuilderAlreadyBuiltError("Builders are single-use after a successful build")

    def _layer(self) -> _Layer:
        registry = _clone_registry(self._composition._registry)
        registration_when = dict(self._registration_when)
        decorator_when = dict(self._decorator_when)

        discovered = legacy._Registry()
        for rule in self._registration_discoveries:
            rule.materialize(discovered, registration_when)
        for service_type, registrations in discovered._registrations.items():
            # Explicit composition always precedes convention-based discovery.
            registry._registrations[service_type].extend(registrations)

        generated_decorators: dict[Any, list[tuple[int, legacy.Decorator]]] = defaultdict(list)
        for rule in self._generic_decorator_discoveries:
            for service_type, decorator in rule.materialize():
                generated_decorators[service_type].append((rule.order, decorator))
                decorator_when[id(decorator)] = rule.when

        decorator_service_types = {*registry._decorators, *generated_decorators}
        for service_type in decorator_service_types:
            ordered: list[tuple[int, legacy.Decorator]] = []
            for fallback_order, decorator in enumerate(registry.get_decorators(service_type)):
                ordered.append((self._decorator_orders.get(id(decorator), -fallback_order - 1), decorator))
            ordered.extend(generated_decorators.get(service_type, ()))
            store = legacy._DecoratorStore()
            for _, decorator in sorted(ordered, key=lambda item: item[0]):
                store.add_decorator(decorator)
            registry._decorators[service_type] = store

        return _Layer(
            registry=registry,
            internal_ids=self._internal_ids,
            owner_token=self._owner_token,
            registration_when=registration_when,
            factory_ids=frozenset(self._factory_ids),
            factory_specializations=dict(self._factory_specializations),
            decorator_when=decorator_when,
            pre_configuration_when=dict(self._pre_configuration_when),
            pre_configuration_states=dict(self._pre_configuration_states),
            slots=frozenset(self._slots),
            entrypoints=tuple(self._entrypoints),
        )

    def _new_decorator_order(self) -> int:
        value = self._next_decorator_order
        self._next_decorator_order += 1
        return value

    def register(
        self,
        service_type: type[TService],
        implementation_type: type[TService] | None = None,
        *,
        factory: Callable[..., Any] | None = None,
        factory_specialization: object | None = None,
        instance: TService | None = None,
        lifespan: legacy.Lifespan = legacy.Lifespan.once_per_graph,
        name: str | None = None,
        dependency_config: legacy.DependencyConfig = {},
        tags: Iterable[legacy.Tag] | None = None,
        when: ComponentFilter = all_components,
        parent_node_filter: Callable[[Any], bool] = legacy.default_parent_node_filter,
    ) -> str:
        self._assert_mutable()
        if factory_specialization is not None and factory is None:
            raise ValueError("factory_specialization requires factory=")
        component_id = self._composition.register(
            service_type,
            implementation_type,
            factory=factory,
            instance=instance,
            lifespan=lifespan,
            name=name,
            dependency_config=dependency_config,
            tags=tags,
            parent_node_filter=parent_node_filter,
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
        dependency_config: legacy.DependencyConfig | None = None,
        lifespan: legacy.Lifespan | None = None,
        tags: Iterable[legacy.Tag] | None = None,
    ) -> None:
        self._assert_mutable()
        try:
            self._composition.patch_registration(
                service_type,
                component_id,
                dependency_config=dependency_config,
                lifespan=lifespan,
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
            dependency_config=dependency_config,
            lifespan=lifespan,
            tags=tags,
        )

    patch_registration = patch_component

    def register_decorator(
        self,
        service_type: type,
        decorator_type: type | Callable,
        *,
        when: ComponentFilter = all_components,
        decorated_arg: str | None = None,
        dependency_config: legacy.DependencyConfig = {},
        position: int = 0,
        registration_filter: ComponentFilter = all_components,
        decorator_node_filter: ComponentFilter = all_components,
    ) -> None:
        self._assert_mutable()
        before = {id(item) for item in self._composition._registry.get_decorators(service_type)}
        self._composition.register_decorator(
            service_type,
            decorator_type,
            registration_filter=cast(Any, registration_filter),
            decorator_node_filter=cast(Any, decorator_node_filter),
            decorated_arg=decorated_arg,
            dependency_config=dependency_config,
            position=position,
        )
        item = next(item for item in self._composition._registry.get_decorators(service_type) if id(item) not in before)
        self._decorator_when[id(item)] = when
        self._decorator_orders[id(item)] = self._new_decorator_order()

    def pre_configure(
        self,
        service_type: type | Iterable[type],
        configuration_function: Callable[..., Any],
        *,
        when: ComponentFilter = all_components,
        dependency_config: legacy.DependencyConfig = {},
        continue_on_failure: bool = False,
        registration_filter: ComponentFilter = all_components,
    ) -> None:
        self._assert_mutable()
        service_types = (
            tuple(service_type)
            if isinstance(service_type, Iterable) and not isinstance(service_type, type)
            else (service_type,)
        )
        before = {
            id(item) for target in service_types for item in self._composition._registry.get_pre_configurations(target)
        }
        self._composition.pre_configure(
            service_type,
            configuration_function,
            registration_filter=cast(Any, registration_filter),
            dependency_config=dependency_config,
            continue_on_failure=continue_on_failure,
        )
        for target in service_types:
            for item in self._composition._registry.get_pre_configurations(target):
                if id(item) not in before:
                    self._pre_configuration_when[id(item)] = when
                    self._pre_configuration_states.setdefault(id(item), _PreConfigurationState())

    def declare_scope_slot(self, service_type: type, name: str | None = None) -> _BuilderBase:
        self._assert_mutable()
        self._slots.add((service_type, name))
        return self

    expect_to_be_scoped = declare_scope_slot

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
        lifespan: legacy.Lifespan = legacy.Lifespan.once_per_graph,
        subclass_type_filter: Callable[[type], bool] = legacy.always_true,
        name: str | None = None,
        tags: Iterable[legacy.Tag] | None = None,
        when: ComponentFilter = all_components,
        parent_node_filter: Callable[[Any], bool] = legacy.default_parent_node_filter,
    ) -> None:
        """Queue concrete subclass discovery for the next successful build."""

        self._assert_mutable()
        self._registration_discoveries.append(
            _RegistrationDiscovery(
                base_type=base_type,
                generic=False,
                fallback_type=None,
                lifespan=lifespan,
                subclass_type_filter=subclass_type_filter,
                name=name,
                tags=tuple(tags or ()),
                parent_node_filter=parent_node_filter,
                when=when,
            )
        )

    def register_generic_subclasses(
        self,
        generic_service_type: type,
        *,
        fallback_type: type | None = None,
        lifespan: legacy.Lifespan = legacy.Lifespan.once_per_graph,
        subclass_type_filter: Callable[[type], bool] = legacy.always_true,
        name: str | None = None,
        tags: Iterable[legacy.Tag] | None = None,
        when: ComponentFilter = all_components,
        parent_node_filter: Callable[[Any], bool] = legacy.default_parent_node_filter,
    ) -> None:
        """Queue closed-generic subclass discovery for the build snapshot."""

        self._assert_mutable()
        self._registration_discoveries.append(
            _RegistrationDiscovery(
                base_type=generic_service_type,
                generic=True,
                fallback_type=fallback_type,
                lifespan=lifespan,
                subclass_type_filter=subclass_type_filter,
                name=name,
                tags=tuple(tags or ()),
                parent_node_filter=parent_node_filter,
                when=when,
            )
        )

    def register_generic_decorator(
        self,
        generic_service_type: type,
        generic_decorator_type: type,
        *,
        subclass_type_filter: Callable[[type], bool] = legacy.always_true,
        when: ComponentFilter = all_components,
        decorated_arg: str | None = None,
        dependency_config: legacy.DependencyConfig = {},
        registration_filter: ComponentFilter = all_components,
        decorator_node_filter: ComponentFilter = all_components,
        position: int = 0,
    ) -> None:
        """Queue generic decorator materialization for the build snapshot."""

        self._assert_mutable()
        self._generic_decorator_discoveries.append(
            _GenericDecoratorDiscovery(
                order=self._new_decorator_order(),
                generic_service_type=generic_service_type,
                generic_decorator_type=generic_decorator_type,
                subclass_type_filter=subclass_type_filter,
                when=when,
                decorated_arg=decorated_arg,
                dependency_config=dependency_config,
                registration_filter=registration_filter,
                decorator_node_filter=decorator_node_filter,
                position=position,
            )
        )

    def apply_bundle(self, bundle: Callable[[Any], None]) -> None:
        self._assert_mutable()
        bundle(self)

    def _preview_components(self, service_type: Any) -> tuple[Component, ...]:
        self._assert_mutable()
        plan = _Compiler(_Blueprint((self._layer(),))).compile()
        return tuple(item.component for item in plan.roots.get(service_type, ()))

    def has_component(self, service_type: Any, filter: ComponentFilter = default_component_filter) -> bool:
        return any(filter(component) for component in self._preview_components(service_type))

    def get_component_ids(
        self,
        service_type: Any,
        *,
        filter: ComponentFilter = default_component_filter,
        list_modifier: ComponentListModifier = default_component_list_modifier,
    ) -> list[str]:
        components = list_modifier(
            [component for component in self._preview_components(service_type) if filter(component)]
        )
        return [component.id for component in components]

    def get_component_id(
        self,
        service_type: Any,
        *,
        filter: ComponentFilter = default_component_filter,
    ) -> str | None:
        return next(iter(self.get_component_ids(service_type, filter=filter)), None)


class ContainerBuilder(_BuilderBase):
    """Mutable root composition API. Call :meth:`build` exactly once."""

    def build(self) -> Container:
        self._assert_mutable()
        plan = _compile_with_report(_Blueprint((self._layer(),)))
        container = Container(plan, self._owner_token)
        self._built = True
        return container


class ScopeBuilder(_BuilderBase):
    """Compile a child scope with registrations layered over a runtime parent."""

    def __init__(self, parent: Scope):
        super().__init__()
        self._parent = parent

    def build(self) -> Scope:
        self._assert_mutable()
        blueprint = _Blueprint((self._layer(), *self._parent._plan.blueprint.layers))
        plan = _compile_with_report(
            blueprint,
            anchored_singleton_steps=_anchored_singletons(self._parent._plan),
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
