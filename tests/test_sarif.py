import gc
import json
import subprocess
import sys
import weakref
from dataclasses import replace
from importlib.metadata import version
from pathlib import Path
from urllib.parse import unquote

import pytest
from jsonschema import Draft4Validator

import clean_ioc.component_filters as cf
from clean_ioc import BuildIssue, BuildReport, ContainerBuilder, ContainerBuildError, IssueSeverity, Provider, build_arg
from clean_ioc.cli import main
from clean_ioc.policies import PolicyPack, forbid_dependency
from clean_ioc.tooling import CompiledGraph, FailureEvidence, SourceLocation, qualified_name


@pytest.fixture(scope="module")
def validator():
    schema = json.loads((Path(__file__).parent / "fixtures" / "sarif-schema-2.1.0.json").read_text(encoding="utf-8"))
    Draft4Validator.check_schema(schema)
    return Draft4Validator(schema, format_checker=Draft4Validator.FORMAT_CHECKER)


def validated_run(value, validator):
    document = json.loads(value)
    validator.validate(document)
    assert document["version"] == "2.1.0"
    return document["runs"][0]


class Dependency:
    def __init__(self):
        raise AssertionError("SARIF must not activate dependencies")


class Service:
    def __init__(self, dependency: Dependency):
        raise AssertionError("SARIF must not activate services")


def policy_builder(mode="validation"):
    builder = ContainerBuilder()
    builder.register(Dependency)
    builder.register(Service)
    builder.apply_bundle(
        PolicyPack(
            "architecture", [forbid_dependency(cf.service_type_is(Service), cf.service_type_is(Dependency))], mode=mode
        )
    )
    return builder


def test_valid_report_is_deterministic_and_records_version_and_complete_graph_fingerprint(validator):
    builder = ContainerBuilder()
    builder.register(Dependency)
    container = builder.build()
    report = container.validation_report()
    value = report.to_sarif(graph=container.graph)
    run = validated_run(value, validator)

    assert run["results"] == []
    assert run["tool"]["driver"]["version"] == version("clean_ioc")
    assert run["properties"] == {
        "checkedRoots": 1,
        "graphFingerprint": container.graph.manifest(all_roots=True).fingerprint,
    }
    assert value == report.to_sarif(graph=container.graph)
    assert json.loads(value) == json.loads(report.to_sarif(graph=container.graph, indent=None))


@pytest.mark.parametrize("mode", ["build", "validation"])
def test_cli_policy_failures_have_registration_locations_and_source_linked_dependency_flows(
    mode, monkeypatch, capsys, validator
):
    monkeypatch.setattr("clean_ioc.cli._load_object", lambda _: lambda: policy_builder(mode))
    assert main(["check", "example:builder", "--format", "sarif"]) == 1
    output = capsys.readouterr()
    assert output.err == ""
    run = validated_run(output.out, validator)
    result = run["results"][0]
    assert result["ruleId"] == "policy-forbidden-dependency"
    assert result["level"] == "error"
    assert "architecture" in result["message"]["text"]
    assert run["properties"]["graphFingerprint"]
    path = result["properties"]["componentPath"]
    assert path == [qualified_name(Service), qualified_name(Dependency)]
    flow = result["codeFlows"][0]["threadFlows"][0]["locations"]
    assert [item["location"]["logicalLocations"][0]["fullyQualifiedName"] for item in flow] == path
    assert all(
        item["location"]["physicalLocation"]["artifactLocation"]["uri"] == "tests/test_sarif.py" for item in flow
    )
    assert result["locations"][0] == flow[-1]["location"]


def test_programmatic_failed_policy_keeps_complete_graph_and_uses_same_renderer(validator):
    with pytest.raises(ContainerBuildError) as raised:
        policy_builder("build").build()
    error = raised.value
    assert error.compiled_graph is not None
    assert error.report is not None
    run = validated_run(error.to_sarif(), validator)
    assert run["properties"]["graphFingerprint"] == error.compiled_graph.manifest(all_roots=True).fingerprint
    assert json.loads(error.to_sarif()) == json.loads(error.report.to_sarif(graph=error.compiled_graph))


