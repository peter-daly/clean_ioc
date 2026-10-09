"""Fallbacks reuse the request's filters and generic bindings."""

from typing import Generic, TypeVar

import pytest

import clean_ioc.component_filters as cf
from clean_ioc import ContainerBuilder, ContainerBuildError, Provider, Tag, select

T = TypeVar("T")


@pytest.mark.parametrize("fallback_first", [True, False])
def test_ordinary_registration_wins_for_roots_and_collections(fallback_first):
    class Service:
        pass

    class Primary(Service):
        pass

    class Default(Service):
        pass

    class Consumer:
        def __init__(self, one: Service, many: list[Service], deferred: Provider[Service]):
            self.one, self.many, self.deferred = one, many, deferred

    builder = ContainerBuilder()
    if fallback_first:
        builder.register_fallback(Service, Default)
    builder.register(Service, Primary)
    if not fallback_first:
        builder.register_fallback(Service, Default)
    builder.register(Consumer)
    container = builder.build()

    assert isinstance(container.resolve(Service), Primary)
    assert [type(item) for item in container.resolve(list[Service])] == [Primary]
    consumer = container.resolve(Consumer)
    assert isinstance(consumer.one, Primary)
    assert [type(item) for item in consumer.many] == [Primary]
    assert isinstance(consumer.deferred(), Primary)
    assert isinstance(container.resolve(Provider[Service])(), Primary)


@pytest.mark.parametrize("generic", [False, True])
def test_fallback_reuses_name_tag_filter_and_actual_parent(generic):
    class Service(Generic[T]):
        pass

    class Primary(Service[T]):
        pass

    class Default(Service[T]):
        pass

    requested = Service[int] if generic else Service

    class Consumer:
        def __init__(self, value: requested):
            self.value = value

    class Other:
        def __init__(self, value: requested):
            self.value = value

    builder = ContainerBuilder()
    builder.register(requested, Primary, name="different")
    builder.register_fallback(
        Service,
        Default,
        name="namedx",
        tags=[Tag("Y", "Z")],
        when=cf.parent(cf.implementation_type_is(Consumer)),
    )
    builder.register_fallback(
        Service, Primary, name="namedx", tags=[Tag("Y", "Z")], when=cf.parent(cf.implementation_type_is(Other))
    )
    predicate = cf.with_name("namedx") & cf.has_tag("Y", "Z")
    builder.register(Consumer, arguments={"value": select(predicate)})
    builder.register(Other, arguments={"value": select(predicate)})
    container = builder.build()

    assert isinstance(container.resolve(Consumer).value, Default)
    assert isinstance(container.resolve(Other).value, Primary)


def test_generic_fallback_specializes_its_own_dependencies_and_singleton_cache():
    class Service(Generic[T]):
        pass

    class Default(Service[T]):
        def __init__(self, value: T):
            self.value = value

    class Consumer:
        def __init__(self, number: Service[int], text: Service[str], again: Service[int]):
            self.number, self.text, self.again = number, text, again

    builder = ContainerBuilder()
    builder.register(int, instance=123)
    builder.register(str, instance="abc")
    builder.register_fallback(Service, Default, lifespan="singleton")
    builder.register(Consumer)
    container = builder.build()
    consumer = container.resolve(Consumer)

    assert isinstance(consumer.number, Default)
    assert isinstance(consumer.text, Default)
    assert consumer.number.value == 123
    assert consumer.text.value == "abc"
    assert consumer.number is consumer.again
    assert consumer.number is not consumer.text


def test_closed_generic_primary_rejected_by_when_uses_fallback():
    class Service(Generic[T]):
        pass

    class Primary(Service[int]):
        pass

    class Default(Service[T]):
        pass

    class Consumer:
        def __init__(self, value: Service[int]):
            self.value = value

    builder = ContainerBuilder()
    builder.register(Service[int], Primary, when=lambda component: component.parent is None)
    builder.register_fallback(Service, Default)
    builder.register(Consumer)
    container = builder.build()
    assert isinstance(container.resolve(Service[int]), Primary)
    assert isinstance(container.resolve(Consumer).value, Default)


