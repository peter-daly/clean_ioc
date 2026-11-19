"""Retain mapping failures that ordinary value-equivalence screens miss."""

import importlib.util
import json
from pathlib import Path
from types import MappingProxyType

path = Path(__file__).with_name("08-probe.py")
spec = importlib.util.spec_from_file_location("task08_probe", path)
if spec is None or spec.loader is None:
    raise RuntimeError("Missing Task08 probe")
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)


class Key:
    def __init__(self):
        self.calls = 0
        self.limit = 100

    def __eq__(self, other):
        return other == 4000

    def __hash__(self):
        self.calls += 1
        if self.calls > self.limit:
            raise RuntimeError("extra user hashing")
        return 4000


def measure(factory, operation):
    key = Key()
    mapping = factory()
    if operation in ("pop", "copy", "equality"):
        mapping[key] = "value"
    source = {key: "value"} if operation == "update" else None
    key.calls = 0
    key.limit = 1 if operation in ("setdefault", "pop") else 0
    try:
        if operation == "setdefault":
            mapping.setdefault(key, "value")
        elif operation == "pop":
            mapping.pop(key)
        elif operation == "copy":
            mapping.copy()
        elif operation == "equality":
            mapping == mapping
        else:
            mapping.update(source)
    except RuntimeError as error:
        outcome = str(error)
    else:
        outcome = "success"
    return {"outcome": outcome, "hash_calls": key.calls}


class NativeDelegation(probe.CompactIndex):
    """Unmeasured feasibility refinement; not installed in compiler or codec."""

    __slots__ = ()

    def setdefault(self, key, default=None):
        return self.promote().setdefault(key, default)

    def pop(self, key, *default):
        return self.promote().pop(key, *default)

    def copy(self):
        return self.promote().copy()

    def __eq__(self, other):
        if isinstance(other, NativeDelegation):
            other = other.promote()
        return self.promote() == other

    def update(self, *arguments, **keywords):
        if len(arguments) == 1 and isinstance(arguments[0], NativeDelegation):
            arguments = (arguments[0].promote(),)
        return self.promote().update(*arguments, **keywords)


results = []
for operation in ("setdefault", "pop", "copy", "equality", "update"):
    results.append(
        {
            "operation": operation,
            "dict": measure(dict, operation),
            "measured_compact": measure(probe.CompactIndex, operation),
            "native_delegation": measure(NativeDelegation, operation),
        }
    )


def proxy_equality(factory):
    key = Key()
    other = {key: "value"}
    mapping = factory()
    mapping[4000] = "value"
    key.calls, key.limit = 0, 0
    try:
        matched = MappingProxyType(mapping) == other
    except RuntimeError as error:
        outcome = str(error)
    else:
        outcome = "success" if matched else "false"
    return {"outcome": outcome, "hash_calls": key.calls}


results.append(
    {
        "operation": "public-proxy-equality-with-int-equivalent-key",
        "dict": proxy_equality(dict),
        "measured_compact": proxy_equality(probe.CompactIndex),
        "native_delegation": proxy_equality(NativeDelegation),
    }
)
if any(row["dict"] != row["native_delegation"] for row in results):
    raise AssertionError("Native-delegation refinement still differs")
print(
    json.dumps(
        {
            "counterexamples": results,
            "implication": "Measured candidate needs native dictionary delegation for general operations before implementation.",
        },
        indent=2,
    )
)
