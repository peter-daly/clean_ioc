"""Observer storage, lookup, scaling and unpromoted inspection screens."""

# ruff: noqa: E402
import argparse
import hashlib
import json
import statistics
import sys
import time
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))
from clean_ioc._compact_index import _CompactIndex as Index

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
            for name, cls in (("dict", dict), ("compact", Index)):
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
print(json.dumps(result, indent=2))
