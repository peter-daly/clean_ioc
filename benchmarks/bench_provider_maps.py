"""Lazy map costs: acquisition, prepared-key lookup, direct invocation, and build.

Fixture construction, keys, target annotations, and singleton warmup are excluded
from runtime measurements. Acquisition constructs handles, never targets. Build
explicitly includes declarations, complete compilation, and closing the container.
"""

from collections.abc import Iterator, Mapping

from benchbro import Case, system

from clean_ioc import Container, ContainerBuilder, Provider


class Service:
    pass


MAP_TYPE = Mapping[str, Provider[Service]]
SIZES = (1, 10, 100)


def make_map(size: int, lifespan="transient") -> Container:
    builder = ContainerBuilder()
    for index in range(size):
        builder.register(Service, name=f"service-{index}", lifespan=lifespan)
    builder.register_provider_map(Service, key=lambda component: component.name)
    return builder.build()


@system(scope="session")
def map_fixtures() -> Iterator[dict]:
    containers = {size: make_map(size) for size in SIZES}
    cached = make_map(1, "singleton")
    maps = {size: container.resolve(MAP_TYPE) for size, container in containers.items()}
    transient = maps[1]["service-0"]
    singleton = cached.resolve(MAP_TYPE)["service-0"]
    singleton()
    try:
        yield {"containers": containers, "maps": maps, "transient": transient, "singleton": singleton}
    finally:
        for container in (*containers.values(), cached):
            with container:
                pass


runtime = Case(
    name="provider-map-runtime",
    tags=["runtime", "provider-map"],
    min_iterations=10_000,
    setup_timing="exclude",
    teardown_timing="exclude",
)


@runtime.benchmark(name="acquire")
@runtime.parametrize("size", SIZES)
def acquire(map_fixtures, size):
    return map_fixtures["containers"][size].resolve(MAP_TYPE)


@runtime.benchmark(name="lookup")
@runtime.parametrize("size", SIZES)
def lookup(map_fixtures, size):
    return map_fixtures["maps"][size]["service-0"]


@runtime.benchmark(name="invoke")
@runtime.parametrize("lifespan", ["transient", "singleton"])
def invoke(map_fixtures, lifespan):
    return map_fixtures[lifespan]()


build = Case(name="provider-map-build", tags=["build", "provider-map"], min_iterations=5)


@build.benchmark(name="compile")
@build.parametrize("size", [1, 10])
def compile_map(size):
    with make_map(size):
        pass
