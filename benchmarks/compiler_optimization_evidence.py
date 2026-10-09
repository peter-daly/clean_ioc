"""Separate allocation/count/cProfile probes; never latency baselines.

Run from repo root with `uv run python -m benchmarks.compiler_optimization_evidence`.
Writes /tmp outputs by default. Private plan inspection emits aggregate counts and
shallow executable storage only, never values, identities, callback state or owners.
"""

import argparse
import cProfile
import gc
import json
import pstats
import statistics
import sys
import tracemalloc
from collections import Counter
from dataclasses import fields, is_dataclass
from pathlib import Path
from typing import Any, cast

from clean_ioc import CompilationProfiler, ContainerBuildError
from clean_ioc.container import _Step

from . import bench_compiler_optimization as workloads

_LINK_FIELDS = frozenset(
    {
        "step",
        "target",
        "inner",
        "dependencies",
        "pre_configurations",
        "decorators",
        "members",
        "resolution_requests",
        "targets",
        "plans",
    }
)


def executable_inventory(owner) -> dict:
    """Count distinct retained steps across roots, providers and warmup roots.

    Includes shallow storage for steps, edge records and their tuple containers.
    Excludes graph/blueprint metadata, registrations, values, owners, Python code,
    runtime caches/coordinators, and allocator overhead; this is a lower bound.
    """
    plan = owner._plan
    pending = [root for roots in plan.roots.values() for root in roots]
    pending += [root for roots in plan.provider_roots.values() for root in roots]
    pending += [root for roots in plan.warmup_steps.values() for root in roots]
    seen = set()
    counts = Counter()
    bytes_total = 0
    edge_records = 0
    tuple_count = 0
    while pending:
        value = pending.pop()
        identity = id(value)
        if identity in seen:
            continue
        seen.add(identity)
        if isinstance(value, tuple):
            tuple_count += 1
            bytes_total += sys.getsizeof(value)
            pending.extend(value)
        elif is_dataclass(value) and type(value).__module__ == "clean_ioc.container":
            bytes_total += sys.getsizeof(value)
            if isinstance(value, _Step):
                counts[type(value).__name__] += 1
            else:
                edge_records += 1
            for item in fields(value):
                if item.name in _LINK_FIELDS:
                    pending.append(getattr(value, item.name))
    visits = list(owner.graph.walk())
    return {
        "retained_unique_steps": sum(counts.values()),
        "step_classes": dict(sorted(counts.items())),
        "executable_shallow_bytes_lower_bound": bytes_total,
        "root_and_edge_records": edge_records,
        "executable_tuple_count": tuple_count,
        "graph_walk_visits": len(visits),
        "unique_graph_occurrences": len({visit.component.occurrence_id for visit in visits}),
        "maximum_graph_path_components": max((len(visit.components) for visit in visits), default=0),
    }


def allocation_samples(shape: str) -> dict:
    # Warm stable typing caches first; allocation is the next fresh builder build.
    with workloads.make_builder(shape).build(**workloads.build_inputs(shape)):
        pass
    samples = []
    for _ in range(5):
        builder = workloads.make_builder(shape)
        inputs = workloads.build_inputs(shape)
        gc.collect()
        tracemalloc.start()
        before, _ = tracemalloc.get_traced_memory()
        owner = builder.build(**inputs)
        _, peak = tracemalloc.get_traced_memory()
        del builder
        gc.collect()
        retained, _ = tracemalloc.get_traced_memory()
        owner.__exit__()
        del owner
        gc.collect()
        released, _ = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        samples.append(
            {
                "build_peak_bytes": peak - before,
                "retained_runtime_and_plan_bytes": retained - before,
                "post_close_and_release_bytes": released - before,
            }
        )
    return {
        "sample_count": len(samples),
        "samples": samples,
        "median": {key: statistics.median(row[key] for row in samples) for key in samples[0]},
    }


def profile_costs(shape: str, output: Path, *, declarations: bool) -> dict:
    profiler = cProfile.Profile()
    for _ in range(5):
        if declarations:
            profiler.enable()
            builder = workloads.make_builder(shape)
        else:
            builder = workloads.make_builder(shape)
            profiler.enable()
        owner = builder.build(**workloads.build_inputs(shape))
        profiler.disable()
        owner.__exit__()
    profiler.dump_stats(str(output))
    stats = cast(Any, pstats.Stats(profiler))
    rows = []
    for (filename, line, function), (primitive, calls, self_time, cumulative, _) in stats.stats.items():
        # Only source locations and aggregate times/call counts are exported.
        rows.append(
            {
                "file": Path(filename).name,
                "line": line,
                "function": function,
                "primitive_calls": primitive,
                "calls": calls,
                "self_s": self_time,
                "cumulative_s": cumulative,
            }
        )
    return {
        "build_count": 5,
        "total_profiled_s": stats.total_tt,
        "top_self": sorted(rows, key=lambda row: row["self_s"], reverse=True)[:25],
        "top_cumulative": sorted(rows, key=lambda row: row["cumulative_s"], reverse=True)[:25],
        "signature_type_targets": [
            row
            for row in rows
            if row["function"]
            in {
                "_get_arg_info",
                "_validate_dependency_names",
                "signature",
                "get_type_hints",
                "_factory_result_annotation",
                "_specialized_factory_dependencies",
                "_specialize_registration",
                "_census_inventory",
                "_graph_roots",
                "_finalize_plan",
                "_clone_component",
                "_type_namespace",
            }
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prefix", default="/tmp/compiler-optimization")  # noqa: S108 - explicitly requested local evidence path
    args = parser.parse_args()
    prefix = args.prefix
    rows = {}
    for shape in workloads.SHAPES:
        profile = CompilationProfiler(max_records=50_000)
        with workloads.make_builder(shape).build(profile=profile, **workloads.build_inputs(shape)) as owner:
            inventory = executable_inventory(owner)
        report = profile.report()
        Path(f"{prefix}-{shape}-compilation-profile.json").write_text(report.to_json())
        rows[shape] = {
            "inventory": inventory,
            "allocations": allocation_samples(shape),
            "compiler_counters": report.counters.to_dict(),
            "compiler_phase_ns": dict(report.phases_ns),
            "compiler_omitted_records": report.omitted_records,
            "build_cprofile": profile_costs(shape, Path(f"{prefix}-{shape}-build.prof"), declarations=False),
            "declaration_build_cprofile": profile_costs(
                shape, Path(f"{prefix}-{shape}-declarations.prof"), declarations=True
            ),
        }

    # Failed-build diagnostic retries are a distinct budget workload.
    class Missing:
        pass

    class Broken:
        def __init__(self, missing: Missing):
            raise AssertionError("Diagnostic compilation must not activate")

    builder = workloads.ContainerBuilder()
    builder.register(Broken)
    profile = CompilationProfiler(max_records=50_000)
    try:
        builder.build(profile=profile)
    except ContainerBuildError:
        pass
    else:
        raise AssertionError("Broken compiler workload unexpectedly succeeded")
    report = profile.report()
    Path(f"{prefix}-failed-compilation-profile.json").write_text(report.to_json())
    rows["failed-one-root"] = {
        "compiler_counters": report.counters.to_dict(),
        "compiler_phase_ns": dict(report.phases_ns),
    }
    if workloads.ACTIVATIONS:
        raise AssertionError("Compilation probe activated application objects")
    Path(f"{prefix}-evidence.json").write_text(json.dumps(rows, indent=2) + "\n")
    print(f"Wrote {prefix}-evidence.json; all compilation probes had zero activations")


if __name__ == "__main__":
    main()
