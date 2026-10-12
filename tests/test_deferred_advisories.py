"""Lean finalization preserves selection and safety while deferring only reachability."""

import pytest

from clean_ioc import (
    BuildIssue,
    CompilationBudget,
    CompilationProfiler,
    ContainerBuilder,
    Expose,
    IssueSeverity,
    Provider,
    ScopeBuilder,
)
from clean_ioc import component_filters as cf
from clean_ioc.cli import main
from tests.verification_helpers import present


class Leaf:
    pass


class Root:
    def __init__(self, leaf: Leaf):
        self.leaf = leaf


class Unused:
    pass


class Wrapped(Root):
    def __init__(self, inner: Root):
        self.inner = inner


def builder():
    result = ContainerBuilder()
    result.register(Leaf)
    result.register(Root)
    result.register(Unused)
    result.mark_entrypoint(Root)
    return result


def test_completed_advisories_keep_exact_findings_without_replaying_callbacks(monkeypatch):
    eager = builder().set_provider_roots(()).verify()
    calls = []
    result = builder()

    def eligible(component):
        calls.append(component.service_type)
        return True

    result.register(str, instance="extra", when=eligible)
    result.mark_entrypoint(list[str], filter=eligible)
    result.set_provider_roots(())
    with result.verify() as analysis, analysis.create_runtime() as runtime:
        baseline = tuple(calls)
        assert analysis.warnings == eager.warnings
        assert not hasattr(runtime._plan, "unreachable_checked")
        root = next(root.component for root in analysis.graph.roots if root.requested_type is Root)
        assert analysis.graph.explain(root).selected[0].origin.layer == "root"
        assert analysis.graph.manifest(all_roots=True).fingerprint
        assert analysis.graph.to_text(all_roots=True)
        assert runtime.selected_registrations
        assert analysis.selection_census(all_roots=True)
        monkeypatch.setattr(ContainerBuilder, "verify", lambda *a, **kw: pytest.fail("unexpected compilation"))
        monkeypatch.setattr(Root, "__init__", lambda *a, **kw: pytest.fail("unexpected activation"))
        for _ in range(2):
            assert analysis.issues == eager.issues
            assert analysis.triage_report().report.issues == eager.issues
        assert tuple(calls) == baseline


def test_minimal_entrypoint_selection_preserves_fallbacks_providers_decorators_and_callback_counts():
    def run(diagnostics):
        calls = []
        result = ContainerBuilder()
        result.register(Leaf)
        result.register(Root, name="ordinary")
        result.register_fallback(Root, name="fallback")
        result.register(Root, name="excluded", when=lambda _: False)
        result.register_decorator(Root, Wrapped)

        def select(component):
            calls.append((component.name, component.service_type))
            return True

        result.mark_entrypoint(list[Root], filter=select)
        result.mark_entrypoint(Provider[Root], filter=select)
        # A narrower request must still select fallback when ordinary is filtered out.
        result.mark_entrypoint(Root, filter=cf.with_name("fallback"))
        result.set_provider_roots(())
        with result.verify() as scope_analysis, scope_analysis.create_runtime() as scope:
            names = tuple(root.component.name for root in present(scope_analysis.graph).entrypoints)
            assert names == ("ordinary", "ordinary", "fallback")
            assert isinstance(scope.resolve(Root, filter=cf.with_name("ordinary")), Wrapped)
            fallback = next(
                root.component
                for root in present(scope_analysis.graph).entrypoints
                if root.component.name == "fallback"
            )
            assert "selected-fallback" in present(scope_analysis.graph).explain(fallback).selected[0].reason_codes
            assert present(scope_analysis.graph).explain_decorators(fallback).selected
            manifest = present(scope_analysis.graph).manifest(all_roots=True).fingerprint
            if diagnostics:
                assert present(scope_analysis.graph)._known_root_selections
                assert present(scope_analysis.graph)._census_root_selections
                assert present(scope_analysis.graph).explain(Root, filter=select).rejected
            else:
                assert present(scope_analysis.graph).explain(Root, filter=select).rejected
            return calls, manifest

    plain, rich = run(False), run(True)
    assert plain == rich
    assert len(plain[0]) == 4


