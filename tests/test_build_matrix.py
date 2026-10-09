import gc
import json
import weakref
from dataclasses import FrozenInstanceError
from pathlib import Path
from typing import Any, cast

import pytest
from jsonschema import Draft4Validator

from clean_ioc import BuildIssue, ContainerBuilder, ContainerBuildError, IssueSeverity, build_arg
from clean_ioc.cli import main
from clean_ioc.matrix import (
    BuildMatrix,
    BuildVariant,
    require_valid_variants,
    same_entrypoints,
    semantic_drift,
)
from clean_ioc.tooling import ChangeAllowance, ChangeRisk, DiffPolicy, GraphChangeKind


class Repository:
    def __init__(self):
        raise AssertionError("Matrix checks must not activate components")


class SqlRepository(Repository):
    pass


class SandboxRepository(Repository):
    pass


class Application:
    def __init__(self, repository: Repository):
        raise AssertionError("Matrix checks must not activate components")


class OtherApplication:
    pass


class Missing:
    pass


class Broken:
    def __init__(self, missing: Missing):
        raise AssertionError("Matrix checks must not activate components")


def builder(implementation=SqlRepository, *, entrypoint=True):
    result = ContainerBuilder()
    result.register(Repository, implementation)
    result.register(Application)
    if entrypoint:
        result.mark_entrypoint(Application)
    return result


def broken_builder():
    result = ContainerBuilder()
    result.register(Broken)
    return result


def matrix(*variants, reference="production", policies=()):
    return BuildMatrix(
        variants or (BuildVariant("production", builder), BuildVariant("staging", builder)),
        reference=reference,
        policies=policies,
    )


@pytest.fixture(scope="module")
def validator():
    schema = json.loads((Path(__file__).parent / "fixtures" / "sarif-schema-2.1.0.json").read_text())
    return Draft4Validator(schema, format_checker=Draft4Validator.FORMAT_CHECKER)


def sarif(report, validator):
    document = json.loads(report.to_sarif())
    validator.validate(document)
    return document


def results(document):
    return [result for run in document["runs"] for result in run["results"]]


def test_builds_in_declaration_order_reference_position_and_closes_before_policies():
    calls = []
    scopes = []

    class TrackedBuilder(ContainerBuilder):
        def build(self, **kwargs):
            scope = super().build(**kwargs)
            scopes.append(scope)
            return scope

    def factory(name):
        def create():
            calls.append(name)
            created = TrackedBuilder()
            created.register(Repository)
            return created

        return create

    def policy(context):
        assert all(scope._closed for scope in scopes)
        assert [variant.name for variant in context.variants] == ["staging", "production", "local"]
        calls.append("policy")
        return ()

    report = matrix(
        *(BuildVariant(name, factory(name)) for name in ("staging", "production", "local")), policies=(policy,)
    ).check()
    assert report.is_valid and report.exit_code == 0
    assert calls == ["staging", "production", "local", "policy"]
    assert all(variant.difference.is_empty for variant in report.variants)
    assert all(scope._closed for scope in scopes)
    assert len({variant.fingerprint for variant in report.variants}) == 1


def test_each_check_uses_fresh_factories_and_stable_captured_reports(validator):
    definition = matrix(policies=(same_entrypoints(), semantic_drift(DiffPolicy())))
    first, second = definition.check(), definition.check()
    assert first.is_valid and second.is_valid
    assert first.to_json() == second.to_json()
    assert first.to_sarif() == second.to_sarif()
    assert "schema_version" not in first.to_dict()
    assert all(run["results"] == [] for run in sarif(first, validator)["runs"])
    assert first.assert_valid() is None


