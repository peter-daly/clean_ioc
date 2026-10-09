"""Separate untraced default-allocator attribution, never a production change."""

import gc
import json
import os
import sys
import sysconfig
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from benchmarks.graph_memory_evidence import _memory, source_provenance
from benchmarks.graph_memory_fixture import build

result = {
    "source": source_provenance(),
    "python": sys.version,
    "PYTHONMALLOC": os.environ.get("PYTHONMALLOC"),
    "WITH_PYMALLOC": sysconfig.get_config_var("WITH_PYMALLOC"),
    "Py_GIL_DISABLED": sysconfig.get_config_var("Py_GIL_DISABLED"),
    "routes": 8,
    "diagnostics": False,
    "explain_metadata": False,
    "allow_scope_builders": False,
    "note": "sys._debugmallocstats output is stderr; RSS observations force collection",
}
gc.collect()
result["before"] = _memory(False)
print("BEFORE BUILD", file=sys.stderr, flush=True)
sys._debugmallocstats()
fixture = build(8, explain_metadata=False, allow_scope_builders=False)
result["after_build_gc"] = _memory(False)
print("AFTER BUILD AND GC", file=sys.stderr, flush=True)
sys._debugmallocstats()
fixture.runtime.__exit__(None, None, None)
del fixture
gc.collect()
result["after_runtime_release_gc"] = _memory(False)
print("AFTER RUNTIME RELEASE AND GC", file=sys.stderr, flush=True)
sys._debugmallocstats()
print(json.dumps(result, indent=2, sort_keys=True))
