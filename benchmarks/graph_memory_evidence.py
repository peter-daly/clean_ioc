"""Fresh-process memory evidence for templates, providers and provider maps.

Run: python -m benchmarks.graph_memory_evidence repeat --routes 8 --repeats 3
"""

import argparse
import asyncio
import dataclasses
import gc
import hashlib
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
from collections import Counter
from pathlib import Path
from unittest.mock import patch

from clean_ioc import container as runtime_code


def _memory(heap):
    gc.collect()
    if sys.platform == "darwin":
        rss = int(subprocess.check_output(["/bin/ps", "-o", "rss=", "-p", str(os.getpid())])) * 1024  # noqa: S603
    elif sys.platform == "linux":
        rss = next(
            int(line.split()[1]) * 1024
            for line in Path("/proc/self/status").read_text().splitlines()
            if line.startswith("VmRSS:")
        )
    else:
        raise RuntimeError("RSS observation is implemented for Linux and macOS")
    result = {
        "rss_bytes": rss,
        "peak_rss_bytes": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        * (1 if sys.platform == "darwin" else 1024),
    }
    if heap:
        retained, peak = tracemalloc.get_traced_memory()
        result.update(traced_retained_bytes=retained, traced_peak_bytes=peak)
    return result


def decorator_census(runtime):
    """Identity census outside timed intervals; sizes exclude referenced objects."""
    explanations, decisions, templates, tuples = {}, {}, {}, {}
    logical_outcomes, logical_reasons = Counter(), Counter()
    patterns = {}
    for explanation in runtime._plan.decorator_explanations.values():
        explanations[id(explanation)] = explanation
        source = (
            explanation.source if isinstance(explanation, runtime_code._RemappedDecoratorExplanation) else explanation
        )
        explanations[id(source)] = source
        patterns[id(source)] = source
        for group in (source.selected, source.rejected):
            tuples[id(group)] = group
            for decision in group:
                decisions[id(decision)] = decision
                logical_outcomes[decision.outcome.value] += 1
                logical_reasons.update(decision.reason_codes)
                if decision.template is not None:
                    templates[id(decision.template)] = decision.template
    groups = {
        "explanations": explanations,
        "decisions": decisions,
        "template_facts": templates,
        "decision_tuples": tuples,
    }
    return {
        "unique_objects": {name: len(values) for name, values in groups.items()},
        "unique_patterns": len(patterns),
        "logical_outcomes_by_entry": dict(logical_outcomes),
        "logical_reason_codes_by_entry": dict(logical_reasons),
        "shallow_storage_bytes": {name: sum(map(sys.getsizeof, values.values())) for name, values in groups.items()},
        "outcomes": dict(Counter(value.outcome.value for value in decisions.values())),
        "reason_codes": dict(Counter(code for value in decisions.values() for code in value.reason_codes)),
    }


