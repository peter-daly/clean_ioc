"""Differential contract and capacity checks, outside graph measurements."""

# ruff: noqa: S101, S311
import gc
import importlib.util
import io
import json
import random
import time
import tracemalloc
from fractions import Fraction
from pathlib import Path
from types import MappingProxyType
from typing import Any

path = Path(__file__).with_name("09-probe.py")
spec = importlib.util.spec_from_file_location("task09_probe", path)
if spec is None or spec.loader is None:
    raise RuntimeError("Missing Task09 probe")
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)
Index = probe.CompactIndex


class IntSubclass(int):
    pass


class Equivalent:
    def __hash__(self):
        return hash(1)

    def __eq__(self, other):
        return other == 1


class Colliding:
    def __hash__(self):
        return hash(1)

    def __eq__(self, other):
        return self is other


def outcome(operation):
    try:
        return ("value", operation())
    except Exception as error:
        return (type(error).__name__, str(error))


reference: dict[Any, Any]
checks = 0
for first in (1, True, 1.0, Fraction(1), IntSubclass(1), Equivalent()):
    for query in (1, True, 1.0, Fraction(1), IntSubclass(1), Equivalent()):
        mapping, reference = Index(), {}
        mapping[first] = reference[first] = "initial"
        assert mapping.get(query) == reference.get(query)
        assert (query in mapping) == (query in reference)
        mapping[query] = reference[query] = "updated"
        assert list(mapping.items()) == list(reference.items())
        assert next(iter(mapping)) is next(iter(reference))
        del mapping[query]
        del reference[query]
        assert dict(mapping) == reference
        checks += 1
for special in (Colliding(), None, "1", -((1 << 64) + 4), 10**100, float("nan")):
    mapping, reference = Index(), dict[Any, Any]({1: "one"})
    mapping[1] = "one"
    assert outcome(lambda: mapping[special]) == outcome(lambda: reference[special])
    mapping[special] = reference[special] = "special"
    assert list(mapping.items()) == list(reference.items())
    checks += 1
for key in ([], {}, set()):
    mapping = Index()
    assert outcome(lambda: mapping.get(key)) == outcome(lambda: {}.get(key))
    checks += 1
for mutation in ("insert", "delete", "update", "delete-reinsert", "delete-insert", "clear"):
    for view in ("keys", "values", "items", "reversed"):
        mapping, reference = Index(), {}
        for key in (4, 1, 7):
            mapping[key] = reference[key] = key
        views = [reversed(m) if view == "reversed" else iter(getattr(m, view)()) for m in (mapping, reference)]
        assert next(views[0]) == next(views[1])
        for item in (mapping, reference):
            if mutation == "insert":
                item[9] = 9
            elif mutation == "delete":
                del item[1]
            elif mutation == "update":
                item[1] = 10
            elif mutation == "delete-reinsert":
                del item[1]
                item[1] = 10
            elif mutation == "delete-insert":
                del item[1]
                item[9] = 9
            else:
                item.clear()
        assert outcome(lambda: list(views[0])) == outcome(lambda: list(views[1]))
        checks += 1
mapping, reference = Index(), {}
proxy = MappingProxyType(mapping)
keys, values, items = mapping.keys(), mapping.values(), mapping.items()
snapshot = proxy.copy()
for key in (4, 1, 9):
    mapping[key] = reference[key] = key
assert list(keys) == list(reference.keys())
assert list(values) == list(reference.values())
assert list(items) == list(reference.items())
assert snapshot == {}
assert proxy == reference
assert proxy | {3: 5} == reference | {3: 5}
assert {3: 5} | proxy == {3: 5} | reference
assert outcome(lambda: mapping.popitem()) == outcome(lambda: reference.popitem())
assert mapping == reference
assert dict(keys.mapping) == reference
assert list(reversed(keys)) == list(reversed(reference.keys()))
assert list(reversed(values)) == list(reversed(reference.values()))
assert list(reversed(items)) == list(reversed(reference.items()))
checks += 13
rng = random.Random(8009)
for repeat in range(100):
    mapping, reference = Index(), {}
    for step in range(100):
        key = rng.choice((0, 1, 4, 9, -3, 10**20, True, 1.0, "other"))
        operation = rng.choice(("set", "delete", "setdefault", "pop"))
        if operation == "set":
            mapping[key] = reference[key] = step
        else:

            def apply(target):
                if operation == "delete":
                    del target[key]
                    return None
                return getattr(target, operation)(key, step)

            assert outcome(lambda: apply(mapping)) == outcome(lambda: apply(reference))
        assert mapping.copy() == reference
        checks += 1
