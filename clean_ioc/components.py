"""The immutable, build-time component model used by Clean IoC 2."""

from __future__ import annotations

import inspect
from collections.abc import Hashable
from dataclasses import dataclass, field, replace
from enum import Enum
from types import UnionType
from typing import (
    TYPE_CHECKING,
    Any,
    Callable,
    Iterable,
    Iterator,
    Literal,
    Mapping,
    Protocol,
    TypeAlias,
    TypeVar,
    Union,
    overload,
)

from typetoolbox.generics import GenericTypeMap
from typing_extensions import TypeForm

from .generic_utils import constructor_type
from .metadata import Tag
from .provider_maps import ProviderMapGroup
from .sentinels import Undefined, _Undefined
from .service_groups import ServiceGroup
from .type_aliases import normalize_type_alias

if TYPE_CHECKING:
    from ._decorator_templates import DecoratorTemplate, RegistrationInfo
    from ._registration_templates import RegistrationTemplate
    from .boundaries import Expose, Use
    from .container import BoundaryBuilder
    from .preferences import ComponentPreference
    from .tooling import ValidationRule

Lifespan: TypeAlias = Literal["transient", "per_resolution", "scoped", "singleton"]
LifespanPolicy: TypeAlias = Lifespan | Literal["auto"]
ScopePolicy: TypeAlias = Literal["current", "per_call"]
RootPolicy: TypeAlias = Literal["entrypoint", "resolvable", "dependency_only"]
ValidationRuleMode: TypeAlias = Literal["build", "validation"]
BundleRunScope: TypeAlias = Literal["boundary", "scope", "container"]
K = TypeVar("K")
TProviderService = TypeVar("TProviderService")


class RuntimeOwnerKind(str, Enum):
    """Stable category for a compiled cache or cleanup owner."""

    none = "none"
    resolution = "resolution"
    scope = "scope"
    singleton = "singleton"
    supplied = "supplied"


class ComponentKind(str, Enum):
    """The role an occurrence has in a compiled component plan."""

    registration = "registration"
    decorator = "decorator"
    pre_configuration = "pre_configuration"
    collection = "collection"
    scope_slot = "scope_slot"
    value = "value"
    runtime_context = "runtime_context"
    provider = "provider"
    managed_provider = "managed_provider"
    provider_map = "provider_map"
    per_call_handle = "per_call_handle"


class ComponentActivation(str, Enum):
    """How a compiled occurrence obtains its runtime value."""

    constructor = "constructor"
    factory = "factory"
    instance = "instance"
    supplied = "supplied"
    collection = "collection"
    context = "context"
    deferred = "deferred"


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
    build_args: Mapping[str, Any]
    kind: ComponentKind
    activation: ComponentActivation
    requires_async: bool
    manages_cleanup: bool
    cache_owner: RuntimeOwnerKind
    cleanup_owner: RuntimeOwnerKind
    owner_id: int | None
    ownership_reason: str
    provider_mode: Literal["sync", "async"] | None
    position: int | None
    argument: str | None
    parent_id: int | None
    dependency_ids: tuple[int, ...]
    decorator_ids: tuple[int, ...]
    decorated_id: int | None
    pre_configuration_ids: tuple[int, ...]
    boundary: str | None
    declared_service_type: Any | None
    _generic_mapping: GenericTypeMap | None = field(default=None, compare=False, repr=False)

    @property
    def generic_mapping(self) -> GenericTypeMap:
        mapping = self._generic_mapping
        if mapping is None:
            mapping = GenericTypeMap(self.service_type)
            object.__setattr__(self, "_generic_mapping", mapping)
        return mapping


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
    build_args: Mapping[str, Any]
    kind: ComponentKind
    activation: ComponentActivation
    requires_async: bool = False
    manages_cleanup: bool = False
    cache_owner: RuntimeOwnerKind = RuntimeOwnerKind.none
    cleanup_owner: RuntimeOwnerKind = RuntimeOwnerKind.none
    owner_id: int | None = None
    ownership_reason: str = "No runtime-owned cache or cleanup"
    provider_mode: Literal["sync", "async"] | None = None
    position: int | None = None
    argument: str | None = None
    parent_id: int | None = None
    dependency_ids: tuple[int, ...] = ()
    decorator_ids: tuple[int, ...] = ()
    decorated_id: int | None = None
    pre_configuration_ids: tuple[int, ...] = ()
    boundary: str | None = None
    declared_service_type: Any | None = None

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
            build_args=self.build_args,
            kind=self.kind,
            activation=self.activation,
            requires_async=self.requires_async,
            manages_cleanup=self.manages_cleanup,
            cache_owner=self.cache_owner,
            cleanup_owner=self.cleanup_owner,
            owner_id=self.owner_id,
            ownership_reason=self.ownership_reason,
            provider_mode=self.provider_mode,
            position=self.position,
            argument=self.argument,
            parent_id=self.parent_id,
            dependency_ids=self.dependency_ids,
            decorator_ids=self.decorator_ids,
            decorated_id=self.decorated_id,
            pre_configuration_ids=self.pre_configuration_ids,
            boundary=self.boundary,
            declared_service_type=self.declared_service_type,
        )