def test_runs_build_rules_once_and_validation_only_rules_once_per_variant():
    calls = []

    def create():
        created = builder()

        def build_rule(_):
            calls.append("build")
            return ()

        def validation_rule(_):
            calls.append("validation")
            return (BuildIssue("validation-finding", IssueSeverity.error, "Validation failed."),)

        created.add_validation_rule(build_rule)
        created.add_validation_rule(validation_rule, mode="validation")
        return created

    report = matrix(BuildVariant("production", builder), BuildVariant("staging", create)).check()
    assert calls == ["build", "validation"]
    assert not report.is_valid and report.exit_code == 1
    assert report.variants[1].build_report.errors[0].code == "validation-finding"
    assert report.variants[1].fingerprint is None and report.variants[1].difference is None
    for _ in range(2):
        report.to_json()
        report.to_text()
        report.to_sarif()
    assert calls == ["build", "validation"]


def test_aggregates_independent_build_failures_and_continues_later_variants(validator):
    calls = []

    def last():
        calls.append("last")
        return builder()

    report = matrix(
        BuildVariant("production", builder),
        BuildVariant("broken", broken_builder),
        BuildVariant("also-broken", broken_builder),
        BuildVariant("last", last),
    ).check()
    assert calls == ["last"]
    assert [variant.is_valid for variant in report.variants] == [True, False, False, True]
    assert [(issue.code, issue.root) for issue in report.issues] == [
        ("matrix-build-failed", "broken"),
        ("matrix-build-failed", "also-broken"),
    ]
    for variant in report.variants[1:3]:
        issue = variant.build_report.errors[0]
        assert issue.code == "missing-component" and issue.path[-1].endswith(".Missing")
    missing = [result for result in results(sarif(report, validator)) if result["ruleId"] == "missing-component"]
    assert {result["properties"]["variant"] for result in missing} == {"broken", "also-broken"}
    assert all(result["locations"][0].get("physicalLocation") for result in missing)


def test_invalid_reference_has_one_comparison_finding_and_custom_policies_still_run():
    called = []

    def custom(context):
        called.append(context.reference_report.is_valid)
        return ()

    report = matrix(
        BuildVariant("staging", builder),
        BuildVariant("production", broken_builder),
        BuildVariant("local", builder),
        policies=(same_entrypoints(), semantic_drift(DiffPolicy()), custom),
    ).check()
    assert called == [False]
    assert [issue.code for issue in report.issues] == ["matrix-build-failed", "matrix-reference-invalid"]
    assert all(variant.difference is None for variant in report.variants)
    assert report.variants[0].fingerprint is not None and report.variants[1].fingerprint is None


def test_cannot_disable_validity_or_duplicate_the_implicit_policy():
    report = matrix(
        BuildVariant("production", builder),
        BuildVariant("broken", broken_builder),
        policies=(require_valid_variants(), require_valid_variants()),
    ).check()
    assert not report.is_valid
    assert [issue.code for issue in report.issues] == ["matrix-build-failed"]


def test_semantic_drift_rejects_risky_replacements_and_allows_explicit_exceptions(validator):
    variants = (BuildVariant("production", builder), BuildVariant("staging", lambda: builder(SandboxRepository)))
    rejected = matrix(
        *variants, policies=(same_entrypoints(), semantic_drift(DiffPolicy(fail_at=ChangeRisk.high)))
    ).check()
    assert [issue.code for issue in rejected.issues] == ["matrix-graph-drift"]
    issue = rejected.issues[0]
    assert issue.root == "staging" and issue.path[0].endswith("/dependency:repository:0")
    change = rejected.variants[1].difference.semantic_changes[0]
    assert change.kind is GraphChangeKind.implementation_changed
    assert change.affected_entrypoints
    drift = next(result for result in results(sarif(rejected, validator)) if result["ruleId"] == "matrix-graph-drift")
    assert drift["properties"]["variant"] == "staging"
    assert drift["locations"][0]["physicalLocation"]["artifactLocation"]["uri"] == "tests/test_build_matrix.py"
    allowed = matrix(
        *variants,
        policies=(
            semantic_drift(
                DiffPolicy(
                    allowances=(
                        ChangeAllowance(
                            kind=GraphChangeKind.implementation_changed, path_glob="*/dependency:repository:*"
                        ),
                    )
                )
            ),
        ),
    ).check()
    assert allowed.is_valid and allowed.variants[1].difference.semantic_changes


