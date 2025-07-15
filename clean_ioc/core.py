"""Simple IOC container."""

from __future__ import annotations

import abc
import asyncio
import inspect
import logging
import types
from collections import defaultdict, deque
from collections.abc import Callable, Collection, Iterable, MutableSequence, Sequence
from contextlib import _AsyncGeneratorContextManager, _GeneratorContextManager, contextmanager
from dataclasses import dataclass
from enum import IntEnum
from typing import (
    Any,
    ClassVar,
    Protocol,
    TypeVar,
    _GenericAlias,  # type: ignore
    get_type_hints,
)
from typing import Collection as TypingCollection
from typing import Iterable as TypingIterable
from typing import MutableSequence as TypingMutableSequence
from typing import Sequence as TypingSequence
from uuid import uuid4

from theutilitybelt.functional.predicate import always_true
from theutilitybelt.functional.utils import constant
from theutilitybelt.typing.generics import GenericTypeMap, get_generic_bases, try_to_map_generic_args_to_open_type
from theutilitybelt.typing.utils import get_subclasses

from clean_ioc.utils import singleton

from .type_filters import is_abstract, name_starts_with

logger = logging.getLogger(__name__)

TService = TypeVar("TService")
TReturn = TypeVar("TReturn")


@singleton
class _empty:  # noqa: N801
    def __bool__(self):
        return False


@singleton
class _unknown:  # noqa: N801
    def __bool__(self):
        return False


EMPTY = _empty()
UNKNOWN = _unknown()


def create_generic_decorator_type(concrete_decorator: type):
    return types.new_class(
        f"__DecoratedGeneric__{concrete_decorator.__name__}",
        (concrete_decorator,),
        {},
    )


class ArgInfo:
    def __init__(self, name: str, arg_type: type, default_value: Any):
        self.name = name
        self.arg_type = arg_type
        self.default_value = EMPTY if default_value == inspect._empty else default_value


def _get_arg_info(subject: Callable, local_ns: dict = {}, global_ns: dict | None = None) -> dict[str, ArgInfo]:
    arg_spec_fn = subject if inspect.isfunction(subject) else subject.__init__
    args = get_type_hints(arg_spec_fn, global_ns, local_ns)
    signature = inspect.signature(subject)
    d: dict[str, ArgInfo] = {}
    for name, param in signature.parameters.items():
        if "*" in str(param):
            continue
        d[name] = ArgInfo(name=name, arg_type=args[name], default_value=param.default)
    return d


def _set_up_dependencies(
    creator_function: Callable,
    dependency_config: DependencyConfig,
) -> dict[str, Dependency]:
    args_infos = _get_arg_info(creator_function)
    defaulted_dependency_config = defaultdict(DependencySettings, dependency_config)

    dependencies = {
        name: Dependency(
            name=name,
            parent_implementation=creator_function,
            service_type=arg_info.arg_type,
            settings=defaulted_dependency_config[name],
            default_value=arg_info.default_value,
        )
        for name, arg_info in args_infos.items()
    }

    for extra_kwarg in set(defaulted_dependency_config.keys()) ^ set(dependencies.keys()):
        dependencies[extra_kwarg] = Dependency(
            name=extra_kwarg,
            parent_implementation=creator_function,
            service_type=Any,
            settings=dependency_config[extra_kwarg],
            default_value=EMPTY,
        )

    return dependencies


def _resolve_dependencies(
    dependencies: dict[str, Dependency], context: _ResolvingContext, dependency_node: DependencyNode
) -> dict[str, Any]:
    kwargs = {}
    for arg_name, arg_dep in dependencies.items():
        kwargs[arg_name] = arg_dep.resolve(context, dependency_node)
    return kwargs


async def _resolve_dependencies_async(
    dependencies: dict[str, Dependency], context: _ResolvingContext, dependency_node: DependencyNode
) -> dict[str, Any]:
    kwargs = {}
    for arg_name, arg_dep in dependencies.items():
        kwargs[arg_name] = await arg_dep.resolve_async(context, dependency_node)
    return kwargs


def default_registration_filter(r: Registration) -> bool:
    return r.name is None


def default_parameter_value_factory(default_value: Any, _: DependencyContext) -> Any:
    return default_value


def default_registration_list_modifier(registrations: list[Registration]) -> list[Registration]:
    return registrations


default_parent_node_filter = constant(True)
default_decorated_node_filter = constant(True)


@dataclass
class Tag:
    name: str
    value: str | None = None

    def __iter__(self):
        yield self.name
        if self.value is not None:
            yield self.value


class Lifespan(IntEnum):
    transient = 0
    once_per_graph = 1
    scoped = 2
    singleton = 3


class Node(Protocol):
    service_type: type
    implementation: type | Callable
    parent: Node
    children: list[Node]
    decorator: Node
    decorated: Node
    pre_configured_by: Node
    pre_configures: Node
    registration_name: str | None
    registration_tags: Iterable[Tag]
    instance: Any = UNKNOWN
    lifespan: Lifespan

    def has_registration_tag(self, name: str, value: str | None) -> bool: ...
    def unparent(self): ...
    @property
    def implementation_type(self) -> type: ...
    @property
    def instance_type(self) -> type: ...

    @property
    def bottom_decorated_node(self) -> Node: ...
    @property
    def top_decorated_node(self) -> Node: ...
    def has_dependant_service_type(self, service_type: type) -> bool: ...

    def has_dependant_implementation_type(self, implementation_type: type) -> bool: ...

    def has_dependant_instance_type(self, instance_type: type) -> bool: ...

    @property
    def generic_mapping(self) -> GenericTypeMap: ...


@singleton
class EmptyNode(Node):
    _GENERIC_MAPPING: GenericTypeMap | None = None

    def __init__(self):
        self.service_type = _empty
        self.implementation = _empty
        self.parent = self
        self.decorated = self
        self.decorator = self
        self.pre_configured_by = self
        self.pre_configures = self
        self.registration_name = None
        self.registration_tags = ()
        self.instance = EMPTY
        self.lifespan = Lifespan.singleton
        self.children = []

    def __bool__(self):
        return False

    def has_registration_tag(self, name: str, value: str | None):
        return False

    def unparent(self):
        pass

    @property
    def implementation_type(self):
        return _empty

    @property
    def instance_type(self):
        return _empty

    @property
    def bottom_decorated_node(self):
        return self

    @property
    def top_decorated_node(self):
        return self

    @property
    def generic_mapping(self):
        if not self.__class__._GENERIC_MAPPING:
            self.__class__._GENERIC_MAPPING = GenericTypeMap(_empty)

        return self.__class__._GENERIC_MAPPING

    def has_dependant_service_type(self, service_type: type) -> bool:
        return False

    def has_dependant_implementation_type(self, implementation_type: type) -> bool:
        return False

    def has_dependant_instance_type(self, instance_type: type) -> bool:
        return False

    def __repr__(self):
        return "EmptyNode()"


