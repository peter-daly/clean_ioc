"""BenchBro microbenchmarks for representative Clean IoC operations."""

from benchbro import Case, system

from clean_ioc import Container, Lifespan


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


@system(scope="session")
def instance_container() -> Container:
    container = Container()
    container.register(Leaf, instance=Leaf())
    return container


@system(scope="session")
def singleton_container() -> Container:
    container = Container()
    container.register(Leaf, lifespan=Lifespan.singleton)
    container.resolve(Leaf)
    return container


@system(scope="session")
def transient_container() -> Container:
    container = Container()
    container.register(Leaf, lifespan=Lifespan.transient)
    return container


@system(scope="session")
def graph_container() -> Container:
    container = Container()
    for service_type in (Leaf, LevelFour, LevelThree, LevelTwo, LevelOne):
        container.register(service_type)
    return container


case = Case(
    name="container-operations",
    tags=["core", "resolution"],
    setup_timing="exclude",
    teardown_timing="exclude",
)


@case.benchmark(name="direct-python-construction")
def direct_python_construction() -> Leaf:
    return Leaf()


@case.benchmark(name="resolve-pre-built-instance")
def resolve_pre_built_instance(instance_container: Container) -> Leaf:
    return instance_container.resolve(Leaf)


@case.benchmark(name="resolve-cached-singleton")
def resolve_cached_singleton(singleton_container: Container) -> Leaf:
    return singleton_container.resolve(Leaf)


@case.benchmark(name="resolve-transient")
def resolve_transient(transient_container: Container) -> Leaf:
    return transient_container.resolve(Leaf)


@case.benchmark(name="resolve-five-node-graph")
def resolve_five_node_graph(graph_container: Container) -> LevelOne:
    return graph_container.resolve(LevelOne)


@case.benchmark(name="explain-five-node-graph")
def explain_five_node_graph(graph_container: Container) -> object:
    return graph_container.explain(LevelOne)
