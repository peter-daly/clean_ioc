import asyncio
import json
import sys
from collections.abc import Mapping
from contextlib import asynccontextmanager, contextmanager
from typing import Any, Generic, NewType, TypeVar
from typing import Mapping as TypingMapping

import pytest
from typing_extensions import TypeAliasType

import clean_ioc.component_filters as cf
from clean_ioc import (
    AsyncProvider,
    Boundary,
    ComponentKind,
    ContainerBuilder,
    ContainerBuildError,
    Expose,
    Provider,
    ProviderMapGroup,
    ProviderScopeClosedError,
    ResolutionContext,
    Scope,
    Use,
    select,
)


def codes(error):
    return {issue.code for issue in error.value.report.errors}


def test_provider_map_group_selects_contributors_before_compiling_delegator():
    class MessageProcessor:
        async def process_message(self) -> str:
            raise NotImplementedError

    delegated = ProviderMapGroup("delegated-processors", str, MessageProcessor)

    class CommandProcessor(MessageProcessor):
        async def process_message(self) -> str:
            return "command"

    class DelegatingProcessor(MessageProcessor):
        def __init__(self, processors: Mapping[str, AsyncProvider[MessageProcessor]]):
            self.processors = processors

        async def process_message(self) -> str:
            return await (await self.processors["command"]()).process_message()

    builder = ContainerBuilder()
    builder.register(
        MessageProcessor,
        CommandProcessor,
        name="command",
        contributes={delegated: "command"},
    )
    builder.register_provider_map(delegated, asynchronous=True)
    builder.register(MessageProcessor, DelegatingProcessor)

    container = builder.build()
    delegator = container.resolve(MessageProcessor)
    assert isinstance(delegator, DelegatingProcessor)
    assert list(delegator.processors) == ["command"]
    assert isinstance(container.resolve(MessageProcessor, cf.with_name("command")), CommandProcessor)


def test_provider_map_group_contributions_do_not_change_ordinary_resolution():
    class Service:
        pass

    group = ProviderMapGroup("services", str, Service)
    builder = ContainerBuilder()
    builder.register(Service, contributes={group: "default"})
    builder.register_provider_map(group)

    container = builder.build()
    assert isinstance(container.resolve(Service), Service)
    assert isinstance(container.resolve(Mapping[str, Provider[Service]])["default"](), Service)


def test_provider_map_group_duplicate_contribution_keys_fail():
    class Service:
        pass

    group = ProviderMapGroup("services", str, Service)
    builder = ContainerBuilder()
    builder.register(Service, name="first", contributes={group: "same"})
    builder.register(Service, name="second", contributes={group: "same"})
    builder.register_provider_map(group)

    with pytest.raises(ContainerBuildError) as error:
        builder.build()
    assert "provider-map-duplicate-key" in codes(error)


def test_provider_map_groups_are_identity_tokens_and_one_registration_can_contribute_to_many():
    class Service:
        pass

    first = ProviderMapGroup("same", str, Service)
    second = ProviderMapGroup("same", str, Service)
    builder = ContainerBuilder()
    builder.register(Service, contributes={first: "first", second: "second"})
    builder.register_provider_map(first, name="first")
    builder.register_provider_map(second, name="second")
    container = builder.build()

    first_map = container.resolve(Mapping[str, Provider[Service]], cf.with_name("first"))
    second_map = container.resolve(Mapping[str, Provider[Service]], cf.with_name("second"))
    assert list(first_map) == ["first"]
    assert list(second_map) == ["second"]


def test_provider_map_group_rejects_incompatible_contributions_transactionally():
    class Service:
        pass

    class Other:
        pass

    group = ProviderMapGroup("services", str, Service)
    builder = ContainerBuilder()
    with pytest.raises(TypeError, match="incompatible"):
        builder.register(Other, contributes={group: "wrong"})
    builder.register(Service, contributes={group: "right"})
    builder.register_provider_map(group)
    assert list(builder.build().resolve(Mapping[str, Provider[Service]])) == ["right"]


