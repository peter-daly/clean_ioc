"""Private sealed-container compiler experiment.

This module deliberately lives outside :mod:`clean_ioc` so the prototype does
not become part of the distributed package or its public compatibility surface.
"""

from __future__ import annotations

import asyncio
import inspect
import time
from dataclasses import dataclass
from typing import Any, TypeVar, cast, get_args

from clean_ioc.core import (
    EMPTY,
    AsyncFactoryActivator,
    AsyncGeneratorActivator,
    ChildScope,
    Container,
    CurrentGraph,
    Decorator,
    Dependency,
    DependencyContext,
    DependencyGraph,
    DependencyNode,
    DependencySettings,
    Lifespan,
    PreConfiguration,
    RegistrationFilter,
    Registrator,
    Resolver,
    Scope,
    ScopeCreator,
    _Registration,
    _ResolvingContext,
    default_decorated_node_filter,
    default_parameter_value_factory,
    default_parent_node_filter,
    default_registration_filter,
    default_registration_list_modifier,
    type_expected_to_be_scoped,
)
from clean_ioc.diagnostics import ValidationReport
from clean_ioc.value_factories import dont_use_default_value, use_default_value

TService = TypeVar("TService")

_SCOPE_SELF_TYPES = frozenset({Scope, Resolver, Registrator, ScopeCreator})


class SealedContainerError(RuntimeError):
    """Raised when root composition is changed after compilation."""


class _UnsupportedCompilationError(Exception):
    pass


@dataclass(frozen=True)
class CompilationFallback:
    service_type: Any
    reason: str


@dataclass(frozen=True)
class CompilationReport:
    validation: ValidationReport
    duration_s: float
    candidate_roots: int
    async_compiled_roots: int
    sync_compiled_roots: int
    fallbacks: tuple[CompilationFallback, ...]

    @property
    def fallback_roots(self) -> int:
        return len(self.fallbacks)


class _CompiledStep:
    sync_supported = True

    def resolve(self, context: _ResolvingContext, parent_node: DependencyNode) -> Any:
        raise NotImplementedError

    async def resolve_async(self, context: _ResolvingContext, parent_node: DependencyNode) -> Any:
        raise NotImplementedError


@dataclass(frozen=True)
class _ValueStep(_CompiledStep):
    value: Any

    def resolve(self, context: _ResolvingContext, parent_node: DependencyNode) -> Any:
        return self.value

    async def resolve_async(self, context: _ResolvingContext, parent_node: DependencyNode) -> Any:
        return self.value


@dataclass(frozen=True)
class _DependencyContextStep(_CompiledStep):
    name: str

    def resolve(self, context: _ResolvingContext, parent_node: DependencyNode) -> DependencyContext:
        return DependencyContext(name=self.name, dependency_node=parent_node)

    async def resolve_async(
        self,
        context: _ResolvingContext,
        parent_node: DependencyNode,
    ) -> DependencyContext:
        return self.resolve(context, parent_node)


@dataclass(frozen=True)
class _ScopeSelfStep(_CompiledStep):
    dependency: Dependency

    def _find_registration(
        self,
        context: _ResolvingContext,
        parent_node: DependencyNode,
    ) -> _Registration:
        return context.find_registration(
            service_type=cast(type, self.dependency.service_type),
            registration_filter=self.dependency.settings.filter,
            parent_node=parent_node,
        )

    def resolve(self, context: _ResolvingContext, parent_node: DependencyNode) -> Scope:
        with self.dependency._propagate_resolve_error():
            registration = self._find_registration(context, parent_node)
            return cast(Scope, registration.build(context, parent_node))

    async def resolve_async(self, context: _ResolvingContext, parent_node: DependencyNode) -> Scope:
        with self.dependency._propagate_resolve_error():
            registration = self._find_registration(context, parent_node)
            return cast(Scope, await registration.build_async(context, parent_node))


