"""BenchBro experiments for Clean IoC 2 build and runtime boundaries."""

from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from typing import Any, Generic, TypeVar

from benchbro import Case, system

from clean_ioc import (
    Assembly,
    BuildIssue,
    BuildReport,
    CompiledGraph,
    ComponentBuilder,
    Container,
    ContainerBuilder,
    Expose,
    GraphDiff,
    GraphManifest,
    OwnershipReport,
    Provider,
    Scope,
    Use,
    ValidationContext,
)


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


class ProviderLevelOne:
    def __init__(self, child: Provider[LevelTwo]):
        self.child = child


@contextmanager
def create_managed_leaf() -> Iterator[Leaf]:
    yield Leaf()


def foundation_bundle(builder: ComponentBuilder) -> None:
    for service_type in (Leaf, LevelFour, LevelThree):
        builder.register(service_type)


def application_bundle(builder: ComponentBuilder) -> None:
    for service_type in (LevelTwo, LevelOne):
        builder.register(service_type)


def validate_graph_walk(context: ValidationContext) -> Iterable[BuildIssue]:
    for _ in context.graph.walk():
        pass
    return ()


def validate_implementation_asts(context: ValidationContext) -> Iterable[BuildIssue]:
    inspected: set[type] = set()
    for visit in context.graph.walk():
        implementation_type = visit.component.implementation_type
        if implementation_type in inspected:
            continue
        inspected.add(implementation_type)
        context.type_ast(implementation_type)
    return ()


def build_graph_builder(*, mark_entrypoint: bool = False) -> ContainerBuilder:
    builder = ContainerBuilder()
    for service_type in (Leaf, LevelFour, LevelThree, LevelTwo, LevelOne):
        builder.register(service_type)
    if mark_entrypoint:
        builder.mark_entrypoint(LevelOne)
    return builder


def build_feature_graph(scenario: str) -> Container:
    if scenario in {"core", "ordinary-validation", "deferred-strict-validation"}:
        builder = build_graph_builder()
        if scenario == "ordinary-validation":
            builder.add_validation_rule(validate_graph_walk)
        elif scenario == "deferred-strict-validation":
            builder.add_validation_rule(validate_implementation_asts, strict_only=True)
        return builder.build()

    if scenario == "resource-ownership":
        builder = ContainerBuilder()
        builder.register(Leaf, factory=create_managed_leaf, lifespan="transient")
        for service_type in (LevelFour, LevelThree, LevelTwo, LevelOne):
            builder.register(service_type, lifespan="singleton")
        return builder.build()

    if scenario == "typed-provider":
        builder = ContainerBuilder()
        for service_type in (Leaf, LevelFour, LevelThree, LevelTwo, ProviderLevelOne):
            builder.register(service_type)
        return builder.build()

    if scenario == "assembly-boundaries":
        builder = ContainerBuilder()
        builder.install_assembly(
            Assembly(
                "foundation",
                foundation_bundle,
                exposes=(Expose(LevelThree),),
            )
        )
        builder.install_assembly(
            Assembly(
                "application",
                application_bundle,
                uses=(Use("foundation", LevelThree),),
                exposes=(Expose(LevelOne),),
            )
        )
        return builder.build()

    raise ValueError(f"Unknown compiler feature scenario: {scenario}")


def build_transient_chain(depth: int) -> tuple[Container, type]:
    """Build a compiled constructor chain with exactly ``depth`` components."""

    builder = ContainerBuilder()
    child_type = type(f"ScaledLeaf{depth}", (), {})
    builder.register(child_type, lifespan="transient")
    for index in range(1, depth):
        dependency_type = child_type

        def init(self: Any, child: object) -> None:
            self.child = child

        init.__annotations__ = {"child": dependency_type, "return": None}
        child_type = type(f"ScaledNode{depth}_{index}", (), {"__init__": init})
        builder.register(child_type, lifespan="transient")
    return builder.build(), child_type


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
def scaled_transient_containers() -> dict[int, tuple[Container, type]]:
    return {depth: build_transient_chain(depth) for depth in (1, 5, 20, 50)}


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