def test_provider_map_group_filters_before_component_filter_and_keeps_contributing_cycles():
    class Service:
        pass

    group = ProviderMapGroup("services", str, Service)
    calls = []
    builder = ContainerBuilder()
    builder.register(Service, name="excluded")
    builder.register(Service, name="included", contributes={group: "included"})
    builder.register_provider_map(group, component_filter=lambda component: calls.append(component.name) or True)
    assert list(builder.build().resolve(Mapping[str, Provider[Service]])) == ["included"]
    assert calls == ["included"]

    class Recursive:
        pass

    def recursive_factory(providers: Mapping[str, Provider[Recursive]]) -> Recursive:
        return Recursive()

    recursive_group = ProviderMapGroup("recursive", str, Recursive)
    recursive = ContainerBuilder()
    recursive.register(Recursive, factory=recursive_factory, contributes={recursive_group: "recursive"})
    recursive.register_provider_map(recursive_group)
    with pytest.raises(ContainerBuildError) as error:
        recursive.build()
    assert "circular-dependency" in codes(error)


def test_named_ordered_read_only_map_is_lazy_and_compilation_stays_frozen(monkeypatch):
    events = []
    seen = []

    class Service:
        def __init__(self, label: str):
            events.append(label)
            self.label = label

    class Consumer:
        def __init__(self, services: Mapping[str, Provider[Service]]):
            self.services = services

    def key(component):
        assert component.parent.kind is ComponentKind.provider
        seen.append(component.occurrence_id)
        return component.name

    builder = ContainerBuilder()
    builder.register(Service, name="first", arguments={"label": "first"})
    builder.register(Service, name="second", arguments={"label": "second"})
    builder.register_provider_map(Service, key=key)
    builder.register(Consumer)
    container = builder.build()
    count = len(seen)
    assert len(seen) == len(set(seen))

    def forbidden(*args, **kwargs):
        pytest.fail("runtime attempted compilation or discovery")

    import clean_ioc.container as runtime

    monkeypatch.setattr(runtime._Compiler, "_compile_candidates", forbidden)
    monkeypatch.setattr(runtime._Compiler, "_compile_registration", forbidden)
    monkeypatch.setattr(runtime._Blueprint, "registrations", forbidden)
    services = container.resolve(Consumer).services
    assert list(services) == ["second", "first"]
    assert len(services.values()) == 2
    assert not events
    with pytest.raises(TypeError):
        services["third"] = services["first"]  # ty: ignore[invalid-assignment]
    with pytest.raises(KeyError):
        services["missing"]
    assert services["second"]().label == "second"
    assert events == ["second"]
    assert len(seen) == count


def test_empty_non_string_and_typing_mapping_keys():
    class Service:
        pass

    for annotation in (Mapping[int, Provider[Service]], TypingMapping[int, Provider[Service]]):
        builder = ContainerBuilder()
        builder.register_provider_map(Service, key=lambda component: 7, key_type=int)
        with builder.build() as container:
            assert dict(container.resolve(annotation)) == {}
    builder = ContainerBuilder()
    builder.register(Service)
    builder.register_provider_map(Service, key=lambda component: (1, "x"), key_type=tuple[int, str])
    result = builder.build().resolve(TypingMapping[tuple[int, str], Provider[Service]])
    assert isinstance(result[(1, "x")](), Service)


def test_multiple_maps_select_map_definitions_and_filter_entries_independently():
    class Service:
        pass

    class Consumer:
        def __init__(self, values: TypingMapping[str, Provider[Service]]):
            self.values = values

    builder = ContainerBuilder()
    builder.register(Service, name="a")
    builder.register(Service, name="b")
    builder.register_provider_map(Service, key=lambda c: c.name, name="all")
    builder.register_provider_map(Service, key=lambda c: c.name, component_filter=cf.with_name("b"), name="b-only")
    builder.register(Consumer, arguments={"values": select(cf.with_name("b-only"))})
    container = builder.build()
    assert list(container.resolve(Consumer).values) == ["b"]
    assert list(container.resolve(Mapping[str, Provider[Service]], cf.with_name("all"))) == ["b", "a"]
    assert len(container.resolve(list[Service])) == 0