@dataclass(frozen=True)
class _ScopeSlotStep(_CompiledStep):
    dependency: Dependency

    def _find_registration(
        self,
        context: _ResolvingContext,
        parent_node: DependencyNode,
    ) -> _Registration:
        return context.find_registration(
            service_type=cast(type, self.dependency.service_type),
            registration_filter=self.dependency.settings.filter,
            parent_node=parent_node,
        )

    def resolve(self, context: _ResolvingContext, parent_node: DependencyNode) -> Any:
        with self.dependency._propagate_resolve_error():
            return self._find_registration(context, parent_node).build(context, parent_node)

    async def resolve_async(self, context: _ResolvingContext, parent_node: DependencyNode) -> Any:
        with self.dependency._propagate_resolve_error():
            registration = self._find_registration(context, parent_node)
            return await registration.build_async(context, parent_node)


@dataclass(frozen=True)
class _CollectionStep(_CompiledStep):
    service_type: Any
    collection_type: type
    members: tuple[_CompiledStep, ...]

    @property
    def sync_supported(self) -> bool:
        return all(member.sync_supported for member in self.members)

    def _node(self, parent_node: DependencyNode) -> DependencyNode:
        node = DependencyNode(
            service_type=cast(type, self.service_type),
            implementation=self.collection_type,
            lifespan=Lifespan.transient,
        )
        parent_node.add_child(node)
        return node

    def resolve(self, context: _ResolvingContext, parent_node: DependencyNode) -> Any:
        node = self._node(parent_node)
        value = self.collection_type(member.resolve(context, node) for member in self.members)
        node.set_instance(value)
        return value

    async def resolve_async(self, context: _ResolvingContext, parent_node: DependencyNode) -> Any:
        node = self._node(parent_node)
        values = await asyncio.gather(*(member.resolve_async(context, node) for member in self.members))
        value = self.collection_type(values)
        node.set_instance(value)
        return value


@dataclass(frozen=True)
class _CompiledDependency:
    name: str
    step: _CompiledStep


@dataclass(frozen=True)
class _CompiledPreConfiguration:
    source: PreConfiguration
    dependencies: tuple[_CompiledDependency, ...]

    @property
    def sync_supported(self) -> bool:
        return not _requires_async(self.source.activator_class, self.source.configuration_fn) and all(
            dependency.step.sync_supported for dependency in self.dependencies
        )

    def run(self, context: _ResolvingContext, node: DependencyNode) -> None:
        if self.source.has_run:
            return
        resolved = {item.name: item.step.resolve(context, node) for item in self.dependencies}
        with self.source._run_safely():
            self.source.activator_class.activate(
                self.source.configuration_fn,
                resolved,
                context,
                Lifespan.scoped,
            )

    async def run_async(self, context: _ResolvingContext, node: DependencyNode) -> None:
        if self.source.has_run:
            return
        resolved = {item.name: await item.step.resolve_async(context, node) for item in self.dependencies}
        with self.source._run_safely():
            await self.source.activator_class.activate_async(
                self.source.configuration_fn,
                resolved,
                context,
                Lifespan.scoped,
            )


@dataclass(frozen=True)
class _CompiledDecorator:
    source: Decorator
    dependencies: tuple[_CompiledDependency, ...]

    @property
    def sync_supported(self) -> bool:
        return not _requires_async(self.source.activator_class, self.source.decorator_type) and all(
            dependency.step.sync_supported for dependency in self.dependencies
        )

    def decorate(
        self,
        instance: Any,
        context: _ResolvingContext,
        node: DependencyNode,
        registration: _Registration,
    ) -> Any:
        with self.source._propagate_resolve_error():
            resolved = {item.name: item.step.resolve(context, node) for item in self.dependencies}
            resolved[self.source.decorated_arg] = instance
            return self.source.activator_class.activate(
                self.source.decorator_type,
                resolved,
                context,
                lifespan=registration.lifespan,
            )

    async def decorate_async(
        self,
        instance: Any,
        context: _ResolvingContext,
        node: DependencyNode,
        registration: _Registration,
    ) -> Any:
        with self.source._propagate_resolve_error():
            resolved = {item.name: await item.step.resolve_async(context, node) for item in self.dependencies}
            resolved[self.source.decorated_arg] = instance
            return await self.source.activator_class.activate_async(
                self.source.decorator_type,
                resolved,
                context,
                lifespan=registration.lifespan,
            )


