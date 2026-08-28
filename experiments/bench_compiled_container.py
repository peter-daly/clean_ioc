"""BenchBro comparison for the private sealed-container compiler experiment."""

from collections.abc import Generator

from benchbro import Case, system

from clean_ioc import Container, Scope
from experiments.compiled_container import CompiledContainer


class RequestValue:
    pass


class Leaf:
    pass


class LevelFour:
    def __init__(self, leaf: Leaf):
        self.leaf = leaf


class LevelThree:
    def __init__(self, child: LevelFour):
        self.child = child


class LevelTwo:
    def __init__(self, child: LevelThree):
        self.child = child


class LevelOne:
    def __init__(self, child: LevelTwo):
        self.child = child


class RequestHandler:
    def __init__(self, request_value: RequestValue, child: LevelOne):
        self.request_value = request_value
        self.child = child


def _register_graph(container: Container) -> None:
    for service_type in (Leaf, LevelFour, LevelThree, LevelTwo, LevelOne):
        container.register(service_type)


@system(scope="session")
def existing_container() -> Container:
    container = Container()
    _register_graph(container)
    return container


@system(scope="session")
def compiled_container() -> CompiledContainer:
    container = CompiledContainer()
    _register_graph(container)
    container.seal()
    return container


@system(scope="session")
def existing_request_scope() -> Generator[Scope, None, None]:
    container = Container()
    _register_graph(container)
    container.register(RequestHandler)
    with container.new_scope() as scope:
        scope.register(RequestValue, instance=RequestValue())
        yield scope


@system(scope="session")
def compiled_request_scope() -> Generator[Scope, None, None]:
    container = CompiledContainer()
    _register_graph(container)
    container.expect_to_be_scoped(RequestValue)
    container.register(RequestHandler)
    container.seal()
    with container.new_scope() as scope:
        scope.register(RequestValue, instance=RequestValue())
        yield scope


resolution = Case(
    name="sealed-container-resolution",
    tags=["experiment", "compiled-container"],
    setup_timing="exclude",
    teardown_timing="exclude",
    repeats=30,
    warmup_iterations=5,
    min_iterations=10_000,
    adaptive=True,
    min_repeats=15,
    min_time_s=0.25,
    max_time_s=10.0,
    target_relative_margin_pct=2.0,
    noise_threshold_pct=10.0,
)


@resolution.benchmark(name="existing-five-node-graph")
def resolve_existing_graph(existing_container: Container) -> LevelOne:
    return existing_container.resolve(LevelOne)


@resolution.benchmark(name="compiled-five-node-graph")
def resolve_compiled_graph(compiled_container: CompiledContainer) -> LevelOne:
    return compiled_container.resolve(LevelOne)


@resolution.benchmark(name="existing-request-scope-graph")
def resolve_existing_request_graph(existing_request_scope: Scope) -> RequestHandler:
    return existing_request_scope.resolve(RequestHandler)


@resolution.benchmark(name="compiled-request-scope-graph")
def resolve_compiled_request_graph(compiled_request_scope: Scope) -> RequestHandler:
    return compiled_request_scope.resolve(RequestHandler)


compilation = Case(
    name="sealed-container-compilation",
    tags=["experiment", "compiled-container", "startup"],
    setup_timing="exclude",
    teardown_timing="exclude",
    repeats=20,
    warmup_iterations=3,
    min_iterations=100,
    adaptive=True,
    min_repeats=15,
    min_time_s=0.25,
    max_time_s=10.0,
    target_relative_margin_pct=3.0,
    noise_threshold_pct=10.0,
)


@compilation.benchmark(name="build-and-seal-five-node-container")
def build_and_seal_container() -> CompiledContainer:
    container = CompiledContainer()
    _register_graph(container)
    container.seal()
    return container
