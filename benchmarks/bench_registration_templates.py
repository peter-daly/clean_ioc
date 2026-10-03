"""Registration-template expansion versus equivalent explicit registrations.

Build measures declarations, compilation, and container teardown. Runtime uses
prebuilt, warmed containers; fixture setup and teardown are excluded. Both modes
produce one Worker per Source with an exact registration-ID dependency binding.
The original cases measure Worker -> Source; parent-build measures Source -> Dependency.
"""

from collections.abc import Iterator

from benchbro import Case, system

from clean_ioc import Container, ContainerBuilder, Lifespan, RegistrationTemplate, select
from clean_ioc import component_filters as cf


class Source:
    def __init__(self, key: int):
        self.key = key


class Worker:
    def __init__(self, source: Source):
        self.source = source


def make_container(count: int, mode: str, lifespan: Lifespan = "transient") -> Container:
    builder = ContainerBuilder()
    source_ids = [builder.register(Source, arguments={"key": key}, lifespan=lifespan) for key in range(count)]
    if mode == "template":
        builder.register_registration_template(
            for_each=Source,
            template=lambda source: RegistrationTemplate(
                Worker,
                arguments={"source": select(cf.with_id(source.id))},
                lifespan=lifespan,
            ),
        )
    elif mode == "explicit":
        for source_id in source_ids:
            builder.register(Worker, arguments={"source": select(cf.with_id(source_id))}, lifespan=lifespan)
    else:
        raise ValueError(mode)
    return builder.build()


build = Case(name="registration-template-build", tags=["build", "registration-template"], min_iterations=3)


@build.benchmark(name="source-worker-pairs")
@build.parametrize("count", [1, 10, 100])
@build.parametrize("mode", ["explicit", "template"])
def build_pairs(count: int, mode: str) -> None:
    with make_container(count, mode):
        pass


@system(scope="session")
def registration_template_fixtures() -> Iterator[dict[tuple[int, str, Lifespan], Container]]:
    fixtures: dict[tuple[int, str, Lifespan], Container] = {}
    try:
        for count in (1, 100):
            for mode in ("explicit", "template"):
                for lifespan in ("transient", "singleton"):
                    container = make_container(count, mode, lifespan)
                    fixtures[count, mode, lifespan] = container
                    workers = container.resolve(list[Worker])
                    if [worker.source.key for worker in workers] != list(reversed(range(count))):
                        raise AssertionError("Benchmark modes must produce identical source-worker pairs")
                    container.resolve(Worker)
        yield fixtures
    finally:
        for container in fixtures.values():
            with container:
                pass


runtime = Case(
    name="registration-template-runtime",
    tags=["runtime", "registration-template"],
    min_iterations=20_000,
    setup_timing="exclude",
    teardown_timing="exclude",
)


@runtime.benchmark(name="resolve-worker")
@runtime.parametrize("count", [1, 100])
@runtime.parametrize("mode", ["explicit", "template"])
@runtime.parametrize("lifespan", ["transient", "singleton"])
def resolve_worker(registration_template_fixtures, count: int, mode: str, lifespan: Lifespan) -> Worker:
    return registration_template_fixtures[count, mode, lifespan].resolve(Worker)


collection = Case(
    name="registration-template-collection",
    tags=["runtime", "registration-template"],
    min_iterations=1_000,
    setup_timing="exclude",
    teardown_timing="exclude",
)


@collection.benchmark(name="resolve-100-workers")
@collection.parametrize("mode", ["explicit", "template"])
@collection.parametrize("lifespan", ["transient", "singleton"])
def resolve_workers(registration_template_fixtures, mode: str, lifespan: Lifespan) -> list[Worker]:
    return registration_template_fixtures[100, mode, lifespan].resolve(list[Worker])


class ParentDependency:
    def __init__(self, owner_id: str):
        self.owner_id = owner_id


class ParentSource:
    def __init__(self, dependency: ParentDependency):
        self.dependency = dependency


def make_parent_container(count: int, mode: str) -> Container:
    builder = ContainerBuilder()
    source_ids = [builder.register(ParentSource) for _ in range(count)]
    if mode == "template":
        builder.register_registration_template(
            for_each=ParentSource,
            template=lambda source: RegistrationTemplate(
                ParentDependency,
                arguments={"owner_id": source.id},
                when=cf.parent(cf.with_id(source.id)),
                root_policy="dependency_only",
            ),
        )
    elif mode == "explicit":
        for source_id in source_ids:
            builder.register(
                ParentDependency,
                arguments={"owner_id": source_id},
                when=cf.parent(cf.with_id(source_id)),
                root_policy="dependency_only",
            )
    else:
        raise ValueError(mode)
    return builder.build()


parent_build = Case(
    name="registration-template-parent-build",
    tags=["build", "registration-template", "parent"],
    min_iterations=3,
)


@parent_build.benchmark(name="source-dependency-pairs")
@parent_build.parametrize("count", [1, 10, 100])
@parent_build.parametrize("mode", ["explicit", "template"])
def build_parent_pairs(count: int, mode: str) -> None:
    with make_parent_container(count, mode):
        pass
