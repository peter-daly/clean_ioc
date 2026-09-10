"""Canonical runtime keys must not pay for alias expansion on every lookup."""

import sys
import types
from collections.abc import Iterator
from typing import Generic, NewType, TypeVar

import pytest
from typing_extensions import TypeAliasType

import clean_ioc.container as runtime
import clean_ioc.type_aliases as aliases
from clean_ioc import (
    AsyncProvider,
    CannotResolveError,
    Container,
    ContainerBuilder,
    Provider,
    ScopeClosedError,
    ScopeProvisionError,
)
from clean_ioc import component_filters as cf
from clean_ioc.factories import use_component, use_component_async

T = TypeVar("T")


class Service:
    pass


class Alternative:
    pass


class Repository(Generic[T]):
    pass


class Request(Generic[T]):
    pass


ServiceId = NewType("ServiceId", str)
RepoAlias = TypeAliasType("RepoAlias", Repository[int])
RequestAlias = TypeAliasType("RequestAlias", Request[int])


def forbid_normalization(value):
    pytest.fail("A known canonical runtime key reached alias normalization")


@pytest.fixture
def lookup_container() -> Iterator[Container]:
    builder = ContainerBuilder()
    builder.register(Service, lifespan="singleton")
    builder.register(Service, name="named", lifespan="singleton")
    builder.register(Repository[int], lifespan="singleton")
    builder.register(Service | Alternative, instance=Service())
    builder.register(ServiceId, instance=ServiceId("service"))
    builder.declare_scope_slot(Request[int])
    builder.declare_scope_slot(Request[int], name="named")
    container = builder.build()
    with container:
        yield container


def test_plain_class_normalization_does_not_inspect_aliases(monkeypatch):
    monkeypatch.setattr(aliases, "_contains_alias", forbid_normalization)
    assert aliases.normalize_type_alias(Service) is Service
    assert aliases.normalize_type_alias(str) is str


@pytest.mark.parametrize("key", [Service, Repository[int], Service | Alternative, ServiceId])
async def test_known_keys_bypass_normalization_in_sync_async_and_metadata_lookups(lookup_container, monkeypatch, key):
    expected = lookup_container.resolve(key)
    monkeypatch.setattr(runtime, "normalize_type_alias", forbid_normalization)

    assert lookup_container.resolve(key) is expected
    assert await lookup_container.resolve_async(key) is expected
    assert lookup_container.has_component(key)
    assert lookup_container.resolve(key, cf.with_name(None)) is expected
    assert await lookup_container.resolve_async(key, cf.with_name(None)) is expected


async def test_provider_and_collection_keys_bypass_normalization(lookup_container, monkeypatch):
    expected = lookup_container.resolve(Service)
    named_filter = cf.with_name("named")
    named = lookup_container.resolve(Service, named_filter)
    monkeypatch.setattr(runtime, "normalize_type_alias", forbid_normalization)

    assert lookup_container.resolve(Provider[Service])() is expected
    assert await lookup_container.resolve(AsyncProvider[Service])() is expected
    assert (await lookup_container.resolve_async(Provider[Service]))() is expected
    assert await (await lookup_container.resolve_async(AsyncProvider[Service]))() is expected
    assert lookup_container.resolve(Provider[Service], named_filter)() is named
    assert lookup_container.has_component(Provider[Service], named_filter)
    assert lookup_container.resolve(list[Service]) == [expected]
    assert await lookup_container.resolve_async(list[Service]) == [expected]
    assert lookup_container.resolve(list[Service], named_filter) == [named]
    assert await lookup_container.resolve_async(list[Service], named_filter) == [named]


def test_filter_rejection_does_not_trigger_normalization_or_retry(lookup_container, monkeypatch):
    seen = []

    def reject(component):
        seen.append(component.id)
        return False

    monkeypatch.setattr(runtime, "normalize_type_alias", forbid_normalization)
    with pytest.raises(CannotResolveError):
        lookup_container.resolve(Repository[int], reject)
    assert len(seen) == 1
    assert not lookup_container.has_component(Repository[int], reject)
    assert len(seen) == 2
    assert lookup_container.resolve(list[Repository[int]], reject) == []
    assert len(seen) == 3


def test_known_named_only_key_keeps_default_selection_empty(monkeypatch):
    builder = ContainerBuilder()
    builder.register(Repository[int], name="only")
    with builder.build() as container:
        monkeypatch.setattr(runtime, "normalize_type_alias", forbid_normalization)
        assert not container.has_component(Repository[int])
        assert container.resolve(list[Repository[int]]) == []
        with pytest.raises(CannotResolveError):
            container.resolve(Repository[int])
        with pytest.raises(CannotResolveError):
            container.resolve(Provider[Repository[int]])