def test_same_entrypoints_detects_marker_loss_even_when_the_graph_still_builds():
    report = matrix(
        BuildVariant("production", builder),
        BuildVariant("staging", lambda: builder(entrypoint=False)),
        policies=(same_entrypoints(),),
    ).check()
    assert all(variant.is_valid for variant in report.variants)
    assert [(issue.code, issue.root) for issue in report.issues] == [("matrix-entrypoint-drift", "staging")]


def test_same_entrypoints_detects_requested_type_and_selected_name_changes():
    def create(name):
        def factory():
            created = ContainerBuilder()
            created.register(Repository, name=name)
            created.mark_entrypoint(list[Repository], filter=lambda _: True)
            return created

        return factory

    report = matrix(
        BuildVariant("production", create("first")),
        BuildVariant("staging", create("second")),
        policies=(same_entrypoints(),),
    ).check()
    assert [issue.code for issue in report.issues] == ["matrix-entrypoint-drift"]
    assert report.variants[0].entrypoints[0][0].startswith("list[")


@pytest.mark.parametrize("name", ["", "has space", "has/slash", "not:valid", "é", "😀", "line\n", None, 1])
def test_rejects_invalid_names_without_echoing_them(name):
    with pytest.raises(ValueError, match="matrix-invalid-name") as raised:
        BuildVariant(name, builder)
    assert "has space" not in str(raised.value)


@pytest.mark.parametrize("name", ["production", "qa-2", "uk.east", "tenant_12", "123"])
def test_accepts_supported_ascii_names(name):
    assert BuildMatrix((BuildVariant(name, builder),), reference=name).check().is_valid


def test_definition_validation_and_captured_build_input_mapping():
    inputs = {"environment": "production"}
    variant = BuildVariant("production", builder, inputs)
    inputs["environment"] = "staging"
    assert variant.build_args["environment"] == "production"
    with pytest.raises(TypeError):
        cast(Any, variant.build_args)["environment"] = "local"
    with pytest.raises(FrozenInstanceError):
        setattr(variant, "name", "local")
    assert "environment" not in repr(variant) and "builder" not in repr(variant)
    with pytest.raises(ValueError, match="matrix-invalid-name"):
        BuildMatrix((variant, variant), reference="production")
    with pytest.raises(ValueError, match="matrix-reference-missing"):
        BuildMatrix((variant,), reference="missing")
    with pytest.raises(ValueError, match="matrix-reference-missing"):
        BuildMatrix((), reference="production")
    with pytest.raises(ValueError, match="matrix-invalid-variant"):
        BuildMatrix(cast(Any, (builder,)), reference="production")
    with pytest.raises(ValueError, match="matrix-invalid-inputs"):
        BuildVariant("production", builder, cast(Any, {object(): "private"}))


@pytest.mark.parametrize("factory", [lambda: None, lambda: {}, lambda: builder().build(), lambda: object()])
def test_factory_rejects_invalid_results_and_continues(factory):
    report = matrix(BuildVariant("invalid", factory), BuildVariant("production", builder)).check()
    assert report.exit_code == 2 and report.variants[1].is_valid
    assert report.variants[0].build_report.errors[0].code == "matrix-factory-error"


def test_prebuilt_and_reused_builders_including_failed_builders_are_rejected():
    used = builder()
    used.build()
    prebuilt = matrix(BuildVariant("bad", lambda: used), BuildVariant("production", builder)).check()
    assert prebuilt.exit_code == 2
    reused = builder()
    report = matrix(BuildVariant("production", lambda: reused), BuildVariant("staging", lambda: reused)).check()
    assert report.exit_code == 2
    assert report.variants[1].build_report.errors[0].code == "matrix-reused-builder"
    failed = broken_builder()
    report = matrix(
        BuildVariant("bad", lambda: failed), BuildVariant("reused", lambda: failed), BuildVariant("production", builder)
    ).check()
    assert report.variants[1].build_report.errors[0].code == "matrix-reused-builder"


