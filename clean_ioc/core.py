"""Simple IOC container.
"""
from __future__ import annotations
import abc
import asyncio
from collections import defaultdict, deque
from dataclasses import dataclass
from functools import reduce
import types
from clean_ioc.utils import deprecated
from enum import IntEnum
from typing import Any, Sequence, Type, TypeVar, get_type_hints
from collections.abc import Callable
from typing import _GenericAlias  # type: ignore
from uuid import uuid4
from .functional_utils import constant, always_true
from .type_filters import is_abstract, name_starts_with
from .typing_utils import (
    GenericTypeMap,
    get_generic_bases,
    get_generic_types,
    get_subclasses,
    is_open_generic_type,
    try_to_complete_generic,
)
import inspect


TService = TypeVar("TService")


class SingletonMeta(type):
    __INSTANCE__ = None

    def __call__(cls, *args, **kwargs):
        if cls.__INSTANCE__ is None:
            cls.__INSTANCE__ = super().__call__(*args, **kwargs)

        return cls.__INSTANCE__


class _empty(metaclass=SingletonMeta):
    def __bool__(self):
        return False


class _unknown(metaclass=SingletonMeta):
    def __bool__(self):
        return False


EMPTY = _empty()
UNKNOWN = _unknown()


class ArgInfo:
    def __init__(self, name: str, arg_type: type, default_value: Any):
        self.name = name
        self.arg_type = arg_type
        self.default_value = (
            _empty() if default_value == inspect._empty else default_value
        )


def get_arg_info(
    subject: Callable, local_ns: dict = {}, global_ns: dict | None = None
) -> dict[str, ArgInfo]:
    arg_spec_fn = subject if inspect.isfunction(subject) else subject.__init__
    args = get_type_hints(arg_spec_fn, global_ns, local_ns)
    signature = inspect.signature(subject)
    d: dict[str, ArgInfo] = {}
    for name, param in signature.parameters.items():
        if "*" in str(param):
            continue
        d[name] = ArgInfo(name=name, arg_type=args[name], default_value=param.default)
    return d


def _default_registration_filter(r: Registration) -> bool:
    return not r.is_named


def _default_dependency_value_factory(default_value: Any, _: DependencyContext) -> Any:
    return default_value


_default_registration_list_reducing_filter = constant(True)
_default_parent_context_filter = constant(True)
_default_decorator_context_filter = constant(True)


@dataclass
class Tag:
    name: str
    value: str | None = None


class Lifespan(IntEnum):
    transient = 0
    once_per_graph = 1
    scoped = 2
    singleton = 3


class __Node__:
    service_type: type
    implementation: type | Callable
    parent: __Node__
    children: list[__Node__]
    decorator: __Node__
    decorated: __Node__
    pre_configured_by: __Node__
    pre_configures: __Node__
    registration_name: str | None = None
    instance: Any = UNKNOWN
    lifespan: Lifespan

    def unparent(self):
        self.parent = EmptyNode()
        if decorated := self.decorated:
            decorated.unparent()

        if pre_configures := self.pre_configured_by:
            pre_configures.pre_configures = EmptyNode()
            self.pre_configured_by = EmptyNode()

    @property
    def implementation_type(self):
        return (
            self.implementation
            if isinstance(self.implementation, type)
            else type(self.implementation)
        )

    @property
    def instance_type(self):
        return type(self.instance)

    @property
    def generic_mapping(self):
        return GenericTypeMap.from_type(self.service_type)

    @property
    def bottom_decorated_node(self):
        if not self.decorated:
            return self
        return self.decorated.bottom_decorated_node

    @property
    def top_decorated_node(self):
        if not self.decorator:
            return self
        return self.decorator.top_decorated_node

    def has_dependant_service_type(self, service_type: type) -> bool:
        for child in self.children:
            if child.service_type == service_type:
                return True
            if child.has_dependant_service_type(service_type):
                return True
        return False

    def has_dependant_implementation_type(self, implementation_type: type) -> bool:
        for child in self.children:
            if child.implementation_type == implementation_type:
                return True
            if child.has_dependant_implementation_type(implementation_type):
                return True
        return False

    def has_dependant_instance_type(self, instance_type: type) -> bool:
        for child in self.children:
            if child.instance_type == instance_type:
                return True
            if child.has_dependant_instance_type(instance_type):
                return True
        return False

    def __repr__(self) -> str:
        return f"{self.service_type}--{self.implementation}"


class EmptyNode(__Node__, metaclass=SingletonMeta):
    def __init__(self):
        self.service_type = _empty
        self.implementation = _empty
        self.parent = self
        self.decorated = self
        self.pre_configured_by = self
        self.registration_name = None
        self.instance = EMPTY
        self.lifespan = Lifespan.singleton

    def __bool__(self):
        return False

    @property
    def children(self):
        return ()


class DependencyNode(__Node__):
    def __init__(
        self,
        service_type: type,
        implementation: type | Callable,
        lifespan: Lifespan,
        registration_name: str | None = None,
    ):
        self.service_type = service_type
        self.implementation = implementation
        self.lifespan = lifespan
        self.registration_name: str | None = registration_name
        self.parent = EmptyNode()
        self.children = []
        self.decorated = EmptyNode()
        self.decorator = EmptyNode()
        self.pre_configured_by = EmptyNode()
        self.pre_configures = EmptyNode()
        self.instance = UNKNOWN

    def set_instance(self, instance: Any):
        if self.instance is UNKNOWN:
            self.instance = instance
        else:
            raise Exception("Cannot set instance on a node that already has one")

    def add_child(self, child_node: DependencyNode):
        self.children.append(child_node)
        child_node.parent = self

    def add_decorator(self, decorator_node: DependencyNode):
        self.decorator = decorator_node
        decorator_node.decorated = self
        decorator_node.parent = self.parent
        self.parent.children.append(decorator_node)
        self.parent.children.remove(self)

    def add_pre_configuration(self, pre_configuration_node: DependencyNode):
        self.pre_configured_by = pre_configuration_node
        pre_configuration_node.pre_configures = self


