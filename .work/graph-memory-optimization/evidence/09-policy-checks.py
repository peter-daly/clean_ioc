"""Storage/transition screens; keys and values are borrowed, counted once."""

# ruff: noqa: S101
import importlib.util
import json
import sys
import time
import tracemalloc
from pathlib import Path
from typing import Any

path = Path(__file__).with_name("09-probe.py")
spec = importlib.util.spec_from_file_location("task09_probe", path)
if spec is None or spec.loader is None:
    raise RuntimeError("Missing probe")
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)
Index = probe.CompactIndex
rows = []
for threshold in (32, 64, 128, 256):
    Index.THRESHOLD = threshold
    for size in (0, 1, 10, 32, 64, 127, 128, 129, 256, 1000, 10000):
        for shape in ("dense", "gapped", "reverse", "negative", "huge", "mixed"):
            keys = list(range(size))
            if shape == "gapped":
                keys = [4 * k for k in keys]
            elif shape == "reverse":
                keys.reverse()
            elif shape == "negative":
                keys = [-k - 1 for k in keys]
            elif shape == "huge":
                keys = [10**100 + k for k in keys]
            elif shape == "mixed":
                keys = [k if k % 4 else -k - 1 for k in keys]
            row = {"threshold": threshold, "size": size, "shape": shape}
            for label, cls in (("dict", dict), ("candidate", Index)):
                start = time.perf_counter()
                mapping: Any = cls()
                for key in keys:
                    mapping[key] = "value"
                row[label] = {
                    "seconds": time.perf_counter() - start,
                    "shallow_bytes": sys.getsizeof(mapping) if cls is dict else mapping.capacity()["shallow_bytes"],
                }
            rows.append(row)
Index.THRESHOLD = 128
transitions = []
for shape in ("threshold-128", "late-density-256", "dense-to-sparse", "public-promotion"):
    mapping = Index()
    keys = (
        range(127)
        if shape == "threshold-128"
        else (([0] + [2 * key + 5 for key in range(127)]) if shape == "late-density-256" else range(10000))
    )
    for key in keys:
        mapping[key] = "value"
    before = mapping.capacity()
    tracemalloc.start()
    start = time.perf_counter()
    if shape == "threshold-128":
        mapping[127] = "value"
    elif shape == "late-density-256":
        for key in [key for key in range(258) if key not in mapping][:128]:
            mapping[key] = "value"
    elif shape == "dense-to-sparse":
        for key in range(2000):
            mapping[-key - 1] = "value"
    else:
        mapping.promote()
    elapsed = time.perf_counter() - start
    retained, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    transitions.append(
        {
            "shape": shape,
            "before": before,
            "after": mapping.capacity(),
            "seconds": elapsed,
            "new_retained_bytes": retained,
            "new_peak_bytes": peak,
        }
    )
    assert not mapping._eligible
    if shape in ("dense-to-sparse", "public-promotion"):
        assert mapping._dict is not None and mapping._values is mapping._keys is mapping._sparse is None
# At most one compaction and one permanent promotion; native views remain live.
index = Index()
states = []
for key in range(5000):
    index[key] = "value"
    state = index._dict is None
    if not states or states[-1] != state:
        states.append(state)
view = index.items()
backing = index._dict
for key in range(5000, 10000):
    index[key] = "value"
index.clear()
for key in range(5000):
    index[key] = "value"
assert states == [False, True] and index._dict is backing and len(view) == 5000
print(
    json.dumps(
        {
            "policy_rows": rows,
            "transitions": transitions,
            "bounded_transitions": True,
            "carrier_overhead_bytes": sys.getsizeof(Index()),
        },
        indent=2,
    )
)
