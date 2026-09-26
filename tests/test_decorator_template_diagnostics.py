"""Captured, value-free explanations for registration-driven decorators."""

from dataclasses import FrozenInstanceError
from typing import Generic, TypeVar

import pytest
from typing_extensions import TypeAliasType

from clean_ioc import (
    ContainerBuilder,
    ContainerBuildError,
    DecoratorTemplate,
    DerivedServices,
    Expose,
    ServiceGroup,
    select,
)
from clean_ioc import component_filters as cf


class Source:
    pass


class Target:
    pass


class Wrapper(Target):
    def __init__(self, inner: Target, source: Source):
        self.inner, self.source = inner, source


def _roots(graph, service):
    return [root.component for root in graph.roots if root.requested_type is service]


def test_source_and_target_decisions_are_frozen_and_do_not_replay_callbacks():
    builder = ContainerBuilder()
    source_a = builder.register(Source, name="a")
    source_b = builder.register(Source, name="b")
    group = ServiceGroup("targets", service_type=Target)
    target_a = builder.register(Target, name="a", groups=[group])
    target_b = builder.register(Target, name="b", groups=[group])
    target_nonmember = builder.register(Target, name="nonmember")
    calls = {"source": 0, "when": 0, "factory": 0}
    inspect_started = False

    def source_filter(component):
        assert not inspect_started
        calls["source"] += 1
        return component.name == "a"

    def when(component):
        assert not inspect_started
        calls["when"] += 1
        return component.name == "a"

    def factory(source):
        assert not inspect_started
        calls["factory"] += 1
        return DecoratorTemplate(group, Wrapper, arguments={"source": select(cf.with_id(source.id))}, when=when)

    template_id = builder.register_decorator_template(for_each=Source, source_filter=source_filter, template=factory)
    graph = builder.build().graph
    before = dict(calls)
    before_manifest = graph.manifest(all_roots=True).to_json()
    inspect_started = True

    sources = graph.explain_template_sources(template_id)
    assert [(item.source_registration_id, item.selected) for item in sources] == [
        (source_a, True),
        (source_b, False),
    ]
    assert sources[0].generated_definition_id is not None
    assert sources[1].generated_definition_id is None
    assert sources[0].origin.definition_id == template_id
    assert source_a in sources[0].to_text()
    assert source_a in sources[0].to_json()
    with pytest.raises(FrozenInstanceError):
        sources[0].selected = False  # ty: ignore[invalid-assignment]

    decisions = {component.name: graph.explain_decorators(component) for component in _roots(graph, Target)}
    assert [item.template.target_registration_id for item in decisions["a"].selected if item.template] == [target_a]
    assert [item.template.target_registration_id for item in decisions["b"].rejected if item.template] == [target_b]
    assert [item.template.target_registration_id for item in decisions["nonmember"].rejected if item.template] == [
        target_nonmember
    ]
    assert decisions["nonmember"].rejected[0].reason_codes == ("template-target-not-selected",)
    selected = decisions["a"].selected[0]
    assert selected.template is not None
    assert selected.template.template_id == template_id
    assert selected.template.source_registration_id == source_a
    assert selected.template.generated_definition_id == sources[0].generated_definition_id
    target_component = next(item for item in _roots(graph, Target) if item.name == "a")
    assert selected.template.target_occurrence_id == target_component.occurrence_id
    assert selected.template.selector_kind == "service-group"
    assert selected.template.selector_contract.endswith("Target")
    assert "template" in selected.to_dict()
    assert graph.manifest(all_roots=True).to_json() == before_manifest
    assert calls == before