DEFINITION_FIELDS = (
    "id",
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


def component_census(records):
    """Identity-only equivalence census: never hash or compare application values."""
    patterns = Counter()
    definition_patterns = set()
    fields = {name: set() for name in DEFINITION_FIELDS}
    kinds = {}
    definitions = {}
    for record in records.values():
        key = tuple(
            tuple(id(tag) for tag in record.tags) if name == "tags" else id(getattr(record, name))
            for name in DEFINITION_FIELDS
        )
        patterns[key] += 1
        definition_patterns.add(key[1:])
        kinds.setdefault(record.kind.value, set()).add(key)
        for name in DEFINITION_FIELDS:
            fields[name].add(id(getattr(record, name)))
        definition = getattr(record, "_definition", None)
        if definition is not None:
            definitions[id(definition)] = definition
    return {
        "identity_patterns": len(patterns),
        "definition_identity_patterns": len(definition_patterns),
        "patterns_by_kind": {name: len(values) for name, values in kinds.items()},
        "unique_field_objects": {name: len(values) for name, values in fields.items()},
        "shared_definition_objects": len(definitions),
        "shared_definition_bytes": sum(map(sys.getsizeof, definitions.values())),
        "retained_definition_index_bytes": 0,
    }


def census(runtime):
    """Count shared execution objects once; do not equate shallow sizes with RSS."""
    plan = runtime._plan
    root_plans = [
        root
        for roots in (plan.roots, plan.provider_roots, plan.managed_provider_roots, plan.warmup_steps)
        for group in roots.values()
        for root in group
    ]
    root_plans.extend(root for _, _, root in plan.architecture_roots)
    pending = [root.step for root in root_plans]
    seen, steps, registrations = set(), {}, {}
    helpers = Counter()
    retained_composition = Counter()
    executable_types = (
        runtime_code._Step,
        runtime_code._CompiledDependency,
        runtime_code._CompiledDecorator,
        runtime_code._CompiledPreConfiguration,
        runtime_code._CompiledResolutionRequest,
    )
    while pending:
        value = pending.pop()
        if id(value) in seen:
            continue
        seen.add(id(value))
        if isinstance(value, (tuple, list)):
            pending.extend(value)
        elif isinstance(value, executable_types):
            if isinstance(value, runtime_code._Step):
                steps[id(value)] = value
            else:
                helpers[type(value).__name__] += 1
            if isinstance(value, runtime_code._RegistrationStep):
                registrations[id(value.registration)] = value.registration
            if isinstance(value, runtime_code._CompiledDecorator):
                retained_composition["decorator_definitions"] += value.source.definition is not None
                retained_composition["decorator_dependency_settings"] += len(value.source.dependencies)
            if isinstance(value, runtime_code._CompiledPreConfiguration):
                retained_composition["preconfiguration_definitions"] += isinstance(
                    value.definition, runtime_code._PreConfigurationDefinition
                )
            pending.extend(getattr(value, field.name) for field in dataclasses.fields(value))
    records = plan.graph._records or {}
    links, occurrence_ids = {}, {}
    for key, record in records.items():
        for value in (key, record.occurrence_id, record.parent_id, record.owner_id, record.decorated_id):
            if isinstance(value, int) and not isinstance(value, bool):
                occurrence_ids[id(value)] = value
        for field in ("dependency_ids", "decorator_ids", "pre_configuration_ids"):
            values = getattr(record, field)
            links[id(values)] = values
            for value in values:
                occurrence_ids[id(value)] = value
    origin_maps = {}
    for mapping in (
        plan.occurrence_origins,
        (plan.compiled_graph._occurrence_origins if plan.compiled_graph else {}),
        getattr(plan.occurrence_layers, "origins", plan.occurrence_layers),
    ):
        backing = gc.get_referents(mapping)[0] if type(mapping).__name__ == "mappingproxy" else mapping
        origin_maps[id(backing)] = backing
    return {
        "decorator_objects": decorator_census(runtime),
        "component_metadata": component_census(records),
        "physical_records": len(records),
        "logical_graph_visits": sum(1 for _ in runtime.graph.walk()) if plan.explain_metadata else None,
        "provider_view_contexts": len(plan.graph._views),
        "record_kinds": dict(Counter(record.kind.value for record in records.values())),
        "activation_kinds": dict(Counter(record.activation.value for record in records.values())),
        "unique_execution_steps": len(steps),
        "execution_step_kinds": dict(Counter(type(step).__name__ for step in steps.values())),
        "unique_registration_objects": len(registrations),
        "registration_carrier_kinds": dict(Counter(type(value).__name__ for value in registrations.values())),
        "retained_execution_composition": {
            **dict(retained_composition),
            "registration_dependency_settings": sum(
                len(getattr(value, "dependencies", ())) for value in registrations.values()
            ),
        },
        "retained_plan_fields": {
            item.name: {
                "type": type(value).__name__,
                "entries": len(value)
                if isinstance(value, (tuple, dict, list, frozenset, runtime_code.Mapping))
                else None,
                "shallow_bytes": sys.getsizeof(gc.get_referents(value)[0])
                if type(value).__name__ == "mappingproxy"
                else sys.getsizeof(value),
            }
            for item in dataclasses.fields(plan)
            for value in (getattr(plan, item.name),)
        },
        "executable_helpers": dict(helpers),
        "selected_registrations": len(plan.selected_registrations),
        "unique_origins": len({id(origin) for origin in plan.occurrence_origins.values()}),
        "shallow_storage_bytes": {
            "component_records": sum(map(sys.getsizeof, records.values())),
            "record_index": sys.getsizeof(records),
            "link_tuples": sum(map(sys.getsizeof, links.values())),
            "occurrence_integers": sum(map(sys.getsizeof, occurrence_ids.values())),
            "origin_indexes": sum(map(sys.getsizeof, origin_maps.values())),
            "execution_steps": sum(map(sys.getsizeof, steps.values())),
            "registration_objects": sum(map(sys.getsizeof, registrations.values())),
        },
        "metadata_entries": {
            name: len(getattr(plan, name))
            for name in (
                "occurrence_explanations",
                "parameter_explanations",
                "generic_explanations",
                "decorator_explanations",
                "root_candidates",
                "census_sources",
                "census_definitions",
            )
        },
    }


def source_provenance():
    files = (
        "clean_ioc/components.py",
        "clean_ioc/container.py",
        "clean_ioc/tooling.py",
        "clean_ioc/selection_census.py",
        "benchmarks/graph_memory_fixture.py",
        "benchmarks/graph_memory_evidence.py",
    )
    return {
        "revision": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),  # noqa: S603,S607
        "local_changes": subprocess.check_output(["git", "status", "--short"], text=True),  # noqa: S603,S607
        "source_sha256": {name: hashlib.sha256(Path(name).read_bytes()).hexdigest() for name in files},
    }


