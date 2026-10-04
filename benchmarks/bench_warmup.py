"""Explicit warm-up cost: cached batches, build demand and complete resource lifecycle.

Cached cases report 100 explicit calls per batch; divide by 100. Build and cold
lifecycle cases measure one complete operation, including owner shutdown. Resource
factories have no I/O. Fixture creation is excluded and session owners are closed.
"""

from collections.abc import Iterator

from benchbro import Case, system

from clean_ioc import ContainerBuilder, Instrumentation, ResolutionProfiler, WarmupPlan, WarmupTarget


class Resource:
    pass


def resource() -> Iterator[Resource]:
    yield Resource()


def builder(declared: bool = True):
    result = ContainerBuilder()
    result.register(Resource, factory=resource, lifespan="singleton")
    if declared:
        result.add_warmup_plan(WarmupPlan("startup", [WarmupTarget(Resource)]))
    return result


@system(scope="session")
def warmed() -> Iterator[dict]:
    containers = {}
    for observed in (False, True):
        instrumentation = Instrumentation(ResolutionProfiler()) if observed else None
        container = builder().build(instrumentation=instrumentation)
        container.warmup("startup").assert_valid()
        containers[observed] = container
    try:
        yield containers
    finally:
        for container in containers.values():
            container.__exit__()


cached = Case(name="warmup-cached", tags=["warmup", "runtime"], min_iterations=100)


@cached.benchmark(name="batch-of-100")
@cached.parametrize("observed", [False, True])
def cached_runs(warmed: dict, observed: bool):
    for _ in range(100):
        warmed[observed].warmup("startup").raise_for_errors()


lifecycle = Case(name="warmup-build-lifecycle", tags=["warmup", "build"], min_iterations=10)


@lifecycle.benchmark()
@lifecycle.parametrize("declared", [False, True])
def compile_plan(declared: bool):
    with builder(declared).build():
        pass


@lifecycle.benchmark()
def cold_activation_and_shutdown():
    with builder().build() as container:
        container.warmup("startup").raise_for_errors()
