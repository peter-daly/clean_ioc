import asyncio
from types import GenericAlias
from typing import Generic, TypeVar, cast

import pytest
from typing_extensions import TypeForm

from clean_ioc import AsyncProvider, ContainerBuilder, Provider, ProviderScopeClosedError, ScopeClosedError
from clean_ioc.container import _RuntimeResolutionContext

T = TypeVar("T")


class Repository(Generic[T]):
    pass


class Plain:
    pass


def forbid_context_allocations(monkeypatch):
    def unexpected_context(self, scope):
        pytest.fail("A warm cache hit allocated a resolution context")

    monkeypatch.setattr(_RuntimeResolutionContext, "__init__", unexpected_context)


@pytest.mark.asyncio
@pytest.mark.parametrize("key", [Plain, Repository[int]])
async def test_child_cache_hits_check_singleton_owner_and_provider_scope(key, monkeypatch):
    builder = ContainerBuilder().set_provider_roots([Provider[key], AsyncProvider[key]])
    builder.register(key, lifespan="singleton")
    container = builder.build()
    with container.new_scope() as child:
        with container:
            provider = child.resolve(Provider[key])
            async_provider = child.resolve(AsyncProvider[key])
            cached = container.resolve(key)
            forbid_context_allocations(monkeypatch)

            assert child.resolve(key) is cached
            assert await child.resolve_async(key) is cached
            assert provider() is cached
            assert await async_provider() is cached

        with pytest.raises(ScopeClosedError, match="The runtime ownership boundary is closed"):
            child.resolve(key)
        with pytest.raises(ScopeClosedError, match="The runtime ownership boundary is closed"):
            await child.resolve_async(key)
        with pytest.raises(ScopeClosedError, match="The runtime ownership boundary is closed"):
            provider()
        with pytest.raises(ScopeClosedError, match="The runtime ownership boundary is closed"):
            await async_provider()

    with pytest.raises(ProviderScopeClosedError, match="The provider's bound scope is closed"):
        provider()
    with pytest.raises(ProviderScopeClosedError, match="The provider's bound scope is closed"):
        await async_provider()


@pytest.mark.asyncio
async def test_generic_cache_hits_reuse_a_parent_scoped_value(monkeypatch):
    class RequestInput:
        pass

    def create(value: RequestInput) -> Repository[int]:
        assert value is provided
        return Repository()

    provided = RequestInput()
    key = Repository[int]
    builder = ContainerBuilder().set_provider_roots([Provider[key], AsyncProvider[key]])
    builder.declare_slot(RequestInput, target="scoped")
    builder.register(key, factory=create, lifespan="scoped")
    with builder.build() as container:
        with container.new_scope() as parent:
            parent.provide(RequestInput, provided)
            cached = parent.resolve(key)
            with parent.new_scope() as child:
                provider = child.resolve(Provider[key])
                async_provider = child.resolve(AsyncProvider[key])
                forbid_context_allocations(monkeypatch)

                assert child.resolve(key) is cached
                assert await child.resolve_async(key) is cached
                assert provider() is cached
                assert await async_provider() is cached


@pytest.mark.asyncio
async def test_generic_root_and_provider_share_singleton_retry_and_async_requirement():
    started = asyncio.Event()
    release = asyncio.Event()
    attempts = 0

    async def create() -> Repository[int]:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            started.set()
            await release.wait()
            raise ValueError("first activation failed")
        return Repository()

    key = Repository[int]
    builder = ContainerBuilder().set_provider_roots([AsyncProvider[key]])
    builder.register(key, factory=create, lifespan="singleton")
    async with builder.build() as container:
        provider = container.resolve(AsyncProvider[key])
        builder_call = asyncio.create_task(provider())
        await started.wait()
        waiter = asyncio.create_task(container.resolve_async(key))
        await asyncio.sleep(0)
        release.set()

        for call in (builder_call, waiter):
            with pytest.raises(ValueError, match="first activation failed"):
                await call
        assert attempts == 1

        cache = await provider()
        assert await container.resolve_async(key) is cache
        assert await provider() is cache
        assert attempts == 2
        with pytest.raises(RuntimeError, match=r"requires resolve_async\(\)"):
            container.resolve(key)


@pytest.mark.asyncio
async def test_collection_filters_observe_the_same_request_classification():
    reads = []

    class Request(GenericAlias):
        @property
        def __class__(self):
            reads.append(True)
            return GenericAlias

    key = cast(TypeForm[list[Plain]], Request(list, Plain))
    builder = ContainerBuilder()
    builder.register(Plain, lifespan="singleton")
    with builder.build() as container:
        expected = container.resolve(key)
        expected_reads = len(reads)
        assert len(expected) == 1
        assert expected_reads > 0

        reads.clear()
        assert container.resolve(key, lambda _: len(reads) == expected_reads) == expected
        reads.clear()
        assert await container.resolve_async(key, lambda _: len(reads) == expected_reads) == expected