def test_asynchronous_callbacks_are_rejected_or_closed_without_activation(recwarn):
    async def async_factory():
        raise AssertionError("Must not execute async factories")

    async def async_policy(_):
        raise AssertionError("Must not execute async policies")

    class AsyncFactory:
        async def __call__(self):
            raise AssertionError("Must not execute async factories")

    for factory in (async_factory, AsyncFactory(), None):
        with pytest.raises(ValueError, match="matrix-factory-error"):
            BuildVariant("production", cast(Any, factory))
    with pytest.raises(ValueError, match="matrix-policy-error"):
        matrix(policies=cast(Any, (async_policy,)))
    report = matrix(
        BuildVariant("production", builder),
        BuildVariant("async", cast(Any, lambda: async_factory())),
        policies=(lambda context: cast(Any, async_policy(context)),),
    ).check()
    assert report.exit_code == 2
    assert report.variants[1].build_report.errors[0].code == "matrix-factory-error"
    assert report.issues[-1].code == "matrix-policy-error"
    gc.collect()
    assert not [warning for warning in recwarn if warning.category is RuntimeWarning]


def test_missing_build_input_keeps_the_input_key_out_of_reports(validator):
    class Configured:
        def __init__(self, configured: str):
            raise AssertionError("Must not activate")

    def create():
        created = ContainerBuilder()
        created.register(Configured, arguments={"configured": build_arg("private-key")})
        return created

    report = matrix(BuildVariant("production", builder), BuildVariant("missing-input", create)).check()
    assert report.variants[1].build_report.errors[0].code == "invalid-derived-argument"
    for value in (report.to_json(), report.to_text(), report.to_sarif()):
        assert "private-key" not in value
    sarif(report, validator)


def test_removed_component_drift_uses_the_reference_source_location(validator):
    class EmptyApplication(Application):
        def __init__(self):
            raise AssertionError("Must not activate")

    def create():
        created = ContainerBuilder()
        created.register(Application, EmptyApplication, root_policy="entrypoint")
        return created

    report = matrix(
        BuildVariant("production", builder), BuildVariant("staging", create), policies=(semantic_drift(DiffPolicy()),)
    ).check()
    removed = next(
        result
        for result in results(sarif(report, validator))
        if result["ruleId"] == "matrix-graph-drift" and "dependency-removed" in result["message"]["text"]
    )
    assert removed["properties"]["variant"] == "staging"
    location = removed["locations"][0]
    assert location["logicalLocations"][0]["fullyQualifiedName"].endswith(".Repository")
    assert location["physicalLocation"]["artifactLocation"]["uri"] == "tests/test_build_matrix.py"


def test_build_inputs_select_compositions_and_filters_are_not_replayed():
    calls = []

    def create():
        created = ContainerBuilder()

        def production(component):
            calls.append("filter")
            return component.build_args["private-key"] == "private-production"

        created.register(Repository, SqlRepository, when=production)
        created.register(
            Repository,
            SandboxRepository,
            when=lambda component: component.build_args["private-key"] != "private-production",
        )
        created.register(Application, root_policy="entrypoint")
        return created

    report = matrix(
        BuildVariant("production", create, {"private-key": "private-production"}),
        BuildVariant("staging", create, {"private-key": "private-staging"}),
    ).check()
    assert report.is_valid and report.variants[1].difference.semantic_changes
    previous = list(calls)
    for value in (report.to_text(), report.to_json(), report.to_sarif()):
        assert "private-key" not in value and "private-production" not in value and "private-staging" not in value
    assert calls == previous


def test_matrix_captures_declaration_lists_and_rejects_noniterables():
    variants = [BuildVariant("production", builder)]
    policies = [same_entrypoints()]
    definition = BuildMatrix(variants, reference="production", policies=policies)
    variants.clear()
    policies.clear()
    assert len(definition.variants) == len(definition.policies) == 1
    with pytest.raises(ValueError, match="matrix-invalid-variant"):
        BuildMatrix(cast(Any, None), reference="production")
    with pytest.raises(ValueError, match="matrix-policy-error"):
        matrix(policies=cast(Any, None))
    with pytest.raises(ValueError, match="diff-policy-invalid"):
        semantic_drift(cast(Any, None))