def inspect_graph(runtime):
    """Measure bounded public explanations and full public census separately."""
    graph = runtime.graph
    components = []
    seen = set()
    for visit in graph.walk():
        component = visit.component
        if component.occurrence_id in graph._decorator_explanations and component.occurrence_id not in seen:
            seen.add(component.occurrence_id)
            components.append(component)
            if len(components) == 128:
                break
    result = {"explanation_sample_size": len(components), "passes": []}
    tracemalloc.start()
    try:
        result["before"] = _memory(True)
        for label in ("first", "repeated"):
            started = time.perf_counter()
            decisions = 0
            for component in components:
                explanation = graph.explain_decorators(component)
                decisions += len(explanation.selected) + len(explanation.rejected)
            del explanation
            sample = {"pass": label, "explain_seconds": time.perf_counter() - started, "sample_decisions": decisions}
            sample["after_explanations"] = _memory(True)
            if graph.diagnostics_enabled:
                started = time.perf_counter()
                census_result = graph.selection_census(all_roots=True)
                sample["census_seconds"] = time.perf_counter() - started
                del census_result
                sample["after_census"] = _memory(True)
            started = time.perf_counter()
            visits = 0
            for visit in graph.walk():
                component = visit.component
                for name in DEFINITION_FIELDS:
                    getattr(component, name)
                visits += 1
            sample["traversal_seconds"] = time.perf_counter() - started
            sample["traversal_visits"] = visits
            sample["after_traversal"] = _memory(True)
            started = time.perf_counter()
            manifest = graph.manifest(all_roots=True)
            sample["manifest_seconds"] = time.perf_counter() - started
            sample["manifest_fingerprint"] = manifest.fingerprint
            del manifest
            sample["after_manifest"] = _memory(True)
            result["passes"].append(sample)
        return result
    finally:
        tracemalloc.stop()


