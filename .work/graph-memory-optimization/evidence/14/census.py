# ruff: noqa: E402, S101
"""Intrusive constructor/live/pool census; excluded from measured processes."""

import gc
import json
import shutil
import sys
import tempfile
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))
policy, variant = sys.argv[1:]
if policy == "before":
    baseline = Path(tempfile.mkdtemp(prefix="draft-definition-before-"))
    shutil.copytree(ROOT / "clean_ioc", baseline / "clean_ioc")
    for name in ("components.py", "container.py"):
        shutil.copyfile(Path(__file__).parent / (name + ".before.txt"), baseline / "clean_ioc" / name)
    sys.path.insert(0, str(baseline))

from clean_ioc import ContainerBuilder, Tag, components, container

counts, graphs, after_build = {}, [], []


def observe(cls):
    original = cls.__init__

    def init(self, *args, **kwargs):
        original(self, *args, **kwargs)
        count = counts.setdefault(type(self).__name__, Counter())
        count["constructed"] += 1
        count["live"] += 1
        count["maximum_live"] = max(count["maximum_live"], count["live"])

    def delete(self):
        counts[type(self).__name__]["live"] -= 1

    cls.__init__ = init
    cls.__del__ = delete


for cls in (components._ComponentDraft, components._ComponentDefinition, components._ComponentRecord):
    observe(cls)

pool_counts = Counter()
if policy != "before":
    original_intern = components._DraftDefinitionPool.intern

    def intern(self, values):
        result = original_intern(self, values)
        pool_counts["calls"] += 1
        pool_counts["maximum_entries_one_pool"] = max(pool_counts["maximum_entries_one_pool"], len(self.definitions))
        return result

    components._DraftDefinitionPool.intern = intern


def inspect_graph(graph, phase):
    drafts = tuple(graph._drafts.values())
    pool = getattr(graph, "_definitions", None)
    graphs.append(
        {
            "phase": phase,
            "drafts": len(drafts),
            "draft_shallow_bytes": sum(map(sys.getsizeof, drafts)),
            "definition_shallow_bytes": sum(
                map(sys.getsizeof, {id(d._definition): d._definition for d in drafts}.values())
            )
            if policy != "before"
            else 0,
            "live_definitions": len({id(d._definition) for d in drafts}) if policy != "before" else None,
            "tag_tuples": len({id(d.tags) for d in drafts}),
            "ordered_tag_patterns": len({tuple(id(tag) for tag in d.tags) for d in drafts}),
            "nonempty_tag_drafts": sum(bool(d.tags) for d in drafts),
            "pool_entries": len(pool.definitions) if pool is not None else 0,
            "pool_key_bytes": sum(sys.getsizeof(key) for key in pool.definitions.data) if pool is not None else 0,
            "pool_key_integer_bytes": sum(sys.getsizeof(value) for key in pool.definitions.data for value in key)
            if pool is not None
            else 0,
            "pool_weakref_bytes": sum(sys.getsizeof(value) for value in pool.definitions.data.values())
            if pool is not None
            else 0,
            "pool_table_bytes": sys.getsizeof(pool.definitions.data) if pool is not None else 0,
            "pool_wrapper_bytes": sum(map(sys.getsizeof, (pool, pool.definitions, pool.definitions.__dict__)))
            if pool is not None
            else 0,
        }
    )


original_freeze = components._ComponentGraph.freeze


def freeze(self):
    inspect_graph(self, "freeze")
    original_freeze(self)


components._ComponentGraph.freeze = freeze
original_retain = container._retain_runtime_graph


def retain(plan, **kwargs):
    inspect_graph(plan.graph, "before-runtime-retention")
    return original_retain(plan, **kwargs)


container._retain_runtime_graph = retain  # ty: ignore[invalid-assignment]
original_build = ContainerBuilder.build


def build(self, **kwargs):
    result = original_build(self, **kwargs)
    gc.collect()
    after_build.append({name: dict(value) for name, value in counts.items()})
    return result


ContainerBuilder.build = build
if variant == "tagged":
    original_register = ContainerBuilder.register
    tag = Tag("screen")

    def register(self, *args, **kwargs):
        kwargs["tags"] = (*kwargs.get("tags", ()), tag)
        return original_register(self, *args, **kwargs)

    ContainerBuilder.register = register

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "12"))
from measure import sample  # ty: ignore[unresolved-import]

if variant == "diversity":
    sys.path.insert(0, str(Path(__file__).parent))
    from diversity import sample as diversity_sample

    result = diversity_sample("run", False)
else:
    result = sample("run" if variant == "tagged" else variant, False)
gc.collect()
print(
    json.dumps(
        {
            "policy": policy,
            "variant": variant,
            "counts": counts,
            "after_build": after_build,
            "graphs": graphs,
            "pool": pool_counts,
            "graph": result.get("graph"),
        },
        indent=2,
    )
)
if policy == "before":
    shutil.rmtree(baseline)
