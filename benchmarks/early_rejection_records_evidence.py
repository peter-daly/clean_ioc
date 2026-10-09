"""Fresh-process physical-record and allocation evidence for early exclusions."""

import argparse
import gc
import hashlib
import json
import platform
import resource
import sys
import time
import tracemalloc
from pathlib import Path

import clean_ioc
from clean_ioc import CompilationProfiler, ContainerBuilder
from clean_ioc import component_filters as cf


class Leaf:
    pass


class Middle:
    def __init__(self, leaf: Leaf):
        self.leaf = leaf


class Transport:
    pass


def builder_for(count):
    builder = ContainerBuilder()
    builder.register(Leaf, root_policy="dependency_only")
    builder.register(Middle, root_policy="dependency_only")
    routes = []
    for index in range(count):

        def sender_init(self, transport):
            self.transport = transport

        sender_init.__annotations__ = {"transport": Transport}
        sender = type(f"Sender{index}", (), {"__init__": sender_init})
        routes.append(sender)
        sender_id = builder.register(sender)

        def transport_init(self, middle):
            self.middle = middle

        transport_init.__annotations__ = {"middle": Middle}
        implementation = type(f"Transport{index}", (Transport,), {"__init__": transport_init})
        builder.register(
            Transport,
            implementation,
            root_policy="dependency_only",
            candidate_when=cf.parent(cf.with_id(sender_id)),
        )
    return builder, routes


def source_fingerprint():
    root = Path(clean_ioc.__file__).parent
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*.py")):
        digest.update(str(path.relative_to(root)).encode())
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--diagnostics", action="store_true")
    parser.add_argument("--heap", action="store_true")
    parser.add_argument("--profile", action="store_true")
    parser.add_argument("--routes", type=int, default=64)
    arguments = parser.parse_args()
    builder, routes = builder_for(arguments.routes)
    profile = CompilationProfiler(max_records=0) if arguments.profile else None
    gc.collect()
    if arguments.heap:
        tracemalloc.start()
    started = time.monotonic()
    scope = builder.build(diagnostics=arguments.diagnostics, profile=profile)
    seconds = time.monotonic() - started
    result = {
        "python": platform.python_version(),
        "platform": platform.platform(),
        "diagnostics": arguments.diagnostics,
        "routes": arguments.routes,
        "instrumentation": "tracemalloc" if arguments.heap else "profile" if arguments.profile else "none",
        "seconds": seconds,
        "peak_rss_bytes": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        * (1 if sys.platform == "darwin" else 1024),
        "physical_records": len(scope._plan.graph._records or ()),
        "provider_view_contexts": len(scope._plan.graph._views),
    }
    if arguments.heap:
        gc.collect()
        retained, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        result.update(traced_retained_bytes=retained, traced_peak_bytes=peak)
    if profile is not None:
        result["counters"] = profile.report().counters.to_dict()
    result["source_fingerprint"] = source_fingerprint()
    result["fingerprint"] = scope.graph.manifest(all_roots=True).fingerprint
    result["resolved_types"] = [type(scope.resolve(route).transport).__name__ for route in routes]
    scope.__exit__()
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
