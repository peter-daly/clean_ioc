"""Untimed, resolution-only compact-index access census; never a timing result."""

# ruff: noqa: E402, S101, S603
import asyncio
import json
import subprocess
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.resolve().parents[3]))
from benchmarks.graph_memory_evidence import source_provenance
from benchmarks.graph_memory_fixture import ACTIVATIONS, build, resolve_workload, validate
from clean_ioc import ContainerBuilder
from clean_ioc._compact_index import _CompactIndex


async def sample(variant):
    if variant == "rich-run":
        original_build = ContainerBuilder.build

        def rich_build(self, **kwargs):
            def rule(context):
                assert context.graph.diagnostics_enabled
                return ()

            self.add_validation_rule(rule)
            return original_build(self, **kwargs)

        ContainerBuilder.build = rich_build
    fixture = build(2 if variant == "analysis" else 8, mode="analysis" if variant == "analysis" else "run")
    originals = {name: getattr(_CompactIndex, name) for name in ("get", "__getitem__", "__contains__")}
    counts = Counter()
    enabled = False

    def wrapper(name, original):
        def count(self, *args, **kwargs):
            if enabled:
                counts[name] += 1
            return original(self, *args, **kwargs)

        return count

    for name, original in originals.items():
        setattr(_CompactIndex, name, wrapper(name, original))
    samples, results = [], []
    try:
        for iteration in range(8):
            ACTIVATIONS.clear()
            counts.clear()
            enabled = True
            try:
                held = await resolve_workload(fixture)
            finally:
                enabled = False
            samples.append({"iteration": iteration, "accesses": {name: counts[name] for name in originals}})
            results.append(validate(fixture, held))
            await held.scope.__aexit__(None, None, None)
            del held
    finally:
        for name, original in originals.items():
            setattr(_CompactIndex, name, original)
        await fixture.runtime.__aexit__(None, None, None)
    assert all(result == results[0] for result in results)
    return {
        "variant": variant,
        "timed": False,
        "source": source_provenance(),
        "samples": samples,
        "validated": results[0],
    }


if len(sys.argv) > 1:
    print(json.dumps(asyncio.run(sample(sys.argv[1]))))
else:
    rows = []
    for variant in ("run", "rich-run", "analysis"):
        rows.append(json.loads(subprocess.check_output([sys.executable, __file__, variant], text=True)))
    (HERE / "resolution-accesses.json").write_text(json.dumps(rows, indent=2) + "\n")
    print(json.dumps([{"variant": row["variant"], "samples": row["samples"]} for row in rows]))