class DependencyGraph(DependencyNode):
    @staticmethod
    def __ROOT__():
        pass

    def __init__(self, service_type: type, filter: RegistrationFilter):
        dependency_settings = DependencySettings(filter=filter)
        self.root_dependency = Dependency(
            name="__ROOT__",
            parent_implementation=DependencyGraph.__ROOT__,
            service_type=service_type,
            settings=dependency_settings,
            default_value=_empty(),
        )

        super().__init__(
            service_type=service_type,
            implementation=DependencyGraph.__ROOT__,
            lifespan=Lifespan.once_per_graph,
        )

    def resolve(self, context: ResolvingContext):
        instance = self.root_dependency.resolve(context, self)
        self.set_instance(instance)
        return self

    async def resolve_async(self, context: ResolvingContext):
        instance = await self.root_dependency.resolve_async(context, self)
        self.set_instance(instance)
        return self


class DependencyContext:
    def __init__(self, name: str, dependency_node: DependencyNode):
        self.name = name
        self.service_type = dependency_node.service_type
        self.implementation = dependency_node.implementation
        self.parent = dependency_node.parent
        self.decorated = dependency_node.decorated


class ParentContext:
    def __init__(self, parent: DependencyNode):
        self.parent = parent


class DecoratorContext:
    def __init__(self, decorated: DependencyNode):
        self.decorated = decorated


class CannotResolveException(Exception):
    def __init__(self):
        self.dependencies: list[Dependency] = []

    def append(self, d: Dependency):
        self.dependencies.append(d)

    @staticmethod
    def print_dependency(d: Dependency):
        # Format the dependency information with ASCII box
        content = f"implementation: {d.parent_implementation}\ndependency_name: {d.name}\nservice_type: {d.service_type}"
        content_lines = content.split("\n")
        width = max(len(line) for line in content_lines)
        top_border = "┌" + "─" * (width + 2) + "┐"
        bottom_border = "└" + "─" * (width + 2) + "┘"
        padded_content = "\n".join(
            "│ " + line.ljust(width) + " │" for line in content_lines
        )
        return f"{top_border}\n{padded_content}\n{bottom_border}"

    @property
    def message(self):
        top_dependency = self.dependencies[0]
        return f"Failed to resolve {top_dependency.parent_implementation} could not find {top_dependency.service_type}"

    @property
    def dependency_chain(self):
        chain = ""
        arrow = "↑\n↑\n↑\n"

        for index, item in enumerate(self.dependencies):
            printer_item = CannotResolveException.print_dependency(item)
            if index == 0:
                chain += f"{printer_item}\n"
            else:
                # Adding fixed spacing before arrow for alignment, then adding the dependency
                chain += f"{arrow}{printer_item}\n"

        return chain

    def __str__(self):
        return f"\n{self.message}\n\n{"Dependency chain:"}\n{self.dependency_chain}"


class Dependency:
    def __init__(
        self,
        name: str,
        parent_implementation: Callable | type,
        service_type: Any,
        settings: DependencySettings,
        default_value: Any,
    ):
        self.name = name
        self.parent_implementation = parent_implementation
        if isinstance(parent_implementation, type):
            self.service_type = try_to_complete_generic(
                service_type, parent_implementation
            )
        else:
            self.service_type = service_type
        self.settings = settings
        self.is_dependency_context = service_type == DependencyContext
        generic_origin = getattr(self.service_type, "__origin__", None)

        if generic_origin and generic_origin in (list, tuple, set):
            self.generic_collection_type = generic_origin
        else:
            self.generic_collection_type = None

        self.default_value = default_value

    def resolve(self, context: ResolvingContext, dependency_node: DependencyNode):
        dependency_context = DependencyContext(
            name=self.name, dependency_node=dependency_node
        )
        value = self.settings.value_factory(self.default_value, dependency_context)

        if value is not EMPTY:
            return value

        if self.is_dependency_context:
            return DependencyContext(name=self.name, dependency_node=dependency_node)

        if self.generic_collection_type:
            regs = context.find_registrations(
                service_type=self.service_type.__args__[0],  # type: ignore
                registration_filter=self.settings.filter,
                registration_list_reducing_filter=self.settings.list_reducing_filter,
                parent_node=dependency_node,
            )
            sequence_node = DependencyNode(
                service_type=self.service_type,
                implementation=self.generic_collection_type,
                lifespan=Lifespan.transient,
            )

            dependency_node.add_child(sequence_node)

            generator = (r.build(context, sequence_node) for r in regs)
            collection = self.generic_collection_type(generator)
            sequence_node.set_instance(collection)

            return collection
        try:
            reg = context.find_registration(
                service_type=self.service_type,
                registration_filter=self.settings.filter,
                parent_node=dependency_node,
            )
            return reg.build(context, dependency_node)
        except CannotResolveException as ex:
            ex.append(self)
            raise ex

    async def resolve_async(
        self, context: ResolvingContext, dependency_node: DependencyNode
    ):
        dependency_context = DependencyContext(
            name=self.name, dependency_node=dependency_node
        )
        value = self.settings.value_factory(self.default_value, dependency_context)

        if value is not EMPTY:
            return value

        if self.is_dependency_context:
            return DependencyContext(name=self.name, dependency_node=dependency_node)

        if self.generic_collection_type:
            regs = context.find_registrations(
                service_type=self.service_type.__args__[0],  # type: ignore
                registration_filter=self.settings.filter,
                registration_list_reducing_filter=self.settings.list_reducing_filter,
                parent_node=dependency_node,
            )
            sequence_node = DependencyNode(
                service_type=self.service_type,
                implementation=self.generic_collection_type,
                lifespan=Lifespan.transient,
            )

            dependency_node.add_child(sequence_node)

            generator = (r.build_async(context, sequence_node) for r in regs)
            items = await asyncio.gather(*generator)
            collection = self.generic_collection_type(items)
            sequence_node.set_instance(collection)

            return collection
        try:
            reg = context.find_registration(
                service_type=self.service_type,
                registration_filter=self.settings.filter,
                parent_node=dependency_node,
            )
            return await reg.build_async(context, dependency_node)
        except CannotResolveException as ex:
            ex.append(self)
            raise ex


