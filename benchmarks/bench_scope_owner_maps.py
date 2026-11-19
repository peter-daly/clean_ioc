"""Measure scope lifecycles and traced allocations below a root or five overlays."""

import gc
import json
import tracemalloc
from collections.abc import Iterator
from contextlib import ExitStack, contextmanager
from typing import Protocol

from benchbro import Case, system

import clean_ioc
from clean_ioc import ContainerBuilder, ManagedProvider, Scope, ScopeBuilder


class Singleton:
    pass


class Resource:
    pass


def resource() -> Iterator[Resource]:
    yield Resource()


class Operation(Protocol):
    def run(self) -> None: ...


class Implementation:
    def __init__(self, value: Resource):
        self.value = value

    def run(self) -> None:
        pass


@contextmanager
def scope_parents():
    builder = ContainerBuilder().set_provider_roots((ManagedProvider[Resource],))
    builder.register(Singleton, lifespan="singleton")
    builder.register(Resource, factory=resource, lifespan="scoped")
    builder.register(Operation, Implementation, scope="per_call")
    composition = builder.retain_composition()
    with ExitStack() as stack:
        root = parent = stack.enter_context(builder.build())
        for _ in range(5):
            overlay = ScopeBuilder(parent, composition=composition)
            composition = overlay.retain_composition()
            parent = stack.enter_context(overlay.build())
        root.resolve(Singleton)
        yield root, parent, composition


@system(scope="session")
def scope_fixtures():
    with scope_parents() as (root, overlay, composition):
        yield root, overlay, composition, root.resolve(ManagedProvider[Resource]), root.resolve(Operation)


def run_lifecycle(parent: Scope, activate: bool) -> None:
    with parent.new_scope() as child:
        if activate:
            child.resolve(Resource)


OPERATIONS_PER_BATCH = 100

lifecycles = Case(name="scope-owner-map-lifecycles", min_iterations=500)
overlay_builds = Case(name="scope-owner-map-overlay-control", min_iterations=50)


@lifecycles.benchmark()
@lifecycles.parametrize("activate", [False, True], ids=["empty", "resource"])
@lifecycles.parametrize("parent_index", [0, 1], ids=["root", "overlay-chain"])
def ordinary(scope_fixtures, parent_index, activate):
    parent = scope_fixtures[parent_index]
    for _ in range(OPERATIONS_PER_BATCH):
        run_lifecycle(parent, activate)


@lifecycles.benchmark()
def managed(scope_fixtures):
    handle = scope_fixtures[3]
    for _ in range(OPERATIONS_PER_BATCH):
        with handle():
            pass


@lifecycles.benchmark()
def per_call(scope_fixtures):
    operation = scope_fixtures[4]
    for _ in range(OPERATIONS_PER_BATCH):
        operation.run()


@lifecycles.benchmark()
def cached_singleton(scope_fixtures):
    root = scope_fixtures[0]
    for _ in range(OPERATIONS_PER_BATCH):
        root.resolve(Singleton)


@overlay_builds.benchmark()
def build_and_close(scope_fixtures):
    _, parent, composition, _, _ = scope_fixtures
    with ScopeBuilder(parent, composition=composition).build():
        pass


def allocation_sample(parent: Scope, activate: bool) -> dict[str, int]:
    for _ in range(100):
        run_lifecycle(parent, activate)
    scopes = []
    gc.collect()
    tracemalloc.start()
    try:
        for _ in range(1000):
            child = parent.new_scope()
            scopes.append(child)
            if activate:
                child.resolve(Resource)
        gc.collect()
        retained, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
        for child in reversed(scopes):
            child.__exit__()
    return {"retained_bytes": retained, "peak_bytes": peak}


if __name__ == "__main__":
    with scope_parents() as (root, overlay, _):
        samples = {
            f"{label}-{kind}": allocation_sample(parent, activate)
            for label, parent in (("root", root), ("overlay-chain", overlay))
            for kind, activate in (("empty", False), ("resource", True))
        }
    print(json.dumps({"source": clean_ioc.__file__, "samples": samples}, indent=2))
