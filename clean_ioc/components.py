"""The immutable, build-time component model used by Clean IoC 2."""

from __future__ import annotations

import inspect
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, Iterable, Iterator, Literal, Protocol, TypeAlias

from typetoolbox.generics import GenericTypeMap

from .configuration import Tag

Lifespan: TypeAlias = Literal["transient", "once_per_graph", "scoped", "singleton"]


class ComponentKind(str, Enum):
    """The role an occurrence has in a compiled component plan."""

    registration = "registration"
    decorator = "decorator"
    pre_configuration = "pre_configuration"
    collection = "collection"
    scope_slot = "scope_slot"
    value = "value"
    value_provider = "value_provider"
    runtime_context = "runtime_context"


class ComponentActivation(str, Enum):
    """How a compiled occurrence obtains its runtime value."""

    constructor = "constructor"
    factory = "factory"
    instance = "instance"
    supplied = "supplied"
    collection = "collection"
    context = "context"


@dataclass(frozen=True, slots=True)
class _ComponentRecord:
    id: str
    occurrence_id: int
    service_type: Any
    implementation: Any
    implementation_type: type
    lifespan: Lifespan
    name: str | None
    tags: tuple[Tag, ...]
    kind: ComponentKind
    activation: ComponentActivation
    requires_async: bool
    manages_cleanup: bool
    position: int | None
    argument: str | None
    generic_mapping: GenericTypeMap
    parent_id: int | None
    dependency_ids: tuple[int, ...]
    decorator_ids: tuple[int, ...]
    decorated_id: int | None
    pre_configuration_ids: tuple[int, ...]


@dataclass(slots=True)
class _ComponentDraft:
    id: str
    occurrence_id: int
    service_type: Any
    implementation: Any
    implementation_type: type
    lifespan: Lifespan
    name: str | None
    tags: tuple[Tag, ...]
    kind: ComponentKind
    activation: ComponentActivation
    requires_async: bool = False
    manages_cleanup: bool = False
    position: int | None = None
    argument: str | None = None
    parent_id: int | None = None
    dependency_ids: tuple[int, ...] = ()
    decorator_ids: tuple[int, ...] = ()
    decorated_id: int | None = None
    pre_configuration_ids: tuple[int, ...] = ()

    def freeze(self) -> _ComponentRecord:
        return _ComponentRecord(
            id=self.id,
            occurrence_id=self.occurrence_id,
            service_type=self.service_type,
            implementation=self.implementation,
            implementation_type=self.implementation_type,
            lifespan=self.lifespan,
            name=self.name,
            tags=self.tags,
            kind=self.kind,
            activation=self.activation,
            requires_async=self.requires_async,
            manages_cleanup=self.manages_cleanup,
            position=self.position,
            argument=self.argument,
            generic_mapping=GenericTypeMap(self.service_type),
            parent_id=self.parent_id,
            dependency_ids=self.dependency_ids,
            decorator_ids=self.decorator_ids,
            decorated_id=self.decorated_id,
            pre_configuration_ids=self.pre_configuration_ids,
        )


def normalize_implementation_type(implementation: Any, service_type: Any) -> type:
    """Return a stable type for classes, instances, and factory callables."""

    if isinstance(implementation, type):
        return implementation
    try:
        annotation = inspect.signature(implementation).return_annotation
    except (TypeError, ValueError):
        annotation = inspect.Signature.empty
    if isinstance(annotation, type):
        return annotation
    origin = getattr(service_type, "__origin__", None)
    if isinstance(origin, type):
        return origin
    return service_type if isinstance(service_type, type) else type(implementation)


class _ComponentGraph:
    __slots__ = ("_drafts", "_records")

    def __init__(self) -> None:
        self._drafts: dict[int, _ComponentDraft] = {}
        self._records: dict[int, _ComponentRecord] | None = None

    def add(self, draft: _ComponentDraft) -> Component:
        self._drafts[draft.occurrence_id] = draft
        return Component(self, draft.occurrence_id)

    def record(self, occurrence_id: int) -> _ComponentDraft | _ComponentRecord:
        if self._records is not None:
            return self._records[occurrence_id]
        return self._drafts[occurrence_id]

    def freeze(self) -> None:
        self._records = {key: value.freeze() for key, value in self._drafts.items()}
        self._drafts.clear()


