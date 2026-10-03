"""Direct closed aliases must compile constructors without generating classes."""

from typing import Generic, TypeVar, cast, final

import pytest

from clean_ioc import ComponentActivation, ContainerBuilder, ContainerBuildError

T = TypeVar("T")
Item = TypeVar("Item")
Value = TypeVar("Value")
X = TypeVar("X")
Y = TypeVar("Y")


class Repository(Generic[T]):
    pass


class Dependency:
    pass


@final
class Consumer(Generic[T]):
    def __init__(self, dependency: Dependency, repository: Repository[T], repositories: list[Repository[T]]):
        self.dependency = dependency
        self.repository = repository
        self.repositories = repositories


class Contract(Generic[Item]):
    pass


class Implementation(Contract[Value], Generic[Value]):
    def __init__(self, repository: Repository[Value]):
        self.repository = repository


class Base(Generic[Item, Value]):
    def __init__(self, first: Repository[Item], second: Repository[Value]):
        self.first = first
        self.second = second


class Inherited(Base[Y, X], Generic[X, Y]):
    pass


def test_closed_alias_dependencies_identity_and_independent_singletons():
    builder = ContainerBuilder()
    builder.register(Dependency, lifespan="singleton")
    for item in (str, int):
        builder.register(Repository[item], lifespan="singleton")
        builder.register(Consumer[item], lifespan="singleton")
    with builder.build() as container:
        for item in (str, int):
            consumer = container.resolve(Consumer[item])
            assert type(consumer) is Consumer
            assert isinstance(consumer.dependency, Dependency)
            assert consumer.repository is container.resolve(Repository[item])
            assert consumer.repositories == [consumer.repository]
            assert container.resolve(Consumer[item]) is consumer
        assert container.resolve(Consumer[str]) is not container.resolve(Consumer[int])


def test_explicit_pair_and_inherited_reordered_bindings_and_metadata():
    builder = ContainerBuilder()
    builder.register(Repository[str])
    builder.register(Repository[int])
    builder.register(Contract[str], Implementation[str])
    builder.register(Inherited[str, int])
    with builder.build() as container:
        service = container.resolve(Contract[str])
        assert type(service) is Implementation
        component = next(r.component for r in container.graph.roots if r.component.service_type == Contract[str])
        assert component.implementation == Implementation[str]
        assert component.implementation_type is Implementation
        assert component.activation is ComponentActivation.constructor
        assert component.generic_mapping["Item"] is str
        assert component.generic_mapping.get("Value") is None
        inherited = container.resolve(Inherited[str, int])
        assert type(inherited) is Inherited
        assert getattr(inherited.first, "__orig_class__") == Repository[int]
        assert getattr(inherited.second, "__orig_class__") == Repository[str]


def test_missing_closed_dependency_is_a_recoverable_build_failure():
    builder = ContainerBuilder()
    builder.register(Contract[str], Implementation[str])
    with pytest.raises(ContainerBuildError, match="Repository\\[str\\]") as error:
        builder.build()
    assert "repository" in str(error.value)
    assert "Implementation" in str(error.value)
    builder.register(Repository[str])
    assert type(builder.build().resolve(Contract[str])) is Implementation


def test_argument_policies_specialized_context_names_tags_and_patching():
    from clean_ioc import INJECT, REMOVE, Tag, derive, generic_arg, inject, select
    from clean_ioc import component_filters as cf

    class Configured(Generic[T]):
        def __init__(
            self,
            repository: Repository[T] = cast(Repository[T], None),
            label: str = "default",
            item_type: type = cast(type, None),
        ):
            self.repository = repository
            self.label = label
            self.item_type = item_type

    seen = []

    def policy(context):
        assert context.annotation == Repository[str]
        assert context.component.implementation_type is Configured
        assert context.component.activation is ComponentActivation.constructor
        assert context.component.generic_mapping["T"] is str
        seen.append(context)
        return INJECT

    builder = ContainerBuilder()
    default = Repository[str]()
    named = Repository[str]()
    builder.register(Repository[str], instance=default)
    builder.register(Repository[str], instance=named, name="chosen", tags=[Tag("source", "named")])
    builder.register(Configured[str], name="defaults")
    component_id = builder.register(
        Configured[str], arguments={"repository": "replace", "label": "literal", "item_type": generic_arg("T")}
    )
    builder.patch_component(Configured[str], component_id, arguments={"repository": derive(policy), "label": REMOVE})
    builder.register(Configured[str], name="inject", arguments={"repository": inject()})
    builder.register(Configured[str], name="select", arguments={"repository": select(cf.with_name("chosen"))})
    with builder.build() as container:
        count = len(seen)
        assert count > 0
        assert container.resolve(Configured[str]).repository is default
        assert container.resolve(Configured[str]).label == "default"
        assert container.resolve(Configured[str]).item_type is str
        assert container.resolve(Configured[str], filter=cf.with_name("defaults")).repository is None
        assert container.resolve(Configured[str], filter=cf.with_name("inject")).repository is default
        assert container.resolve(Configured[str], filter=cf.with_name("select")).repository is named
        assert len(seen) == count


