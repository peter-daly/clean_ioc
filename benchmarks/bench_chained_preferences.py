"""Optional chains versus completed parent-precedence behavior (work item 15).

Run the same source on both snapshots. New API detection and reusable predicate/
chain creation happen at import, outside timing. Builds include registration,
compilation and close; runtime fixture setup, warming and teardown are excluded.
The old snapshot omits preference declarations; enabled single builds deliberately
choose a different registration. All candidates use the same implementation.
"""

from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

from benchbro import Case, system

import clean_ioc
from clean_ioc import ComponentFilter, ContainerBuilder, Provider, Scope, Tag, select
from clean_ioc import component_filters as cf

_prefer = getattr(clean_ioc, "prefer", None)
SUPPORTS_PREFERENCES = _prefer is not None


def chain(*predicates: ComponentFilter) -> Any:
    if _prefer is None:
        return None
    result = _prefer(predicates[0])
    for predicate in predicates[1:]:
        result = result.then(predicate)
    return result


def options(preference: Any) -> dict[str, Any]:
    return {"prefer": preference} if SUPPORTS_PREFERENCES and preference is not None else {}


PRIMARY = cf.has_tag("primary")
BATCH_PARENT = cf.parent(cf.has_tag("workload", "batch"))
ABSENT_PARENT = cf.parent(cf.has_tag("workload", "absent"))
UNRESOLVED_PREFIX = (cf.all_components, cf.has_tag("absent")) * 3 + (cf.all_components,)
CONSUMER_EARLY = chain(PRIMARY, *UNRESOLVED_PREFIX)
CONSUMER_LATE = chain(*UNRESOLVED_PREFIX, PRIMARY)
REGISTRATION_LATE_MATCH = chain(*UNRESOLVED_PREFIX, BATCH_PARENT)
REGISTRATION_LATE_MISS = chain(*UNRESOLVED_PREFIX, ABSENT_PARENT)


class PreferenceService:
    pass


class PreferenceConsumer:
    def __init__(self, service: PreferenceService):
        self.service = service


class PreferenceProviderConsumer:
    def __init__(self, service: Provider[PreferenceService]):
        self.service = service


class PreferenceCollectionConsumer:
    def __init__(self, services: list[PreferenceService]):
        self.services = services


def declare_services(builder: ContainerBuilder, count: int, *, registration_chain: bool = False) -> None:
    for index in range(count):
        preference = (REGISTRATION_LATE_MATCH if index == 0 else REGISTRATION_LATE_MISS) if registration_chain else None
        builder.register(PreferenceService, tags=[Tag("primary")] if index == 0 else (), **options(preference))


build = Case(
    name="chained-preferences-build",
    tags=["preferences", "build"],
    min_iterations=3,
    setup_timing="exclude",
    teardown_timing="exclude",
)


@build.benchmark(name="single-dependency")
@build.parametrize("mode", ["absent", "consumer-early-8", "consumer-late-8", "registration-late-8"])
@build.parametrize("candidate_count", [4, 16], ids=["4-candidates", "16-candidates"])
@build.parametrize("parent_count", [1, 8], ids=["1-parent", "8-parents"])
def single_dependency(mode: str, candidate_count: int, parent_count: int) -> None:
    builder = ContainerBuilder()
    declare_services(builder, candidate_count, registration_chain=mode == "registration-late-8")
    preference = CONSUMER_EARLY if mode == "consumer-early-8" else CONSUMER_LATE if mode == "consumer-late-8" else None
    for index in range(parent_count):
        builder.register(
            PreferenceConsumer,
            name=f"worker-{index}",
            tags=[Tag("workload", "batch")],
            arguments={"service": select(cf.all_components, **options(preference))},
        )
    with builder.build():
        pass


@build.benchmark(name="provider-unique-eligible")
def provider_unique_eligible() -> None:
    """Comparable successful builds; the overlap benefit is covered by probes."""
    builder = ContainerBuilder()
    for index in range(16):
        builder.register(
            PreferenceService,
            when=cf.parent(cf.parent(cf.with_name(f"worker-{index}"))),
            **options(REGISTRATION_LATE_MATCH),
        )
    for index in range(8):
        builder.register(
            PreferenceProviderConsumer,
            name=f"worker-{index}",
            arguments={"service": select(cf.all_components, **options(CONSUMER_LATE))},
        )
    with builder.build():
        pass


@build.benchmark(name="collection-membership")
def collection_membership() -> None:
    builder = ContainerBuilder()
    declare_services(builder, 16, registration_chain=True)
    for index in range(8):
        builder.register(
            PreferenceCollectionConsumer,
            name=f"worker-{index}",
            tags=[Tag("workload", "batch")],
            arguments={"services": select(cf.all_components, **options(CONSUMER_LATE))},
        )
    with builder.build():
        pass


@dataclass
class PreferenceRuntimeState:
    absent: Scope
    enabled: Scope


def runtime_builder(*, enabled: bool) -> ContainerBuilder:
    builder = ContainerBuilder()
    for index in range(16):
        builder.register(
            PreferenceService,
            lifespan="singleton",
            tags=[Tag("primary")] if index == 0 else (),
        )
    builder.register(
        PreferenceConsumer,
        lifespan="transient",
        arguments={"service": select(cf.all_components, **options(CONSUMER_LATE if enabled else None))},
    )
    return builder


@system(scope="session")
def preference_runtime() -> Iterator[PreferenceRuntimeState]:
    with runtime_builder(enabled=False).build() as absent, runtime_builder(enabled=True).build() as enabled:
        for container in (absent, enabled):
            container.resolve(PreferenceService)
            container.resolve(PreferenceConsumer)
            container.resolve(list[PreferenceService], filter=cf.all_components)
        yield PreferenceRuntimeState(absent, enabled)


runtime = Case(
    name="chained-preferences-runtime",
    tags=["preferences", "runtime"],
    min_iterations=5_000,
    setup_timing="exclude",
    teardown_timing="exclude",
)


@runtime.benchmark(name="direct-python-control", min_iterations=20_000)
def direct_python_control() -> PreferenceService:
    return PreferenceService()


@runtime.benchmark(name="cached-root", min_iterations=20_000)
def cached_root(preference_runtime: PreferenceRuntimeState) -> PreferenceService:
    return preference_runtime.enabled.resolve(PreferenceService)


@runtime.benchmark(name="frozen-injection-absent")
def frozen_injection_absent(preference_runtime: PreferenceRuntimeState) -> PreferenceConsumer:
    return preference_runtime.absent.resolve(PreferenceConsumer)


@runtime.benchmark(name="frozen-injection-enabled")
def frozen_injection_enabled(preference_runtime: PreferenceRuntimeState) -> PreferenceConsumer:
    return preference_runtime.enabled.resolve(PreferenceConsumer)


@runtime.benchmark(name="explicit-filter-root")
def explicit_filter_root(preference_runtime: PreferenceRuntimeState) -> PreferenceService:
    return preference_runtime.enabled.resolve(PreferenceService, filter=PRIMARY)


@runtime.benchmark(name="collection-root", min_iterations=1_000)
def collection_root(preference_runtime: PreferenceRuntimeState) -> list[PreferenceService]:
    return preference_runtime.enabled.resolve(list[PreferenceService], filter=cf.all_components)
