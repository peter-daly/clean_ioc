"""Fresh-process build/export/load comparison; run from the repository root.

Unfinished experiment: not ready for production and may be dropped.
Status and findings: docs/graph-artifact-experiment.md.

Example: .venv/bin/python -m benchmarks.graph_artifact_evidence compare --roots 256
"""

import argparse
import gc
import importlib
import json
import os
import platform
import resource
import statistics
import subprocess
import sys
import time
import tracemalloc
from pathlib import Path
from typing import Any, NoReturn

from benchmarks.graph_artifact import SCHEMA, dump_graph, load_graph


def _rss() -> int:
    if sys.platform == "linux":
        for line in Path("/proc/self/status").read_text().splitlines():
            if line.startswith("VmRSS:"):
                return int(line.split()[1]) * 1024
    if sys.platform == "darwin":
        return int(subprocess.check_output(["/bin/ps", "-o", "rss=", "-p", str(os.getpid())])) * 1024  # noqa: S603
    raise RuntimeError("RSS observation is implemented for Linux and macOS")


def _memory(heap: bool) -> dict[str, int]:
    gc.collect()
    result = {
        "rss_bytes": _rss(),
        "peak_rss_bytes": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        * (1 if sys.platform == "darwin" else 1024),
    }
    if heap:
        retained, peak = tracemalloc.get_traced_memory()
        result.update(traced_retained_bytes=retained, traced_peak_bytes=peak)
    return result


def _forbid_compilation(*args, **kwargs) -> NoReturn:
    raise AssertionError("The artifact loader attempted compilation or dependency inspection")


def measure(mode: str, artifact: Path, roots: int, heap: bool) -> dict[str, Any]:
    result: dict[str, Any] = {
        "mode": mode,
        "artifact_schema": SCHEMA,
        "roots": roots,
        "python": platform.python_version(),
        "platform": platform.platform(),
        "machine": platform.machine(),
        "instrumentation": "tracemalloc" if heap else "none",
        "pid": os.getpid(),
    }
    result["before"] = _memory(False)
    if heap:
        tracemalloc.start()
    if mode == "load":
        from clean_ioc import _legacy, container

        container.ContainerBuilder.build = _forbid_compilation
        container._Compiler.__init__ = _forbid_compilation
        setattr(_legacy, "_set_up_dependencies", _forbid_compilation)
        if "benchmarks.graph_artifact_fixture" in sys.modules:
            raise AssertionError("The load process imported the fixture before measurement")
    started = time.perf_counter()
    if mode == "load":
        runtime = load_graph(artifact)
    else:
        fixture = importlib.import_module("benchmarks.graph_artifact_fixture")
        runtime = fixture.build(roots)
    result["prepare_seconds"] = time.perf_counter() - started
    result["prepared"] = _memory(heap)
    if mode == "export":
        started = time.perf_counter()
        result.update(dump_graph(runtime, artifact))
        result["export_seconds"] = time.perf_counter() - started
        result["exported"] = _memory(heap)
    fixture = importlib.import_module("benchmarks.graph_artifact_fixture")
    if fixture.ACTIVATIONS:
        raise AssertionError("Building/loading unexpectedly constructed application instances")
    root_types = tuple(runtime._plan.default_roots)
    if len(root_types) != roots:
        raise AssertionError("Artifact root count differs from the requested fixture")
    result["physical_records"] = len(runtime._plan.graph._records or ())
    if result["physical_records"] != roots * 256:
        raise AssertionError("Unexpected component record count")
    started = time.perf_counter()
    instances = [runtime.resolve(service) for service in root_types]
    result["resolve_seconds"] = time.perf_counter() - started
    result["resolved"] = _memory(heap)
    if heap:
        tracemalloc.stop()
    # Validation runs after measurements: its own sets and manifest are not part
    # of the reported preparation/resolution peak or retained memory.
    result["resolved_graph"] = fixture.inspect_instances(instances)
    result["activations"] = fixture.ACTIVATIONS
    if result["activations"] != roots * 256:
        raise AssertionError("Unexpected activation count")
    result["graph_fingerprint"] = runtime.graph.manifest(all_roots=True).fingerprint
    result["compilation_disabled"] = mode == "load"
    runtime.__exit__()
    return result


def compare(arguments) -> dict[str, Any]:
    runs = []
    for heap in (False, True):
        for repeat in range(arguments.repeats):
            triplet = []
            for mode in ("compile", "export", "load"):
                command = [
                    sys.executable,
                    "-m",
                    "benchmarks.graph_artifact_evidence",
                    mode,
                    "--roots",
                    str(arguments.roots),
                    "--artifact",
                    str(arguments.artifact),
                ]
                if heap:
                    command.append("--heap")
                run = json.loads(subprocess.check_output(command, text=True))  # noqa: S603
                run["repeat"] = repeat + 1
                runs.append(run)
                triplet.append(run)
                print(f"{mode}, {'heap' if heap else 'RSS'}, repeat {repeat + 1}: done", file=sys.stderr)
            if len({run["graph_fingerprint"] for run in triplet}) != 1:
                raise AssertionError("Compilation and artifact loading produced different graphs")
    medians = {}
    for mode in ("compile", "export", "load"):
        samples = [run for run in runs if run["mode"] == mode and run["instrumentation"] == "none"]
        heaps = [run for run in runs if run["mode"] == mode and run["instrumentation"] == "tracemalloc"]
        medians[mode] = {
            "prepare_seconds": statistics.median(run["prepare_seconds"] for run in samples),
            "resolve_seconds": statistics.median(run["resolve_seconds"] for run in samples),
            **{
                stage: {
                    **{key: statistics.median(run[stage][key] for run in samples) for key in samples[0][stage]},
                    **{
                        key: statistics.median(run[stage][key] for run in heaps)
                        for key in ("traced_retained_bytes", "traced_peak_bytes")
                    },
                }
                for stage in ("prepared", "resolved")
            },
        }
    return {"roots": arguments.roots, "repeats": arguments.repeats, "medians": medians, "runs": runs}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("compile", "export", "load", "compare"))
    parser.add_argument("--roots", type=int, default=256)
    parser.add_argument("--artifact", type=Path, default=Path(".cache/graph-artifact/graph.jsonl"))
    parser.add_argument("--heap", action="store_true")
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--output", type=Path)
    arguments = parser.parse_args()
    if not 1 <= arguments.roots <= 512 or arguments.repeats < 1:
        parser.error("roots must be 1..512 and repeats must be positive")
    result = (
        compare(arguments)
        if arguments.mode == "compare"
        else measure(arguments.mode, arguments.artifact, arguments.roots, arguments.heap)
    )
    encoded = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if arguments.output:
        arguments.output.parent.mkdir(parents=True, exist_ok=True)
        arguments.output.write_text(encoded)
    else:
        print(encoded, end="")


if __name__ == "__main__":
    main()
