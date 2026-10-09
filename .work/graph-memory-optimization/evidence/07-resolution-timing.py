"""Longer warm-scope workload timing, separately from memory comparisons."""

import asyncio
import gc
import importlib.util
import json
import statistics
import sys
import time
from pathlib import Path

path = Path(__file__).with_name("07-probe.py")
spec = importlib.util.spec_from_file_location("task07_probe", path)
if spec is None or spec.loader is None:
    raise RuntimeError("Missing Task07 probe")
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)
probe.install(sys.argv[1])
from benchmarks import graph_memory_fixture as fixture_module  # noqa: E402


async def measure():
    fixture = fixture_module.build(8, explain_metadata=False)
    durations = []
    try:
        for iteration in range(51):
            # Each invocation starts in a new scope. Reset fixture counters so
            # its laziness/activation checks apply independently to this run.
            gc.collect()
            fixture_module.ACTIVATIONS.clear()
            started = time.perf_counter()
            held = await fixture_module.resolve_workload(fixture)
            elapsed = time.perf_counter() - started
            fixture_module.validate(fixture, held)
            await held.scope.__aexit__(None, None, None)
            del held
            if iteration:
                durations.append(elapsed)
    finally:
        await fixture.runtime.__aexit__(None, None, None)
    return {
        "probe": sys.argv[1],
        "runs": len(durations),
        "seconds": durations,
        "median_seconds": statistics.median(durations),
        "total_seconds": sum(durations),
        "transformed_hashes": probe.TRANSFORM_HASHES,
        "python": sys.version,
    }


print(json.dumps(asyncio.run(measure()), indent=2))