def normalize_implementation_type(implementation: Any, service_type: Any) -> type:
    """Return a stable type for classes, instances, and factory callables."""

    implementation = normalize_type_alias(implementation)
    service_type = normalize_type_alias(service_type)

    if (implementation_class := constructor_type(implementation)) is not None:
        return implementation_class
    try:
        annotation = inspect.signature(implementation).return_annotation
    except (TypeError, ValueError):
        annotation = inspect.Signature.empty
    if annotation is not inspect.Signature.empty:
        annotation = normalize_type_alias(annotation)
    if annotation is not inspect.Signature.empty and isinstance(annotation, type):
        return annotation
    origin = getattr(service_type, "__origin__", None)
    # Python 3.14 exposes a class origin for unions. It describes the type
    # expression, not the unknown concrete result of this factory.
    if isinstance(origin, type) and origin not in (Union, UnionType):
        return origin
    return service_type if isinstance(service_type, type) else type(implementation)


class _ComponentGraph:
    __slots__ = ("_drafts", "_records", "_views")

    def __init__(self) -> None:
        self._views: list[_ComponentViewContext] = []
        self._drafts: dict[int, _ComponentDraft] = {}
        self._records: dict[int, _ComponentRecord] | None = None

    def add(self, draft: _ComponentDraft) -> Component:
        self._drafts[draft.occurrence_id] = draft
        return Component(self, draft.occurrence_id)

    def view(self, source: Component, parent: Component) -> Component:
        context = _ComponentViewContext(source.occurrence_id, parent.occurrence_id, len(self._views))
        self._views.append(context)
        return Component(self, context.remap(source.occurrence_id))

    def view_source(self, occurrence_id: int) -> tuple[_ComponentViewContext, int] | None:
        if occurrence_id > -(1 << 64):
            return None
        context, source = divmod(-occurrence_id, 1 << 64)
        if context > len(self._views):
            return None
        return self._views[context - 1], source

    def record(self, occurrence_id: int) -> _ComponentDraft | _ComponentRecord | _ComponentViewRecord:
        records = self._drafts if self._records is None else self._records
        if occurrence_id in records:
            return records[occurrence_id]
        view = self.view_source(occurrence_id)
        if view is not None:
            return _ComponentViewRecord(self, *view)
        raise KeyError(occurrence_id)

    def freeze(self) -> None:
        records: dict[int, _ComponentRecord] = {}
        # Release each draft as its frozen replacement is created.
        for key in tuple(self._drafts):
            records[key] = self._drafts.pop(key).freeze()
        self._records = records


@dataclass(frozen=True, slots=True)
class _ComponentViewContext:
    root: int
    parent: int
    index: int

    def remap(self, source: int) -> int:
        return -(((self.index + 1) << 64) + source)