def test_generic_discovery_and_separate_fallback():
    class Service(Generic[T]):
        pass

    class Primary(Service[int]):
        pass

    class Default(Service[T]):
        pass

    class Consumer:
        def __init__(self, number: Service[int], text: Service[str]):
            self.number, self.text = number, text

    builder = ContainerBuilder()
    builder.register_subclasses(Service)
    builder.register_fallback(Service, Default)
    builder.register(Consumer)
    consumer = builder.build().resolve(Consumer)
    assert isinstance(consumer.number, Primary)
    assert isinstance(consumer.text, Default)


def test_filtered_generic_roots_and_collections_choose_fallback_only_when_needed():
    class Service(Generic[T]):
        pass

    class Primary(Service[int]):
        pass

    class Default(Service[T]):
        pass

    builder = ContainerBuilder()
    builder.register(Service[int], Primary, tags=[Tag("primary")])
    builder.register_fallback(Service, Default, tags=[Tag("fallback")])
    container = builder.build()
    assert isinstance(container.resolve(Service[int]), Primary)
    assert isinstance(container.resolve(Service[int], cf.has_tag("fallback")), Default)
    assert [type(x) for x in container.resolve(list[Service[int]], cf.all_components)] == [Primary]
    assert all(isinstance(x, Default) for x in container.resolve(list[Service[int]], cf.has_tag("fallback")))
    assert len(container.resolve(list[Service[int]], cf.has_tag("fallback"))) == 1
    assert isinstance(container.resolve(Provider[Service[int]], cf.has_tag("fallback"))(), Default)


def test_broken_primary_does_not_silently_switch_to_fallback():
    class Missing:
        pass

    class Service:
        pass

    class Broken(Service):
        def __init__(self, missing: Missing):
            pass

    builder = ContainerBuilder()
    builder.register(Service, Broken)
    builder.register_fallback(Service)
    with pytest.raises(ContainerBuildError):
        builder.build()


def test_generic_factory_fallback_and_nested_constructor_bindings():
    U = TypeVar("U")

    class Service(Generic[T]):
        pass

    class Default(Service[U]):
        def __init__(self, values: list[U]):
            self.values = values

    def fallback(value: T) -> Service[T]:
        return Default([value])

    class Consumer:
        def __init__(self, number: Service[int], text: Service[str]):
            self.number, self.text = number, text

    builder = ContainerBuilder()
    builder.register(int, instance=123)
    builder.register(str, instance="abc")
    builder.register_fallback(Service, Default)
    builder.register_fallback(Service, factory=fallback, name="factory")
    builder.register(Consumer, arguments={"text": select(cf.with_name("factory"))})
    consumer = builder.build().resolve(Consumer)
    assert isinstance(consumer.number, Default)
    assert isinstance(consumer.text, Default)
    assert consumer.number.values == [123]
    assert consumer.text.values == ["abc"]


def test_fallback_collection_and_provider_dependencies():
    class Service(Generic[T]):
        pass

    class Default(Service[T]):
        pass

    class Consumer:
        def __init__(self, values: list[Service[int]], one: Provider[Service[int]], many: Provider[list[Service[int]]]):
            self.values, self.one, self.many = values, one, many

    builder = ContainerBuilder()
    builder.register_fallback(Service, Default)
    builder.register(Consumer)
    consumer = builder.build().resolve(Consumer)
    assert len(consumer.values) == 1
    assert isinstance(consumer.values[0], Default)
    assert isinstance(consumer.one(), Default)
    assert len(consumer.many()) == 1
    assert isinstance(consumer.many()[0], Default)


def test_generic_fallback_keeps_singleton_ownership_in_overlay():
    class Service(Generic[T]):
        pass

    class Default(Service[T]):
        pass

    builder = ContainerBuilder()
    builder.register_fallback(Service, Default, lifespan="singleton")
    builder.mark_entrypoint(Service[int])
    container = builder.build()
    value = container.resolve(Service[int])
    overlay = container.new_scope_builder().build()
    assert overlay.resolve(Service[int]) is value


def test_generic_fallback_visible_through_boundary():
    from clean_ioc import Expose

    class Service(Generic[T]):
        pass

    class Default(Service[T]):
        pass

    class Consumer:
        def __init__(self, value: Service[int]):
            self.value = value

    builder = ContainerBuilder()
    boundary = builder.create_boundary("source", exposes=[Expose(Service)])
    boundary.register_fallback(Service, Default)
    builder.register(Consumer)
    assert isinstance(builder.build().resolve(Consumer).value, Default)