class DependencyNode(Node):
    def __init__(
        self,
        service_type: type,
        implementation: type | Callable,
        lifespan: Lifespan,
        registration_name: str | None = None,
        registration_tags: Iterable[Tag] = (),
    ):
        self.service_type = service_type
        self.implementation = implementation
        self.lifespan = lifespan
        self.registration_name: str | None = registration_name
        self.registration_tags = registration_tags
        self.parent = EmptyNode()
        self.children = []
        self.decorated = EmptyNode()
        self.decorator = EmptyNode()
        self.pre_configured_by = EmptyNode()
        self.pre_configures = EmptyNode()
        self.instance = UNKNOWN

        self._generic_mapping: GenericTypeMap | None = None

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

    def has_registration_tag(self, name: str, value: str | None):
        if value is not None:
            return any(t.name == name and t.value == value for t in self.registration_tags)

        return any(t.name == name for t in self.registration_tags)

    def unparent(self):
        self.parent = EmptyNode()
        if decorated := self.decorated:
            decorated.unparent()

        if pre_configures := self.pre_configured_by:
            pre_configures.pre_configures = EmptyNode()
            self.pre_configured_by = EmptyNode()

    @property
    def implementation_type(self):
        return self.implementation if isinstance(self.implementation, type) else type(self.implementation)

    @property
    def instance_type(self):
        return type(self.instance)

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

    @property
    def generic_mapping(self):
        if not self._generic_mapping:
            self._generic_mapping = GenericTypeMap(self.service_type)

        return self._generic_mapping

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


class DependencyGraph(DependencyNode):
    def __init__(self, service_type: type, filter: RegistrationFilter):
        dependency_settings = DependencySettings(filter=filter)
        self.root_dependency = Dependency(
            name="__ROOT__",
            parent_implementation=DependencyGraph,
            service_type=service_type,
            settings=dependency_settings,
            default_value=EMPTY,
        )

        super().__init__(
            service_type=service_type,
            implementation=DependencyGraph,
            lifespan=Lifespan.once_per_graph,
        )

    def resolve(self, context: _ResolvingContext):
        instance = self.root_dependency.resolve(context, self)
        self.set_instance(instance)
        return self

    async def resolve_async(self, context: _ResolvingContext):
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


class CurrentGraph:
    def __init__(self, parent_node: DependencyNode, resolving_context: _ResolvingContext):
        self.parent_node = parent_node
        self.resolving_context = resolving_context

    def _get_dependency_and_graph_node(
        self, service_type: type[TService], filter: RegistrationFilter = default_registration_filter
    ):
        current_graph_node = DependencyNode(
            service_type=CurrentGraph,
            implementation=CurrentGraph,
            lifespan=Lifespan.transient,
        )
        self.parent_node.add_child(current_graph_node)
        dependency_settings = DependencySettings(filter=filter)

        dependency = Dependency(
            name="__CURRENT_GRAPH__",
            parent_implementation=CurrentGraph,
            service_type=service_type,
            settings=dependency_settings,
            default_value=EMPTY,
        )

        return dependency, current_graph_node

    def resolve(
        self, service_type: type[TService], filter: RegistrationFilter = default_registration_filter
    ) -> TService:
        dependency, current_graph_node = self._get_dependency_and_graph_node(service_type, filter)

        return dependency.resolve(self.resolving_context, current_graph_node)

    async def resolve_async(
        self, service_type: type[TService], filter: RegistrationFilter = default_registration_filter
    ) -> TService:
        dependency, current_graph_node = self._get_dependency_and_graph_node(service_type, filter)

        return await dependency.resolve_async(self.resolving_context, current_graph_node)


class CannotResolveError(Exception):
    def __init__(self):
        self.dependencies: list[Dependency] = []

    def append(self, d: Dependency):
        self.dependencies.append(d)

    @staticmethod
    def print_dependency(d: Dependency):
        # Format the dependency information with ASCII box
        content = (
            f"implementation: {d.parent_implementation}\ndependency_name: {d.name}\nservice_type: {d.service_type}"
        )
        content_lines = content.split("\n")
        width = max(len(line) for line in content_lines)
        top_border = "┌" + "─" * (width + 2) + "┐"
        bottom_border = "└" + "─" * (width + 2) + "┘"
        padded_content = "\n".join("│ " + line.ljust(width) + " │" for line in content_lines)
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
            printer_item = CannotResolveError.print_dependency(item)
            if index == 0:
                chain += f"{printer_item}\n"
            else:
                # Adding fixed spacing before arrow for alignment, then adding the dependency
                chain += f"{arrow}{printer_item}\n"

        return chain

    def __str__(self):
        return f"\n{self.message}\n\nDependency chain:\n{self.dependency_chain}"


