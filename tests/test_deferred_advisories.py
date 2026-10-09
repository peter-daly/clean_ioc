"""Lean finalization preserves selection and safety while deferring only reachability."""

from typing import Any, cast

import pytest

from clean_ioc import (
    BuildIssue,
    CompilationBudget,
    CompilationProfiler,
    ContainerBuilder,
    ContainerBuildError,
    Expose,
    IssueSeverity,
    Provider,
)
from clean_ioc import component_filters as cf
from clean_ioc.cli import main


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


@pytest.mark.parametrize("diagnostics", [False, True])
@pytest.mark.parametrize("compact", [False, True])
def test_deferred_advisories_recover_exact_findings_without_replaying_callbacks(diagnostics, compact, monkeypatch):
    calls = []
    eager = builder().build(diagnostics=diagnostics, provider_roots=())
    result = builder()

    def eligible(component):
        calls.append(component.service_type)
        return True

    result.register(str, instance="extra", when=eligible)
    result.mark_entrypoint(list[str], filter=eligible)
    with result.build(
        check_unreachable=False, diagnostics=diagnostics, provider_roots=(), allow_scope_builders=not compact
    ) as scope:
        baseline = tuple(calls)
        assert scope.build_report.warnings == ()
        assert scope._plan.unreachable_checked is False
        assert scope.allow_scope_builders is not compact
        root = next(root.component for root in scope.graph.roots if root.requested_type is Root)
        assert scope.graph.explain(root).selected[0].origin.layer == "root"
        assert scope.graph.manifest(all_roots=True).fingerprint
        assert scope.graph.to_text(all_roots=True)
        assert scope.selected_registrations
        if diagnostics:
            assert scope.graph.selection_census(all_roots=True)
        else:
            assert not scope.graph._known_root_selections
            assert not scope.graph._census_root_selections
        monkeypatch.setattr(ContainerBuilder, "build", lambda *a, **kw: pytest.fail("unexpected compilation"))
        monkeypatch.setattr(Root, "__init__", lambda *a, **kw: pytest.fail("unexpected activation"))
        for checked in (scope, scope.new_scope()):
            assert checked.validation_report().issues == eager.validation_report().issues
            assert checked.validation_report().issues == eager.build_report.issues
        assert tuple(calls) == baseline
        assert scope.build_report.warnings == ()
    eager.__exit__()


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
        with result.build(diagnostics=diagnostics, provider_roots=(), check_unreachable=False) as scope:
            names = tuple(root.component.name for root in scope.graph.entrypoints)
            assert names == ("ordinary", "ordinary", "fallback")
            assert isinstance(scope.resolve(Root, filter=cf.with_name("ordinary")), Wrapped)
            fallback = next(root.component for root in scope.graph.entrypoints if root.component.name == "fallback")
            assert "selected-fallback" in scope.graph.explain(fallback).selected[0].reason_codes
            assert scope.graph.explain_decorators(fallback).selected
            manifest = scope.graph.manifest(all_roots=True).fingerprint
            if diagnostics:
                assert scope.graph._known_root_selections
                assert scope.graph._census_root_selections
                assert scope.graph.explain(Root, filter=select).rejected
            else:
                assert not scope.graph._known_root_selections
                assert not scope.graph._census_root_selections
                with pytest.raises(ValueError, match="diagnostics-disabled"):
                    scope.graph.explain(Root, filter=select)
            return calls, manifest

    plain, rich = run(False), run(True)
    assert plain == rich
    assert len(plain[0]) == 4


@pytest.mark.parametrize("diagnostics", [False, True])
def test_boundary_selection_and_contracts_survive_deferred_compact_overlay(diagnostics):
    parent = ContainerBuilder()
    parent.register(Leaf, lifespan="singleton")
    parent.mark_entrypoint(Leaf)
    with parent.build(provider_roots=()) as container:
        overlay = container.new_scope_builder()
        boundary = overlay.create_boundary("internal", exposes=[Expose(Root)])
        boundary.register(Leaf)
        boundary.register(Root)
        boundary.register(Unused)
        boundary.mark_entrypoint(Root)
        with overlay.build(
            check_unreachable=False, diagnostics=diagnostics, provider_roots=(), allow_scope_builders=False
        ) as child:
            assert child.build_report.warnings == ()
            assert any(issue.code == "unreachable-component" for issue in child.validation_report().warnings)
            assert child.graph.boundaries[0]["name"] == "internal"
            assert child.graph.boundaries[0]["exposures"]
            assert any(root.boundary == "internal" for root in child.graph.entrypoints)
            assert isinstance(child.resolve(Root).leaf, Leaf)
            assert child.resolve(Leaf) is container.resolve(Leaf)
            if diagnostics:
                assert any(area == "internal" for area, _ in child.graph._census_root_selections)
            else:
                assert not child.graph._known_root_selections
                assert not child.graph._census_root_selections


