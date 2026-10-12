"""Execution omits diagnostic capture while analysis keeps original decisions."""

import gc
import os
import weakref
from collections.abc import Mapping
from dataclasses import fields
from pathlib import Path
from typing import Generic, TypeVar

import pytest

import clean_ioc.container as compiler
from clean_ioc import (
    CompilationBudget,
    CompilationProfiler,
    ContainerBuilder,
    ContainerBuildError,
    DecoratorTemplate,
    DerivedServices,
    Expose,
    Provider,
    ProviderMapGroup,
    RegistrationTemplate,
    ScopeBuilder,
    WarmupPlan,
    WarmupTarget,
)
from tests.verification_helpers import present

T = TypeVar("T")


class Resource:
    pass


class Source:
    def __init__(self, resource: Resource):
        self.resource = resource


class Target(Generic[T]):
    def __init__(self, resource: Resource, payload: T):
        self.resource, self.payload = resource, payload


class Wrapper:
    def __init__(self, inner: Target[int]):
        self.inner = inner


class Dispatcher:
    def __init__(self, targets: Mapping[str, Provider[Target[int]]]):
        self.targets = targets


def forbid(*args, **kwargs):
    raise AssertionError("Execution allocated analysis-only evidence")


def forbid_evidence(monkeypatch):
    for cls in (
        compiler.DefinitionOrigin,
        compiler.SourceLocation,
        compiler.CandidateDecision,
        compiler._CandidateRecord,
        compiler.TemplateDecision,
        compiler._TemplateSourceSelection,
        compiler.CompilationExplanation,
        compiler.ParameterExplanation,
        compiler.GenericBindingExplanation,
        compiler.BuildIssue,
        compiler._RemappedDecoratorExplanation,
        compiler._OccurrenceLayers,
        compiler.FailureEvidence,
        compiler.CompilationAttempt,
        compiler.PartialGraph,
        compiler.CompiledGraph,
        compiler.VerificationReport,
        compiler._PlanSet,
        compiler._ExplanationCloneContext,
    ):
        monkeypatch.setattr(cls, "__init__", forbid)
    for name in ("_origin_evidence", "_source_evidence", "_source_binding_labels", "_filter_description"):
        monkeypatch.setattr(compiler, name, forbid)


def facts(component):
    return (
        component.service_type,
        component.implementation_type,
        component.boundary,
        component.argument,
        component.position,
        component.parent.occurrence_id if component.parent is not None else None,
        tuple(child.occurrence_id for child in component.dependencies),
        tuple(child.occurrence_id for child in component.decorators),
        tuple(component.generic_mapping.items()),
    )


def complex_builder(calls, snapshots, *, automatic_providers=False, rules=True):
    source = ContainerBuilder()
    if not automatic_providers:
        source.set_provider_roots(())
    boundary = source.create_boundary("private", exposes=(Expose(Dispatcher),))
    boundary.register(Resource, lifespan="singleton", root_policy="dependency_only")
    boundary.register(Source, name="yes", root_policy="dependency_only")
    boundary.register(Source, name="no", root_policy="dependency_only")
    group = ProviderMapGroup("targets", str, Target[int])

    def source_filter(component):
        calls.append(("source", component.name))
        assert component.dependencies[0].service_type is Resource
        snapshots.append((component, facts(component)))
        return component.name == "yes"

    def template(info):
        calls.append(("registration", info.name))
        return RegistrationTemplate(
            Target[int],
            arguments={"payload": 42},
            root_policy="dependency_only",
            contributes={group: "chosen"},
        )

    def when(component):
        calls.append(("when", component.service_type))
        assert component.generic_mapping[T] is int
        snapshots.append((component, facts(component)))
        return True

    def position(preview, component):
        calls.append(("position", component.service_type))
        assert preview.decorated.occurrence_id == component.occurrence_id
        assert preview.position is None
        snapshots.extend(((preview, facts(preview)), (component, facts(component))))
        return 3

    boundary.register_registration_template(for_each=Source, source_filter=source_filter, template=template)
    boundary.register_decorator_template(
        for_each=Source,
        source_filter=source_filter,
        template=lambda _: DecoratorTemplate(DerivedServices(Target[int]), Wrapper, when=when, position=position),
    )
    boundary.register_decorator_template(
        for_each=Source,
        source_filter=source_filter,
        template=lambda _: DecoratorTemplate(DerivedServices(bytes), Wrapper),
    )
    boundary.register_provider_map(group, root_policy="dependency_only")
    boundary.register(Dispatcher)
    if rules:
        source.add_validation_rule(lambda context: calls.append(("rule", "root")) or ())
        boundary.add_validation_rule(lambda context: calls.append(("rule", "boundary")) or ())
    return source