class Dependency:
    GENERIC_COLLECTION_MAPPINGS: ClassVar[dict[type, type]] = {
        tuple: tuple,
        list: list,
        set: set,
        Sequence: tuple,
        TypingSequence: tuple,
        Iterable: tuple,
        TypingCollection: tuple,
        TypingIterable: tuple,
        Collection: tuple,
        MutableSequence: list,
        TypingMutableSequence: list,
    }

    __slots__ = (
        "default_value",
        "generic_collection_type",
        "is_current_graph",
        "is_dependency_context",
        "name",
        "parent_implementation",
        "service_type",
        "settings",
    )

    def __init__(
        self,
        name: str,
        parent_implementation: Callable | type,
        service_type: Any,
        settings: DependencySettings,
        default_value: Any,
    ):
        self.is_dependency_context = False
        self.is_current_graph = False

        self.name = name
        self.parent_implementation = parent_implementation
        if isinstance(parent_implementation, type):
            self.service_type = try_to_map_generic_args_to_open_type(service_type, parent_implementation)
        else:
            self.service_type = service_type
        self.settings = settings
        generic_origin = getattr(self.service_type, "__origin__", None)

        if generic_origin and generic_origin in self.GENERIC_COLLECTION_MAPPINGS:
            self.generic_collection_type = self.GENERIC_COLLECTION_MAPPINGS[generic_origin]
        else:
            self.generic_collection_type = None

        self.default_value = default_value

        if self.service_type == DependencyContext:
            self.is_dependency_context = True
        elif self.service_type == CurrentGraph:
            self.is_current_graph = True

    def resolve(self, context: _ResolvingContext, dependency_node: DependencyNode) -> Any:
        dependency_context = DependencyContext(name=self.name, dependency_node=dependency_node)
        value = self.settings.value_factory(self.default_value, dependency_context)

        if value is not EMPTY:
            return value

        if self.is_dependency_context:
            return dependency_context

        if self.is_current_graph:
            return CurrentGraph(parent_node=dependency_node, resolving_context=context)

        if self.generic_collection_type:
            regs = context.find_registrations(
                service_type=self.service_type.__args__[0],  # type: ignore
                registration_filter=self.settings.filter,
                parent_node=dependency_node,
                registration_list_modifier=self.settings.list_modifier,
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
        except CannotResolveError as ex:
            ex.append(self)
            raise ex

    async def resolve_async(self, context: _ResolvingContext, dependency_node: DependencyNode) -> Any:
        dependency_context = DependencyContext(name=self.name, dependency_node=dependency_node)
        value = self.settings.value_factory(self.default_value, dependency_context)

        if value is not EMPTY:
            return value

        if self.is_dependency_context:
            return DependencyContext(name=self.name, dependency_node=dependency_node)

        if self.is_current_graph:
            return CurrentGraph(parent_node=dependency_node, resolving_context=context)

        if self.generic_collection_type:
            regs = context.find_registrations(
                service_type=self.service_type.__args__[0],  # type: ignore
                registration_filter=self.settings.filter,
                parent_node=dependency_node,
                registration_list_modifier=self.settings.list_modifier,
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
        except CannotResolveError as ex:
            ex.append(self)
            raise ex


class Activator(abc.ABC):
    @classmethod
    @abc.abstractmethod
    def activate(
        cls, factory: Callable, resolved_dependencies: dict[str, Any], context: _ResolvingContext, lifespan: Lifespan
    ) -> Any: ...

    @classmethod
    @abc.abstractmethod
    def activate_async(
        cls, factory: Callable, resolved_dependencies: dict[str, Any], context: _ResolvingContext, lifespan: Lifespan
    ) -> Any: ...


class FactoryActivator(Activator):
    @classmethod
    def _contextmanager_finalizer(cls, cm: _GeneratorContextManager):
        def inner():
            try:
                cm.__exit__(None, None, None)
            except Exception as ex:
                logger.warning(f"Failed to close context manager {cm} with exception {ex}")

        return inner

    @classmethod
    def _asynccontextmanager_finalizer(cls, cm: _AsyncGeneratorContextManager):
        async def inner():
            try:
                await cm.__aexit__(None, None, None)
            except Exception as ex:
                logger.warning(f"Failed to close async context manager {cm} with exception {ex}")

        return inner

    @classmethod
    def activate(
        cls, factory: Callable, resolved_dependencies: dict[str, Any], context: _ResolvingContext, lifespan: Lifespan
    ):
        instance = factory(**resolved_dependencies)

        if isinstance(instance, _GeneratorContextManager):
            context.add_finalizer(lifespan, cls._contextmanager_finalizer(instance))
            return instance.__enter__()

        return instance

    @classmethod
    async def activate_async(
        cls, factory: Callable, resolved_dependencies: dict[str, Any], context: _ResolvingContext, lifespan: Lifespan
    ):
        instance = cls.activate(factory, resolved_dependencies, context, lifespan)

        if isinstance(instance, _AsyncGeneratorContextManager):
            context.add_finalizer(lifespan, cls._asynccontextmanager_finalizer(instance))
            return await instance.__aenter__()

        return instance


class GeneratorActivator(Activator):
    @classmethod
    def _generator_close(cls, generator: types.GeneratorType):
        def inner():
            try:
                next(generator)
                generator.close()
            except StopIteration:
                pass

        return inner

    @classmethod
    def activate(
        cls,
        factory: Callable,
        resolved_dependencies: dict[str, Any],
        context: _ResolvingContext,
        lifespan: Lifespan,
    ):
        generator = factory(**resolved_dependencies)
        instance = next(generator)
        context.add_finalizer(lifespan, cls._generator_close(generator))
        return instance

    @classmethod
    async def activate_async(
        cls, factory: Callable, resolved_dependencies: dict[str, Any], context: _ResolvingContext, lifespan: Lifespan
    ):
        return cls.activate(factory, resolved_dependencies, context, lifespan)


class AsyncFactoryActivator(Activator):
    @classmethod
    def activate(
        cls,
        factory: Callable,
        resolved_dependencies: dict[str, Any],
        context: _ResolvingContext,
        lifespan: Lifespan,
    ):
        raise Exception("Only async allowed")

    @classmethod
    async def activate_async(
        cls,
        factory: Callable,
        resolved_dependencies: dict[str, Any],
        context: _ResolvingContext,
        lifespan: Lifespan,
    ):
        return await factory(**resolved_dependencies)


class AsyncGeneratorActivator(Activator):
    @classmethod
    def _generator_close(cls, generator: types.AsyncGeneratorType):
        async def inner():
            try:
                await anext(generator)
                await generator.aclose()
            except StopAsyncIteration:
                pass

        return inner

    @classmethod
    def activate(
        cls,
        factory: Callable,
        resolved_dependencies: dict[str, Any],
        context: _ResolvingContext,
        lifespan: Lifespan,
    ):
        raise Exception("Only async allowed")

    @classmethod
    async def activate_async(
        cls,
        factory: Callable,
        resolved_dependencies: dict[str, Any],
        context: _ResolvingContext,
        lifespan: Lifespan,
    ):
        generator = factory(**resolved_dependencies)
        instance = await anext(generator)
        context.add_finalizer(lifespan, cls._generator_close(generator))
        return instance


class PreConfiguration:
    __slots__ = (
        "activator_class",
        "configuration_fn",
        "continue_on_failure",
        "dependencies",
        "has_run",
        "registration_filter",
    )

    def __init__(
        self,
        pre_configuration: Callable[..., None],
        activator_class: type[Activator],
        registration_filter: RegistrationFilter,
        dependency_config: DependencyConfig,
        continue_on_failure: bool = False,
    ):
        self.configuration_fn = pre_configuration
        self.activator_class = activator_class
        self.registration_filter = registration_filter
        self.dependencies = _set_up_dependencies(pre_configuration, dependency_config)
        self.continue_on_failure = continue_on_failure
        self.has_run = False

    @contextmanager
    def _run_safely(self):
        try:
            yield
            self.has_run = True
        except Exception as ex:
            logger.exception(f"Failed to run pre-configuration {self.configuration_fn}")
            if not self.continue_on_failure:
                raise ex

    def run(self, context: _ResolvingContext, dependency_node: DependencyNode):
        resolved_dependencies = _resolve_dependencies(self.dependencies, context, dependency_node)
        with self._run_safely():
            self.activator_class.activate(self.configuration_fn, resolved_dependencies, context, Lifespan.scoped)

    async def run_async(self, context: _ResolvingContext, dependency_node: DependencyNode):
        resolved_dependencies = await _resolve_dependencies_async(self.dependencies, context, dependency_node)
        with self._run_safely():
            await self.activator_class.activate_async(
                self.configuration_fn, resolved_dependencies, context, Lifespan.scoped
            )


class Decorator:
    __slots__ = (
        "activator_class",
        "decorated_arg",
        "decorated_node_filter",
        "decorator_type",
        "dependencies",
        "parent_node_filter",
        "position",
        "registration_filter",
        "service_type",
    )

    def __init__(
        self,
        service_type: type,
        decorator_type: type | Callable,
        *,
        activator_class: type[Activator],
        registration_filter: RegistrationFilter,
        decorator_node_filter: NodeFilter,
        decorated_arg: str | None,
        dependency_config: DependencyConfig = {},
        position: int = 0,
    ):
        self.service_type = service_type
        self.decorator_type = decorator_type

        dependencies = _set_up_dependencies(decorator_type, dependency_config)

        self.decorated_arg = decorated_arg or next(
            name for name, dep in dependencies.items() if dep.service_type == service_type
        )
        self.registration_filter = registration_filter
        self.decorated_node_filter = decorator_node_filter
        self.activator_class = activator_class
        self.position = position

        del dependencies[self.decorated_arg]

        self.dependencies: dict[str, Dependency] = dependencies

    def decorate(
        self, instance: Any, context: _ResolvingContext, dependency_node: DependencyNode, registration: Registration
    ):
        resolved_dependencies = _resolve_dependencies(self.dependencies, context, dependency_node)
        resolved_dependencies[self.decorated_arg] = instance

        return self.activator_class.activate(
            self.decorator_type, resolved_dependencies, context, lifespan=registration.lifespan
        )

    async def decorate_async(
        self, instance: Any, context: _ResolvingContext, dependency_node: DependencyNode, registration: Registration
    ):
        resolved_dependencies = await _resolve_dependencies_async(self.dependencies, context, dependency_node)
        resolved_dependencies[self.decorated_arg] = instance

        return await self.activator_class.activate_async(
            self.decorator_type, resolved_dependencies, context, lifespan=registration.lifespan
        )


class Registration(Protocol):
    service_type: type
    implementation: Callable
    lifespan: Lifespan
    name: str | None
    id: str

    def has_tag(self, name: str, value: Any) -> bool: ...

    @property
    def generic_mapping(self) -> GenericTypeMap: ...


class _Registration(Registration):
    __slots__ = (
        "_generic_mapping",
        "activator_class",
        "dependencies",
        "id",
        "implementation",
        "is_named",
        "lifespan",
        "name",
        "parent_node_filter",
        "scoped_teardown",
        "service_type",
        "tags",
        "was_used",
    )

    def __init__(
        self,
        *,
        activator_class: type[Activator],
        service_type: type,
        implementation: Callable,
        lifespan: Lifespan,
        name: str | None = None,
        dependency_config: DependencyConfig = {},
        parent_node_filter: NodeFilter = default_parent_node_filter,
        tags: Iterable[Tag] | None = None,
        scoped_teardown: Callable | None = None,
    ):
        if scoped_teardown and not lifespan <= Lifespan.scoped:
            raise ValueError("Scoped teardowns can only be used with scoped and singleton lifestyles")

        self.service_type = service_type
        self.implementation = implementation
        self.activator_class = activator_class
        self.lifespan = lifespan
        self.name = name
        self.tags = tuple(tags) if tags else tuple()
        self.id = str(uuid4())
        self.parent_node_filter = parent_node_filter
        self.scoped_teardown = scoped_teardown
        self.was_used = False
        self.is_named = name is not None
        self.dependencies: dict[str, Dependency] = _set_up_dependencies(implementation, dependency_config)

        self._generic_mapping: GenericTypeMap | None = None

    def has_tag(self, name: str, value: str | None):
        if value is not None:
            return any(t.name == name and t.value == value for t in self.tags)

        return any(t.name == name for t in self.tags)

    @property
    def generic_mapping(self):
        if not self._generic_mapping:
            self._generic_mapping = GenericTypeMap(self.service_type)

        return self._generic_mapping

    def _try_find_cached_node(self, context: _ResolvingContext, parent_node: DependencyNode):
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
            registration_tags=self.tags,
        )

        parent_node.add_child(new_instance_node)
        return new_instance_node

    def build(self, context: _ResolvingContext, parent_node: DependencyNode):
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

        resolved_dependencies = _resolve_dependencies(self.dependencies, context, new_instance_node)

        built_instance = self.activator_class.activate(
            self.implementation, resolved_dependencies, context, lifespan=self.lifespan
        )
        new_instance_node.set_instance(built_instance)

        top_decorated_node = new_instance_node
        for dec in context.find_decorators_that_apply(self, decorated_instance_node=new_instance_node):
            next_decorated_node = DependencyNode(
                service_type=self.service_type,
                implementation=dec.decorator_type,
                lifespan=self.lifespan,
            )
            top_decorated_node.add_decorator(next_decorated_node)
            built_instance = dec.decorate(built_instance, context, next_decorated_node, self)
            next_decorated_node.set_instance(built_instance)
            top_decorated_node = next_decorated_node

        context.new_instance_created(self, top_decorated_node)
        self.was_used = True
        return built_instance

    async def build_async(self, context: _ResolvingContext, parent_node: DependencyNode):
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

        resolved_dependencies = await _resolve_dependencies_async(self.dependencies, context, new_instance_node)
        built_instance = await self.activator_class.activate_async(
            self.implementation, resolved_dependencies, context, lifespan=self.lifespan
        )
        new_instance_node.set_instance(built_instance)

        top_decorated_node = new_instance_node

        for dec in context.find_decorators_that_apply(self, decorated_instance_node=new_instance_node):
            next_decorated_node = DependencyNode(
                service_type=self.service_type,
                implementation=dec.decorator_type,
                lifespan=self.lifespan,
            )
            top_decorated_node.add_decorator(next_decorated_node)
            built_instance = await dec.decorate_async(built_instance, context, next_decorated_node, self)
            next_decorated_node.set_instance(built_instance)
            top_decorated_node = next_decorated_node

        context.new_instance_created(self, top_decorated_node)
        self.was_used = True
        return built_instance


class _DecoratorStore:
    def __init__(self):
        self._decorators: list[tuple[int, Decorator]] = []
        self.next_index = 0

    @classmethod
    def sort_key(cls, item: tuple[int, Decorator]):
        insert_index, decorator = item
        sort_index = decorator.position
        return (sort_index, -insert_index)

    def add_decorator(self, decorator: Decorator):
        self._decorators.append((self.next_index, decorator))
        self.next_index += 1
        self._decorators.sort(key=self.sort_key)

    def __len__(self):
        return len(self._decorators)

    def __iter__(self):
        for _, decorator in self._decorators:
            yield decorator


class _Registry:
    def __init__(self):
        self._registrations: dict[type, deque[_Registration]] = defaultdict(deque)
        self._decorators: dict[type, _DecoratorStore] = defaultdict(_DecoratorStore)
        self._pre_configurations: dict[type, deque[PreConfiguration]] = defaultdict(deque)

    def register_implementation(
        self,
        *,
        service_type: type[TService],
        implementation: type[TService],
        lifespan: Lifespan,
        name: str | None,
        dependency_config: DependencyConfig,
        tags: Iterable[Tag] | None,
        parent_node_filter: NodeFilter,
        scoped_teardown: Callable[[TService], Any] | None,
    ):
        registration = _Registration(
            activator_class=FactoryActivator,
            service_type=service_type,
            implementation=implementation,
            lifespan=lifespan,
            name=name,
            dependency_config=dependency_config,
            parent_node_filter=parent_node_filter,
            scoped_teardown=scoped_teardown,
            tags=tags,
        )

        self._registrations[service_type].appendleft(registration)
        self._registrations[implementation].appendleft(registration)

    def register_concrete(
        self,
        *,
        service_type: type[TService],
        lifespan: Lifespan,
        name: str | None,
        dependency_config: DependencyConfig,
        tags: Iterable[Tag] | None,
        parent_node_filter: NodeFilter,
        scoped_teardown: Callable[[TService], Any] | None,
    ):
        registration = _Registration(
            activator_class=FactoryActivator,
            service_type=service_type,
            implementation=service_type,
            lifespan=lifespan,
            name=name,
            dependency_config=dependency_config,
            parent_node_filter=parent_node_filter,
            scoped_teardown=scoped_teardown,
            tags=tags,
        )

        self._registrations[service_type].appendleft(registration)

    def register_instance(
        self,
        *,
        service_type: type[TService],
        instance: TService,
        lifespan: Lifespan,
        name: str | None,
        dependency_config: DependencyConfig,
        tags: Iterable[Tag] | None,
        parent_node_filter: NodeFilter,
        scoped_teardown: Callable[[TService], Any] | None,
    ):
        instance_lifespan = lifespan if lifespan == Lifespan.singleton else Lifespan.scoped

        registration = _Registration(
            activator_class=FactoryActivator,
            service_type=service_type,
            implementation=constant(instance),
            lifespan=instance_lifespan,
            name=name,
            dependency_config=dependency_config,
            parent_node_filter=parent_node_filter,
            scoped_teardown=scoped_teardown,
            tags=tags,
        )
        self._registrations[service_type].appendleft(registration)

    @classmethod
    def _get_activator_class(cls, creator_function: Callable) -> type[Activator]:
        if inspect.iscoroutinefunction(creator_function):
            return AsyncFactoryActivator
        if inspect.isasyncgenfunction(creator_function):
            return AsyncGeneratorActivator
        if inspect.isgeneratorfunction(creator_function):
            return GeneratorActivator
        return FactoryActivator

    def register_factory(
        self,
        *,
        service_type: type[TService],
        factory: Callable[..., TService],
        lifespan: Lifespan,
        name: str | None,
        dependency_config: DependencyConfig,
        tags: Iterable[Tag] | None,
        parent_node_filter: NodeFilter,
        scoped_teardown: Callable[[TService], Any] | None,
    ):
        registration = _Registration(
            activator_class=self._get_activator_class(factory),
            service_type=service_type,
            implementation=factory,
            lifespan=lifespan,
            name=name,
            dependency_config=dependency_config,
            parent_node_filter=parent_node_filter,
            scoped_teardown=scoped_teardown,
            tags=tags,
        )

        self._registrations[service_type].appendleft(registration)

    def register_decorator(
        self,
        *,
        service_type: type,
        decorator_type: type | Callable,
        registration_filter: Callable[[_Registration], bool],
        decorator_node_filter: NodeFilter,
        decorated_arg: str | None,
        dependency_config: DependencyConfig,
        position: int,
    ):
        decorator = Decorator(
            service_type=service_type,
            decorator_type=decorator_type,
            registration_filter=registration_filter,
            activator_class=self._get_activator_class(decorator_type),
            decorator_node_filter=decorator_node_filter,
            decorated_arg=decorated_arg,
            dependency_config=dependency_config,
            position=position,
        )
        self._decorators[service_type].add_decorator(decorator)

    def register_pre_configuration(
        self,
        *,
        service_type: type | Iterable[type],
        configuration_function: Callable,
        registration_filter: RegistrationFilter,
        dependency_config: DependencyConfig,
        continue_on_failure: bool = False,
    ):
        pre_configuration = PreConfiguration(
            pre_configuration=configuration_function,
            activator_class=self._get_activator_class(configuration_function),
            registration_filter=registration_filter,
            dependency_config=dependency_config,
            continue_on_failure=continue_on_failure,
        )

        service_types = service_type if isinstance(service_type, Iterable) else (service_type,)

        for st in service_types:
            self._pre_configurations[st].appendleft(pre_configuration)

    def get_registrations(self, service_type: type):
        return self._registrations[service_type]

    def get_pre_configurations(self, service_type: type):
        return self._pre_configurations[service_type]

    def get_decorators(self, service_type: type):
        return self._decorators[service_type]


class _DependencyCache:
    def __init__(self, scope: Scope):
        self.scope = scope
        self._current_items: dict[str, DependencyNode] = {
            **{k: v for k, v in scope.singleton_instances.items()},
            **{k: v for k, v in scope.scoped_instances.items()},
        }

    def get(self, registration_id: str) -> DependencyNode | None:
        node = self._current_items.get(registration_id)
        if node:
            return node

        node = self.scope.find_scoped_node(registration_id)
        if node:
            self._current_items[registration_id] = node
            return node

        node = self.scope.find_singleton_node(registration_id)
        if node:
            self._current_items[registration_id] = node
            return node

        return None

    def put(self, registration: _Registration, dependency_node: DependencyNode):
        if registration.lifespan == Lifespan.singleton:
            self.scope.add_singleton_node(registration, dependency_node)
        elif registration.lifespan == Lifespan.scoped:
            self.scope.add_scoped_node(
                registration,
                dependency_node,
            )

        if registration.lifespan >= Lifespan.once_per_graph:
            self._current_items[registration.id] = dependency_node

    def clean_up_parents(self):
        for node in self._current_items.values():
            node.unparent()


class _ResolvingContext:
    def __init__(self, scope: Scope):
        self.scope = scope
        self._cache = _DependencyCache(scope=scope)

    def try_generic_fallback(
        self, service_type: _GenericAlias, parent_node: DependencyNode, registration_filter: RegistrationFilter
    ):
        return self.find_registration(
            service_type=service_type.__origin__,
            registration_filter=registration_filter,
            parent_node=parent_node,
        )

    def find_registration(
        self,
        service_type: type,
        registration_filter: Callable,
        parent_node: DependencyNode,
    ) -> _Registration:
        regs = self.find_registrations(
            service_type=service_type,
            registration_filter=registration_filter,
            parent_node=parent_node,
            registration_list_modifier=default_registration_list_modifier,
        )
        reg = next(iter(regs), None)

        if reg is None:
            if type(service_type) is _GenericAlias:
                reg = self.try_generic_fallback(service_type, parent_node, registration_filter)
            if reg is None:
                raise CannotResolveError()
        return reg

    def find_registrations(
        self,
        service_type: type,
        registration_filter: Callable[[_Registration], bool],
        registration_list_modifier: RegistrationListModifier,
        parent_node: DependencyNode,
    ) -> list[_Registration]:
        registrations = self.scope.find_registrations(
            service_type=service_type,
            parent_node=parent_node,
            filter=registration_filter,
            list_modifier=registration_list_modifier,
        )
        return registrations

    def find_decorators_that_apply(
        self, registration: _Registration, decorated_instance_node: DependencyNode
    ) -> list[Decorator]:
        return self.scope.find_decorators(registration=registration, decorated_instance_node=decorated_instance_node)

    def find_pre_configurations_that_apply(self, registration: _Registration):
        return self.scope.find_pre_configurations(registration=registration)

    def add_finalizer(self, lifespan: Lifespan, generator: Callable):
        self.scope.add_finalizer(lifespan, generator)

    def get_cached(self, reg_id: str) -> DependencyNode | None:
        return self._cache.get(reg_id)

    def new_instance_created(self, registration: _Registration, node: DependencyNode):
        self._cache.put(registration=registration, dependency_node=node)

    def __del__(self):
        self._cache.clean_up_parents()


class Resolver(Protocol):
    def resolve(
        self,
        service_type: type[TService],
        filter: RegistrationFilter = default_registration_filter,
    ) -> TService: ...

    async def resolve_async(
        self,
        service_type: type[TService],
        filter: RegistrationFilter = default_registration_filter,
    ) -> TService: ...


class Registrator(Protocol):
    def register(
        self,
        service_type: type[TService],
        implementation_type: type[TService] | None = None,
        *,
        factory: Callable[..., TService] | None = None,
        instance: TService | None = None,
        lifespan: Lifespan = Lifespan.once_per_graph,
        name: str | None = None,
        dependency_config: DependencyConfig = {},
        tags: Iterable[Tag] | None = None,
        parent_node_filter: NodeFilter = default_parent_node_filter,
        scoped_teardown: Callable[[TService], Any] | None = None,
    ): ...


class ScopeCreator(Protocol):
    def new_scope(
        self,
    ) -> Scope: ...


class Scope:
    def __init__(
        self,
    ):
        self._id = str(uuid4())
        self._registry = _Registry()
        self._scoped_instances: dict[str, DependencyNode] = {}
        self._sync_teardowns: dict[str, Callable] = {}
        self._async_teardowns: dict[str, Callable] = {}
        self._finalizers: deque[Callable] = deque()

        self.register(ScopeCreator, instance=self)
        self.register(Resolver, instance=self)
        self.register(Registrator, instance=self)
        self.register(Scope, instance=self)

    @property
    def id(self):
        return self._id

    def resolve(
        self,
        service_type: type[TService],
        filter: RegistrationFilter = default_registration_filter,
    ) -> TService:
        graph = self.resolve_dependency_graph(service_type, filter)
        return graph.instance

    async def resolve_async(
        self,
        service_type: type[TService],
        filter: RegistrationFilter = default_registration_filter,
    ) -> TService:
        graph = await self.resolve_dependency_graph_async(service_type, filter)
        return graph.instance

    def call(self, fn: Callable[..., TReturn]) -> TReturn:
        name: str = str(uuid4())
        with self.new_scope() as scope:
            return scope.register(Callable, fn, name=name).resolve(Callable, filter=lambda r: r.name == name)  # type: ignore  # type: ignore

    async def call_async(self, fn: Callable[..., TReturn]) -> TReturn:
        name: str = str(uuid4())
        with self.new_scope() as scope:
            return await scope.register(Callable, fn, name=name).resolve_async(  # type: ignore
                Callable,  # type: ignore
                filter=lambda r: r.name == name,
            )

    def resolve_dependency_graph(
        self,
        service_type: type,
        filter: RegistrationFilter = default_registration_filter,
    ) -> DependencyGraph:
        graph = DependencyGraph(service_type=service_type, filter=filter)
        context = _ResolvingContext(self)
        graph.resolve(context)
        del context
        return graph

    async def resolve_dependency_graph_async(
        self,
        service_type: type,
        filter: RegistrationFilter = default_registration_filter,
    ) -> DependencyGraph:
        graph = DependencyGraph(service_type=service_type, filter=filter)
        context = _ResolvingContext(self)
        await graph.resolve_async(context)
        del context
        return graph

    def resolve_from_registration_id(self, service_type: type[TService], registration_id: str):
        """
        Resolve a service from a registration ID.
        This is useful for advanced use cases where you need to resolve a specific registration
        """
        return self.resolve(
            service_type,
            filter=lambda r: r.id == registration_id,
        )

    async def resolve_from_registration_id_async(self, service_type: type[TService], registration_id: str):
        """
        Resolve a service from a registration ID.
        This is useful for advanced use cases where you need to resolve a specific registration
        """
        return await self.resolve_async(
            service_type,
            filter=lambda r: r.id == registration_id,
        )

    def register(
        self,
        service_type: type[TService],
        implementation_type: type[TService] | None = None,
        *,
        factory: Callable[..., TService] | None = None,
        instance: TService | None = None,
        lifespan: Lifespan = Lifespan.once_per_graph,
        name: str | None = None,
        dependency_config: DependencyConfig = {},
        tags: Iterable[Tag] | None = None,
        parent_node_filter: NodeFilter = default_parent_node_filter,
        scoped_teardown: Callable[[TService], Any] | None = None,
    ) -> Scope:
        if instance is not None:
            self._registry.register_instance(
                service_type=service_type,
                instance=instance,
                lifespan=lifespan,
                name=name,
                tags=tags,
                dependency_config=dependency_config,
                parent_node_filter=parent_node_filter,
                scoped_teardown=scoped_teardown,
            )
        elif factory is not None:
            self._registry.register_factory(
                service_type=service_type,
                factory=factory,
                lifespan=lifespan,
                name=name,
                tags=tags,
                dependency_config=dependency_config,
                parent_node_filter=parent_node_filter,
                scoped_teardown=scoped_teardown,
            )
        elif implementation_type is not None:
            self._registry.register_implementation(
                service_type=service_type,
                implementation=implementation_type,
                lifespan=lifespan,
                name=name,
                tags=tags,
                dependency_config=dependency_config,
                parent_node_filter=parent_node_filter,
                scoped_teardown=scoped_teardown,
            )
        else:
            self._registry.register_concrete(
                service_type=service_type,
                lifespan=lifespan,
                name=name,
                tags=tags,
                dependency_config=dependency_config,
                parent_node_filter=parent_node_filter,
                scoped_teardown=scoped_teardown,
            )

        return self

    def pre_configure(
        self,
        service_type: type | Iterable[type],
        configuration_function: Callable,
        *,
        registration_filter: RegistrationFilter = default_registration_filter,
        dependency_config: DependencyConfig = {},
        continue_on_failure: bool = False,
    ) -> Scope:
        self._registry.register_pre_configuration(
            service_type=service_type,
            configuration_function=configuration_function,
            registration_filter=registration_filter,
            dependency_config=dependency_config,
            continue_on_failure=continue_on_failure,
        )

        return self

    def register_decorator(
        self,
        service_type: type,
        decorator_type: type | Callable,
        *,
        registration_filter: Callable[[_Registration], bool] = default_registration_filter,
        decorator_node_filter: NodeFilter = default_decorated_node_filter,
        decorated_arg: str | None = None,
        dependency_config: DependencyConfig = {},
        position: int = 0,
    ) -> Scope:
        self._registry.register_decorator(
            service_type=service_type,
            decorator_type=decorator_type,
            registration_filter=registration_filter,
            decorator_node_filter=decorator_node_filter,
            decorated_arg=decorated_arg,
            dependency_config=dependency_config,
            position=position,
        )

        return self

    def add_singleton_node(self, registration: _Registration, node: DependencyNode) -> Scope: ...

    def find_singleton_node(self, registration_id: str) -> DependencyNode | None: ...

    def find_scoped_node(self, registration_id: str) -> DependencyNode | None:
        return self._scoped_instances.get(registration_id)

    def get_registration_ids(
        self,
        service_type,
        *,
        filter: RegistrationFilter = default_registration_filter,
        list_modifier: RegistrationListModifier = default_registration_list_modifier,
    ) -> list[str]:
        """
        Get the registration IDs for a specific service type.
        This is for more advanced use cases where you need to know more about the internals of the Scope
        """

        registrations = [r for r in self._registry.get_registrations(service_type) if filter(r)]
        registrations = list_modifier(registrations)  # type: ignore
        return [r.id for r in registrations]

    def find_registrations(
        self,
        *,
        service_type,
        filter: RegistrationFilter = default_registration_filter,
        list_modifier: RegistrationListModifier = default_registration_list_modifier,
        parent_node: Node,
    ) -> list[_Registration]:
        registrations = [
            r for r in self._registry.get_registrations(service_type) if filter(r) and r.parent_node_filter(parent_node)
        ]
        return list_modifier(registrations)  # type: ignore

    def find_decorators(
        self, *, registration: _Registration, decorated_instance_node: DependencyNode
    ) -> list[Decorator]:
        return [
            d
            for d in self._registry.get_decorators(registration.service_type)
            if d.registration_filter(registration) and d.decorated_node_filter(decorated_instance_node)
        ]

    def find_pre_configurations(self, *, registration: _Registration):
        return [
            c
            for c in self._registry.get_pre_configurations(registration.service_type)
            if not c.has_run and c.registration_filter(registration)
        ]

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args, **kwargs):
        await self._run_async_teardowns()
        self._run_sync_teardowns()
        await self._async_close_finalizers()

    def __enter__(self):
        return self

    def __exit__(self, *args, **kwargs):
        self._run_sync_teardowns()
        self._close_finalizers()

    def add_finalizer(self, lifespan: Lifespan, finalizer: Callable) -> Scope:
        self._finalizers.appendleft(finalizer)
        return self

    def _close_finalizers(self):
        for finalizer in self._finalizers:
            finalizer()

    async def _async_close_finalizers(self):
        for finalizer in self._finalizers:
            if inspect.iscoroutinefunction(finalizer):
                await finalizer()
            else:
                finalizer()

    async def _run_async_teardowns(self):
        for registration_id, teardown_fn in self._async_teardowns.items():
            cached_dependency = self._scoped_instances[registration_id]
            await teardown_fn(cached_dependency.instance)

    def _run_sync_teardowns(self):
        for registration_id, teardown_fn in self._sync_teardowns.items():
            cached_dependency = self._scoped_instances[registration_id]
            teardown_fn(cached_dependency.instance)

    def add_scoped_node(self, registration: _Registration, node: DependencyNode) -> Scope:
        self._scoped_instances[registration.id] = node
        if registration.scoped_teardown:
            is_async = inspect.iscoroutinefunction(registration.scoped_teardown)
            if is_async:
                self._async_teardowns[registration.id] = registration.scoped_teardown
            else:
                self._sync_teardowns[registration.id] = registration.scoped_teardown

        return self

    @property
    def scoped_instances(self) -> dict[str, DependencyNode]:
        return self._scoped_instances

    @property
    def singleton_instances(self) -> dict[str, DependencyNode]: ...

    def new_scope(self) -> Scope: ...


