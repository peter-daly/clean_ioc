"""Early definition sharing preserves independent draft mutation and ownership."""

import gc
import weakref
from dataclasses import fields, replace

import pytest

from clean_ioc.components import _ComponentGraph, _DraftDefinitionPool, _undecorated_component_view
from tests.test_shared_component_definitions import Hostile, draft


@pytest.mark.parametrize(
    "field_name",
    (
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
    ),
)
def test_every_definition_field_uses_isolated_copy_on_write_and_restoration(field_name):
    graph = _ComponentGraph()
    first, second = draft(1), draft(2)
    graph.add(first)
    graph.add(second)
    original = first._definition
    before = getattr(first, field_name)
    replacement = (Hostile(),) if field_name == "tags" else Hostile()
    assert second._definition is original
    setattr(first, field_name, replacement)
    assert getattr(first, field_name) is replacement
    assert getattr(second, field_name) is before
    assert second._definition is original
    setattr(first, field_name, before)
    assert first._definition is original
    assert len(graph._definitions.definitions) == 1


def test_overwritten_opaque_fact_releases_without_pool_clear_and_snapshot_is_independent():
    graph = _ComponentGraph()
    first = draft(1)
    component = graph.add(first)
    value = Hostile()
    reference = weakref.ref(value)
    first.implementation = value
    snapshot = _undecorated_component_view(component)
    definition = weakref.ref(first._definition)
    del value
    first.implementation = object
    gc.collect()
    assert reference() is snapshot.implementation
    assert definition() is not None
    del snapshot
    gc.collect()
    assert reference() is None
    assert definition() is None
    assert len(graph._definitions.definitions) == 1


def test_pool_does_not_retain_overwritten_facts_even_when_saved_by_caller():
    graph = _ComponentGraph()
    first = draft(1)
    graph.add(first)
    pool = graph._definitions
    value = Hostile()
    reference = weakref.ref(value)
    first.name = value
    del value
    first.name = None
    assert reference() is None
    del first, graph
    gc.collect()
    assert len(pool.definitions) == 0


def test_freeze_reuses_definition_discards_keys_and_preserves_snapshot_after_mutation():
    graph = _ComponentGraph()
    first = draft(1)
    component = graph.add(first)
    snapshot = first.freeze()
    first.name = "changed"
    replacement = first._definition
    graph.freeze()
    assert component._record._definition is replacement
    assert snapshot.name is None
    assert component.name == "changed"
    assert len(graph._definitions.definitions) == 0


def test_dataclass_replace_keeps_private_representation_and_definition_overrides():
    graph = _ComponentGraph()
    first = draft(1)
    graph.add(first)
    second = replace(first, occurrence_id=2, name="replacement", parent_id=1)
    assert first.name is None
    assert second.name == "replacement"
    assert second.parent_id == 1
    assert second.service_type is first.service_type
    assert second._definitions is first._definitions
    assert "_definition" in {field.name for field in fields(first)}
    assert "service_type" not in {field.name for field in fields(first)}


def test_direct_pool_construction_interns_before_graph_add():
    pool = _DraftDefinitionPool()
    first = replace(draft(1), _definitions=pool)
    second = replace(first, occurrence_id=2)
    assert first._definition is second._definition
    assert len(pool.definitions) == 1


@pytest.mark.parametrize("mode", ("run", "analysis"))
def test_public_when_observes_distinct_tag_tuple_identity_before_freeze(mode):
    from clean_ioc import ContainerBuilder, Tag

    class Service:
        pass

    tag = Tag("same")
    seen = []

    def choose(component):
        distinct = not seen or component.tags is not seen[0]
        seen.append(component.tags)
        return distinct

    builder = ContainerBuilder()
    builder.set_provider_roots(())
    builder.register(Service, tags=tuple([tag]), when=choose)
    builder.register(Service, tags=tuple([tag]), when=choose)
    with builder.build() as runtime:
        assert len(seen) == 2
        assert seen[0] is not seen[1]
        assert len(runtime.selected_registrations) == 2


def test_live_tags_and_detached_snapshot_keep_exact_tuple_until_final_freeze():
    graph = _ComponentGraph()
    tag = Hostile()
    first_tags, second_tags = tuple([tag]), tuple([tag])
    first, second = draft(1, tags=first_tags), draft(2, tags=second_tags)
    graph.add(first)
    second_component = graph.add(second)
    assert first.tags is first_tags
    assert second.tags is second_tags
    snapshot = _undecorated_component_view(second_component)
    assert snapshot.tags is second_tags
    graph.freeze()
    assert graph.record(1)._definition is graph.record(2)._definition
    assert snapshot.tags is second_tags


def test_equal_ordered_tag_setter_preserves_new_tuple_and_restores_exact_old_tuple():
    graph = _ComponentGraph()
    tag = Hostile()
    old_tags, new_tags = tuple([tag]), tuple([tag])
    first = draft(1, tags=old_tags)
    component = graph.add(first)
    snapshot = _undecorated_component_view(component)
    original = first._definition
    first.tags = new_tags
    assert first.tags is new_tags
    assert snapshot.tags is old_tags
    first.tags = old_tags
    assert first.tags is old_tags
    assert first._definition is original


def test_detached_snapshot_does_not_keep_source_pool_alive():
    graph = _ComponentGraph()
    first = draft(1, implementation=Hostile())
    component = graph.add(first)
    pool_reference = weakref.ref(graph._definitions.definitions)
    snapshot = _undecorated_component_view(component)
    implementation = first.implementation
    del graph, first, component
    gc.collect()
    assert pool_reference() is None
    assert snapshot.implementation is implementation


@pytest.mark.parametrize("mode", ("run", "analysis"))
def test_failed_build_releases_weak_pools_when_error_owners_are_released(monkeypatch, mode):
    from clean_ioc import ContainerBuilder

    references = []
    original = _ComponentGraph.__init__

    def graph_init(self):
        original(self)
        references.append(weakref.ref(self._definitions.definitions))

    monkeypatch.setattr(_ComponentGraph, "__init__", graph_init)

    class Service:
        pass

    callback_calls = []

    def fail(component):
        callback_calls.append(component.id)
        raise RuntimeError("deliberate callback failure")

    builder = ContainerBuilder()
    builder.set_provider_roots(())
    builder.register(Service, when=fail)
    caught_analysis = builder.verify()
    assert not caught_analysis.is_valid
    assert callback_calls
    assert caught_analysis is not None
    assert {issue.code for issue in caught_analysis.errors} == {"compile-error"}
    del caught_analysis, builder
    gc.collect()
    assert references
    assert all(reference() is None for reference in references)
