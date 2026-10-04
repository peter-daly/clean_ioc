"""Tests of item 18's isolated experiment, not a supported compiler cache."""

import gc
import inspect
import types
import weakref
from concurrent.futures import ThreadPoolExecutor

import pytest

from benchmarks import bench_compiler_optimization as fixtures
from benchmarks.incremental_analysis_probe import ORIGINAL, ParameterShapeProbe, investigation
from clean_ioc import ContainerBuilder, ContainerBuildError


def plain(value=1, *, setting=2):
    pass


def test_parameter_shape_uses_code_and_default_shape_and_preserves_errors():
    probe = ParameterShapeProbe()
    probe.validate(plain, {"value": None})
    probe.validate(plain, {"setting": None})
    assert probe.counts["misses"] == 1
    assert probe.counts["hits"] == 1
    with pytest.raises(ContainerBuildError, match="has no argument named 'missing'"):
        probe.validate(plain, {"missing": None})


def test_code_default_signature_wrapper_mutations_and_reload(monkeypatch):
    function = types.FunctionType(plain.__code__, {}, argdefs=(1,))
    function.__kwdefaults__ = {"setting": 2}
    probe = ParameterShapeProbe()
    probe.validate(function, {"value": None})
    function.__defaults__ = (2,)
    probe.validate(function, {"value": None})
    assert probe.counts["hits"] == 1  # Default value cannot change accepted names.
    function.__defaults__ = None
    probe.validate(function, {"value": None})
    assert probe.counts["misses"] == 2
    monkeypatch.setattr(function, "__signature__", inspect.Signature(), raising=False)
    with pytest.raises(ContainerBuildError):
        probe.validate(function, {"value": None})
    monkeypatch.delattr(function, "__signature__")

    def changed(replacement):
        pass

    function.__code__ = changed.__code__
    with pytest.raises(ContainerBuildError):
        probe.validate(function, {"value": None})
    probe.validate(function, {"replacement": None})
    monkeypatch.setattr(function, "__wrapped__", plain, raising=False)
    probe.validate(function, {"setting": None})
    assert probe.counts["rejected: signature control"] == 2
    namespace = {}
    exec("def reloaded(new_name): pass", namespace)  # noqa: S102 - controlled reload fixture.
    probe.validate(namespace["reloaded"], {"new_name": None})
    assert probe.counts["misses"] == 4


def test_class_constructor_changes_and_custom_metaclass_are_rejected():
    class Source:
        def __init__(self, first):
            pass

    probe = ParameterShapeProbe()
    probe.validate(Source, {"first": None})
    setattr(Source, "__init__", lambda self, second: None)
    with pytest.raises(ContainerBuildError):
        probe.validate(Source, {"first": None})

    class Meta(type):
        def __call__(cls, alternative):
            return super().__call__()

    class Custom(metaclass=Meta):
        pass

    probe.validate(Custom, {"alternative": None})
    assert probe.counts["rejected: nonstandard callable"] == 1


def test_deferred_annotations_and_custom_dictionaries_use_original(monkeypatch):
    calls = []
    function = types.FunctionType(plain.__code__, {}, argdefs=(1,))

    class Annotations(dict):
        pass

    function.__annotations__ = Annotations()
    probe = ParameterShapeProbe()
    probe.validate(function, {"value": None})
    assert probe.counts["rejected: nonstandard annotations"] == 1
    if hasattr(function, "__annotate__"):
        function.__annotations__ = {}

        def annotate(format):
            calls.append(format)
            return {}

        function.__annotate__ = annotate
        probe.validate(function, {"value": None})
        assert probe.counts["rejected: deferred annotations"] == 1
        # Explicit fallback invokes original, including its current annotation
        # behavior. No cache contract assumes the evaluator pure or repeatable.
        assert probe.entries == {}


def test_probe_retains_no_function_globals_defaults_or_closure():
    class Private:
        pass

    secret = Private()
    reference = weakref.ref(secret)
    function = types.FunctionType(plain.__code__, {"private": secret}, argdefs=(secret,))
    function.__code__ = function.__code__.replace(co_consts=(*function.__code__.co_consts, secret))
    function_reference = weakref.ref(function)
    function.__annotations__ = {"value": secret}
    probe = ParameterShapeProbe()
    probe.validate(function, {"value": None})
    del secret, function
    gc.collect()
    assert reference() is None
    assert function_reference() is None
    assert len(probe.entries) == 1
    probe.clear()
    assert not probe.entries