class ChildScope(Scope):
    def __init__(self, parent_scope: Scope):
        super().__init__()
        self._parent_scope = parent_scope

    def add_singleton_node(
        self,
        registration: _Registration,
        node: DependencyNode,
    ) -> ChildScope:
        self._parent_scope.add_singleton_node(registration, node)
        return self

    def find_singleton_node(self, registration_id: str) -> DependencyNode | None:
        return self._parent_scope.find_singleton_node(registration_id)

    def find_scoped_node(self, registration_id: str) -> DependencyNode | None:
        if scoped_node := super().find_scoped_node(registration_id):
            return scoped_node
        return self._parent_scope.find_scoped_node(registration_id)

    def find_registrations(
        self,
        *,
        service_type,
        filter: Callable[[_Registration], bool] = default_registration_filter,
        list_modifier=default_registration_list_modifier,
        parent_node: Node,
    ) -> list[_Registration]:
        registrations = super().find_registrations(service_type=service_type, filter=filter, parent_node=parent_node)
        from_parent = self._parent_scope.find_registrations(
            service_type=service_type, filter=filter, parent_node=parent_node
        )
        return list_modifier(registrations + from_parent)  # type: ignore

    def find_decorators(
        self, *, registration: _Registration, decorated_instance_node: DependencyNode
    ) -> list[Decorator]:
        decorators = super().find_decorators(registration=registration, decorated_instance_node=decorated_instance_node)

        return decorators + self._parent_scope.find_decorators(
            registration=registration, decorated_instance_node=decorated_instance_node
        )

    def find_pre_configurations(self, *, registration: _Registration):
        pre_configurations = super().find_pre_configurations(registration=registration)
        return pre_configurations + self._parent_scope.find_pre_configurations(registration=registration)

    def add_finalizer(self, lifespan: Lifespan, finalizer: Callable) -> ChildScope:
        if lifespan == Lifespan.singleton:
            self._parent_scope.add_finalizer(lifespan, finalizer)
            return self

        super().add_finalizer(lifespan, finalizer)
        return self

    @property
    def singleton_instances(self) -> dict[str, DependencyNode]:
        return self._parent_scope.singleton_instances

    def new_scope(self) -> Scope:
        return ChildScope(self)


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