@pytest.mark.parametrize("diagnostics", [False, True])
def test_boundary_selection_and_contracts_survive_deferred_compact_overlay(diagnostics):
    parent = ContainerBuilder()
    parent.register(Leaf, lifespan="singleton")
    parent.mark_entrypoint(Leaf)
    parent.set_provider_roots(())
    container_composition = parent.retain_composition()
    with parent.build() as container:
        overlay = ScopeBuilder(container, composition=container_composition)
        boundary = overlay.create_boundary("internal", exposes=[Expose(Root)])
        boundary.register(Leaf)
        boundary.register(Root)
        boundary.register(Unused)
        boundary.mark_entrypoint(Root)
        overlay.set_provider_roots(())
        with overlay.verify() as child_analysis, child_analysis.create_runtime() as child:
            assert any(issue.code == "unreachable-component" for issue in child_analysis.warnings)
            assert present(child_analysis.graph).boundaries[0]["name"] == "internal"
            assert present(child_analysis.graph).boundaries[0]["exposures"]
            assert any(root.boundary == "internal" for root in present(child_analysis.graph).entrypoints)
            assert isinstance(child.resolve(Root).leaf, Leaf)
            assert child.resolve(Leaf) is container.resolve(Leaf)
            if diagnostics:
                assert any(area == "internal" for area, _ in present(child_analysis.graph)._census_root_selections)
            else:
                assert present(child_analysis.graph)._known_root_selections
                assert present(child_analysis.graph)._census_root_selections


@pytest.mark.parametrize("value", [None, 0, 1, "yes"])
def test_check_unreachable_rejects_non_bool_without_consuming_or_starting_profile(value):
    result = builder()
    profile = CompilationProfiler()
    with pytest.raises(TypeError, match="check_unreachable"):
        result.build(profile=profile, check_unreachable=value)
    assert not profile.report().spans
    scope_composition = result.retain_composition()
    with result.build() as scope:
        overlay = ScopeBuilder(scope, composition=scope_composition)
        with pytest.raises(TypeError, match="check_unreachable"):
            overlay.build(check_unreachable=value)  # ty: ignore[unknown-argument]  # Deliberately invalid input.
        overlay.build().__exit__()


@pytest.mark.parametrize("diagnostics", [False, True])
def test_entrypoint_callback_budget_and_prior_errors_are_never_deferred(diagnostics):
    result = ContainerBuilder()
    result.register(Leaf)
    result.mark_entrypoint(Unused)
    calls = []

    def select(component):
        calls.append(component.id)
        return True

    result.mark_entrypoint(Leaf, filter=select)
    result.set_provider_roots(())
    caught_analysis = result.verify(budget=CompilationBudget(preparation_operations=1))
    assert not caught_analysis.is_valid
    assert not calls
    assert caught_analysis is not None
    assert [issue.code for issue in caught_analysis.errors] == [
        "missing-entrypoint",
        "compilation-budget-exceeded",
    ]
    assert result._built


def test_build_skips_policies_and_analysis_completes_them_once():
    calls = []

    def safety(context):
        calls.append("policy")
        root = next(root.component for root in context.graph.roots if root.requested_type is Root)
        assert context.graph.explain(root).selected[0].origin.layer == "root"
        return (BuildIssue("application-safety", IssueSeverity.error, "Required application condition failed"),)

    execution = builder()
    execution.add_validation_rule(safety)
    with execution.build() as runtime:
        assert isinstance(runtime.resolve(Root), Root)
        assert calls == []
    analysis_builder = builder()
    analysis_builder.add_validation_rule(safety)
    result = analysis_builder.verify()
    assert any(issue.code == "application-safety" for issue in result.errors)
    assert calls == ["policy"]
    for _ in range(2):
        assert not result.is_valid
    assert calls == ["policy"]


def test_cli_strict_check_recovers_deferred_findings_from_existing_scope(monkeypatch, capsys):
    import clean_ioc.cli as cli

    composition_builder_227 = builder()
    composition_builder_227.set_provider_roots(())
    with composition_builder_227.verify() as scope_analysis, scope_analysis.create_runtime() as _scope:
        monkeypatch.setattr(cli, "_load_object", lambda _: scope_analysis)
        assert main(["check", "test:scope", "--strict"]) == 1
        assert "unreachable-component" in capsys.readouterr().out
        assert main(["check", "test:scope", "--strict", "--ignore", "unreachable-component"]) == 0
        assert scope_analysis.warnings


def test_analysis_preserves_equal_findings_from_distinct_rule_declarations():
    initial = builder()
    initial.set_provider_roots(())
    with initial.verify() as initial_analysis:
        advisory = initial_analysis.warnings[0]
    application_warning = BuildIssue("application-warning", IssueSeverity.warning, "Custom application advisory")
    validation_warning = BuildIssue("validation-warning", IssueSeverity.warning, "Custom validation advisory")
    calls = []

    def first_rule(_):
        calls.append("first")
        return application_warning, advisory, application_warning

    def second_rule(_):
        calls.append("second")
        return validation_warning, advisory

    composition = builder()
    composition.add_validation_rule(first_rule)
    composition.add_validation_rule(second_rule)
    composition.set_provider_roots(())
    with composition.verify() as analysis:
        report = analysis
        assert report.issues == (advisory, application_warning, advisory, validation_warning, advisory)
        # The same declaration's duplicate is removed, while each distinct source survives.
        assert len({issue._origin for issue in report.issues if issue == advisory}) == 3
        for _ in range(2):
            assert analysis is report
            analysis.triage_report()
            report.to_sarif()
        assert calls == ["first", "second"]
