"""Separate counts/allocations for item 18; no instrumented latency claims."""

import gc
import hashlib
import json
import platform
import sys
import tracemalloc
from pathlib import Path

from benchmarks import bench_compiler_optimization as fixtures
from benchmarks.incremental_analysis_probe import ParameterShapeProbe, investigation


def shape_counts(shape):
    probe = ParameterShapeProbe()
    counts = []
    for _ in range(2):
        with investigation("candidate", probe):
            with fixtures.make_builder(shape).build(**fixtures.build_inputs(shape)):
                pass
        counts.append(dict(probe.counts))
    return {"cumulative_counts": counts, "retained_entries": len(probe.entries), "entry_limit": probe.limit}


def lifetime_counts(shape):
    result = {}
    for mode in ("warm", "cleared-per-build"):
        probe = ParameterShapeProbe()
        for _ in range(3):
            if mode == "cleared-per-build":
                probe.clear()
            with investigation("candidate", probe):
                with fixtures.make_builder(shape).build(**fixtures.build_inputs(shape)):
                    pass
        result[mode] = dict(probe.counts)
    return result


def allocation_samples(shape, mode):
    probe = ParameterShapeProbe()
    with investigation(mode, probe):
        with fixtures.make_builder(shape).build(**fixtures.build_inputs(shape)):
            pass
    samples = []
    for _ in range(5):
        builder = fixtures.make_builder(shape)
        inputs = fixtures.build_inputs(shape)
        gc.collect()
        tracemalloc.start()
        try:
            with investigation(mode, probe):
                owner = builder.build(**inputs)
            _, peak = tracemalloc.get_traced_memory()
            del builder
            gc.collect()
            retained, _ = tracemalloc.get_traced_memory()
            owner.__exit__()
            del owner
            gc.collect()
            released, _ = tracemalloc.get_traced_memory()
            samples.append(
                {"build_peak_bytes": peak, "runtime_retained_bytes": retained, "post_release_bytes": released}
            )
        finally:
            tracemalloc.stop()
    return samples


def main():
    starting_activations = fixtures.ACTIVATIONS
    source = Path(__file__).with_name("incremental_analysis_probe.py")
    result = {
        "python": sys.version,
        "platform": platform.platform(),
        "probe_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "allocation_boundary": (
            "Fresh declarations excluded; public build and patch context included; warm probe retained"
        ),
        "allocation_limits": "Python tracemalloc, not RSS; five samples; post-release bytes are not a leak proof",
        "counts": {shape: shape_counts(shape) for shape in fixtures.SHAPES},
        "lifetime_counts": {shape: lifetime_counts(shape) for shape in ("generic-8-roots", "collection-12")},
        "allocations": {
            shape: {mode: allocation_samples(shape, mode) for mode in ("full", "candidate")}
            for shape in fixtures.SHAPES
        },
    }
    if fixtures.ACTIVATIONS != starting_activations:
        raise AssertionError("Compilation evidence must not activate application objects")
    path = Path("/tmp/item18-evidence.json")  # noqa: S108 - explicit local experiment output, never read as input.
    path.write_text(json.dumps(result, indent=2) + "\n")
    print(path)


if __name__ == "__main__":
    main()