class _ComponentViewRecord:
    """Ephemeral metadata projection; no target subtree is copied or retained."""

    __slots__ = ("graph", "context", "source")

    def __init__(self, graph: _ComponentGraph, context: _ComponentViewContext, source: int) -> None:
        self.graph = graph
        self.context = context
        self.source = source

    def __getattr__(self, name: str) -> Any:
        record = self.graph.record(self.source)
        if name == "occurrence_id":
            return self.context.remap(self.source)
        value = getattr(record, name)
        if name == "parent_id":
            return (
                self.context.parent if self.source == self.context.root or value is None else self.context.remap(value)
            )
        if name in ("owner_id", "decorated_id"):
            return None if value is None else self.context.remap(value)
        if name in ("dependency_ids", "decorator_ids", "pre_configuration_ids"):
            return tuple(self.context.remap(item) for item in value)
        if name == "ownership_reason" and record.cache_owner is RuntimeOwnerKind.scope:
            parent = Component(self.graph, record.parent_id) if record.parent_id is not None else None
            while parent is not None and parent.kind not in (
                ComponentKind.managed_provider,
                ComponentKind.per_call_handle,
            ):
                parent = parent.parent
            if parent is None:
                parent = Component(self.graph, self.context.parent)
                while parent is not None and parent.kind not in (
                    ComponentKind.managed_provider,
                    ComponentKind.per_call_handle,
                ):
                    parent = parent.parent
            if parent is not None and parent.kind is ComponentKind.managed_provider:
                return "The scoped instance closes with its managed acquisition scope"
        return value

    def freeze(self) -> _ComponentRecord:
        record = self.graph.record(self.source)
        base = record if isinstance(record, _ComponentRecord) else record.freeze()
        return replace(
            base,
            **{
                name: getattr(self, name)
                for name in (
                    "occurrence_id",
                    "parent_id",
                    "owner_id",
                    "decorated_id",
                    "dependency_ids",
                    "decorator_ids",
                    "pre_configuration_ids",
                    "ownership_reason",
                )
            },
            _generic_mapping=None,
        )


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
    def _record(self) -> _ComponentDraft | _ComponentRecord | _ComponentViewRecord:
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
    def declared_service_type(self) -> Any:
        """Original alias spelling when one was declared, otherwise the canonical service type."""

        declared = self._record.declared_service_type
        return self._record.service_type if declared is None else declared

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
    def build_args(self) -> Mapping[str, Any]:
        """Immutable user inputs supplied for this component's compilation."""

        return self._record.build_args

    @property
    def boundary(self) -> str | None:
        """Composition area where this component was defined; ``None`` is root."""

        return self._record.boundary

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
    def cache_owner(self) -> RuntimeOwnerKind:
        """Owner category of this occurrence's cached instance, if any."""

        return self._record.cache_owner

    @property
    def cleanup_owner(self) -> RuntimeOwnerKind:
        """Owner category selected for cleanup performed by this occurrence."""

        return self._record.cleanup_owner

    @property
    def owner_occurrence_id(self) -> int | None:
        """Occurrence responsible for promoted ownership, without a runtime identity."""

        return self._record.owner_id

    @property
    def ownership_reason(self) -> str:
        return self._record.ownership_reason

    @property
    def provider_mode(self) -> Literal["sync", "async"] | None:
        """Invocation mode for a synthetic deferred provider occurrence."""

        return self._record.provider_mode

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

    def has_dependant_service_type(self, service_type: TypeForm[Any]) -> bool:
        service_type = normalize_type_alias(service_type)
        return self.has_descendant(lambda component: component.service_type == service_type)

    def has_dependant_implementation_type(self, implementation_type: TypeForm[Any]) -> bool:
        implementation_type = normalize_type_alias(implementation_type)
        return self.has_descendant(lambda component: component.implementation_type == implementation_type)

    def __repr__(self) -> str:
        return f"Component({self.service_type!r} -> {self.implementation!r}, occurrence={self.occurrence_id})"