def test_generic_source_and_target_projections_remain_separate():
    SourceT = TypeVar("T")  # ty: ignore[mismatched-type-name]
    TargetT = TypeVar("T")  # ty: ignore[mismatched-type-name]

    class Backend(Source, Generic[SourceT]):
        pass

    class Operation(Generic[TargetT]):
        pass

    class Handler(Operation[int]):
        pass

    class GenericWrapper(Operation[TargetT], Generic[TargetT]):
        def __init__(self, inner: Operation[TargetT], source: Source):
            self.inner, self.source = inner, source

    builder = ContainerBuilder()
    builder.register(Source, instance=Backend[str]())
    builder.register(Handler)
    builder.register_decorator_template(
        for_each=Source,
        template=lambda source: DecoratorTemplate(
            DerivedServices(Operation),
            GenericWrapper,
            arguments={"source": select(cf.with_id(source.id))},
        ),
    )
    graph = builder.build().graph
    source_decision = graph.explain_template_sources()[0]
    assert any(key.endswith("Backend.T") and value == "str" for key, value in source_decision.source_bindings)
    handler = _roots(graph, Handler)[0]
    decision = graph.explain_decorators(handler).selected[0].template
    assert decision is not None
    assert decision.source_bindings == source_decision.source_bindings
    assert decision.projected_contract is not None and decision.projected_contract.endswith("Operation[int]")
    assert any(key.endswith("Operation.T") and value == "int" for key, value in decision.target_bindings)
    assert decision.selector_kind == "derived-services"
    assert "source bindings:" in graph.explain_decorators(handler).to_text()
    assert "target bindings:" in graph.explain_decorators(handler).to_text()


def test_independent_overlapping_policies_keep_both_identities():
    builder = ContainerBuilder()
    source = builder.register(Source)
    builder.register(Target)

    def factory(info):
        return DecoratorTemplate(DerivedServices(Target), Wrapper, arguments={"source": select(cf.with_id(info.id))})

    first = builder.register_decorator_template(for_each=Source, template=factory)
    second = builder.register_decorator_template(for_each=Source, template=factory)
    graph = builder.build().graph
    target = _roots(graph, Target)[0]
    decisions = graph.explain_decorators(target).selected
    assert {decision.template.template_id for decision in decisions if decision.template is not None} == {
        first,
        second,
    }
    assert all("template-policy-overlap" in decision.reason_codes for decision in decisions)
    assert all(
        decision.template is not None and decision.template.source_registration_id == source for decision in decisions
    )


def test_alias_target_label_survives_frozen_template_inspection():
    PublicTargetAlias = TypeAliasType("PublicTargetAlias", Target)  # noqa: N806
    builder = ContainerBuilder()
    builder.register(Source)
    builder.register(PublicTargetAlias)
    builder.register_decorator_template(
        for_each=Source,
        template=lambda source: DecoratorTemplate(
            DerivedServices(Target), Wrapper, arguments={"source": select(cf.with_id(source.id))}
        ),
    )
    graph = builder.build().graph
    target = _roots(graph, Target)[0]
    assert graph.explain_decorators(target).selected[0].template is not None
    assert "PublicTargetAlias" in graph.explain(PublicTargetAlias).subject


def test_private_boundary_facts_keep_declaration_and_target_context():
    ids = {}

    def private(builder):
        ids["source"] = builder.register(Source)
        builder.register(Target)
        ids["template"] = builder.register_decorator_template(
            for_each=Source,
            template=lambda source: DecoratorTemplate(
                DerivedServices(Target), Wrapper, arguments={"source": select(cf.with_id(source.id))}
            ),
        )

    builder = ContainerBuilder()
    builder.create_boundary("private", exposes=(Expose(Target),)).apply_bundle(private)
    graph = builder.build().graph
    sources = graph.explain_template_sources(ids["template"])
    assert len(sources) == 1
    assert sources[0].source_registration_id == ids["source"]
    assert sources[0].declaration_boundary == sources[0].source_boundary == "private"
    assert sources[0].origin.boundary == "private"
    target = _roots(graph, Target)[0]
    decision = graph.explain_decorators(target).selected[0].template
    assert decision is not None
    assert decision.boundary == "private"
    assert decision.template_id == ids["template"]


