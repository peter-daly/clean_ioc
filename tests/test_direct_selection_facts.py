"""Direct fact capture preserves public mode execution and captured evidence."""

import gc
import weakref
from collections import defaultdict

import pytest

from clean_ioc import (
    ContainerBuilder,
    ContainerBuildError,
    DecoratorTemplate,
    DerivedServices,
    Expose,
    ServiceGroup,
    VerificationReport,
)
from clean_ioc.container import _Compiler
from clean_ioc.tooling import _RemappedDecoratorExplanation


class Source:
    pass


class Target:
    pass


class Wrapper(Target):
    def __init__(self, inner: Target):
        self.inner = inner


class Consumer:
    def __init__(self, first: Target, second: Target, source: Source, other_source: Source):
        self.first, self.second = first, second


@pytest.mark.parametrize("mode,rich", [("run", False), ("run", True), ("analysis", False)])
@pytest.mark.parametrize("boundary", [False, True])
@pytest.mark.parametrize("derived", [False, True])
def test_direct_facts_preserve_occurrences_callbacks_and_escaped_snapshots(mode, rich, boundary, derived, monkeypatch):
    captured, compiler_refs, saved, calls = [], [], [], defaultdict(int)
    original = _Compiler._compile_decorators

    def capture(compiler, registration, layer, core):
        compiler_refs.append(weakref.ref(compiler))
        result = original(compiler, registration, layer, core)
        target_occurrence_id = core.occurrence_id
        explanation = compiler.decorator_explanations.get(target_occurrence_id)
        if explanation is None:
            return result
        materialized = (
            explanation.materialize() if isinstance(explanation, _RemappedDecoratorExplanation) else explanation
        )
        for decision in (*materialized.selected, *materialized.rejected):
            if decision.template is not None:
                assert decision.template.target_occurrence_id == target_occurrence_id
        captured.append((id(compiler_refs[-1]), compiler._diagnostics, explanation, materialized))
        return result

    monkeypatch.setattr(_Compiler, "_compile_decorators", capture)
    builder = ContainerBuilder().set_provider_roots(())
    declaration = builder.create_boundary("private", exposes=(Expose(Consumer),)) if boundary else builder
    source_id = declaration.register(Source, lifespan="transient")
    group = ServiceGroup("target", service_type=Target)
    target_id = declaration.register(Target, groups=[group], lifespan="transient")
    declaration.register(Consumer)

    def when(component):
        calls["when"] += 1
        return True

    def position(decorator, target):
        calls["position"] += 1
        assert decorator.implementation is Wrapper
        assert target.service_type is Target
        return 4

    def template(source):
        calls["factory"] += 1
        assert source.id == source_id
        return DecoratorTemplate(DerivedServices(Target) if derived else group, Wrapper, when=when, position=position)

    template_id = declaration.register_decorator_template(for_each=Source, template=template)

    def rule(context):
        graph = context.graph
        assert graph.diagnostics_enabled
        saved.append(graph)
        before = dict(calls)
        for visit in graph.walk():
            if graph._component_evidence(graph._decorator_explanations, visit.component) is None:
                continue
            first = graph.explain_decorators(visit.component)
            assert graph.explain_decorators(visit.component) == first
        assert dict(calls) == before
        return ()

    if rich:
        declaration.add_validation_rule(rule)
    analysis = builder.verify() if mode == "analysis" else None
    runtime = analysis.create_runtime() if analysis is not None else builder.build()
    before = dict(calls)
    resolved = runtime.resolve(Consumer)
    assert isinstance(resolved.first, Wrapper)
    assert isinstance(resolved.second, Wrapper)
    assert resolved.first is not resolved.second
    assert dict(calls) == before
    assert calls["factory"] == 1
    assert calls["when"] == calls["position"] > 0
    facts = [
        decision.template for _, _, _, explanation in captured for decision in explanation.selected if decision.template
    ]
    if mode == "analysis":
        assert facts
        assert all(
            fact.source_registration_id == source_id and fact.target_registration_id == target_id for fact in facts
        )
        assert all(
            fact.template_id == template_id and fact.boundary == ("private" if boundary else None) for fact in facts
        )
        if rich:
            assert all(graph.explain_metadata_enabled for graph in saved)
    else:
        assert captured == []
        assert saved == []
        assert not hasattr(runtime, "graph")
    gc.collect()
    assert all(reference() is None for reference in compiler_refs)
    runtime.__exit__(None, None, None)