def test_schema_valid_report_without_provenance_or_any_source_information(validator):
    container = policy_builder().build()
    report = container.validation_report()
    graph = CompiledGraph(container.graph.roots)
    result = validated_run(report.to_sarif(graph=graph), validator)["results"][0]
    assert "physicalLocation" not in result["locations"][0]
    assert all(
        "physicalLocation" not in item["location"] for item in result["codeFlows"][0]["threadFlows"][0]["locations"]
    )
    standalone = BuildReport(report.issues, checked_roots=report.checked_roots)
    no_graph = validated_run(standalone.to_sarif(), validator)
    assert "graphFingerprint" not in no_graph["properties"]


def test_stable_rules_severity_and_unlocated_findings_preserve_existing_json_shape(validator):
    report = BuildReport(
        (
            BuildIssue("custom-rule", IssueSeverity.warning, "Advisory"),
            BuildIssue("other-rule", IssueSeverity.error, "Required"),
            BuildIssue("custom-rule", IssueSeverity.error, "Another finding"),
        ),
        checked_roots=3,
    )
    run = validated_run(report.to_sarif(), validator)
    assert run["tool"]["driver"]["rules"] == [{"id": "custom-rule"}, {"id": "other-rule"}]
    assert [result["ruleIndex"] for result in run["results"]] == [0, 1, 0]
    assert [result["level"] for result in run["results"]] == ["warning", "error", "error"]
    assert all("locations" not in result and "codeFlows" not in result for result in run["results"])
    assert json.loads(report.to_json()) == {
        "valid": False,
        "checked_roots": 3,
        "issues": [
            {"code": "custom-rule", "severity": "warning", "message": "Advisory", "root": None, "path": []},
            {"code": "other-rule", "severity": "error", "message": "Required", "root": None, "path": []},
            {"code": "custom-rule", "severity": "error", "message": "Another finding", "root": None, "path": []},
        ],
    }


def test_exact_occurrence_attribution_does_not_guess_between_same_type_named_registrations(monkeypatch, validator):
    monkeypatch.setattr(
        "clean_ioc.container._source_location", lambda: SourceLocation(None, None, "src/default.py", 10)
    )
    builder = ContainerBuilder()
    builder.register(Dependency)
    monkeypatch.setattr("clean_ioc.container._source_location", lambda: SourceLocation(None, None, "src/named.py", 20))
    builder.register(Dependency, name="named")
    graph = builder.build(diagnostics=True).graph
    visit = next(visit for visit in graph.walk() if visit.component.name == "named")
    exact = visit.issue("example-policy", "Finding")
    ambiguous = BuildIssue(exact.code, exact.severity, exact.message, root=exact.root, path=exact.path)
    assert exact == ambiguous
    assert hash(exact) == hash(ambiguous)
    assert exact.to_dict() == ambiguous.to_dict()
    located = validated_run(BuildReport((exact,)).to_sarif(graph=graph), validator)["results"][0]
    assert located["locations"][0]["physicalLocation"] == {
        "artifactLocation": {"uri": "src/named.py"},
        "region": {"startLine": 20},
    }
    unlocated = validated_run(BuildReport((ambiguous,)).to_sarif(graph=graph), validator)["results"][0]
    assert "physicalLocation" not in unlocated["locations"][0]
    assert "occurrence" not in json.dumps(located)


@pytest.mark.parametrize(
    "source_path, expected",
    [
        ("src/a file#%é.py", "src/a%20file%23%25%C3%A9.py"),
        (str(Path.cwd() / "src" / "absolute.py"), "src/absolute.py"),
        ("../external.py", None),
        ("/external/private/project.py", None),
        (r"C:\private\project.py", None),
        (r"\\server\private\project.py", None),
        ("<generated>", None),
        (None, None),
    ],
)
def test_source_uris_are_relative_encoded_and_omit_external_paths(source_path, expected, monkeypatch, validator):
    source = SourceLocation("example", "register", source_path, 12)
    monkeypatch.setattr("clean_ioc.container._source_location", lambda: source)
    builder = ContainerBuilder()
    builder.register(Dependency)
    graph = builder.build(diagnostics=True).graph
    issue = next(graph.walk()).issue("example-policy", "Finding")
    value = BuildReport((issue,)).to_sarif(graph=graph)
    result = validated_run(value, validator)["results"][0]
    if expected is None:
        assert "physicalLocation" not in result["locations"][0]
        if source_path is not None:
            assert source_path not in value
    else:
        assert result["locations"][0]["physicalLocation"]["artifactLocation"]["uri"] == expected
        assert not Path(unquote(expected)).is_absolute()
    assert str(Path.cwd()) not in value


