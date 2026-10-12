# ruff: noqa: E402, S101
"""Bounded retained callback graph/late generic inspection comparison."""

import gc
import json
import os
import platform
import resource
import sys
import time
import tracemalloc
from typing import Generic, TypeVar

from source_loader import LOADED, install

policy, mode, kind = sys.argv[1:]
install(policy)
from clean_ioc import ContainerBuilder, DecoratorTemplate, DerivedServices
from clean_ioc.components import _ComponentGraph, _ComponentRecord

T = TypeVar("T")


class Resource:
    pass


class Source:
    def __init__(self, resource: Resource):
        self.resource = resource


class Target(Generic[T]):
    def __init__(self, resource: Resource):
        self.resource = resource


class Wrapper:
    def __init__(self, inner: Target[int]):
        self.inner = inner


saved = []
calls = []


def source_filter(component):
    assert component.dependencies[0].service_type is Resource
    saved.append(component)
    calls.append("source")
    return True


def when(component):
    saved.append(component)
    calls.append("when")
    return True


def position(decorator, component):
    saved.extend((decorator, component))
    calls.append("position")
    return 4


def inspect_saved():
    result = []
    for component in saved:
        result.append(
            (
                component.id,
                component.occurrence_id,
                component.position,
                component.boundary,
                component.owner_occurrence_id,
                tuple(component.generic_mapping.items()),
                tuple((child.id, child.argument) for child in component.descendants()),
            )
        )
    return result


def memory():
    gc.collect()
    current, peak = tracemalloc.get_traced_memory()
    return {"retained": current, "peak": peak, "peak_rss": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss}


if kind == "heap":
    tracemalloc.start()
start = time.perf_counter()
builder = ContainerBuilder()
builder.set_provider_roots(())
builder.register(Resource)
builder.register(Source)
for index in range(64):
    builder.register(Target[int], name=str(index))
builder.register_decorator_template(
    for_each=Source,
    source_filter=source_filter,
    template=lambda _: DecoratorTemplate(DerivedServices(Target[int]), Wrapper, when=when, position=position),
)
runtime = builder.build(mode=mode)  # ty: ignore[invalid-argument-type]
del builder
build_time = time.perf_counter() - start
prepared = memory()
start = time.perf_counter()
first = inspect_saved()
first_time = time.perf_counter() - start
first_memory = memory()
start = time.perf_counter()
second = inspect_saved()
second_time = time.perf_counter() - start
assert first == second
second_memory = memory()
graphs = {id(c._graph): c._graph for c in saved}
records = {id(r): r for g in graphs.values() for r in g._records.values()}
assert all(isinstance(r, _ComponentRecord) for r in records.values())
assert all(not g._drafts and not g._views and not g._definitions.definitions for g in graphs.values())
counts = {
    "saved_views": len(saved),
    "graphs": len(graphs),
    "records": len(records),
    "definitions": len({id(r._definition) for r in records.values()}),
    "calls": {k: calls.count(k) for k in set(calls)},
}
del graphs, records, first, second
runtime.__exit__(None, None, None)
del runtime
gc.collect()
assert len(inspect_saved()) == len(saved)
only_saved = memory()
saved.clear()
gc.collect()
released = memory()
remaining = {
    "graphs": sum(type(x) is _ComponentGraph for x in gc.get_objects()),
    "records": sum(type(x) is _ComponentRecord for x in gc.get_objects()),
}
print(
    json.dumps(
        {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "pid": os.getpid(),
            "policy": policy,
            "mode": mode,
            "kind": kind,
            "source": LOADED,
            "build_seconds": build_time,
            "first_inspection_seconds": first_time,
            "second_inspection_seconds": second_time,
            "prepared": prepared,
            "first_inspection": first_memory,
            "second_inspection": second_memory,
            "only_saved": only_saved,
            "released": released,
            "counts": counts,
            "remaining": remaining,
        }
    )
)
