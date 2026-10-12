"""Equivalence proof for copying an occurrence's captured implementation type."""

import inspect
from collections.abc import Mapping
from dataclasses import fields, is_dataclass

import pytest

import clean_ioc.container as compiler_module
from benchmarks import bench_compiler_optimization as workloads
from clean_ioc import ComponentActivation, ComponentKind, ContainerBuilder, ScopeBuilder


def _baseline_draft(original):
    def draft(self, **kwargs):
        captured = kwargs.pop("implementation_type", compiler_module._IMPLEMENTATION_TYPE_UNSET)
        component, record = original(self, **kwargs)
        # Reproduce the discarded normalization and immediate overwrite in the
        # old clone path. Ordinary fresh occurrences are unchanged.
        if captured is not compiler_module._IMPLEMENTATION_TYPE_UNSET:
            record.implementation_type = captured
        return component, record

    return draft


def _normalized(value, replacements):
    """Compare private facts in memory, accounting for fresh generated IDs."""
    if isinstance(value, str):
        for before, after in replacements.items():
            value = value.replace(before, after)
        return value
    if isinstance(value, Mapping):
        return {_normalized(key, replacements): _normalized(item, replacements) for key, item in value.items()}
    if is_dataclass(value) and not isinstance(value, type):
        return {item.name: _normalized(getattr(value, item.name), replacements) for item in fields(value)}
    if isinstance(value, (tuple, list)):
        return tuple(_normalized(item, replacements) for item in value)
    return value


def _assert_equivalent(make_builder, monkeypatch, *, build_args=None):
    optimized = make_builder().verify(build_args=build_args)
    with monkeypatch.context() as patch:
        patch.setattr(compiler_module._Compiler, "_draft", _baseline_draft(compiler_module._Compiler._draft))
        baseline = make_builder().verify(build_args=build_args)
    optimized.assert_valid()
    baseline.assert_valid()
    left = optimized.graph.roots[0].component._graph._records
    right = baseline.graph.roots[0].component._graph._records
    assert tuple(left) == tuple(right)
    ids = {record.id: right[occurrence].id for occurrence, record in left.items()}
    baseline_ids = {reference: identity for identity, reference in baseline.graph._census_ids.items()}
    ids.update({identity: baseline_ids[reference] for identity, reference in optimized.graph._census_ids.items()})
    assert _normalized(left, ids) == _normalized(right, {})
    for name in (
        "_occurrence_explanations",
        "_occurrence_origins",
        "_decorator_explanations",
        "_parameter_explanations",
        "_generic_explanations",
        "_occurrence_layers",
        "_census_definitions",
        "_census_sources",
    ):
        assert _normalized(getattr(optimized.graph, name), ids) == _normalized(getattr(baseline.graph, name), {})
    assert optimized.graph.manifest(all_roots=True).to_json() == baseline.graph.manifest(all_roots=True).to_json()
    assert optimized.graph.manifest().fingerprint == baseline.graph.manifest().fingerprint
    assert not optimized.graph.diff(baseline.graph.manifest()).changed
    assert optimized.to_json() == baseline.to_json()
    assert optimized.graph.to_text(all_roots=True) == baseline.graph.to_text(all_roots=True)
    assert optimized.graph.to_mermaid(all_roots=True) == baseline.graph.to_mermaid(all_roots=True)
    assert optimized.graph.ownership_report().to_json() == baseline.graph.ownership_report().to_json()
    assert optimized.graph.sharing_report().to_json() == baseline.graph.sharing_report().to_json()
    for actual_root, expected_root in zip(optimized.graph.roots, baseline.graph.roots, strict=True):
        assert (
            optimized.graph.activation_report(actual_root.component).to_json()
            == baseline.graph.activation_report(expected_root.component).to_json()
        )
    assert optimized.selection_census(all_roots=True).to_json() == baseline.selection_census(all_roots=True).to_json()
    with optimized.create_runtime() as actual, baseline.create_runtime() as expected:
        assert [(item.service_type, item.implementation_type) for item in actual.selected_registrations] == [
            (item.service_type, item.implementation_type) for item in expected.selected_registrations
        ]


@pytest.mark.parametrize("shape", workloads.SHAPES)
def test_cloned_metadata_matches_discarded_normalization_baseline(shape, monkeypatch):
    _assert_equivalent(lambda: workloads.make_builder(shape), monkeypatch, **workloads.build_inputs(shape))


def test_anchored_overlay_preserves_source_graph_sidecars(monkeypatch):
    parent_builder = ContainerBuilder()
    parent_builder.register(workloads.Leaf, lifespan="singleton")
    parent_builder.register(workloads.Worker, lifespan="singleton")
    parent_composition = parent_builder.retain_composition()
    with parent_builder.build() as parent:

        def make_builder():
            builder = ScopeBuilder(parent, composition=parent_composition)
            builder.register(workloads.CollectionRoot)
            return builder

        _assert_equivalent(make_builder, monkeypatch)


