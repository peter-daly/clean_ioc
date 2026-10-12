"""Separate deterministic work, tracemalloc and cProfile evidence for item 20.

No instrumented duration is a latency result. Inputs/declarations precede tracing;
retained bytes keep either the unactivated runtime or safe failure report alive.
Each sample is collected independently; allocation peaks are Python-traced bytes,
not RSS. Five cProfile builds per cell exclude normal close and declarations.
"""

import cProfile
import gc
import hashlib
import json
import pstats
import tracemalloc
from pathlib import Path
from tempfile import gettempdir
from typing import Any, cast

from benchmarks import bench_compiler_optimization as fixtures
from benchmarks.compilation_budget_experiment import BUDGETS
from clean_ioc import CompilationProfiler, ContainerBuildError

SHAPES = ("wide-24", "generic-8-roots", "collection-12", "template-12")
FUNCTIONS = {
    "_draft",
    "_clone_component_tree",
    "_specialize_registration",
    "admit",
    "occurrence",
    "_compile_provider_roots",
}


def build(builder, shape, budget, profile=None):
    try:
        return builder.build(budget=budget, profile=profile, **fixtures.build_inputs(shape)), None
    except ContainerBuildError as error:
        if error.report is None or error.report.errors[-1].code != "compilation-budget-exceeded":
            raise
        return None, error


def source_digests():
    paths = sorted(Path("clean_ioc").glob("*.py"))
    paths += [
        Path("benchmarks") / name
        for name in (
            "bench_compiler_optimization.py",
            "compiler_optimization_evidence.py",
            "compilation_budget_experiment.py",
            "compilation_budget_evidence.py",
        )
    ]
    return {str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in paths}


def main():
    document = {"source_digests": source_digests(), "cells": [], "activations": 0}
    before_activations = fixtures.ACTIVATIONS
    for shape in SHAPES:
        for mode, budget in BUDGETS.items():
            with fixtures.make_builder(shape).build(**fixtures.build_inputs(shape)):
                pass
            samples = []
            for _ in range(5):
                builder = fixtures.make_builder(shape)
                gc.collect()
                tracemalloc.start()
                owner, error = build(builder, shape, budget)
                peak = tracemalloc.get_traced_memory()[1]
                del builder
                gc.collect()
                retained = tracemalloc.get_traced_memory()[0]
                tracemalloc.stop()
                samples.append(
                    {
                        "peak_bytes": peak,
                        "retained_bytes": retained,
                        "retained_object": "runtime" if owner is not None else "failure evidence",
                    }
                )
                if owner is not None:
                    owner.__exit__()
                del owner, error
                gc.collect()
            profile = CompilationProfiler(max_records=50_000)
            owner, error = build(fixtures.make_builder(shape), shape, budget, profile)
            profile_path = Path(gettempdir()) / f"item20-{shape}-{mode}-compilation-profile.json"
            profile_path.write_text(profile.report().to_json() + "\n")
            cell = {
                "shape": shape,
                "mode": mode,
                "allocations": samples,
                "budget_usage": dict(profile.report().budget_usage or ()),
                "counters": profile.report().counters.to_dict(),
                "profile_omitted_records": profile.report().omitted_records,
                "failure": None if error is None else error.report.to_dict(),
            }
            if owner is not None:
                owner.__exit__()
            del owner, error
            profiler = cProfile.Profile()
            for _ in range(5):
                builder = fixtures.make_builder(shape)
                gc.collect()
                owner, error = profiler.runcall(build, builder, shape, budget)
                if owner is not None:
                    owner.__exit__()
                del owner, error, builder
            cprofile_path = Path(gettempdir()) / f"item20-{shape}-{mode}.prof"
            profiler.dump_stats(cprofile_path)
            stats = pstats.Stats(profiler)
            cell["cprofile"] = [
                {
                    "function": name,
                    "primitive_calls": values[0],
                    "calls": values[1],
                    "self_s": values[2],
                    "cumulative_s": values[3],
                }
                for (_, _, name), values in sorted(cast(Any, stats).stats.items())
                if name in FUNCTIONS
            ]
            document["cells"].append(cell)
            print(f"Captured {shape}/{mode}", flush=True)
    document["activations"] = fixtures.ACTIVATIONS - before_activations
    if document["activations"]:
        raise AssertionError("Compilation activated application objects")
    if source_digests() != document["source_digests"]:
        raise AssertionError("Source changed during evidence capture")
    (Path(gettempdir()) / "item20-evidence.json").write_text(json.dumps(document, indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
