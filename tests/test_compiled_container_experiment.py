import asyncio
import threading
from collections.abc import Generator
from concurrent.futures import ThreadPoolExecutor
from typing import Any
from unittest.mock import Mock

import pytest

from clean_ioc import (
    CaptiveDependencyError,
    ContainerValidationError,
    DependencyContext,
    DependencySettings,
    Lifespan,
    Registrator,
    Resolver,
    Scope,
    ScopeCreator,
)
from clean_ioc.value_factories import dont_use_default_value
from experiments.compiled_container import (
    CompiledChildScope,
    CompiledContainer,
    SealedContainerError,
)


class Leaf:
    pass


class Pair:
    def __init__(self, first: Leaf, second: Leaf):
        self.first = first
        self.second = second


def test_seal_validates_and_compiles_without_running_user_code():
    calls = 0

    def build_leaf() -> Leaf:
        nonlocal calls
        calls += 1
        return Leaf()

    container = CompiledContainer()
    container.register(Leaf, factory=build_leaf)
    container.register(Pair)

    report = container.seal()

    assert report.validation.is_valid
    assert report.candidate_roots >= 2
    assert report.sync_compiled_roots == report.async_compiled_roots
    assert report.fallback_roots == 0
    assert calls == 0

    pair = container.resolve(Pair)
    assert calls == 1
    assert pair.first is pair.second


def test_seal_rejects_an_invalid_graph_before_running_factories():
    class Missing:
        pass

    class Broken:
        def __init__(self, missing: Missing):
            self.missing = missing

    container = CompiledContainer()
    container.register(Broken)

    with pytest.raises(ContainerValidationError):
        container.seal()

    assert not container.is_sealed


def test_root_composition_is_immutable_after_seal():
    class DecoratedLeaf(Leaf):
        def __init__(self, child: Leaf):
            self.child = child

    container = CompiledContainer()
    registration_id = container.register(Leaf)
    container.seal()

    with pytest.raises(SealedContainerError):
        container.register(Pair)
    with pytest.raises(SealedContainerError):
        container.patch_registration(Leaf, registration_id, lifespan=Lifespan.singleton)
    with pytest.raises(SealedContainerError):
        container.pre_configure(Leaf, lambda: None)
    with pytest.raises(SealedContainerError):
        container.register_decorator(Leaf, DecoratedLeaf, decorated_arg="child")


@pytest.mark.parametrize(
    ("lifespan", "same_within_graph", "same_across_graphs"),
    [
        (Lifespan.transient, False, False),
        (Lifespan.once_per_graph, True, False),
        (Lifespan.scoped, True, True),
        (Lifespan.singleton, True, True),
    ],
)
def test_compiled_resolution_preserves_lifespans(
    lifespan: Lifespan,
    same_within_graph: bool,
    same_across_graphs: bool,
):
    container = CompiledContainer()
    container.register(Leaf, lifespan=lifespan)
    container.register(Pair)
    container.seal()

    with container.new_scope() as scope:
        first = scope.resolve(Pair)
        second = scope.resolve(Pair)
        assert (first.first is first.second) is same_within_graph
        assert (first.first is second.first) is same_across_graphs

    if lifespan in (Lifespan.scoped, Lifespan.singleton):
        with container.new_scope() as other_scope:
            third = other_scope.resolve(Pair)
        assert (first.first is third.first) is (lifespan is Lifespan.singleton)


def test_compiled_resolution_preserves_collections_defaults_context_preconfiguration_and_decorators():
    class Plugin:
        pass

    class FirstPlugin(Plugin):
        pass

    class SecondPlugin(Plugin):
        pass

    class Config:
        pass

    class Service:
        def __init__(
            self,
            plugins: list[Plugin],
            context: DependencyContext,
            label: str = "default-label",
        ):
            self.plugins = plugins
            self.context = context
            self.label = label

    class DecoratedService:
        def __init__(self, child: Service, config: Config):
            self.child = child
            self.config = config

    configured: list[Config] = []

    def configure(config: Config) -> None:
        configured.append(config)

    container = CompiledContainer()
    container.register(Plugin, FirstPlugin)
    container.register(Plugin, SecondPlugin)
    container.register(Config, lifespan=Lifespan.singleton)
    container.register(Service)
    container.pre_configure(Service, configure)
    container.register_decorator(Service, DecoratedService, decorated_arg="child")
    container.seal()

    result: Any = container.resolve(Service)
    again: Any = container.resolve(Service)

    assert [type(plugin) for plugin in result.child.plugins] == [SecondPlugin, FirstPlugin]
    assert result.child.context.name == "context"
    assert result.child.label == "default-label"
    assert result.config is configured[0]
    assert again.config is result.config
    assert configured == [result.config]


def test_scope_self_dependencies_refer_to_the_compiled_child_scope():
    class UsesScope:
        def __init__(
            self,
            scope: Scope,
            resolver: Resolver,
            registrator: Registrator,
            scope_creator: ScopeCreator,
        ):
            self.values = (scope, resolver, registrator, scope_creator)

    container = CompiledContainer()
    container.register(UsesScope)
    container.seal()

    with container.new_scope() as scope:
        result = scope.resolve(UsesScope)

    assert all(value is scope for value in result.values)


def test_compiled_singleton_cannot_capture_a_child_scope():
    class UsesScope:
        def __init__(self, scope: Scope):
            self.scope = scope

    container = CompiledContainer()
    container.register(UsesScope, lifespan=Lifespan.singleton)
    container.seal()

    with container.new_scope() as scope:
        with pytest.raises(CaptiveDependencyError):
            scope.resolve(UsesScope)