def test_unstructured_build_exceptions_do_not_stop_later_variants():
    class UnexpectedBuilder(ContainerBuilder):
        def build(self, **kwargs):
            raise RuntimeError("private-key private-value")

    report = matrix(BuildVariant("unexpected", UnexpectedBuilder), BuildVariant("production", builder)).check()
    assert report.exit_code == 1 and report.variants[1].is_valid
    assert report.variants[0].build_report.errors[0].code == "matrix-build-failed"
    assert "private-value" not in report.to_json()


def test_unstructured_container_build_errors_remain_safe():
    class UnexpectedBuilder(ContainerBuilder):
        def build(self, **kwargs):
            raise ContainerBuildError("private-key private-value")

    report = matrix(BuildVariant("production", UnexpectedBuilder)).check()
    assert not report.is_valid
    assert "private-value" not in report.to_json()


def test_factory_and_policy_exception_text_and_hostile_repr_are_never_copied(validator):
    class HostileError(Exception):
        def __str__(self):
            raise AssertionError("Must not stringify exceptions")

        __repr__ = __str__

    def factory():
        raise HostileError("private-key private-value")

    def policy(_):
        raise HostileError("private-key private-value")

    report = matrix(BuildVariant("production", builder), BuildVariant("failed", factory), policies=(policy,)).check()
    assert report.exit_code == 2
    assert report.issues[-1].code == "matrix-policy-error"
    for value in (report.to_json(), report.to_text(), report.to_sarif(), repr(report)):
        assert "private-key" not in value and "private-value" not in value
        assert "HostileError" not in value
    sarif(report, validator)


@pytest.mark.parametrize(
    "returned", [None, 1, "invalid", (object(),), (BuildIssue("", IssueSeverity.error, "Invalid."),)]
)
def test_malformed_policy_results_do_not_stop_subsequent_policies(returned):
    calls = []

    def last(context):
        calls.append("last")
        return (context.issue("production", "later-finding", "A later policy ran."),)

    report = matrix(policies=(lambda _: returned, last)).check()
    assert calls == ["last"]
    assert [issue.code for issue in report.issues] == ["matrix-policy-error", "later-finding"]


def test_yielded_findings_survive_a_later_policy_error():
    def policy(context):
        yield context.issue("staging", "first-finding", "First finding.")
        raise RuntimeError("private-value")

    report = matrix(policies=(policy,)).check()
    assert [issue.code for issue in report.issues] == ["first-finding", "matrix-policy-error"]


def test_warning_only_reports_and_matrix_findings_pass(validator):
    def create():
        created = builder()
        created.add_validation_rule(lambda _: (BuildIssue("warning", IssueSeverity.warning, "Warning."),))
        return created

    def policy(context):
        return (context.issue("production", "matrix-warning", "Warning.", severity=IssueSeverity.warning),)

    report = matrix(BuildVariant("production", create), policies=(policy,)).check()
    assert report.is_valid and report.exit_code == 0 and report.assert_valid() is None
    assert {result["level"] for result in results(sarif(report, validator))} == {"warning"}


def test_policy_context_has_no_graph_inputs_and_nested_snapshots_cannot_affect_other_policies():
    def mutate(context):
        assert not hasattr(context, "build_args")
        for variant in context.variants:
            assert variant.build_report._graph is None
            assert variant.build_report._explanations == () and variant.build_report._evidence == ()
        manifest = context.manifest("production")
        manifest.data.clear()
        context.variants[1].difference.semantic_changes[0].after.clear()
        with pytest.raises(TypeError):
            context._manifests["production"] = "{}"
        return ()

    def check(context):
        assert context.manifest("production").data["roots"]
        assert context.variants[1].difference.semantic_changes[0].after["implementation"]
        return ()

    report = matrix(
        BuildVariant("production", builder),
        BuildVariant("staging", lambda: builder(SandboxRepository)),
        policies=(mutate, check),
    ).check()
    assert report.is_valid and report.variants[1].difference.semantic_changes[0].after