@pytest.mark.parametrize("lifespan", ["transient", "per_resolution", "scoped", "singleton"])
def test_lifespans_and_scope_bound_handles(lifespan):
    class Service:
        pass

    builder = ContainerBuilder()
    builder.register(Service, lifespan=lifespan)
    builder.register_provider_map(Service, key=lambda c: "service")
    with builder.build() as container:
        with container.new_scope() as scope:
            provider = scope.resolve(Mapping[str, Provider[Service]])["service"]
            first, second = provider(), provider()
            assert (first is second) == (lifespan in ("scoped", "singleton"))
            with scope.new_scope() as nested:
                nested_provider = nested.resolve(Mapping[str, Provider[Service]])["service"]
                assert (nested_provider() is first) == (lifespan in ("scoped", "singleton"))
        with pytest.raises(ProviderScopeClosedError):
            provider()


def test_each_call_starts_a_fresh_resolution_context():
    class Leaf:
        pass

    class Pair:
        def __init__(self, left: Leaf, right: Leaf):
            self.left, self.right = left, right

    builder = ContainerBuilder()
    builder.register(Leaf)
    builder.register(Pair)
    builder.register_provider_map(Pair, key=lambda c: "pair")
    provider = builder.build().resolve(Mapping[str, Provider[Pair]])["pair"]
    first, second = provider(), provider()
    assert first.left is first.right
    assert second.left is second.right
    assert first.left is not second.left


def test_sync_resources_cleanup_once_for_invoked_entries_only():
    class Resource:
        pass

    events = []

    @contextmanager
    def factory(label: str):
        events.append(f"open:{label}")
        yield Resource()
        events.append(f"close:{label}")

    builder = ContainerBuilder()
    for label in ("a", "b"):
        builder.register(Resource, factory=factory, arguments={"label": label}, name=label, lifespan="scoped")
    builder.register_provider_map(Resource, key=lambda c: c.name)
    with builder.build() as container:
        with container.new_scope() as scope:
            values = scope.resolve(Mapping[str, Provider[Resource]])
            assert not events
            assert values["a"]() is values["a"]()
        assert events == ["open:a", "close:a"]


@pytest.mark.asyncio
async def test_async_map_injection_root_resolution_and_resources():
    class Resource:
        pass

    class Consumer:
        def __init__(self, values: Mapping[str, AsyncProvider[Resource]]):
            self.values = values

    events = []

    @asynccontextmanager
    async def factory():
        events.append("open")
        yield Resource()
        events.append("close")

    builder = ContainerBuilder()
    builder.register(Resource, factory=factory, lifespan="scoped")
    builder.register_provider_map(Resource, key=lambda c: "r", asynchronous=True)
    builder.register(Consumer)
    async with builder.build() as container:
        async with container.new_scope() as scope:
            values = scope.resolve(Consumer).values
            root = await scope.resolve_async(TypingMapping[str, AsyncProvider[Resource]])
            assert not events
            assert await values["r"]() is await root["r"]()
        assert events == ["open", "close"]
        with pytest.raises(ProviderScopeClosedError):
            await values["r"]()


def test_sync_map_rejects_async_target():
    class Service:
        pass

    async def factory():
        return Service()

    builder = ContainerBuilder()
    builder.register(Service, factory=factory)
    builder.register_provider_map(Service, key=lambda c: "service")
    with pytest.raises(ContainerBuildError) as caught:
        builder.build()
    assert "provider-requires-async" in codes(caught)


@pytest.mark.parametrize("edge", ["scoped", "slot", "scope", "context"])
def test_singleton_capture_rejects_scope_state_transitively(edge):
    class Scoped:
        pass

    dependency = Scope if edge == "scope" else ResolutionContext if edge == "context" else Scoped

    class Service:
        def __init__(self, value: dependency):
            self.value = value

    class Consumer:
        def __init__(self, values: Mapping[str, Provider[Service]]):
            self.values = values

    builder = ContainerBuilder()
    if edge == "slot":
        builder.declare_scope_slot(Scoped)
    elif edge == "scoped":
        builder.register(Scoped, lifespan="scoped")
    builder.register(Service, lifespan="transient")
    builder.register_provider_map(Service, key=lambda c: "s")
    builder.register(Consumer, lifespan="singleton")
    with pytest.raises(ContainerBuildError) as caught:
        builder.build()
    assert "provider-captive-scope" in codes(caught)


