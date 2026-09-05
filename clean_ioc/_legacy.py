"""Private V1 machinery retained while the V2 compiler is made self-contained."""

from __future__ import annotations

import abc
import asyncio
import concurrent.futures
import contextvars
import functools
import inspect
import logging
import threading
import types
from collections import defaultdict, deque
from collections.abc import Callable, Collection, Iterable, MutableSequence, Sequence
from contextlib import _AsyncGeneratorContextManager, _GeneratorContextManager, contextmanager
from dataclasses import dataclass
from enum import IntEnum
from typing import (
    TYPE_CHECKING,
    Any,
    ClassVar,
    Protocol,
    TypeVar,
    _GenericAlias,  # type: ignore
    get_args,
    get_origin,
    get_type_hints,
)
from typing import Collection as TypingCollection
from typing import Iterable as TypingIterable
from typing import MutableSequence as TypingMutableSequence
from typing import Sequence as TypingSequence
from uuid import uuid4

from funcie import always_true, constant
from typetoolbox import get_subclasses
from typetoolbox.generics import (
    GenericTypeMap,
    get_generic_bases,
    try_to_map_generic_args_to_specialization,
)

from clean_ioc.generic_utils import map_type_vars_to_parent
from clean_ioc.utils import send_deprecation_warning, singleton

from ._legacy_configuration import (
    EMPTY,
    UNKNOWN,
    DependencyConfig,
    DependencySettings,
    NodeFilter,
    RegistrationFilter,
    RegistrationListModifier,
    RemoveDependencySetting,
    SubDependencies,
    Tag,
)
from ._legacy_configuration import (
    _Empty as _empty,
)
from ._legacy_configuration import (
    default_component_filter as default_registration_filter,
)
from ._legacy_configuration import (
    default_component_list_modifier as default_registration_list_modifier,
)
from .type_filters import is_abstract, name_starts_with

if TYPE_CHECKING:
    from ._legacy_diagnostics import DependencyPlan, ValidationReport

logger = logging.getLogger(__name__)

TService = TypeVar("TService")
TReturn = TypeVar("TReturn")


@functools.cache
def create_generic_decorator_type(concrete_decorator: type):
    # Memoised: minting a fresh class per call leaks — dynamically created
    # classes end up pinned for the life of the process by typing's
    # parameterisation caches (and, before typetoolbox held its GenericTypeMap
    # cache weakly, by that too), so every register_generic_decorator call on
    # a new container grew the heap by thousands of classes. The generated
    # class is a pure template (never mutated after creation), so one per
    # concrete decorator serves every container in the process.
    return types.new_class(
        f"__DecoratedGeneric__{concrete_decorator.__name__}",
        (concrete_decorator,),
        {},
    )


def dependency_config_to_subdependencies(dependency_config: DependencyConfig) -> SubDependencies:
    dependencies = {}

    for name, settings in dependency_config.items():
        if isinstance(settings, DependencySettings):
            dependencies[name] = settings
        else:
            dependencies[name] = DependencySettings(value_factory=constant(settings))

    return dependencies


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

        arg_type = args[name]

        d[name] = ArgInfo(name=name, arg_type=arg_type, default_value=param.default)
    return d


