"""Optional activation reuse preserves observable application ownership."""

import gc
import weakref
from collections.abc import Mapping
from contextlib import contextmanager
from dataclasses import dataclass, replace
from types import SimpleNamespace
from typing import Any, Literal

import pytest

from clean_ioc import (
    ContainerBuilder,
    ContainerBuildError,
    Instrumentation,
    Provider,
    ResolutionProfiler,
    ScopeBuilder,
    VerificationReport,
    derive,
)
from clean_ioc import container as code


class Payload:
    pass


class StringPayload(str):
    pass


@dataclass(frozen=True)
class MapKey:
    label: str


class Target:
    pass


class ValueCandidate:
    def __init__(self, value: object):
        self.value = value


class MapCandidate:
    def __init__(self, values: Mapping[MapKey, Provider[Target]]):
        self.values = values


class FirstValues:
    def __init__(self, values: list[ValueCandidate]):
        self.values = values


class FirstMaps:
    def __init__(self, values: list[MapCandidate]):
        self.values = values


class Later:
    def __init__(self, alive: bool):
        self.alive = alive


def opaque_case(kind, *, mode=None, diagnostics=False, metadata=False, caller_held=False, fail=False):
    references, calls, held, observations = [], [], [], []

    def make_value(context):
        calls.append("derive")
        value = StringPayload("opaque string subclass") if kind == "string-subclass" else Payload()
        references.append(weakref.ref(value))
        if caller_held:
            held.append(value)
        return [value] if kind == "container" else value

    def make_key(component):
        calls.append("key")
        value = MapKey(component.id)
        references.append(weakref.ref(value))
        return value

    def reject(component):
        calls.append("reject")
        return False

    def observe(context):
        calls.append("observe")
        gc.collect()
        result = bool(references and references[0]() is not None)
        observations.append(result)
        if fail:
            raise RuntimeError("failure after observing discarded branch")
        return result

    builder = ContainerBuilder().set_provider_roots(())
    if kind == "map-key":
        builder.register(Target, root_policy="dependency_only")
        builder.register_provider_map(Target, key=make_key, key_type=MapKey, root_policy="dependency_only")
        builder.register(MapCandidate, root_policy="dependency_only", when=reject)
        builder.register(FirstMaps)
    else:
        builder.register(
            ValueCandidate, root_policy="dependency_only", arguments={"value": derive(make_value)}, when=reject
        )
        builder.register(FirstValues)
    builder.register(Later, arguments={"alive": derive(observe)})
    if fail:
        assert mode is not None
        with pytest.raises(ContainerBuildError):
            builder.build()
        assert observations and all(observations)
        return
    output = builder.verify() if mode == "analysis" else builder.build()
    with output:
        owner = output.create_runtime() if isinstance(output, VerificationReport) else output
        assert owner.resolve(Later).alive is True
        expected = ["key" if kind == "map-key" else "derive", "reject", "observe"]
        if mode == "analysis":
            expected += ["key", "key", "reject"] if kind == "map-key" else ["derive", "reject"]
        assert calls == expected
        if caller_held:
            assert references[0]() is not None


@pytest.mark.parametrize("kind", ["object", "string-subclass", "container", "map-key"])
@pytest.mark.parametrize("diagnostics", [False, True])
@pytest.mark.parametrize("metadata", [False, True])
def test_original_sixteen_opaque_lifetime_cases(kind, diagnostics, metadata):
    opaque_case(kind, diagnostics=diagnostics, metadata=metadata)


@pytest.mark.parametrize("kind", ["object", "string-subclass", "container", "map-key"])
@pytest.mark.parametrize("mode", ["run", "analysis"])
def test_public_modes_keep_rejected_opaque_closures(kind, mode):
    opaque_case(kind, mode=mode)


@pytest.mark.parametrize("mode", ["run", "analysis"])
@pytest.mark.parametrize("kind", ["object", "map-key"])
def test_failed_branches_keep_values_through_later_callback(mode, kind):
    opaque_case(kind, mode=mode, fail=True)


@pytest.mark.parametrize("mode", ["run", "analysis"])
def test_caller_owned_values_keep_independent_lifetimes(mode):
    opaque_case("object", mode=mode, caller_held=True)