def test_singleton_handles_bind_owner_and_overlay_maps_use_new_targets():
    class Service:
        pass

    class Original(Service):
        pass

    class Replacement(Service):
        pass

    class Consumer:
        def __init__(self, values: Mapping[str, Provider[Service]]):
            self.values = values

    builder = ContainerBuilder()
    builder.register(Service, Original, name="a", lifespan="transient")
    builder.register_provider_map(Service, key=lambda c: c.name)
    builder.register(Consumer, lifespan="singleton")
    with builder.build() as container:
        overlay_builder = container.new_scope_builder()
        overlay_builder.register(Service, Replacement, name="b", lifespan="transient")
        with overlay_builder.build() as overlay:
            with overlay.new_scope() as nested:
                consumer = nested.resolve(Consumer)
                assert list(consumer.values) == ["a"]
                assert isinstance(consumer.values["a"](), Original)
                assert list(nested.resolve(Mapping[str, Provider[Service]])) == ["b", "a"]
        assert isinstance(consumer.values["a"](), Original)
    with pytest.raises(ProviderScopeClosedError):
        consumer.values["a"]()


def test_slots_are_supplied_only_when_provider_is_called():
    class Request:
        pass

    class Service:
        def __init__(self, request: Request):
            self.request = request

    builder = ContainerBuilder()
    builder.declare_scope_slot(Request)
    builder.register(Service)
    builder.register_provider_map(Service, key=lambda c: "s")
    with builder.build() as container:
        with container.new_scope() as scope:
            request = Request()
            scope.provide(Request, request)
            assert scope.resolve(Mapping[str, Provider[Service]])["s"]().request is request


@pytest.mark.parametrize(
    "failure", ["duplicate", "unhashable", "callback", "hash", "equality", "async", "async-result", "invalid"]
)
def test_key_failures_are_structured_redacted_and_repairable(failure):
    secret = "private-value-do-not-leak"  # noqa: S105

    class Service:
        pass

    class BrokenHash:
        def __hash__(self):
            raise ValueError(secret)

    class BrokenEquality:
        def __hash__(self):
            return 0

        def __eq__(self, other):
            raise ValueError(secret)

    async def async_key(c):
        return secret

    repaired = False

    def key(c):
        if repaired:
            return c.name
        if failure == "callback":
            raise ValueError(secret)
        if failure == "hash":
            return BrokenHash()
        if failure == "equality":
            return BrokenEquality()
        if failure == "unhashable":
            return [secret]
        if failure == "async-result":
            return async_key(c)
        return secret

    builder = ContainerBuilder()
    builder.register(Service, name="a")
    builder.register(Service, name="b")
    callback: Any = async_key if failure == "async" else "name" if failure == "invalid" else key
    builder.register_provider_map(Service, key=callback)
    with pytest.raises(ContainerBuildError) as caught:
        builder.build()
    expected = {
        "duplicate": "provider-map-duplicate-key",
        "unhashable": "provider-map-unhashable-key",
        "async": "provider-map-invalid-key",
        "async-result": "provider-map-invalid-key",
        "invalid": "provider-map-invalid-key",
    }.get(failure, "provider-map-key-evaluation")
    assert expected in codes(caught)
    assert secret not in str(caught.value)
    assert caught.value.report is not None
    assert secret not in str(caught.value.report.to_dict())
    if failure not in ("async", "invalid"):
        repaired = True
        assert list(builder.build().resolve(Mapping[str, Provider[Service]])) == ["b", "a"]


def test_key_hashing_happens_only_in_build_and_lookup_not_map_acquisition():
    class Key:
        calls = 0

        def __hash__(self):
            Key.calls += 1
            return 42

    class Service:
        pass

    key = Key()
    builder = ContainerBuilder()
    builder.register(Service)
    builder.register_provider_map(Service, key=lambda c: key, key_type=Key)
    container = builder.build()
    count = Key.calls
    values = container.resolve(Mapping[Key, Provider[Service]])
    assert list(values) == [key]
    assert Key.calls == count
    assert isinstance(values[key](), Service)
    assert Key.calls == count + 1