def _undecorated_component_view(component: Component) -> Component:
    """Snapshot an occurrence for generated-template applicability predicates.

    Hide attached decorator pipelines throughout the graph without recompiling
    selected dependencies or changing occurrence, parent, or ownership metadata.
    Ancestors retain the context available at this compilation point. This is
    an inspection graph only; ordinary decorator predicates keep their old view.
    """
    source = component._graph
    # Follow only this occurrence's connected context. Unrelated compiled roots
    # must not increase the cost of a predicate snapshot. Parent/dependency and
    # owner links preserve everything a contextual component predicate can read.
    records: dict[int, _ComponentRecord] = {}
    pending = [component.occurrence_id]
    while pending:
        key = pending.pop()
        if key in records:
            continue
        value = source.record(key)
        record = value if isinstance(value, _ComponentRecord) else value.freeze()
        records[key] = replace(record, decorator_ids=())
        pending.extend(record.dependency_ids)
        pending.extend(record.pre_configuration_ids)
        pending.extend(item for item in (record.parent_id, record.decorated_id, record.owner_id) if item is not None)
    graph = _ComponentGraph()
    graph._records = records
    return Component(graph, component.occurrence_id)


ComponentFilter: TypeAlias = Callable[[Component], bool]


def all_components(_: Component) -> bool:
    return True


def default_component_filter(component: Component) -> bool:
    return component.name is None


