import json
import sys

import pytest

from benchmarks import graph_memory_fixture as fixture
from benchmarks.graph_memory_evidence import census
from clean_ioc import ComponentActivation, ComponentKind, ProviderScopeClosedError
from clean_ioc import component_filters as cf
from tests.verification_helpers import present


@pytest.mark.parametrize("routes,diagnostics", [(1, False), (3, False), (3, True)])
async def test_template_directions_decorators_providers_maps_and_lifetimes(routes, diagnostics):
    case = fixture.build(routes)
    assert not fixture.ACTIVATIONS
    held = None
    try:
        held = await fixture.resolve_workload(case)
        assert held.lazy_counts == {
            "route_dependency": routes,
            "route_source": routes,
            "endpoint": routes,
            "endpoint_decorator": routes,
        }
        verified = fixture.validate(case, held)
        assert verified["workers"] == routes * (routes + 7) + 4
        assert verified["managed_scopes"] == 3 * routes + 2
        assert verified["source_map_calls"] == routes**2
        records = case.runtime._plan.graph._records
        assert records is not None
        assert all(record.activation is not ComponentActivation.instance for record in records.values())
        kinds = {record.kind for record in records.values()}
        assert {ComponentKind.decorator, ComponentKind.provider, ComponentKind.managed_provider} <= kinds
        assert ComponentKind.provider_map in kinds
        counts = census(case.runtime)
        assert counts["unique_execution_steps"] < counts["physical_records"]
        assert counts["executable_helpers"]["_CompiledDecorator"] > 0
        assert counts["execution_step_kinds"]["_ProviderMapStep"] > 0
        assert counts["execution_step_kinds"]["_ManagedProviderStep"] > 0
        await held.scope.__aexit__(None, None, None)
        with pytest.raises(ProviderScopeClosedError):
            held.endpoints[0].inner.worker()
    finally:
        if held is not None:
            await held.scope.__aexit__(None, None, None)
        await case.runtime.__aexit__(None, None, None)


def test_route_fanout_scales_graph_and_template_expansion():
    counts = []
    for routes in (2, 4):
        case = fixture.build(routes)
        with case.runtime:
            assert case.callbacks_after_build == {
                "source_to_generated_dependency": routes,
                "generated_worker_to_source": routes,
                "policy_to_worker_decorator": 2,
                "generated_worker_to_endpoint_decorator": routes,
            }
            counts.append(census(case.runtime))
    assert counts[1]["physical_records"] > 2 * counts[0]["physical_records"]
    assert counts[1]["record_kinds"]["provider_map"] > counts[0]["record_kinds"]["provider_map"]


async def test_source_map_acquisition_does_not_activate_other_routes():
    case = fixture.build(3)
    with case.runtime, case.runtime.new_scope() as scope:
        endpoint = scope.resolve(fixture.Endpoint, cf.with_name("route-000"))
        assert isinstance(endpoint, fixture.EndpointDecorator)
        assert fixture.ACTIVATIONS["route_source"] == 1
        assert fixture.ACTIVATIONS["worker"] == 0
        assert set(endpoint.inner.sources) == set(case.source_ids)
        assert fixture.ACTIVATIONS["route_source"] == 1
        other = await endpoint.inner.sources["route-002"]()
        assert fixture.ACTIVATIONS["route_source"] == 2
        assert other.key == "route-002"
        assert other.dependency.owner_id == case.source_ids["route-002"]


@pytest.mark.parametrize("routes", [0, -1, 129])
def test_invalid_scale_fails_before_build(routes):
    with pytest.raises(ValueError, match="routes"):
        fixture.build(routes)


def test_measurement_cli_forwards_heap_options_without_running_measurements(monkeypatch, capsys):
    from benchmarks import graph_memory_evidence

    calls = []

    async def measure(*arguments):
        calls.append(arguments)
        return {"instrumentation": "tracemalloc", "stubbed": True}

    monkeypatch.setattr(graph_memory_evidence, "measure", measure)
    monkeypatch.setattr(sys, "argv", ["graph_memory_evidence", "measure", "--routes", "2", "--heap"])
    graph_memory_evidence.main()
    result = json.loads(capsys.readouterr().out)
    assert result["stubbed"]
    assert result["instrumentation"] == "tracemalloc"
    assert calls[0][:2] == (2, True)
    assert not result["eager_decorator_facts"]


def test_compact_richer_fixture_explanations_preserve_all_captured_fields():
    from dataclasses import replace

    from clean_ioc.tooling import _RemappedDecoratorExplanation

    case = fixture.build(1, operation="verify")
    checked = 0
    with case.runtime:
        callbacks = dict(fixture.TEMPLATE_CALLS)
        assert case.analysis is not None
        graph = case.analysis.graph
        for visit in present(graph).walk():
            component = visit.component
            stored = present(graph)._component_evidence(present(graph)._decorator_explanations, component)
            if stored is None:
                continue
            source = stored.source if isinstance(stored, _RemappedDecoratorExplanation) else stored
            source_selected, source_rejected = source.selected, source.rejected

            def remap(decisions):
                return tuple(
                    decision
                    if decision.template is None
                    else replace(
                        decision, template=replace(decision.template, target_occurrence_id=component.occurrence_id)
                    )
                    for decision in decisions
                )

            expected = (remap(source_selected), remap(source_rejected))
            first = present(graph).explain_decorators(component)
            second = present(graph).explain_decorators(component)
            assert (first.selected, first.rejected) == expected
            assert (second.selected, second.rejected) == expected
            assert first.subject == source.subject
            assert all(
                decision.template is None or decision.template.target_occurrence_id == component.occurrence_id
                for decision in (*first.selected, *first.rejected)
            )
            assert source.selected is source_selected
            assert source.rejected is source_rejected
            checked += 1
        assert checked > 100
        assert fixture.TEMPLATE_CALLS == callbacks


def test_compact_fixture_matches_eager_manifests_and_complete_decorator_facts(monkeypatch):
    from dataclasses import asdict
    from uuid import UUID

    from clean_ioc.container import _ExplanationCloneContext

    def snapshot():
        case = fixture.build(1, operation="verify")
        with case.runtime:
            assert case.analysis is not None
            graph = case.analysis.graph
            identities = {}

            def normalize(value):
                if isinstance(value, str):
                    try:
                        UUID(value)
                    except ValueError:
                        return value
                    return identities.setdefault(value, f"identity:{len(identities)}")
                if isinstance(value, dict):
                    return {key: normalize(item) for key, item in value.items()}
                if isinstance(value, (tuple, list)):
                    return tuple(map(normalize, value))
                return value

            facts = []
            for visit in present(graph).walk():
                component = visit.component
                if present(graph)._component_evidence(present(graph)._decorator_explanations, component) is None:
                    continue
                explanation = present(graph).explain_decorators(component)
                facts.append(
                    (
                        component.occurrence_id,
                        explanation.subject,
                        normalize(tuple(asdict(decision) for decision in explanation.selected)),
                        normalize(tuple(asdict(decision) for decision in explanation.rejected)),
                    )
                )
            return present(graph).manifest(all_roots=True).to_json(), facts

    compact = snapshot()
    monkeypatch.setattr(_ExplanationCloneContext, "remap_decorators", _ExplanationCloneContext.remap)
    assert snapshot() == compact