class ImplementationCreate(abc.ABC):
    @classmethod
    def create(
        cls,
        factory: Callable,
        resolved_dependencies: dict[str, Any],
        context: ResolvingContext,
    ) -> Any:
        ...

    @classmethod
    def create_async(
        cls,
        factory: Callable,
        resolved_dependencies: dict[str, Any],
        context: ResolvingContext,
    ) -> Any:
        ...


class FactoryCreate(ImplementationCreate):
    @classmethod
    def create(
        cls,
        factory: Callable,
        resolved_dependencies: dict[str, Any],
        context: ResolvingContext,
    ):
        return factory(**resolved_dependencies)

    @classmethod
    async def create_async(
        cls,
        factory: Callable,
        resolved_dependencies: dict[str, Any],
        context: ResolvingContext,
    ):
        return cls.create(factory, resolved_dependencies, context)


class GeneratorCreate(ImplementationCreate):
    @classmethod
    def _generator_close(cls, generator: types.GeneratorType):
        def inner():
            try:
                next(generator)
            except StopIteration:
                pass

        return inner

    @classmethod
    def create(
        cls,
        factory: Callable,
        resolved_dependencies: dict[str, Any],
        context: ResolvingContext,
    ):
        generator = factory(**resolved_dependencies)
        instance = next(generator)
        context.add_generator(cls._generator_close(generator))
        return instance

    @classmethod
    async def create_async(
        cls,
        factory: Callable,
        resolved_dependencies: dict[str, Any],
        context: ResolvingContext,
    ):
        return cls.create(factory, resolved_dependencies, context)


class AsyncFactoryCreate(ImplementationCreate):
    @classmethod
    def _generator_close(cls, generator: types.GeneratorType):
        def inner():
            try:
                next(generator)
            except StopIteration:
                pass

        return inner

    @classmethod
    def create(
        cls,
        factory: Callable,
        resolved_dependencies: dict[str, Any],
        context: ResolvingContext,
    ):
        raise Exception("Only async allowed")

    @classmethod
    async def create_async(
        cls,
        factory: Callable,
        resolved_dependencies: dict[str, Any],
        context: ResolvingContext,
    ):
        return await factory(**resolved_dependencies)


class AsyncGeneratorCreate(ImplementationCreate):
    @classmethod
    def _generator_close(cls, generator: types.AsyncGeneratorType):
        async def inner():
            try:
                await anext(generator)
            except StopAsyncIteration:
                pass

        return inner

    @classmethod
    def create(
        cls,
        factory: Callable,
        resolved_dependencies: dict[str, Any],
        context: ResolvingContext,
    ):
        raise Exception("Only async allowed")

    @classmethod
    async def create_async(
        cls,
        factory: Callable,
        resolved_dependencies: dict[str, Any],
        context: ResolvingContext,
    ):
        generator = factory(**resolved_dependencies)
        instance = await anext(generator)
        context.add_generator(cls._generator_close(generator))
        return instance


class ImplementationCreator:
    def __init__(
        self,
        creator_function: Callable,
        dependency_config: dict[str, DependencySettings] = {},
    ):
        self.dependency_config = defaultdict(DependencySettings, dependency_config)
        self.creator_function = creator_function
        self.dependencies: dict[str, Dependency] = self._get_dependencies(
            self.creator_function, self.dependency_config
        )
        self.create_class = self._get_create_class(creator_function)

    @classmethod
    def _get_create_class(
        cls, creator_function: Callable
    ) -> type[ImplementationCreate]:
        if inspect.iscoroutinefunction(creator_function):
            return AsyncFactoryCreate
        if inspect.isasyncgenfunction(creator_function):
            return AsyncGeneratorCreate
        if inspect.isgeneratorfunction(creator_function):
            return GeneratorCreate
        return FactoryCreate

    @classmethod
    def _get_default_value(cls, paramater: inspect.Parameter):
        default_value = EMPTY
        if not paramater.default == inspect._empty():
            default_value = paramater.default
        return default_value

    @classmethod
    def _get_dependencies(
        cls,
        creator_function: Callable,
        dependency_config: dict[str, DependencySettings],
    ) -> dict[str, Dependency]:
        args_infos = get_arg_info(creator_function)
        dependencies = {
            name: Dependency(
                name=name,
                parent_implementation=creator_function,
                service_type=arg_info.arg_type,
                settings=dependency_config[name],
                default_value=arg_info.default_value,
            )
            for name, arg_info in args_infos.items()
        }

        for extra_kwarg in set(dependency_config.keys()) ^ set(dependencies.keys()):
            dependencies[extra_kwarg] = Dependency(
                name=extra_kwarg,
                parent_implementation=creator_function,
                service_type=Any,
                settings=dependency_config[extra_kwarg],
                default_value=_empty(),
            )

        return dependencies

    def create(
        self,
        context: ResolvingContext,
        dependency_node: DependencyNode,
        **kwargs,
    ):
        for arg_name, arg_dep in self.dependencies.items():
            kwargs[arg_name] = arg_dep.resolve(context, dependency_node)

        return self.create_class.create(self.creator_function, kwargs, context)

    async def create_async(
        self,
        context: ResolvingContext,
        dependency_node: DependencyNode,
        **kwargs,
    ):
        for arg_name, arg_dep in self.dependencies.items():
            kwargs[arg_name] = await arg_dep.resolve_async(context, dependency_node)

        return await self.create_class.create_async(
            self.creator_function, kwargs, context
        )


class DecoratorCreator(ImplementationCreator):
    def __init__(
        self,
        service_type: type,
        decorator_type: type,
        decorated_arg: str | None,
        dependency_config: dict[str, DependencySettings] = {},
    ):
        self.service_type = service_type
        super().__init__(
            creator_function=decorator_type, dependency_config=dependency_config
        )

        self.decorated_arg = decorated_arg or next(
            name
            for name, dep in self.dependencies.items()
            if dep.service_type == service_type
        )
        self.dependencies = {
            name: dep
            for name, dep in self.dependencies.items()
            if name != self.decorated_arg
        }


