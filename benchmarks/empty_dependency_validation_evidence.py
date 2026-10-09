"""Fresh-process frozen-wheel comparison of repeated parameterless infrastructure.

Uses actual Bark time/header helpers in a synthetic multi-route graph. Normal
timings, traced allocations and diagnostic signature/counter runs are separate.
No source override, global signature cache or garbage-collection change is used.
"""

import argparse
import gc
import hashlib
import inspect
import json
import platform
import resource
import sys
import time
import tracemalloc
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import clean_ioc
from clean_ioc import CompilationProfiler, ContainerBuilder
from clean_ioc._legacy import Dependency


def source_fingerprint(package):
    root = Path(package.__file__).parent
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*.py")):
        digest.update(str(path.relative_to(root)).encode())
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def builder_for(routes, contextual, counts):
    from bark_core.messaging import (  # ty: ignore[unresolved-import]
        HeaderBasedPrefixResolver,
        ResolveQueueNameFromHeader,
    )
    from bark_core.utilities import UtcDatetimeProvider  # ty: ignore[unresolved-import]

    leaves = (UtcDatetimeProvider, HeaderBasedPrefixResolver, ResolveQueueNameFromHeader)
    builder = ContainerBuilder()

    def selected(component):
        counts["callbacks"] += 1
        # Record parent context in the callback's observable result. Arbitrary
        # filters must run independently of the invariant compilation shortcut.
        if component.parent is None:
            raise RuntimeError("Expected a dependency occurrence")
        return True

    for leaf in leaves:
        options = {"when": selected} if contextual else {}
        builder.register(leaf, lifespan="transient", root_policy="dependency_only", **options)

    def infrastructure_init(self, clock, prefix, queue):
        counts["infrastructure_activations"] += 1
        self.clock, self.prefix, self.queue = clock, prefix, queue

    infrastructure_init.__annotations__ = dict(zip(("clock", "prefix", "queue"), leaves, strict=True))
    infrastructure = type("Infrastructure", (), {"__init__": infrastructure_init})
    builder.register(infrastructure, lifespan="transient", root_policy="dependency_only")
    route_types = []
    for index in range(routes):

        def route_init(self, clock, prefix, queue, infrastructure):
            counts["route_activations"] += 1
            self.clock, self.prefix, self.queue, self.infrastructure = clock, prefix, queue, infrastructure

        route_init.__annotations__ = dict(zip(("clock", "prefix", "queue"), leaves, strict=True)) | {
            "infrastructure": infrastructure
        }
        route = type(f"Route{index}", (), {"__init__": route_init})
        builder.register(route)
        route_types.append(route)
    return builder, route_types, leaves


def main():
    import bark_core  # ty: ignore[unresolved-import]

    from clean_ioc import container as compiler_module

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--routes", type=int, default=256)
    parser.add_argument("--contextual", action="store_true")
    parser.add_argument("--diagnostics", action="store_true")
    parser.add_argument("--measurement", choices=("normal", "heap", "counts"), default="normal")
    args = parser.parse_args()
    if "site-packages" not in str(clean_ioc.__file__) or "site-packages" not in str(bark_core.__file__):
        raise RuntimeError("Evidence must use installed wheels outside the source repositories")
    counts = {"callbacks": 0, "infrastructure_activations": 0, "route_activations": 0}
    builder, route_types, leaves = builder_for(args.routes, args.contextual, counts)
    profile = None
    if args.measurement == "counts":
        profile = CompilationProfiler(max_records=0)
        original_parse = getattr(inspect, "_signature_fromstr")
        original_validate = compiler_module._validate_dependency_names
        counts.update(builtin_signature_parses=0, empty_name_validations=0, nonempty_name_validations=0)

        def counted_parse(*positional, **keywords):
            counts["builtin_signature_parses"] += 1
            return original_parse(*positional, **keywords)

        def counted_validate(implementation: Any, dependencies: Mapping[str, Dependency]) -> None:
            counts["nonempty_name_validations" if dependencies else "empty_name_validations"] += 1
            return original_validate(implementation, dependencies)

        setattr(inspect, "_signature_fromstr", counted_parse)
        setattr(compiler_module, "_validate_dependency_names", counted_validate)
    # Identical pre-build collection in both stages. Heap sampling begins after
    # imports and registration; only retained sampling collects after the build.
    gc.collect()
    imported_modules = len(sys.modules)
    if args.measurement == "heap":
        tracemalloc.start()
    started = time.monotonic()
    owner = builder.build(
        provider_roots=(),
        allow_scope_builders=False,
        check_unreachable=False,
        aggregate_errors=False,
        diagnostics=args.diagnostics,
        profile=profile,
    )
    seconds = time.monotonic() - started
    peak_rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * (1 if sys.platform == "darwin" else 1024)
    result = {
        "python": platform.python_version(),
        "platform": platform.platform(),
        "routes": args.routes,
        "contextual": args.contextual,
        "diagnostics": args.diagnostics,
        "instrumentation": args.measurement,
        "seconds": seconds,
        "peak_rss_bytes": peak_rss,
        "imported_modules_before_build": imported_modules,
        "build_counts": dict(counts),
    }
    if args.measurement == "heap":
        current, peak = tracemalloc.get_traced_memory()
        gc.collect()
        retained, _ = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        result.update(traced_immediate_bytes=current, traced_retained_bytes=retained, traced_peak_bytes=peak)
    if counts["route_activations"] or counts["infrastructure_activations"]:
        raise RuntimeError("Build activated constructors")
    expected_callbacks = args.routes * 6 if args.contextual else 0
    if counts["callbacks"] != expected_callbacks:
        raise RuntimeError("Context callbacks changed")
    result.update(
        manifest_fingerprint=owner.graph.manifest(all_roots=True).fingerprint,
        validation_fingerprint=hashlib.sha256(owner.validation_report().to_json().encode()).hexdigest(),
        physical_records=len(owner._plan.graph._records or ()),
        provider_view_contexts=len(owner._plan.graph._views),
        public_roots=len(owner.components),
        catalogue_entries=len(owner.selected_registrations),
        profiler_counters=None if profile is None else profile.report().counters.to_dict(),
    )
    for route in route_types:
        value = owner.resolve(route)
        for argument, leaf in zip(("clock", "prefix", "queue"), leaves, strict=True):
            direct = getattr(value, argument)
            nested = getattr(value.infrastructure, argument)
            if type(direct) is not leaf or type(nested) is not leaf or direct is nested:
                raise RuntimeError("Runtime parameterless transient dependencies changed")
    if counts["route_activations"] != args.routes or counts["infrastructure_activations"] != args.routes:
        raise RuntimeError("Runtime activation counts changed")
    result["runtime_counts"] = dict(counts)
    result["clean_source_fingerprint"] = source_fingerprint(clean_ioc)
    result["bark_source_fingerprint"] = source_fingerprint(bark_core)
    print(json.dumps(result, sort_keys=True))
    owner.__exit__()


if __name__ == "__main__":
    main()
