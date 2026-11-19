"""Allocate only an identity-key draft fact pool at primary completion."""

import gc
import importlib.util
import json
import sys
import time
import tracemalloc
from pathlib import Path

path = Path(__file__).with_name("07-probe.py")
spec = importlib.util.spec_from_file_location("task07_probe", path)
if spec is None or spec.loader is None:
    raise RuntimeError("Missing Task07 probe")
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)
probe.install("baseline")
from benchmarks.graph_memory_fixture import build  # noqa: E402
from clean_ioc import container  # noqa: E402

fields = (
    "service_type",
    "implementation",
    "implementation_type",
    "lifespan",
    "name",
    "tags",
    "build_args",
    "kind",
    "activation",
    "boundary",
    "declared_service_type",
)
original = container._Compiler.compile
result = {}


def compile_primary(self, *args, **kwargs):
    value = original(self, *args, **kwargs)
    gc.collect()
    tracemalloc.start()
    started = time.perf_counter()
    pool = {}
    for draft in self.graph._drafts.values():
        key = tuple(id(getattr(draft, name)) for name in fields)
        pool.setdefault(key, tuple(getattr(draft, name) for name in fields))
    seconds = time.perf_counter() - started
    retained, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    integer_referents = {id(part): part for key in pool for part in key}
    result.update(
        {
            "drafts": len(self.graph._drafts),
            "definitions": len(pool),
            "seconds": seconds,
            "pool_retained_traced_bytes": retained,
            "pool_allocation_peak_bytes": peak,
            "pool_tuple_dict_shallow_bytes": sys.getsizeof(pool)
            + sum(sys.getsizeof(key) + sys.getsizeof(facts) for key, facts in pool.items()),
            "unique_key_integer_referents": len(integer_referents),
            "key_integer_referent_bytes": sum(sys.getsizeof(part) for part in integer_referents.values()),
            "borrowed_definition_referents": "already held by original drafts; not charged twice",
            "ownership": "observer-only pool; original drafts are retained; no replacement or build-peak saving",
        }
    )
    return value


container._Compiler.compile = compile_primary
fixture = build(8, explain_metadata=False)
fixture.runtime.__exit__(None, None, None)
print(json.dumps(result, indent=2))