@dataclass(frozen=True)
class _CompiledRegistrationStep(_CompiledStep):
    registration: _Registration
    dependencies: tuple[_CompiledDependency, ...]
    pre_configurations: tuple[_CompiledPreConfiguration, ...]
    decorators: tuple[_CompiledDecorator, ...]

    @property
    def sync_supported(self) -> bool:
        return (
            not _requires_async(self.registration.activator_class, self.registration.implementation)
            and all(item.step.sync_supported for item in self.dependencies)
            and all(item.sync_supported for item in self.pre_configurations)
            and all(item.sync_supported for item in self.decorators)
        )

    def _new_node(self, parent_node: DependencyNode) -> DependencyNode:
        return self.registration._create_new_dependency_node(parent_node)

    def _run_pre_configurations(self, context: _ResolvingContext, node: DependencyNode) -> None:
        for compiled in self.pre_configurations:
            if compiled.source.has_run:
                continue
            pre_node = DependencyNode(
                self.registration.service_type,
                compiled.source.configuration_fn,
                lifespan=Lifespan.singleton,
            )
            node.add_pre_configuration(pre_node)
            compiled.run(context, pre_node)
            pre_node.set_instance(compiled.source)

    async def _run_pre_configurations_async(
        self,
        context: _ResolvingContext,
        node: DependencyNode,
    ) -> None:
        for compiled in self.pre_configurations:
            if compiled.source.has_run:
                continue
            pre_node = DependencyNode(
                self.registration.service_type,
                compiled.source.configuration_fn,
                lifespan=Lifespan.singleton,
            )
            node.add_pre_configuration(pre_node)
            await compiled.run_async(context, pre_node)
            pre_node.set_instance(compiled.source)

    def _decorate(self, instance: Any, context: _ResolvingContext, node: DependencyNode) -> tuple[Any, DependencyNode]:
        top = node
        for compiled in self.decorators:
            decorator_node = DependencyNode(
                service_type=self.registration.service_type,
                implementation=compiled.source.decorator_type,
                lifespan=self.registration.lifespan,
            )
            top.add_decorator(decorator_node)
            instance = compiled.decorate(instance, context, decorator_node, self.registration)
            decorator_node.set_instance(instance)
            top = decorator_node
        return instance, top

    async def _decorate_async(
        self,
        instance: Any,
        context: _ResolvingContext,
        node: DependencyNode,
    ) -> tuple[Any, DependencyNode]:
        top = node
        for compiled in self.decorators:
            decorator_node = DependencyNode(
                service_type=self.registration.service_type,
                implementation=compiled.source.decorator_type,
                lifespan=self.registration.lifespan,
            )
            top.add_decorator(decorator_node)
            instance = await compiled.decorate_async(instance, context, decorator_node, self.registration)
            decorator_node.set_instance(instance)
            top = decorator_node
        return instance, top

    def _build_uncached(self, context: _ResolvingContext, parent_node: DependencyNode) -> Any:
        node = self._new_node(parent_node)
        self._run_pre_configurations(context, node)
        resolved = {item.name: item.step.resolve(context, node) for item in self.dependencies}
        instance = self.registration.activator_class.activate(
            self.registration.implementation,
            resolved,
            context,
            lifespan=self.registration.lifespan,
        )
        node.set_instance(instance)
        instance, top = self._decorate(instance, context, node)
        context.new_instance_created(self.registration, top)
        self.registration.was_used = True
        return instance

    async def _build_uncached_async(self, context: _ResolvingContext, parent_node: DependencyNode) -> Any:
        node = self._new_node(parent_node)
        await self._run_pre_configurations_async(context, node)
        resolved = {item.name: await item.step.resolve_async(context, node) for item in self.dependencies}
        instance = await self.registration.activator_class.activate_async(
            self.registration.implementation,
            resolved,
            context,
            lifespan=self.registration.lifespan,
        )
        node.set_instance(instance)
        instance, top = await self._decorate_async(instance, context, node)
        context.new_instance_created(self.registration, top)
        self.registration.was_used = True
        return instance

    def resolve(self, context: _ResolvingContext, parent_node: DependencyNode) -> Any:
        registration = self.registration
        with registration._propagate_resolve_error():
            context.assert_registration_allowed(registration)
            is_cached, cached = registration._try_find_cached_node(
                context,
                parent_node,
            )
            if is_cached:
                return cached

            future, is_builder = context.begin_shared_build(registration)
            if future is not None and not is_builder:
                outcome = future.result()
                if outcome.error is not None:
                    raise outcome.error
                is_cached, cached = registration._try_find_cached_node(
                    context,
                    parent_node,
                )
                if not is_cached:
                    raise RuntimeError(f"Shared dependency {registration.id} completed without a cached instance")
                return cached

            try:
                with context.enter_registration(registration):
                    instance = self._build_uncached(context, parent_node)
            except BaseException as error:
                context.finish_shared_build(registration, future, error)
                raise

            context.finish_shared_build(registration, future)
            return instance

    async def resolve_async(self, context: _ResolvingContext, parent_node: DependencyNode) -> Any:
        registration = self.registration
        with registration._propagate_resolve_error():
            context.assert_registration_allowed(registration)
            is_cached, cached = registration._try_find_cached_node(
                context,
                parent_node,
            )
            if is_cached:
                return cached

            future, is_builder = context.begin_shared_build(registration)
            if future is not None and not is_builder:
                outcome = await asyncio.shield(asyncio.wrap_future(future))
                if outcome.error is not None:
                    raise outcome.error
                is_cached, cached = registration._try_find_cached_node(
                    context,
                    parent_node,
                )
                if not is_cached:
                    raise RuntimeError(f"Shared dependency {registration.id} completed without a cached instance")
                return cached

            try:
                with context.enter_registration(registration):
                    instance = await self._build_uncached_async(context, parent_node)
            except BaseException as error:
                context.finish_shared_build(registration, future, error)
                raise

            context.finish_shared_build(registration, future)
            return instance