def step_with(*dependencies, step_type: Any = code._TransientRegistrationStep):
    return step_type(
        registration=SimpleNamespace(),
        source_service_type=Target,
        owner_token="owner",  # noqa: S106
        component=SimpleNamespace(),
        dependencies=tuple(code._CompiledDependency(str(i), step) for i, step in enumerate(dependencies)),
        pre_configurations=(),
        decorators=(),
        cleanup_owner=code._NO_CLEANUP_OWNER,
        sync_supported=True,
    )


def cache_key(step=None):
    return (
        1,
        2,
        ("object", id(Target)),
        code._TransientRegistrationStep,
        "owner",
        code._NO_CLEANUP_OWNER,
        True,
        () if step is None else tuple((item.name, id(item.step)) for item in step.dependencies),
    )


@pytest.mark.parametrize("value", [None, False, 1, 1.2, 1j, "text", b"text"])
def test_exact_scalars_release_cache_keys_without_application_hashing(value):
    cache = code._ActivationTemplateCache()
    step = step_with(code._ValueStep(value))
    key = cache_key(step)
    cache[key] = step
    assert cache.get(key) is step
    reference = weakref.ref(step)
    del step
    gc.collect()
    assert reference() is None
    assert cache.get(key) is None
    assert not cache._entries


@pytest.mark.parametrize("value", [Payload(), StringPayload("x"), [], {}, (), frozenset(), object()])
def test_non_scalar_and_subclass_values_keep_whole_dependency_closure(value):
    cache = code._ActivationTemplateCache()
    leaf = step_with(code._ValueStep(value))
    step = step_with(leaf)
    cache[cache_key()] = step
    reference = weakref.ref(leaf)
    del step, leaf
    gc.collect()
    assert reference() is not None
    cached = cache.get(cache_key())
    assert cached is not None
    assert cached.dependencies[0].step is reference()
    assert all(type(entry) is not weakref.ReferenceType for entry in cache._entries.values())


def test_unknown_execution_forms_and_decorated_steps_stay_strong_without_content_inspection():
    class Unknown(code._TransientRegistrationStep):
        pass

    class Hostile:
        def __hash__(self):
            pytest.fail("eligibility hashed application value")

        def __eq__(self, other):
            pytest.fail("eligibility compared application value")

        def __getattribute__(self, name):
            pytest.fail("eligibility inspected application value")

    plain = step_with()
    unknown = step_with(step_type=Unknown)
    for step in (
        step_with(code._ValueStep(Hostile())),
        unknown,
        step_with(unknown),
        step_with(code._CollectionStep(list, (plain,), True)),
        step_with(code._ProvidedStep(Target, None)),
        step_with(code._ProviderStep("sync", plain, None)),
        replace(plain, decorators=(Hostile(),)),
        replace(plain, pre_configurations=(Hostile(),)),
    ):
        assert not code._scalar_activation_closure(step)