def test_override_removal_rebuilds_specialized_required_dependency():
    from clean_ioc import REMOVE

    builder = ContainerBuilder()
    builder.register(Repository[str])
    key = builder.register(Implementation[str], arguments={"repository": "override"})
    builder.patch_component(Implementation[str], key, arguments={"repository": REMOVE})
    assert type(builder.build().resolve(Implementation[str]).repository) is Repository


def test_real_constructor_controls_unknown_argument_validation():
    builder = ContainerBuilder()
    builder.register(Implementation[str], arguments={"typo": 1, "repository": 2})
    with pytest.raises(ContainerBuildError, match="no argument named 'typo'"):
        builder.build()

    class Flexible(Generic[T]):
        def __init__(self, repository: Repository[T], **kwargs):
            self.repository = repository
            self.kwargs = kwargs

    builder = ContainerBuilder()
    builder.register(Repository[str])
    builder.register(Flexible[str], arguments={"extra": 1})
    result = builder.build().resolve(Flexible[str])
    assert type(result.repository) is Repository
    assert result.kwargs == {"extra": 1}


@pytest.mark.parametrize("lifespan", ["transient", "per_resolution", "scoped", "singleton"])
def test_closed_lifespans_and_scope_boundaries(lifespan):
    class Pair:
        def __init__(self, first: Implementation[str], second: Implementation[str], other: Implementation[int]):
            self.first = first
            self.second = second
            self.other = other

    builder = ContainerBuilder()
    for item in (str, int):
        builder.register(Repository[item], lifespan=lifespan)
        builder.register(Implementation[item], lifespan=lifespan)
    builder.register(Pair)
    with builder.build() as container, container.new_scope() as first_scope, container.new_scope() as second_scope:
        first = first_scope.resolve(Pair)
        repeated = first_scope.resolve(Pair)
        second = second_scope.resolve(Pair)
        assert (first.first is first.second) == (lifespan != "transient")
        assert (first.first is repeated.first) == (lifespan in ("scoped", "singleton"))
        assert (first.first is second.first) == (lifespan == "singleton")
        assert first.first is not first.other
        assert getattr(first.first.repository, "__orig_class__") == Repository[str]
        assert getattr(first.other.repository, "__orig_class__") == Repository[int]


async def test_async_dependency_and_no_constructor_or_discovery_at_runtime(monkeypatch):
    import clean_ioc._legacy as legacy

    calls = []

    class AsyncConsumer(Generic[T]):
        def __init__(self, repository: Repository[T]):
            calls.append("constructor")
            self.repository = repository

    async def repository() -> Repository[str]:
        calls.append("factory")
        return Repository[str]()

    builder = ContainerBuilder()
    builder.register(Repository[str], factory=repository)
    builder.register(AsyncConsumer[str])
    container = builder.build()
    assert calls == []

    def forbidden(*args, **kwargs):
        pytest.fail("Runtime must not discover or specialize constructor dependencies")

    monkeypatch.setattr(legacy, "_get_arg_info", forbidden)
    monkeypatch.setattr(legacy, "resolve_typevars", forbidden)
    async with container:
        result = await container.resolve_async(AsyncConsumer[str])
        assert type(result) is AsyncConsumer
        assert getattr(result.repository, "__orig_class__") == Repository[str]
        assert calls == ["factory", "constructor"]


