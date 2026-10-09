"""Separate-process compilation/export/loading of the richer memory fixture.

Local unfinished experiment, not a supported persistence API.
"""

import argparse
import asyncio
import hashlib
import importlib
import json
import os
import platform
import statistics
import subprocess
import sys
import time
import tracemalloc
from pathlib import Path

from benchmarks.graph_artifact import SCHEMA, dump_graph, load_graph
from benchmarks.graph_artifact_evidence import _forbid_compilation, _memory
from benchmarks.graph_memory_evidence import census, source_provenance


def provenance():
    result = source_provenance()
    result["artifact_experiment_hashes"] = {
        str(path): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in (
            Path(__file__),
            Path(__file__).with_name("graph_artifact.py"),
            Path(__file__).with_name("graph_artifact_evidence.py"),
        )
    }
    return result


def runtime_link_fingerprint(runtime):
    """Compare stored runtime links without requesting a public inspection graph."""
    rows = [
        (
            occurrence,
            record.parent_id,
            record.owner_id,
            record.decorated_id,
            record.dependency_ids,
            record.decorator_ids,
            record.pre_configuration_ids,
        )
        for occurrence, record in sorted(runtime._plan.graph._records.items())
    ]
    payload = {
        "records": rows,
        "contexts": [(view.index, view.root, view.parent) for view in runtime._plan.graph._views],
    }
    return hashlib.sha256(json.dumps(payload, separators=(",", ":")).encode()).hexdigest()


async def measure(mode: str, artifact: Path, routes: int, heap: bool, explain_metadata: bool = True):
    if "benchmarks.graph_memory_fixture" in sys.modules:
        raise AssertionError("Run each observation in a fresh process")
    result = {
        "mode": mode,
        "routes": routes,
        "explain_metadata": explain_metadata,
        "diagnostics": False,
        "allow_scope_builders": False,
        "artifact_schema": SCHEMA,
        "source": provenance(),
        "python": platform.python_version(),
        "platform": platform.platform(),
        "machine": platform.machine(),
        "pid": os.getpid(),
        "instrumentation": "tracemalloc" if heap else "none",
        "before": _memory(False),
    }
    if mode == "load":
        from clean_ioc import _legacy, container

        container.ContainerBuilder.build = _forbid_compilation
        container.ScopeBuilder.build = _forbid_compilation
        container._Compiler.__init__ = _forbid_compilation
        setattr(container, "_retain_runtime_graph", _forbid_compilation)
        setattr(container, "_release_execution_composition", _forbid_compilation)
        _legacy._Registration.__init__ = _forbid_compilation
        setattr(_legacy, "_set_up_dependencies", _forbid_compilation)
    if heap:
        tracemalloc.start()
    started = time.perf_counter()
    if mode == "load":
        runtime = load_graph(artifact)
        result["prepare_seconds"] = time.perf_counter() - started
        result["prepared"] = _memory(heap)
        fixture = importlib.import_module("benchmarks.graph_memory_fixture")
        source_ids = {}
        for root in runtime._plan.roots[fixture.RouteSource]:
            name = root.component.name
            if not isinstance(name, str):
                raise AssertionError("A fixture source is missing its route name")
            source_ids[name] = root.component.id
        case = fixture.Fixture(runtime, source_ids, {}, {})
        if fixture.TEMPLATE_CALLS:
            raise AssertionError("Loading invoked template callbacks")
    else:
        fixture = importlib.import_module("benchmarks.graph_memory_fixture")
        case = fixture.build(routes, explain_metadata=explain_metadata)
        runtime = case.runtime
        result["prepare_seconds"] = time.perf_counter() - started
        result["prepared"] = _memory(heap)
    held = None
    try:
        if runtime.explain_metadata_enabled is not explain_metadata:
            raise AssertionError("Artifact metadata mode differs from the requested mode")
        if len(case.source_ids) != routes or fixture.ACTIVATIONS:
            raise AssertionError("Wrong fixture size or preparation activated application objects")
        result["template_calls"] = dict(fixture.TEMPLATE_CALLS)
        result["compilation_disabled"] = mode == "load"
        if mode == "export":
            started = time.perf_counter()
            result.update(dump_graph(runtime, artifact))
            result["export_seconds"] = time.perf_counter() - started
            result["exported"] = _memory(heap)
        elif mode == "load":
            result["artifact_bytes"] = artifact.stat().st_size
        started = time.perf_counter()
        held = await fixture.resolve_workload(case)
        result["resolve_seconds"] = time.perf_counter() - started
        result["resolved"] = _memory(heap)
        if heap:
            tracemalloc.stop()
        # Census and validation are deliberately outside all measured phases.
        result["validated"] = fixture.validate(case, held)
        result["activations"] = dict(fixture.ACTIVATIONS)
        result["lazy_activations"] = held.lazy_counts
        result["graph"] = census(runtime)
        result["runtime_link_fingerprint"] = runtime_link_fingerprint(runtime)
        if explain_metadata:
            result["graph_fingerprint"] = runtime.graph.manifest(all_roots=True).fingerprint
        else:
            result["graph_fingerprint"] = None
            if any(result["graph"]["metadata_entries"].values()):
                raise AssertionError("Reduced artifact retained explanation metadata")
            for _ in range(2):
                try:
                    _ = runtime.graph
                except RuntimeError as error:
                    if "explain-metadata-disabled" not in str(error):
                        raise
                else:
                    raise AssertionError("Reduced artifact exposes a complete inspection graph")
            if runtime._plan.compiled_graph is not None:
                raise AssertionError("Reduced inspection reconstructed a graph")
        if mode in ("export", "load"):
            with artifact.open("rb") as stream:
                result["artifact_sha256"] = hashlib.file_digest(stream, "sha256").hexdigest()
        if dict(fixture.TEMPLATE_CALLS) != result["template_calls"]:
            raise AssertionError("Resolution or inspection reran a template")
        return result
    finally:
        if tracemalloc.is_tracing():
            tracemalloc.stop()
        if held is not None:
            await held.scope.__aexit__(None, None, None)
        await runtime.__aexit__(None, None, None)


