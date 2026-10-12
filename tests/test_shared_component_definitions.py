"""Definition sharing preserves captured facts and contextual occurrence state."""

from dataclasses import replace
from types import MappingProxyType
from typing import Generic, TypeVar

import pytest

from clean_ioc import Component, ComponentActivation, ComponentKind
from clean_ioc.components import (
    RuntimeOwnerKind,
    _ComponentDraft,
    _ComponentGraph,
    _ComponentRecord,
    _ComponentViewRecord,
    _undecorated_component_view,
)


def draft(occurrence, **changes):
    value = _ComponentDraft(
        id="registration",
        occurrence_id=occurrence,
        service_type=object,
        implementation=object,
        implementation_type=object,
        lifespan="transient",
        name=None,
        tags=(),
        build_args=EMPTY_ARGUMENTS,
        kind=ComponentKind.registration,
        activation=ComponentActivation.constructor,
    )
    return replace(value, **changes)


def record(graph: _ComponentGraph, occurrence: int) -> _ComponentRecord:
    value = graph.record(occurrence)
    assert isinstance(value, _ComponentRecord)
    return value


def frozen(component: Component) -> _ComponentRecord:
    return record(component._graph, component.occurrence_id)


EMPTY_ARGUMENTS = MappingProxyType({})


class Hostile:
    def __eq__(self, other):
        raise AssertionError("Application equality was invoked")

    def __hash__(self):
        raise AssertionError("Application hashing was invoked")

    def __repr__(self):
        raise AssertionError("Application repr was invoked")


def test_shared_definitions_preserve_registration_identity_and_context_without_application_calls():
    graph = _ComponentGraph()
    value = Hostile()
    arguments = MappingProxyType({"value": value})
    first = graph.add(draft(1, implementation=value, build_args=arguments))
    second = graph.add(
        draft(
            2,
            id="another-registration",
            implementation=value,
            build_args=arguments,
            requires_async=True,
            manages_cleanup=True,
            cache_owner=RuntimeOwnerKind.scope,
            cleanup_owner=RuntimeOwnerKind.scope,
            owner_id=1,
            ownership_reason="contextual ownership",
            parent_id=1,
            argument="injected",
            position=7,
            provider_mode="async",
            dependency_ids=(1,),
            decorator_ids=(1,),
            pre_configuration_ids=(1,),
            decorated_id=1,
        )
    )
    graph.freeze()
    assert frozen(first)._definition is frozen(second)._definition
    assert first.id == "registration"
    assert second.id == "another-registration"
    assert first.implementation is second.implementation is value
    assert second.build_args is arguments
    assert second.requires_async and second.manages_cleanup
    assert second.cache_owner is second.cleanup_owner is RuntimeOwnerKind.scope
    assert second.owner_occurrence_id == 1
    assert second.ownership_reason == "contextual ownership"
    parent = second.parent
    assert parent is not None and parent.occurrence_id == 1
    assert second.argument == "injected"
    assert second.position == 7
    assert second.provider_mode == "async"
    for relation in (second.dependencies, second.decorators, second.pre_configurations):
        assert tuple(item.occurrence_id for item in relation) == (1,)
    decorated = second.decorated
    assert decorated is not None and decorated.occurrence_id == 1
    assert graph._drafts == {}


@pytest.mark.parametrize(
    "changes",
    [
        {"service_type": str},
        {"implementation": Hostile()},
        {"implementation_type": str},
        {"lifespan": "singleton"},
        {"name": "different"},
        {"tags": (Hostile(),)},
        {"build_args": MappingProxyType({})},
        {"kind": ComponentKind.value},
        {"activation": ComponentActivation.instance},
        {"boundary": "overlay"},
        {"declared_service_type": str},
    ],
    ids=[
        "service",
        "implementation",
        "implementation-type",
        "lifespan",
        "name",
        "tags",
        "arguments",
        "kind",
        "activation",
        "boundary",
        "declared-service",
    ],
)
def test_each_definition_referent_is_part_of_equivalence(changes):
    graph = _ComponentGraph()
    first = graph.add(draft(1))
    second = graph.add(draft(2, **changes))
    graph.freeze()
    assert frozen(first)._definition is not frozen(second)._definition


def test_tag_sequences_share_only_identical_ordered_referents_and_indexes_are_build_local():
    first_tag, second_tag = Hostile(), Hostile()
    graphs = [_ComponentGraph(), _ComponentGraph()]
    for graph in graphs:
        graph.add(draft(1, tags=(first_tag, second_tag)))
        graph.add(draft(2, tags=tuple([first_tag, second_tag])))
        graph.add(draft(3, tags=(second_tag, first_tag)))
        graph.freeze()
        assert record(graph, 1)._definition is record(graph, 2)._definition
        assert record(graph, 1)._definition is not record(graph, 3)._definition
    assert record(graphs[0], 1)._definition is not record(graphs[1], 1)._definition


T = TypeVar("T")


class Service(Generic[T]):
    pass


def test_specializations_and_lazy_mapping_caches_remain_occurrence_local():
    graph = _ComponentGraph()
    specialized = Service[int]
    first = graph.add(draft(1, service_type=specialized))
    second = graph.add(draft(2, service_type=specialized))
    other = graph.add(draft(3, service_type=Service[str]))
    graph.freeze()
    assert frozen(first)._definition is frozen(second)._definition
    assert frozen(first)._definition is not frozen(other)._definition
    assert frozen(first)._generic_mapping is frozen(second)._generic_mapping is None
    mapping = first.generic_mapping
    assert mapping[T] is int
    assert first.generic_mapping is mapping
    assert frozen(second)._generic_mapping is None
    assert second.generic_mapping[T] is int
    assert frozen(second)._generic_mapping is second.generic_mapping
    assert other.generic_mapping[T] is str


def test_escaped_snapshots_and_provider_view_replacements_keep_contextual_fields():
    graph = _ComponentGraph()
    parent = graph.add(draft(1, kind=ComponentKind.managed_provider))
    source = graph.add(draft(2, parent_id=1, dependency_ids=(3,), decorator_ids=(3,)))
    graph.add(draft(3, parent_id=2))
    escaped = _undecorated_component_view(source)
    view = graph.view(source, parent)
    graph.freeze()
    assert escaped.decorators == ()
    assert tuple(item.occurrence_id for item in escaped.dependencies) == (3,)
    escaped_parent = escaped.parent
    assert escaped_parent is not None and escaped_parent.occurrence_id == 1
    assert tuple(item.occurrence_id for item in source.decorators) == (3,)
    projection = view._record
    assert isinstance(projection, _ComponentViewRecord)
    snapshot = projection.freeze()
    assert snapshot._definition is frozen(source)._definition
    assert snapshot.occurrence_id == view.occurrence_id
    assert snapshot.parent_id == parent.occurrence_id
    assert snapshot.dependency_ids == tuple(item.occurrence_id for item in view.dependencies)
    assert snapshot.decorator_ids == tuple(item.occurrence_id for item in view.decorators)
    assert snapshot._generic_mapping is None
