import asyncio
import importlib
import json
import sys
import time
import tracemalloc
from pathlib import Path

from benchmarks.graph_memory_evidence import source_provenance
from clean_ioc.components import _ComponentGraph

samples = []
original = _ComponentGraph.freeze


def freeze(self: _ComponentGraph) -> None:
    current, prior_peak = tracemalloc.get_traced_memory()
    tracemalloc.reset_peak()
    started = time.perf_counter()
    original(self)
    after, peak = tracemalloc.get_traced_memory()
    samples.append(
        dict(
            records=len(self._records or {}),
            seconds=time.perf_counter() - started,
            before_bytes=current,
            after_bytes=after,
            freeze_peak_bytes=peak,
            earlier_build_peak_bytes=prior_peak,
        )
    )


_ComponentGraph.freeze = freeze
tracemalloc.start()
fixture = importlib.import_module("benchmarks.graph_memory_fixture")
case = fixture.build(2)
result = dict(source=source_provenance(), routes=2, python=sys.version, samples=samples)
Path(sys.argv[1]).write_text(json.dumps(result, indent=2) + "\n")
asyncio.run(case.runtime.__aexit__(None, None, None))