def _equivalence(run):
    graph = run["graph"]
    return {
        "explain_metadata": run["explain_metadata"],
        "fingerprint": run["graph_fingerprint"],
        "runtime_links": run["runtime_link_fingerprint"],
        "validated": run["validated"],
        "activations": run["activations"],
        "lazy_activations": run["lazy_activations"],
        **{
            key: graph[key]
            for key in (
                "physical_records",
                "unique_execution_steps",
                "provider_view_contexts",
                "record_kinds",
                "activation_kinds",
                "logical_graph_visits",
            )
        },
        "definitions": graph["component_metadata"]["shared_definition_objects"],
        "decorator_objects": graph["decorator_objects"]["unique_objects"],
        "decorator_outcomes": graph["decorator_objects"]["logical_outcomes_by_entry"],
        "registration_carrier_kinds": graph["registration_carrier_kinds"],
        "metadata_entries": graph["metadata_entries"],
        "retained_execution_composition": graph["retained_execution_composition"],
    }


def compare(arguments):
    runs = []
    for heap in (False, True):
        for repeat in range(arguments.repeats):
            triplet = []
            for mode in ("compile", "export", "load"):
                command = [
                    sys.executable,
                    "-m",
                    "benchmarks.graph_memory_artifact_evidence",
                    mode,
                    "--routes",
                    str(arguments.routes),
                    "--artifact",
                    str(arguments.artifact),
                ]
                if heap:
                    command.append("--heap")
                if arguments.no_explain_metadata:
                    command.append("--no-explain-metadata")
                run = json.loads(subprocess.check_output(command, text=True))  # noqa: S603
                run["repeat"] = repeat + 1
                runs.append(run)
                triplet.append(run)
                print(f"{mode}, {'heap' if heap else 'RSS'}, repeat {repeat + 1}: done", file=sys.stderr)
            if any(_equivalence(run) != _equivalence(triplet[0]) for run in triplet[1:]):
                raise AssertionError("Compiled and loaded graph structure or resolution differs")
            if triplet[1]["artifact_sha256"] != triplet[2]["artifact_sha256"]:
                raise AssertionError("Loader did not read the exported artifact")
    if any(run["source"] != runs[0]["source"] for run in runs[1:]):
        raise AssertionError("Sources changed during the comparison")
    if any(_equivalence(run) != _equivalence(runs[0]) for run in runs[1:]):
        raise AssertionError("Structure or resolution differs across repetitions")
    medians = {}
    for mode in ("compile", "export", "load"):
        normal = [run for run in runs if run["mode"] == mode and run["instrumentation"] == "none"]
        traced = [run for run in runs if run["mode"] == mode and run["instrumentation"] == "tracemalloc"]
        stages = ("prepared", "resolved", "exported") if mode == "export" else ("prepared", "resolved")
        timings = (
            ("prepare_seconds", "resolve_seconds", "export_seconds")
            if mode == "export"
            else (
                "prepare_seconds",
                "resolve_seconds",
            )
        )
        medians[mode] = {key: statistics.median(run[key] for run in normal) for key in timings}
        for stage in stages:
            medians[mode][stage] = {
                **{key: statistics.median(run[stage][key] for run in normal) for key in normal[0][stage]},
                **{
                    key: statistics.median(run[stage][key] for run in traced)
                    for key in ("traced_retained_bytes", "traced_peak_bytes")
                },
            }
    return {
        "routes": arguments.routes,
        "repeats": arguments.repeats,
        "explain_metadata": not arguments.no_explain_metadata,
        "medians": medians,
        "runs": runs,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("compile", "export", "load", "compare"))
    parser.add_argument("--routes", type=int, default=8)
    parser.add_argument("--artifact", type=Path, default=Path(".cache/graph-artifact/rich-graph.jsonl"))
    parser.add_argument("--heap", action="store_true")
    parser.add_argument("--no-explain-metadata", action="store_true")
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--output", type=Path)
    arguments = parser.parse_args()
    if not 1 <= arguments.routes <= 128 or arguments.repeats < 1:
        parser.error("routes must be 1..128 and repeats must be positive")
    if arguments.mode == "compare" and arguments.heap:
        parser.error("compare already runs separate normal and traced processes")
    result = (
        compare(arguments)
        if arguments.mode == "compare"
        else asyncio.run(
            measure(
                arguments.mode, arguments.artifact, arguments.routes, arguments.heap, not arguments.no_explain_metadata
            )
        )
    )
    encoded = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if arguments.output:
        arguments.output.parent.mkdir(parents=True, exist_ok=True)
        arguments.output.write_text(encoded)
    else:
        print(encoded, end="")


if __name__ == "__main__":
    main()