@dataclass(frozen=True)
class _CompiledRoot:
    service_type: Any
    step: _CompiledStep

    @property
    def sync_supported(self) -> bool:
        return self.step.sync_supported

    def resolve(self, scope: Scope) -> Any:
        root = DependencyNode(
            service_type=cast(type, self.service_type),
            implementation=DependencyGraph,
            lifespan=Lifespan.once_per_graph,
        )
        context = _ResolvingContext(scope)
        try:
            return self.step.resolve(context, root)
        finally:
            del context

    async def resolve_async(self, scope: Scope) -> Any:
        root = DependencyNode(
            service_type=cast(type, self.service_type),
            implementation=DependencyGraph,
            lifespan=Lifespan.once_per_graph,
        )
        context = _ResolvingContext(scope)
        try:
            return await self.step.resolve_async(context, root)
        finally:
            del context


def _requires_async(activator_class: type, implementation: Any) -> bool:
    if activator_class in (AsyncFactoryActivator, AsyncGeneratorActivator):
        return True
    wrapped = getattr(implementation, "__wrapped__", None)
    return wrapped is not None and (inspect.iscoroutinefunction(wrapped) or inspect.isasyncgenfunction(wrapped))


class _Compiler:
    def __init__(self, container: CompiledContainer):
        self.container = container
        self._registration_cache: dict[str, _CompiledRegistrationStep] = {}
        self._stack: set[str] = set()

    def compile_root(self, service_type: Any) -> _CompiledRoot:
        parent = DependencyNode(
            service_type=cast(type, service_type),
            implementation=DependencyGraph,
            lifespan=Lifespan.once_per_graph,
        )
        dependency = Dependency(
            name="__ROOT__",
            parent_implementation=DependencyGraph,
            service_type=service_type,
            settings=DependencySettings(),
            default_value=EMPTY,
        )
        return _CompiledRoot(service_type=service_type, step=self._compile_dependency(dependency, parent))

    def _raw_registrations(self, service_type: Any) -> list[_Registration]:
        return list(self.container._registry.get_registrations(service_type))

    def _select_registrations(
        self,
        dependency: Dependency,
        parent_node: DependencyNode,
    ) -> list[_Registration]:
        raw = [
            registration
            for registration in self._raw_registrations(dependency.service_type)
            if dependency.settings.filter(registration)
        ]
        if any(registration.parent_node_filter is not default_parent_node_filter for registration in raw):
            raise _UnsupportedCompilationError("custom parent-node filter")

        registrations = self.container.find_registrations(
            service_type=dependency.service_type,
            filter=dependency.settings.filter,
            list_modifier=dependency.settings.list_modifier,
            parent_node=parent_node,
        )
        return registrations

    def _compile_dependency(self, dependency: Dependency, parent_node: DependencyNode) -> _CompiledStep:
        value_factory = dependency.settings.value_factory
        if value_factory is default_parameter_value_factory:
            if dependency.default_value is not EMPTY:
                return _ValueStep(dependency.default_value)
        elif value_factory is use_default_value:
            if dependency.default_value is not EMPTY:
                return _ValueStep(dependency.default_value)
        elif value_factory is not dont_use_default_value:
            raise _UnsupportedCompilationError("custom value provider")

        if dependency.service_type is DependencyContext:
            return _DependencyContextStep(dependency.name)
        if dependency.service_type in _SCOPE_SELF_TYPES:
            if dependency.settings.filter is not default_registration_filter:
                raise _UnsupportedCompilationError("custom scope-self filter")
            if dependency.settings.list_modifier is not default_registration_list_modifier:
                raise _UnsupportedCompilationError("custom scope-self registration modifier")
            return _ScopeSelfStep(dependency)
        if dependency.service_type is CurrentGraph:
            raise _UnsupportedCompilationError("CurrentGraph dependency")

        if dependency.generic_collection_type:
            if dependency.settings.filter is not default_registration_filter:
                raise _UnsupportedCompilationError("filtered collection dependency")
            if dependency.settings.list_modifier is not default_registration_list_modifier:
                raise _UnsupportedCompilationError("custom collection modifier")
            element_type = get_args(dependency.service_type)[0]
            element_dependency = Dependency(
                name=dependency.name,
                parent_implementation=dependency.parent_implementation,
                service_type=element_type,
                settings=dependency.settings,
                default_value=EMPTY,
            )
            registrations = self._select_registrations(element_dependency, parent_node)
            if any(registration.id in self.container._scope_slot_ids for registration in registrations):
                raise _UnsupportedCompilationError("collection containing a scope slot")
            members = tuple(self._compile_registration(registration) for registration in registrations)
            return _CollectionStep(
                service_type=dependency.service_type,
                collection_type=dependency.generic_collection_type,
                members=members,
            )

        registrations = self._select_registrations(dependency, parent_node)
        registration = next(iter(registrations), None)
        if registration is None:
            origin = getattr(dependency.service_type, "__origin__", None)
            if origin is not None and self._raw_registrations(origin):
                raise _UnsupportedCompilationError("open-generic fallback")
            raise _UnsupportedCompilationError("no matching registration")

        if registration.id in self.container._scope_slot_ids:
            return _ScopeSlotStep(dependency)
        if dependency.settings.filter is not default_registration_filter:
            raise _UnsupportedCompilationError("custom dependency filter")
        if dependency.settings.list_modifier is not default_registration_list_modifier:
            raise _UnsupportedCompilationError("custom registration modifier")
        return self._compile_registration(registration)

    def _compile_dependencies(
        self,
        dependencies: dict[str, Dependency],
        parent_node: DependencyNode,
    ) -> tuple[_CompiledDependency, ...]:
        return tuple(
            _CompiledDependency(name=name, step=self._compile_dependency(dependency, parent_node))
            for name, dependency in dependencies.items()
        )

    def _compile_pre_configurations(
        self,
        registration: _Registration,
        parent_node: DependencyNode,
    ) -> tuple[_CompiledPreConfiguration, ...]:
        candidates = list(self.container._registry.get_pre_configurations(registration.service_type))
        if any(candidate.registration_filter is not default_registration_filter for candidate in candidates):
            raise _UnsupportedCompilationError("custom pre-configuration filter")
        return tuple(
            _CompiledPreConfiguration(
                source=candidate,
                dependencies=self._compile_dependencies(candidate.dependencies, parent_node),
            )
            for candidate in candidates
            if not candidate.has_run and candidate.registration_filter(registration)
        )

    def _compile_decorators(
        self,
        registration: _Registration,
        parent_node: DependencyNode,
    ) -> tuple[_CompiledDecorator, ...]:
        candidates = list(self.container._registry.get_decorators(registration.service_type))
        if any(candidate.registration_filter is not default_registration_filter for candidate in candidates):
            raise _UnsupportedCompilationError("custom decorator registration filter")
        if any(candidate.decorated_node_filter is not default_decorated_node_filter for candidate in candidates):
            raise _UnsupportedCompilationError("custom decorator node filter")
        return tuple(
            _CompiledDecorator(
                source=candidate,
                dependencies=self._compile_dependencies(candidate.dependencies, parent_node),
            )
            for candidate in candidates
            if candidate.registration_filter(registration)
        )

    def _compile_registration(self, registration: _Registration) -> _CompiledRegistrationStep:
        cached = self._registration_cache.get(registration.id)
        if cached is not None:
            return cached
        if registration.id in self._stack:
            raise _UnsupportedCompilationError("circular dependency")
        if registration.parent_node_filter is not default_parent_node_filter:
            raise _UnsupportedCompilationError("custom parent-node filter")

        self._stack.add(registration.id)
        try:
            parent_node = DependencyNode(
                service_type=registration.service_type,
                implementation=registration.implementation,
                lifespan=registration.lifespan,
                registration_name=registration.name,
                registration_tags=registration.tags,
            )
            compiled = _CompiledRegistrationStep(
                registration=registration,
                dependencies=self._compile_dependencies(registration.dependencies, parent_node),
                pre_configurations=self._compile_pre_configurations(registration, parent_node),
                decorators=self._compile_decorators(registration, parent_node),
            )
            self._registration_cache[registration.id] = compiled
            return compiled
        finally:
            self._stack.remove(registration.id)


