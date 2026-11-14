"""One fresh-process retained-heap sample; run separately from time benchmarks.

Example: uv run python -m benchmarks.runtime_memory_evidence --routes 4
Tracing starts after imports and includes declarations and compilation. Retained
bytes are sampled after GC with the runtime (and optional verification report)
alive. This measures Python allocations, not process RSS.
"""

import argparse
import gc
import hashlib
import json
import platform
import tracemalloc
from pathlib import Path

from benchmarks.graph_memory_fixture import build
from clean_ioc import container


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--routes", type=int, default=4)
    parser.add_argument("--operation", choices=("build", "verify"), default="build")
    arguments = parser.parse_args()
    gc.collect()
    tracemalloc.start()
    fixture = build(arguments.routes, operation=arguments.operation)
    try:
        gc.collect()
        retained, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        records = fixture.runtime._plan.graph._records
        if records is None:
            raise AssertionError("Runtime graph was not frozen")
        print(
            json.dumps(
                {
                    "python": platform.python_version(),
                    "platform": platform.platform(),
                    "container_sha256": hashlib.sha256(Path(container.__file__).read_bytes()).hexdigest(),
                    "routes": arguments.routes,
                    "operation": arguments.operation,
                    "traced_retained_bytes": retained,
                    "traced_peak_bytes": peak,
                    "runtime_records": len(records),
                    "selected_registrations": len(fixture.runtime.selected_registrations),
                }
            )
        )
    finally:
        tracemalloc.stop()
        fixture.runtime.__exit__()
        if fixture.analysis is not None:
            fixture.analysis.close()


if __name__ == "__main__":
    main()