def test_bounds_failure_cleanup_and_concurrent_cache_lookups():
    probe = ParameterShapeProbe(limit=1)
    probe.validate(plain, {})

    def other(second):
        pass

    probe.validate(other, {})
    assert len(probe.entries) == 1
    assert probe.counts["evictions"] == 1
    with ThreadPoolExecutor(max_workers=4) as executor:
        list(executor.map(lambda _: probe.validate(other, {"second": None}), range(40)))
    assert probe.counts["hits"] == 40
    with investigation("candidate", probe):
        raise_after_patch = False
        try:
            with investigation("full", probe):
                raise RuntimeError("probe failure")
        except RuntimeError:
            raise_after_patch = True
        assert raise_after_patch
    from clean_ioc import container

    assert container._validate_dependency_names is ORIGINAL

    class BadSignature:
        def __init__():
            pass

    probe.clear()
    probe.validate(BadSignature, {})
    assert probe.counts["signature failures"] == 1
    assert not probe.entries


def test_signature_controls_and_constructor_descriptors_are_ineligible(monkeypatch):
    function = types.FunctionType(plain.__code__, {}, argdefs=(1,))
    setattr(function, "__text_signature__", "(replacement)")
    probe = ParameterShapeProbe()
    probe.validate(function, {"replacement": None})
    assert probe.counts["rejected: signature control"] == 1
    monkeypatch.delattr(function, "__text_signature__")
    function.__annotations__ = {"value": "MissingGlobal"}
    # Strings stay strings in name-only inspect.signature; mutation cannot
    # affect names and no annotation/global result is retained.
    probe.validate(function, {"value": None})
    function.__annotations__["value"] = int
    probe.validate(function, {"value": None})
    assert probe.counts["hits"] == 1

    class Descriptor:
        def __get__(self, instance, owner):
            raise AssertionError("guard must not evaluate constructor descriptors")

    class Source:
        __init__ = Descriptor()

    assert probe._key(Source) == (None, "nonstandard callable")

    class NewSource:
        __new__ = Descriptor()

    assert probe._key(NewSource) == (None, "custom constructor")


@pytest.mark.parametrize("shape", fixtures.SHAPES)
def test_fresh_builds_keep_graphs_counts_and_owners(shape):
    manifests = []
    profiles = []
    probe = ParameterShapeProbe()
    from clean_ioc import CompilationProfiler

    starting_activations = fixtures.ACTIVATIONS
    for mode in ("full", "candidate", "candidate"):
        profiler = CompilationProfiler()
        with investigation(mode, probe):
            with fixtures.make_builder(shape).build(**fixtures.build_inputs(shape), profile=profiler) as owner:
                manifests.append(owner.graph.manifest(all_roots=True).fingerprint)
                profiles.append(profiler.report().counters.values)
    assert fixtures.ACTIVATIONS == starting_activations
    assert len(set(manifests)) == 1
    assert profiles[0] == profiles[1] == profiles[2]


def test_callbacks_mutable_closure_failed_builder_repair_and_fresh_singletons():
    class Root:
        pass

    class Consumer:
        def __init__(self, root):
            self.root = root

    Consumer.__init__.__annotations__ = {"root": Root}

    histories = []
    for mode in ("full", "candidate"):
        state = {"accept": False}
        calls = []

        def predicate(component):
            calls.append(state["accept"])
            return state["accept"]

        builder = ContainerBuilder()
        builder.register(Root, lifespan="singleton", when=predicate)
        builder.register(Consumer)
        probe = ParameterShapeProbe()
        with investigation(mode, probe):
            with pytest.raises(ContainerBuildError):
                builder.build()
            state["accept"] = True
            with builder.build() as first:
                other = ContainerBuilder()
                other.register(Root, lifespan="singleton", when=predicate)
                other.register(Consumer)
                with other.build() as second:
                    assert first.resolve(Root) is not second.resolve(Root)
                    overlay_builder = first.new_scope_builder()
                    with overlay_builder.build() as overlay:
                        assert overlay.resolve(Root) is first.resolve(Root)
        histories.append(calls)
    assert histories[0] == histories[1]
