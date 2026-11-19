"""Separate normal/traced export and load, parked private full-metadata fixture."""

# ruff: noqa: E402, S101, S603
import asyncio
import gc
import json
import subprocess
import sys
import time
import tracemalloc
from pathlib import Path

HERE = Path(__file__).parent
if sys.argv[1] == "sample":
    policy, operation, kind = sys.argv[2:]
    from source_loader import LOADED, ROOT, install

    install(policy)
    from benchmarks import graph_memory_evidence as evidence
    from benchmarks import graph_memory_fixture as code
    from benchmarks.graph_artifact import SCHEMA, dump_graph, load_graph
    from clean_ioc import container
    from clean_ioc._compact_index import _CompactIndex

    path = ROOT / ".cache" / "graph-memory-task15" / (policy + ".jsonl")
    path.parent.mkdir(parents=True, exist_ok=True)
    heap = kind == "heap"
    if heap:
        tracemalloc.start()
    if operation == "export":
        fixture = code.build(8, explain_metadata=True, diagnostics=False, allow_scope_builders=False)
        runtime = fixture.runtime
    else:

        def forbidden(*args, **kwargs):
            raise AssertionError("Artifact load attempted compilation")

        container._Compiler.__init__ = forbidden
        container.ContainerBuilder.build = forbidden
    gc.collect()
    if heap:
        tracemalloc.reset_peak()
    started = time.perf_counter()
    if operation == "export":
        artifact = dump_graph(runtime, path)
    else:
        runtime = load_graph(path)
        artifact = {"artifact_bytes": path.stat().st_size}
    seconds = time.perf_counter() - started
    memory = evidence._memory(heap)
    if heap:
        tracemalloc.stop()
    if operation == "load":
        sources = {root.component.name: root.component.id for root in runtime._plan.roots[code.RouteSource]}
        fixture = code.Fixture(runtime, sources, {}, dict(code.TEMPLATE_CALLS))  # ty: ignore[invalid-argument-type]

    async def resolve():
        started = time.perf_counter()
        held = await code.resolve_workload(fixture)
        elapsed = time.perf_counter() - started
        validated = code.validate(fixture, held)
        await held.scope.__aexit__(None, None, None)
        await runtime.__aexit__(None, None, None)
        return elapsed, validated

    resolve_seconds, validated = asyncio.run(resolve())
    capacities = {}
    for name in ("occurrence_origins", "decorator_explanations"):
        backing = gc.get_referents(getattr(runtime._plan, name))[0]
        capacities[name] = (
            backing.capacity() if type(backing) is _CompactIndex else {"shallow_bytes": sys.getsizeof(backing)}
        )
    print(
        json.dumps(
            {
                "policy": policy,
                "operation": operation,
                "kind": kind,
                "pid": __import__("os").getpid(),
                "schema": SCHEMA,
                "loaded": LOADED,
                "seconds": seconds,
                "memory": memory,
                "resolve_seconds": resolve_seconds,
                "validated": validated,
                "artifact": artifact,
                "capacities": capacities,
            }
        )
    )
else:
    rows = []
    for operation in ("export", "load"):
        for repeat in range(3):
            for kind in ("normal", "heap"):
                for policy in ("before", "after"):
                    row = json.loads(
                        subprocess.check_output(
                            [sys.executable, __file__, "sample", policy, operation, kind], text=True
                        )
                    )
                    rows.append(row)
                    (HERE / "artifacts.json").write_text(json.dumps(rows, indent=2) + "\n")
                    print(operation, repeat, kind, policy, row["seconds"], flush=True)