def test_target_decorators_generics_unions_newtypes_and_aliases():
    item = TypeVar("item")

    class Service(Generic[item]):
        pass

    class Wrapper(Service[item], Generic[item]):
        def __init__(self, child: Service[item]):
            self.child = child

    service_alias = TypeAliasType("service_alias", Service[int])
    key_alias = TypeAliasType("key_alias", int)
    provider_alias = TypeAliasType("provider_alias", Provider[service_alias])
    map_alias = TypeAliasType("map_alias", TypingMapping[key_alias, provider_alias])

    class Consumer:
        def __init__(self, values: map_alias):
            self.values = values

    builder = ContainerBuilder()
    builder.register(service_alias)
    builder.register_decorator(Service, Wrapper)
    builder.register_provider_map(service_alias, key=lambda c: 1, key_type=key_alias)
    builder.register(Consumer)
    container = builder.build()
    assert isinstance(container.resolve(Consumer).values[1](), Wrapper)
    wrapped = container.resolve(map_alias)[1]()
    assert isinstance(wrapped, Wrapper)
    assert isinstance(wrapped.child, Service)
    nominal = NewType("nominal", int)
    union = int | str
    for target, value in ((nominal, nominal(7)), (union, "seven")):
        builder = ContainerBuilder()
        builder.register(target, instance=value)
        builder.register_provider_map(target, key=lambda c: "value")
        assert builder.build().resolve(Mapping[str, Provider[target]])["value"]() == value


@pytest.mark.skipif(sys.version_info < (3, 12), reason="native type aliases require Python 3.12")
def test_native_aliases_nested_around_provider_maps():
    namespace = {"ContainerBuilder": ContainerBuilder, "Mapping": Mapping, "Provider": Provider}
    exec("class Service: pass\ntype Key = int\ntype P = Provider[Service]\ntype M = Mapping[Key, P]\n", namespace)  # noqa: S102
    builder = ContainerBuilder()
    builder.register(namespace["Service"])
    builder.register_provider_map(namespace["Service"], key=lambda c: 3, key_type=namespace["Key"])
    assert isinstance(builder.build().resolve(namespace["M"])[3](), namespace["Service"])


def test_boundary_map_visibility_exports_and_bundle_protocol():
    class Service:
        pass

    def area_a(builder):
        builder.register(Service, name="a")
        builder.register_provider_map(Service, key=lambda c: c.name)

    def area_b(builder):
        builder.register(Service, name="b")

    map_type = Mapping[str, Provider[Service]]
    builder = ContainerBuilder()
    builder.install_boundary(Boundary("a", area_a, exposes=(Expose(map_type),)))
    builder.install_boundary(Boundary("b", area_b))
    container = builder.build()
    assert list(container.resolve(map_type)) == ["a"]
    assert isinstance(container.resolve(map_type)["a"](), Service)
    assert not container.has_component(Service)


def test_uncalled_missing_target_and_recursive_maps_fail_build():
    class Missing:
        pass

    class Service:
        def __init__(self, missing: Missing):
            self.missing = missing

    builder = ContainerBuilder()
    builder.register(Service)
    builder.register_provider_map(Service, key=lambda c: "s")
    with pytest.raises(ContainerBuildError):
        builder.build()
    builder.register(Missing)
    assert isinstance(builder.build().resolve(Mapping[str, Provider[Service]])["s"](), Service)

    class Recursive:
        pass

    def factory(values: Mapping[str, Provider[Recursive]]):
        return Recursive()

    builder = ContainerBuilder()
    builder.register(Recursive, factory=factory)
    builder.register_provider_map(Recursive, key=lambda c: "recursive")
    with pytest.raises(ContainerBuildError) as caught:
        builder.build()
    assert "circular-dependency" in codes(caught)


