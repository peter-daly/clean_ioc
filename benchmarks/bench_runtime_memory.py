"""Memory and time for execution storage, graph finalization and scope cleanup.

Graph cases include declarations, build (or verify + create_runtime), and close.
They reuse the template/provider/decorator fixture without activating services.
Memory cases measure traced peak allocations, not RSS or retained heap. Scope
batches keep 1,000 scopes alive at once; their parent is prepared outside tracing.
Time cases measure one scope's complete lifecycle, including resource cleanup.
Graph measurements inherit automatic GC; scope measurements disable it.
"""

import gc
from collections.abc import Iterator

from benchbro import Case, system

from benchmarks.graph_memory_fixture import build
from clean_ioc import ContainerBuilder


class Resource:
    pass


def resource() -> Iterator[Resource]:
    yield Resource()


@system(scope="session")
def memory_parent():
    builder = ContainerBuilder().set_provider_roots(())
    builder.register(Resource, factory=resource, lifespan="scoped")
    with builder.build() as runtime:
        yield runtime


scope_time = Case(name="memory-scope-time", tags=["memory-improvements"], min_iterations=1000)
scope_memory = Case(name="memory-scope-peak", tags=["memory-improvements"], metric_type="memory", min_iterations=1)
graph_time = Case(name="memory-graph-time", tags=["memory-improvements"], min_iterations=1, gc_control="inherit")
graph_memory = Case(
    name="memory-graph-peak",
    tags=["memory-improvements"],
    metric_type="memory",
    min_iterations=1,
    gc_control="inherit",
)


@scope_time.benchmark()
@scope_time.parametrize("activate", [False, True], ids=["empty", "resource"])
def scope_lifecycle(memory_parent, activate):
    with memory_parent.new_scope() as scope:
        if activate:
            scope.resolve(Resource)


@scope_memory.benchmark()
@scope_memory.parametrize("activate", [False, True], ids=["empty", "resource"])
def concurrent_scopes(memory_parent, activate):
    scopes = []
    try:
        for _ in range(1000):
            scope = memory_parent.new_scope()
            scopes.append(scope)
            if activate:
                scope.resolve(Resource)
    finally:
        for scope in reversed(scopes):
            scope.__exit__()


def compile_graph(operation):
    fixture = build(2, operation=operation)
    try:
        fixture.runtime.__exit__()
    finally:
        if fixture.analysis is not None:
            fixture.analysis.close()


@graph_time.benchmark()
@graph_time.parametrize("operation", ["build", "verify"], ids=["build", "verify-runtime"])
def graph_lifecycle(operation):
    compile_graph(operation)


@graph_memory.benchmark()
@graph_memory.parametrize("operation", ["build", "verify"], ids=["build", "verify-runtime"])
def graph_allocations(operation):
    # Release cycles from the preceding sample before creating another graph.
    gc.collect()
    compile_graph(operation)