def test_inputs_values_types_counts_and_input_hashes_are_absent_from_all_reports(validator):
    class PrivateInput:
        def __str__(self):
            raise AssertionError("Must not stringify private inputs")

        __repr__ = __str__

    class Configured:
        def __init__(self, configured: object):
            raise AssertionError("Must not activate")

    def create():
        created = ContainerBuilder()
        created.register(Configured, root_policy="entrypoint", arguments={"configured": build_arg("private-key")})
        return created

    checked = []

    def policy(context):
        captured = context.manifest("production").to_json()
        assert "PrivateInput" not in captured
        assert "private-key" not in captured and "unused-secret" not in captured
        checked.append(True)
        return ()

    report = matrix(
        BuildVariant("production", create, {"private-key": PrivateInput()}),
        BuildVariant("staging", create, {"private-key": object(), "unused-secret": "private-value"}),
        policies=(policy, semantic_drift(DiffPolicy())),
    ).check()
    assert checked == [True] and report.is_valid
    assert report.variants[0].fingerprint == report.variants[1].fingerprint
    assert report.variants[1].difference.is_empty
    for value in (report.to_text(), report.to_json(), report.to_sarif(), repr(report)):
        for forbidden in ("private-key", "private-value", "unused-secret", "PrivateInput", "build_args", "input_count"):
            assert forbidden not in value
    document = sarif(report, validator)
    assert all(run["properties"]["graphFingerprint"] == report.variants[0].fingerprint for run in document["runs"])
    assert all(
        json.loads(captured)["runs"][0]["properties"]["graphFingerprint"] == report.variants[0].fingerprint
        for captured in report._sarif
    )


def test_validation_callback_errors_are_redacted_but_keep_their_code():
    def create():
        created = builder()

        def bad_rule(_):
            raise RuntimeError("private-key private-value")

        created.add_validation_rule(bad_rule, mode="validation")
        return created

    report = matrix(BuildVariant("production", create)).check()
    assert report.variants[0].build_report.errors[0].code == "validation-rule-error"
    for value in (report.to_json(), report.to_text(), report.to_sarif()):
        assert "private-key" not in value and "private-value" not in value


def test_matrix_reports_do_not_retain_runtime_containers(validator):
    references = []

    class TrackedBuilder(ContainerBuilder):
        def build(self, **kwargs):
            scope = super().build(**kwargs)
            references.append(weakref.ref(scope))
            return scope

    def create():
        created = TrackedBuilder()
        created.register(Repository)
        return created

    report = matrix(BuildVariant("production", create)).check()
    gc.collect()
    assert all(reference() is None for reference in references)
    sarif(report, validator)


def test_overlay_variants_close_the_overlay_and_leave_the_parent_open():
    from clean_ioc import ScopeBuilder

    parent = builder().build()
    scopes = []

    class TrackedScopeBuilder(ScopeBuilder):
        def build(self, **kwargs):
            scope = super().build(**kwargs)
            scopes.append(scope)
            return scope

    def create():
        overlay = TrackedScopeBuilder(parent)
        overlay.register(OtherApplication)
        return overlay

    report = matrix(
        BuildVariant("production", create),
        BuildVariant("staging", create),
        policies=(same_entrypoints(), semantic_drift(DiffPolicy())),
    ).check()
    assert report.is_valid
    assert len(scopes) == 2 and all(scope._closed for scope in scopes)
    assert parent._closed is False
    parent.__exit__(None, None, None)


