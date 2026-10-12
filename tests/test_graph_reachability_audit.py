"""The offline audit must protect contextual and executable occurrence links."""

from dataclasses import replace

import pytest

from benchmarks.graph_memory_fixture import build
from benchmarks.graph_reachability_audit import audit
from clean_ioc import ScopeBuilder


@pytest.mark.parametrize("diagnostics", [False, True])
def test_rich_fixture_audit_classifies_every_record_without_broken_views(diagnostics):
    fixture = build(1, operation="verify" if diagnostics else "build")
    with fixture.runtime:
        result = audit(fixture.runtime._plan)
        assert not result["missing_graph_qualified_links"]
        assert sum(result["disjoint_categories"].values()) == result["physical_records"]
        assert result["overlapping_reachability"]["managed_provider_roots"]["physical_records"]
        assert result["overlapping_reachability"]["execution_components_including_map_targets"]["physical_records"]
        assert result["overlapping_reachability"]["contextual_view_sources_and_parents"]["logical_ids"]


def test_audit_distinguishes_isolated_record_and_detects_unreachable_broken_link():
    fixture = build(1)
    with fixture.runtime:
        plan = fixture.runtime._plan
        records = plan.graph._records
        assert records is not None
        original = audit(plan)
        source = next(iter(records.values()))
        orphan_id = max(records) + 100
        records[orphan_id] = replace(
            source,
            occurrence_id=orphan_id,
            parent_id=None,
            owner_id=None,
            decorated_id=None,
            dependency_ids=(),
            decorator_ids=(),
            pre_configuration_ids=(),
        )
        result = audit(plan)
        assert result["outside_roots_occurrence_ids"] == sorted([*original["outside_roots_occurrence_ids"], orphan_id])
        assert not result["missing_graph_qualified_links"]
        missing = orphan_id + 1
        records[orphan_id] = replace(records[orphan_id], owner_id=missing)
        assert [id(plan.graph), missing] in [list(key) for key in audit(plan)["missing_graph_qualified_links"]]


def test_audit_qualifies_inherited_execution_components_and_warmup_roots():
    from clean_ioc import ContainerBuilder, WarmupPlan, WarmupTarget

    class Resource:
        pass

    class Consumer:
        def __init__(self, resource: Resource):
            self.resource = resource

    builder = ContainerBuilder()
    builder.register(Resource, lifespan="singleton")
    builder.register(Consumer)
    builder.add_warmup_plan(WarmupPlan("startup", [WarmupTarget(Resource)]))
    parent_composition = builder.retain_composition()
    with builder.build() as parent:
        with ScopeBuilder(parent, composition=parent_composition).build() as overlay:
            result = audit(overlay._plan)
            assert not result["missing_graph_qualified_links"]
            assert result["graph_count_including_inherited_execution_graphs"] >= 2
            assert result["overlapping_reachability"]["warmup_roots"]["physical_records"]
            assert overlay.resolve(Consumer).resource is parent.resolve(Resource)


def test_selection_callback_records_remain_readable_with_compact_runtime_closure(monkeypatch):
    from clean_ioc import component_filters as cf

    captured = []
    original = cf.with_name

    def recording_with_name(name):
        predicate = original(name)

        def capture(component):
            captured.append(component)
            return predicate(component)

        return capture

    monkeypatch.setattr(cf, "with_name", recording_with_name)
    fixture = build(2, operation="verify")
    with fixture.runtime:
        result = audit(fixture.runtime._plan, external_components=captured)
        assert not result["missing_graph_qualified_links"]
        assert result["overlapping_reachability"]["externally_retained_components"]["logical_ids"] > 0
        assert result["externally_reachable_outside_runtime_roots"] == 0
        # Escaped components remain live public objects, including rejected
        # contextual candidates. Inspection must still work after compilation.
        assert all(component.service_type is not None for component in captured)
        assert all(component.parent is None or component.parent.dependencies is not None for component in captured)


def test_audit_includes_unexposed_boundary_architecture_roots():
    from clean_ioc import ContainerBuilder

    class PrivateService:
        pass

    builder = ContainerBuilder()

    def register_private(boundary):
        boundary.register(PrivateService)

    builder.create_boundary("feature").apply_bundle(register_private)
    with builder.build() as runtime:
        result = audit(runtime._plan)
        assert not result["missing_graph_qualified_links"]
        assert result["overlapping_reachability"]["architecture_roots"]["physical_records"] == 0
        assert runtime.components == ()
        assert not runtime.has_component(PrivateService)
