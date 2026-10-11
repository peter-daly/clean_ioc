# ruff: noqa: E402, S101, S603
"""Fresh-process cold/steady resolution, deliberately excluding compilation."""

import asyncio
import json
import statistics
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))
from benchmarks.graph_memory_evidence import source_provenance
from benchmarks.graph_memory_fixture import ACTIVATIONS, build, resolve_workload, validate
from clean_ioc import ContainerBuilder
from clean_ioc import container as code


async def sample(policy, variant):
    if policy == "before":
        code._ActivationTemplateCache = dict  # ty: ignore[invalid-assignment]
    if variant == "rich-run":
        original = ContainerBuilder.build

        def rich_build(self, **kwargs):
            def rule(context):
                assert context.graph.diagnostics_enabled
                return ()

            self.add_validation_rule(rule)
            return original(self, **kwargs)

        ContainerBuilder.build = rich_build
    fixture = build(2 if variant == "analysis" else 8, mode="analysis" if variant == "analysis" else "run")
    elapsed, cpu, results = [], [], []
    for _ in range(8):
        ACTIVATIONS.clear()
        started_cpu, started = time.process_time(), time.perf_counter()
        held = await resolve_workload(fixture)
        elapsed.append(time.perf_counter() - started)
        cpu.append(time.process_time() - started_cpu)
        results.append(validate(fixture, held))
        await held.scope.__aexit__(None, None, None)
        del held
    await fixture.runtime.__aexit__(None, None, None)
    assert all(result == results[0] for result in results)
    return {
        "policy": policy,
        "variant": variant,
        "source": source_provenance(),
        "wall_seconds": elapsed,
        "cpu_seconds": cpu,
        "cold_seconds": elapsed[0],
        "steady_median_seconds": statistics.median(elapsed[1:]),
        "cold_cpu_seconds": cpu[0],
        "steady_median_cpu_seconds": statistics.median(cpu[1:]),
        "validated": results[0],
    }


if sys.argv[1] == "sample":
    print(json.dumps(asyncio.run(sample(*sys.argv[2:]))))
else:
    results = []
    for variant in ("run", "rich-run", "analysis"):
        for repeat in range(3):
            for policy in ("before", "after"):
                result = json.loads(
                    subprocess.check_output([sys.executable, __file__, "sample", policy, variant], text=True)
                )
                results.append(result)
                Path(sys.argv[2]).write_text(json.dumps(results, indent=2) + "\n")
                print(variant, repeat, policy, result["cold_seconds"], result["steady_median_seconds"], flush=True)