@pytest.mark.parametrize("rules", [False, True])
@pytest.mark.parametrize("automatic_providers", [False, True])
@pytest.mark.parametrize("profile", [False, True])
def test_registration_preparation_and_execution_construct_no_analysis_evidence(
    monkeypatch, rules, automatic_providers, profile
):
    forbid_evidence(monkeypatch)
    calls, snapshots = [], []
    source = complex_builder(calls, snapshots, automatic_providers=automatic_providers, rules=rules)
    with source.build(
        profile=CompilationProfiler() if profile else None,
        budget=CompilationBudget(preparation_operations=10000),
    ) as runtime:
        before = list(calls)
        target = runtime.resolve(Dispatcher).targets["chosen"]()
        assert isinstance(target, Wrapper)
        assert target.inner.payload == 42
        assert calls == before
        assert not any(kind == "rule" for kind, _ in calls)
        assert {info.implementation_type for info in runtime.selected_registrations} >= {Target[int], Wrapper}
        assert source._registration_origins == {}
        assert not {"root_candidates", "occurrence_origins", "decorator_explanations"} & {
            field.name for field in fields(runtime._plan)
        }
    assert snapshots
    for component, before in snapshots:
        assert facts(component) == before


def test_analysis_keeps_original_source_and_target_decisions_without_callback_replay():
    calls, snapshots = [], []
    with complex_builder(calls, snapshots).verify() as result:
        assert result.is_valid
        assert calls.count(("rule", "root")) == 1
        assert calls.count(("rule", "boundary")) == 1
        before = list(calls)
        graph = result.graph
        sources = graph._template_source_decisions
        assert len(sources) == 6
        assert {item.selected for item in sources} == {False, True}
        assert all(isinstance(item.origin, compiler.DefinitionOrigin) for item in sources)
        assert all(item.origin.location.path.endswith("test_execution_evidence_capture.py") for item in sources)
        decisions = [
            item
            for explanation in graph._decorator_explanations.values()
            for item in (*explanation.selected, *explanation.rejected)
            if item.template is not None
        ]
        assert any("template-target-not-selected" in item.reason_codes for item in decisions)
        assert any(item.template.target_bindings for item in decisions)
        result.to_text()
        graph.manifest(all_roots=True).to_json()
        graph.selection_census().to_dict()
        runtime = result.create_runtime()
        assert runtime.resolve(Dispatcher).targets["chosen"]().inner.payload == 42
        assert calls == before
    for component, before in snapshots:
        assert facts(component) == before


def test_provenance_uses_declaration_directory_and_line_after_cwd_changes(monkeypatch, tmp_path):
    source = ContainerBuilder().set_provider_roots(())
    directory = os.getcwd()
    line = __import__("sys")._getframe().f_lineno + 1
    identity = source.register(Resource)
    origin = source._registration_origins[identity]
    assert type(origin) is compiler._DeclarationOrigin
    assert type(origin.location) is compiler._SourceReference
    monkeypatch.chdir(tmp_path)
    with source.verify() as result:
        captured = next(
            origin for origin in present(result.graph)._occurrence_origins.values() if origin.definition_id == identity
        )
        assert type(captured) is compiler.DefinitionOrigin
        assert present(captured.location).line == line
        assert present(captured.location).path == os.path.relpath(__file__, directory).replace(os.sep, "/")
        assert (
            present(captured.location).symbol == "test_provenance_uses_declaration_directory_and_line_after_cwd_changes"
        )