def _set_up_dependencies(
    creator_function: Callable,
    dependency_config: SubDependencies,
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


default_parent_node_filter = constant(True)
default_decorated_node_filter = constant(True)


class Lifespan(IntEnum):
    transient = 0
    once_per_graph = 1
    scoped = 2
    singleton = 3


@dataclass(frozen=True)
class _BuildOutcome:
    error: BaseException | None = None


class _SharedBuildCoordinator:
    """Coordinate scoped/singleton activation across threads and event loops."""

    def __init__(self):
        self._lock = threading.Lock()
        self._in_flight: dict[str, concurrent.futures.Future[_BuildOutcome]] = {}

    def begin(self, registration_id: str) -> tuple[concurrent.futures.Future[_BuildOutcome], bool]:
        with self._lock:
            if existing := self._in_flight.get(registration_id):
                return existing, False

            future: concurrent.futures.Future[_BuildOutcome] = concurrent.futures.Future()
            self._in_flight[registration_id] = future
            return future, True

    def finish(
        self,
        registration_id: str,
        future: concurrent.futures.Future[_BuildOutcome],
        error: BaseException | None = None,
    ) -> None:
        with self._lock:
            if self._in_flight.get(registration_id) is future:
                del self._in_flight[registration_id]

        future.set_result(_BuildOutcome(error=error))


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
        self._chain_items: list[dict] = []
        self.first_dependency: Dependency | None = None

    def append_registration(self, r: _Registration):
        self._chain_items.append(
            {
                "type": "Registration",
                "id": r.id,
                "service_type": r.service_type,
                "implementation": r.implementation,
                "name": r.name,
                "lifespan": r.lifespan.name,
                "tags": [(t.name, t.value) for t in r.tags],
            }
        )

    def append_decorator(self, d: Decorator):
        self._chain_items.append(
            {
                "type": "Decorator",
                "service_type": d.service_type,
                "decorator_type": d.decorator_type,
                "decorated_arg": d.decorated_arg,
            }
        )

    def append_dependency(self, d: Dependency):
        self._chain_items.append(
            {
                "type": "Dependency",
                "service_type": d.service_type,
                "arg_name": d.name,
                "settings": {
                    "filter": d.settings.filter.__repr__(),
                    "value_factory": d.settings.value_factory.__repr__(),
                },
            }
        )

        if not self.first_dependency:
            self.first_dependency = d

    def append_pre_configuration(self, p: PreConfiguration):
        self._chain_items.append(
            {
                "type": "PreConfiguration",
                "pre_configuration": p.configuration_fn,
            }
        )

    def _print_chain_item(self, item: dict):
        content = "-------------------------\n"

        for key, value in item.items():
            content += f"{key}: {value}\n"

        content += "-------------------------\n"

        return content

    @property
    def chain(self):
        return "\u2b06\n".join(self._print_chain_item(item) for item in self._chain_items)

    @property
    def message(self):
        first_dependency = self.first_dependency
        if not first_dependency:
            return "Failed to resolve unknown dependency"

        return (
            f"***{first_dependency.parent_implementation} could not find "
            f"{first_dependency.service_type} for argument '{first_dependency.name}'***"
        )

    def __str__(self):
        return f"\n{self.message}\nChain:\n\n{self.chain}"


def _display_type(subject: Any) -> str:
    origin = get_origin(subject)
    arguments = get_args(subject)
    if origin is not None and arguments:
        return f"{_display_type(origin)}[{', '.join(_display_type(argument) for argument in arguments)}]"
    return getattr(subject, "__name__", str(subject).replace("typing.", ""))


class CircularDependencyError(CannotResolveError):
    """Raised when a registration is encountered twice in one active graph path."""

    def __init__(self, registrations: Sequence[_Registration]):
        super().__init__()
        self.registrations = tuple(registrations)

    @property
    def message(self):
        path = " -> ".join(_display_type(registration.service_type) for registration in self.registrations)
        return f"Circular dependency detected: {path}"


class CaptiveDependencyError(CannotResolveError):
    """Raised when a singleton attempts to retain a scoped dependency."""

    def __init__(self, singleton: _Registration, scoped: _Registration, registrations: Sequence[_Registration]):
        super().__init__()
        self.singleton = singleton
        self.scoped = scoped
        self.registrations = tuple(registrations)

    @property
    def message(self):
        path = " -> ".join(_display_type(registration.service_type) for registration in self.registrations)
        return (
            f"Singleton {_display_type(self.singleton.service_type)} cannot depend on scoped "
            f"{_display_type(self.scoped.service_type)}. Path: {path}"
        )


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
            self.service_type = map_type_vars_to_parent(child_type=service_type, parent_type=parent_implementation)
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

    @contextmanager
    def _propagate_resolve_error(self):
        try:
            yield
        except CannotResolveError as e:
            e.append_dependency(self)
            raise e

    def resolve(self, context: _ResolvingContext, dependency_node: DependencyNode) -> Any:
        with self._propagate_resolve_error():
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
                    service_type=self.service_type,  # pyright: ignore[reportArgumentType]  # ty:ignore[invalid-argument-type]
                    implementation=self.generic_collection_type,
                    lifespan=Lifespan.transient,
                )

                dependency_node.add_child(sequence_node)

                generator = (r.build(context, sequence_node) for r in regs)
                collection = self.generic_collection_type(generator)
                sequence_node.set_instance(collection)

                return collection

            reg = context.find_registration(
                service_type=self.service_type,  # pyright: ignore[reportArgumentType]  # ty:ignore[invalid-argument-type]
                registration_filter=self.settings.filter,
                parent_node=dependency_node,
            )
            return reg.build(context, dependency_node)

    async def resolve_async(self, context: _ResolvingContext, dependency_node: DependencyNode) -> Any:
        with self._propagate_resolve_error():
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
                    service_type=self.service_type,  # pyright: ignore[reportArgumentType]  # ty:ignore[invalid-argument-type]
                    implementation=self.generic_collection_type,
                    lifespan=Lifespan.transient,
                )

                dependency_node.add_child(sequence_node)

                generator = (r.build_async(context, sequence_node) for r in regs)
                items = await asyncio.gather(*generator)
                collection = self.generic_collection_type(items)
                sequence_node.set_instance(collection)

                return collection

            reg = context.find_registration(
                service_type=self.service_type,  # pyright: ignore[reportArgumentType]  # ty:ignore[invalid-argument-type]
                registration_filter=self.settings.filter,
                parent_node=dependency_node,
            )
            return await reg.build_async(context, dependency_node)


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
            cm.__exit__(None, None, None)

        return inner

    @classmethod
    def _asynccontextmanager_finalizer(cls, cm: _AsyncGeneratorContextManager):
        async def inner():
            await cm.__aexit__(None, None, None)

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
        sub_dependencies: SubDependencies,
        continue_on_failure: bool = False,
    ):
        self.configuration_fn = pre_configuration
        self.activator_class = activator_class
        self.registration_filter = registration_filter
        self.dependencies = _set_up_dependencies(pre_configuration, sub_dependencies)
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

    @contextmanager
    def _propagate_resolve_error(self):
        try:
            yield
        except CannotResolveError as e:
            e.append_pre_configuration(self)
            raise e

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
        sub_dependencies: SubDependencies = {},
        position: int = 0,
    ):
        self.service_type = service_type
        self.decorator_type = decorator_type

        dependencies = _set_up_dependencies(decorator_type, sub_dependencies)

        self.decorated_arg = decorated_arg or next(
            name for name, dep in dependencies.items() if dep.service_type == service_type
        )
        self.registration_filter = registration_filter
        self.decorated_node_filter = decorator_node_filter
        self.activator_class = activator_class
        self.position = position

        del dependencies[self.decorated_arg]

        self.dependencies: dict[str, Dependency] = dependencies

    @contextmanager
    def _propagate_resolve_error(self):
        try:
            yield
        except CannotResolveError as e:
            e.append_decorator(self)
            raise e

    def decorate(
        self, instance: Any, context: _ResolvingContext, dependency_node: DependencyNode, registration: Registration
    ):
        with self._propagate_resolve_error():
            resolved_dependencies = _resolve_dependencies(self.dependencies, context, dependency_node)
            resolved_dependencies[self.decorated_arg] = instance

            return self.activator_class.activate(
                self.decorator_type, resolved_dependencies, context, lifespan=registration.lifespan
            )

    async def decorate_async(
        self, instance: Any, context: _ResolvingContext, dependency_node: DependencyNode, registration: Registration
    ):
        with self._propagate_resolve_error():
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
        "is_instance",
        "is_root_owned_instance",
        "is_named",
        "lifespan",
        "name",
        "parent_node_filter",
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
        sub_dependencies: SubDependencies = {},
        parent_node_filter: NodeFilter = default_parent_node_filter,
        tags: Iterable[Tag] | None = None,
        is_instance: bool = False,
        is_root_owned_instance: bool = False,
    ):
        self.service_type = service_type
        self.implementation = implementation
        self.is_instance = is_instance
        self.is_root_owned_instance = is_root_owned_instance
        self.activator_class = activator_class
        self.lifespan = lifespan
        self.name = name
        self.tags = tuple(tags) if tags else tuple()
        self.id = str(uuid4())
        self.parent_node_filter = parent_node_filter
        self.was_used = False
        self.is_named = name is not None
        self.dependencies: dict[str, Dependency] = _set_up_dependencies(implementation, sub_dependencies)

        self._generic_mapping: GenericTypeMap | None = None

    def has_tag(self, name: str, value: str | None):
        if value is not None:
            return any(t.name == name and t.value == value for t in self.tags)

        return any(t.name == name for t in self.tags)

    def patch(
        self,
        *,
        dependency_config: DependencyConfig | None = None,
        lifespan: Lifespan | None = None,
        tags: Iterable[Tag] | None = None,
    ) -> None:
        if self.was_used:
            raise RuntimeError(f"Registration {self.id} cannot be patched after it has been used")

        if dependency_config is not None:
            merged_dependency_config: DependencyConfig = {
                name: dependency.settings for name, dependency in self.dependencies.items()
            }
            for name, settings in dependency_config.items():
                if settings is RemoveDependencySetting:
                    merged_dependency_config.pop(name, None)
                else:
                    merged_dependency_config[name] = settings

            self.dependencies = _set_up_dependencies(
                self.implementation,
                dependency_config_to_subdependencies(merged_dependency_config),
            )

        if lifespan is not None:
            self.lifespan = lifespan

        if tags is not None:
            merged_tags = {tag.name: tag for tag in self.tags}
            for tag in tags:
                merged_tags[tag.name] = tag
            self.tags = tuple(merged_tags.values())

    @property
    def generic_mapping(self):
        if not self._generic_mapping:
            self._generic_mapping = GenericTypeMap(self.service_type)

        return self._generic_mapping

    def _try_find_cached_node(self, context: _ResolvingContext, parent_node: DependencyNode):
        cached_node = context.get_cached(self.id)
        if cached_node is not None:
            parent_node.add_child(cached_node)
            return True, cached_node.instance
        return False, None

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

    @contextmanager
    def _propagate_resolve_error(self):
        try:
            yield
        except CannotResolveError as e:
            e.append_registration(self)
            raise e

    def _build_uncached(self, context: _ResolvingContext, parent_node: DependencyNode):
        new_instance_node = self._create_new_dependency_node(parent_node)

        for pre_configuration in context.find_pre_configurations_that_apply(self):
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

    async def _build_uncached_async(self, context: _ResolvingContext, parent_node: DependencyNode):
        new_instance_node = self._create_new_dependency_node(parent_node)

        for pre_configuration in context.find_pre_configurations_that_apply(self):
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

    def build(self, context: _ResolvingContext, parent_node: DependencyNode):
        with self._propagate_resolve_error():
            context.assert_registration_allowed(self)
            is_cached, cached_instance = self._try_find_cached_node(context, parent_node)
            if is_cached:
                return cached_instance

            future, is_builder = context.begin_shared_build(self)
            if future is not None and not is_builder:
                outcome = future.result()
                if outcome.error is not None:
                    raise outcome.error
                is_cached, cached_instance = self._try_find_cached_node(context, parent_node)
                if not is_cached:
                    raise RuntimeError(f"Shared dependency {self.id} completed without a cached instance")
                return cached_instance

            try:
                with context.enter_registration(self):
                    built_instance = self._build_uncached(context, parent_node)
            except BaseException as error:
                context.finish_shared_build(self, future, error)
                raise

            context.finish_shared_build(self, future)
            return built_instance

    async def build_async(self, context: _ResolvingContext, parent_node: DependencyNode):
        with self._propagate_resolve_error():
            context.assert_registration_allowed(self)
            is_cached, cached_instance = self._try_find_cached_node(context, parent_node)
            if is_cached:
                return cached_instance

            future, is_builder = context.begin_shared_build(self)
            if future is not None and not is_builder:
                outcome = await asyncio.shield(asyncio.wrap_future(future))
                if outcome.error is not None:
                    raise outcome.error
                is_cached, cached_instance = self._try_find_cached_node(context, parent_node)
                if not is_cached:
                    raise RuntimeError(f"Shared dependency {self.id} completed without a cached instance")
                return cached_instance

            try:
                with context.enter_registration(self):
                    built_instance = await self._build_uncached_async(context, parent_node)
            except BaseException as error:
                context.finish_shared_build(self, future, error)
                raise

            context.finish_shared_build(self, future)
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
    ) -> str:
        registration = _Registration(
            activator_class=FactoryActivator,
            service_type=service_type,
            implementation=implementation,
            lifespan=lifespan,
            name=name,
            sub_dependencies=dependency_config_to_subdependencies(dependency_config),
            parent_node_filter=parent_node_filter,
            tags=tags,
        )

        self._registrations[service_type].appendleft(registration)
        self._registrations[implementation].appendleft(registration)
        return registration.id

    def register_concrete(
        self,
        *,
        service_type: type[TService],
        lifespan: Lifespan,
        name: str | None,
        dependency_config: DependencyConfig,
        tags: Iterable[Tag] | None,
        parent_node_filter: NodeFilter,
    ) -> str:
        registration = _Registration(
            activator_class=FactoryActivator,
            service_type=service_type,
            implementation=service_type,
            lifespan=lifespan,
            name=name,
            sub_dependencies=dependency_config_to_subdependencies(dependency_config),
            parent_node_filter=parent_node_filter,
            tags=tags,
        )

        self._registrations[service_type].appendleft(registration)
        return registration.id

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
        is_root_owned_instance: bool,
    ) -> str:
        instance_lifespan = lifespan if lifespan == Lifespan.singleton else Lifespan.scoped

        registration = _Registration(
            activator_class=FactoryActivator,
            service_type=service_type,
            implementation=constant(instance),
            lifespan=instance_lifespan,
            name=name,
            sub_dependencies=dependency_config_to_subdependencies(dependency_config),
            parent_node_filter=parent_node_filter,
            tags=tags,
            is_instance=True,
            is_root_owned_instance=is_root_owned_instance,
        )
        self._registrations[service_type].appendleft(registration)
        return registration.id

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
    ) -> str:
        registration = _Registration(
            activator_class=self._get_activator_class(factory),
            service_type=service_type,
            implementation=factory,
            lifespan=lifespan,
            name=name,
            sub_dependencies=dependency_config_to_subdependencies(dependency_config),
            parent_node_filter=parent_node_filter,
            tags=tags,
        )

        self._registrations[service_type].appendleft(registration)

        return registration.id

    def patch_registration(
        self,
        service_type: type,
        registration_id: str,
        *,
        dependency_config: DependencyConfig | None = None,
        lifespan: Lifespan | None = None,
        tags: Iterable[Tag] | None = None,
    ) -> None:
        registration = next(
            (
                registration
                for registration in self._registrations.get(service_type, ())
                if registration.service_type == service_type and registration.id == registration_id
            ),
            None,
        )
        if registration is None:
            raise KeyError(f"No registration found for {service_type} with ID {registration_id}")

        registration.patch(
            dependency_config=dependency_config,
            lifespan=lifespan,
            tags=tags,
        )

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
            sub_dependencies=dependency_config_to_subdependencies(dependency_config),
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
            sub_dependencies=dependency_config_to_subdependencies(dependency_config),
            continue_on_failure=continue_on_failure,
        )

        service_types = service_type if isinstance(service_type, Iterable) else (service_type,)

        for st in service_types:
            self._pre_configurations[st].appendleft(pre_configuration)  # ty:ignore[invalid-argument-type]

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
        self._registration_stack: contextvars.ContextVar[tuple[_Registration, ...]] = contextvars.ContextVar(
            f"clean_ioc_registration_stack_{id(self)}",
            default=(),
        )

    def assert_registration_allowed(self, registration: _Registration) -> None:
        stack = self._registration_stack.get()
        if registration in stack:
            cycle_start = stack.index(registration)
            raise CircularDependencyError((*stack[cycle_start:], registration))

        singleton = next((item for item in stack if item.lifespan == Lifespan.singleton), None)
        is_safe_root_instance = registration.is_instance and registration.is_root_owned_instance
        if singleton is not None and registration.lifespan == Lifespan.scoped and not is_safe_root_instance:
            raise CaptiveDependencyError(singleton, registration, (*stack, registration))

    @contextmanager
    def enter_registration(self, registration: _Registration):
        stack = self._registration_stack.get()
        token = self._registration_stack.set((*stack, registration))
        try:
            yield
        finally:
            self._registration_stack.reset(token)

    def begin_shared_build(
        self, registration: _Registration
    ) -> tuple[concurrent.futures.Future[_BuildOutcome] | None, bool]:
        if registration.lifespan not in (Lifespan.scoped, Lifespan.singleton):
            return None, True
        return self.scope.get_build_coordinator(registration.lifespan).begin(registration.id)

    def finish_shared_build(
        self,
        registration: _Registration,
        future: concurrent.futures.Future[_BuildOutcome] | None,
        error: BaseException | None = None,
    ) -> None:
        if future is None:
            return
        self.scope.get_build_coordinator(registration.lifespan).finish(registration.id, future, error)

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
    ) -> TService:
        """
        Resolve and return an instance for ``service_type``.

        Args:
            service_type:
                The target type to resolve.
            filter:
                Registration filter used when multiple registrations exist for
                ``service_type``.

        Returns:
            The resolved service instance.

        Raises:
            CannotResolveError:
                If no matching registration can be found for the service or a
                nested dependency.

        Examples:
            Resolve a concrete service:

            ```python
            service = resolver.resolve(UserService)
            ```

            Resolve a named registration:

            ```python
            from clean_ioc._legacy_registration_filters import with_name

            gateway = resolver.resolve(PaymentGateway, filter=with_name("stripe"))
            ```
        """
        ...

    async def resolve_async(
        self,
        service_type: type[TService],
        filter: RegistrationFilter = default_registration_filter,
    ) -> TService:
        """
        Resolve and return an instance for ``service_type`` asynchronously.

        This is the async counterpart to ``resolve(...)`` and should be used
        when dependency creation includes async factories or async generators.

        Args:
            service_type:
                The target type to resolve.
            filter:
                Registration filter used when multiple registrations exist for
                ``service_type``.

        Returns:
            The resolved service instance.

        Raises:
            CannotResolveError:
                If no matching registration can be found for the service or a
                nested dependency.

        Examples:
            Resolve asynchronously:

            ```python
            handler = await resolver.resolve_async(MessageHandler)
            ```
        """
        ...


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
    ) -> str:
        """
        Register a dependency for a service type and return its registration ID.

        The registration target can be provided in four different ways:

        1. ``implementation_type``:
           Maps ``service_type`` to a concrete implementation class.
        2. ``factory``:
           Uses a callable to build the instance. Factory parameters are injected
           using normal dependency resolution and type hints.
        3. ``instance``:
           Uses a pre-built object instance.
        4. no target supplied:
           Treats ``service_type`` as its own concrete implementation.

        Args:
            service_type:
                The abstraction/type used during resolution.
            implementation_type:
                Concrete class to instantiate for ``service_type``.
            factory:
                Callable used to create instances. Can be sync/async and supports
                generator/contextmanager patterns handled by activators.
            instance:
                Pre-constructed object to return for this registration.
            lifespan:
                Controls reuse semantics (``transient``, ``once_per_graph``,
                ``scoped``, ``singleton``).
            name:
                Optional name used by registration filters to disambiguate
                multiple registrations of the same service.
            dependency_config:
                Per-parameter overrides for dependency resolution and value
                injection.
            tags:
                Optional metadata used by registration filters.
            parent_node_filter:
                Predicate that must match the current parent dependency node for
                this registration to be considered during resolution.

        Returns:
            A unique registration ID string.

        Examples:
            Register implementation mapping:

            ```python
            container.register(IService, ServiceImpl)
            ```

            Register concrete type:

            ```python
            container.register(ServiceImpl)
            ```

            Register factory (sync or async callable):

            ```python
            def build_service(repo: Repo) -> ServiceImpl:
                return ServiceImpl(repo)

            container.register(IService, factory=build_service)
            ```

            Register pre-built instance:

            ```python
            config = AppConfig(env="prod")
            container.register(AppConfig, instance=config)
            ```
        """
        ...

    def patch_registration(
        self,
        service_type: type,
        registration_id: str,
        *,
        dependency_config: DependencyConfig | None = None,
        lifespan: Lifespan | None = None,
        tags: Iterable[Tag] | None = None,
    ) -> None:
        """Patch an unused registration identified by service type and registration ID.

        Dependency settings are shallow-merged by parameter name. Tags are merged by
        tag name, and a supplied lifespan replaces the existing lifespan. Use
        ``RemoveDependencySetting`` as a dependency-config value to remove an override.

        Raises:
            KeyError:
                If this registrator does not own the requested registration.
            RuntimeError:
                If the registration has already created an instance.
        """
        ...


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
        self._build_coordinator = _SharedBuildCoordinator()
        self._scoped_instances: dict[str, DependencyNode] = {}
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
        """
        Resolve and return an instance for ``service_type``.

        This creates a new dependency graph for the call, resolves the graph
        root using the selected registration, and returns the built instance.

        Args:
            service_type:
                The target type to resolve.
            filter:
                Optional registration filter used to choose a registration when
                multiple registrations are available.

        Returns:
            The resolved instance of ``service_type``.

        Raises:
            CannotResolveError:
                If no registration matches ``service_type`` and ``filter``, or
                if any nested dependency cannot be resolved.

        Examples:
            Basic resolution:

            ```python
            service = container.resolve(UserService)
            ```

            Resolve a named registration:

            ```python
            from clean_ioc._legacy_registration_filters import with_name

            gateway = container.resolve(PaymentGateway, filter=with_name("stripe"))
            ```
        """
        graph = self.resolve_dependency_graph(service_type, filter)
        return graph.instance

    async def resolve_async(
        self,
        service_type: type[TService],
        filter: RegistrationFilter = default_registration_filter,
    ) -> TService:
        """
        Resolve and return an instance for ``service_type`` asynchronously.

        This behaves like ``resolve(...)`` but executes the async resolution
        path, allowing async factories and async generator-based dependencies to
        be activated correctly.

        Args:
            service_type:
                The target type to resolve.
            filter:
                Optional registration filter used to choose a registration when
                multiple registrations are available.

        Returns:
            The resolved instance of ``service_type``.

        Raises:
            CannotResolveError:
                If no registration matches ``service_type`` and ``filter``, or
                if any nested dependency cannot be resolved.

        Examples:
            Async resolution:

            ```python
            service = await container.resolve_async(UserService)
            ```
        """
        graph = await self.resolve_dependency_graph_async(service_type, filter)
        return graph.instance

    def call(self, fn: Callable[..., TReturn]) -> TReturn:
        name: str = str(uuid4())
        with self.new_scope() as scope:
            scope.register(Callable, fn, name=name)
            return scope.resolve(Callable, filter=lambda r: r.name == name)

    async def call_async(self, fn: Callable[..., TReturn]) -> TReturn:
        name: str = str(uuid4())
        with self.new_scope() as scope:
            scope.register(Callable, fn, name=name)

            return await scope.resolve_async(
                Callable,
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

    def explain(
        self,
        service_type: type,
        filter: RegistrationFilter = default_registration_filter,
        *,
        allow_async: bool = True,
    ) -> DependencyPlan:
        """Describe how a service would be assembled without creating instances.

        The returned plan includes registrations, lifespans, supplied values,
        collections, decorators, pre-configurations, and any validation issues.
        Use ``plan.to_text()`` for terminal output or ``plan.to_mermaid()`` for
        documentation and pull requests.
        """

        from ._legacy_diagnostics import explain

        return explain(self, service_type, filter, allow_async=allow_async)

    def validate(self, *service_types: type, allow_async: bool = True) -> ValidationReport:
        """Fail fast when registrations contain invalid dependency graphs.

        When no service types are supplied, every registration visible to this
        scope is checked. The analysis is static and does not call user code.
        Set ``allow_async=False`` to flag graphs that require async resolution.
        """

        from ._legacy_diagnostics import validate

        return validate(self, *service_types, allow_async=allow_async)

    def resolve_from_registration_id(self, service_type: type[TService], registration_id: str):
        """
        Resolve a service from a registration ID.
        This is useful for advanced use cases where you need to resolve a specific registration

        .. deprecated:: 1.23.0
            Use ``resolve(service_type, filter=with_id(registration_id))`` instead.
        """
        send_deprecation_warning(
            "resolve_from_registration_id() is deprecated; "
            "use resolve(service_type, filter=with_id(registration_id)) instead."
        )
        return self.resolve(
            service_type,
            filter=lambda r: r.id == registration_id,
        )

    async def resolve_from_registration_id_async(self, service_type: type[TService], registration_id: str):
        """
        Resolve a service from a registration ID.
        This is useful for advanced use cases where you need to resolve a specific registration

        .. deprecated:: 1.23.0
            Use ``resolve_async(service_type, filter=with_id(registration_id))`` instead.
        """
        send_deprecation_warning(
            "resolve_from_registration_id_async() is deprecated; "
            "use resolve_async(service_type, filter=with_id(registration_id)) instead."
        )
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
    ) -> str:
        """
        Register a dependency for ``service_type`` and return the registration ID.

        Resolution behavior is determined by which target argument is provided:

        - ``instance``: register a pre-built object.
        - ``factory``: register a callable that creates the object.
        - ``implementation_type``: map service type to a concrete implementation.
        - none of the above: register ``service_type`` as its own implementation.

        Precedence is ``instance`` > ``factory`` > ``implementation_type`` >
        concrete ``service_type``.

        Args:
            service_type:
                The type requested during ``resolve(...)``.
            implementation_type:
                Optional concrete class to instantiate for ``service_type``.
            factory:
                Optional creation callable. Parameters are dependency-injected.
                Async factories and generator/contextmanager patterns are
                supported by the internal activator system.
            instance:
                Optional already-created object.
            lifespan:
                Instance reuse policy.
            name:
                Optional registration name for filter-based selection.
            dependency_config:
                Argument-level overrides for dependency resolution/value
                factories.
            tags:
                Optional metadata attached to the registration.
            parent_node_filter:
                Restricts when this registration is eligible based on the
                current parent node in the dependency graph.

        Returns:
            The registration ID that can later be used for diagnostics or
            filter-based resolution.

        Examples:
            Register implementation mapping:

            ```python
            container.register(IService, ServiceImpl)
            ```

            Register concrete type:

            ```python
            container.register(ServiceImpl)
            ```

            Register factory:

            ```python
            def build_service(repo: Repo) -> ServiceImpl:
                return ServiceImpl(repo)

            container.register(IService, factory=build_service)
            ```

            Register pre-built instance:

            ```python
            config = AppConfig(env="prod")
            container.register(AppConfig, instance=config)
            ```
        """
        if instance is not None:
            return self._registry.register_instance(
                service_type=service_type,
                instance=instance,
                lifespan=lifespan,
                name=name,
                tags=tags,
                dependency_config=dependency_config,
                parent_node_filter=parent_node_filter,
                is_root_owned_instance=isinstance(self, Container),
            )
        if factory is not None:
            return self._registry.register_factory(
                service_type=service_type,
                factory=factory,
                lifespan=lifespan,
                name=name,
                tags=tags,
                dependency_config=dependency_config,
                parent_node_filter=parent_node_filter,
            )
        if implementation_type is not None:
            return self._registry.register_implementation(
                service_type=service_type,
                implementation=implementation_type,
                lifespan=lifespan,
                name=name,
                tags=tags,
                dependency_config=dependency_config,
                parent_node_filter=parent_node_filter,
            )

        return self._registry.register_concrete(
            service_type=service_type,
            lifespan=lifespan,
            name=name,
            tags=tags,
            dependency_config=dependency_config,
            parent_node_filter=parent_node_filter,
        )

    def patch_registration(
        self,
        service_type: type,
        registration_id: str,
        *,
        dependency_config: DependencyConfig | None = None,
        lifespan: Lifespan | None = None,
        tags: Iterable[Tag] | None = None,
    ) -> None:
        """Patch an unused registration owned by this scope.

        ``dependency_config`` is shallow-merged by parameter name. Set a value to
        ``RemoveDependencySetting`` to remove an existing override. ``tags`` are
        merged by tag name, with later values replacing earlier values.

        Args:
            service_type:
                The original service type used to register the dependency.
            registration_id:
                The ID returned by ``register(...)``.
            dependency_config:
                Dependency-setting additions, replacements, or removals.
            lifespan:
                Replacement lifespan for future resolution.
            tags:
                Tags to add or replace by name.

        Raises:
            KeyError:
                If this scope does not own the requested type/ID pair.
            RuntimeError:
                If the registration has already created an instance.
        """
        self._registry.patch_registration(
            service_type,
            registration_id,
            dependency_config=dependency_config,
            lifespan=lifespan,
            tags=tags,
        )

    def pre_configure(
        self,
        service_type: type | Iterable[type],
        configuration_function: Callable,
        *,
        registration_filter: RegistrationFilter = default_registration_filter,
        dependency_config: DependencyConfig = {},
        continue_on_failure: bool = False,
    ) -> None:
        self._registry.register_pre_configuration(
            service_type=service_type,
            configuration_function=configuration_function,
            registration_filter=registration_filter,
            dependency_config=dependency_config,
            continue_on_failure=continue_on_failure,
        )

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
    ) -> None:
        """
        Register a decorator for a service type.

        Decorators are applied during resolution after the base registration is
        created. Multiple decorators form a chain, where each decorator receives
        the previously built instance.

        Args:
            service_type:
                The service type whose registrations can be decorated.
            decorator_type:
                Decorator class or callable used to wrap the resolved service.
                Non-decorated parameters are dependency-injected.
            registration_filter:
                Predicate used to decide whether the decorator applies to a
                specific registration.
            decorator_node_filter:
                Predicate used to decide whether the decorator applies for the
                current decorated node in the dependency graph.
            decorated_arg:
                Name of the decorator argument that should receive the wrapped
                instance. If omitted, it is auto-detected by matching
                ``service_type`` in the decorator signature annotations.
            dependency_config:
                Optional dependency overrides for decorator parameters.
            position:
                Ordering value for decorator application. Lower values are
                applied first; ties are resolved by registration insertion order.

        Examples:
            Register a class decorator:

            ```python
            container.register(Service, ServiceImpl)
            container.register_decorator(Service, LoggingDecorator)
            ```

            Register a decorator with explicit wrapped-arg name:

            ```python
            container.register_decorator(
                Service,
                LoggingDecorator,
                decorated_arg="child",
                position=10,
            )
            ```

            Register with filters:

            ```python
            from clean_ioc._legacy_registration_filters import has_tag

            container.register_decorator(
                Service,
                LoggingDecorator,
                registration_filter=has_tag("channel", "api"),
            )
            ```
        """
        self._registry.register_decorator(
            service_type=service_type,
            decorator_type=decorator_type,
            registration_filter=registration_filter,
            decorator_node_filter=decorator_node_filter,
            decorated_arg=decorated_arg,
            dependency_config=dependency_config,
            position=position,
        )

    def add_singleton_node(
        self, registration: _Registration, node: DependencyNode
    ) -> Scope: ...  # ty:ignore[empty-body]

    def find_singleton_node(self, registration_id: str) -> DependencyNode | None: ...

    def find_scoped_node(self, registration_id: str) -> DependencyNode | None:
        return self._scoped_instances.get(registration_id)

    def get_build_coordinator(self, lifespan: Lifespan) -> _SharedBuildCoordinator:
        return self._build_coordinator

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
        registrations = list_modifier(registrations)
        return [r.id for r in registrations]

    def get_registration_id(
        self,
        service_type,
        *,
        filter: RegistrationFilter = default_registration_filter,
    ) -> str | None:
        """Return the first matching registration ID, or ``None`` when no registration matches.

        Registrations use the same most-recently-registered-first order as
        normal resolution.
        """
        registration_ids = self.get_registration_ids(service_type, filter=filter)
        return registration_ids[0] if registration_ids else None

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
        return list_modifier(registrations)

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
        await self._async_close_finalizers()

    def __enter__(self):
        return self

    def __exit__(self, *args, **kwargs):
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

    def add_scoped_node(self, registration: _Registration, node: DependencyNode) -> Scope:
        self._scoped_instances[registration.id] = node
        return self

    @property
    def scoped_instances(self) -> dict[str, DependencyNode]:
        return self._scoped_instances

    @property
    def singleton_instances(self) -> dict[str, DependencyNode]: ...  # ty:ignore[empty-body]

    def new_scope(self) -> Scope: ...  # ty:ignore[empty-body]


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

    def get_build_coordinator(self, lifespan: Lifespan) -> _SharedBuildCoordinator:
        if lifespan == Lifespan.singleton:
            return self._parent_scope.get_build_coordinator(lifespan)
        return super().get_build_coordinator(lifespan)

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
        return list_modifier(registrations + from_parent)

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
    ) -> list[str]:
        ids: list[str] = []

        full_type_filter = ~(is_abstract) & subclass_type_filter
        subclasses = get_subclasses(base_type, filter=full_type_filter)
        for sc in subclasses:
            reg_id = self.register(
                base_type,
                sc,
                lifespan=lifespan,
                name=name,
                tags=tags,
                parent_node_filter=parent_node_filter,
            )
            ids.append(reg_id)

        return ids

    @staticmethod
    def _get_target_generic_base(generic_service_type: type, subclass: type):
        return next(
            (
                try_to_map_generic_args_to_specialization(b, subclass)
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
    ) -> list[str]:
        ids: list[str] = []

        # Exclude generated decorator template classes (same exclusion as
        # register_generic_decorator): without it, a process that builds more
        # than one container rediscovers an earlier build's
        # __DecoratedGeneric__* classes as implementations and ends up
        # decorating the decorator, recursing at resolve time.
        full_type_filter = ~is_abstract & ~name_starts_with("__DecoratedGeneric__") & subclass_type_filter
        subclasses = get_subclasses(generic_service_type, filter=full_type_filter)
        for subclass in subclasses:
            target_generic_base = self._get_target_generic_base(generic_service_type, subclass)
            if target_generic_base:
                reg_id = self.register(
                    target_generic_base,
                    subclass,
                    lifespan=lifespan,
                    name=name,
                    tags=tags,
                    parent_node_filter=parent_node_filter,
                )

                ids.append(reg_id)

        if fallback_type:
            self.register(
                generic_service_type,
                fallback_type,
                lifespan=lifespan,
                name=name,
                tags=tags,
                parent_node_filter=parent_node_filter,
            )

        return ids

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
    ) -> None:
        """
        Register decorators across all discovered subclasses of an open generic service.

        For each discovered subclass of ``generic_service_type``, Clean IoC maps
        that subclass to its concrete closed generic base and registers a
        decorator for that concrete service type.

        If ``generic_decorator_type`` is open generic, it is concretized per
        subclass mapping before registration.

        Args:
            generic_service_type:
                Open generic service base (for example ``Handler`` when
                resolving ``Handler[UserCreated]``).
            generic_decorator_type:
                Decorator type to apply. Can be open generic or concrete.
            subclass_type_filter:
                Predicate to limit which discovered subclasses are included.
            decorated_arg:
                Name of the decorator argument that receives the wrapped service
                instance. If omitted, auto-detection is used.
            dependency_config:
                Optional dependency overrides for decorator parameters.
            registration_filter:
                Predicate used to select which matching registrations should be
                decorated.
            decorated_node_filter:
                Predicate used to select where in dependency graphs the decorator
                should be applied.
            position:
                Ordering value for decorator application.

        Examples:
            Register an open-generic decorator for all mapped handlers:

            ```python
            container.register_generic_subclasses(Handler)
            container.register_generic_decorator(Handler, LoggingHandlerDecorator)
            ```

            Register with explicit wrapped arg and ordering:

            ```python
            container.register_generic_decorator(
                Handler,
                LoggingHandlerDecorator,
                decorated_arg="child",
                position=5,
            )
            ```
        """
        full_type_filter = ~is_abstract & ~name_starts_with("__DecoratedGeneric__") & subclass_type_filter
        subclasses = get_subclasses(generic_service_type, filter=full_type_filter)
        decorator_generic_map = GenericTypeMap(generic_decorator_type)
        decorator_is_open_generic = decorator_generic_map.is_mapping_generic()
        processed_target_generic_bases = set()

        for subclass in subclasses:
            target_generic_base = self._get_target_generic_base(generic_service_type, subclass)
            if target_generic_base:
                if target_generic_base in processed_target_generic_bases:
                    continue
                processed_target_generic_bases.add(target_generic_base)

                if decorator_is_open_generic:
                    concrete_decorator = try_to_map_generic_args_to_specialization(generic_decorator_type, subclass)
                    DecoratedType = create_generic_decorator_type(  # noqa: N806
                        concrete_decorator
                    )

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
    ) -> None:
        bundle_fn(self)

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