class PreConfiguration:
    def __init__(
        self,
        service_type: type,
        pre_configuration: Callable[..., None],
        registration_filter: RegistrationFilter,
        dependency_config: dict[str, DependencySettings],
    ):
        self.service_type = service_type
        self.configuration_fn = pre_configuration
        self.filter = registration_filter
        self.dependency_config = dependency_config

        self.creator = ImplementationCreator(
            creator_function=self.configuration_fn,
            dependency_config=self.dependency_config,
        )

        self.id = str(uuid4())
        self.has_run = False

    def run(self, context: ResolvingContext, dependency_node: DependencyNode):
        self.creator.create(context=context, dependency_node=dependency_node)
        self.has_run = True

    async def run_async(
        self, context: ResolvingContext, dependency_node: DependencyNode
    ):
        await self.creator.create(context=context, dependency_node=dependency_node)
        self.has_run = True


class Decorator:
    def __init__(
        self,
        service_type: type,
        decorator_type: type,
        registration_filter: RegistrationFilter,
        decorator_context_filter: DecoratorContextFilter,
        decorated_arg: str | None,
        dependency_config: dict[str, DependencySettings] = {},
    ):
        self.service_type = service_type
        self.decorator_type = decorator_type
        self.creator = DecoratorCreator(
            service_type=service_type,
            decorator_type=decorator_type,
            decorated_arg=decorated_arg,
            dependency_config=dependency_config,
        )
        self.registration_filter = registration_filter
        self.decorator_context_filter = decorator_context_filter

    def decorate(
        self,
        instance: Any,
        context: ResolvingContext,
        dependency_node: DependencyNode,
    ):
        kwargs = {}
        kwargs[self.creator.decorated_arg] = instance
        return self.creator.create(context, dependency_node, **kwargs)


class Registration:
    def __init__(
        self,
        service_type: type,
        implementation: Callable,
        lifespan: Lifespan,
        name: str | None = None,
        dependency_config: dict[str, DependencySettings] = {},
        parent_context_filter: ParentContextFilter = _default_parent_context_filter,
        tags: list[Tag] | None = None,
        scoped_teardown: Callable | None = None,
    ):
        if scoped_teardown and not lifespan == Lifespan.scoped:
            raise ValueError("Scoped teardowns can only be used with scoped lifestyles")

        if lifespan == Lifespan.singleton and inspect.isgeneratorfunction(
            implementation
        ):
            raise ValueError("Generators cannot be singletons")
        self.service_type = service_type
        self.implementation = implementation
        self.creator = ImplementationCreator(
            creator_function=implementation, dependency_config=dependency_config
        )
        self.lifespan = lifespan
        self.name = name
        self.tags = tuple(tags) if tags else tuple()
        self.id = str(uuid4())
        self.parent_context_filter = parent_context_filter
        self.scoped_teardown = scoped_teardown
        self.was_used = False

    @property
    def generic_mapping(self):
        return GenericTypeMap.from_type(self.service_type)

    @property
    def is_named(self):
        return self.name is not None

    def has_tag(self, name: str, value: str | None):
        if value is not None:
            return any(t.name == name and t.value == value for t in self.tags)

        return any(t.name == name for t in self.tags)

    def _try_find_cached_node(
        self, context: ResolvingContext, parent_node: DependencyNode
    ):
        cached_node = context.get_cached(self.id)
        if cached_node:
            parent_node.add_child(cached_node)
            return cached_node.instance
        return None

    def _create_new_dependency_node(self, parent_node: DependencyNode):
        new_instance_node = DependencyNode(
            service_type=self.service_type,
            implementation=self.implementation,
            lifespan=self.lifespan,
            registration_name=self.name,
        )

        parent_node.add_child(new_instance_node)
        return new_instance_node

    def _finish_preparing_instance(
        self,
        built_instance: Any,
        context: ResolvingContext,
        new_instance_node: DependencyNode,
    ):
        new_instance_node.set_instance(built_instance)

        decorator_context = DecoratorContext(decorated=new_instance_node)
        top_decorated_node = new_instance_node

        for dec in context.find_decorators_that_apply(self, decorator_context):
            next_decorated_node = DependencyNode(
                service_type=self.service_type,
                implementation=dec.decorator_type,
                lifespan=self.lifespan,
            )
            top_decorated_node.add_decorator(next_decorated_node)
            built_instance = dec.decorate(built_instance, context, next_decorated_node)
            next_decorated_node.set_instance(built_instance)
            top_decorated_node = next_decorated_node

        context.new_instance_created(self, top_decorated_node)
        self.was_used = True
        return built_instance

    def build(self, context: ResolvingContext, parent_node: DependencyNode):
        if cached_node := self._try_find_cached_node(context, parent_node):
            return cached_node

        new_instance_node = self._create_new_dependency_node(parent_node)

        pre_configurations = context.find_pre_configurations_that_apply(self)

        for pre_configuration in pre_configurations:
            pre_configuration_node = DependencyNode(
                self.service_type,
                pre_configuration.configuration_fn,
                lifespan=Lifespan.singleton,
            )
            new_instance_node.add_pre_configuration(pre_configuration_node)

            pre_configuration.run(context, pre_configuration_node)
            pre_configuration_node.set_instance(pre_configuration)

        built_instance = self.creator.create(context, new_instance_node)

        return self._finish_preparing_instance(
            built_instance=built_instance,
            context=context,
            new_instance_node=new_instance_node,
        )

    async def build_async(self, context: ResolvingContext, parent_node: DependencyNode):
        if cached_node := self._try_find_cached_node(context, parent_node):
            return cached_node

        new_instance_node = self._create_new_dependency_node(parent_node)

        pre_configurations = context.find_pre_configurations_that_apply(self)

        for pre_configuration in pre_configurations:
            pre_configuration_node = DependencyNode(
                self.service_type,
                pre_configuration.configuration_fn,
                lifespan=Lifespan.singleton,
            )
            new_instance_node.add_pre_configuration(pre_configuration_node)

            await pre_configuration.run_async(context, pre_configuration_node)
            pre_configuration_node.set_instance(pre_configuration)

        built_instance = await self.creator.create_async(context, new_instance_node)

        return self._finish_preparing_instance(
            built_instance=built_instance,
            context=context,
            new_instance_node=new_instance_node,
        )