@pytest.mark.parametrize("failure", ["capture", "policy"])
def test_scopes_are_closed_on_capture_or_policy_failure(monkeypatch, failure):
    import clean_ioc.matrix as matrix_module

    scopes = []

    class TrackedBuilder(ContainerBuilder):
        def build(self, **kwargs):
            scope = super().build(**kwargs)
            scopes.append(scope)
            return scope

    def create():
        created = TrackedBuilder()
        created.register(Repository)
        return created

    original = matrix_module._capture

    def capture_failed(name, report, graph=None):
        if graph is not None:
            raise RuntimeError("private-value")
        return original(name, report)

    def policy_failed(_):
        assert all(scope._closed for scope in scopes)
        raise RuntimeError("private-value")

    if failure == "capture":
        monkeypatch.setattr(matrix_module, "_capture", capture_failed)
    report = matrix(
        BuildVariant("production", create), policies=(policy_failed,) if failure == "policy" else ()
    ).check()
    assert not report.is_valid and len(scopes) == 1
    assert all(scope._closed for scope in scopes)
    assert "private-value" not in report.to_json()


def test_assertion_failure_is_a_valid_variant_linked_sarif_document(validator):
    report = matrix(BuildVariant("production", builder), BuildVariant("failed", broken_builder)).check()
    with pytest.raises(AssertionError) as raised:
        report.assert_valid()
    document = json.loads(str(raised.value))
    validator.validate(document)
    assert "failed" in {result["properties"].get("variant") for result in results(document)}


def test_cli_formats_output_exit_status_and_target_factories(tmp_path, capsys, validator):
    target = "tests.tooling_targets:valid_matrix"
    assert main(["matrix", target]) == 0
    assert "Build matrix passed" in capsys.readouterr().out
    assert main(["matrix", target, "--format", "json"]) == 0
    assert json.loads(capsys.readouterr().out)["valid"] is True
    output = tmp_path / "matrix.sarif"
    assert main(["matrix", "tests.tooling_targets:invalid_matrix", "--format", "sarif", "-o", str(output)]) == 1
    validator.validate(json.loads(output.read_text()))
    assert capsys.readouterr().out == ""
    assert main(["matrix", "tests.tooling_targets:factory_error_matrix", "--format", "json"]) == 2
    assert json.loads(capsys.readouterr().out)["valid"] is False
    assert main(["matrix", "tests.tooling_targets:matrix_object", "--format", "json"]) == 0
    assert json.loads(capsys.readouterr().out)["reference"] == "production"


@pytest.mark.parametrize(
    "target",
    [
        "not-a-locator",
        "tests.tooling_targets:missing",
        "tests.tooling_targets:builder",
        "tests.tooling_targets:invalid_matrix_factory",
        "tests.tooling_targets:dictionary_matrix",
    ],
)
def test_cli_invalid_targets_leave_existing_output_untouched(target, tmp_path, capsys):
    output = tmp_path / "existing.json"
    output.write_text("existing-report")
    assert main(["matrix", target, "--format", "json", "-o", str(output)]) == 2
    assert capsys.readouterr().err
    assert output.read_text() == "existing-report"


def test_cli_invalid_output_and_no_build_input_arguments(tmp_path, capsys):
    assert main(["matrix", "tests.tooling_targets:valid_matrix", "-o", str(tmp_path)]) == 2
    assert capsys.readouterr().err
    with pytest.raises(SystemExit) as raised:
        main(["matrix", "tests.tooling_targets:valid_matrix", "--build-args", "private-key=private-value"])
    assert raised.value.code == 2


def test_cli_matrix_factory_failures_do_not_echo_secrets(monkeypatch, capsys, recwarn):
    def broken():
        raise RuntimeError("private-key private-value")

    async def asynchronous():
        raise AssertionError("Must not activate")

    for target in (broken, asynchronous, lambda: asynchronous()):
        monkeypatch.setattr("clean_ioc.cli._load_object", lambda _: target)
        assert main(["matrix", "example:matrix"]) == 2
        message = capsys.readouterr().err
        assert "private-key" not in message and "private-value" not in message
    gc.collect()
    assert not [warning for warning in recwarn if warning.category is RuntimeWarning]
