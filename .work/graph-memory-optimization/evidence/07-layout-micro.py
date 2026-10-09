"""Separate layout allocation and mutable shared-fact screens; no build measurement."""

# ruff: noqa: S101
import gc
import hashlib
import importlib.util
import json
import sys
import time
import tracemalloc
import weakref
from pathlib import Path

path = Path(__file__).with_name("07-probe.py")
spec = importlib.util.spec_from_file_location("task07_probe", path)
if spec is None or spec.loader is None:
    raise RuntimeError("Cannot load Task07 probe")
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)
probe.install(sys.argv[1])
from clean_ioc import _legacy, components, container, tooling  # noqa: E402


def allocate(factory, count):
    gc.collect()
    tracemalloc.start()
    started = time.perf_counter()
    values = [factory() for _ in range(count)]
    duration = time.perf_counter() - started
    retained, peak = tracemalloc.get_traced_memory()
    shallow = sum(sys.getsizeof(value) for value in values)
    tracemalloc.stop()
    return {
        "count": count,
        "seconds": duration,
        "retained_bytes": retained,
        "peak_bytes": peak,
        "instance_shallow_bytes": shallow,
        "list_bytes": sys.getsizeof(values),
        "weakref_ok": weakref.ref(values[0])() is values[0],
    }


class CowFacts:
    __slots__ = ("definition", "pool")

    def __init__(self, values, pool):
        self.pool = pool
        self.definition = self.intern(values)

    def intern(self, values):
        key = tuple(id(value) for value in values)
        return self.pool.setdefault(key, values)

    def replace(self, index, value):
        values = list(self.definition)
        values[index] = value
        self.definition = self.intern(tuple(values))


pool = {}
values = tuple(object() for _ in range(11))
a = CowFacts(values, pool)
b = CowFacts(values, pool)
assert a.definition is b.definition
old = a.definition
a.replace(0, object())
assert b.definition is old and a.definition is not old
a.replace(0, old[0])
assert a.definition is b.definition


class Payload:
    pass


payload = Payload()
payload_reference = weakref.ref(payload)
a.replace(0, payload)
del payload
a.replace(0, old[0])
gc.collect()
alive_before_clear = payload_reference() is not None
assert alive_before_clear
pool.clear()
gc.collect()
alive_after_clear = payload_reference() is not None
assert not alive_after_clear


result = {
    "probe": sys.argv[1],
    "python": sys.version,
    "transformed_hashes": probe.TRANSFORM_HASHES,
    "source_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    "values": [allocate(lambda: container._ValueStep(1), 100_000) for _ in range(3)],
    "cow_pool_lifetime": {
        "unused_fact_alive_before_clear": alive_before_clear,
        "unused_fact_alive_after_clear": alive_after_clear,
    },
    "cow_checks": "shared fact tuple; replacement isolated; restoring previous fact reunites identity",
    "draft_slots": len(components._ComponentDraft.__slots__),
    "metadata_layouts": [
        {
            "name": cls.__name__,
            "dict_offset": cls.__dictoffset__,
            "weakref_offset": cls.__weakrefoffset__,
            "shallow_bytes": sys.getsizeof(object.__new__(cls)),
            "slots": cls.__dict__.get("__slots__"),
        }
        for cls in (
            components.Component,
            components._ComponentDraft,
            components._ComponentRecord,
            components._ComponentDefinition,
            components._ComponentGraph,
            components._ComponentViewContext,
            components._ComponentViewRecord,
            tooling.CandidateDecision,
            tooling.TemplateDecision,
            tooling.CompilationExplanation,
            tooling.ParameterExplanation,
            tooling.GenericBindingExplanation,
            tooling._RemappedDecoratorExplanation,
            container._CompiledDependency,
            container._CompiledDecorator,
        )
    ],
    "legacy_mro": [
        {
            "name": base.__name__,
            "dict_offset": base.__dictoffset__,
            "weakref_offset": base.__weakrefoffset__,
            "slots": base.__dict__.get("__slots__"),
        }
        for base in _legacy._Registration.__mro__
    ],
}
print(json.dumps(result, indent=2))