class Registry:
    def __init__(self):
        self._registrations: dict[type, deque[Registration]] = defaultdict(deque)
        self._decorators: dict[type, deque[Decorator]] = defaultdict(deque)
        self._pre_configurations: dict[type, deque[PreConfiguration]] = defaultdict(
            deque
        )
        self._singletons: dict[str, DependencyNode] = {}

    def add_registration(self, registration: Registration):
        self._registrations[registration.service_type].appendleft(registration)

    def add_decorator(self, decorator: Decorator):
        self._decorators[decorator.service_type].appendleft(decorator)

    def add_pre_configuration(self, pre_configuration: PreConfiguration):
        self._pre_configurations[pre_configuration.service_type].appendleft(
            pre_configuration
        )

    def add_singleton_instance(self, registration: Registration, node: DependencyNode):
        self._singletons[registration.id] = node

    def get_registrations(self, service_type: type):
        return self._registrations[service_type]

    def get_pre_configurations(self, service_type: type):
        return self._pre_configurations[service_type]

    def get_decorators(self, service_type: type):
        return self._decorators[service_type]

    def get_singleton(self, registration_id):
        return self._singletons.get(registration_id)

    @property
    def singletons(self):
        return self._singletons


class DependencyCache:
    def __init__(self, registry: Registry, scope: Scope):
        self.registry = registry
        self.scope = scope
        self._current_items: dict[str, DependencyNode] = {
            **{k: v for k, v in registry.singletons.items()},
            **{k: v for k, v in scope.scoped_instances.items()},
        }

    def get(self, registration_id: str) -> DependencyNode | None:
        node = self._current_items.get(registration_id)
        if node:
            return node

        node = self.scope.scoped_instances.get(registration_id)
        if node:
            self._current_items[registration_id] = node
            return node

        node = self.registry.singletons.get(registration_id)
        if node:
            self._current_items[registration_id] = node
            return node

        return None

    def put(self, registration: Registration, dependency_node: DependencyNode):
        if registration.lifespan == Lifespan.singleton:
            self.registry.add_singleton_instance(registration, dependency_node)
        elif registration.lifespan == Lifespan.scoped:
            self.scope.add_scoped_instance(
                registration,
                dependency_node,
            )

        if registration.lifespan >= Lifespan.once_per_graph:
            self._current_items[registration.id] = dependency_node

    def clean_up_parents(self):
        for node in self.registry.singletons.values():
            node.unparent()
        for node in self.scope.scoped_instances.values():
            node.unparent()


class ResolvingContext:
    def __init__(self, registry: Registry, scope: Scope):
        self.registry = registry
        self.scope = scope
        self._cache = DependencyCache(registry=registry, scope=scope)

    def try_generic_fallback(
        self, service_type: _GenericAlias, parent_node: DependencyNode
    ):
        return self.find_registration(
            service_type=service_type.__origin__,
            registration_filter=_default_registration_filter,
            parent_node=parent_node,
        )

    def find_registration(
        self,
        service_type: type,
        registration_filter: Callable,
        parent_node: DependencyNode,
    ) -> Registration:
        regs = self.find_registrations(
            service_type=service_type,
            registration_filter=registration_filter,
            registration_list_reducing_filter=constant(True),
            parent_node=parent_node,
        )
        reg = next(iter(regs), None)

        if reg is None:
            if type(service_type) == _GenericAlias:
                reg = self.try_generic_fallback(service_type, parent_node)
            if reg is None:
                print(f"{service_type} is None")
                raise CannotResolveException()
        return reg

    def find_registrations(
        self,
        service_type: type,
        registration_filter: Callable[[Registration], bool],
        registration_list_reducing_filter: Callable[
            [Registration, Sequence[Registration]], bool
        ],
        parent_node: DependencyNode,
    ) -> list[Registration]:
        parent_context = ParentContext(parent=parent_node)
        scoped_registrations = [
            r
            for r in self.scope.get_registrations(service_type)
            if registration_filter(r) and r.parent_context_filter(parent_context)
        ]
        container_registrations = [
            r
            for r in self.registry.get_registrations(service_type)
            if registration_filter(r) and r.parent_context_filter(parent_context)
        ]
        combined_registrations = scoped_registrations + container_registrations

        def reducer(
            accumulator: list[Registration], registration: Registration
        ) -> list[Registration]:
            if registration_list_reducing_filter(registration, accumulator):
                accumulator.append(registration)
            return accumulator

        return reduce(reducer, combined_registrations, [])

    def find_decorators_that_apply(
        self, registration: Registration, decorator_context: DecoratorContext
    ) -> list[Decorator]:
        return [
            d
            for d in self.registry.get_decorators(registration.service_type)
            if d.registration_filter(registration)
            and d.decorator_context_filter(decorator_context)
        ]

    def find_pre_configurations_that_apply(self, registration: Registration):
        return [
            c
            for c in self.registry.get_pre_configurations(registration.service_type)
            if not c.has_run and c.filter(registration)
        ]

    def add_generator(self, generator: Callable):
        self.scope.add_generator(generator)

    def get_cached(self, reg_id: str) -> DependencyNode | None:
        return self._cache.get(reg_id)

    def new_instance_created(self, registration: Registration, node: DependencyNode):
        self._cache.put(registration=registration, dependency_node=node)

    def __del__(self):
        self._cache.clean_up_parents()


class Resolver(abc.ABC):
    @abc.abstractmethod
    def resolve(
        self,
        service_type: type[TService],
        filter: RegistrationFilter = _default_registration_filter,
        *args,
        **kwargs,
    ) -> TService:
        pass

    @abc.abstractmethod
    async def resolve_async(
        self,
        service_type: type[TService],
        filter: RegistrationFilter = _default_registration_filter,
        *args,
        **kwargs,
    ) -> TService:
        pass


