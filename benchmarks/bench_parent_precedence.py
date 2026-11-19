"""Build-time contextual preference versus the 2.0.0b23 boolean baseline.

The same source runs against both versions. API support is detected once during
module loading, outside measured intervals. The baseline omits new precedence
keywords; scored single builds intentionally select a different registration.
Build cases include composition, compilation, and closing an unused container.
Runtime fixture setup, singleton warming, and teardown are excluded.
"""

from collections.abc import Iterator
from dataclasses import dataclass
from inspect import signature
from typing import Any

from benchbro import Case, system

from clean_ioc import ComponentFilter, ContainerBuilder, Provider, Scope, Tag
from clean_ioc import component_filters as cf

SUPPORTS_PARENT_PRECEDENCE = "parent_precedence" in signature(ContainerBuilder.register).parameters


def precedence_options(value: int) -> dict[str, Any]:
    return {"parent_precedence": value} if SUPPORTS_PARENT_PRECEDENCE else {}


class PrecedenceService:
    pass


class PrecedenceConsumer:
    def __init__(self, service: PrecedenceService):
        self.service = service


class PrecedenceProviderConsumer:
    def __init__(self, service: Provider[PrecedenceService]):
        self.service = service


class PrecedenceCollectionConsumer:
    def __init__(self, services: list[PrecedenceService]):
        self.services = services


build = Case(
    name="parent-precedence-build",
    tags=["parent-precedence", "build"],
    min_iterations=3,
    setup_timing="exclude",
    teardown_timing="exclude",
)


@build.benchmark(name="single-dependency")
@build.parametrize("scored", [False, True], ids=["zero-defaults", "explicit-precedence"])
@build.parametrize("candidate_count", [4, 16], ids=["4-candidates", "16-candidates"])
@build.parametrize("parent_count", [1, 8], ids=["1-parent", "8-parents"])
def single_dependency(candidate_count: int, parent_count: int, scored: bool) -> None:
    builder = ContainerBuilder()
    condition = cf.parent(cf.has_tag("workload", "batch"))
    for index in range(candidate_count):
        options = precedence_options(candidate_count - index) if scored else {}
        builder.register(PrecedenceService, when=condition, **options)
    for index in range(parent_count):
        builder.register(PrecedenceConsumer, name=f"worker-{index}", tags=[Tag("workload", "batch")])
    with builder.build():
        pass


@build.benchmark(name="provider-unique-eligible-16-candidates-8-parents")
def provider_unique_eligible() -> None:
    """Comparable successful provider builds; overlapping-provider benefit is tested separately."""
    builder = ContainerBuilder()
    for index in range(16):
        builder.register(
            PrecedenceService,
            when=cf.parent(cf.parent(cf.with_name(f"worker-{index}"))),
            **precedence_options(index + 1),
        )
    for index in range(8):
        builder.register(PrecedenceProviderConsumer, name=f"worker-{index}")
    with builder.build():
        pass


@build.benchmark(name="collection-16-candidates-8-parents")
def collection_membership() -> None:
    builder = ContainerBuilder()
    condition = cf.parent(cf.parent(cf.is_named))
    for index in range(16):
        builder.register(PrecedenceService, when=condition, **precedence_options(index + 1))
    for index in range(8):
        builder.register(PrecedenceCollectionConsumer, name=f"worker-{index}")
    with builder.build():
        pass


@dataclass
class PrecedenceRuntimeFixture:
    container: Scope
    exact_name: ComponentFilter
    alternatives: ComponentFilter


@system(scope="session")
def precedence_runtime() -> Iterator[PrecedenceRuntimeFixture]:
    builder = ContainerBuilder()
    alternatives = cf.with_name("service-0")
    for index in range(32):
        builder.register(
            PrecedenceService,
            name=f"service-{index}",
            tags=[Tag("route", str(index))],
            lifespan="singleton",
            **precedence_options(32 - index),
        )
        alternatives |= cf.has_tag("route", str(index))
    builder.register(PrecedenceService, lifespan="singleton")
    with builder.build() as container:
        container.resolve(PrecedenceService)
        container.resolve(list[PrecedenceService], filter=cf.all_components)
        yield PrecedenceRuntimeFixture(container, cf.with_name("service-0"), alternatives)


runtime = Case(
    name="parent-precedence-runtime",
    tags=["parent-precedence", "runtime"],
    min_iterations=500,
    setup_timing="exclude",
    teardown_timing="exclude",
)


@runtime.benchmark(name="direct-python-control", min_iterations=20_000)
def direct_python_control() -> PrecedenceService:
    return PrecedenceService()


@runtime.benchmark(name="default-cached-root", min_iterations=20_000)
def default_cached_root(precedence_runtime: PrecedenceRuntimeFixture) -> PrecedenceService:
    return precedence_runtime.container.resolve(PrecedenceService)


@runtime.benchmark(name="explicit-name-root")
def explicit_name_root(precedence_runtime: PrecedenceRuntimeFixture) -> PrecedenceService:
    return precedence_runtime.container.resolve(PrecedenceService, filter=precedence_runtime.exact_name)


@runtime.benchmark(name="or-root-32-candidates")
def or_root(precedence_runtime: PrecedenceRuntimeFixture) -> PrecedenceService:
    return precedence_runtime.container.resolve(PrecedenceService, filter=precedence_runtime.alternatives)


@runtime.benchmark(name="or-collection-32-candidates")
def or_collection(precedence_runtime: PrecedenceRuntimeFixture) -> list[PrecedenceService]:
    return precedence_runtime.container.resolve(list[PrecedenceService], filter=precedence_runtime.alternatives)


@runtime.benchmark(name="default-collection")
def default_collection(precedence_runtime: PrecedenceRuntimeFixture) -> list[PrecedenceService]:
    return precedence_runtime.container.resolve(list[PrecedenceService])
