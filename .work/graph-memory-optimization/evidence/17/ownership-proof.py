# ruff: noqa: E402, S101
"""Bounded internal ownership witness, not a timing or public-composition benchmark."""

import gc
import json
import sys
import weakref
from types import SimpleNamespace

from source_loader import LOADED, install

policy = sys.argv[1]
install(policy)
from clean_ioc import Tag, components, container
from tests.test_shared_component_definitions import draft

events: list[dict[str, object]] = []
graph = components._ComponentGraph()
tag = Tag("same")
first_tags, second_tags = (tag,), (tag,)
assert first_tags is not second_tags
selected = graph.add(draft(1, tags=first_tags, dependency_ids=(2,)))
second = graph.add(draft(2, tags=second_tags, parent_id=1))


class Opaque:
    def __del__(self):
        events.append(
            {
                "event": "discarded opaque released",
                "graph_frozen": graph._records is not None,
                "selected_tags_normalized": second.tags is first_tags,
                "selected_dependency": selected.dependencies[0].occurrence_id,
            }
        )


value = Opaque()
reference = weakref.ref(value)
graph.add(draft(3, implementation=value))
del value
released_drafts = []
setattr(components._ComponentDraft, "__del__", lambda self: released_drafts.append(self.occurrence_id))
original = components._ComponentGraph.freeze


def freeze(self):
    events.append({"event": "freeze begin", "opaque_alive": reference() is not None})
    original(self)
    events.append(
        {
            "event": "freeze end",
            "opaque_alive": reference() is not None,
            "released_drafts": list(released_drafts),
        }
    )


components._ComponentGraph.freeze = freeze
plan = SimpleNamespace(
    graph=graph,
    roots={object: (selected,)},
    provider_roots={},
    managed_provider_roots={},
    warmup_steps=(),
    architecture_roots=(),
    _blueprint=None,
)
container._retain_runtime_graph(plan)  # ty: ignore[invalid-argument-type]
gc.collect()
assert reference() is None
assert graph._records is not None
assert tuple(graph._records) == (1, 2)
assert second.tags is first_tags
parent = selected.dependencies[0].parent
assert parent is not None and parent.occurrence_id == selected.occurrence_id
events.append({"event": "returned", "released_drafts": list(released_drafts)})
print(json.dumps({"policy": policy, "source": LOADED, "events": events}, indent=2))