class _CompiledScopeMixin:
    _compiler_owner: CompiledContainer
    _compiled_eligible: bool

    def _resolve_compiled(
        self,
        service_type: type[TService],
        filter: RegistrationFilter,
    ) -> TService:
        owner = self._compiler_owner
        if owner.is_sealed and self._compiled_eligible and filter is default_registration_filter:
            plan = owner._compiled_roots.get(service_type)
            if plan is not None and plan.sync_supported:
                return cast(TService, plan.resolve(cast(Scope, self)))
        return Scope.resolve(cast(Scope, self), service_type, filter=filter)

    async def _resolve_compiled_async(
        self,
        service_type: type[TService],
        filter: RegistrationFilter,
    ) -> TService:
        owner = self._compiler_owner
        if owner.is_sealed and self._compiled_eligible and filter is default_registration_filter:
            plan = owner._compiled_roots.get(service_type)
            if plan is not None:
                return cast(TService, await plan.resolve_async(cast(Scope, self)))
        return await Scope.resolve_async(cast(Scope, self), service_type, filter=filter)


class CompiledChildScope(_CompiledScopeMixin, ChildScope):
    """Child scope that reuses sealed parent plans when its overlay is declared."""

    def __init__(self, parent_scope: Scope, compiler_owner: CompiledContainer, *, eligible: bool):
        self._compiler_owner = compiler_owner
        self._compiled_eligible = eligible
        self._initializing = True
        super().__init__(parent_scope)
        self._initializing = False

    def register(self, *args: Any, **kwargs: Any) -> str:
        registration_id = super().register(*args, **kwargs)
        if not self._initializing:
            service_type = args[0] if args else kwargs["service_type"]
            name = kwargs.get("name")
            if (service_type, name) not in self._compiler_owner._scope_slots:
                self._compiled_eligible = False
        return registration_id

    def patch_registration(self, *args: Any, **kwargs: Any) -> None:
        self._compiled_eligible = False
        super().patch_registration(*args, **kwargs)

    def pre_configure(self, *args: Any, **kwargs: Any) -> None:
        self._compiled_eligible = False
        super().pre_configure(*args, **kwargs)

    def register_decorator(self, *args: Any, **kwargs: Any) -> None:
        self._compiled_eligible = False
        super().register_decorator(*args, **kwargs)

    def resolve(
        self,
        service_type: type[TService],
        filter: RegistrationFilter = default_registration_filter,
    ) -> TService:
        return self._resolve_compiled(service_type, filter)

    async def resolve_async(
        self,
        service_type: type[TService],
        filter: RegistrationFilter = default_registration_filter,
    ) -> TService:
        return await self._resolve_compiled_async(service_type, filter)

    def new_scope(self) -> Scope:
        return CompiledChildScope(
            self,
            self._compiler_owner,
            eligible=self._compiled_eligible,
        )