def test_graph_explain_fingerprints_are_deterministic_and_keys_redacted():
    class Service:
        pass

    def build(secret):
        builder = ContainerBuilder()
        builder.register(Service, name="a")
        builder.register(Service, name="b")
        builder.register_provider_map(Service, key=lambda c: secret + c.name)
        return builder.build()

    first, second = build("private-one"), build("private-two")
    assert first.graph.manifest().fingerprint == second.graph.manifest().fingerprint
    payload = json.dumps(first.graph.manifest().data)
    assert "private-one" not in payload
    assert '"provider_map"' in payload
    assert '"key_type": "str"' in payload
    map_root = next(
        visit.component for visit in first.graph.walk() if visit.component.kind is ComponentKind.provider_map
    )
    assert len(map_root.dependencies) == 2
    assert all(entry.kind is ComponentKind.provider for entry in map_root.dependencies)
    assert [entry.dependencies[0].name for entry in map_root.dependencies] == ["b", "a"]
    assert len(first.graph.explain(map_root).selected) == 2
    assert "private-one" not in first.graph.explain(map_root).to_json()
    assert "provides on demand" in first.graph.to_text()


def test_dictionary_equality_collisions_and_nested_unhashable_keys():
    class Service:
        pass

    for key, expected in (
        (lambda c: 1 if c.name == "a" else True, "provider-map-duplicate-key"),
        (lambda c: ([],), "provider-map-unhashable-key"),
    ):
        builder = ContainerBuilder()
        builder.register(Service, name="a")
        builder.register(Service, name="b")
        builder.register_provider_map(Service, key=key)
        with pytest.raises(ContainerBuildError) as caught:
            builder.build()
        assert expected in codes(caught)


def test_async_callable_objects_and_async_generator_results_are_rejected():
    class Service:
        pass

    class AsyncKey:
        async def __call__(self, component):
            return "async"

    async def generator():
        yield "async"

    for key in (AsyncKey(), lambda c: generator()):
        builder = ContainerBuilder()
        builder.register(Service)
        builder.register_provider_map(Service, key=key)
        with pytest.raises(ContainerBuildError) as caught:
            builder.build()
        assert "provider-map-invalid-key" in codes(caught)


def test_provider_maps_require_closed_declarations_and_cannot_be_patched_to_cached_lifespans():
    parameter = TypeVar("parameter")

    class Service(Generic[parameter]):
        pass

    for target, key_type in ((Service, str), (Service[int], parameter)):
        builder = ContainerBuilder()
        builder.register_provider_map(target, key=lambda c: "s", key_type=key_type)
        with pytest.raises(ContainerBuildError) as caught:
            builder.build()
        assert "provider-map-invalid-declaration" in codes(caught)
    builder = ContainerBuilder()
    map_id = builder.register_provider_map(Service[int], key=lambda c: "s")
    builder.patch_component(Mapping[str, Provider[Service[int]]], map_id, lifespan="singleton")
    with pytest.raises(ContainerBuildError) as caught:
        builder.build()
    assert "provider-map-invalid-declaration" in codes(caught)
    builder.patch_component(Mapping[str, Provider[Service[int]]], map_id, lifespan="transient")
    assert not builder.build().resolve(Mapping[str, Provider[Service[int]]])


def test_safe_singleton_capture_owns_deferred_transient_resources():
    class Resource:
        pass

    class Consumer:
        def __init__(self, values: Mapping[str, Provider[Resource]]):
            self.values = values

    events = []

    @contextmanager
    def factory():
        events.append("open")
        yield Resource()
        events.append("close")

    builder = ContainerBuilder()
    builder.register(Resource, factory=factory, lifespan="transient")
    builder.register_provider_map(Resource, key=lambda c: "resource")
    builder.register(Consumer, lifespan="singleton")
    with builder.build() as container:
        with container.new_scope() as scope:
            consumer = scope.resolve(Consumer)
            consumer.values["resource"]()
        assert events == ["open"]
    assert events == ["open", "close"]


