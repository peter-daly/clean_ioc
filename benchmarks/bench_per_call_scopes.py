"""Compare per-call handles with equivalent handwritten scope wrappers.

Both paths activate a scoped service and a generator-managed dependency in a
fresh scope, call one method, and close the scope. Parent scopes are not warmed.
Container construction and handle acquisition are excluded from runtime timing.
Async measurements include async activation and cleanup, without external I/O.
Runtime benchmark invocations batch 100 operations to amortize runner overhead;
divide their reported times by OPERATIONS_PER_BATCH for a per-operation value.
"""

from collections.abc import AsyncIterator, Iterator
from typing import Literal, Protocol

from benchbro import Case, system

from clean_ioc import Container, ContainerBuilder, Scope

Mode = Literal["manual", "per_call"]
OPERATIONS_PER_BATCH = 100


class Resource:
    closed = False


def managed_resource() -> Iterator[Resource]:
    resource = Resource()
    try:
        yield resource
    finally:
        resource.closed = True


async def async_managed_resource() -> AsyncIterator[Resource]:
    resource = Resource()
    try:
        yield resource
    finally:
        resource.closed = True


class SyncOperation(Protocol):
    def process(self, value: int) -> int: ...


class AsyncOperation(Protocol):
    async def process(self, value: int) -> int: ...


class SyncImplementation:
    def __init__(self, resource: Resource):
        self.resource = resource

    def process(self, value: int) -> int:
        if self.resource.closed:
            raise RuntimeError("Operation used a closed resource")
        return value + 1


class AsyncImplementation:
    def __init__(self, resource: Resource):
        self.resource = resource

    async def process(self, value: int) -> int:
        if self.resource.closed:
            raise RuntimeError("Operation used a closed resource")
        return value + 1


def sync_builder(mode: Mode) -> ContainerBuilder:
    builder = ContainerBuilder()
    builder.register(Resource, factory=managed_resource, lifespan="scoped")
    if mode == "per_call":
        builder.register(SyncOperation, SyncImplementation, scope="per_call")
    else:
        builder.register(SyncOperation, SyncImplementation, lifespan="scoped")
    return builder


def async_builder(mode: Mode) -> ContainerBuilder:
    builder = ContainerBuilder()
    builder.register(Resource, factory=async_managed_resource, lifespan="scoped")
    if mode == "per_call":
        builder.register(AsyncOperation, AsyncImplementation, scope="per_call")
    else:
        builder.register(AsyncOperation, AsyncImplementation, lifespan="scoped")
    return builder


class ManualSyncOperation:
    def __init__(self, container: Scope):
        self.container = container

    def process(self, value: int) -> int:
        with self.container.new_scope() as scope:
            return scope.resolve(SyncOperation).process(value)


class ManualAsyncOperation:
    def __init__(self, container: Scope):
        self.container = container

    async def process(self, value: int) -> int:
        async with self.container.new_scope() as scope:
            target = await scope.resolve_async(AsyncOperation)
            return await target.process(value)


@system(scope="session")
def per_call_sync_operations() -> Iterator[dict[Mode, SyncOperation]]:
    with sync_builder("manual").build() as manual, sync_builder("per_call").build() as per_call:
        yield {"manual": ManualSyncOperation(manual), "per_call": per_call.resolve(SyncOperation)}


@system(scope="session")
async def per_call_async_operations() -> AsyncIterator[dict[Mode, AsyncOperation]]:
    async with async_builder("manual").build() as manual, async_builder("per_call").build() as per_call:
        yield {"manual": ManualAsyncOperation(manual), "per_call": per_call.resolve(AsyncOperation)}


sync_calls = Case(
    name="per-call-sync",
    tags=["per-call", "runtime"],
    min_iterations=100,
    setup_timing="exclude",
    teardown_timing="exclude",
)


@sync_calls.benchmark(name="batch-of-100-scoped-operations")
@sync_calls.parametrize("mode", ["manual", "per_call"])
def sync_scoped_operation(per_call_sync_operations: dict[Mode, SyncOperation], mode: Mode) -> int:
    operation = per_call_sync_operations[mode]
    result = 0
    for _ in range(OPERATIONS_PER_BATCH):
        result = operation.process(41)
    return result


async_calls = Case(
    name="per-call-async",
    tags=["per-call", "runtime"],
    min_iterations=100,
    setup_timing="exclude",
    teardown_timing="exclude",
)


@async_calls.benchmark(name="batch-of-100-scoped-operations")
@async_calls.parametrize("mode", ["manual", "per_call"])
async def async_scoped_operation(per_call_async_operations: dict[Mode, AsyncOperation], mode: Mode) -> int:
    operation = per_call_async_operations[mode]
    result = 0
    for _ in range(OPERATIONS_PER_BATCH):
        result = await operation.process(41)
    return result


build = Case(
    name="per-call-build",
    tags=["per-call", "build"],
    min_iterations=100,
    setup_timing="exclude",
    teardown_timing="exclude",
)


@build.benchmark(name="build-scoped-operation")
@build.parametrize("mode", ["manual", "per_call"])
def build_scoped_operation(mode: Mode) -> Container:
    return sync_builder(mode).build()
