"""Measure runtime profiling updates, snapshots, and Python allocation costs."""

import gc
import json
import platform
import sys
import tracemalloc
from contextlib import ExitStack

from benchbro import Case, system

from clean_ioc import ContainerBuilder, Instrumentation, ResolutionProfiler

RATES = [0.0, 0.5, 1.0]
MODES = ["counts", "half", "full"]
SHAPES = ["catalog", "dense"]


def declarations(size, shape):
    services = tuple(type(f"Service{index}", (), {}) for index in range(size))
    builder = ContainerBuilder()
    if shape == "dense":
        builder.set_provider_roots(())
    for service in services:
        builder.register(service, lifespan="transient" if shape == "dense" else "singleton")
    return builder, services


@system(scope="session")
def histogram_runtimes():
    with ExitStack() as stack:
        fixtures = {}
        for shape in SHAPES:
            for rate in [None, *RATES]:
                builder, services = declarations(8, shape)
                profiler = ResolutionProfiler(sample_durations=rate) if rate is not None else None
                runtime = stack.enter_context(
                    builder.build(instrumentation=Instrumentation(profiler) if profiler is not None else None)
                )
                for service in services:
                    runtime.resolve(service)
                    runtime.resolve(service)
                fixtures[rate, shape] = runtime, services, profiler
        yield fixtures


updates = Case(name="profiler-histogram-updates", min_iterations=500, setup_timing="exclude")
reports = Case(name="profiler-histogram-reports", min_iterations=3, setup_timing="exclude")


@updates.benchmark()
@updates.parametrize("rate", [None, *RATES], ids=["plain", *MODES])
@updates.parametrize("shape", SHAPES)
def resolve_batch(histogram_runtimes, rate, shape):
    runtime, services, _ = histogram_runtimes[rate, shape]
    for service in services:
        runtime.resolve(service)
        runtime.resolve(service)


@reports.benchmark()
@reports.parametrize("rate", RATES, ids=MODES)
@reports.parametrize("shape", SHAPES)
def snapshot(histogram_runtimes, rate, shape):
    _, _, profiler = histogram_runtimes[rate, shape]
    profiler.report()


def allocation_probe(size, shape, rate):
    builder, services = declarations(size, shape)

    def measure_phase():
        _, peak = tracemalloc.get_traced_memory()
        gc.collect()
        retained, _ = tracemalloc.get_traced_memory()
        tracemalloc.reset_peak()
        return {"retained_bytes": retained, "peak_bytes": peak}

    gc.collect()
    tracemalloc.start()
    try:
        profiler = ResolutionProfiler(sample_durations=rate) if rate is not None else None
        runtime = builder.build(instrumentation=Instrumentation(profiler) if profiler is not None else None)
        with runtime:
            phases = {"build": measure_phase()}
            for service in services:
                runtime.resolve(service)
                runtime.resolve(service)
            phases["resolve"] = measure_phase()
            # Measure snapshot allocation separately on the smaller fixture.
            if profiler is not None and size == 8:
                report = profiler.report()
                phases["holding_report"] = measure_phase()
                del report
                phases["discarded_report"] = measure_phase()
            tracemalloc.stop()
            histograms = (
                sum(len(record.durations) for record in profiler._records.values() if record.durations)
                if profiler is not None
                else 0
            )
    finally:
        tracemalloc.stop()
    return {
        "services": size,
        "shape": shape,
        "rate": rate,
        "records": len(profiler._records) if profiler is not None else 0,
        "histograms": histograms,
        "phases": phases,
    }


if __name__ == "__main__":
    print(
        json.dumps(
            {
                "python": sys.version,
                "platform": platform.platform(),
                "workloads": [
                    allocation_probe(100, "catalog", 0.0),
                    allocation_probe(8, "catalog", 0.0),
                    allocation_probe(8, "dense", None),
                    allocation_probe(8, "dense", 1.0),
                ],
            },
            indent=2,
        )
    )
