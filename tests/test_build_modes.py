"""The two public operations and their deliberately different capabilities."""

import inspect

import pytest

from clean_ioc import (
    BuilderAlreadyBuiltError,
    BuildIssue,
    BuildMatrix,
    BuildVariant,
    CompilationProfiler,
    ContainerBuilder,
    ContainerBuildError,
    IssueSeverity,
    Provider,
    ScopeBuilder,
)
from clean_ioc.cli import _load_analysis, main
from tests.verification_helpers import present


class Leaf:
    pass


class Service:
    def __init__(self, leaf: Leaf):
        self.leaf = leaf


def composition():
    builder = ContainerBuilder()
    builder.register(Leaf, lifespan="singleton", root_policy="dependency_only")
    builder.register(Service)
    return builder


def test_default_build_retains_execution_discovery_and_ordinary_scopes():
    with composition().build() as runtime:
        assert {item.implementation_type for item in runtime.selected_registrations} == {Leaf, Service}
        with runtime.new_scope() as child:
            assert child.selected_registrations is runtime.selected_registrations
            assert child.resolve(Service).leaf is runtime.resolve(Service).leaf
        for attribute in (
            "build_mode",
            "explain_metadata_enabled",
            "allow_scope_builders",
            "build_report",
            "validation_report",
            "graph",
            "new_scope_builder",
        ):
            assert not hasattr(runtime, attribute)
        with pytest.raises(TypeError, match="composition"):
            ScopeBuilder(runtime)  # ty: ignore[missing-argument]  # Deliberately invalid input.


@pytest.mark.parametrize("operation", ["build", "verify"])
@pytest.mark.parametrize(
    "option",
    [
        "mode",
        "diagnostics",
        "explain_metadata",
        "check_unreachable",
        "aggregate_errors",
        "clean_orphans",
        "allow_scope_builders",
        "provider_roots",
    ],
)
def test_removed_flags_leave_both_builders_and_profiler_untouched(operation, option):
    profile = CompilationProfiler()
    with composition().verify() as analysis:
        parent = analysis.create_runtime()
        for builder in (composition(), ScopeBuilder(parent, composition=present(analysis.composition))):
            method = getattr(builder, operation)
            with pytest.raises(TypeError, match=option):
                method(profile=profile, **{option: False})
            assert not builder._built
            assert not profile.report().spans
            assert option not in inspect.signature(method).parameters
            with builder.build() as child:
                assert isinstance(child.resolve(Service), Service)


@pytest.mark.parametrize("operation", ["build", "verify"])
def test_analysis_parent_supports_explicit_overlays_without_mutating_parent(operation):
    with composition().verify() as analysis:
        parent = analysis.create_runtime()
        original = parent.resolve(Service).leaf
        manifest = analysis.graph.manifest(all_roots=True).fingerprint
        builder = ScopeBuilder(parent, composition=present(analysis.composition))
        child_composition = builder.retain_composition()
        if operation == "verify":
            with builder.verify() as child_analysis:
                child = child_analysis.create_runtime()
                assert child.resolve(Service).leaf is original
                with ScopeBuilder(child, composition=present(child_analysis.composition)).build() as nested:
                    assert nested.resolve(Service).leaf is original
        else:
            with builder.build() as child:
                assert child.resolve(Service).leaf is original
                with ScopeBuilder(child, composition=child_composition).build() as nested:
                    assert nested.resolve(Service).leaf is original
        assert analysis.graph.manifest(all_roots=True).fingerprint == manifest


def test_provider_declarations_capture_replace_and_validate_without_changing_injection():
    builder = composition()
    values = [Provider[Service]]
    assert builder.set_provider_roots(values) is builder
    values.clear()
    with pytest.raises(TypeError, match="provider annotations"):
        builder.set_provider_roots([Service])
    with builder.build() as runtime:
        assert isinstance(runtime.resolve(Provider[Service])(), Service)
        with pytest.raises(BuilderAlreadyBuiltError):
            builder.set_provider_roots(None)
    builder = composition().set_provider_roots([Provider[Service]])
    builder.set_provider_roots(None).set_provider_roots(())
    handle = builder.retain_composition()
    with builder.build() as parent:
        assert not parent.has_component(Provider[Service])
        assert isinstance(parent.resolve(Service), Service)
        with ScopeBuilder(parent, composition=handle).build() as child:
            assert child.has_component(Provider[Service])
        with ScopeBuilder(parent, composition=handle).set_provider_roots(()).build() as child:
            assert not child.has_component(Provider[Service])


def test_analysis_validates_orphans_without_expanding_public_roots_or_discovery():
    class Orphan:
        pass

    def factory():
        builder = composition().set_provider_roots(())
        builder.register(Orphan, root_policy="dependency_only")
        return builder

    with factory().build() as production, factory().verify() as analysis:
        runtime = analysis.create_runtime()
        for owner in (production, runtime):
            assert not owner.has_component(Orphan)
            assert isinstance(owner.resolve(Service).leaf, Leaf)
            assert [item.implementation_type for item in owner.selected_registrations] == [Service, Leaf]
        assert any(visit.component.service_type is Orphan for visit in analysis.graph.walk())
        assert analysis.selection_census(all_roots=True)