class Container(Scope):
    def __init__(self):
        super().__init__()
        self._singletons: dict[str, DependencyNode] = {}
        self.register(Container, instance=self)

    def register_subclasses(
        self,
        base_type: type,
        *,
        lifespan: Lifespan = Lifespan.once_per_graph,
        subclass_type_filter: Callable[[type], bool] = always_true,
        name: str | None = None,
        tags: list[Tag] | None = None,
        parent_node_filter: NodeFilter = default_parent_node_filter,
    ):
        full_type_filter = ~(is_abstract) & subclass_type_filter
        subclasses = get_subclasses(base_type, filter=full_type_filter)
        for sc in subclasses:
            self.register(
                base_type,
                sc,
                lifespan=lifespan,
                name=name,
                tags=tags,
                parent_node_filter=parent_node_filter,
            )

    @staticmethod
    def _get_target_generic_base(generic_service_type: type, subclass: type):
        return next(
            (
                try_to_map_generic_args_to_open_type(b, subclass)
                for b in get_generic_bases(
                    subclass,
                    lambda t: getattr(t, "__origin__", None) == generic_service_type,
                )
            ),
            None,
        )

    def register_generic_subclasses(
        self,
        generic_service_type: type,
        *,
        fallback_type: type | None = None,
        lifespan: Lifespan = Lifespan.once_per_graph,
        subclass_type_filter: Callable[[type], bool] = always_true,
        name: str | None = None,
        tags: list[Tag] | None = None,
        parent_node_filter: NodeFilter = default_parent_node_filter,
    ) -> Container:
        full_type_filter = ~is_abstract & subclass_type_filter
        subclasses = get_subclasses(generic_service_type, filter=full_type_filter)
        for subclass in subclasses:
            target_generic_base = self._get_target_generic_base(generic_service_type, subclass)
            if target_generic_base:
                self.register(
                    target_generic_base,
                    subclass,
                    lifespan=lifespan,
                    name=name,
                    tags=tags,
                    parent_node_filter=parent_node_filter,
                )

        if fallback_type:
            self.register(
                generic_service_type,
                fallback_type,
                lifespan=lifespan,
                name=name,
                tags=tags,
                parent_node_filter=parent_node_filter,
            )

        return self

    def register_generic_decorator(
        self,
        generic_service_type: type,
        generic_decorator_type: type,
        *,
        subclass_type_filter: Callable[[type], bool] = always_true,
        decorated_arg: str | None = None,
        dependency_config: DependencyConfig = {},
        registration_filter: Callable[[_Registration], bool] = default_registration_filter,
        decorated_node_filter: NodeFilter = default_decorated_node_filter,
        position: int = 0,
    ) -> Container:
        full_type_filter = ~is_abstract & ~name_starts_with("__DecoratedGeneric__") & subclass_type_filter
        subclasses = get_subclasses(generic_service_type, filter=full_type_filter)
        decorator_generic_map = GenericTypeMap(generic_decorator_type)
        decorator_is_open_generic = decorator_generic_map.is_generic_mapping_open()

        for subclass in subclasses:
            target_generic_base = try_to_map_generic_args_to_open_type(generic_service_type, subclass)
            if target_generic_base:
                if decorator_is_open_generic:
                    concrete_decorator = try_to_map_generic_args_to_open_type(generic_decorator_type, subclass)
                    DecoratedType = create_generic_decorator_type(concrete_decorator)  # noqa: N806

                    self.register_decorator(
                        target_generic_base,
                        DecoratedType,
                        decorated_arg=decorated_arg,
                        dependency_config=dependency_config,
                        registration_filter=registration_filter,
                        decorator_node_filter=decorated_node_filter,
                        position=position,
                    )
                else:
                    self.register_decorator(
                        target_generic_base,
                        generic_decorator_type,
                        decorated_arg=decorated_arg,
                        dependency_config=dependency_config,
                        registration_filter=registration_filter,
                        decorator_node_filter=decorated_node_filter,
                        position=position,
                    )

        return self

    def force_run_pre_configuration(
        self,
        service_type: type,
        registration_filter: RegistrationFilter = default_registration_filter,
    ):
        self.resolve(service_type, filter=registration_filter)

    async def force_run_pre_configuration_async(
        self,
        service_type: type,
        registration_filter: RegistrationFilter = default_registration_filter,
    ):
        await self.resolve_async(service_type, filter=registration_filter)

    def expect_to_be_scoped(self, service_type: type, name: str | None = None) -> Container:
        self.register(
            service_type=service_type,
            factory=type_expected_to_be_scoped(service_type, name),
            name=name,
        )
        return self

    def apply_bundle(
        self,
        bundle_fn: Callable[[Container], None],
    ) -> Container:
        bundle_fn(self)

        return self

    def has_registration(self, service_type, filter: RegistrationFilter = default_registration_filter):
        found_registrations = [r for r in self._registry.get_registrations(service_type) if filter(r)]
        return len(found_registrations) > 0

    def add_singleton_node(
        self,
        registration: _Registration,
        node: DependencyNode,
    ) -> Container:
        self._singletons[registration.id] = node

        return self

    def find_singleton_node(self, registration_id: str) -> DependencyNode | None:
        return self._singletons.get(registration_id)

    @property
    def singleton_instances(self) -> dict[str, DependencyNode]:
        return self._singletons

    def new_scope(self) -> Scope:
        return ChildScope(self)


@dataclass(kw_only=True)
class DependencySettings:
    value_factory: ParameterValueFactory = default_parameter_value_factory
    filter: RegistrationFilter = default_registration_filter
    list_modifier: RegistrationListModifier = default_registration_list_modifier


DependencyConfig = dict[str, DependencySettings]
RegistrationFilter = Callable[[_Registration], bool]
NodeFilter = Callable[[Node], bool]
ParameterValueFactory = Callable[[Any, DependencyContext], Any]
RegistrationListModifier = Callable[[list[Registration]], list[Registration]]