@pytest.mark.parametrize("value", [None, 0, 1, "yes"])
def test_check_unreachable_rejects_non_bool_without_consuming_or_starting_profile(value):
    result = builder()
    profile = CompilationProfiler()
    with pytest.raises(TypeError, match="check_unreachable must be a bool"):
        result.build(check_unreachable=cast(Any, value), profile=profile)
    assert not profile.report().spans
    with result.build() as scope:
        overlay = scope.new_scope_builder()
        with pytest.raises(TypeError, match="check_unreachable must be a bool"):
            overlay.build(check_unreachable=cast(Any, value))
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
    with pytest.raises(ContainerBuildError) as caught:
        result.build(
            check_unreachable=False,
            diagnostics=diagnostics,
            provider_roots=(),
            budget=CompilationBudget(preparation_operations=1),
        )
    assert not calls
    assert caught.value.report is not None
    assert [issue.code for issue in caught.value.report.errors] == ["missing-entrypoint", "compilation-budget-exceeded"]
    assert not result._built


@pytest.mark.parametrize("diagnostics", [False, True])
def test_custom_build_rules_still_fail_and_validation_rules_still_run_fresh(diagnostics):
    calls = []
    result = builder()

    def safety(context):
        calls.append("build")
        root = next(root.component for root in context.graph.roots if root.requested_type is Root)
        assert context.graph.explain(root).selected[0].origin.layer == "root"
        return (BuildIssue("application-safety", IssueSeverity.error, "Required application condition failed"),)

    result.add_validation_rule(safety)
    with pytest.raises(ContainerBuildError, match="application-safety"):
        result.build(check_unreachable=False, diagnostics=diagnostics, provider_roots=())
    assert calls == ["build"]
    assert not result._built
    result = builder()
    result.add_validation_rule(lambda _: calls.append("validation") or (), mode="validation")
    with result.build(check_unreachable=False, diagnostics=diagnostics, provider_roots=()) as scope:
        assert calls == ["build"]
        scope.validation_report()
        scope.validation_report()
        assert calls == ["build", "validation", "validation"]


def test_cli_strict_check_recovers_deferred_findings_from_existing_scope(monkeypatch, capsys):
    import clean_ioc.cli as cli

    with builder().build(check_unreachable=False, provider_roots=(), allow_scope_builders=False) as scope:
        monkeypatch.setattr(cli, "_load_object", lambda _: scope)
        assert main(["check", "test:scope", "--strict"]) == 1
        assert "unreachable-component" in capsys.readouterr().out
        assert main(["check", "test:scope", "--strict", "--ignore", "unreachable-component"]) == 0
        assert scope.build_report.warnings == ()


@pytest.mark.parametrize("diagnostics", [False, True])
def test_deferred_advisory_order_and_deduplication_match_eager_build_rule_findings(diagnostics):
    eager = builder().build(provider_roots=(), diagnostics=diagnostics)
    advisory = eager.build_report.warnings[0]
    eager.__exit__()
    application_warning = BuildIssue("application-warning", IssueSeverity.warning, "Custom build advisory")
    validation_warning = BuildIssue("validation-warning", IssueSeverity.warning, "Custom validation advisory")

    def run(check_unreachable):
        result = builder()
        # Duplicate pre-existing built-in findings and the deferred advisory.
        result.add_validation_rule(lambda _: (application_warning, advisory, application_warning))
        result.add_validation_rule(lambda _: (validation_warning, advisory), mode="validation")
        with result.build(
            check_unreachable=check_unreachable, diagnostics=diagnostics, provider_roots=(), allow_scope_builders=False
        ) as scope:
            return scope.validation_report().issues

    assert run(False) == run(True) == (advisory, application_warning, validation_warning)