left_namespace, right_namespace = Index(), Index()
left_origin, right_origin = object(), object()
left_namespace[1], right_namespace[1] = left_origin, right_origin
assert left_namespace[1] is left_origin and right_namespace[1] is right_origin
checks += 1
capacity_cases = []
for label, keys_to_add in (
    ("dense", range(10000)),
    ("gapped", range(0, 40000, 4)),
    ("reverse", reversed(range(10000))),
    ("negative", range(-10000, 0)),
    ("huge", (10**100 + i for i in range(10000))),
):
    mapping = Index()
    value = object()
    for key in keys_to_add:
        mapping[key] = value
    capacity = mapping.capacity()
    assert capacity["dense_length"] <= min(Index.LIMIT, max(64, len(mapping) * 4))
    assert all(item is value for _, item in mapping.raw_items())
    capacity_cases.append({"case": label, **capacity})
    for key, _ in list(mapping.raw_items())[:9999]:
        del mapping[key]
    capacity_cases[-1]["after_deletion"] = mapping.capacity()
original_limit = Index.LIMIT
try:
    Index.LIMIT = 128
    bounded = Index()
    for key in range(1000):
        bounded[key] = "bounded"
    assert bounded.capacity()["dense_length"] == 0
    assert bounded.capacity()["entries"] == 1000
    assert bounded[999] == "bounded"
finally:
    Index.LIMIT = original_limit
checks += 3
# Conversion overlap and promotion explicitly include both representations.
reference = dict.fromkeys(range(88558), object())
tracemalloc.start()
started = time.perf_counter()
mapping = Index()
for key, item in reference.items():
    mapping[key] = item
conversion_seconds = time.perf_counter() - started
conversion = tracemalloc.get_traced_memory()
tracemalloc.reset_peak()
started = time.perf_counter()
list(mapping)
promotion_seconds = time.perf_counter() - started
promotion = tracemalloc.get_traced_memory()
tracemalloc.stop()
# Direct codec exercises backing sharing, ordered sparse IDs and malformed rows.
probe.install("both")
from benchmarks.graph_artifact import _Reader, _Writer  # noqa: E402

mapping = Index()
for key in (4, 1, -((1 << 64) + 4), 10**100):
    mapping[key] = "value"
stream = io.StringIO()
writer = _Writer(stream)
left, right = MappingProxyType(mapping), MappingProxyType(mapping)
writer.ref((left, right))
reader = _Reader()
for row in stream.getvalue().splitlines():
    index, kind, payload = json.loads(row)
    assert index == len(reader.objects)
    reader.objects.append(reader.decode(kind, payload))
loaded = reader.objects[-1]
assert gc.get_referents(loaded[0])[0] is gc.get_referents(loaded[1])[0]
assert list(loaded[0].items()) == list(mapping.items())
for payload in (None, [[None]], [[True, None]], [[None, None]], [[1, None], [1, None]]):
    assert outcome(lambda: _Reader().decode("compact09", payload))[0] == "ValueError"
checks += 7
print(
    json.dumps(
        {
            "differential_checks": checks,
            "capacity": capacity_cases,
            "conversion_seconds": conversion_seconds,
            "conversion_retained_peak": conversion,
            "promotion_seconds": promotion_seconds,
            "promotion_retained_peak": promotion,
            "codec_sharing": True,
        },
        indent=2,
    )
)