def test_anchored_overlay_relabels_target_occurrence_without_replaying_factory():
    builder = ContainerBuilder()
    source = builder.register(Source, lifespan="singleton")
    builder.register(Target, lifespan="singleton")
    calls = []
    builder.register_decorator_template(
        for_each=Source,
        template=lambda info: (
            calls.append(info.id),
            DecoratorTemplate(DerivedServices(Target), Wrapper, arguments={"source": select(cf.with_id(info.id))}),
        )[1],
    )
    container = builder.build()
    parent = _roots(container.graph, Target)[0]
    parent_fact = container.graph.explain_decorators(parent).selected[0].template
    overlay_builder = container.new_scope_builder()
    overlay_builder.register(Source, name="new-overlay-source", lifespan="singleton")
    overlay = overlay_builder.build()
    child = _roots(overlay.graph, Target)[0]
    child_fact = overlay.graph.explain_decorators(child).selected[0].template
    assert parent_fact is not None and child_fact is not None
    assert child_fact.template_id == parent_fact.template_id
    assert child_fact.source_registration_id == source
    assert child_fact.target_occurrence_id == child.occurrence_id
    decorator_fact = overlay.graph.explain(child.decorators[0]).selected[0].template
    assert decorator_fact is not None
    assert decorator_fact.target_occurrence_id == child.occurrence_id
    assert decorator_fact.template_id == parent_fact.template_id
    assert overlay.graph.explain(child).selected[0].origin.kind == "registration"
    assert overlay.graph.explain(child.decorators[0]).selected[0].origin.kind == "decorator-template"
    grandchild = overlay.new_scope_builder().build()
    grandchild_target = _roots(grandchild.graph, Target)[0]
    grandchild_decision = grandchild.graph.explain_decorators(grandchild_target).selected[0]
    grandchild_wrapper_decision = grandchild.graph.explain(grandchild_target.decorators[0]).selected[0]
    assert grandchild_decision.template is not None
    assert grandchild_wrapper_decision.template is not None
    assert grandchild_decision.template.template_id == parent_fact.template_id
    assert grandchild_wrapper_decision.template.template_id == parent_fact.template_id
    assert grandchild_decision.template.target_occurrence_id == grandchild_target.occurrence_id
    assert grandchild_wrapper_decision.template.target_occurrence_id == grandchild_target.occurrence_id
    assert grandchild_decision.origin.kind == grandchild_wrapper_decision.origin.kind == "decorator-template"
    assert grandchild.graph.explain(grandchild_target).selected[0].origin.kind == "registration"
    assert calls.count(source) == 3


def test_failure_keeps_context_without_exception_or_argument_secrets():
    class Secret:
        def __repr__(self):
            raise AssertionError("secret representation must not be read")

    builder = ContainerBuilder()
    source = builder.register(Source)
    target = builder.register(Target)
    secret = Secret()

    def broken_filter(_):
        raise RuntimeError("private-filter-value")

    template = builder.register_decorator_template(
        for_each=Source,
        template=lambda _: DecoratorTemplate(
            DerivedServices(Target), Wrapper, arguments={"unused": secret}, when=broken_filter
        ),
    )
    with pytest.raises(ContainerBuildError) as caught:
        builder.build()
    assert caught.value.report is not None
    assert caught.value.partial_graph is not None
    issue = caught.value.report.errors[0]
    assert issue.code == "decorator-filter-failed"
    assert all(item in issue.path for item in (template, source, target))
    assert "Target" in issue.message
    output = caught.value.report.to_json() + "\n" + caught.value.partial_graph.to_json()
    assert "private-filter-value" not in output
    assert "Secret" not in output
    assert "unused" not in output


@pytest.mark.parametrize("phase", ["filter", "factory"])
def test_pregraph_expansion_failure_identifies_phase_and_source(phase):
    builder = ContainerBuilder()
    source = builder.register(Source)

    def source_filter(_):
        if phase == "filter":
            raise RuntimeError("private-source-filter-secret")
        return True

    def factory(_):
        raise RuntimeError("private-factory-secret")

    template = builder.register_decorator_template(for_each=Source, source_filter=source_filter, template=factory)
    with pytest.raises(ContainerBuildError) as caught:
        builder.build()
    assert caught.value.report is not None
    assert caught.value.partial_graph is not None
    issue = caught.value.report.errors[0]
    assert issue.code == "template-expansion"
    assert issue.path[:2] == (template, source)
    assert ("Source filter" if phase == "filter" else "Template factory") in issue.message
    assert caught.value.partial_graph.attempts[0].witness_path[:2] == (template, source)
    assert "private-" not in caught.value.report.to_json()


