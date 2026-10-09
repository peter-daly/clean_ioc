"""Measured reduced final-validation rejection; retain published graph evidence."""

import argparse
import hashlib
import importlib.util
import json
import time
import tracemalloc
from pathlib import Path

path = Path(__file__).with_name("09-probe.py")
spec = importlib.util.spec_from_file_location("task09_probe", path)
if spec is None or spec.loader is None:
    raise RuntimeError("Missing Task09 probe")
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)
parser = argparse.ArgumentParser()
parser.add_argument("--probe", default="both")
parser.add_argument("--heap", action="store_true")
parser.add_argument("--diagnostics", action="store_true")
args = parser.parse_args()
probe.install(args.probe)
from benchmarks.graph_memory_evidence import _memory  # noqa: E402
from clean_ioc import BuildIssue, ContainerBuilder, ContainerBuildError, IssueSeverity  # noqa: E402

original = ContainerBuilder.build


def refuse(self, *arguments, **keywords):
    self.add_validation_rule(lambda graph: [BuildIssue("task09-refused", IssueSeverity.error, "task09-refused")])
    return original(self, *arguments, **keywords)


ContainerBuilder.build = refuse
result = {
    "probe": args.probe,
    "diagnostics": args.diagnostics,
    "instrumentation": "tracemalloc" if args.heap else "none",
    "before": _memory(False),
    "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
}
if args.heap:
    tracemalloc.start()
started = time.perf_counter()
from benchmarks.graph_memory_fixture import build  # noqa: E402

try:
    build(2, diagnostics=args.diagnostics, explain_metadata=False, allow_scope_builders=False)
except ContainerBuildError as error:
    result["build_seconds"] = time.perf_counter() - started
    # Keep only the published evidence, not compiler tracebacks.
    graph, report = error.compiled_graph, error.report
else:
    raise AssertionError("Expected failed final validation")
result["failed"] = _memory(args.heap)
if args.heap:
    tracemalloc.stop()
if graph is None or report is None:
    raise AssertionError("Expected published final-validation evidence")
result["roots"] = len(graph.roots)
result["manifest"] = graph.manifest(all_roots=True).fingerprint
result["issues"] = [issue.code for issue in report.issues]
result["decorator_selected"] = sum(len(graph.explain_decorators(root.component).selected) for root in graph.roots)
result["compatibility"] = probe.compatibility()
print(json.dumps(result, indent=2, sort_keys=True))