class CompiledContainer(_CompiledScopeMixin, Container):
    """Internal opt-in container that compiles its registry when sealed."""

    def __init__(self):
        self._sealed = False
        self._sealing = False
        self._compiled_roots: dict[Any, _CompiledRoot] = {}
        self._scope_slots: set[tuple[Any, str | None]] = set()
        self._scope_slot_ids: set[str] = set()
        self._compilation_report: CompilationReport | None = None
        self._compiler_owner = self
        self._compiled_eligible = True
        super().__init__()

    @property
    def is_sealed(self) -> bool:
        return self._sealed

    @property
    def compilation_report(self) -> CompilationReport | None:
        return self._compilation_report

    def _assert_mutable(self) -> None:
        if self._sealed and not self._sealing:
            raise SealedContainerError("The experimental container is sealed")

    def register(self, *args: Any, **kwargs: Any) -> str:
        self._assert_mutable()
        return super().register(*args, **kwargs)

    def patch_registration(self, *args: Any, **kwargs: Any) -> None:
        self._assert_mutable()
        super().patch_registration(*args, **kwargs)

    def pre_configure(self, *args: Any, **kwargs: Any) -> None:
        self._assert_mutable()
        super().pre_configure(*args, **kwargs)

    def register_decorator(self, *args: Any, **kwargs: Any) -> None:
        self._assert_mutable()
        super().register_decorator(*args, **kwargs)

    def expect_to_be_scoped(self, service_type: type, name: str | None = None) -> CompiledContainer:
        self._assert_mutable()
        registration_id = self.register(
            service_type=service_type,
            factory=type_expected_to_be_scoped(service_type, name),
            lifespan=Lifespan.scoped,
            name=name,
        )
        self._scope_slots.add((service_type, name))
        self._scope_slot_ids.add(registration_id)
        return self

    def has_scope_slot(self, service_type: type, name: str | None = None) -> bool:
        return (service_type, name) in self._scope_slots

    def _candidate_root_types(self) -> tuple[Any, ...]:
        candidates: list[Any] = []
        for service_type, registrations in self._registry._registrations.items():
            if any(default_registration_filter(registration) for registration in registrations):
                candidates.append(service_type)
        return tuple(dict.fromkeys(candidates))

    def seal(self) -> CompilationReport:
        if self._compilation_report is not None:
            return self._compilation_report

        started = time.perf_counter()
        self._sealing = True
        try:
            candidates = self._candidate_root_types()
            validation = self.validate(*candidates)
            compiler = _Compiler(self)
            compiled: dict[Any, _CompiledRoot] = {}
            fallbacks: list[CompilationFallback] = []
            for service_type in candidates:
                try:
                    compiled[service_type] = compiler.compile_root(service_type)
                except _UnsupportedCompilationError as error:
                    fallbacks.append(CompilationFallback(service_type=service_type, reason=str(error)))

            report = CompilationReport(
                validation=validation,
                duration_s=time.perf_counter() - started,
                candidate_roots=len(candidates),
                async_compiled_roots=len(compiled),
                sync_compiled_roots=sum(plan.sync_supported for plan in compiled.values()),
                fallbacks=tuple(fallbacks),
            )
            self._compiled_roots = compiled
            self._compilation_report = report
            self._sealed = True
            return report
        finally:
            self._sealing = False

    def resolve(
        self,
        service_type: type[TService],
        filter: RegistrationFilter = default_registration_filter,
    ) -> TService:
        return self._resolve_compiled(service_type, filter)

    async def resolve_async(
        self,
        service_type: type[TService],
        filter: RegistrationFilter = default_registration_filter,
    ) -> TService:
        return await self._resolve_compiled_async(service_type, filter)

    def new_scope(self) -> Scope:
        return CompiledChildScope(self, self, eligible=True)
