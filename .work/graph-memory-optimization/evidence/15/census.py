"""Intrusive sidecar/relationship census, excluded from latency and memory runs."""

# ruff: noqa: E402, S101
import gc
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))
from clean_ioc import ContainerBuilder, container
from clean_ioc._compact_index import _CompactIndex

observations = []
counts = Counter()
after_build = []
original_init = _CompactIndex.__init__


def initialize(self):
    original_init(self)
    counts["constructed"] += 1
    counts["live"] += 1
    counts["maximum_live"] = max(counts["maximum_live"], counts["live"])


def finalize(self):
    counts["live"] -= 1


_CompactIndex.__init__ = initialize
_CompactIndex.__del__ = finalize  # ty: ignore[unresolved-attribute]
original_build = ContainerBuilder.build


def build(self, **kwargs):
    result = original_build(self, **kwargs)
    gc.collect()
    after_build.append(dict(counts))
    return result


ContainerBuilder.build = build


def relationships(graph):
    records = list((graph._records if graph._records is not None else graph._drafts).values())
    sequences = {}
    by_field = {}
    for name in ("dependency_ids", "decorator_ids", "pre_configuration_ids"):
        items = [getattr(record, name) for record in records]
        unique = {id(item): item for item in items}
        sequences.update(unique)
        by_field[name] = {
            "references": len(items),
            "unique_objects": len(unique),
            "lengths": dict(Counter(map(len, items))),
        }
    nonempty = [item for item in sequences.values() if item]
    content = set(nonempty)
    contiguous = [item for item in nonempty if all(b == a + 1 for a, b in zip(item, item[1:]))]  # noqa: RUF007
    integer_refs = {id(value): value for item in nonempty for value in item}
    return {
        "records": len(records),
        "fields": by_field,
        "nonempty_unique_tuples": len(nonempty),
        "unique_contents": len(content),
        "tuple_shallow_bytes": sum(map(sys.getsizeof, sequences.values())),
        "duplicate_tuple_bytes_upper_bound": sum(map(sys.getsizeof, nonempty)) - sum(map(sys.getsizeof, content)),
        "intern_table_shallow_bytes": sys.getsizeof(dict.fromkeys(content)),
        "borrowed_unique_integer_objects": len(integer_refs),
        "borrowed_integer_bytes_NOT_ADDITIVE": sum(map(sys.getsizeof, integer_refs.values())),
        "contiguous_unique_tuples": len(contiguous),
        "contiguous_lengths": dict(Counter(map(len, contiguous))),
        "range_shallow_bytes": sys.getsizeof(range(1)),
        "range_best_saving_bytes_before_fallback_or_view_cost": sum(
            max(0, sys.getsizeof(item) - sys.getsizeof(range(1))) for item in contiguous
        ),
        "packed_64bit_references_bytes": sum(len(item) * 8 for item in nonempty),
        "packed_64bit_offset_length_pairs_bytes": len(nonempty) * 16,
        "row_64bit_six_scalar_relationship_fields_bytes": len(records) * 48,
    }


def index(mapping):
    compact = type(mapping) is _CompactIndex
    rows = list(mapping.raw_items()) if compact else list(mapping.items())
    return {
        "capacity": mapping.capacity()
        if compact
        else {"entries": len(mapping), "shallow_bytes": sys.getsizeof(mapping)},
        "unique_values": len({id(value) for _, value in rows}),
        "value_bytes_NOT_ADDITIVE": sum(map(sys.getsizeof, {id(value): value for _, value in rows}.values())),
        "dense_capacity_slots": (mapping._values.__sizeof__() - [].__sizeof__()) // 8
        if compact and mapping._values is not None
        else 0,
        "order_capacity_slots": (mapping._keys.__sizeof__() - [].__sizeof__()) // 8
        if compact and mapping._keys is not None
        else 0,
    }


original = container._Compiler.compile


def compile(self, *args, **kwargs):
    result = original(self, *args, **kwargs)
    observations.append(
        {
            "phase": "compiled",
            "origins": index(self.origins),
            "decorators": index(self.decorator_explanations),
            "relationships": relationships(self.graph),
        }
    )
    return result


container._Compiler.compile = compile
original_retain = container._retain_runtime_graph


def retain(plan, **kwargs):
    original_retain(plan, **kwargs)
    observations.append({"phase": "retained", "relationships": relationships(plan.graph)})


container._retain_runtime_graph = retain  # ty: ignore[invalid-assignment]
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "12"))
from measure import sample  # ty: ignore[unresolved-import]

result = sample(sys.argv[1], False)
gc.collect()
print(
    json.dumps(
        {
            "index_constructor_census": dict(counts),
            "after_build": after_build,
            "variant": sys.argv[1],
            "observations": observations,
            "graph": result["graph"],
        },
        indent=2,
    )
)
