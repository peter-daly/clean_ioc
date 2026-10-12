"""Successful retention preserves opaque owners and all earlier graph consumers."""

import gc
import weakref
from types import SimpleNamespace

import pytest

from clean_ioc import ContainerBuilder, Tag, components, container
from clean_ioc.components import _ComponentGraph, _undecorated_component_view
from tests.test_shared_component_definitions import Hostile, draft


def retention_plan(graph, selected):
    return SimpleNamespace(
        graph=graph,
        roots={object: (selected,)},
        provider_roots={},
        managed_provider_roots={},
        warmup_steps=(),
        architecture_roots=(),
        _blueprint=None,
    )


def test_discarded_opaque_finalizer_observes_completed_freeze_and_tag_normalization():
    graph = _ComponentGraph()
    tag = Tag("same")
    first_tags, second_tags = (tag,), (tag,)
    assert first_tags is not second_tags
    first = graph.add(draft(1, tags=first_tags, dependency_ids=(2,)))
    second = graph.add(draft(2, tags=second_tags, parent_id=1))
    observations = []

    class Opaque:
        def __del__(self):
            parent = first.dependencies[0].parent
            observations.append(
                (
                    graph._records is not None,
                    second.tags is first_tags,
                    None if parent is None else parent.occurrence_id,
                )
            )

    value = Opaque()
    reference = weakref.ref(value)
    graph.add(draft(3, implementation=value))
    del value
    container._retain_runtime_graph(retention_plan(graph, first))
    assert reference() is None
    assert observations == [(True, True, 1)]
    assert graph._records is not None
    assert tuple(graph._records) == (1, 2)
    assert second.tags is first_tags


def test_retained_opaque_facts_survive_freeze_then_detached_snapshot_owns_them(monkeypatch):
    graph = _ComponentGraph()
    value = Hostile()
    reference = weakref.ref(value)
    first = graph.add(draft(1, implementation=value, dependency_ids=(2,)))
    graph.add(draft(2, implementation=value, parent_id=1, owner_id=1))
    snapshot = _undecorated_component_view(first)
    del value
    original = components._ComponentDraft.freeze
    observations = []

    def freeze(self, *args, **kwargs):
        result = original(self, *args, **kwargs)
        observations.append(reference() is result.implementation)
        return result

    monkeypatch.setattr(components._ComponentDraft, "freeze", freeze)
    plan = retention_plan(graph, first)
    container._retain_runtime_graph(plan)
    assert observations == [True, True]
    assert first.implementation is snapshot.implementation is reference()
    assert first.dependencies[0].owner_occurrence_id == first.occurrence_id
    del plan, first, graph
    gc.collect()
    assert reference() is snapshot.dependencies[0].implementation
    del snapshot
    gc.collect()
    assert reference() is None


class Leaf:
    pass


class Choice:
    pass


class Accepted(Choice):
    def __init__(self, leaf: Leaf):
        self.leaf = leaf


class Rejected(Choice):
    def __init__(self, leaf: Leaf):
        self.leaf = leaf


class Consumer:
    def __init__(self, choices: list[Choice]):
        self.choices = choices


@pytest.mark.parametrize("mode", ["run", "analysis"])
@pytest.mark.parametrize("fail", [False, True])
def test_late_graph_rule_reads_rejected_live_captures_before_retention_and_keeps_original_failure(mode, fail):
    builder = ContainerBuilder().set_provider_roots(())
    calls = []
    saved = []
    fail_rule = fail

    def choose(component):
        calls.append(component.implementation.__name__)
        saved.append(component)
        return component.implementation is Accepted

    def rule(context):
        calls.append("late-rule")
        assert {component.implementation for component in saved} == {Accepted, Rejected}
        for component in saved:
            assert component.dependencies[0].implementation is Leaf
            assert component.dependencies[0].parent.occurrence_id == component.occurrence_id
        assert context.graph.manifest(all_roots=True).fingerprint
        assert context.graph.selection_census(all_roots=True)
        if fail_rule:
            return [next(context.graph.walk()).issue("late-owner-witness", "Original late failure")]
        return ()

    builder.register(Leaf)
    builder.register(Choice, Accepted, root_policy="dependency_only", when=choose)
    builder.register(Choice, Rejected, root_policy="dependency_only", when=choose)
    builder.register(Consumer)
    builder.add_validation_rule(rule)
    if fail:
        caught_analysis = builder.verify()
        assert not caught_analysis.is_valid
        assert calls.count("late-rule") == 1
        assert caught_analysis is not None
        assert caught_analysis.errors[0].code == "late-owner-witness"
        assert caught_analysis.errors[0].path
        fact = caught_analysis._evidence[0]
        assert fact is not None and fact.source_location is not None and fact.source_location.path is not None
        assert fact.source_location.path.endswith("test_intermediate_occurrence_lifetimes.py")
        assert builder._built
        saved.clear()
        fail_rule = False
        builder = ContainerBuilder().set_provider_roots(())
        builder.register(Leaf)
        builder.register(Choice, Accepted, root_policy="dependency_only", when=choose)
        builder.register(Choice, Rejected, root_policy="dependency_only", when=choose)
        builder.register(Consumer)
        builder.add_validation_rule(rule)
    with builder.verify() as result, result.create_runtime() as runtime:
        finished_calls = tuple(calls)
        assert len(runtime.resolve(Consumer).choices) == 1
        assert type(runtime.resolve(Consumer).choices[0]) is Accepted
        assert tuple(calls) == finished_calls
        assert calls.count("late-rule") == (2 if fail else 1)
