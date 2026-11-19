"""Observer storage, lookup, scaling and unpromoted inspection screens."""

import argparse
import gc
import hashlib
import importlib.util
import json
import statistics
import sys
import time
from pathlib import Path
from typing import Any

path = Path(__file__).with_name("09-probe.py")
spec = importlib.util.spec_from_file_location("task09_probe", path)
if spec is None or spec.loader is None:
    raise RuntimeError("Missing Task09 probe")
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)
parser = argparse.ArgumentParser()
parser.add_argument("mode", choices=("storage", "inspection", "inventory"))
parser.add_argument("--probe", default="both")
parser.add_argument("--routes", type=int, default=8)
parser.add_argument("--diagnostics", action="store_true")
args = parser.parse_args()
result = {
    "mode": args.mode,
    "probe": args.probe,
    "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
}
if args.mode == "storage":
    rows = []
    for size in (0, 1, 10, 100, 1000, 10000, 100000):
        for label, keys in (
            ("dense", range(size)),
            ("gapped", range(0, size * 4, 4)),
            ("reverse", reversed(range(size))),
            ("negative", range(-size, 0)),
            ("huge", (10**100 + i for i in range(size))),
        ):
            value = object()
            keys = list(keys)
            mappings: dict[str, Any] = {}
            row: dict[str, Any] = {"size": size, "shape": label}
            for name, cls in (("dict", dict), ("compact", probe.CompactIndex)):
                started = time.perf_counter()
                mapping: Any = cls()
                for key in keys:
                    mapping[key] = value
                elapsed = time.perf_counter() - started
                mappings[name] = mapping
                row[name] = {
                    "construct_seconds": elapsed,
                    "storage": mapping.capacity() if name == "compact" else {"shallow_bytes": sys.getsizeof(mapping)},
                }
                batches = []
                for _ in range(3):
                    started = time.perf_counter()
                    for _ in range(5):
                        for key in keys:
                            mapping.get(key)
                    batches.append(time.perf_counter() - started)
                row[name]["get_seconds_batches"] = batches
                row[name]["get_seconds_median"] = statistics.median(batches)
            started = time.perf_counter()
            for _ in range(5):
                for key, value in mappings["dict"].items():
                    pass
            row["dict_iteration_seconds"] = time.perf_counter() - started
            started = time.perf_counter()
            for _ in range(5):
                for key, value in mappings["compact"].raw_items():
                    pass
            row["compact_raw_iteration_seconds"] = time.perf_counter() - started
            started = time.perf_counter()
            list(mappings["compact"])
            row["promotion_seconds"] = time.perf_counter() - started
            row["promoted_storage"] = mappings["compact"].capacity()
            rows.append(row)
    result["rows"] = rows
else:
    probe.install(args.probe)
    from benchmarks.graph_memory_evidence import inspect_graph
    from benchmarks.graph_memory_fixture import build
    from clean_ioc import container

    captures = []
    if args.mode == "inventory":
        original = container._Compiler.compile

        def capture(self, *arguments, **keywords):
            value = original(self, *arguments, **keywords)
            row = {"phase": self._profile_phase, "graph_records": len(self.graph._drafts or self.graph._records or {})}
            for name in ("origins", "decorator_explanations"):
                mapping = getattr(self, name)
                items = list(mapping.raw_items()) if isinstance(mapping, probe.CompactIndex) else list(mapping.items())
                row[name] = {
                    "entries": len(mapping),
                    "unique_values": len({id(value) for _, value in items}),
                    "min_id": min((key for key, _ in items), default=0),
                    "max_id": max((key for key, _ in items), default=0),
                    "sorted_order": [key for key, _ in items] == sorted(key for key, _ in items),
                    "capacity": mapping.capacity()
                    if isinstance(mapping, probe.CompactIndex)
                    else {"shallow_bytes": sys.getsizeof(mapping)},
                }
            captures.append(row)
            return value

        container._Compiler.compile = capture
    fixture = build(args.routes, explain_metadata=True, diagnostics=args.diagnostics, allow_scope_builders=False)
    plan = fixture.runtime._plan

    def capacities():
        result = {}
        for name in ("occurrence_origins", "decorator_explanations"):
            mapping = getattr(plan, name)
            mapping = gc.get_referents(mapping)[0]
            result[name] = (
                mapping.capacity()
                if isinstance(mapping, probe.CompactIndex)
                else {"shallow_bytes": sys.getsizeof(mapping)}
            )
        return result

    result["before_inspection"] = capacities()
    if args.mode == "inspection":
        result["inspection"] = inspect_graph(fixture.runtime)
        result["after_inspection"] = capacities()
        if (
            fixture.callbacks_after_build
            != __import__("benchmarks.graph_memory_fixture", fromlist=["TEMPLATE_CALLS"]).TEMPLATE_CALLS
        ):
            raise AssertionError("Inspection replayed callbacks")
    else:
        result["primary_captures"] = captures
    result["physical_records"] = len(plan.graph._records or {})
    result["compatibility"] = probe.compatibility()
    fixture.runtime.__exit__(None, None, None)
print(json.dumps(result, indent=2, sort_keys=True))
