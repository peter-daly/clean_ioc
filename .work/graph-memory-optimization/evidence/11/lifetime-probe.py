"""Bounded saved-validation-view ownership probe; one fresh process per sample."""

import gc
import hashlib
import json
import platform
import resource
import sys
import time
import tracemalloc
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))

from clean_ioc import ContainerBuilder, ContainerBuildError, WarmupPlan, WarmupTarget  # noqa: E402


def build(fail):
    saved = []
    builder = ContainerBuilder().set_provider_roots(())
    boundary = builder.create_boundary("commands")

    class Leaf:
        pass

    class Command:
        def __init__(self, leaf: Leaf):
            self.leaf = leaf

    builder.register(Leaf, lifespan="singleton")
    boundary.register(Leaf, lifespan="singleton")
    for index in range(160):
        builder.register(Command, name=str(index))
        boundary.register(Command, name=str(index))
    builder.add_warmup_plan(WarmupPlan("startup", [WarmupTarget(Leaf)]))

    def inspect(context):
        graph = context.graph
        graph.manifest(all_roots=True)
        graph.ownership_report()
        graph.analysis_index()
        saved.append(graph)
        if fail:
            return [next(graph.walk()).issue("refused", "Deliberate rule rejection")]
        return ()

    builder.add_validation_rule(inspect)
    boundary.add_validation_rule(inspect)
    try:
        retained = builder.build()
    except ContainerBuildError as error:
        # Exception traceback chains and the caller's mutable builder are separate
        # owners. This probe isolates documented error/report/view ownership.
        retained = error
        pending: list[BaseException] = [error]
        while pending:
            current = pending.pop()
            pending.extend(e for e in (current.__cause__, current.__context__) if e is not None)
            current.__traceback__ = current.__cause__ = current.__context__ = None
    return retained, saved


traced = "--traced" in sys.argv
fail = "--failure" in sys.argv
if traced:
    tracemalloc.start()
started = time.perf_counter()
retained, saved = build(fail)
elapsed = time.perf_counter() - started
gc.collect()
current, peak = tracemalloc.get_traced_memory() if traced else (None, None)
print(
    json.dumps(
        {
            "traced": traced,
            "failure": fail,
            "seconds": elapsed,
            "python_retained": current,
            "python_peak": peak,
            "peak_rss_bytes": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
            "saved_views": len(saved),
            "active_views": sum(g.explain_metadata_enabled for g in saved),
            "origin_entries": sum(len(g._occurrence_origins) for g in saved),
            "cached_manifests": sum(len(g._manifest_cache) for g in saved),
            "error_graph": bool(fail and retained.compiled_graph is not None),
            "report_graph": bool(fail and retained.report._graph is not None),
            "python": sys.version,
            "platform": platform.platform(),
            "source_hashes": {
                name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
                for name in ("clean_ioc/container.py", "clean_ioc/tooling.py")
            },
        }
    )
)