def test_unavailable_cwd_does_not_prevent_declaration_or_build(monkeypatch):
    def unavailable():
        raise FileNotFoundError("directory was removed")

    monkeypatch.setattr(compiler.os, "getcwd", unavailable)
    source = ContainerBuilder().set_provider_roots(())
    identity = source.register(Resource)
    captured = source._registration_origins[identity]
    assert isinstance(captured.location, compiler._SourceReference)
    assert captured.location.directory is None
    location = compiler._origin_evidence(captured).location
    assert location is not None and location.path == Path(__file__).name
    forbid_evidence(monkeypatch)
    with source.build() as runtime:
        assert isinstance(runtime.resolve(Resource), Resource)


def test_declaration_provenance_never_retains_caller_frames():
    class Owner:
        pass

    source = ContainerBuilder().set_provider_roots(())

    def declare():
        owner = Owner()
        source.register(Resource)
        return weakref.ref(owner)

    owner = declare()
    gc.collect()
    assert owner() is None
    with source.verify() as result:
        assert result.is_valid


@pytest.mark.parametrize("failure", ["missing", "cycle", "filter", "private", "warmup"])
def test_failed_build_does_not_construct_evidence(monkeypatch, failure):
    forbid_evidence(monkeypatch)
    source = ContainerBuilder().set_provider_roots(())
    if failure == "cycle":

        class Recursive:
            pass

        setattr(Recursive, "__init__", lambda self, other: None)
        Recursive.__init__.__annotations__ = {"other": Recursive}
        source.register(Recursive)
    elif failure == "filter":
        source.register(Resource, when=lambda _: bool(1 / 0))
    elif failure == "warmup":
        source.add_warmup_plan(WarmupPlan("start", (WarmupTarget(Resource),)))
    else:
        source.register(Source)
        if failure == "private":
            source.create_boundary("hidden").register(Resource)
    with pytest.raises(ContainerBuildError) as caught:
        source.build()
    assert caught.value.report is None
    assert caught.value.evidence == ()


def test_empty_provider_collections_survive_rejected_non_early_root_without_candidate_records(monkeypatch):
    forbid_evidence(monkeypatch)
    source = ContainerBuilder()
    source.register(Resource, when=lambda component: bool(component.dependencies))
    with source.build() as runtime:
        assert runtime.resolve(Provider[list[Resource]])() == []


def test_scope_build_needs_no_origin_or_explanation_clone_tables(monkeypatch):
    source = ContainerBuilder().set_provider_roots(())
    source.register(Resource, lifespan="singleton")
    with source.verify() as analysis:
        parent = analysis.create_runtime()
        child = ScopeBuilder(parent, composition=present(analysis.composition)).set_provider_roots(())
        child.register(Source)
        forbid_evidence(monkeypatch)
        with child.build() as runtime:
            assert runtime.resolve(Source).resource is parent.resolve(Resource)


def test_rule_findings_keep_exact_occurrence_provenance():
    source = ContainerBuilder().set_provider_roots(())
    line = __import__("sys")._getframe().f_lineno + 1
    identity = source.register(Resource)
    captured = []

    def rule(context):
        visit = next(item for item in context.graph.walk() if item.component.id == identity)
        captured.append(context.graph._occurrence_origins[visit.component.occurrence_id])
        return (visit.issue("located", "Exact registration location"),)

    source.add_validation_rule(rule)
    with source.verify() as result:
        finding = next(issue for issue in result.issues if issue.code == "located")
        assert finding._origin is captured[0]
        assert finding._origin.kind == "registration"
        assert finding._origin.location.line == line


def test_discovery_with_budget_never_formats_callback_descriptions(monkeypatch):
    class Base:
        pass

    class Discovered(Base):
        pass

    forbid_evidence(monkeypatch)
    source = ContainerBuilder().set_provider_roots(())
    source.register_subclasses(Base, subclass_type_filter=lambda cls: cls is Discovered)
    with source.build(budget=CompilationBudget(preparation_operations=1000)) as runtime:
        assert isinstance(runtime.resolve(Base), Discovered)


def test_pattern_factory_binding_and_derived_values_need_no_diagnostic_labels(monkeypatch):
    from clean_ioc import generic_arg

    class Box(Generic[T]):
        def __init__(self, payload):
            self.payload = payload

    def factory(payload: type):
        return Box(payload)

    class Consumer:
        def __init__(self, box: Box[list[int]]):
            self.box = box

    forbid_evidence(monkeypatch)
    monkeypatch.setattr(compiler, "_generic_binding_label", forbid)
    source = ContainerBuilder().set_provider_roots(())
    source.register_pattern(Box[list[T]], factory=factory, arguments={"payload": generic_arg(T)})
    source.register(Consumer)
    with source.build() as runtime:
        assert runtime.resolve(Consumer).box.payload == list[int]


