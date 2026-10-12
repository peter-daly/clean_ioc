"""Separate full public walk/census/manifest promotion and inspection screen."""

# ruff: noqa: E402, S101
import gc
import json
import sys

from source_loader import LOADED, install

install(sys.argv[1])
from benchmarks.graph_memory_evidence import inspect_graph
from benchmarks.graph_memory_fixture import TEMPLATE_CALLS, build
from clean_ioc._compact_index import _CompactIndex

fixture = build(2, mode="analysis")
runtime = fixture.runtime


def capacities():
    result = {}
    for name in ("occurrence_origins", "decorator_explanations"):
        backing = gc.get_referents(getattr(runtime._plan, name))[0]
        result[name] = (
            backing.capacity() if type(backing) is _CompactIndex else {"shallow_bytes": sys.getsizeof(backing)}
        )
    return result


before = capacities()
calls = dict(TEMPLATE_CALLS)
result = inspect_graph(runtime)
assert calls == TEMPLATE_CALLS
assert before == capacities()
print(
    json.dumps(
        {"policy": sys.argv[1], "loaded": LOADED, "before": before, "after": capacities(), "inspection": result},
        indent=2,
    )
)
runtime.__exit__(None, None, None)
