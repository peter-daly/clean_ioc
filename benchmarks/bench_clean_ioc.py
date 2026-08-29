"""BenchBro experiments for Clean IoC 2 build and runtime boundaries."""

from typing import Generic, TypeVar

from benchbro import Case, system

from clean_ioc import CompiledGraph, Container, ContainerBuilder, GraphDiff, GraphManifest, Scope


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


class Request:
    pass


class RequestHandler:
    def __init__(self, request: Request, child: LevelOne):
        self.request = request
        self.child = child


TBenchmark = TypeVar("TBenchmark")


class GenericFactoryDependency(Generic[TBenchmark]):
    pass


class IntGenericFactoryDependency(GenericFactoryDependency[int]):
    pass


class GenericFactoryProduct(Generic[TBenchmark]):
    def __init__(self, dependency: GenericFactoryDependency[TBenchmark]):
        self.dependency = dependency


class GenericFactoryConsumer:
    def __init__(self, product: GenericFactoryProduct[int]):
        self.product = product


def create_generic_factory_product(
    dependency: GenericFactoryDependency[TBenchmark],
) -> GenericFactoryProduct[TBenchmark]:
    return GenericFactoryProduct(dependency)


def build_graph_builder(*, mark_entrypoint: bool = False) -> ContainerBuilder:
    builder = ContainerBuilder()
    for service_type in (Leaf, LevelFour, LevelThree, LevelTwo, LevelOne):
        builder.register(service_type)
    if mark_entrypoint:
        builder.mark_entrypoint(LevelOne)
    return builder


@system(scope="session")
def instance_container() -> Container:
    builder = ContainerBuilder()
    builder.register(Leaf, instance=Leaf())
    return builder.build()


@system(scope="session")
def singleton_container() -> Container:
    builder = ContainerBuilder()
    builder.register(Leaf, lifespan="singleton")
    container = builder.build()
    container.resolve(Leaf)
    return container


@system(scope="session")
def transient_container() -> Container:
    builder = ContainerBuilder()
    builder.register(Leaf, lifespan="transient")
    return builder.build()


@system(scope="session")
def graph_container() -> Container:
    return build_graph_builder().build()


@system(scope="session")
def request_scope() -> Scope:
    builder = build_graph_builder()
    builder.declare_scope_slot(Request)
    builder.register(RequestHandler)
    return builder.build().new_scope().provide(Request, Request())


@system(scope="session")
def tooling_graph(graph_container: Container) -> CompiledGraph:
    return graph_container.graph


@system(scope="session")
def tooling_manifest(tooling_graph: CompiledGraph) -> GraphManifest:
    return tooling_graph.manifest(all_roots=True)


@system(scope="session")
def changed_tooling_manifest() -> GraphManifest:
    class AlternateLeaf(Leaf):
        pass

    builder = ContainerBuilder()
    builder.register(Leaf, AlternateLeaf)
    for service_type in (LevelFour, LevelThree, LevelTwo, LevelOne):
        builder.register(service_type)
    return builder.build().graph.manifest(all_roots=True)


runtime = Case(
    name="compiled-runtime",
    tags=["core", "runtime"],
    setup_timing="exclude",
    teardown_timing="exclude",
)


@runtime.benchmark(name="direct-python-construction")
def direct_python_construction() -> Leaf:
    return Leaf()


@runtime.benchmark(name="resolve-pre-built-instance")
def resolve_pre_built_instance(instance_container: Container) -> Leaf:
    return instance_container.resolve(Leaf)


@runtime.benchmark(name="resolve-cached-singleton")
def resolve_cached_singleton(singleton_container: Container) -> Leaf:
    return singleton_container.resolve(Leaf)


@runtime.benchmark(name="resolve-transient")
def resolve_transient(transient_container: Container) -> Leaf:
    return transient_container.resolve(Leaf)


@runtime.benchmark(name="resolve-five-component-plan")
def resolve_five_component_plan(graph_container: Container) -> LevelOne:
    return graph_container.resolve(LevelOne)


@runtime.benchmark(name="create-scope")
def create_scope(graph_container: Container) -> Scope:
    return graph_container.new_scope()


@runtime.benchmark(name="resolve-request-slot-plan")
def resolve_request_slot_plan(request_scope: Scope) -> RequestHandler:
    return request_scope.resolve(RequestHandler)


build = Case(
    name="compiled-build",
    tags=["core", "build"],
    setup_timing="exclude",
    teardown_timing="exclude",
)


@build.benchmark(name="build-five-component-container")
def build_five_component_container() -> Container:
    return build_graph_builder().build()


@build.benchmark(name="build-five-component-container-with-entrypoint-diagnostics")
def build_five_component_container_with_entrypoint_diagnostics() -> Container:
    return build_graph_builder(mark_entrypoint=True).build()


@build.benchmark(name="build-scope-overlay")
def build_scope_overlay(graph_container: Container) -> Scope:
    builder = graph_container.new_scope_builder()
    builder.register(Leaf, lifespan="singleton")
    return builder.build()


@build.benchmark(name="build-open-generic-factory-container")
def build_open_generic_factory_container() -> Container:
    builder = ContainerBuilder()
    builder.register(GenericFactoryDependency[int], IntGenericFactoryDependency)
    builder.register(GenericFactoryProduct, factory=create_generic_factory_product)
    builder.register(GenericFactoryConsumer)
    return builder.build()


tooling = Case(
    name="compiler-tooling",
    tags=["core", "tooling"],
    setup_timing="exclude",
    teardown_timing="exclude",
)


@tooling.benchmark(name="create-semantic-manifest")
def create_semantic_manifest(tooling_graph: CompiledGraph) -> GraphManifest:
    uncached = CompiledGraph(tooling_graph.roots, tooling_graph.entrypoints)
    return uncached.manifest(all_roots=True)


@tooling.benchmark(name="diff-identical-manifest")
def diff_identical_manifest(tooling_manifest: GraphManifest) -> GraphDiff:
    return tooling_manifest.diff(tooling_manifest)


@tooling.benchmark(name="diff-single-edge-change")
def diff_single_edge_change(
    tooling_manifest: GraphManifest,
    changed_tooling_manifest: GraphManifest,
) -> GraphDiff:
    return changed_tooling_manifest.diff(tooling_manifest)


allocations = Case(
    name="compiled-allocations",
    tags=["core", "memory"],
    metric_type="memory",
    setup_timing="exclude",
    teardown_timing="exclude",
)


@allocations.benchmark(name="resolve-five-component-plan")
def allocate_five_component_plan(graph_container: Container) -> LevelOne:
    return graph_container.resolve(LevelOne)


@allocations.benchmark(name="create-scope")
def allocate_scope(graph_container: Container) -> Scope:
    return graph_container.new_scope()
