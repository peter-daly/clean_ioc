"""Preserve newly discovered task09 failures alongside the corrected normal source."""

# ruff: noqa: E402, S101
import hashlib
import importlib.util
import json
import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.resolve().parents[3]))
from clean_ioc._compact_index import _CompactIndex

path = HERE.parent / "09-probe.py"
spec = importlib.util.spec_from_file_location("task09_boundary_reference", path)
assert spec is not None and spec.loader is not None
old = importlib.util.module_from_spec(spec)
spec.loader.exec_module(old)


def outcome(call):
    try:
        value = call()
        return {"value": repr(value)}
    except Exception as error:
        return {"exception": type(error).__name__}


class Operand:
    @property
    def __class__(self):
        raise RuntimeError("application __class__ callback")


rows = {}
for name, operation_fn in {
    "hostile-class-eq": lambda d: d == Operand(),
    "hostile-class-update": lambda d: d.update(Operand()),
    "hostile-class-union": lambda d: d | Operand(),
    "keyword-dunder": lambda d: d.__getitem__(key=1),
    "native-NotImplemented": lambda d: d.__eq__(object()),
    "self-update-keyword": lambda d: d.update(self=1),
}.items():
    rows[name] = {}
    for label, factory in (("dict", dict), ("task09", old.CompactIndex), ("task15", _CompactIndex)):
        mapping = factory()
        mapping[1] = 1
        rows[name][label] = outcome(lambda: operation_fn(mapping))
    assert rows[name]["task15"] == rows[name]["dict"], name
for operation in ("set", "get", "getitem", "contains", "set-new"):
    row = {}
    for label, factory in (("dict", dict), ("task09", old.CompactIndex), ("task15", _CompactIndex)):
        mapping = factory()
        for key in range(127):
            mapping[key] = key

        class Key:
            def __hash__(self):
                mapping[127] = 127
                mapping[126] = "changed"
                return 5000 if operation == "set-new" else 126

            def __eq__(self, other):
                return other == 126

        def apply():
            key = Key()
            if operation in ("set", "set-new"):
                mapping[key] = "inserted"
            elif operation == "get":
                return mapping.get(key)
            elif operation == "getitem":
                return mapping[key]
            else:
                return key in mapping
            return None

        result = outcome(apply)
        row[label] = {"result": result, "entries": len(mapping), "value126": mapping[126]}
    assert row["dict"] == row["task15"], operation
    rows["reentrant-" + operation] = row
print(json.dumps({"task09_probe_sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "rows": rows}, indent=2))