def test_provider_map_uses_filtered_fallback_contributions():
    from collections.abc import Mapping

    from clean_ioc import ProviderMapGroup

    class Service:
        pass

    class Default(Service):
        pass

    group = ProviderMapGroup("services", str, Service)
    builder = ContainerBuilder()
    builder.register(Service, contributes={group: "ordinary"}, tags=[Tag("ordinary")])
    builder.register_fallback(Service, Default, contributes={group: "default"}, tags=[Tag("default")])
    builder.register_provider_map(group, component_filter=cf.has_tag("default"))
    providers = builder.build().resolve(Mapping[str, Provider[Service]])
    assert list(providers) == ["default"]
    assert isinstance(providers["default"](), Default)


@pytest.mark.asyncio
async def test_async_generic_fallback_factory():
    from clean_ioc import AsyncProvider

    class Service(Generic[T]):
        def __init__(self, value: T):
            self.value = value

    async def fallback(value: T) -> Service[T]:
        return Service(value)

    class Consumer:
        def __init__(self, value: AsyncProvider[Service[int]]):
            self.value = value

    builder = ContainerBuilder()
    builder.register(int, instance=123)
    builder.register_fallback(Service, factory=fallback)
    builder.register(Consumer)
    container = builder.build()
    consumer = container.resolve(Consumer)
    assert (await consumer.value()).value == 123


def test_closed_generic_subclass_base_uses_ordinary_discovery():
    class Service(Generic[T]):
        pass

    class IntService(Service[int]):
        pass

    class Concrete(IntService):
        pass

    builder = ContainerBuilder()
    builder.register_subclasses(IntService)
    assert type(builder.build().resolve(IntService)) is Concrete


def test_v2_exposes_one_subclass_discovery_method():
    assert not hasattr(ContainerBuilder, "register_generic_subclasses")


def test_closed_generic_fallback_binds_open_constructor():
    class Service(Generic[T]):
        pass

    class Default(Service[T]):
        def __init__(self, value: T):
            self.value = value

    builder = ContainerBuilder()
    builder.register(int, instance=123)
    builder.register_fallback(Service[int], Default)
    result = builder.build().resolve(Service[int])
    assert isinstance(result, Default)
    assert result.value == 123


@pytest.mark.parametrize("predicate", [cf.with_name("other"), cf.has_tag("Y", "wrong")])
def test_generic_fallback_does_not_bypass_dependency_filter(predicate):
    class Service(Generic[T]):
        pass

    class Default(Service[T]):
        pass

    class Consumer:
        def __init__(self, value: Service[int]):
            self.value = value

    builder = ContainerBuilder()
    builder.register_fallback(Service, Default, name="namedx", tags=[Tag("Y", "Z")])
    builder.register(Consumer, arguments={"value": select(predicate)})
    with pytest.raises(ContainerBuildError, match="missing-component"):
        builder.build()


def test_unused_dependency_only_fallback_is_not_compiled():
    class Service:
        pass

    class Missing:
        pass

    class Default(Service):
        def __init__(self, missing: Missing):
            pass

    class Consumer:
        def __init__(self, value: Service):
            self.value = value

    builder = ContainerBuilder()
    builder.register(Service)
    builder.register_fallback(Service, Default, root_policy="dependency_only")
    builder.register(Consumer)
    assert type(builder.build().resolve(Consumer).value) is Service


def test_fallback_explanation_retains_rejected_ordinary_candidate():
    class Service(Generic[T]):
        pass

    class Default(Service[T]):
        pass

    class Consumer:
        def __init__(self, value: Service[int]):
            self.value = value

    builder = ContainerBuilder()
    ordinary = builder.register(Service[int], name="other")
    builder.register_fallback(Service, Default)
    builder.register(Consumer)
    container = builder.build(diagnostics=True)
    consumer = next(root.component for root in container.graph.roots if root.component.service_type is Consumer)
    explanation = container.graph.explain(consumer.dependencies[0])
    assert "selected-fallback" in explanation.selected[0].reason_codes
    assert any(item.component_id == ordinary and "rejected-name" in item.reason_codes for item in explanation.rejected)