def test_compiled_slot_keys_bypass_normalization_and_keep_provision_rules(lookup_container, monkeypatch):
    request = Request[int]()
    monkeypatch.setattr(runtime, "normalize_type_alias", forbid_normalization)
    with lookup_container.new_scope() as scope:
        assert scope.has_scope_slot(Request[int])
        assert scope.has_scope_slot(Request[int], "named")
        assert not scope.has_provision(Request[int])
        scope.provide(Request[int], request)
        scope.provide(Request[int], request, "named")
        assert scope.has_provision(Request[int], "named")
        with pytest.raises(ScopeProvisionError):
            scope.provide(Request[int], request)
        with scope.new_scope() as child:
            assert child.has_provision(Request[int])
            assert child.has_provision(Request[int], "named")
        assert scope.resolve(list[Request[int]]) == []
    with pytest.raises(ScopeClosedError):
        scope.provide(Request[int], request)


@pytest.mark.parametrize("asynchronous", [False, True])
async def test_declared_context_requests_use_compiled_keys(monkeypatch, asynchronous):
    factory = use_component_async(Repository[int]) if asynchronous else use_component(Repository[int])
    builder = ContainerBuilder()
    builder.register(Repository[int], lifespan="singleton")
    builder.register(object, factory=factory)
    with builder.build() as container:
        expected = container.resolve(Repository[int])
        monkeypatch.setattr(runtime, "normalize_type_alias", forbid_normalization)
        if asynchronous:
            assert await container.resolve_async(object) is expected
        else:
            assert container.resolve(object) is expected


async def test_unknown_alias_spellings_still_resolve_without_runtime_compilation(lookup_container, monkeypatch):
    expected = lookup_container.resolve(Repository[int])
    calls = []

    def normalize(value):
        calls.append(value)
        return aliases.normalize_type_alias(value)

    def forbid_compilation(*args, **kwargs):
        pytest.fail("Alias lookup must execute frozen plans, not compile new ones")

    monkeypatch.setattr(runtime, "normalize_type_alias", normalize)
    monkeypatch.setattr(runtime, "_compile_with_report", forbid_compilation)
    assert lookup_container.resolve(RepoAlias) is expected
    assert calls == [RepoAlias]
    assert await lookup_container.resolve_async(RepoAlias) is expected
    assert lookup_container.has_component(RepoAlias)
    assert lookup_container.resolve(list[RepoAlias]) == [expected]
    assert await lookup_container.resolve_async(list[RepoAlias]) == [expected]
    assert lookup_container.resolve(Provider[RepoAlias])() is expected
    assert await lookup_container.resolve(AsyncProvider[RepoAlias])() is expected
    with lookup_container.new_scope() as scope:
        request = Request[int]()
        scope.provide(RequestAlias, request)
        assert scope.has_scope_slot(RequestAlias)
        assert scope.has_provision(RequestAlias)
        with scope.new_scope() as child:
            assert child.has_provision(RequestAlias)


def test_rejected_alias_request_does_not_retry_the_filter(lookup_container):
    seen = []

    def reject(component):
        seen.append(component.id)
        return False

    with pytest.raises(CannotResolveError):
        lookup_container.resolve(RepoAlias, reject)
    assert len(seen) == 1


def test_runtime_alias_failures_can_be_repaired_without_locking_scope_provisions(lookup_container, monkeypatch):
    module = types.ModuleType("runtime_alias_repair_fixture")
    monkeypatch.setitem(sys.modules, module.__name__, module)
    exec(  # noqa: S102 - isolated namespace exercises unresolved alias evaluation
        "from typing_extensions import TypeAliasType\nLate = TypeAliasType('Late', 'Service')",
        module.__dict__,
    )
    with lookup_container.new_scope() as scope:
        with pytest.raises(aliases.TypeAliasNormalizationError):
            scope.resolve(module.Late)
        scope.provide(Request[int], Request[int]())
        module.__dict__["Service"] = Repository[int]
        assert scope.resolve(module.Late) is lookup_container.resolve(Repository[int])


def test_overlay_alias_lookup_keeps_the_overlays_own_plan(lookup_container):
    parent_value = lookup_container.resolve(Repository[int])
    builder = lookup_container.new_scope_builder()
    replacement = Repository[int]()
    builder.register(Repository[int], instance=replacement)
    with builder.build() as overlay:
        assert overlay.resolve(RepoAlias) is replacement
        assert lookup_container.resolve(RepoAlias) is parent_value
