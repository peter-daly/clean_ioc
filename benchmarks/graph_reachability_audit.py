"""Offline task-03 reachability census; never called by compilation or resolution.

Run in a fresh process: python -m benchmarks.graph_reachability_audit --routes 8
This deliberately conservative audit is evidence, not a pruning permission.
"""

import argparse
import dataclasses
import gc
import hashlib
import json
import time
import tracemalloc
from collections import Counter
from pathlib import Path
from types import MappingProxyType
from typing import Any
from unittest.mock import patch

from benchmarks.graph_memory_evidence import source_provenance
from clean_ioc.components import Component

LINKS = ("parent_id", "owner_id", "decorated_id", "dependency_ids", "decorator_ids", "pre_configuration_ids")


def audit(plan, *, external_components=()):
    """Classify graph-qualified identities, resolving negative view IDs to sources.

    Traverse only captured library dataclasses/containers, never arbitrary user
    objects or callable attributes. Origins alone are bookkeeping, not liveness.
    Include ancestors because supported filters may traverse back to siblings.
    """
    started = time.perf_counter()
    graphs = {id(plan.graph): plan.graph}
    missing = set()
    expired = set()

    def closure(seeds, *, allow_expired=False):
        physical, logical = set(), set()
        pending = list(seeds)
        while pending:
            graph, occurrence = pending.pop()
            key = (id(graph), occurrence)
            if key in logical:
                continue
            logical.add(key)
            graphs[id(graph)] = graph
            view = graph.view_source(occurrence)
            if view is not None:
                context, source = view
                pending.extend(((graph, source), (graph, context.parent)))
            else:
                physical.add(key)
            try:
                record = graph.record(occurrence)
            except RuntimeError as error:
                if "explain-metadata-disabled" not in str(error):
                    raise
                if allow_expired:
                    expired.add(key)
                else:
                    missing.add(key)
                physical.discard(key)
                continue
            except KeyError:
                missing.add(key)
                continue
            for name in LINKS:
                value = getattr(record, name)
                values = value if isinstance(value, tuple) else (() if value is None else (value,))
                pending.extend((graph, target) for target in values)
        return physical, logical

    def components(values):
        pending, seen, seeds = list(values), set(), []
        while pending:
            value = pending.pop()
            if id(value) in seen:
                continue
            seen.add(id(value))
            if type(value) is Component:
                seeds.append((value._graph, value.occurrence_id))
            elif type(value) in (tuple, list):
                pending.extend(value)
            elif type(value) in (dict, MappingProxyType):
                pending.extend(value.values())
            elif type(value).__module__.startswith("clean_ioc.") and dataclasses.is_dataclass(type(value)):
                pending.extend(getattr(value, field.name) for field in dataclasses.fields(value))
        return seeds

    roots: dict[str, Any] = {
        "public_roots": plan.roots,
        "provider_roots": plan.provider_roots,
        "managed_provider_roots": plan.managed_provider_roots,
        "warmup_roots": plan.warmup_steps,
        "architecture_roots": plan.architecture_roots,
        "public_graph_roots": plan.compiled_graph.roots if plan.compiled_graph else (),
    }
    groups = {}
    for name, values in roots.items():
        seeds = []
        if name in ("architecture_roots", "public_graph_roots"):
            plans = [item[2] for item in values] if name == "architecture_roots" else values
        else:
            plans = [root for group in values.values() for root in group]
        for root in plans:
            seeds.append((root.component._graph, root.component.occurrence_id))
        groups[name] = closure(seeds)
    all_roots = [
        root
        for mapping in (plan.roots, plan.provider_roots, plan.managed_provider_roots, plan.warmup_steps)
        for group in mapping.values()
        for root in group
    ]
    all_roots.extend(root for _, _, root in plan.architecture_roots)
    groups["execution_components_including_map_targets"] = closure(components([root.step for root in all_roots]))
    groups["eligible_root_candidates"] = closure(
        components(
            [
                candidate
                for mapping in (plan.root_candidates, *plan.area_root_candidates.values())
                for group in mapping.values()
                for candidate in group
                if candidate.eligible
            ]
        )
    )
    groups["rejected_root_candidates"] = closure(
        components(
            [
                candidate
                for mapping in (plan.root_candidates, *plan.area_root_candidates.values())
                for group in mapping.values()
                for candidate in group
                if not candidate.eligible
            ]
        )
    )
    evidence_seeds = []
    for name in ("occurrence_explanations", "decorator_explanations", "parameter_explanations", "generic_explanations"):
        evidence_seeds.extend((plan.graph, occurrence) for occurrence in getattr(plan, name))
    # Compact wrappers are authoritative; source patterns retain original IDs
    # as captured provenance, and must not be interpreted as remapped live links.
    groups["evidence_index_owners"] = closure(evidence_seeds)
    groups["contextual_view_sources_and_parents"] = closure(
        [seed for context in plan.graph._views for seed in ((plan.graph, context.root), (plan.graph, context.parent))],
        allow_expired=not plan.explain_metadata,
    )
    groups["externally_retained_components"] = closure(
        components(external_components), allow_expired=not plan.explain_metadata
    )
    groups["captured_template_source_graphs"] = closure(
        components(plan._blueprint.template_selections if plan._blueprint is not None else ())
    )
    live = set().union(*(physical for physical, _ in groups.values()))
    all_records = {
        (identity, occurrence)
        for identity, graph in graphs.items()
        for occurrence in (graph._records if graph._records is not None else graph._drafts)
    }
    # Validate every stored edge independently, even for records outside roots.
    closure([(graphs[identity], occurrence) for identity, occurrence in all_records])
    main = {(id(plan.graph), occurrence) for occurrence in plan.graph._records or plan.graph._drafts}
    public = groups["public_roots"][0] | groups["public_graph_roots"][0]
    execution = groups["execution_components_including_map_targets"][0]
    runtime = set().union(*(groups[name][0] for name in roots), execution)
    candidates = groups["eligible_root_candidates"][0] | groups["rejected_root_candidates"][0]
    evidence = groups["evidence_index_owners"][0]
    categories = {
        "public_relationship_closure": main & public,
        "additional_execution_or_other_roots": (main & runtime) - public,
        "additional_candidate_evidence": (main & candidates) - runtime - public,
        "additional_explanation_evidence": (main & evidence) - runtime - public - candidates,
        "additional_view_sources": (main & live) - runtime - public - candidates - evidence,
        "outside_all_audited_roots": main - live,
    }
    return {
        "audit_seconds": time.perf_counter() - started,
        "explain_metadata": plan.explain_metadata,
        "expired_external_or_inspection_ids": len(expired),
        "physical_records": len(main),
        "graph_count_including_inherited_execution_graphs": len(graphs),
        "all_graph_physical_records": len(all_records),
        "overlapping_reachability": {
            name: {"physical_records": len(physical & main), "logical_ids": len(logical)}
            for name, (physical, logical) in groups.items()
        },
        "disjoint_categories": {name: len(values) for name, values in categories.items()},
        "externally_reachable_outside_runtime_roots": len(groups["externally_retained_components"][0] & main - runtime),
        "outside_runtime_roots_by_kind": dict(Counter(plan.graph.record(key[1]).kind.value for key in main - runtime)),
        "outside_runtime_root_sample_ids": sorted(key[1] for key in main - runtime)[:32],
        "outside_roots_by_kind": dict(
            Counter(plan.graph.record(key[1]).kind.value for key in categories["outside_all_audited_roots"])
        ),
        "missing_graph_qualified_links": sorted(missing),
        "outside_roots_occurrence_ids": sorted(key[1] for key in categories["outside_all_audited_roots"]),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--routes", type=int, default=8)
    parser.add_argument("--diagnostics", action="store_true")
    parser.add_argument("--no-explain-metadata", action="store_true")
    parser.add_argument("--allow-scope-builders", action="store_true")
    parser.add_argument("--trace-audit", action="store_true")
    parser.add_argument("--capture-selection-views", action="store_true")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    from benchmarks.graph_memory_fixture import build

    captured = []
    if args.capture_selection_views:
        from clean_ioc import component_filters as cf

        original = cf.with_name

        def recording_with_name(name: str | None):
            predicate = original(name)

            def capture(component):
                captured.append(component)
                return predicate(component)

            return capture

        with patch.object(cf, "with_name", recording_with_name):
            fixture = build(
                args.routes,
                diagnostics=args.diagnostics,
                explain_metadata=not args.no_explain_metadata,
                allow_scope_builders=args.allow_scope_builders,
            )
    else:
        fixture = build(
            args.routes,
            diagnostics=args.diagnostics,
            explain_metadata=not args.no_explain_metadata,
            allow_scope_builders=args.allow_scope_builders,
        )
    if args.trace_audit:
        gc.collect()
        tracemalloc.start()
    observed = audit(fixture.runtime._plan, external_components=captured)
    observed["captured_selection_view_count"] = len(captured)
    if args.trace_audit:
        gc.collect()
        retained, peak = tracemalloc.get_traced_memory()
        observed["audit_traced_retained_bytes_including_result"] = retained
        observed["audit_traced_peak_bytes"] = peak
        tracemalloc.stop()
    result = {
        "source": source_provenance(),
        "routes": args.routes,
        "diagnostics": args.diagnostics,
        "audit_source_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "audit": observed,
    }
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result["audit"], indent=2))


if __name__ == "__main__":
    main()