@pytest.mark.parametrize("line", [None, 0, -1, True])
def test_unknown_or_invalid_lines_are_omitted_without_fabrication(line, monkeypatch, validator):
    monkeypatch.setattr("clean_ioc.container._source_location", lambda: SourceLocation(None, None, "src/app.py", line))
    builder = ContainerBuilder()
    builder.register(Dependency)
    graph = builder.build(diagnostics=True).graph
    issue = next(graph.walk()).issue("example-policy", "Finding")
    result = validated_run(BuildReport((issue,)).to_sarif(graph=graph), validator)["results"][0]
    assert result["locations"][0]["physicalLocation"] == {"artifactLocation": {"uri": "src/app.py"}}


@pytest.mark.parametrize("failure", ["missing", "cycle", "captive"])
def test_structural_failures_produce_schema_valid_reports_and_captured_source_locations(failure, validator):
    class Missing:
        pass

    class Invalid:
        def __init__(self, dependency: Missing):
            raise AssertionError("must not activate")

    if failure == "cycle":
        Invalid.__init__.__annotations__["dependency"] = Invalid
    builder = ContainerBuilder()
    if failure == "captive":
        builder.register(Missing, lifespan="scoped")
    registration_line = sys._getframe().f_lineno + 1
    builder.register(Invalid, lifespan="singleton" if failure == "captive" else "transient")
    with pytest.raises(ContainerBuildError) as raised:
        builder.build()
    error = raised.value
    assert error.compiled_graph is None
    run = validated_run(error.to_sarif(), validator)
    assert "graphFingerprint" not in run["properties"]
    result = run["results"][0]
    assert result["level"] == "error"
    assert result["properties"]["componentPath"]
    if failure != "cycle":
        assert result["locations"][0]["physicalLocation"]["region"]["startLine"] == registration_line


@pytest.mark.parametrize("mode", ["build", "validation"])
@pytest.mark.parametrize(
    "options, expected, count", [([], 1, 1), (["--no-strict"], 0, 1), (["--ignore", "warning"], 0, 0)]
)
def test_cli_strictness_and_warning_suppression_do_not_reclassify_sarif_levels(
    mode, options, expected, count, monkeypatch, capsys, validator
):
    def make_builder():
        builder = ContainerBuilder()
        builder.register(Dependency)
        builder.add_validation_rule(lambda _: (BuildIssue("warning", IssueSeverity.warning, "Advisory"),), mode=mode)
        return builder

    monkeypatch.setattr("clean_ioc.cli._load_object", lambda _: make_builder)
    assert main(["check", "example:builder", "--format", "sarif", *options]) == expected
    run = validated_run(capsys.readouterr().out, validator)
    assert len(run["results"]) == count
    assert all(result["level"] == "warning" for result in run["results"])


def test_cli_ignore_never_suppresses_an_error(capsys, validator):
    assert (
        main(["check", "tests.tooling_targets:invalid_builder", "--format", "sarif", "--ignore", "missing-component"])
        == 1
    )
    run = validated_run(capsys.readouterr().out, validator)
    assert run["results"][0]["ruleId"] == "missing-component"


