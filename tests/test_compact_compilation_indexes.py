"""Native adapter boundaries, bounded storage, graph/codec integration."""

import gc
import io
import json
from types import MappingProxyType

import pytest

from benchmarks.graph_artifact import _Reader, _Writer
from clean_ioc._compact_index import _CompactIndex


def outcome(call):
    try:
        return ("value", call())
    except Exception as error:
        return (type(error).__name__,)


class ClassOperand:
    @property
    def __class__(self):
        raise AssertionError("application __class__ callback")


@pytest.mark.parametrize("operation", ("__eq__", "__or__", "__ror__", "__ior__", "update"))
def test_general_operations_do_not_inspect_foreign_class_attribute(operation):
    operand = ClassOperand()
    assert outcome(lambda: getattr(_CompactIndex(), operation)(operand)) == outcome(
        lambda: getattr({}, operation)(operand)
    )


@pytest.mark.parametrize(
    "method,keywords",
    (
        ("__getitem__", {"key": 1}),
        ("__setitem__", {"key": 1, "value": 2}),
        ("__delitem__", {"key": 1}),
        ("__contains__", {"key": 1}),
        ("__eq__", {"other": {}}),
        ("__or__", {"other": {}}),
        ("__ror__", {"other": {}}),
        ("__ior__", {"other": {}}),
        ("get", {"key": 1}),
        ("pop", {"key": 1}),
        ("setdefault", {"key": 1}),
    ),
)
def test_native_methods_reject_keyword_arguments(method, keywords):
    assert outcome(lambda: getattr(_CompactIndex(), method)(**keywords)) == outcome(
        lambda: getattr({}, method)(**keywords)
    )


def test_update_self_keyword_is_a_mapping_entry():
    index = _CompactIndex()
    index.update(self=42)
    assert index.copy() == {"self": 42}


@pytest.mark.parametrize("state", ("tiny", "compact", "promoted", "sparse"))
def test_codec_keeps_shared_proxy_backing_and_original_value_identity(state):
    index = _CompactIndex()
    keys = range(300) if state in ("compact", "promoted") else range(3) if state == "tiny" else range(-300, 0)
    for key in keys:
        index[key] = ("same",)
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
    assert left[next(iter(keys))] is right[next(iter(keys))]


@pytest.mark.parametrize("payload", (None, [None], [[1]], [[True, None]], [[1, None], [1, None]]))
def test_codec_rejects_malformed_compact_rows(payload):
    with pytest.raises(ValueError):
        _Reader().decode("compact-index", payload)


def test_live_views_lock_one_native_backing_after_clear_and_growth():
    index = _CompactIndex()
    index[1] = "first"
    view = MappingProxyType(index).items()
    iterator = iter(view)
    assert next(iterator) == (1, "first")
    backing = index._dict
    index.clear()
    for key in range(512):
        index[key] = key
    assert index._dict is backing
    assert list(view) == list(index.items())
    with pytest.raises(RuntimeError):
        next(iterator)


@pytest.mark.parametrize("keys", (range(-300, 0), range(10000, 0, -1), range(0, 10000, 20), (10**100, -(10**100))))
def test_sparse_or_reverse_indexes_keep_bounded_backing(keys):
    index = _CompactIndex()
    for key in keys:
        index[key] = key
    assert index._dict is not None
    assert index._values is None
    assert list(index) == list(keys)


def test_dense_conversion_and_promotion_release_old_containers():
    index = _CompactIndex()
    for key in range(512):
        index[key] = key
    assert index._dict is None
    for key in range(100):
        index[10**100 + key] = key
    assert index._dict is not None
    assert index._values is index._keys is index._sparse is None


class CountedHash:
    def __init__(self):
        self.calls = 0
        self.limit = 100

    def __hash__(self):
        self.calls += 1
        if self.calls > self.limit:
            raise RuntimeError("extra hash")
        return 4000

    def __eq__(self, other):
        return other == 4000


@pytest.mark.parametrize("operation", ("pop", "copy", "equality", "update", "setdefault", "proxy-equality"))
def test_original_six_custom_hash_regressions(operation):
    def run(factory):
        key = CountedHash()
        mapping = factory()
        if operation in ("pop", "copy", "equality"):
            mapping[key] = "value"
        if operation == "proxy-equality":
            for number in range(5000):
                mapping[number] = "value"
        source: dict[object, str] | None = {key: "value"} if operation in ("update", "proxy-equality") else None
        if operation == "proxy-equality":
            assert source is not None
            source.update({number: "value" for number in range(5000) if number != 4000})
        key.calls = 0
        key.limit = 1 if operation in ("pop", "setdefault") else 0

        def apply():
            if operation == "pop":
                mapping.pop(key)
            elif operation == "copy":
                mapping.copy()
            elif operation == "equality":
                return mapping == mapping
            elif operation == "update":
                mapping.update(source)
            elif operation == "proxy-equality":
                return MappingProxyType(mapping) == source
            else:
                mapping.setdefault(key, "value")
            return None

        return outcome(apply), key.calls

    assert run(_CompactIndex) == run(dict)


@pytest.mark.parametrize("operation", ("set", "get", "getitem", "contains"))
@pytest.mark.parametrize("raises", (False, True))
def test_foreign_hash_reentrancy_cannot_detach_an_in_progress_native_operation(operation, raises):
    def run(factory):
        mapping = factory()
        for number in range(127):
            mapping[number] = number

        class Key:
            def __hash__(self):
                mapping[127] = 127
                mapping[126] = "changed"
                if raises:
                    raise RuntimeError("hash failure")
                return 126

            def __eq__(self, other):
                return other == 126

        key = Key()

        def apply():
            if operation == "set":
                mapping[key] = "inserted"
                return None
            if operation == "get":
                return mapping.get(key)
            if operation == "getitem":
                return mapping[key]
            return key in mapping

        result = outcome(apply)
        return result, dict(mapping)

    assert run(_CompactIndex) == run(dict)


@pytest.mark.parametrize("mode", ("run", "analysis"))
def test_caller_held_sidecar_proxy_survives_build_and_native_promotion(mode):
    from clean_ioc import ContainerBuilder

    saved = []

    def rule(context):
        mapping = context.graph._occurrence_origins
        backing = gc.get_referents(mapping)[0]
        assert isinstance(backing, dict)
        saved.append((mapping, mapping.items(), len(mapping), backing))
        return ()

    builder = ContainerBuilder()
    for number in range(140):
        builder.register(type(f"Service{number}", (), {}))
    builder.set_provider_roots(())
    builder.add_validation_rule(rule)
    with builder.verify() as analysis, analysis.create_runtime() as runtime:
        mapping, view, count, backing = saved[0]
        assert len(mapping) == len(view) == count
        assert gc.get_referents(mapping)[0] is backing
        assert len(runtime.selected_registrations) == 140
    assert len(mapping) == len(view) == count
