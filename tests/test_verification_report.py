"""The direct public verification contract, independent of runtime ownership."""

import json
import subprocess
import sys
from dataclasses import FrozenInstanceError

import pytest

import clean_ioc
from clean_ioc import (
    BuildIssue,
    ContainerBuilder,
    IssueSeverity,
    ScopeBuilder,
    VerificationReport,
    VerificationRuntimeUnavailableError,
)


def test_public_api_has_one_direct_report_without_legacy_aliases():
    for name in ("AnalysisResult", "AnalysisReport", "AnalysisRuntimeUnavailableError"):
        assert not hasattr(clean_ioc, name)
    for builder in (ContainerBuilder, ScopeBuilder):
        assert not hasattr(builder, "analyse")
        assert hasattr(builder, "verify")
    with ContainerBuilder().verify() as report:
        assert isinstance(report, VerificationReport)
        assert not hasattr(report, "report")
        report.assert_valid()
        assert report.is_valid and report.complete and report.emission_complete


def test_findings_stay_frozen_and_readable_after_runtime_ownership_closes():
    calls = []
    builder = ContainerBuilder()
    builder.add_validation_rule(
        lambda _: calls.append("rule") or [BuildIssue("notice", IssueSeverity.warning, "Notice")]
    )
    report = builder.verify()
    before = report.to_json()
    first = report.create_runtime()
    second = report.create_runtime()
    assert first is not second
    with pytest.raises(FrozenInstanceError):
        report.complete = False  # ty: ignore[invalid-assignment]
    report.close()
    assert first._closed and second._closed
    assert report.to_json() == before
    assert report.assert_valid() is None
    assert report.warnings and not report.errors
    assert calls == ["rule"]
    with pytest.raises(RuntimeError, match="closed"):
        report.create_runtime()


def test_manually_constructed_valid_findings_have_no_execution_plan():
    report = VerificationReport()
    report.assert_valid()
    assert report.is_valid and not report.emission_complete
    assert report.selected_registrations is None
    with pytest.raises(VerificationRuntimeUnavailableError) as caught:
        report.create_runtime()
    assert caught.value.report is report


def test_direct_builder_assertion_remains_active_under_optimized_python():
    source = """
from clean_ioc import BuildIssue, ContainerBuilder, IssueSeverity
builder = ContainerBuilder()
builder.add_validation_rule(lambda _: [BuildIssue('required', IssueSeverity.error, 'Required')])
report = builder.verify()
try:
    report.assert_valid()
except AssertionError as error:
    print(error)
else:
    raise RuntimeError('Verification assertion was disabled')
"""
    command = [sys.executable, "-O", "-c", source]
    completed = subprocess.run(command, check=True, capture_output=True, text=True)  # noqa: S603
    result = json.loads(completed.stdout)["runs"][0]["results"][0]
    assert result["ruleId"] == "required"