def test_cli_suppresses_failed_build_warnings_and_keeps_failure_evidence_aligned(monkeypatch, capsys, validator):
    report = BuildReport(
        (
            BuildIssue("warning", IssueSeverity.warning, "Advisory"),
            BuildIssue("failure", IssueSeverity.error, "Required"),
        )
    )
    facts = (
        FailureEvidence("custom", "Service", "warning", source_location=SourceLocation(None, None, "src/warn.py", 1)),
        FailureEvidence("custom", "Service", "error", source_location=SourceLocation(None, None, "src/error.py", 2)),
    )

    def failed_builder():
        raise ContainerBuildError(report=report, evidence=facts)

    monkeypatch.setattr("clean_ioc.cli._load_object", lambda _: failed_builder)
    assert main(["check", "example:builder", "--format", "sarif", "--ignore", "warning"]) == 1
    results = validated_run(capsys.readouterr().out, validator)["results"]
    assert len(results) == 1
    assert results[0]["ruleId"] == "failure"
    assert results[0]["locations"][0]["physicalLocation"]["artifactLocation"]["uri"] == "src/error.py"


def test_source_linked_paths_cover_decorators_preconfigurations_and_deferred_providers(validator):
    class Decorated(Service):
        def __init__(self, inner: Service, dependency: Dependency):
            raise AssertionError("must not activate")

    class LazyService:
        def __init__(self, dependency: Provider[Dependency]):
            raise AssertionError("must not activate")

    def configure(dependency: Dependency):
        raise AssertionError("must not activate")

    builder = ContainerBuilder()
    builder.register(Dependency, lifespan="singleton")
    builder.register(Service)
    builder.register(LazyService)
    builder.register_decorator(Service, Decorated, decorated_arg="inner")
    builder.pre_configure(Service, configure)
    graph = builder.build(diagnostics=True).graph
    issues = tuple(visit.issue("example-policy", "Finding") for visit in graph.walk())
    run = validated_run(BuildReport(issues).to_sarif(graph=graph), validator)
    for result in run["results"]:
        path = result["properties"]["componentPath"]
        if path[-1] in (qualified_name(Decorated), qualified_name(configure), qualified_name(Dependency)):
            assert result["locations"][0]["physicalLocation"]["artifactLocation"]["uri"] == "tests/test_sarif.py"
    assert any("Provider[" in result["message"]["text"] for result in run["results"])


def test_overlay_uses_declaring_registration_sources_and_full_overlay_fingerprint(monkeypatch, validator):
    monkeypatch.setattr("clean_ioc.container._source_location", lambda: SourceLocation(None, None, "src/root.py", 10))
    builder = ContainerBuilder()
    builder.register(Dependency, lifespan="singleton")
    parent = builder.build(diagnostics=True)
    overlay = parent.new_scope_builder()
    monkeypatch.setattr(
        "clean_ioc.container._source_location", lambda: SourceLocation(None, None, "src/overlay.py", 20)
    )
    overlay.register(Service)
    scope = overlay.build(diagnostics=True)
    visit = next(visit for visit in scope.graph.walk() if len(visit.components) == 2)
    run = validated_run(BuildReport((visit.issue("example-policy", "Finding"),)).to_sarif(graph=scope.graph), validator)
    flow = run["results"][0]["codeFlows"][0]["threadFlows"][0]["locations"]
    assert [item["location"]["physicalLocation"]["artifactLocation"]["uri"] for item in flow] == [
        "src/overlay.py",
        "src/root.py",
    ]
    assert run["properties"]["graphFingerprint"] == scope.graph.manifest(all_roots=True).fingerprint


def test_cli_already_built_container_runs_validation_once(monkeypatch, capsys, validator):
    container = policy_builder().build()
    calls = []
    original = type(container).validation_report

    def validation_report(self):
        calls.append("validation")
        return original(self)

    monkeypatch.setattr(type(container), "validation_report", validation_report)
    monkeypatch.setattr("clean_ioc.cli._load_object", lambda _: container)
    assert main(["check", "example:container", "--format", "sarif"]) == 1
    validated_run(capsys.readouterr().out, validator)
    assert calls == ["validation"]