def test_scope_builder_declarations_and_boundary_use_of_an_exposed_map():
    class Service:
        pass

    class Consumer:
        def __init__(self, values: Mapping[str, Provider[Service]]):
            self.values = values

    map_type = Mapping[str, Provider[Service]]

    def source(builder):
        builder.register(Service, name="private")
        builder.register_provider_map(Service, key=lambda c: c.name)

    def destination(builder):
        builder.register(Consumer)

    builder = ContainerBuilder()
    builder.install_boundary(Boundary("source", source, exposes=(Expose(map_type),)))
    builder.install_boundary(
        Boundary("destination", destination, uses=(Use("source", map_type),), exposes=(Expose(Consumer),))
    )
    with builder.build() as container:
        assert list(container.resolve(Consumer).values) == ["private"]
        overlay_builder = container.new_scope_builder()
        overlay_builder.register(Service, name="local")
        overlay_builder.register_provider_map(Service, key=lambda c: c.name, name="overlay")
        with overlay_builder.build() as overlay:
            assert list(overlay.resolve(map_type, cf.with_name("overlay"))) == ["local"]
            assert list(overlay.resolve(Consumer).values) == ["private"]


def test_group_provider_maps_see_overlay_contributions_but_anchored_singletons_stay_frozen():
    class Service:
        pass

    class Consumer:
        def __init__(self, values: Mapping[str, Provider[Service]]):
            self.values = values

    group = ProviderMapGroup("services", str, Service)
    map_type = Mapping[str, Provider[Service]]
    builder = ContainerBuilder()
    builder.register(Service, name="parent", contributes={group: "parent"})
    builder.register_provider_map(group)
    builder.register(Consumer, lifespan="singleton")
    with builder.build() as container:
        parent_consumer = container.resolve(Consumer)
        assert list(parent_consumer.values) == ["parent"]
        overlay_builder = container.new_scope_builder()
        overlay_builder.register(Service, name="overlay", contributes={group: "overlay"})
        overlay_builder.register_provider_map(group, name="overlay-map")
        with overlay_builder.build() as overlay:
            overlay_map = overlay.resolve(map_type, cf.with_name("overlay-map"))
            assert list(overlay_map) == ["overlay", "parent"]
            assert list(overlay.resolve(Consumer).values) == ["parent"]


def test_provider_map_group_key_failures_are_structured_and_redacted():
    class Service:
        pass

    secret = "group-key-secret"  # noqa: S105

    class BrokenKey:
        def __hash__(self):
            raise RuntimeError(secret)

    group = ProviderMapGroup("services", str, Service)
    builder = ContainerBuilder()
    builder.register(Service, contributes={group: BrokenKey()})
    builder.register_provider_map(group)
    with pytest.raises(ContainerBuildError) as error:
        builder.build()
    assert "provider-map-key-evaluation" in codes(error)
    assert secret not in str(error.value)
    assert error.value.report is not None
    assert secret not in json.dumps(error.value.report.to_dict())


def test_newtype_key_identity_is_not_its_supertype():
    class Service:
        pass

    key_type = NewType("key_type", int)
    builder = ContainerBuilder()
    builder.register(Service)
    builder.register_provider_map(Service, key=lambda c: key_type(1), key_type=key_type)
    container = builder.build()
    assert container.has_component(Mapping[key_type, Provider[Service]])
    assert not container.has_component(Mapping[int, Provider[Service]])
    assert isinstance(container.resolve(Mapping[key_type, Provider[Service]])[key_type(1)](), Service)


def test_callback_inspection_and_invalid_coroutine_cleanup_cannot_leak_errors():
    class Service:
        pass

    class BrokenCallback:
        def __getattribute__(self, name):
            raise ValueError("private-inspection-value")

        def __call__(self, component):
            return "key"

    async def coroutine():
        try:
            await asyncio.sleep(0)
        finally:
            raise ValueError("private-cleanup-value")

    def key(component):
        result = coroutine()
        result.send(None)
        return result

    for callback in (BrokenCallback(), key):
        builder = ContainerBuilder()
        builder.register(Service)
        builder.register_provider_map(Service, key=callback)
        with pytest.raises(ContainerBuildError) as caught:
            builder.build()
        assert "provider-map-invalid-key" in codes(caught)
        assert "private-" not in str(caught.value)
