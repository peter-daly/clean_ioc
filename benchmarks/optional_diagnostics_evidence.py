"""Fresh-process comparison of normal and diagnostic compilation allocations."""

import argparse
import gc
import json
import platform
import resource
import sys
import time
import tracemalloc

from clean_ioc import ContainerBuilder


class Leaf:
    pass


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--diagnostics", action="store_true")
    parser.add_argument("--heap", action="store_true")
    parser.add_argument("--routes", type=int, default=256)
    arguments = parser.parse_args()
    builder = ContainerBuilder()
    previous = Leaf
    builder.register(Leaf, root_policy="dependency_only")
    for index in range(8):

        def init(self, dependency):
            self.dependency = dependency

        init.__annotations__ = {"dependency": previous}
        previous = type(f"Middle{index}", (), {"__init__": init})
        builder.register(previous, root_policy="dependency_only")
    for index in range(arguments.routes):

        def init(self, dependency):
            self.dependency = dependency

        init.__annotations__ = {"dependency": previous}
        builder.register(type(f"Route{index}", (), {"__init__": init}))
    gc.collect()
    if arguments.heap:
        tracemalloc.start()
    started = time.monotonic()
    scope = builder.build(diagnostics=arguments.diagnostics)
    seconds = time.monotonic() - started
    result = {
        "python": platform.python_version(),
        "platform": platform.platform(),
        "diagnostics": arguments.diagnostics,
        "routes": arguments.routes,
        "instrumentation": "tracemalloc" if arguments.heap else "none",
        "seconds": seconds,
        "peak_rss_bytes": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        * (1 if sys.platform == "darwin" else 1024),
        "physical_records": len(scope._plan.graph._records or ()),
        "provider_view_contexts": len(scope._plan.graph._views),
        "occurrence_explanations": len(scope._plan.occurrence_explanations),
        "parameter_explanations": len(scope._plan.parameter_explanations),
        "generic_explanations": len(scope._plan.generic_explanations),
    }
    if arguments.heap:
        gc.collect()
        retained, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        result.update(traced_retained_bytes=retained, traced_peak_bytes=peak)
    result["fingerprint"] = scope.graph.manifest(all_roots=True).fingerprint
    scope.__exit__()
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