def test_ambiguous_failure_decisions_do_not_create_a_source_location(validator):
    container = policy_builder().build(diagnostics=True)
    visit = next(visit for visit in container.graph.walk() if len(visit.components) == 2)
    decision = container.graph.explain(visit.component)
    first = replace(
        decision.selected[0],
        origin=replace(decision.selected[0].origin, location=SourceLocation(None, None, "src/a.py", 1)),
    )
    second = replace(first, origin=replace(first.origin, location=SourceLocation(None, None, "src/b.py", 2)))
    explanation = replace(decision, path=visit.path, selected=(first, second))
    report = BuildReport((visit.issue("example-policy", "Finding"),))
    result = validated_run(report.to_sarif(explanations=(explanation,)), validator)["results"][0]
    assert "physicalLocation" not in result["locations"][0]


@pytest.mark.parametrize("format", ["text", "json", "sarif"])
@pytest.mark.parametrize("target", ["valid_builder", "invalid_builder", "validation_only_error_builder"])
def test_check_output_file_handles_success_and_both_failure_phases(format, target, tmp_path, capsys, validator):
    output = tmp_path / "report"
    expected = 0 if target == "valid_builder" else 1
    assert (
        main(["check", f"tests.tooling_targets:{target}", "--format", format, "--no-strict", "-o", str(output)])
        == expected
    )
    captured = capsys.readouterr()
    assert captured.out == captured.err == ""
    value = output.read_text(encoding="utf-8")
    assert value.endswith("\n")
    if format == "sarif":
        run = validated_run(value, validator)
        assert any(result["level"] == "error" for result in run["results"]) is bool(expected)
    elif format == "json":
        assert json.loads(value)["valid"] is (expected == 0)
    else:
        assert "Container" in value


@pytest.mark.parametrize("options", [["--triage"], ["--triage", "--format", "json"]])
def test_existing_triage_output_still_works(options, tmp_path, capsys):
    output = tmp_path / "triage"
    assert main(["check", "tests.tooling_targets:invalid_builder", *options, "-o", str(output)]) == 1
    assert "tests.tooling_targets.Missing" in output.read_text(encoding="utf-8")
    assert capsys.readouterr().out == ""


@pytest.mark.parametrize(
    "target", ["not-a-locator", "tests.tooling_targets:does_not_exist", "tests.tooling_targets:TItem"]
)
def test_invalid_targets_do_not_create_or_overwrite_sarif(target, tmp_path, capsys):
    output = tmp_path / "report.sarif"
    output.write_text("original", encoding="utf-8")
    assert main(["check", target, "--format", "sarif", "-o", str(output)]) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err.startswith("clean-ioc:")
    assert output.read_text(encoding="utf-8") == "original"


def test_invalid_sarif_triage_combination_is_rejected_before_loading_target(monkeypatch, tmp_path, capsys):
    def must_not_load(_):
        raise AssertionError("must validate options before loading application code")

    monkeypatch.setattr("clean_ioc.cli._load_object", must_not_load)
    output = tmp_path / "report.sarif"
    assert main(["check", "example:builder", "--triage", "--format", "sarif", "-o", str(output)]) == 2
    assert "--triage supports text and JSON" in capsys.readouterr().err
    assert not output.exists()


def test_invalid_output_path_returns_usage_error_and_no_sarif_on_stdout(tmp_path, capsys):
    output = tmp_path / "missing-directory" / "report.sarif"
    assert main(["check", "tests.tooling_targets:valid_builder", "--format", "sarif", "-o", str(output)]) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err.startswith("clean-ioc:")
    assert not output.exists()


def test_sarif_redacts_inputs_values_runtime_ids_and_does_not_replay_rules_or_filters(validator):
    private_key = "private_build_input_key"
    private_value = "do-not-serialize-this-value"
    calls = []

    class Configured:
        def __init__(self, value: str):
            raise AssertionError("must not activate")

    builder = ContainerBuilder()
    builder.register(Configured, arguments={"value": build_arg(private_key)})
    builder.register(str, instance=private_value)

    def when(_):
        calls.append("filter")
        return True

    builder.register(Dependency, when=when)

    def rule(context):
        calls.append("rule")
        for visit in context.graph.walk():
            yield visit.issue("example-policy", "Safe issue", severity=IssueSeverity.warning)

    builder.add_validation_rule(rule, mode="validation")
    container = builder.build(build_args={private_key: private_value})
    report = container.validation_report()
    before = calls.copy()
    fingerprint = container.graph.manifest(all_roots=True).fingerprint
    value = report.to_sarif(graph=container.graph)
    validated_run(value, validator)
    assert calls == before
    assert container.graph.manifest(all_roots=True).fingerprint == fingerprint
    for serialized in (value, report.to_json()):
        assert private_key not in serialized
        assert private_value not in serialized
        assert " at 0x" not in serialized
        assert str(Path.cwd()) not in serialized
        for issue in report.issues:
            assert str(issue._occurrence_path) not in serialized