@pytest.mark.parametrize("mode", ["run", "analysis"])
@pytest.mark.parametrize("lifespan", ["transient", "per_resolution", "scoped", "singleton"])
def test_rejected_then_selected_key_preserves_observed_edge_and_cleanup(mode, lifespan, monkeypatch):
    def run(strong):
        events, lookups, calls = [], [], []
        original = code._ActivationTemplateCache

        class Cache(original):
            def get(self, key):
                value = super().get(key)
                lookups.append((key, value is not None))
                return value

            def __setitem__(self, key, step):
                if strong:
                    self._entries[key] = step
                else:
                    super().__setitem__(key, step)

        monkeypatch.setattr(code, "_ActivationTemplateCache", Cache)

        class Resource:
            pass

        class Wrapper(Resource):
            def __init__(self, inner: Resource):
                self.inner = inner

        class First:
            def __init__(self, values: list[Resource]):
                self.values = values

        class Second:
            def __init__(self, value: Resource):
                self.value = value

        @contextmanager
        def resource():
            events.append("enter")
            yield Resource()
            events.append("exit")

        def when(component):
            calls.append("when")
            parent = component.parent
            while parent is not None:
                if parent.service_type is First:
                    return False
                parent = parent.parent
            return True

        builder = ContainerBuilder().set_provider_roots(())
        builder.register(Resource, factory=resource, lifespan=lifespan, root_policy="dependency_only", when=when)
        # An arbitrary decorator predicate prevents invariant-subplan reuse but
        # never decorates this scalar-only leaf. The activation key repeats.
        builder.register_decorator(Resource, Wrapper, when=lambda _: False)
        builder.register(First, lifespan=lifespan)
        builder.register(Second, lifespan=lifespan)
        profiler = ResolutionProfiler()
        owner = builder.build(instrumentation=Instrumentation(profiler))
        assert events == []
        with owner:
            assert owner.resolve(First).values == []
            assert isinstance(owner.resolve(Second).value, Resource)
            owner.resolve(Second)
            child = owner.new_scope()
            child.resolve(Second)
            child._close()
        records = [
            (r.kind, r.path, r.attempts, r.completed, r.failed, r.cache_hits, r.cache_misses)
            for r in profiler.report().records
            if r.attempts or r.cache_hits
        ]
        assert not any("<unresolved request>" in r[1] for r in records)
        repeated = [hit for key, hit in lookups if key[0] == lookups[0][0][0]]
        monkeypatch.setattr(code, "_ActivationTemplateCache", original)
        return events, calls, records, repeated

    strong = run(True)
    weak = run(False)
    assert strong[:3] == weak[:3]
    assert strong[3][:2] == [False, True]
    assert weak[3][:2] == [False, False]


@pytest.mark.parametrize("mode", ["run", "analysis"])
def test_overlay_inherits_live_singleton_and_opaque_values(mode):
    value = Payload()
    parent_builder = ContainerBuilder().set_provider_roots(())
    parent_builder.register(ValueCandidate, arguments={"value": value}, lifespan="singleton")
    parent_composition = parent_builder.retain_composition()
    with parent_builder.build() as parent:
        shared = parent.resolve(ValueCandidate)
        builder = ScopeBuilder(parent, composition=parent_composition).set_provider_roots(())
        builder.register(FirstValues)
        with builder.build() as child:
            assert child.resolve(ValueCandidate) is shared
            assert child.resolve(FirstValues).values[0] is shared
            assert shared.value is value


def test_custom_metaclass_never_controls_exact_eligibility_or_releases_payload():
    class HostileMeta(type):
        def __eq__(cls, other):
            pytest.fail("exact carrier eligibility invoked metaclass equality")

        def __hash__(cls):
            pytest.fail("exact carrier eligibility invoked metaclass hashing")

    class Opaque(metaclass=HostileMeta):
        pass

    class UnknownStep(code._TransientRegistrationStep, metaclass=HostileMeta):
        pass

    cache = code._ActivationTemplateCache()
    payload = Opaque()
    reference = weakref.ref(payload)
    step = step_with(code._ValueStep(payload))
    cache[cache_key()] = step
    assert not code._scalar_activation_closure(step_with(step_type=UnknownStep))
    assert not code._activation_key_is_inert((*cache_key()[:3], Opaque, *cache_key()[4:]))
    del payload, step
    gc.collect()
    assert reference() is not None


def test_application_key_fallback_uses_only_original_dictionary_hash_operations():
    calls = []

    class Name(str):
        def __hash__(self):
            calls.append("hash")
            return super().__hash__()

    def operations(cache):
        calls.clear()
        key = (*cache_key()[:7], ((Name("argument"), 123),))
        step = step_with()
        assert cache.get(key) is None
        snapshots = [len(calls)]
        cache[key] = step
        snapshots.append(len(calls))
        reference = weakref.ref(step)
        del step
        gc.collect()
        assert reference() is not None
        assert cache.get(key) is reference()
        snapshots.append(len(calls))
        return snapshots

    assert operations(code._ActivationTemplateCache()) == operations({})


def test_old_weak_callback_cannot_delete_replacement_entry():
    cache = code._ActivationTemplateCache()
    first, second = step_with(), step_with()
    cache[cache_key()] = first
    old = cache._entries[cache_key()]
    assert isinstance(old, weakref.ReferenceType)
    cache[cache_key()] = second
    del first
    gc.collect()
    assert old() is None
    assert cache.get(cache_key()) is second


