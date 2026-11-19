"""Audit native delegation in initial, compact and permanently promoted states."""

# ruff: noqa: S101
import gc
import importlib.util
import io
import json
from pathlib import Path
from types import MappingProxyType

path = Path(__file__).with_name("09-probe.py")
spec = importlib.util.spec_from_file_location("task09_probe", path)
if spec is None or spec.loader is None:
    raise RuntimeError("Missing Task09 probe")
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)
Index = probe.CompactIndex


def outcome(call):
    try:
        return ("value", call())
    except Exception as error:
        return (type(error).__name__, str(error))


checks = 0
for name in ("get", "setdefault", "pop"):
    assert outcome(lambda: getattr(Index(), name)(key=1))[0] == outcome(lambda: getattr({}, name)(key=1))[0]
    checks += 1
for state in ("initial", "compact", "promoted"):
    for operation in (
        "clear",
        "copy",
        "eq",
        "ne",
        "left-eq",
        "proxy-eq",
        "setdefault-present",
        "setdefault-missing",
        "pop-present",
        "pop-missing",
        "pop-default",
        "pop-too-many",
        "popitem",
        "update-dict",
        "update-pairs",
        "update-invalid",
        "update-keywords",
        "update-self",
        "union",
        "reverse-union",
        "inplace-union",
        "union-invalid",
        "views",
        "reversed",
    ):
        index = Index()
        count = 256 if state != "initial" else 3
        native = {key: object() for key in range(count)}
        for key, value in native.items():
            index[key] = value
        if state == "promoted":
            index.promote()
        assert (index._dict is None) == (state == "compact")
        proxy = MappingProxyType(index)

        def apply(mapping):
            if operation == "clear":
                return mapping.clear()
            if operation == "copy":
                return mapping.copy()
            if operation == "eq":
                return mapping == native
            if operation == "ne":
                return mapping != native
            if operation == "left-eq":
                return native == mapping
            if operation == "proxy-eq":
                return MappingProxyType(mapping) == native
            if operation == "setdefault-present":
                return mapping.setdefault(1, "unused")
            if operation == "setdefault-missing":
                return mapping.setdefault(-1, "new")
            if operation == "pop-present":
                return mapping.pop(1)
            if operation == "pop-missing":
                return mapping.pop(-1)
            if operation == "pop-default":
                return mapping.pop(-1, "default")
            if operation == "pop-too-many":
                return mapping.pop(1, 2, 3)
            if operation == "popitem":
                return mapping.popitem()
            if operation == "update-dict":
                return mapping.update({1: "replacement", -1: "new"})
            if operation == "update-pairs":
                return mapping.update([(1, "replacement"), (-1, "new")])
            if operation == "update-invalid":
                return mapping.update([(1, "replacement"), (1, 2, 3)])
            if operation == "update-keywords":
                return mapping.update(foo="new")
            if operation == "update-self":
                return mapping.update(mapping)
            if operation == "union":
                return mapping | {1: "replacement"}
            if operation == "reverse-union":
                return {1: "replacement"} | mapping
            if operation == "inplace-union":
                mapping |= [(1, "replacement")]
                return mapping.copy()
            if operation == "union-invalid":
                return mapping | []
            if operation == "views":
                return (list(mapping.keys()), list(mapping.values()), list(mapping.items()))
            return list(reversed(mapping))

        left = outcome(lambda: apply(index))
        right = outcome(lambda: apply(native))
        # Operator error messages name the private carrier; exact native exception category is required.
        if operation == "union-invalid":
            assert left[0] == right[0]
        else:
            assert left == right, (state, operation, left, right)
        assert list(proxy.items()) == list(native.items())
        checks += 1


class RaisingEqual:
    def __init__(self):
        self.hash_calls = self.eq_calls = 0

    def __hash__(self):
        self.hash_calls += 1
        return 42

    def __eq__(self, other):
        self.eq_calls += 1
        raise RuntimeError("user equality")


for state in ("initial", "compact", "promoted"):
    for method in ("get", "contains", "set", "delete", "pop", "setdefault", "update", "union"):

        def equality_outcome(factory):
            mapping = factory()
            for key in range(64 if state == "initial" else 256):
                mapping[key] = key
            if state == "promoted" and isinstance(mapping, Index):
                mapping.promote()
            query = RaisingEqual()
            source = {query: "new"}
            query.hash_calls = 0

            def apply():
                if method == "get":
                    return mapping.get(query)
                if method == "contains":
                    return query in mapping
                if method == "set":
                    mapping[query] = "new"
                elif method == "delete":
                    del mapping[query]
                elif method == "pop":
                    return mapping.pop(query)
                elif method == "setdefault":
                    return mapping.setdefault(query, "new")
                elif method == "update":
                    return mapping.update(source)
                elif method == "union":
                    return mapping | source
                return None

            result = outcome(apply)
            return result, query.hash_calls, query.eq_calls

        assert equality_outcome(Index) == equality_outcome(dict), (state, method)
        checks += 1

# Views lock native backing so clear and continued exact-int insertions never detach them.
index = Index()
index[1] = object()
view = index.items()
backing = index._dict
index.clear()
for key in range(500):
    index[key] = key
assert index._dict is backing and list(view) == list(index.items())
# Sharing for each codec state, before observation can promote it.
probe.install("both")
from benchmarks.graph_artifact import _Reader, _Writer  # noqa: E402

for state in ("initial", "compact", "promoted", "sparse"):
    index = Index()
    keys = range(300) if state in ("compact", "promoted") else (range(-300, 0) if state == "sparse" else range(3))
    for key in keys:
        index[key] = "value"
    if state == "promoted":
        index.promote()
    stream = io.StringIO()
    _Writer(stream).ref((MappingProxyType(index), MappingProxyType(index)))
    reader = _Reader()
    for line in stream.getvalue().splitlines():
        _, kind, payload = json.loads(line)
        reader.objects.append(reader.decode(kind, payload))
    left, right = reader.objects[-1]
    assert gc.get_referents(left)[0] is gc.get_referents(right)[0]
    assert left == right == dict(index.raw_items())
    checks += 1
print(
    json.dumps(
        {"checks": checks, "states": ["initial", "compact", "promoted", "sparse"], "shared_backing": True}, indent=2
    )
)