@pytest.mark.parametrize("mode", ["run", "analysis"])
def test_template_callback_failure_keeps_original_identity_and_safe_path(mode):
    builder = ContainerBuilder().set_provider_roots(())
    source_id = builder.register(Source)
    target_id = builder.register(Target)
    calls = []

    def fail(component):
        calls.append(component.id)
        raise RuntimeError("private-callback-text")

    template_id = builder.register_decorator_template(
        for_each=Source,
        template=lambda _: DecoratorTemplate(DerivedServices(Target), Wrapper, when=fail),
    )
    if mode == "run":
        with pytest.raises(ContainerBuildError) as raised:
            builder.build()
        issue = raised.value
        assert issue.report is issue.partial_graph is None
        assert calls == [target_id]
        text = str(issue)
    else:
        result = builder.verify()
        assert not result.is_valid
        issue = result.errors[0]
        text = result.to_text()
    assert issue.code == "decorator-filter-failed"
    assert all(identity in issue.path for identity in (template_id, source_id, target_id))
    assert "private-callback-text" not in text


@pytest.mark.parametrize("mode", ["run", "analysis"])
def test_stateful_filter_results_and_descriptions_are_captured_each_time(mode, monkeypatch):
    class Filter:
        def __init__(self):
            self.calls = 0
            self.__clean_ioc_description__ = "initial"

        def __call__(self, component):
            self.calls += 1
            self.__clean_ioc_description__ = f"pass-{self.calls}"
            return bool(self.calls % 2)

        def __hash__(self):
            pytest.fail("Fact interning hashed an application callback")

        def __eq__(self, other):
            pytest.fail("Fact interning compared an application callback")

    predicate = Filter()
    reasons = []
    original = _Compiler._compile_decorators

    def capture(compiler, registration, layer, core):
        result = original(compiler, registration, layer, core)
        explanation = compiler.decorator_explanations.get(core.occurrence_id)
        if explanation is None:
            return result
        for decision in (*explanation.selected, *explanation.rejected):
            if decision.reason_codes in (("decorator-filter-matched",), ("decorator-filter-rejected",)):
                reasons.append(decision.reason)
        return result

    monkeypatch.setattr(_Compiler, "_compile_decorators", capture)
    builder = ContainerBuilder().set_provider_roots(())
    builder.register(Source)
    builder.register(Target)
    builder.register(Consumer)
    builder.register_decorator_template(
        for_each=Source,
        template=lambda _: DecoratorTemplate(DerivedServices(Target), Wrapper, when=predicate),
    )
    with builder.verify() if mode == "analysis" else builder.build():
        assert predicate.calls > 1
        if mode == "run":
            assert reasons == []
            return
        assert reasons == [
            f"Decorator filter pass-{number} returned {'true' if number % 2 else 'false'}"
            for number in range(1, predicate.calls + 1)
        ]


@pytest.mark.parametrize("mode", ["run", "analysis"])
def test_direct_facts_keep_independent_generic_source_and_target_bindings(mode, monkeypatch):
    from typing import Generic, TypeVar

    SourceT = TypeVar("SourceT")
    TargetT = TypeVar("TargetT")

    class Backend(Source, Generic[SourceT]):
        pass

    class Operation(Generic[TargetT]):
        pass

    class Handler(Operation[int]):
        pass

    class GenericWrapper(Operation[TargetT], Generic[TargetT]):
        def __init__(self, inner: Operation[TargetT], source: Source):
            self.inner, self.source = inner, source

    facts = []
    original = _Compiler._compile_decorators

    def capture(compiler, registration, layer, core):
        result = original(compiler, registration, layer, core)
        explanation = compiler.decorator_explanations.get(core.occurrence_id)
        if explanation is None:
            return result
        view = explanation.materialize() if isinstance(explanation, _RemappedDecoratorExplanation) else explanation
        facts.extend(decision.template for decision in view.selected if decision.template)
        return result

    monkeypatch.setattr(_Compiler, "_compile_decorators", capture)
    builder = ContainerBuilder().set_provider_roots(())
    backend = Backend[str]()
    builder.register(Source, instance=backend)
    builder.register(Handler)
    builder.register_decorator_template(
        for_each=Source,
        template=lambda _: DecoratorTemplate(DerivedServices(Operation), GenericWrapper),
    )
    output = builder.verify() if mode == "analysis" else builder.build()
    with output:
        runtime = output.create_runtime() if isinstance(output, VerificationReport) else output
        resolved = runtime.resolve(Handler)
        assert isinstance(resolved, GenericWrapper)
        assert resolved.source is backend
        if mode == "run":
            assert facts == []
            return
        assert facts
        assert all(
            any(key.endswith("Backend.SourceT") and value == "str" for key, value in fact.source_bindings)
            for fact in facts
        )
        assert all(
            any(key.endswith("Operation.TargetT") and value == "int" for key, value in fact.target_bindings)
            for fact in facts
        )
        assert all(
            fact.projected_contract is not None and fact.projected_contract.endswith("Operation[int]") for fact in facts
        )