@pytest.mark.parametrize("mode", ["run", "analysis"])
@pytest.mark.parametrize("fail", [False, True])
def test_nested_build_and_failure_release_compiler_local_owners(mode, fail, monkeypatch):
    references, caches, events = [], [], []
    original = code._Compiler.__init__

    def initialize(compiler, *args, **kwargs):
        original(compiler, *args, **kwargs)
        references.append(weakref.ref(compiler))
        caches.append(weakref.ref(compiler._activation_templates))

    monkeypatch.setattr(code._Compiler, "__init__", initialize)

    class Tracked:
        def __del__(self):
            events.append("deleted")

    def value(context):
        events.append("created")
        return Tracked()

    def later(context):
        events.append("observed")
        assert "deleted" not in events
        nested = ContainerBuilder().set_provider_roots(())
        nested.register(Target)
        with nested.build() as child:
            assert isinstance(child.resolve(Target), Target)
        if fail:
            raise RuntimeError("nested build completed")
        return True

    builder = ContainerBuilder().set_provider_roots(())
    builder.register(
        ValueCandidate, root_policy="dependency_only", when=lambda _: False, arguments={"value": derive(value)}
    )
    builder.register(FirstValues)
    builder.register(Later, arguments={"alive": derive(later)})
    if fail:
        # Analysis may retry independent roots. Each observation must still see
        # the original primary compiler's live strong closure.
        with pytest.raises(ContainerBuildError) as caught:
            builder.build()
        del caught
    else:
        with builder.build() as owner:
            assert owner.resolve(Later).alive is True
        del owner
    del builder
    gc.collect()
    assert all(reference() is None for reference in references)
    assert all(reference() is None for reference in caches)
    assert events.index("created") < events.index("observed") < events.index("deleted")
    assert events.count("created") == events.count("deleted")


@pytest.mark.parametrize("mode", ["run", "analysis"])
def test_mutable_literal_metadata_never_adds_application_equality_during_cache_removal(mode, monkeypatch):
    original = code._ActivationTemplateCache

    def run(strong):
        calls, comparisons_after_second_rejection = [], []
        rejections = 0

        class Name(str):
            __hash__ = str.__hash__

            def __eq__(self, other):
                calls.append("equality")
                if rejections == 2:
                    comparisons_after_second_rejection.append(True)
                return False

        class Scalar(str):
            pass

        Scalar.__module__ = Name("literal_metadata")
        contract = Literal[Scalar("token")]  # ty: ignore[invalid-type-form]

        class First:
            def __init__(self, values: list[contract]):
                self.values = values

        class Second:
            def __init__(self, values: list[contract]):
                self.values = values

        class Wrapper:
            def __init__(self, inner: contract):
                self.inner = inner

        def reject(component):
            nonlocal rejections
            rejections += 1
            calls.append("reject")
            Scalar.__module__ = "literal_metadata"
            return False

        def observe(context):
            calls.append("observe")
            return bool(comparisons_after_second_rejection)

        monkeypatch.setattr(code, "_ActivationTemplateCache", dict if strong else original)
        builder = ContainerBuilder().set_provider_roots(())
        builder.register(contract, factory=lambda: "token", root_policy="dependency_only", when=reject)
        builder.register_decorator(contract, Wrapper, when=lambda _: False)
        builder.register(First)
        builder.register(Second)
        builder.register(Later, arguments={"alive": derive(observe)})
        with builder.build() as owner:
            result = owner.resolve(Later).alive
        return result

    assert run(True) is False
    assert run(False) is False


@pytest.mark.parametrize(
    "type_key",
    [
        ("literal", "builtins", "str", "'x'"),
        ("sequence", "list", ()),
        ("generic", 1, (("literal", "builtins", "int", "1"),)),
        ("future", 1),
    ],
)
def test_metadata_and_unknown_type_key_grammars_remain_strong(type_key):
    cache = code._ActivationTemplateCache()
    key = (*cache_key()[:2], type_key, *cache_key()[3:])
    step = step_with()
    cache[key] = step
    reference = weakref.ref(step)
    del step
    gc.collect()
    assert cache.get(key) is reference()
    assert reference() is not None
