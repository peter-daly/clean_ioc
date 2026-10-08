"""Fresh-process installed-wheel evidence for optional diagnostic root retries.

Use the frozen step-5 wheel in baseline mode and step-6 in aggregate/no-retry
modes. Each root has six independent dependency-only stages plus its own missing
request. Constructors/factories never run on the failure path. No source override.
"""

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
from clean_ioc import ContainerBuilder, ContainerBuildError
from clean_ioc.container import _Compiler


def source_fingerprint(module):
    digest = hashlib.sha256()
    root = Path(module.__file__).parent
    for path in sorted(root.rglob("*.py")):
        digest.update(str(path.relative_to(root)).encode())
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def builder_for(roots, depth, valid, counters):
    builder = ContainerBuilder()
    retained_types = []

    def selected(component):
        counters["callbacks"] += 1
        return True

    def dormant(child):
        raise RuntimeError("A failed build must not activate a factory")

    def leaf_factory():
        return object()

    for index in range(roots):
        dependency = type(f"Leaf{index}", (), {})
        retained_types.append(dependency)
        builder.register(dependency, factory=leaf_factory, when=selected, root_policy="dependency_only")
        for level in range(depth - 1):
            stage = type(f"Stage{index}_{level}", (), {})
            retained_types.append(stage)

            # Return the injected child on the valid execution path.
            def stage_factory(child):
                return child

            stage_factory.__annotations__ = {"child": dependency, "return": stage}
            builder.register(stage, factory=stage_factory, when=selected, root_policy="dependency_only")
            dependency = stage
        missing = type(f"Missing{index}", (), {})
        root = type(f"Root{index}", (), {})
        retained_types.extend((missing, root))

        def root_factory(child, required):
            return child, required

        root_factory.__annotations__ = {"child": dependency, "required": missing, "return": root}
        builder.register(root, factory=root_factory)
        builder.mark_entrypoint(root)
        if valid:
            builder.register(missing, factory=leaf_factory, root_policy="dependency_only")
    # Keep one explicitly dormant function alive to make activation refusal clear.
    retained_types.append(dormant)
    return builder, retained_types


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--roots", type=int, default=120)
    parser.add_argument("--depth", type=int, default=6)
    parser.add_argument("--mode", choices=("baseline", "aggregate", "no-retry"), required=True)
    parser.add_argument("--heap", action="store_true")
    parser.add_argument("--diagnostics", action="store_true")
    parser.add_argument("--valid", action="store_true")
    args = parser.parse_args()
    warmup, _ = builder_for(0, args.depth, True, {"callbacks": 0})
    warmup.build(provider_roots=(), allow_scope_builders=False).__exit__()
    del warmup
    gc.collect()
    counts = {"callbacks": 0, "compiler_attempts": 0}
    original_compile = _Compiler.compile

    def counted_compile(self, *positional, **keywords):
        counts["compiler_attempts"] += 1
        return original_compile(self, *positional, **keywords)

    _Compiler.compile = counted_compile
    if args.heap:
        tracemalloc.start()
    builder, retained_types = builder_for(args.roots, args.depth, args.valid, counts)
    kwargs = {} if args.mode == "baseline" else {"aggregate_errors": args.mode == "aggregate"}
    runtime, failure = None, None
    started = time.monotonic()
    try:
        runtime = builder.build(
            provider_roots=(),
            allow_scope_builders=False,
            check_unreachable=False,
            diagnostics=args.diagnostics,
            **kwargs,
        )
    except ContainerBuildError as error:
        failure = error
    seconds = time.monotonic() - started
    # Failure tracing includes diagnostic construction/tracebacks until sampling;
    # no retained-runtime comparison is implied for invalid builds.
    result = {
        "mode": args.mode,
        "python": platform.python_version(),
        "platform": platform.platform(),
        "independent_roots": args.roots,
        "dependency_stages_per_root": args.depth,
        "retained_fixture_definitions": len(retained_types),
        "diagnostics": args.diagnostics,
        "valid": args.valid,
        "instrumentation": "tracemalloc" if args.heap else "none",
        "seconds": seconds,
        "peak_rss_bytes": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        * (1 if sys.platform == "darwin" else 1024),
        **counts,
    }
    if args.heap:
        current, peak = tracemalloc.get_traced_memory()
        result.update(traced_live_failure_bytes=current, traced_peak_bytes=peak)
        tracemalloc.stop()
    if args.valid:
        if runtime is None or failure is not None:
            raise RuntimeError("Valid fixture failed compilation")
        result.update(
            manifest_fingerprint=runtime.graph.manifest(all_roots=True).fingerprint,
            validation_fingerprint=hashlib.sha256(runtime.validation_report().to_json().encode()).hexdigest(),
            physical_records=len(runtime._plan.graph._records or ()),
            provider_views=len(runtime._plan.graph._views),
            catalogue_entries=len(runtime.selected_registrations),
            root_count=len(runtime.components),
        )
        for root in runtime.components:
            runtime.resolve(root.service_type)
        runtime.__exit__()
    else:
        if failure is None or runtime is not None or failure.report is None or builder._built:
            raise RuntimeError("Invalid fixture was admitted or consumed its builder")
        issues = failure.report.errors
        if any(issue.code != "missing-component" for issue in issues):
            raise RuntimeError("Expected only missing dependency failures")
        if not issues[0].path[-1].endswith(".Missing0"):
            raise RuntimeError("Original first failure changed")
        result.update(
            errors=len(issues),
            checked_diagnostic_roots=failure.report.checked_roots,
            primary_error_code=issues[0].code,
            first_path_fingerprint=hashlib.sha256(json.dumps(issues[0].path).encode()).hexdigest(),
            partial_attempts=None if failure.partial_graph is None else failure.partial_graph.total_attempts,
            partial_retained_attempts=None if failure.partial_graph is None else len(failure.partial_graph.attempts),
            evidence_count=len(failure.evidence),
            builder_reusable=not builder._built,
        )
    result["clean_source_fingerprint"] = source_fingerprint(clean_ioc)
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
