"""Managed provider entry/exit cost, excluding build and application block work.

Each timed invocation batches 100 operations. Divide reported time by 100 for
per-acquisition cost. Observed variants include existing exact counts and full
sampling; resources use no I/O. Ordinary provider is a cached singleton call.
"""

from collections.abc import AsyncIterator, Iterator

from benchbro import Case, system

from clean_ioc import (
    AsyncManagedProvider,
    ContainerBuilder,
    Instrumentation,
    ManagedProvider,
    Provider,
    ResolutionProfiler,
)

OPERATIONS_PER_BATCH = 100


class Resource:
    pass


def resource() -> Iterator[Resource]:
    yield Resource()


async def async_resource() -> AsyncIterator[Resource]:
    yield Resource()


@system(scope="session")
def handles() -> Iterator[dict]:
    containers = []
    result = {}
    for observed in (False, True):
        for lifespan in ("scoped", "singleton"):
            builder = ContainerBuilder()
            builder.register(Resource, factory=resource, lifespan=lifespan)
            instrumentation = Instrumentation(ResolutionProfiler()) if observed else None
            container = builder.build(instrumentation=instrumentation)
            containers.append(container)
            result[observed, lifespan] = container.resolve(ManagedProvider[Resource])
            result[observed, lifespan, "ordinary"] = container.resolve(Provider[Resource])
            result[observed, lifespan, "container"] = container
    try:
        yield result
    finally:
        for container in containers:
            container.__exit__()


@system(scope="session")
async def async_handles() -> AsyncIterator[dict]:
    containers = []
    result = {}
    for observed in (False, True):
        builder = ContainerBuilder()
        builder.register(Resource, factory=async_resource, lifespan="scoped")
        instrumentation = Instrumentation(ResolutionProfiler()) if observed else None
        container = builder.build(instrumentation=instrumentation)
        containers.append(container)
        result[observed] = container.resolve(AsyncManagedProvider[Resource])
    try:
        yield result
    finally:
        for container in containers:
            await container.__aexit__()


sync = Case(name="managed-provider-sync", tags=["managed-provider", "runtime"], min_iterations=100)


@sync.benchmark(name="batch-of-100-acquisitions")
@sync.parametrize("observed", [False, True], ids=["plain", "observed"])
@sync.parametrize("lifespan", ["scoped", "singleton"])
def acquire(handles: dict, observed: bool, lifespan: str):
    handle = handles[observed, lifespan]
    for _ in range(OPERATIONS_PER_BATCH):
        with handle() as value:
            pass
    return value


@sync.benchmark(name="batch-of-100-unentered-managers")
@sync.parametrize("observed", [False, True], ids=["plain", "observed"])
def manager_creation(handles: dict, observed: bool):
    handle = handles[observed, "scoped"]
    for _ in range(OPERATIONS_PER_BATCH):
        manager = handle()
    return manager


@sync.benchmark(name="batch-of-100-handle-resolutions")
@sync.parametrize("observed", [False, True], ids=["plain", "observed"])
def handle_resolution(handles: dict, observed: bool):
    container = handles[observed, "scoped", "container"]
    for _ in range(OPERATIONS_PER_BATCH):
        handle = container.resolve(ManagedProvider[Resource])
    return handle


@sync.benchmark(name="batch-of-100-ordinary-singleton-provider-calls")
@sync.parametrize("observed", [False, True], ids=["plain", "observed"])
def ordinary_provider(handles: dict, observed: bool):
    handle = handles[observed, "singleton", "ordinary"]
    for _ in range(OPERATIONS_PER_BATCH):
        value = handle()
    return value


asynchronous = Case(name="managed-provider-async", tags=["managed-provider", "runtime"], min_iterations=100)


@asynchronous.benchmark(name="batch-of-100-resource-acquisitions")
@asynchronous.parametrize("observed", [False, True], ids=["plain", "observed"])
async def async_acquire(async_handles: dict, observed: bool):
    handle = async_handles[observed]
    for _ in range(OPERATIONS_PER_BATCH):
        async with handle() as value:
            pass
    return value