class ComponentBuilder(Protocol):
    """Structural protocol documented for bundle authors.

    The concrete builders intentionally use duck typing so third-party bundle
    packages do not need to inherit from a Clean IoC base class.
    """

    id: str

    def apply_bundle(self, bundle: Callable[[ComponentBuilder], None]) -> None: ...

    def create_boundary(
        self,
        name: str,
        *,
        uses: Iterable[Use] = (),
        exposes: Iterable[Expose] = (),
    ) -> BoundaryBuilder: ...

    def bundle_run_key(self, per: BundleRunScope) -> str: ...

    def add_validation_rule(self, rule: ValidationRule, *, mode: ValidationRuleMode = "build") -> None: ...

    def register(
        self,
        service_type: TypeForm[Any],
        implementation_type: TypeForm[Any] | None = None,
        *,
        factory: Callable[..., Any] | None = None,
        factory_specialization: object | None = None,
        instance: Any | None = None,
        lifespan: LifespanPolicy = "auto",
        scope: ScopePolicy = "current",
        name: str | None = None,
        arguments: Mapping[str, Any] | None = None,
        tags: Iterable[Tag] | None = None,
        when: ComponentFilter = all_components,
        candidate_when: ComponentFilter | None = None,
        parent_precedence: int = 0,
        prefer: ComponentPreference | None = None,
        contributes: Mapping[ProviderMapGroup[Any, Any], Hashable] | None = None,
        groups: Iterable[ServiceGroup] = (),
        root_policy: RootPolicy = "resolvable",
    ) -> str: ...

    def register_fallback(
        self,
        service_type: TypeForm[Any],
        implementation_type: TypeForm[Any] | None = None,
        *,
        factory: Callable[..., Any] | None = None,
        factory_specialization: object | None = None,
        instance: Any | None = None,
        lifespan: LifespanPolicy = "auto",
        scope: ScopePolicy = "current",
        name: str | None = None,
        arguments: Mapping[str, Any] | None = None,
        tags: Iterable[Tag] | None = None,
        when: ComponentFilter = all_components,
        candidate_when: ComponentFilter | None = None,
        parent_precedence: int = 0,
        prefer: ComponentPreference | None = None,
        contributes: Mapping[ProviderMapGroup[Any, Any], Hashable] | None = None,
        groups: Iterable[ServiceGroup] = (),
        root_policy: RootPolicy = "resolvable",
    ) -> str: ...

    def register_pattern(
        self,
        service_type: TypeForm[Any],
        *,
        factory: Callable[..., Any],
        lifespan: LifespanPolicy = "auto",
        scope: ScopePolicy = "current",
        name: str | None = None,
        arguments: Mapping[str, Any] | None = None,
        tags: Iterable[Tag] | None = None,
        when: ComponentFilter = all_components,
        candidate_when: ComponentFilter | None = None,
        parent_precedence: int = 0,
        prefer: ComponentPreference | None = None,
        groups: Iterable[ServiceGroup] = (),
    ) -> str: ...

    @overload
    def register_provider_map(
        self,
        service_type: ProviderMapGroup[K, TProviderService],
        *,
        asynchronous: bool = False,
        component_filter: ComponentFilter = all_components,
        name: str | None = None,
        root_policy: RootPolicy = "resolvable",
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
        root_policy: RootPolicy = "resolvable",
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
        root_policy: RootPolicy = "resolvable",
    ) -> str: ...

    def register_subclasses(
        self,
        base_type: type,
        *,
        ensure_import_modules: str | Iterable[str] = (),
        include_children: bool = False,
        lifespan: LifespanPolicy = "auto",
        scope: ScopePolicy = "current",
        subclass_type_filter: Callable[[type], bool] = ...,
        name: str | None = None,
        tags: Iterable[Tag] | None = None,
        when: ComponentFilter = all_components,
        parent_precedence: int = 0,
        prefer: ComponentPreference | None = None,
        groups: Iterable[ServiceGroup] = (),
    ) -> None: ...

    def register_registration_template(
        self,
        *,
        for_each: Any,
        template: Callable[[RegistrationInfo], RegistrationTemplate],
        source_filter: ComponentFilter = all_components,
    ) -> str: ...

    def patch_registration_template(
        self,
        template_id: str,
        *,
        for_each: Any = ...,
        template: Callable[[RegistrationInfo], RegistrationTemplate] | object = ...,
        source_filter: ComponentFilter | object = ...,
    ) -> None: ...

    def remove_registration_template(self, template_id: str) -> None: ...

    def register_decorator_template(
        self,
        *,
        for_each: Any,
        template: Callable[[RegistrationInfo], DecoratorTemplate],
        source_filter: ComponentFilter = all_components,
    ) -> str: ...

    def patch_decorator_template(
        self,
        template_id: str,
        *,
        for_each: Any = ...,
        template: Callable[[RegistrationInfo], DecoratorTemplate] | object = ...,
        source_filter: ComponentFilter | object = ...,
    ) -> None: ...

    def remove_decorator_template(self, template_id: str) -> None: ...

    def register_decorator(
        self,
        service_type: TypeForm[Any],
        decorator_type: TypeForm[Any] | Callable[..., Any],
        *,
        when: ComponentFilter = all_components,
        decorated_arg: str | None = None,
        arguments: Mapping[str, Any] | None = None,
        position: int = 0,
        name: str | None = None,
        tags: Iterable[Tag] | None = None,
    ) -> str: ...

    def patch_component(
        self,
        service_type: TypeForm[Any],
        component_id: str,
        *,
        arguments: Mapping[str, Any] | None = None,
        lifespan: LifespanPolicy | None = None,
        scope: ScopePolicy | object = ...,
        tags: Iterable[Tag] | None = None,
        parent_precedence: int | None = None,
        prefer: ComponentPreference | None | _Undefined = Undefined,
    ) -> None: ...

    def patch_decorator(
        self,
        service_type: Any,
        decorator_id: str,
        *,
        decorated_arg: str | None | object = ...,
        arguments: Mapping[str, Any] | None = None,
        position: int | object = ...,
        when: ComponentFilter | None = None,
        name: str | None | object = ...,
        tags: Iterable[Tag] | None = None,
    ) -> None: ...

    def remove_decorator(self, service_type: Any, decorator_id: str) -> None: ...

    def pre_configure(
        self,
        service_type: TypeForm[Any] | Iterable[TypeForm[Any]],
        configuration_function: Callable,
        *,
        when: ComponentFilter = all_components,
        arguments: Mapping[str, Any] | None = None,
        continue_on_failure: bool = False,
    ) -> str: ...

    def declare_scope_slot(self, service_type: TypeForm[Any], name: str | None = None) -> Any: ...

    def mark_entrypoint(
        self,
        service_type: Any,
        *,
        filter: ComponentFilter = default_component_filter,
    ) -> Any: ...
