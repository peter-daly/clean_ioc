"""Fresh-process diagnostic-label allocation probe, with optional traced heap.

Run this same file with each checkout on PYTHONPATH. Heap tracing is a separate
allocation run; its elapsed time is not comparable to ordinary compilation.
"""

import argparse
import json
import platform
import resource
import sys
import time
from collections.abc import Mapping
from dataclasses import fields, is_dataclass
from typing import Generic, TypeVar

from clean_ioc import ContainerBuilder

T = TypeVar("T")


class Leaf(Generic[T]):
    pass


class Middle(Generic[T]):
    def __init__(self, leaf: Leaf[T]):
        self.leaf = leaf


class Infrastructure(Generic[T]):
    def __init__(self, middle: Middle[T]):
        self.middle = middle


def diagnostic_storage(plan):
    pending = [plan.occurrence_explanations, plan.parameter_explanations, plan.generic_explanations]
    strings = {}
    seen = set()
    while pending:
        value = pending.pop()
        if id(value) in seen:
            continue
        seen.add(id(value))
        if isinstance(value, str):
            strings[id(value)] = value
        elif is_dataclass(value):
            pending.extend(getattr(value, item.name) for item in fields(value))
        elif isinstance(value, Mapping):
            pending.extend(value.values())
        elif isinstance(value, tuple):
            pending.extend(value)
    return {
        "retained_diagnostic_string_objects": len(strings),
        "distinct_diagnostic_strings": len(set(strings.values())),
        "retained_diagnostic_string_bytes": sum(sys.getsizeof(value) for value in strings.values()),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--routes", type=int, default=256)
    parser.add_argument("--heap", action="store_true")
    args = parser.parse_args()
    annotation = dict[str, tuple[list[int], ...]]
    builder = ContainerBuilder()
    for service in (Leaf[annotation], Middle[annotation], Infrastructure[annotation]):
        builder.register(service, root_policy="dependency_only")
    for index in range(args.routes):

        def init(self, infrastructure):
            self.infrastructure = infrastructure

        init.__annotations__ = {"infrastructure": Infrastructure[annotation]}
        builder.register(type(f"Route{index}", (), {"__init__": init}))
    if args.heap:
        import tracemalloc

        tracemalloc.start()
    started = time.monotonic()
    owner = builder.build()
    elapsed = time.monotonic() - started
    result = {
        "routes": args.routes,
        "python": platform.python_version(),
        "platform": platform.platform(),
        "instrumentation": "tracemalloc" if args.heap else "none",
        "seconds": elapsed,
        "peak_rss_bytes": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        * (1 if sys.platform == "darwin" else 1024),
        "physical_records": len(owner._plan.graph._records or ()),
        "provider_view_contexts": len(owner._plan.graph._views),
        **diagnostic_storage(owner._plan),
    }
    if args.heap:
        current, peak = tracemalloc.get_traced_memory()
        result.update(traced_retained_bytes=current, traced_peak_bytes=peak)
    print(json.dumps(result, sort_keys=True))
    owner.__exit__()


if __name__ == "__main__":
    main()
