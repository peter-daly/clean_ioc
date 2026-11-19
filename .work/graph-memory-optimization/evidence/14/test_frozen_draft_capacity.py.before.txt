"""Freezing retains occurrence records, but releases the empty draft hash table."""

import sys
from dataclasses import fields
from types import MappingProxyType

import pytest

from clean_ioc import ComponentActivation, ComponentKind
from clean_ioc.components import _ComponentDraft, _ComponentGraph


def draft(occurrence):
    return _ComponentDraft(
        id="shared-registration",
        occurrence_id=occurrence,
        service_type=object,
        implementation=object,
        implementation_type=object,
        lifespan="transient",
        name=None,
        tags=(),
        build_args=MappingProxyType({}),
        kind=ComponentKind.registration,
        activation=ComponentActivation.constructor,
        parent_id=None if occurrence == 1 else occurrence - 1,
        dependency_ids=() if occurrence == 1 else (occurrence - 1,),
    )


@pytest.mark.parametrize("count", [0, 1, 1024, 8192])
def test_freeze_releases_draft_capacity_and_preserves_every_record(count):
    graph = _ComponentGraph()
    components = []
    snapshots = []
    for occurrence in range(1, count + 1):
        value = draft(occurrence)
        snapshots.append({item.name: getattr(value, item.name) for item in fields(value)})
        components.append(graph.add(value))
    allocated = sys.getsizeof(graph._drafts)
    graph.freeze()
    assert not graph._drafts
    assert sys.getsizeof(graph._drafts) == sys.getsizeof({})
    if count > 1:
        assert allocated > sys.getsizeof(graph._drafts)
    assert graph._records is not None
    assert len(graph._records) == count
    for component, expected in zip(components, snapshots, strict=True):
        record = graph.record(component.occurrence_id)
        assert {name: getattr(record, name) for name in expected} == expected
        assert component._record is record
        if component.parent is not None:
            assert component.parent.occurrence_id == component.occurrence_id - 1
            assert component.dependencies[0].occurrence_id == component.parent.occurrence_id