def test_error_without_structured_report_never_serializes_exception_message(validator):
    error = ContainerBuildError("private-exception-message", code="compile-error")
    value = error.to_sarif()
    run = validated_run(value, validator)
    assert run["results"][0]["ruleId"] == "compile-error"
    assert "private-exception-message" not in value


def test_renderer_rejects_misaligned_failure_evidence():
    with pytest.raises(ValueError, match="More evidence"):
        BuildReport().to_sarif(evidence=(None,))


@pytest.mark.parametrize("issues", [(), (BuildIssue("advisory", IssueSeverity.warning, "Advisory only"),)])
def test_assert_valid_returns_none_without_rendering_for_valid_and_warning_only_reports(issues, monkeypatch):
    def must_not_render(*args, **kwargs):
        raise AssertionError("A valid report must not generate SARIF")

    monkeypatch.setattr(BuildReport, "to_sarif", must_not_render)
    assert BuildReport(issues).assert_valid() is None


def test_assert_valid_raises_with_complete_schema_valid_sarif_for_an_unlocated_error(validator):
    report = BuildReport(
        (
            BuildIssue("advisory", IssueSeverity.warning, "Advisory"),
            BuildIssue("required", IssueSeverity.error, "Required"),
        ),
        checked_roots=2,
    )
    with pytest.raises(AssertionError) as raised:
        report.assert_valid(indent=None)

    value = str(raised.value)
    run = validated_run(value, validator)
    assert raised.value.args == (report.to_sarif(indent=None),)
    assert [result["ruleId"] for result in run["results"]] == ["advisory", "required"]
    assert [result["level"] for result in run["results"]] == ["warning", "error"]
    assert "\n" not in value


def test_assert_valid_links_policy_findings_to_matching_graph_without_repeating_validation(validator, monkeypatch):
    container = policy_builder().build(diagnostics=True)
    report = container.validation_report()

    def must_not_validate(*args, **kwargs):
        raise AssertionError("The assertion must inspect the existing report")

    monkeypatch.setattr(type(container), "validation_report", must_not_validate)
    with pytest.raises(AssertionError) as raised:
        report.assert_valid()

    run = validated_run(str(raised.value), validator)
    result = run["results"][0]
    assert result["ruleId"] == "policy-forbidden-dependency"
    assert result["locations"][0]["physicalLocation"]["artifactLocation"]["uri"] == "tests/test_sarif.py"
    assert run["properties"]["graphFingerprint"] == container.graph.manifest(all_roots=True).fingerprint
    assert result["codeFlows"][0]["threadFlows"][0]["locations"]


def test_assert_valid_accepts_captured_structural_failure_evidence(validator):
    from tests.tooling_targets import invalid_builder

    with pytest.raises(ContainerBuildError) as failed:
        invalid_builder().build()
    error = failed.value
    assert error.report is not None
    with pytest.raises(AssertionError) as raised:
        error.report.assert_valid()

    run = validated_run(str(raised.value), validator)
    result = run["results"][0]
    assert result["ruleId"] == "missing-component"
    assert result["locations"][0]["physicalLocation"]["artifactLocation"]["uri"] == "tests/tooling_targets.py"
    assert str(raised.value) == error.to_sarif()


