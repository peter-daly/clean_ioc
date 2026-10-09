"""Contract checks for optional build profiling."""

from __future__ import annotations

import json
import sys
import types
from typing import Any, cast

import pytest
from typing_extensions import TypeAliasType

from clean_ioc import (
    CompilationProfiler,
    ContainerBuilder,
    ContainerBuildError,
    DecoratorTemplate,
    DerivedServices,
)
from clean_ioc.cli import main


class TemplateSource:
    pass


class TemplateTarget:
    pass


class TemplateWrapper(TemplateTarget):
    def __init__(self, inner: TemplateTarget):
        self.inner = inner


def test_nested_self_time_stays_correct_when_child_detail_overflows():
    ticks = iter(range(0, 1000, 10))
    profile = CompilationProfiler(max_records=1, _clock=lambda: next(ticks))
    profile._begin()

    def parent():
        profile.call("primary compilation", "child", lambda: None)

    profile.call("primary compilation", "phase", parent)
    profile._finish("completed")
    report = profile.report()
    assert report.elapsed_ns == 50
    assert report.phases_ns == (("primary compilation", 30), ("other build work", 20))
    assert report.spans[0].inclusive_ns == 30
    assert report.spans[0].self_ns == 20
    assert report.omitted_records == 1
    assert not report.to_dict()["attribution_complete"]
    assert report.to_json() == report.to_json()


def test_clock_failure_does_not_replace_application_error():
    calls = 0

    def clock():
        nonlocal calls
        calls += 1
        if calls == 3:
            raise RuntimeError("clock failed")
        return calls * 10

    profile = CompilationProfiler(_clock=clock)
    profile._begin()

    def fail():
        raise ValueError("application failure")

    with pytest.raises(ValueError, match="application failure"):
        profile.call("primary compilation", "callback", fail)
    profile._finish("failed")
    assert profile.report().diagnostics


def test_pre_graph_preparation_failure_leaves_a_partial_profile_and_repairable_builder():
    builder = ContainerBuilder()
    profile = CompilationProfiler()
    with pytest.raises(TypeError):
        builder.build(build_args=cast(Any, {1: "PRIVATE-BUILD-VALUE"}), profile=profile)
    report = profile.report()
    assert report.state == "failed"
    assert any(span.phase == "discovery and blueprint preparation" and span.state == "failed" for span in report.spans)
    assert "PRIVATE-BUILD-VALUE" not in report.to_json()
    builder.build(profile=CompilationProfiler())


def test_failed_build_preserves_partial_primary_and_retry_measurements():
    class Root:
        def __init__(self, missing: str):
            self.missing = missing

    builder = ContainerBuilder()
    builder.register(Root)
    profile = CompilationProfiler(max_records=100)
    with pytest.raises(ContainerBuildError):
        builder.build(profile=profile)
    report = profile.report()
    assert report.state == "failed"
    assert report.elapsed_ns >= sum(dict(report.phases_ns).values())
    assert dict(report.counters.values)["diagnostic root attempts"] >= 1
    assert any(span.attempt == "primary" for span in report.spans)
    assert any(span.attempt and span.attempt.startswith("retry:") for span in report.spans)
    with pytest.raises(ValueError, match="single-use"):
        builder.build(profile=profile)
    builder.register(str, instance="repaired")
    assert builder.build(profile=CompilationProfiler()).resolve(Root).missing == "repaired"


def test_profiled_build_runs_callbacks_once_and_redacts_build_values():
    calls: list[str] = []

    class Root:
        pass

    def predicate(component):
        calls.append("predicate")
        return True

    def rule(graph):
        calls.append("rule start")
        yield from ()
        calls.append("rule end")

    builder = ContainerBuilder()
    builder.register(Root, when=predicate)
    builder.add_validation_rule(rule)
    profile = CompilationProfiler(max_records=100)
    container = builder.build(build_args={"secret": "PRIVATE-BUILD-VALUE"}, profile=profile)
    assert container.resolve(Root).__class__ is Root
    assert calls == ["predicate", "rule start", "rule end"]
    report = profile.report()
    assert report.state == "completed"
    assert dict(report.counters.values)["build validation rule calls"] == 1
    assert any(span.operation == "validation rule" for span in report.spans)
    assert "PRIVATE-BUILD-VALUE" not in report.to_json()