def test_generic_decorator_and_service_mapping_policy():
    from clean_ioc import component_filters as cf
    from clean_ioc import generic_arg

    class Wrapper(Contract[Item], Generic[Item]):
        def __init__(self, child: Contract[Item], item_type: type):
            self.child = child
            self.item_type = item_type

    builder = ContainerBuilder()
    builder.register(Repository[str])
    builder.register(Contract[str], Implementation[str])
    builder.register_decorator(
        Contract,
        Wrapper,
        arguments={"item_type": generic_arg("Item")},
        when=cf.implementation_type_is(Implementation),
    )
    with builder.build() as container:
        wrapped = container.resolve(Contract[str])
        assert isinstance(wrapped, Wrapper)
        assert type(wrapped.child) is Implementation
        assert getattr(wrapped.child.repository, "__orig_class__") == Repository[str]
        assert wrapped.item_type is str


def test_unbound_required_nested_typevar_fails_but_value_policies_and_defaults_work():
    class Unbound(Generic[T]):
        def __init__(self, repositories: list[Repository[Value]]):
            self.repositories = repositories

    builder = ContainerBuilder()
    key = builder.register(Unbound[str])
    with pytest.raises(ContainerBuildError, match="Unable to resolve constructor TypeVar.*Value"):
        builder.build()
    builder.patch_component(Unbound[str], key, arguments={"repositories": ["explicit"]})
    assert builder.build().resolve(Unbound[str]).repositories == ["explicit"]


def test_pep695_closed_classes_and_inheritance():
    import sys

    if sys.version_info < (3, 12):
        pytest.skip("PEP 695 requires Python 3.12")
    namespace = {"ContainerBuilder": ContainerBuilder}
    exec(  # noqa: S102 - version-gated syntax must remain parseable on Python 3.11
        """
class Repository[T]:
    pass
class Contract[Item]:
    pass
class Implementation[Value](Contract[Value]):
    def __init__(self, repository: Repository[Value]):
        self.repository = repository
class Base[A, B]:
    def __init__(self, first: Repository[A], second: Repository[B]):
        self.first, self.second = first, second
class Inherited[X, Y](Base[Y, X]):
    pass
builder = ContainerBuilder()
builder.register(Repository[str])
builder.register(Repository[int])
builder.register(Contract[str], Implementation[str])
builder.register(Inherited[str, int])
with builder.build() as container:
    service = container.resolve(Contract[str])
    assert type(service) is Implementation
    assert getattr(service.repository, "__orig_class__") == Repository[str]
    inherited = container.resolve(Inherited[str, int])
    assert type(inherited) is Inherited
    assert getattr(inherited.first, "__orig_class__") == Repository[int]
    assert getattr(inherited.second, "__orig_class__") == Repository[str]
""",
        namespace,
    )


def test_traditional_inherited_generic_without_redundant_generic_base():
    class Implicit(Contract[Value]):
        def __init__(self, repository: Repository[Value]):
            self.repository = repository

    builder = ContainerBuilder()
    builder.register(Repository[str])
    builder.register(Contract[str], Implicit[str])
    with builder.build() as container:
        result = container.resolve(Contract[str])
        assert type(result) is Implicit
        assert getattr(result.repository, "__orig_class__") == Repository[str]


def test_explicit_pair_policies_keep_service_mapping_in_drafts_and_frozen_graph():
    from typetoolbox.generics import GenericTypeMap

    from clean_ioc import component_filters as cf
    from clean_ioc import generic_arg

    class Descriptor(Contract[Value], Generic[Value]):
        def __init__(self, item_type: type, repository: Repository[Value]):
            self.item_type = item_type
            self.repository = repository

    seen = []

    def accepts(component):
        assert component.implementation == Descriptor[str]
        assert component.implementation_type is Descriptor
        assert component.activation is ComponentActivation.constructor
        assert cf.has_generic_arg("Item", str)(component)
        if component.service_type == Contract[str]:
            assert component.generic_mapping.get("Value") is None
        assert GenericTypeMap(component.implementation)["Value"] is str
        seen.append(component)
        return True

    builder = ContainerBuilder()
    builder.register(Repository[str])
    builder.register(Contract[str], Descriptor[str], arguments={"item_type": generic_arg("Item")}, when=accepts)
    with builder.build() as container:
        assert cast(Descriptor[str], container.resolve(Contract[str])).item_type is str
        assert seen
        for component in container.components:
            if component.service_type == Contract[str]:
                accepts(component)

    builder = ContainerBuilder()
    builder.register(Repository[str])
    builder.register(Contract[str], Descriptor[str], arguments={"item_type": generic_arg("Value")})
    with pytest.raises(ContainerBuildError, match="Value"):
        builder.build()
