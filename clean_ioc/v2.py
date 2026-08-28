"""Build-time composition and graph-free runtime for Clean IoC 2."""

from __future__ import annotations

import asyncio
import concurrent.futures
import inspect
import threading
from collections import deque
from collections.abc import Callable, Iterable
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, TypeVar, cast, get_args, get_origin
from uuid import uuid4

from . import core as legacy
from .components import (
    Component,
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

TService = TypeVar("TService")


class BuilderAlreadyBuiltError(RuntimeError):
    pass


class ContainerBuildError(RuntimeError):
    pass


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
class _Layer:
    registry: legacy._Registry
    internal_ids: frozenset[str]
    owner_token: str
    registration_when: dict[str, ComponentFilter]
    decorator_when: dict[int, ComponentFilter]
    pre_configuration_when: dict[int, ComponentFilter]
    pre_configuration_states: dict[int, _PreConfigurationState]
    slots: frozenset[tuple[Any, str | None]]


@dataclass(frozen=True, slots=True)
class _Blueprint:
    layers: tuple[_Layer, ...]

    @property
    def slots(self) -> frozenset[tuple[Any, str | None]]:
        return frozenset(slot for layer in self.layers for slot in layer.slots)

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


def _requires_async(activator_class: type, implementation: Any) -> bool:
    if activator_class in (legacy.AsyncFactoryActivator, legacy.AsyncGeneratorActivator):
        return True
    wrapped = getattr(implementation, "__wrapped__", None)
    return wrapped is not None and (inspect.iscoroutinefunction(wrapped) or inspect.isasyncgenfunction(wrapped))


class _Compiler:
    def __init__(self, blueprint: _Blueprint):
        self.blueprint = blueprint
        self.graph = _ComponentGraph()
        self._next_occurrence = 1
        self._stack: list[legacy._Registration] = []

    def compile(self) -> _PlanSet:
        roots: dict[Any, tuple[_RootPlan, ...]] = {}
        for service_type in self.blueprint.service_types():
            # Open generic registrations are reusable activation templates, not
            # directly resolvable roots. Closed occurrences compile on demand
            # from the concrete services discovered by the builder.
            if getattr(service_type, "__parameters__", ()):
                continue
            candidates = self._compile_candidates(service_type, parent=None, argument=None)
            roots[service_type] = tuple(_RootPlan(component=component, step=step) for component, step in candidates)
        self.graph.freeze()
        return _PlanSet(graph=self.graph, roots=roots, blueprint=self.blueprint)

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
        parent: Component | None,
        argument: str | None = None,
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
        for registration, layer in registrations:
            component, step = self._compile_registration(
                registration,
                layer,
                parent=parent,
                argument=argument,
                requested_service_type=service_type,
            )
            predicate = layer.registration_when.get(registration.id)
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
        if registration in self._stack:
            path = " -> ".join(str(item.service_type) for item in (*self._stack, registration))
            raise ContainerBuildError(f"Circular component dependency: {path}")
        singleton = next((item for item in self._stack if item.lifespan == legacy.Lifespan.singleton), None)
        if singleton is not None and registration.lifespan == legacy.Lifespan.scoped and not registration.is_instance:
            raise ContainerBuildError(
                f"Singleton {singleton.service_type} cannot retain scoped {registration.service_type}"
            )

        component, draft = self._draft(
            component_id=registration.id,
            service_type=requested_service_type,
            implementation=registration.implementation,
            lifespan=registration.lifespan,
            name=registration.name,
            tags=registration.tags,
            kind=ComponentKind.registration,
            parent=parent,
            argument=argument,
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
            return _ValueStep(value), None

        if dependency.service_type in (DependencyContext, legacy.DependencyContext):
            return _DependencyContextStep(dependency.name, parent), None
        if dependency.service_type in (
            Scope,
            Container,
            ResolutionContext,
            legacy.Scope,
            legacy.Resolver,
            legacy.ScopeCreator,
            legacy.CurrentGraph,
        ):
            return _ScopeStep(dependency.service_type), None

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
            component, step = candidates[0]
            if value_factory is not legacy.default_parameter_value_factory:
                return (
                    _ProviderStep(cast(Any, value_factory), dependency.default_value, dependency_context, step),
                    component,
                )
            return step, component

        slot = self._matching_slot(dependency.service_type, dependency.settings.filter, parent, dependency.name)
        if slot is not None:
            name, component = slot
            return _ProvidedStep(dependency.service_type, name), component
        if value_factory is not legacy.default_parameter_value_factory:
            return _ProviderStep(cast(Any, value_factory), dependency.default_value, dependency_context, None), None
        raise ContainerBuildError(
            f"No component for {dependency.service_type!r}, argument {dependency.name!r} of {parent.implementation!r}"
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
                kind=ComponentKind.registration,
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
                parent=parent,
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
                parent=core.parent,
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
        self._sync_teardowns: dict[str, tuple[Callable[..., Any], Any]] = {}
        self._async_teardowns: dict[str, tuple[Callable[..., Any], Any]] = {}
        self._closed = False

    def _remember(
        self,
        registration: legacy._Registration,
        value: Any,
    ) -> None:
        self._singletons[registration.id] = value
        if registration.scoped_teardown is not None:
            target = (
                self._async_teardowns
                if inspect.iscoroutinefunction(registration.scoped_teardown)
                else self._sync_teardowns
            )
            target[registration.id] = (registration.scoped_teardown, value)

    def _close(self) -> None:
        if self._closed:
            return
        for teardown, value in reversed(tuple(self._sync_teardowns.values())):
            teardown(value)
        for finalizer in self._finalizers:
            result = finalizer()
            if inspect.isawaitable(result):
                raise RuntimeError("Async finalizer requires async context management")
        self._closed = True

    async def _close_async(self) -> None:
        if self._closed:
            return
        for teardown, value in reversed(tuple(self._async_teardowns.values())):
            await teardown(value)
        for teardown, value in reversed(tuple(self._sync_teardowns.values())):
            teardown(value)
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
        if self.parent is not None:
            return self.parent._find_scoped(component_id)
        return False, None

    def _remember_scoped(self, registration: legacy._Registration, value: Any) -> None:
        self._scoped[registration.id] = value
        if registration.scoped_teardown is not None:
            target = (
                self._async_teardowns
                if inspect.iscoroutinefunction(registration.scoped_teardown)
                else self._sync_teardowns
            )
            target[registration.id] = (registration.scoped_teardown, value)

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
        self._decorator_when: dict[int, ComponentFilter] = {}
        self._pre_configuration_when: dict[int, ComponentFilter] = {}
        self._pre_configuration_states: dict[int, _PreConfigurationState] = {}
        self._slots: set[tuple[Any, str | None]] = set()
        self._built = False

    def _assert_mutable(self) -> None:
        if self._built:
            raise BuilderAlreadyBuiltError("Builders are single-use after a successful build")

    def _layer(self) -> _Layer:
        return _Layer(
            registry=self._composition._registry,
            internal_ids=self._internal_ids,
            owner_token=self._owner_token,
            registration_when=dict(self._registration_when),
            decorator_when=dict(self._decorator_when),
            pre_configuration_when=dict(self._pre_configuration_when),
            pre_configuration_states=dict(self._pre_configuration_states),
            slots=frozenset(self._slots),
        )

    def register(
        self,
        service_type: type[TService],
        implementation_type: type[TService] | None = None,
        *,
        factory: Callable[..., TService] | None = None,
        instance: TService | None = None,
        lifespan: legacy.Lifespan = legacy.Lifespan.once_per_graph,
        name: str | None = None,
        dependency_config: legacy.DependencyConfig = {},
        tags: Iterable[legacy.Tag] | None = None,
        when: ComponentFilter = all_components,
        parent_node_filter: Callable[[Any], bool] = legacy.default_parent_node_filter,
        scoped_teardown: Callable[[TService], Any] | None = None,
    ) -> str:
        self._assert_mutable()
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
            scoped_teardown=scoped_teardown,
        )
        self._registration_when[component_id] = when
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
        self._composition.patch_registration(
            service_type,
            component_id,
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

    def register_subclasses(self, *args: Any, **kwargs: Any) -> list[str]:
        self._assert_mutable()
        when = kwargs.pop("when", all_components)
        ids = self._composition.register_subclasses(*args, **kwargs)
        self._registration_when.update({component_id: when for component_id in ids})
        return ids

    def register_generic_subclasses(self, *args: Any, **kwargs: Any) -> list[str]:
        self._assert_mutable()
        when = kwargs.pop("when", all_components)
        before = {
            registration.id
            for registrations in self._composition._registry._registrations.values()
            for registration in registrations
        }
        ids = self._composition.register_generic_subclasses(*args, **kwargs)
        after = {
            registration.id
            for registrations in self._composition._registry._registrations.values()
            for registration in registrations
        }
        self._registration_when.update({component_id: when for component_id in after - before})
        return ids

    def register_generic_decorator(self, *args: Any, **kwargs: Any) -> None:
        self._assert_mutable()
        when = kwargs.pop("when", all_components)
        before = {id(decorator) for store in self._composition._registry._decorators.values() for decorator in store}
        self._composition.register_generic_decorator(*args, **kwargs)
        for store in self._composition._registry._decorators.values():
            for decorator in store:
                if id(decorator) not in before:
                    self._decorator_when[id(decorator)] = when

    def apply_bundle(self, bundle: Callable[[Any], None]) -> None:
        self._assert_mutable()
        bundle(self)

    def _preview_components(self, service_type: Any) -> tuple[Component, ...]:
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
        plan = _Compiler(_Blueprint((self._layer(),))).compile()
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
        plan = _Compiler(blueprint).compile()
        scope = Scope(
            plan,
            container=self._parent.container,
            parent=self._parent,
            owners=self._parent._owners,
            owned_token=self._owner_token,
        )
        self._built = True
        return scope