class Component:
    """A read-only occurrence in a compiled dependency plan.

    A component ID identifies the registration. ``occurrence_id`` identifies a
    particular use of that registration, including its static parent and
    dependency subtree.
    """

    __slots__ = ("_graph", "_occurrence_id")

    def __init__(self, graph: _ComponentGraph, occurrence_id: int) -> None:
        self._graph = graph
        self._occurrence_id = occurrence_id

    @property
    def _record(self) -> _ComponentDraft | _ComponentRecord:
        return self._graph.record(self._occurrence_id)

    @property
    def id(self) -> str:
        return self._record.id

    @property
    def occurrence_id(self) -> int:
        return self._occurrence_id

    @property
    def service_type(self) -> Any:
        return self._record.service_type

    @property
    def implementation(self) -> Any:
        return self._record.implementation

    @property
    def implementation_type(self) -> type:
        return self._record.implementation_type

    @property
    def lifespan(self) -> Lifespan:
        return self._record.lifespan

    @property
    def name(self) -> str | None:
        return self._record.name

    @property
    def registration_name(self) -> str | None:
        """Compatibility alias for pre-2.0 node filters."""

        return self.name

    @property
    def tags(self) -> tuple[Tag, ...]:
        return self._record.tags

    @property
    def registration_tags(self) -> tuple[Tag, ...]:
        """Compatibility alias for pre-2.0 node filters."""

        return self.tags

    @property
    def kind(self) -> ComponentKind:
        return self._record.kind

    @property
    def activation(self) -> ComponentActivation:
        return self._record.activation

    @property
    def activation_kind(self) -> ComponentActivation:
        """Descriptive alias used by diagnostics and graph exporters."""

        return self.activation

    @property
    def requires_async(self) -> bool:
        return self._record.requires_async

    @property
    def manages_cleanup(self) -> bool:
        return self._record.manages_cleanup

    @property
    def position(self) -> int | None:
        """Decorator z-index; ``None`` for non-decorator components."""

        return self._record.position

    @property
    def argument(self) -> str | None:
        return self._record.argument

    @property
    def generic_mapping(self) -> GenericTypeMap:
        record = self._record
        if isinstance(record, _ComponentRecord):
            return record.generic_mapping
        return GenericTypeMap(record.service_type)

    @property
    def parent(self) -> Component | None:
        value = self._record.parent_id
        return None if value is None else Component(self._graph, value)

    @property
    def dependencies(self) -> tuple[Component, ...]:
        return tuple(Component(self._graph, value) for value in self._record.dependency_ids)

    @property
    def children(self) -> list[Component]:
        """Compatibility view of dependencies as a list."""

        return list(self.dependencies)

    @property
    def decorators(self) -> tuple[Component, ...]:
        return tuple(Component(self._graph, value) for value in self._record.decorator_ids)

    @property
    def decorator(self) -> Component | None:
        return self.decorators[0] if self.decorators else None

    @property
    def decorated(self) -> Component | None:
        value = self._record.decorated_id
        return None if value is None else Component(self._graph, value)

    @property
    def pre_configurations(self) -> tuple[Component, ...]:
        return tuple(Component(self._graph, value) for value in self._record.pre_configuration_ids)

    def has_tag(self, name: str, value: str | None = None) -> bool:
        return any(tag.name == name and (value is None or tag.value == value) for tag in self.tags)

    def has_registration_tag(self, name: str, value: str | None = None) -> bool:
        return self.has_tag(name, value)

    def descendants(self) -> Iterator[Component]:
        for child in self.dependencies:
            yield child
            yield from child.descendants()
        for configuration in self.pre_configurations:
            yield configuration
            yield from configuration.descendants()
        for decorator in self.decorators:
            yield decorator
            yield from decorator.descendants()

    def has_descendant(self, filter: ComponentFilter) -> bool:
        return any(filter(component) for component in self.descendants())

    def has_dependant_service_type(self, service_type: type) -> bool:
        return self.has_descendant(lambda component: component.service_type == service_type)

    def has_dependant_implementation_type(self, implementation_type: type) -> bool:
        return self.has_descendant(lambda component: component.implementation_type == implementation_type)

    def __repr__(self) -> str:
        return f"Component({self.service_type!r} -> {self.implementation!r}, occurrence={self.occurrence_id})"


ComponentFilter: TypeAlias = Callable[[Component], bool]
ComponentListModifier: TypeAlias = Callable[[list[Component]], list[Component]]


def all_components(_: Component) -> bool:
    return True


def default_component_filter(component: Component) -> bool:
    return component.name is None


def default_component_list_modifier(components: list[Component]) -> list[Component]:
    return components


class ComponentBuilder(Protocol):
    """Structural protocol documented for bundle authors.

    The concrete builders intentionally use duck typing so third-party bundle
    packages do not need to inherit from a Clean IoC base class.
    """

    id: str

    def register(
        self,
        service_type: type,
        implementation_type: type | None = None,
        *,
        factory: Callable[..., Any] | None = None,
        factory_specialization: object | None = None,
        instance: Any | None = None,
        lifespan: Lifespan = "once_per_graph",
        name: str | None = None,
        dependency_config: dict[str, Any] = {},
        tags: Iterable[Tag] | None = None,
        when: ComponentFilter = all_components,
    ) -> str: ...

    def register_decorator(
        self,
        service_type: type,
        decorator_type: type | Callable,
        *,
        when: ComponentFilter = all_components,
        decorated_arg: str | None = None,
        dependency_config: dict[str, Any] = {},
        position: int = 0,
        name: str | None = None,
        tags: Iterable[Tag] | None = None,
    ) -> str: ...

    def patch_decorator(
        self,
        service_type: Any,
        decorator_id: str,
        *,
        decorated_arg: str | None | object = ...,
        dependency_config: dict[str, Any] | None = None,
        position: int | object = ...,
        when: ComponentFilter | None = None,
        name: str | None | object = ...,
        tags: Iterable[Tag] | None = None,
    ) -> None: ...

    def remove_decorator(self, service_type: Any, decorator_id: str) -> None: ...

    def pre_configure(
        self,
        service_type: type | Iterable[type],
        configuration_function: Callable,
        *,
        when: ComponentFilter = all_components,
        dependency_config: dict[str, Any] = {},
        continue_on_failure: bool = False,
    ) -> str: ...

    def declare_scope_slot(self, service_type: type, name: str | None = None) -> Any: ...

    def mark_entrypoint(
        self,
        service_type: Any,
        *,
        filter: ComponentFilter = default_component_filter,
    ) -> Any: ...