def test_overlay_profiles_anchored_reuse_without_charging_parent_build():
    class Shared:
        pass

    root_builder = ContainerBuilder()
    root_builder.register(Shared, lifespan="singleton")
    parent = root_builder.build()
    profile = CompilationProfiler()
    overlay = parent.new_scope_builder().build(profile=profile)
    assert overlay.resolve(Shared) is parent.resolve(Shared)
    assert dict(profile.report().counters.values)["anchored parent plan reuses"] >= 1


def test_distinct_declarations_of_one_implementation_have_distinct_hotspots():
    class Service:
        pass

    builder = ContainerBuilder()
    builder.register(Service, name="PRIVATE-FIRST")
    builder.register(Service, name="PRIVATE-SECOND")
    profile = CompilationProfiler()
    builder.build(profile=profile)
    hotspots = [item for item in profile.report().costly_definitions if item.operation == "candidate compilation"]
    assert len(hotspots) == 2
    assert len({item.definition_ref for item in hotspots}) == 2
    assert {item.definition for item in hotspots} == {hotspots[0].definition}
    assert "PRIVATE-FIRST" not in profile.report().to_json()
    assert "PRIVATE-SECOND" not in profile.report().to_json()


def test_alias_failure_and_post_template_check_are_alias_phase_work():
    target: Any = 42
    invalid = TypeAliasType("invalid", target)
    broken = ContainerBuilder()
    broken.register(invalid, instance=object())
    failed_profile = CompilationProfiler()
    with pytest.raises(ContainerBuildError):
        broken.build(profile=failed_profile)
    assert dict(failed_profile.report().phases_ns)["alias and boundary preparation"] > 0

    builder = ContainerBuilder()
    builder.register(TemplateSource)
    builder.register(TemplateTarget)
    builder.register_decorator_template(
        for_each=TemplateSource,
        template=lambda source: DecoratorTemplate(DerivedServices(TemplateTarget), TemplateWrapper),
    )
    profile = CompilationProfiler()
    builder.build(profile=profile)
    alias_spans = [
        span
        for span in profile.report().spans
        if span.phase == "alias and boundary preparation" and span.operation == "phase"
    ]
    assert len(alias_spans) >= 4


def test_cli_runs_one_factory_and_rejects_built_targets(monkeypatch, capsys):
    module = types.ModuleType("profile_test_target")
    count = 0

    def factory():
        nonlocal count
        count += 1
        builder = ContainerBuilder()
        builder.register(int, instance=1)
        return builder

    module.__dict__["factory"] = factory
    module.__dict__["built"] = ContainerBuilder().build()

    class NeedsString:
        def __init__(self, value: str):
            self.value = value

    def broken_factory():
        builder = ContainerBuilder()
        builder.register(NeedsString)
        return builder

    module.__dict__["broken_factory"] = broken_factory
    monkeypatch.setitem(sys.modules, module.__name__, module)
    assert main(["profile", "profile_test_target:factory", "--format", "json"]) == 0
    assert count == 1
    assert json.loads(capsys.readouterr().out)["state"] == "completed"
    assert main(["profile", "profile_test_target:built"]) == 2
    assert "unbuilt builder" in capsys.readouterr().err
    assert main(["profile", "profile_test_target:factory", "--max-records", "-1"]) == 2
    assert main(["profile", "profile_test_target:broken_factory", "--format", "json"]) == 1
    assert json.loads(capsys.readouterr().out)["state"] == "failed"