def test_hostile_decorator_signature_error_never_formats_exception_text():
    class HostileError(RuntimeError):
        def __str__(self):
            raise AssertionError("hostile __str__ was called")

    class HostileMeta(type):
        @property
        def __signature__(cls):
            raise HostileError("private-signature-secret")

    class HostileWrapper(Target, metaclass=HostileMeta):
        def __init__(self, inner: Target):
            self.inner = inner

    builder = ContainerBuilder()
    source = builder.register(Source)
    target = builder.register(Target)
    template = builder.register_decorator_template(
        for_each=Source,
        template=lambda _: DecoratorTemplate(DerivedServices(Target), HostileWrapper),
    )
    with pytest.raises(ContainerBuildError) as caught:
        builder.build()
    assert caught.value.report is not None
    assert caught.value.partial_graph is not None
    issue = caught.value.report.errors[0]
    assert issue.code == "invalid-decorator"
    assert template in issue.path and source in issue.path and target in issue.path
    output = caught.value.report.to_json() + caught.value.partial_graph.to_json()
    assert "private-signature-secret" not in output
    assert "hostile __str__" not in output
    assert "HostileError" in issue.message


@pytest.mark.parametrize("phase", ["filter", "factory"])
def test_callback_container_build_error_cannot_supply_report_code_or_path(phase):
    builder = ContainerBuilder()
    source = builder.register(Source)

    def source_filter(_):
        if phase == "filter":
            raise ContainerBuildError("private-message", code="private-code", path=("private-path",))
        return True

    def factory(_):
        raise ContainerBuildError("private-message", code="private-code", path=("private-path",))

    template = builder.register_decorator_template(for_each=Source, source_filter=source_filter, template=factory)
    with pytest.raises(ContainerBuildError) as caught:
        builder.build()
    assert caught.value.report is not None
    assert caught.value.partial_graph is not None
    issue = caught.value.report.errors[0]
    assert issue.code == "template-expansion"
    assert issue.path == (template, source)
    output = caught.value.report.to_json() + caught.value.partial_graph.to_json()
    assert "private-" not in output


def test_clone_explanations_follow_growing_and_sibling_occurrence_mappings():
    from dataclasses import replace

    from clean_ioc.container import _ExplanationCloneContext

    builder = ContainerBuilder()
    builder.register(Source)
    builder.register(Target)
    builder.register_decorator_template(
        for_each=Source,
        template=lambda info: DecoratorTemplate(
            DerivedServices(Target), Wrapper, arguments={"source": select(cf.with_id(info.id))}
        ),
    )
    with builder.build() as container:
        graph = container.graph
        target = _roots(graph, Target)[0]
        source = _roots(graph, Source)[0]
        explanation = graph.explain_decorators(target)
        # Include both selected and rejected facts so every target participates
        # in the key, including a target not yet encountered during traversal.
        rejected = graph.explain_decorators(source).rejected
        explanation = replace(explanation, rejected=rejected)
        context = _ExplanationCloneContext()
        mapping = {}
        assert context.remap(explanation, mapping) is explanation
        mapping[target.occurrence_id] = source
        first = context.remap(explanation, mapping)
        assert first.selected[0].template is not None
        assert first.rejected[0].template is not None
        assert first.selected[0].template.target_occurrence_id == source.occurrence_id
        assert first.rejected[0].template.target_occurrence_id == source.occurrence_id
        assert context.remap(explanation, dict(mapping)) is first
        mapping[source.occurrence_id] = target
        second = context.remap(explanation, mapping)
        assert second is not first
        assert second.rejected[0].template is not None
        assert second.rejected[0].template.target_occurrence_id == target.occurrence_id
        assert first.rejected[0].template.target_occurrence_id == source.occurrence_id
        # A sibling clone has a separate mapping even when the source facts match.
        assert context.remap(explanation, {}) is explanation
        other_explanation = replace(explanation, subject="other graph")
        assert context.remap(other_explanation, mapping).subject == "other graph"
        ordinary = graph.explain(target)
        assert context.remap(ordinary, mapping) is ordinary