def test_declared_child_scope_slot_keeps_the_compiled_plan_eligible():
    class RequestValue:
        pass

    class Handler:
        def __init__(self, request_value: RequestValue):
            self.request_value = request_value

    request_value = RequestValue()
    container = CompiledContainer()
    container.expect_to_be_scoped(RequestValue)
    container.register(Handler)
    container.seal()

    with container.new_scope() as scope:
        assert isinstance(scope, CompiledChildScope)
        scope.register(RequestValue, instance=request_value)
        assert scope._compiled_eligible
        assert Handler in container._compiled_roots
        result = scope.resolve(Handler)

    assert result.request_value is request_value


def test_undeclared_child_overlay_falls_back_to_the_existing_resolver():
    class Value:
        pass

    class RootValue(Value):
        pass

    class ChildValue(Value):
        pass

    class Handler:
        def __init__(self, value: Value):
            self.value = value

    container = CompiledContainer()
    container.register(Value, RootValue)
    container.register(Handler)
    container.seal()

    with container.new_scope() as scope:
        scope.register(Value, ChildValue)
        assert isinstance(scope, CompiledChildScope)
        assert not scope._compiled_eligible
        result = scope.resolve(Handler)

    assert isinstance(result.value, ChildValue)


def test_unsupported_custom_value_provider_is_reported_and_transparently_falls_back():
    class Supplied:
        pass

    supplied = Supplied()

    def supply_value(default: Any, context: DependencyContext) -> Supplied:
        return supplied

    class Handler:
        def __init__(self, value: Supplied):
            self.value = value

    container = CompiledContainer()
    container.register(
        Handler,
        dependency_config={"value": DependencySettings(value_factory=supply_value)},
    )

    report = container.seal()
    result = container.resolve(Handler)

    assert any(item.service_type is Handler and item.reason == "custom value provider" for item in report.fallbacks)
    assert result.value is supplied


def test_compiled_generator_finalizer_and_scoped_teardown_run_on_scope_exit():
    events: list[str] = []

    def build_leaf() -> Generator[Leaf, None, None]:
        events.append("open")
        yield Leaf()
        events.append("close")

    teardown = Mock()
    container = CompiledContainer()
    container.register(Leaf, factory=build_leaf, lifespan=Lifespan.scoped, scoped_teardown=teardown)
    container.seal()

    with container.new_scope() as scope:
        leaf = scope.resolve(Leaf)
        assert events == ["open"]

    teardown.assert_called_once_with(leaf)
    assert events == ["open", "close"]


async def test_async_factory_and_generator_use_the_compiled_async_plan_and_finalize():
    events: list[str] = []

    class AsyncLeaf:
        pass

    class AsyncService:
        def __init__(self, leaf: AsyncLeaf):
            self.leaf = leaf

    async def build_leaf():
        events.append("open")
        yield AsyncLeaf()
        events.append("close")

    container = CompiledContainer()
    container.register(AsyncLeaf, factory=build_leaf, lifespan=Lifespan.scoped)
    container.register(AsyncService)
    report = container.seal()

    assert AsyncService in container._compiled_roots
    assert not container._compiled_roots[AsyncService].sync_supported
    assert report.async_compiled_roots > report.sync_compiled_roots

    async with container.new_scope() as scope:
        result = await scope.resolve_async(AsyncService)
        assert isinstance(result.leaf, AsyncLeaf)
        assert events == ["open"]

    assert events == ["open", "close"]


def test_user_factory_failure_is_not_retried_through_the_fallback_path():
    calls = 0

    def fail() -> Leaf:
        nonlocal calls
        calls += 1
        raise RuntimeError("factory failed")

    container = CompiledContainer()
    container.register(Leaf, factory=fail)
    container.seal()

    with pytest.raises(RuntimeError, match="factory failed"):
        container.resolve(Leaf)

    assert calls == 1


def test_concurrent_compiled_resolutions_build_one_singleton():
    calls = 0
    calls_lock = threading.Lock()
    started = threading.Event()
    release = threading.Event()

    def build_leaf() -> Leaf:
        nonlocal calls
        with calls_lock:
            calls += 1
        started.set()
        release.wait(timeout=2)
        return Leaf()

    container = CompiledContainer()
    container.register(Leaf, factory=build_leaf, lifespan=Lifespan.singleton)
    container.seal()

    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = [executor.submit(container.resolve, Leaf) for _ in range(8)]
        assert started.wait(timeout=2)
        release.set()
        leaves = [future.result(timeout=2) for future in futures]

    assert calls == 1
    assert len({id(leaf) for leaf in leaves}) == 1


async def test_concurrent_compiled_async_resolutions_build_one_scoped_instance():
    calls = 0

    async def build_leaf() -> Leaf:
        nonlocal calls
        calls += 1
        await asyncio.sleep(0)
        return Leaf()

    container = CompiledContainer()
    container.register(Leaf, factory=build_leaf, lifespan=Lifespan.scoped)
    container.seal()

    async with container.new_scope() as scope:
        leaves = await asyncio.gather(*(scope.resolve_async(Leaf) for _ in range(20)))

    assert calls == 1
    assert len({id(leaf) for leaf in leaves}) == 1


def test_explicit_dont_use_default_value_remains_compilable():
    class Value:
        pass

    class Handler:
        def __init__(self, value: Value = None):  # ty:ignore[invalid-parameter-default]
            self.value = value

    container = CompiledContainer()
    container.register(Value)
    container.register(
        Handler,
        dependency_config={
            "value": DependencySettings(value_factory=dont_use_default_value),
        },
    )
    report = container.seal()

    assert Handler not in {fallback.service_type for fallback in report.fallbacks}
    assert isinstance(container.resolve(Handler).value, Value)
