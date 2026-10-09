"""Fresh-process comparison of repeated, invariant infrastructure compilation.

The disabled mode changes only the private cache's lookups/stores; all candidate
selection, existing executable interning, graph allocation and validation remain.
Imports and builder registration precede timing and optional allocation tracing.
"""

import argparse
import json
import platform
import resource
import sys
import time
import tracemalloc
from typing import Any

from clean_ioc import CompilationProfiler, ContainerBuilder
from clean_ioc.container import _Compiler


class _DisabledCache(dict):
    def get(self, key, default=None):
        return default

    def __setitem__(self, key, value):
        pass


def builder_for(count):
    builder = ContainerBuilder()
    previous = type("InfrastructureLeaf", (), {})
    builder.register(previous, lifespan="transient", root_policy="dependency_only")
    for index in range(6):

        def init(self, left, right):
            self.left, self.right = left, right

        init.__annotations__ = {"left": previous, "right": previous}
        current = type(f"Infrastructure{index}", (), {"__init__": init})
        builder.register(current, lifespan="transient", root_policy="dependency_only")
        previous = current
    for index in range(count):

        def init(self, infrastructure):
            self.infrastructure = infrastructure

        init.__annotations__ = {"infrastructure": previous}
        route = type(f"Route{index}", (), {"__init__": init})
        builder.register(route)
    return builder


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--routes", type=int, default=64)
    parser.add_argument("--cache", choices=("enabled", "disabled"), default="enabled")
    parser.add_argument("--trace", action="store_true")
    args = parser.parse_args()
    if args.cache == "disabled":
        original = _Compiler.__init__

        def initialize(self, *positional, **keywords):
            original(self, *positional, **keywords)
            self._invariant_subplans = _DisabledCache()

        _Compiler.__init__ = initialize
    builder = builder_for(args.routes)
    profile = CompilationProfiler(max_records=0)
    if args.trace:
        tracemalloc.start()
    started = time.monotonic()
    owner = builder.build(profile=profile)
    elapsed = time.monotonic() - started
    allocations = tracemalloc.get_traced_memory() if args.trace else None
    if args.trace:
        tracemalloc.stop()
    rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    result: dict[str, Any] = {
        "cache": args.cache,
        "python": platform.python_version(),
        "platform": platform.platform(),
        "routes": args.routes,
        "seconds": elapsed,
        "peak_rss_bytes": rss if sys.platform == "darwin" else rss * 1024,
        "traced_current_bytes": None if allocations is None else allocations[0],
        "traced_peak_bytes": None if allocations is None else allocations[1],
        "physical_component_records": len(owner._plan.graph._records or ()),
        "counters": profile.report().counters.to_dict(),
        "instrumentation": "CompilationProfiler(max_records=0)" + (" + tracemalloc" if args.trace else ""),
    }
    print(json.dumps(result, sort_keys=True))
    owner.__exit__()


if __name__ == "__main__":
    main()