def test_container_validation_report_automatically_retains_graph_without_changing_report_identity_semantics(validator):
    container = policy_builder().build(diagnostics=True)
    report = container.validation_report()
    standalone = BuildReport(report.issues, checked_roots=report.checked_roots)
    run = validated_run(report.to_sarif(), validator)
    result = run["results"][0]

    assert result["locations"][0]["physicalLocation"]["artifactLocation"]["uri"] == "tests/test_sarif.py"
    assert run["properties"]["graphFingerprint"] == container.graph.manifest(all_roots=True).fingerprint
    assert report.to_sarif() == report.to_sarif(graph=container.graph)
    assert report == standalone
    assert hash(report) == hash(standalone)
    assert repr(report) == repr(standalone)
    assert report.to_json() == standalone.to_json()
    assert report.to_text() == standalone.to_text()


@pytest.mark.parametrize("mode", ["build", "validation"])
def test_build_and_validation_reports_retain_their_graph_for_warning_findings(mode, validator):
    builder = ContainerBuilder()
    builder.register(Dependency)

    def warning(context):
        for visit in context.graph.walk():
            yield visit.issue("advisory", "Advisory only", severity=IssueSeverity.warning)

    builder.add_validation_rule(warning, mode=mode)
    container = builder.build(diagnostics=True)
    report = container.build_report if mode == "build" else container.validation_report()
    result = validated_run(report.to_sarif(), validator)["results"][0]
    assert result["locations"][0]["physicalLocation"]["artifactLocation"]["uri"] == "tests/test_sarif.py"
    assert report.assert_valid() is None


@pytest.mark.parametrize("failure", ["policy", "structural"])
def test_failed_build_reports_automatically_export_complete_captured_context(failure, validator):
    from tests.tooling_targets import invalid_builder

    builder = policy_builder("build") if failure == "policy" else invalid_builder()
    with pytest.raises(ContainerBuildError) as failed:
        builder.build(diagnostics=True)
    error = failed.value
    assert error.report is not None
    run = validated_run(error.report.to_sarif(), validator)
    assert error.report.to_sarif() == error.to_sarif()
    result = run["results"][0]
    assert "physicalLocation" in result["locations"][0]
    assert ("graphFingerprint" in run["properties"]) is (failure == "policy")


def test_report_can_render_after_container_is_closed_and_collected(validator):
    with policy_builder().build() as container:
        report = container.validation_report()
        expected = report.to_sarif()
        reference = weakref.ref(container)
    del container
    gc.collect()

    assert reference() is None
    assert report.to_sarif() == expected
    validated_run(report.to_sarif(), validator)
    with pytest.raises(AssertionError) as raised:
        report.assert_valid()
    assert str(raised.value) == expected


def test_overlay_report_automatically_uses_overlay_graph(validator):
    builder = ContainerBuilder()
    builder.register(Dependency, lifespan="singleton")
    parent = builder.build(diagnostics=True)
    overlay = parent.new_scope_builder()
    overlay.register(Service)
    overlay.add_validation_rule(
        forbid_dependency(cf.service_type_is(Service), cf.service_type_is(Dependency)), mode="validation"
    )
    scope = overlay.build(diagnostics=True)
    report = scope.validation_report()
    run = validated_run(report.to_sarif(), validator)
    assert run["properties"]["graphFingerprint"] == scope.graph.manifest(all_roots=True).fingerprint
    assert run["properties"]["graphFingerprint"] != parent.graph.manifest(all_roots=True).fingerprint
    assert run["results"][0]["locations"][0]["physicalLocation"]["artifactLocation"]["uri"] == "tests/test_sarif.py"


def test_assert_valid_still_raises_under_optimized_python():
    code = """
import json
from clean_ioc import BuildIssue, BuildReport, IssueSeverity
report = BuildReport((BuildIssue("required", IssueSeverity.error, "Required"),))
try:
    report.assert_valid()
except AssertionError as error:
    document = json.loads(str(error))
    if document["runs"][0]["results"][0]["ruleId"] != "required":
        raise RuntimeError("AssertionError did not contain the SARIF finding")
else:
    raise RuntimeError("Invalid report passed with Python -O")
"""
    result = subprocess.run([sys.executable, "-O", "-c", code], capture_output=True, text=True)  # noqa: S603
    assert result.returncode == 0, result.stderr