async def measure(
    routes: int,
    heap: bool,
    diagnostics: bool,
    inspection: bool = False,
    explain_metadata: bool = True,
    allow_scope_builders: bool = False,
    retain_builder: bool = False,
    capture_selection_views: bool = False,
):
    if "benchmarks.graph_memory_fixture" in sys.modules:
        raise RuntimeError("Run each sample in a fresh process")
    result = {
        "source": source_provenance(),
        "routes": routes,
        "diagnostics": diagnostics,
        "explain_metadata": explain_metadata,
        "allow_scope_builders": allow_scope_builders,
        "ownership": {"retained_builder": retain_builder, "captured_selection_views": capture_selection_views},
        "instrumentation": "tracemalloc" if heap else "none",
        "python": platform.python_version(),
        "platform": platform.platform(),
        "machine": platform.machine(),
        "pid": os.getpid(),
        "before": _memory(False),
    }
    if heap:
        tracemalloc.start()
    started = time.perf_counter()
    fixture_module = importlib.import_module("benchmarks.graph_memory_fixture")
    captured = []
    from clean_ioc import component_filters as cf

    original = cf.with_name

    def recording_with_name(name):
        predicate = original(name)

        def capture(component):
            captured.append(component)
            return predicate(component)

        return capture

    with patch.object(cf, "with_name", recording_with_name if capture_selection_views else original):
        fixture = fixture_module.build(
            routes,
            diagnostics=diagnostics,
            explain_metadata=explain_metadata,
            allow_scope_builders=allow_scope_builders,
            retain_builder=retain_builder,
        )
    result["build_seconds"] = time.perf_counter() - started
    held = None
    try:
        result["prepared"] = _memory(heap)
        result["template_calls"] = dict(fixture_module.TEMPLATE_CALLS)
        started = time.perf_counter()
        held = await fixture_module.resolve_workload(fixture)
        result["resolve_seconds"] = time.perf_counter() - started
        result["resolved"] = _memory(heap)
        if heap:
            tracemalloc.stop()
        # Full topology validation and the census allocate their own indexes;
        # exclude those allocations from all measurements above.
        result["validated"] = fixture_module.validate(fixture, held)
        result["lazy_activations"] = held.lazy_counts
        result["activations"] = dict(fixture_module.ACTIVATIONS)
        result["graph"] = census(fixture.runtime)
        from clean_ioc.components import _ComponentGraph

        graphs = [value for value in gc.get_objects() if type(value) is _ComponentGraph]
        result["retained_graph_inventory"] = {
            "graphs": len(graphs),
            "records": sum(len(value._records or value._drafts) for value in graphs),
            "captured_views": len(captured),
            "saved_views_in_primary_graph": sum(value._graph is fixture.runtime._plan.graph for value in captured),
            "saved_views_in_separate_snapshots": sum(
                value._graph is not fixture.runtime._plan.graph for value in captured
            ),
        }
        del graphs
        if inspection and explain_metadata:
            result["inspection"] = inspect_graph(fixture.runtime)
            fixture_module.require(
                fixture_module.TEMPLATE_CALLS == fixture.callbacks_after_build, "Inspection reran callbacks"
            )
        if inspection and not explain_metadata:
            before = census(fixture.runtime)
            errors = []
            for _ in range(2):
                for operation in (
                    lambda: fixture.runtime.graph,
                    lambda: fixture.runtime.selected_registrations,
                    fixture.runtime.validation_report,
                ):
                    try:
                        operation()
                    except RuntimeError as error:
                        errors.append(str(error))
                    else:
                        raise AssertionError("Reduced inspection unexpectedly succeeded")
            if census(fixture.runtime) != before:
                raise AssertionError("Reduced inspection retained new metadata")
            result["disabled_inspection"] = errors
        return result
    finally:
        if tracemalloc.is_tracing():
            tracemalloc.stop()
        if held is not None:
            await held.scope.__aexit__(None, None, None)
        await fixture.runtime.__aexit__(None, None, None)


