"""Index representation contract screen, independent of compiler measurements."""

# ruff: noqa: S101
import importlib.util
import json
import sys
from pathlib import Path
from types import MappingProxyType

path = Path(__file__).with_name("07-probe.py")
spec = importlib.util.spec_from_file_location("task07_probe", path)
if spec is None or spec.loader is None:
    raise RuntimeError("Missing Task07 probe")
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)
value = probe.IndexedMapping()
reference = {}
operations = (
    ("set", 4),
    ("set", 1),
    ("set", -((1 << 64) + 4)),
    ("set", 10**12),
    ("set", 1),
    ("delete", 4),
    ("set", 4),
    ("set", True),
    ("set", None),
)
for index, (operation, key) in enumerate(operations):
    if operation == "set":
        value[key] = reference[key] = index
    else:
        del value[key]
        del reference[key]
    assert list(value) == list(reference)
    assert list(value.items()) == list(reference.items())
    assert dict(value) == reference
    assert dict(MappingProxyType(value)) == reference
    assert value.get("missing") is None
assert len(value._values) <= 1025
assert value[-((1 << 64) + 4)] == reference[-((1 << 64) + 4)]
assert sys.getsizeof(value._sparse) < 1024
numeric_reference = {1: "one"}
numeric_prototype = probe.IndexedMapping()
numeric_prototype[1] = "one"
numeric_equivalence = numeric_prototype.get(1.0) == numeric_reference.get(1.0)
assert not numeric_equivalence  # Recorded compatibility limitation, not a ready mapping.
print(
    json.dumps(
        {
            "checks": len(operations),
            "keys": list(value),
            "dense_capacity": len(value._values),
            "sparse_entries": len(value._sparse),
            "insertion_order": "preserved",
            "numeric_equivalence_preserved": numeric_equivalence,
        },
        indent=2,
    )
)