def test_invalid_unused_orphan_is_an_analysis_only_failure():
    class Missing:
        pass

    class Orphan:
        def __init__(self, missing: Missing):
            pass

    def factory():
        builder = composition()
        builder.register(Orphan, root_policy="dependency_only")
        return builder

    with factory().build() as runtime:
        assert isinstance(runtime.resolve(Service), Service)
    builder = factory()
    with builder.verify() as analysis:
        assert not analysis.is_valid
        assert analysis.errors[0].code == "missing-component"
    assert builder._built


def test_all_rules_run_only_during_analysis_and_report_reads_never_replay():
    calls = []

    def factory():
        builder = composition()
        builder.add_validation_rule(lambda ctx: calls.append(len(tuple(ctx.graph.walk()))) or ())
        builder.add_validation_rule(lambda ctx: calls.append("second") or ())
        return builder

    with factory().build() as runtime:
        assert isinstance(runtime.resolve(Service), Service)
        assert calls == []
    with factory().verify() as analysis:
        assert analysis.is_valid
        assert calls[-1] == "second"
        captured = list(calls)
        analysis.to_json()
        analysis.to_sarif()
        analysis.selection_census()
        analysis.triage_report()
        analysis.create_runtime().resolve(Service)
        assert calls == captured


def test_rule_failure_consumes_analysis_builder_but_build_skips_rule():
    calls = []

    def factory():
        builder = composition()
        builder.add_validation_rule(
            lambda _: calls.append("rule") or (BuildIssue("denied", IssueSeverity.error, "Denied"),)
        )
        return builder

    builder = factory()
    result = builder.verify()
    assert not result.is_valid
    assert result.complete
    assert calls == ["rule"]
    with pytest.raises(BuilderAlreadyBuiltError):
        builder.build()
    with factory().build() as runtime:
        assert isinstance(runtime.resolve(Service), Service)
    assert calls == ["rule"]


def test_cli_and_matrix_each_run_validation_once(monkeypatch, capsys):
    calls = []

    def factory():
        builder = composition()
        builder.add_validation_rule(lambda _: calls.append("validation") or ())
        return builder

    monkeypatch.setattr("clean_ioc.cli._load_object", lambda _: factory)
    assert main(["check", "ignored:factory"]) == 0
    assert "valid" in capsys.readouterr().out
    assert calls == ["validation"]
    assert BuildMatrix([BuildVariant("one", factory)], reference="one").check().is_valid
    assert calls == ["validation", "validation"]


def test_cli_never_rebuilds_an_execution_runtime(monkeypatch):
    with composition().build() as runtime:
        monkeypatch.setattr("clean_ioc.cli._load_object", lambda _: runtime)
        with pytest.raises(TypeError, match="VerificationReport"):
            _load_analysis("ignored:runtime")


def test_impossible_binding_still_fails_execution_locally():
    builder = ContainerBuilder()
    builder.register(Service)
    with pytest.raises(ContainerBuildError) as raised:
        builder.build()
    assert raised.value.code == "missing-component"
    assert raised.value.report is None
    assert raised.value.partial_graph is None


@pytest.mark.parametrize("before_public,after_public", [(False, True), (True, False)])
def test_analysis_manifests_classify_public_root_promotion_and_demotion(before_public, after_public):
    from clean_ioc import ChangeRisk, GraphChangeKind, GraphManifest

    def graph(public):
        builder = ContainerBuilder().set_provider_roots(())
        builder.register(Leaf, root_policy="resolvable" if public else "dependency_only")
        builder.register(Service, root_policy="entrypoint")
        return builder.verify()

    with graph(before_public) as before, graph(after_public) as after:
        old = before.graph.manifest(all_roots=True)
        new = after.graph.manifest(all_roots=True)
        assert old.fingerprint != new.fingerprint
        assert GraphManifest.from_json(new.to_json()).fingerprint == new.fingerprint
        root = next(root for root in after.graph.roots if root.requested_type is Leaf)
        assert root.resolvable is after_public
        diff = after.graph.diff(old, all_roots=True)
        expected = GraphChangeKind.root_added if after_public else GraphChangeKind.root_removed
        change = next(change for change in diff.semantic_changes if change.kind is expected)
        assert change.fields == ("resolvable",)
        assert change.risk is (ChangeRisk.medium if after_public else ChangeRisk.high)
        assert {item.implementation_type for item in before.selected_registrations} == {Leaf, Service}
        assert {item.implementation_type for item in after.selected_registrations} == {Leaf, Service}
        assert before.is_valid
        assert after.is_valid


def test_manifest_resolvability_is_boolean_and_root_only():
    import copy

    from clean_ioc import GraphManifest

    with composition().set_provider_roots(()).verify() as runtime:
        data = runtime.graph.manifest(all_roots=True).to_dict()
        invalid_root = copy.deepcopy(data)
        invalid_root["roots"][0]["resolvable"] = "no"
        with pytest.raises(ValueError, match="resolvable must be a boolean"):
            GraphManifest.from_json(GraphManifest(invalid_root).to_json())
        invalid_child = copy.deepcopy(data)
        invalid_child["roots"][0]["dependencies"][0]["resolvable"] = False
        with pytest.raises(ValueError, match="resolvable is only valid on root nodes"):
            GraphManifest.from_json(GraphManifest(invalid_child).to_json())
