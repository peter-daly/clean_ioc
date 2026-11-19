# ruff: noqa: E402, S101, S603
"""CPU/traversal attribution only, excluded from normal latency evidence."""

import cProfile
import json
import pstats
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))
from benchmarks.graph_memory_fixture import build
from clean_ioc import ContainerBuilder
from clean_ioc import container as code

policy, variant = sys.argv[1:]
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
profiler = cProfile.Profile()
profiler.enable()
fixture = build(2 if variant == "analysis" else 8, mode="analysis" if variant == "analysis" else "run")
profiler.disable()
fixture.runtime.__exit__(None, None, None)
stats: Any = pstats.Stats(profiler)
names = ("_scalar_activation_closure", "_activation_key_is_inert", "__setitem__", "get", "remove")
selected = [
    {
        "file": key[0],
        "line": key[1],
        "function": key[2],
        "primitive_calls": values[0],
        "total_calls": values[1],
        "own_seconds": values[2],
        "cumulative_seconds": values[3],
    }
    for key, values in stats.stats.items()
    if key[0].endswith("/container.py") and key[2] in names
]
print(
    json.dumps(
        {"policy": policy, "variant": variant, "total_cpu_seconds": stats.total_tt, "functions": selected}, indent=2
    )
)