@pytest.mark.parametrize("captured", [dict, None])
def test_clone_preserves_enriched_or_unknown_type_without_normalizing(monkeypatch, captured):
    builder = ContainerBuilder()
    blueprint, inputs = builder._compilation_snapshot(None)
    compiler = compiler_module._Compiler(blueprint, build_args=inputs["build_args"])
    calls = []
    original = compiler_module.normalize_implementation_type

    def normalize(implementation, service_type):
        calls.append((implementation, service_type))
        return original(implementation, service_type)

    monkeypatch.setattr(compiler_module, "normalize_implementation_type", normalize)
    component, record = compiler._draft(
        component_id="source",
        service_type=workloads.Leaf,
        implementation=workloads.Leaf,
        lifespan="transient",
        name=None,
        tags=(),
        kind=ComponentKind.registration,
        activation=ComponentActivation.constructor,
        parent=None,
    )
    assert len(calls) == 1
    # Source-inspection enrichment can override fresh normalization. None is an
    # explicit captured value, distinct from the private unset sentinel.
    record.implementation_type = captured
    clone = compiler._clone_component_tree(component, parent=None)
    assert len(calls) == 1
    assert clone.implementation_type is captured
    assert clone.occurrence_id != component.occurrence_id
    assert clone._record is not record
    assert clone.service_type is component.service_type
    assert clone.implementation is component.implementation


def test_captured_type_survives_changed_signature_getter_but_fresh_inspection_fails(monkeypatch):
    class Service:
        pass

    class Decorator(Service):
        def __init__(self, inner: Service):
            self.inner = inner

    class Factory:
        broken = False
        activations = 0

        @property
        def __signature__(self):
            if self.broken:
                raise RuntimeError("dynamic signature changed after capture")
            return inspect.Signature(return_annotation=Service)

        def __call__(self) -> Service:
            self.activations += 1
            return Service()

    def composition(factory, callbacks):
        def mutate(component):
            callbacks.append(component.implementation_type)
            factory.broken = True
            return True

        builder = ContainerBuilder()
        builder.register(Service, factory=factory)
        builder.register_decorator(Service, Decorator, decorated_arg="inner", when=mutate)
        return builder

    factory = Factory()
    callbacks = []
    with composition(factory, callbacks).build() as owner:
        assert callbacks == [Service]
        assert factory.activations == 0
        value = owner.resolve(Service)
        assert isinstance(value, Decorator)
        assert isinstance(value.inner, Service)
        assert factory.activations == 1

    # The old path exposed an incidental failure from a repeated signature read
    # whose result was discarded. Registered callback invocation is unchanged.
    original = compiler_module._Compiler._draft
    with monkeypatch.context() as patch:
        patch.setattr(compiler_module._Compiler, "_draft", _baseline_draft(original))
        baseline_factory = Factory()
        baseline_callbacks = []
        # Automatic adapters now read the captured source metadata directly;
        # even forcing fresh normalization on physical clones cannot affect them.
        with composition(baseline_factory, baseline_callbacks).build() as owner:
            assert owner._plan.provider_roots
        assert baseline_callbacks == [Service]
        assert baseline_factory.activations == 0

    # Isolate fresh primary normalization from earlier signature validation.
    # Its errors still surface when no captured override is supplied.
    blueprint, inputs = ContainerBuilder()._compilation_snapshot(None)
    compiler = compiler_module._Compiler(blueprint, build_args=inputs["build_args"])
    with pytest.raises(RuntimeError, match="dynamic signature changed after capture"):
        compiler._draft(
            component_id="fresh",
            service_type=Service,
            implementation=factory,
            lifespan="transient",
            name=None,
            tags=(),
            kind=ComponentKind.registration,
            activation=ComponentActivation.factory,
            parent=None,
        )

    # A fresh primary occurrence still performs reflection. Break the getter
    # after declaration, so this exercises build-time validation rather than
    # registration-time parsing; both clone paths preserve the failure.
    for baseline in (False, True):
        fresh_factory = Factory()
        fresh_callbacks = []
        builder = composition(fresh_factory, fresh_callbacks)
        fresh_factory.broken = True
        with monkeypatch.context() as patch:
            if baseline:
                patch.setattr(compiler_module._Compiler, "_draft", _baseline_draft(original))
            with pytest.raises(RuntimeError, match="dynamic signature changed after capture"):
                builder.verify()
        assert fresh_callbacks == []
        assert fresh_factory.activations == 0