def repeat(arguments):
    runs = []
    for index in range(arguments.repeats):
        for heap in (False, True):
            command = [
                sys.executable,
                "-m",
                "benchmarks.graph_memory_evidence",
                "measure",
                "--routes",
                str(arguments.routes),
            ]
            if heap:
                command.append("--heap")
            if arguments.eager_decorator_facts:
                command.append("--eager-decorator-facts")
            if arguments.inspection:
                command.append("--inspection")
            if arguments.diagnostics:
                command.append("--diagnostics")
            for option in ("no_explain_metadata", "allow_scope_builders", "retain_builder", "capture_selection_views"):
                if getattr(arguments, option):
                    command.append("--" + option.replace("_", "-"))
            run = json.loads(subprocess.check_output(command, text=True))  # noqa: S603
            run["repeat"] = index + 1
            runs.append(run)
            print(f"{'heap' if heap else 'RSS'}, repeat {index + 1}: done", file=sys.stderr)
    normal = [run for run in runs if run["instrumentation"] == "none"]
    traced = [run for run in runs if run["instrumentation"] == "tracemalloc"]
    first = runs[0]
    if any(run["graph"] != first["graph"] or run["validated"] != first["validated"] for run in runs[1:]):
        raise AssertionError("Fresh processes disagreed on graph structure or resolution")
    medians = {key: statistics.median(run[key] for run in normal) for key in ("build_seconds", "resolve_seconds")}
    for stage in ("prepared", "resolved"):
        medians[stage] = {
            **{key: statistics.median(run[stage][key] for run in normal) for key in ("rss_bytes", "peak_rss_bytes")},
            **{
                key: statistics.median(run[stage][key] for run in traced)
                for key in ("traced_retained_bytes", "traced_peak_bytes")
            },
        }
    return {"routes": arguments.routes, "repeats": arguments.repeats, "medians": medians, "runs": runs}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("measure", "repeat"), nargs="?", default="measure")
    parser.add_argument("--routes", type=int, default=8)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--heap", action="store_true")
    parser.add_argument("--inspection", action="store_true")
    parser.add_argument(
        "--eager-decorator-facts",
        action="store_true",
        help="Evidence-only eager reference: disable compact patterns and compact clone remapping",
    )
    parser.add_argument("--diagnostics", action="store_true")
    parser.add_argument("--no-explain-metadata", action="store_true")
    parser.add_argument("--allow-scope-builders", action="store_true")
    parser.add_argument("--retain-builder", action="store_true")
    parser.add_argument("--capture-selection-views", action="store_true")
    parser.add_argument("--output", type=Path)
    arguments = parser.parse_args()
    if not 1 <= arguments.routes <= 128 or arguments.repeats < 1:
        parser.error("routes must be 1..128 and repeats must be positive")
    if arguments.mode == "repeat" and arguments.heap:
        parser.error("repeat already runs separate normal and traced samples")
    if arguments.eager_decorator_facts:
        setattr(runtime_code._Compiler, "_capture_decorator_pattern", lambda _self, explanation: explanation)
        setattr(runtime_code._ExplanationCloneContext, "remap_decorators", runtime_code._ExplanationCloneContext.remap)
    result = (
        repeat(arguments)
        if arguments.mode == "repeat"
        else asyncio.run(
            measure(
                arguments.routes,
                arguments.heap,
                arguments.diagnostics,
                arguments.inspection,
                not arguments.no_explain_metadata,
                arguments.allow_scope_builders,
                arguments.retain_builder,
                arguments.capture_selection_views,
            )
        )
    )
    result["eager_decorator_facts"] = arguments.eager_decorator_facts
    encoded = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if arguments.output:
        arguments.output.parent.mkdir(parents=True, exist_ok=True)
        arguments.output.write_text(encoded)
    else:
        print(encoded, end="")


if __name__ == "__main__":
    main()