class Scope(Resolver):
    def __init__(
        self,
    ):
        self._registrations: dict[type, deque[Registration]] = defaultdict(deque)
        self._scoped_instances: dict[str, DependencyNode] = {}
        self._sync_teardowns: dict[str, Callable] = {}
        self._async_teardowns: dict[str, Callable] = {}
        self._generators: deque[Callable] = deque()

    async def __aenter__(self):
        await self.before_start_async()
        return self

    async def __aexit__(self, *args, **kwargs):
        await self._run_async_teardowns()
        self._run_sync_teardowns()
        await self.after_finish_async()
        await self._async_close_generators()

    def __enter__(self):
        self.before_start()
        return self

    def __exit__(self, *args, **kwargs):
        self._run_sync_teardowns()
        self.after_finish()
        self._close_generators()

    def before_start(self):
        pass

    def after_finish(self):
        pass

    async def before_start_async(self):
        pass

    async def after_finish_async(self):
        pass

    def add_generator(self, generator: Callable):
        self._generators.appendleft(generator)

    def _close_generators(self):
        for generator in self._generators:
            generator()

    async def _async_close_generators(self):
        for generator in self._generators:
            if inspect.iscoroutinefunction(generator):
                await generator()
            else:
                generator()

    async def _run_async_teardowns(self):
        for registration_id, teardown_fn in self._async_teardowns.items():
            cached_dependency = self._scoped_instances[registration_id]
            await teardown_fn(cached_dependency.instance)

    def _run_sync_teardowns(self):
        for registration_id, teardown_fn in self._sync_teardowns.items():
            cached_dependency = self._scoped_instances[registration_id]
            teardown_fn(cached_dependency.instance)

    def add_scoped_instance(self, registration: Registration, node: DependencyNode):
        self._scoped_instances[registration.id] = node
        if registration.scoped_teardown:
            is_async = inspect.iscoroutinefunction(registration.scoped_teardown)
            if is_async:
                self._async_teardowns[registration.id] = registration.scoped_teardown
            else:
                self._sync_teardowns[registration.id] = registration.scoped_teardown

    @abc.abstractmethod
    def register(
        self,
        service_type: type[TService],
        impl_type: type[TService] | None = None,
        factory: Callable[..., TService] | None = None,
        instance: TService | None = None,
        name: str | None = None,
        dependency_config: dict[str, DependencySettings] = {},
        parent_context_filter: ParentContextFilter = _default_parent_context_filter,
    ):
        pass

    def get_registrations(self, service_tyep):
        return self._registrations[service_tyep]

    @property
    def scoped_instances(self):
        return self._scoped_instances


class ContainerScope(Scope):
    def __init__(self, container: Container):
        super().__init__()
        self._container = container
        self.register(ContainerScope, instance=self)
        self.register(Resolver, instance=self)

    def register(
        self,
        service_type: type[TService],
        impl_type: type[TService] | None = None,
        factory: Callable[..., TService] | None = None,
        instance: TService | None = None,
        name: str | None = None,
        dependency_config: dict[str, DependencySettings] = {},
        tags: list[Tag] | None = None,
        parent_context_filter: ParentContextFilter = _default_parent_context_filter,
        scoped_teardown: Callable[[TService], Any] | None = None,
    ):
        if instance is not None:
            self._registrations[service_type].appendleft(
                Registration(
                    service_type=service_type,
                    implementation=lambda: instance,
                    lifespan=Lifespan.scoped,
                    name=name,
                    tags=tags,
                    parent_context_filter=parent_context_filter,
                    scoped_teardown=scoped_teardown,
                )
            )
        elif factory is not None:
            self._registrations[service_type].appendleft(
                Registration(
                    service_type=service_type,
                    implementation=factory,
                    lifespan=Lifespan.scoped,
                    name=name,
                    dependency_config=dependency_config,
                    tags=tags,
                    parent_context_filter=parent_context_filter,
                    scoped_teardown=scoped_teardown,
                )
            )
        elif impl_type is not None:
            self._registrations[service_type].appendleft(
                Registration(
                    service_type=service_type,
                    implementation=impl_type,
                    lifespan=Lifespan.scoped,
                    name=name,
                    dependency_config=dependency_config,
                    tags=tags,
                    parent_context_filter=parent_context_filter,
                    scoped_teardown=scoped_teardown,
                )
            )
        else:
            self._registrations[service_type].appendleft(
                Registration(
                    service_type=service_type,
                    implementation=service_type,
                    lifespan=Lifespan.scoped,
                    name=name,
                    dependency_config=dependency_config,
                    tags=tags,
                    parent_context_filter=parent_context_filter,
                    scoped_teardown=scoped_teardown,
                )
            )

    def resolve(
        self,
        service_type: type[TService],
        filter: RegistrationFilter = _default_registration_filter,
    ) -> TService:
        return self._container.resolve(
            service_type=service_type, filter=filter, scope=self
        )

    async def resolve_async(
        self,
        service_type: type[TService],
        filter: RegistrationFilter = _default_registration_filter,
    ) -> TService:
        return await self._container.resolve_async(
            service_type=service_type, filter=filter, scope=self
        )


class EmptyContainerScope(Scope):
    def __init__(self):
        super().__init__()

    def register(self, *args):
        pass

    def resolve(self, *args):
        pass

    async def resolve_async(self, *args):
        pass

    def get_resolved_instances(
        self, service_type: type[TService]
    ) -> Sequence[TService]:
        return []

    @property
    def scoped_instances(self):
        return {}


class NeedsScopedRegistrationError(Exception):
    def __init__(self, service_type, name):
        self.service_type = service_type
        self.name = name

    def __str__(self):
        with_name = f" with {self.name}" if self.name else ""
        return f"{self.service_type}{with_name} is expected to be used within a scope"


def type_expected_to_be_scoped(service_type: type, name: str | None):
    def raise_error():
        raise NeedsScopedRegistrationError(service_type, name)

    return raise_error