def test_nested_verify_callback_can_build_without_inheriting_capture(monkeypatch):
    calls = []

    def rule(context):
        with monkeypatch.context() as nested_patch:
            forbid_evidence(nested_patch)
            source = ContainerBuilder().set_provider_roots(())
            source.register(Resource)
            source.add_validation_rule(forbid)
            with source.build() as runtime:
                calls.append(type(runtime.resolve(Resource)))
        return ()

    source = ContainerBuilder().set_provider_roots(())
    source.register(Resource)
    source.add_validation_rule(rule)
    with source.verify() as result:
        assert result.is_valid
        assert calls == [Resource]


def test_runtime_provider_boundary_facts_match_analysis_without_origin_index():
    def create():
        source = ContainerBuilder()
        boundary = source.create_boundary("private", exposes=(Expose(Resource),))
        boundary.register(Resource)
        return source

    with create().build() as runtime, create().verify() as analysis:
        for plan in (runtime._plan, analysis._runtime._plan):
            provider = plan.provider_roots[Provider[Resource]][0].component
            assert provider.boundary == "private"
            assert provider.dependencies[0].boundary == "private"


def test_source_compilers_share_immutable_absent_evidence_tables(monkeypatch):
    original = compiler._Compiler.__init__
    phases = []

    def inspect_capture(self, *args, **kwargs):
        original(self, *args, **kwargs)
        assert not self._capture_evidence
        phases.append(self._profile_phase)
        for name in (
            "origins",
            "root_candidates",
            "occurrence_explanations",
            "decorator_explanations",
            "parameter_explanations",
            "generic_explanations",
            "_factory_pattern_bindings",
            "_specialized_dependency_annotations",
            "_partial_candidate_labels",
            "_factory_result_types",
        ):
            assert getattr(self, name) is compiler._EMPTY_EVIDENCE
        for name in ("decision_history", "_partial_edges", "_partial_declaration_edges", "_partial_candidates"):
            assert getattr(self, name) == ()

    monkeypatch.setattr(compiler._Compiler, "__init__", inspect_capture)
    with complex_builder([], []).build():
        pass
    assert {"primary compilation", "boundary preparation", "decorator-template expansion"} <= set(phases)


def test_pattern_dependency_substitutions_are_preserved_without_explanation_tuples(monkeypatch):
    class Box(Generic[T]):
        def __init__(self, item):
            self.item = item

    def nested(child: Box[T]) -> Box[list[T]]:
        return Box([child.item])

    class Consumer:
        def __init__(self, box: Box[list[list[int]]]):
            self.box = box

    forbid_evidence(monkeypatch)
    source = ContainerBuilder().set_provider_roots(())
    source.register(Box[int], instance=Box(4))
    source.register_pattern(Box[list[T]], factory=nested)
    source.register(Consumer)
    with source.build() as runtime:
        assert runtime.resolve(Consumer).box.item == [[4]]


def test_fallback_selection_has_no_diagnostic_fallback_index(monkeypatch):
    class Contract(Generic[T]):
        pass

    class Fallback(Contract[T]):
        def __init__(self, resource: Resource):
            self.resource = resource

    class Consumer:
        def __init__(self, dependency: Contract[int]):
            self.dependency = dependency

    forbid_evidence(monkeypatch)
    source = ContainerBuilder().set_provider_roots(())
    source.register(Resource)
    source.register_fallback(Contract, Fallback)
    source.register(Consumer)
    with source.build() as runtime:
        dependency = runtime.resolve(Consumer).dependency
        assert isinstance(dependency, Fallback)
        assert isinstance(dependency.resource, Resource)


def test_entrypoint_and_registration_share_original_source_capture():
    source = ContainerBuilder().set_provider_roots(())
    identity = source.register(Resource, root_policy="entrypoint")
    assert source._entrypoints[0].origin.location is source._registration_origins[identity].location
    with source.verify() as result:
        assert result.is_valid