@system(scope="session")
def strict_graph_validation_container() -> Container:
    builder = build_graph_builder()
    builder.add_validation_rule(validate_graph_walk, strict_only=True)
    return builder.build()


@system(scope="session")
def strict_ast_validation_container() -> Container:
    builder = build_graph_builder()
    builder.add_validation_rule(validate_implementation_asts, strict_only=True)
    return builder.build()


@system(scope="session")
def ownership_graph() -> CompiledGraph:
    return build_feature_graph("resource-ownership").graph


runtime = Case(
    name="compiled-runtime",
    tags=["core", "runtime"],
    min_iterations=20_000,
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


scaling = Case(
    name="compiled-runtime-scaling",
    tags=["core", "runtime", "scaling"],
    min_iterations=20_000,
    setup_timing="exclude",
    teardown_timing="exclude",
)


@scaling.benchmark(name="resolve-transient-chain")
@scaling.parametrize("depth", [1, 5, 20, 50], ids=["depth-1", "depth-5", "depth-20", "depth-50"])
def resolve_transient_chain(scaled_transient_containers: dict[int, tuple[Container, type]], depth: int) -> object:
    container, root_type = scaled_transient_containers[depth]
    return container.resolve(root_type)


build = Case(
    name="compiled-build",
    tags=["core", "build"],
    min_iterations=100,
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


build_features = Case(
    name="compiled-build-features",
    tags=["core", "build", "compiler-features"],
    min_iterations=100,
    setup_timing="exclude",
    teardown_timing="exclude",
)


@build_features.benchmark(name="build-five-component-graph")
@build_features.parametrize(
    "scenario",
    [
        "core",
        "ordinary-validation",
        "deferred-strict-validation",
        "resource-ownership",
        "typed-provider",
        "assembly-boundaries",
    ],
    ids=[
        "core",
        "ordinary-validation",
        "deferred-strict-validation",
        "resource-ownership",
        "typed-provider",
        "assembly-boundaries",
    ],
)
def build_five_component_feature_graph(scenario: str) -> Container:
    return build_feature_graph(scenario)


validation = Case(
    name="compiler-validation",
    tags=["core", "tooling", "compiler-features", "validation"],
    min_iterations=500,
    setup_timing="exclude",
    teardown_timing="exclude",
)


@validation.benchmark(name="run-deferred-graph-walk")
def run_deferred_graph_walk(strict_graph_validation_container: Container) -> BuildReport:
    return strict_graph_validation_container.validation_report(include_strict_rules=True)


@validation.benchmark(name="run-deferred-type-ast-inspection")
def run_deferred_type_ast_inspection(strict_ast_validation_container: Container) -> BuildReport:
    return strict_ast_validation_container.validation_report(include_strict_rules=True)


tooling = Case(
    name="compiler-tooling",
    tags=["core", "tooling"],
    min_iterations=500,
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


@tooling.benchmark(name="create-resource-ownership-report")
def create_resource_ownership_report(ownership_graph: CompiledGraph) -> OwnershipReport:
    uncached = CompiledGraph(
        ownership_graph.roots,
        ownership_graph.entrypoints,
        ownership_graph.assemblies,
    )
    return uncached.ownership_report()


allocations = Case(
    name="compiled-allocations",
    tags=["core", "memory"],
    metric_type="memory",
    min_iterations=20_000,
    setup_timing="exclude",
    teardown_timing="exclude",
)


@allocations.benchmark(name="resolve-five-component-plan")
def allocate_five_component_plan(graph_container: Container) -> LevelOne:
    return graph_container.resolve(LevelOne)


@allocations.benchmark(name="create-scope")
def allocate_scope(graph_container: Container) -> Scope:
    return graph_container.new_scope()