class Container(Resolver):
    def __init__(self):
        self.registry = Registry()
        self.register(Container, instance=self)
        self.register(Resolver, instance=self)

    def pre_configure(
        self,
        service_type: type,
        configuration_function: Callable[..., None],
        registration_filter: RegistrationFilter = _default_registration_filter,
        dependency_config: dict[str, DependencySettings] = {},
    ):
        self.registry.add_pre_configuration(
            PreConfiguration(
                service_type=service_type,
                pre_configuration=configuration_function,
                registration_filter=registration_filter,
                dependency_config=dependency_config,
            )
        )

    def register(
        self,
        service_type: type[TService],
        impl_type: type[TService] | None = None,
        factory: Callable[..., TService] | None = None,
        instance: TService | None = None,
        lifespan: Lifespan = Lifespan.once_per_graph,
        name: str | None = None,
        dependency_config: dict[str, DependencySettings] = {},
        tags: list[Tag] | None = None,
        parent_context_filter: ParentContextFilter = _default_parent_context_filter,
        scoped_teardown: Callable[[TService], Any] | None = None,
    ):
        if instance is not None:
            self.registry.add_registration(
                Registration(
                    service_type=service_type,
                    implementation=lambda: instance,
                    dependency_config=dependency_config,
                    lifespan=Lifespan.singleton,
                    name=name,
                    tags=tags,
                    parent_context_filter=parent_context_filter,
                    scoped_teardown=scoped_teardown,
                )
            )
        elif factory is not None:
            self.registry.add_registration(
                Registration(
                    service_type=service_type,
                    implementation=factory,
                    dependency_config=dependency_config,
                    lifespan=lifespan,
                    name=name,
                    tags=tags,
                    parent_context_filter=parent_context_filter,
                    scoped_teardown=scoped_teardown,
                )
            )
        elif impl_type is not None:
            self.registry.add_registration(
                Registration(
                    service_type=service_type,
                    implementation=impl_type,
                    dependency_config=dependency_config,
                    lifespan=lifespan,
                    name=name,
                    tags=tags,
                    parent_context_filter=parent_context_filter,
                    scoped_teardown=scoped_teardown,
                )
            )
        else:
            self.registry.add_registration(
                Registration(
                    service_type=service_type,
                    implementation=service_type,
                    dependency_config=dependency_config,
                    lifespan=lifespan,
                    name=name,
                    tags=tags,
                    parent_context_filter=parent_context_filter,
                    scoped_teardown=scoped_teardown,
                )
            )

    def register_subclasses(
        self,
        base_type: type,
        lifespan: Lifespan = Lifespan.once_per_graph,
        subclass_type_filter: Callable[[type], bool] = always_true,
        get_registration_name: Callable[[type], str | None] = constant(None),
        tags: list[Tag] | None = None,
        parent_context_filter: ParentContextFilter = _default_parent_context_filter,
    ):
        full_type_filter = ~(is_abstract) & subclass_type_filter
        subclasses = get_subclasses(base_type, full_type_filter)
        for sc in subclasses:
            name = get_registration_name(sc)
            self.register(
                base_type,
                sc,
                lifespan=lifespan,
                name=name,
                tags=tags,
                parent_context_filter=parent_context_filter,
            )
            self.register(
                sc,
                lifespan=lifespan,
                tags=tags,
                name=name,
                parent_context_filter=parent_context_filter,
            )

    def register_decorator(
        self,
        service_type: type,
        decorator_type: type,
        registration_filter: Callable[
            [Registration], bool
        ] = _default_registration_filter,
        decorator_context_filter: DecoratorContextFilter = _default_decorator_context_filter,
        decorated_arg: str | None = None,
        dependency_config: dict[str, DependencySettings] = {},
    ):
        self.registry.add_decorator(
            Decorator(
                service_type=service_type,
                decorator_type=decorator_type,
                registration_filter=registration_filter,
                decorator_context_filter=decorator_context_filter,
                decorated_arg=decorated_arg,
                dependency_config=dependency_config,
            )
        )

    @staticmethod
    def _get_target_generic_base(generic_service_type: type, subclass: type):
        return next(
            (
                try_to_complete_generic(b, subclass)
                for b in get_generic_bases(
                    subclass,
                    lambda t: getattr(t, "__origin__", None) == generic_service_type,
                )
            ),
            None,
        )

    @deprecated("Use register_generic_subclasses instead")
    def register_open_generic(
        self,
        generic_service_type: type,
        fallback_type: type | None = None,
        fallback_name: str | None = None,
        lifespan: Lifespan = Lifespan.once_per_graph,
        subclass_type_filter: Callable[[type], bool] = always_true,
        get_registration_name: Callable[[type], str | None] = constant(None),
        tags: list[Tag] | None = None,
        parent_context_filter: ParentContextFilter = _default_parent_context_filter,
    ):
        self.register_generic_subclasses(
            generic_service_type=generic_service_type,
            fallback_type=fallback_type,
            fallback_name=fallback_name,
            lifespan=lifespan,
            subclass_type_filter=subclass_type_filter,
            get_registration_name=get_registration_name,
            tags=tags,
            parent_context_filter=parent_context_filter,
        )

    def register_generic_subclasses(
        self,
        generic_service_type: type,
        fallback_type: type | None = None,
        fallback_name: str | None = None,
        lifespan: Lifespan = Lifespan.once_per_graph,
        subclass_type_filter: Callable[[type], bool] = always_true,
        get_registration_name: Callable[[type], str | None] = constant(None),
        tags: list[Tag] | None = None,
        parent_context_filter: ParentContextFilter = _default_parent_context_filter,
    ):
        full_type_filter = ~is_abstract & subclass_type_filter
        subclasses = get_subclasses(generic_service_type, full_type_filter)
        for subclass in subclasses:
            name = get_registration_name(subclass)
            target_generic_base = self._get_target_generic_base(
                generic_service_type, subclass
            )
            if target_generic_base:
                self.register(
                    target_generic_base,
                    subclass,
                    lifespan=lifespan,
                    name=name,
                    tags=tags,
                    parent_context_filter=parent_context_filter,
                )

        if fallback_type:
            self.register(
                generic_service_type,
                fallback_type,
                lifespan=lifespan,
                name=fallback_name,
                tags=tags,
                parent_context_filter=parent_context_filter,
            )

    @deprecated("Use register_generic_decorator instead")
    def register_open_generic_decorator(
        self,
        generic_service_type: type,
        generic_decorator_type: type,
        subclass_type_filter: Callable[[type], bool] = always_true,
        decorated_arg: str | None = None,
        dependency_config: dict[str, DependencySettings] = {},
        registration_filter: Callable[
            [Registration], bool
        ] = _default_registration_filter,
        decorator_context_filter: DecoratorContextFilter = _default_decorator_context_filter,
    ):
        self.register_generic_decorator(
            generic_service_type=generic_service_type,
            generic_decorator_type=generic_decorator_type,
            subclass_type_filter=subclass_type_filter,
            decorated_arg=decorated_arg,
            dependency_config=dependency_config,
            registration_filter=registration_filter,
            decorator_context_filter=decorator_context_filter,
        )

    def register_generic_decorator(
        self,
        generic_service_type: type,
        generic_decorator_type: type,
        subclass_type_filter: Callable[[type], bool] = always_true,
        decorated_arg: str | None = None,
        dependency_config: dict[str, DependencySettings] = {},
        registration_filter: Callable[
            [Registration], bool
        ] = _default_registration_filter,
        decorator_context_filter: DecoratorContextFilter = _default_decorator_context_filter,
    ):
        full_type_filter = (
            ~is_abstract
            & ~name_starts_with("__DecoratedGeneric__")
            & subclass_type_filter
        )
        subclasses = get_subclasses(generic_service_type, full_type_filter)
        decorator_is_open_generic = is_open_generic_type(generic_decorator_type)

        for subclass in subclasses:
            target_generic_base = self._get_target_generic_base(
                generic_service_type, subclass
            )
            if target_generic_base:
                if decorator_is_open_generic:
                    generic_values = get_generic_types(target_generic_base)
                    concrete_decorator = generic_decorator_type[generic_values]  # type: ignore
                    DecoratedType = types.new_class(
                        f"__DecoratedGeneric__{concrete_decorator.__name__}",
                        (concrete_decorator,),
                        {},
                    )

                    self.register_decorator(
                        target_generic_base,
                        DecoratedType,
                        decorated_arg=decorated_arg,
                        dependency_config=dependency_config,
                        registration_filter=registration_filter,
                        decorator_context_filter=decorator_context_filter,
                    )
                else:
                    self.register_decorator(
                        target_generic_base,
                        generic_decorator_type,
                        decorated_arg=decorated_arg,
                        dependency_config=dependency_config,
                        registration_filter=registration_filter,
                        decorator_context_filter=decorator_context_filter,
                    )

    def resolve(
        self,
        service_type: type[TService],
        filter: RegistrationFilter = _default_registration_filter,
        scope: Scope = EmptyContainerScope(),
    ) -> TService:
        graph = self.resolve_dependency_graph(service_type, filter, scope)
        return graph.instance

    async def resolve_async(
        self,
        service_type: type[TService],
        filter: RegistrationFilter = _default_registration_filter,
        scope: Scope = EmptyContainerScope(),
    ) -> TService:
        graph = await self.resolve_dependency_graph_async(service_type, filter, scope)
        return graph.instance

    def resolve_dependency_graph(
        self,
        service_type: type,
        filter: RegistrationFilter = _default_registration_filter,
        scope: Scope = EmptyContainerScope(),
    ) -> DependencyGraph:
        graph = DependencyGraph(service_type=service_type, filter=filter)
        context = ResolvingContext(self.registry, scope)
        graph.resolve(context)
        del context
        return graph

    async def resolve_dependency_graph_async(
        self,
        service_type: type,
        filter: RegistrationFilter = _default_registration_filter,
        scope: Scope = EmptyContainerScope(),
    ) -> DependencyGraph:
        graph = DependencyGraph(service_type=service_type, filter=filter)
        context = ResolvingContext(self.registry, scope)
        await graph.resolve_async(context)
        del context
        return graph

    def force_run_pre_configuration(
        self,
        service_type: type,
        registration_filter: RegistrationFilter = _default_registration_filter,
    ):
        self.resolve(service_type, filter=registration_filter)

    async def force_run_pre_configuration_async(
        self,
        service_type: type,
        registration_filter: RegistrationFilter = _default_registration_filter,
    ):
        await self.resolve_async(service_type, filter=registration_filter)

    def new_scope(
        self, ScopeClass: Type[ContainerScope] = ContainerScope, *args, **kwargs
    ) -> Scope:
        return ScopeClass(self, *args, **kwargs)

    def expect_to_be_scoped(self, service_type: type, name: str | None = None):
        self.register(
            service_type=service_type,
            factory=type_expected_to_be_scoped(service_type, name),
            name=name,
        )

    def apply_bundle(self, bundle_fn: Callable[[Container], None]):
        bundle_fn(self)

    def has_registration(
        self, service_type, filter: RegistrationFilter = _default_registration_filter
    ):
        found_registrations = [
            r for r in self.registry.get_registrations(service_type) if filter(r)
        ]
        return len(found_registrations) > 0


@dataclass(kw_only=True)
class DependencySettings:
    value_factory: DependencyValueFactory = _default_dependency_value_factory
    filter: RegistrationFilter = _default_registration_filter
    list_reducing_filter: RegistrationListReducingFilter = (
        _default_registration_list_reducing_filter
    )


RegistrationFilter = Callable[[Registration], bool]
RegistrationListReducingFilter = Callable[[Registration, Sequence[Registration]], bool]
ParentContextFilter = Callable[[ParentContext], bool]
DependencyValueFactory = Callable[[Any, DependencyContext], Any]
DecoratorContextFilter = Callable[[DecoratorContext], bool]
