"""Execution/analysis policy boundary, completed findings and failure coverage."""

import inspect
from typing import Generic, TypeVar

import pytest

import clean_ioc.container as compiler
from clean_ioc import (
    AnalysisReport,
    AnalysisResult,
    AnalysisRuntimeUnavailableError,
    BuilderAlreadyBuiltError,
    BuildIssue,
    CompilationBudget,
    Container,
    ContainerBuilder,
    ContainerBuildError,
    Expose,
    IssueSeverity,
    Provider,
    ScopeBuilder,
    ServiceGroup,
    Use,
    WarmupPlan,
    WarmupTarget,
)


class Leaf:
    pass


class Service:
    def __init__(self, leaf: Leaf):
        self.leaf = leaf


def make_valid():
    builder = ContainerBuilder()
    builder.set_provider_roots(())
    builder.register(Leaf, lifespan="singleton", root_policy="dependency_only")
    builder.register(Service)
    return builder


def codes(result):
    return {issue.code for issue in result.report.issues}


def test_build_skips_root_boundary_rule_call_and_iteration():
    events = []

    def rule(context):
        events.append("call")

        def issues():
            events.append("iteration")
            raise AssertionError("build must not inspect rules")
            yield

        return issues()

    builder = make_valid()
    builder.add_validation_rule(rule)
    boundary = builder.create_boundary("internal")
    boundary.register(str, instance="value")
    boundary.add_validation_rule(rule)
    with builder.build() as runtime:
        assert isinstance(runtime, Container)
        assert isinstance(runtime.resolve(Service).leaf, Leaf)
        assert not hasattr(runtime._plan, "build_report")
        assert not hasattr(runtime._plan, "validation_rules")
    assert events == []


def test_build_never_calls_policy_audits_even_with_rules(monkeypatch):
    def fail(*args, **kwargs):
        raise AssertionError("analysis-only function called during build")

    for name in (
        "factory_result_compatibility",
        "_validate_dependency_names",
        "_validate_service_groups",
        "_validate_per_call_implementation",
        "_blueprint_alias_errors",
        "_boundary_cycle",
        "_unreachable_component_issues",
        "_run_validation_rules",
    ):
        monkeypatch.setattr(compiler, name, fail)
    monkeypatch.setattr(compiler._Compiler, "_validate_captive_lifespan", fail)
    monkeypatch.setattr(compiler._Compiler, "_validate_runtime_context_dependency", fail)
    builder = make_valid()
    builder.add_validation_rule(fail)
    builder.create_boundary("internal").register(int, instance=1)
    with builder.build() as runtime:
        assert isinstance(runtime.resolve(Service), Service)


def test_analysis_exhausts_each_rule_once_preserves_findings_and_continues():
    events = []

    def broken(context):
        events.append("broken")
        yield BuildIssue("first", IssueSeverity.error, "first finding")
        raise ValueError("bad callback")

    def remaining(context):
        events.append("remaining")
        yield BuildIssue("next", IssueSeverity.warning, "later finding")

    builder = make_valid()
    builder.add_validation_rule(broken)
    builder.add_validation_rule(remaining)
    result = builder.analyse()
    assert isinstance(result, AnalysisResult)
    assert isinstance(result.report, AnalysisReport)
    assert result.emission_complete
    assert not result.report.complete
    assert not result.report.is_valid
    assert {"first", "next", "validation-rule-error"} <= codes(result)
    assert [outcome.status for outcome in result.report.rule_outcomes] == ["failed", "completed"]
    assert [issue.code for issue in result.report.rule_outcomes[0].issues] == ["first", "validation-rule-error"]
    for _ in range(2):
        result.report.to_text()
        result.report.to_json()
        result.report.to_sarif()
        with pytest.raises(AssertionError):
            result.report.assert_valid()
    with result.create_runtime() as runtime:
        assert isinstance(runtime.resolve(Service), Service)
    assert events == ["broken", "remaining"]
    result.close()


@pytest.mark.parametrize("invalid", [None, 42, [object()]])
def test_malformed_rule_result_is_failed_and_next_rule_completes(invalid):
    builder = make_valid()
    builder.add_validation_rule(lambda ctx: invalid)
    builder.add_validation_rule(lambda ctx: ())
    result = builder.analyse()
    assert [outcome.status for outcome in result.report.rule_outcomes] == ["failed", "completed"]
    assert "validation-rule-error" in codes(result)


def test_duplicate_and_boundary_rule_order_and_context():
    events = []

    def root(context):
        events.append(("root", context.boundary))
        return ()

    def local(context):
        events.append(("boundary", context.boundary))
        assert all(root.area == "alpha" for root in context.graph.roots)
        return ()

    builder = make_valid()
    builder.add_validation_rule(root)
    builder.add_validation_rule(root)
    boundary = builder.create_boundary("alpha")
    boundary.register(str, instance="local")
    boundary.add_validation_rule(local)
    result = builder.analyse()
    assert events == [("root", None), ("root", None), ("boundary", "alpha")]
    assert [outcome.declaration for outcome in result.report.rule_outcomes] == ["rule:1", "rule:2", "rule:3"]
    assert result.report.complete
    assert result.graph is not None


def test_inherited_rules_are_skipped_by_build_and_run_once_for_overlay_analysis():
    events = []

    def rule(context):
        events.append("parent")
        return ()

    builder = make_valid()
    builder.add_validation_rule(rule)
    with builder.analyse() as parent_result:
        parent = parent_result.create_runtime()
        assert events == ["parent"]
        with ScopeBuilder(parent, composition=parent_result.composition).build():
            pass
        assert events == ["parent"]
        overlay = ScopeBuilder(parent, composition=parent_result.composition)
        overlay.add_validation_rule(lambda ctx: events.append("child") or ())
        result = overlay.analyse()
        assert result.report.complete
        assert events == ["parent", "parent", "child"]


def test_policy_invalid_graph_preserves_wiring_and_runs_all_rules():
    calls = []

    def wrong_factory() -> str:
        raise AssertionError("No activation during compilation")

    def composition():
        b = ContainerBuilder()
        b.set_provider_roots(())
        b.register(Leaf, lifespan="scoped")
        b.register(Service, lifespan="singleton")
        b.register(int, factory=wrong_factory)
        b.add_validation_rule(lambda ctx: calls.append("rule") or ())
        return b

    with composition().build() as runtime:
        assert isinstance(runtime.resolve(Service).leaf, Leaf)
    assert calls == []
    result = composition().analyse()
    assert result.report.complete
    assert result.emission_complete
    assert not result.report.is_valid
    assert {"captive-dependency", "factory-return-type-mismatch"} <= codes(result)
    assert calls == ["rule"]


def test_missing_wiring_has_minimal_build_failure_and_unavailable_analysis_rules():
    def composition():
        b = ContainerBuilder()
        b.set_provider_roots(())
        b.register(Service)
        b.add_validation_rule(lambda ctx: pytest.fail("partial context passed as full graph"))
        return b

    builder = composition()
    with pytest.raises(ContainerBuildError) as raised:
        builder.build()
    assert raised.value.report is None
    assert raised.value.compiled_graph is None
    assert raised.value.partial_graph is None
    with pytest.raises(BuilderAlreadyBuiltError):
        builder.build()
    result = composition().analyse()
    assert not result.report.complete
    assert not result.emission_complete
    assert result.graph is None
    assert result.partial_graph is not None
    assert [o.status for o in result.report.rule_outcomes] == ["unavailable"]
    with pytest.raises(AnalysisRuntimeUnavailableError) as unavailable:
        result.create_runtime()
    assert unavailable.value.report is result.report


def test_single_attempt_input_rejection_and_callback_mutation_gate():
    builder = make_valid()
    with pytest.raises(TypeError):
        builder.build(build_args=[])
    assert not builder._built
    builder.add_validation_rule(lambda ctx: builder.register(bytes))
    result = builder.analyse()
    assert "validation-rule-error" in codes(result)
    with pytest.raises(BuilderAlreadyBuiltError):
        builder.analyse()


def test_budget_consumes_builder_and_makes_unrun_rules_explicit():
    builder = make_valid()
    builder.add_validation_rule(lambda ctx: ())
    result = builder.analyse(budget=CompilationBudget(graph_occurrences=0))
    assert not result.report.complete
    assert "compilation-budget-exceeded" in codes(result)
    assert [o.status for o in result.report.rule_outcomes] == ["interrupted"]
    with pytest.raises(BuilderAlreadyBuiltError):
        builder.register(bytes)


def test_build_inside_analysis_rule_is_independent_execution():
    events = []

    def rule(context):
        inner = make_valid()
        inner.add_validation_rule(lambda ctx: events.append("unexpected") or ())
        with inner.build() as runtime:
            assert isinstance(runtime.resolve(Service), Service)
        return ()

    builder = make_valid()
    builder.add_validation_rule(rule)
    result = builder.analyse()
    assert result.report.complete
    assert not events


def test_unknown_configured_keyword_emits_declared_value_and_reports_signature():
    def composition():
        b = ContainerBuilder()
        b.set_provider_roots(())
        b.register(Leaf, arguments={"missing": 42})
        return b

    runtime = composition().build()
    with pytest.raises(TypeError):
        runtime.resolve(Leaf)
    runtime.__exit__(None, None, None)
    result = composition().analyse()
    assert result.emission_complete
    assert result.report.complete
    assert "invalid-argument" in codes(result)


def test_explicit_provider_value_does_not_require_library_provider_target():
    value = object()

    class Consumer:
        def __init__(self, provider: Provider[Leaf]):
            self.provider = provider

    def composition():
        b = ContainerBuilder()
        b.set_provider_roots(())
        b.register(Consumer, arguments={"provider": value})
        return b

    with composition().build() as runtime:
        assert runtime.resolve(Consumer).provider is value
    result = composition().analyse()
    assert result.report.is_valid
    with result.create_runtime() as runtime:
        assert runtime.resolve(Consumer).provider is value


def test_sync_provider_async_target_is_analysis_policy_with_runtime_guard():
    async def make_leaf() -> Leaf:
        return Leaf()

    class Consumer:
        def __init__(self, provider: Provider[Leaf]):
            self.provider = provider

    def composition():
        b = ContainerBuilder()
        b.set_provider_roots(())
        b.register(Leaf, factory=make_leaf, root_policy="dependency_only")
        b.register(Consumer)
        return b

    with composition().build() as runtime:
        provider = runtime.resolve(Consumer).provider
        with pytest.raises(Exception):
            provider()
    result = composition().analyse()
    assert result.report.complete
    assert result.emission_complete
    assert "provider-requires-async" in codes(result)


def test_boundary_use_cycle_and_duplicate_same_identity_are_analysis_only():
    class Other:
        pass

    def composition():
        b = ContainerBuilder()
        b.set_provider_roots(())
        a = b.create_boundary("alpha", uses=[Use("beta", Other)], exposes=[Expose(Leaf), Expose(Leaf)])
        a.register(Leaf)
        z = b.create_boundary("beta", uses=[Use("alpha", Leaf), Use("alpha", Leaf)], exposes=[Expose(Other)])
        z.register(Other)
        return b

    with composition().build() as runtime:
        assert isinstance(runtime.resolve(Leaf), Leaf)
    result = composition().analyse()
    assert result.report.complete
    assert result.emission_complete
    assert {"boundary-use-cycle", "boundary-expose-duplicate", "boundary-use-ambiguous"} <= codes(result)


def test_incompatible_service_group_is_declaration_finding_not_registration_rejection():
    group = ServiceGroup("integers", service_type=int)

    def composition():
        b = ContainerBuilder()
        b.set_provider_roots(())
        b.register(Leaf, groups=(group,))
        return b

    with composition().build() as runtime:
        assert isinstance(runtime.resolve(Leaf), Leaf)
    result = composition().analyse()
    assert result.emission_complete
    assert "service-group-incompatible" in codes(result)


T = TypeVar("T")


class Box(Generic[T]):
    pass


def test_unresolved_return_only_typevar_does_not_block_known_activation():
    def factory() -> list[T]:
        return Leaf()  # ty: ignore[invalid-return-type]  # Deliberately invalid input.

    def composition():
        b = ContainerBuilder()
        b.set_provider_roots(())
        b.register(Leaf, factory=factory)
        return b

    with composition().build() as runtime:
        assert isinstance(runtime.resolve(Leaf), Leaf)
    result = composition().analyse()
    assert result.emission_complete
    assert "factory-return-type-unresolved" in codes(result)


def test_open_entrypoint_is_analysis_finding_without_fabricated_specialization():
    def composition():
        b = ContainerBuilder()
        b.set_provider_roots(())
        b.register(Box, root_policy="entrypoint")
        return b

    with composition().build() as runtime:
        assert runtime.selected_registrations == ()
    result = composition().analyse()
    assert result.emission_complete
    assert "missing-entrypoint" in codes(result)


def test_per_call_implementation_conformance_is_analysis_only():
    class Contract:
        def call(self):
            return 1

    class Incompatible:
        pass

    def composition():
        b = ContainerBuilder()
        b.set_provider_roots(())
        b.register(Contract, Incompatible, scope="per_call")
        return b

    with composition().build() as runtime:
        handle = runtime.resolve(Contract)
        with pytest.raises(AttributeError):
            handle.call()
    result = composition().analyse()
    assert result.emission_complete
    assert "per-call-unsupported-member" in codes(result)


def test_explicit_absent_decorated_keyword_is_emitted_and_audited():
    def decorate():
        return Leaf()

    def composition():
        b = ContainerBuilder()
        b.set_provider_roots(())
        b.register(Leaf)
        b.register_decorator(Leaf, decorate, decorated_arg="inner")
        return b

    with composition().build() as runtime:
        with pytest.raises(TypeError):
            runtime.resolve(Leaf)
    result = composition().analyse()
    assert result.emission_complete
    assert "invalid-decorator" in codes(result)


def test_warmup_policy_errors_keep_ordered_declared_targets():
    def composition():
        b = make_valid()
        b.add_warmup_plan(WarmupPlan("start", [WarmupTarget(Service), WarmupTarget(Service)]))
        return b

    with composition().build() as runtime:
        assert len(runtime._plan.warmup_steps["start"]) == 2
    result = composition().analyse()
    assert result.emission_complete
    assert {"warmup-non-singleton-target", "warmup-duplicate-target"} <= codes(result)


def test_removed_mode_arguments_and_single_rule_signature():
    builder = make_valid()
    assert "mode" not in inspect.signature(builder.add_validation_rule).parameters
    assert "mode" not in inspect.signature(builder.build).parameters
    with pytest.raises(TypeError):
        builder.add_validation_rule(lambda ctx: (), mode="validation")
    with pytest.raises(TypeError):
        builder.build(mode="analysis")
    assert not builder._built


def test_callback_with_hostile_exception_text_does_not_suppress_remaining_rules():
    class HostileError(Exception):
        def __str__(self):
            raise AssertionError("Exception text must not be evaluated")

    def first(context):
        yield BuildIssue("before-failure", IssueSeverity.warning, "Captured before failure")
        raise HostileError()

    builder = make_valid()
    builder.add_validation_rule(first)
    builder.add_validation_rule(lambda context: ())
    result = builder.analyse()
    assert [item.status for item in result.report.rule_outcomes] == ["failed", "completed"]
    assert {"before-failure", "validation-rule-error"} <= codes(result)


@pytest.mark.parametrize("operation", ["build", "analyse"])
@pytest.mark.parametrize("error_type", [MemoryError, RuntimeError, KeyboardInterrupt, SystemExit])
def test_fatal_failures_and_internal_compiler_defects_propagate(monkeypatch, operation, error_type):
    error = error_type("internal failure")

    def fail(*args, **kwargs):
        raise error

    monkeypatch.setattr(compiler._Compiler, "compile_execution" if operation == "build" else "compile", fail)
    builder = make_valid()
    with pytest.raises(error_type) as raised:
        getattr(builder, operation)()
    assert raised.value is error
    with pytest.raises(BuilderAlreadyBuiltError):
        builder.register(bytes)


@pytest.mark.parametrize("operation", ["build", "analyse"])
@pytest.mark.parametrize("callback_kind", ["filter", "derive", "template", "warmup"])
def test_callback_allocation_failure_propagates(monkeypatch, operation, callback_kind):
    from clean_ioc import derive

    error = MemoryError("callback allocation failure")

    def fail(*args, **kwargs):
        raise error

    builder = make_valid()
    if callback_kind == "filter":
        builder.register(bytes, instance=b"", when=fail)
    elif callback_kind == "derive":
        builder.register(Service, arguments={"leaf": derive(fail)})
    elif callback_kind == "template":
        builder.register_registration_template(for_each=Leaf, template=fail)
    else:
        builder.add_warmup_plan(WarmupPlan("start", [WarmupTarget(Service, filter=fail)]))
    with pytest.raises(MemoryError) as raised:
        getattr(builder, operation)()
    assert raised.value is error


def test_rule_allocation_failure_propagates_instead_of_becoming_a_finding():
    error = MemoryError("rule allocation failure")

    def fail(context):
        raise error

    builder = make_valid()
    builder.add_validation_rule(fail)
    with pytest.raises(MemoryError) as raised:
        builder.analyse()
    assert raised.value is error


def test_rule_budget_preserves_yielded_findings_and_emitted_plan():
    builder = make_valid()

    def unbounded(context):
        index = 0
        while True:
            yield BuildIssue(f"finding-{index}", IssueSeverity.warning, "A finding")
            index += 1

    builder.add_validation_rule(unbounded)
    builder.add_validation_rule(lambda ctx: pytest.fail("budget must stop later invocation"))
    result = builder.analyse(budget=CompilationBudget(preparation_operations=100))
    assert result.emission_complete
    assert not result.report.complete
    assert "compilation-budget-exceeded" in codes(result)
    assert "finding-0" in codes(result)
    assert [outcome.status for outcome in result.report.rule_outcomes] == ["interrupted", "interrupted"]
    with result.create_runtime() as runtime:
        assert isinstance(runtime.resolve(Service), Service)


def test_partial_analysis_counts_successful_and_failed_independent_roots():
    class Missing:
        pass

    class Broken:
        def __init__(self, missing: Missing):
            pass

    builder = ContainerBuilder()
    builder.set_provider_roots(())
    builder.register(Leaf)
    builder.register(Broken)
    result = builder.analyse()
    assert not result.report.complete
    assert result.report.requested_roots == 2
    assert result.report.compiled_roots == 1
    assert result.report.failed_roots == 1


@pytest.mark.parametrize("placement", ["ordinary", "private", "generated", "deferred"])
def test_captive_audit_covers_mixed_paths_without_blocking_execution(placement):
    from clean_ioc import RegistrationTemplate

    class Consumer:
        def __init__(self, service: Provider[Service]):
            self.service = service

    def composition():
        builder = ContainerBuilder()
        builder.set_provider_roots(())
        layer = builder.create_boundary("private", exposes=[Expose(Service)]) if placement == "private" else builder
        layer.register(Leaf, lifespan="scoped", root_policy="dependency_only")
        if placement == "generated":
            layer.register_registration_template(
                for_each=Leaf, template=lambda source: RegistrationTemplate(Service, lifespan="singleton")
            )
        else:
            layer.register(
                Service,
                lifespan="singleton",
                root_policy="dependency_only" if placement == "deferred" else "resolvable",
            )
        if placement == "deferred":
            layer.register(Consumer)
        return builder

    with composition().build() as runtime:
        service = runtime.resolve(Consumer).service() if placement == "deferred" else runtime.resolve(Service)
        assert isinstance(service.leaf, Leaf)
    result = composition().analyse()
    assert result.emission_complete
    assert result.report.complete
    assert "captive-dependency" in codes(result)


def test_generated_decorator_mismatch_and_configured_names_are_analysis_findings():
    from clean_ioc import DecoratorTemplate, DerivedServices

    class Source:
        pass

    def decorate(inner: int) -> str:
        return inner  # ty: ignore[invalid-return-type]  # Deliberately invalid input.

    def composition():
        builder = make_valid()
        builder.register(Source)
        builder.register_decorator_template(
            for_each=Source,
            template=lambda source: DecoratorTemplate(
                DerivedServices(Service), decorate, decorated_arg="inner", arguments={"extra": 1}
            ),
        )
        return builder

    with composition().build() as runtime:
        with pytest.raises(TypeError):
            runtime.resolve(Service)
    result = composition().analyse()
    assert result.emission_complete
    assert result.report.complete
    assert {"invalid-decorator", "invalid-argument"} & codes(result)
    assert len(result.report.errors) >= 2


def test_ordinary_decorator_return_only_and_decorated_only_variables_do_not_block_emission():
    def decorate(inner: list[T]) -> list[T]:
        return inner

    def composition():
        builder = make_valid()
        builder.register_decorator(Service, decorate, decorated_arg="inner")
        return builder

    with composition().build() as runtime:
        assert isinstance(runtime.resolve(Service), Service)
    result = composition().analyse()
    assert result.emission_complete
    assert "invalid-decorator" in codes(result)


def test_rejected_and_unused_memberships_are_audited_without_emitting_them():
    group = ServiceGroup("integer-service", service_type=int)

    def composition():
        builder = make_valid()
        builder.register(bytes, instance=b"", groups=[group], when=lambda component: False)
        builder.register(str, instance="", groups=[group], root_policy="dependency_only")
        return builder

    with composition().build() as runtime:
        assert all(info.service_type not in (str, bytes) for info in runtime.selected_registrations)
    result = composition().analyse()
    assert result.report.complete
    assert "service-group-incompatible" in codes(result)
    assert {issue.root for issue in result.report.errors if issue.code == "service-group-incompatible"} == {
        "str",
        "bytes",
    }


def test_per_call_supplied_instance_keeps_identity_without_adopting_cleanup():
    events = []

    class Contract:
        def identity(self):
            return id(self)

        def close(self):
            events.append("close")

    instance = Contract()

    def composition():
        builder = ContainerBuilder()
        builder.set_provider_roots(())
        builder.register(Contract, instance=instance, scope="per_call")
        return builder

    with composition().build() as runtime:
        handle = runtime.resolve(Contract)
        assert handle.identity() == handle.identity() == id(instance)
    result = composition().analyse()
    assert result.report.is_valid
    assert events == []


@pytest.mark.parametrize("nominal", [True, False])
def test_missing_union_or_nominal_activation_fails_only_when_selected(nominal):
    from typing import NewType

    Identifier = NewType("Identifier", int)
    key = Identifier if nominal else int | str
    unused = make_valid()
    unused.register(key, root_policy="dependency_only")
    with unused.build() as runtime:
        assert isinstance(runtime.resolve(Service), Service)
    selected = make_valid()
    selected.register(key)
    with pytest.raises(ContainerBuildError) as raised:
        selected.build()
    assert raised.value.code == "missing-activation-source"
    assert raised.value.report is None


def test_unknown_factory_reasoning_is_explicit_without_failing_valid_wiring():
    from typing import Any

    def create() -> Any:
        return Leaf()

    builder = ContainerBuilder()
    builder.register(Leaf, factory=create)
    result = builder.analyse()
    assert result.emission_complete
    assert result.report.complete
    assert any(stage.status == "unknown" for stage in result.report.stage_outcomes)


@pytest.mark.parametrize("boundary", [False, True])
def test_failed_architecture_entrypoint_filter_marks_check_incomplete_and_runs_rules(boundary):
    events = []

    def broken_filter(component):
        events.append("filter")
        raise ValueError("broken filter")

    def composition():
        builder = make_valid()
        layer = builder.create_boundary("feature") if boundary else builder
        if boundary:
            layer.register(Leaf)
        layer.mark_entrypoint(Leaf if boundary else Service, filter=broken_filter)
        builder.add_validation_rule(lambda context: events.append("rule") or ())
        return builder

    with composition().build():
        pass
    assert events == []
    result = composition().analyse()
    assert result.emission_complete
    assert not result.report.complete
    assert "entrypoint-filter-error" in codes(result)
    assert events == ["filter", "rule"]
    assert result.report.rule_outcomes[0].status == "completed"
    assert any(stage.status == "failed" for stage in result.report.stage_outcomes)


def test_successful_diagnostic_retries_preserve_original_callback_failure_and_no_runtime():
    calls = []

    def stateful(component):
        calls.append(component.service_type)
        if len(calls) == 1:
            raise ValueError("primary callback failed")
        return True

    builder = ContainerBuilder()
    builder.set_provider_roots(())
    builder.register(Leaf, when=stateful)
    builder.add_validation_rule(lambda context: pytest.fail("No complete primary graph"))
    result = builder.analyse()
    assert len(calls) == 2
    assert not result.emission_complete
    assert not result.report.complete
    assert result.partial_graph.inconsistent_retries
    assert [issue.code for issue in result.report.errors] == ["compile-error"]
    assert result.report.errors[0].path[0].endswith("Leaf")
    assert result.report._evidence[0].attempt_ref == "attempt:1"
    assert result.report.rule_outcomes[0].status == "unavailable"
    result.report.to_json()
    assert len(calls) == 2


def test_partial_analysis_preserves_policy_findings_collected_before_wiring_failure():
    def wrong() -> str:
        return "value"

    builder = ContainerBuilder()
    builder.set_provider_roots(())
    builder.register(int, factory=wrong)
    builder.register(Service)
    result = builder.analyse()
    assert not result.emission_complete
    assert {"factory-return-type-mismatch", "missing-component"} <= codes(result)


def test_report_reads_and_runtime_creation_do_not_replay_wiring_callbacks():
    from clean_ioc import RegistrationTemplate

    events = []

    def selected(component):
        events.append("select")
        return True

    def template(source):
        events.append("template")
        return RegistrationTemplate(Service)

    builder = ContainerBuilder()
    builder.set_provider_roots(())
    builder.register(Leaf, when=selected)
    builder.register_registration_template(for_each=Leaf, template=template)
    builder.add_validation_rule(lambda context: events.append("rule") or ())
    result = builder.analyse()
    assert result.report.complete
    before = list(events)
    for _ in range(2):
        result.report.to_json()
        result.report.to_text()
        result.report.to_sarif()
        with result.create_runtime() as runtime:
            assert isinstance(runtime.resolve(Service), Service)
    assert events == before


def test_failed_warmup_binding_is_incomplete_and_rules_are_unavailable():
    builder = make_valid()
    builder.add_warmup_plan(WarmupPlan("missing", [WarmupTarget(bytes)]))
    builder.add_validation_rule(lambda context: pytest.fail("Incomplete warmup plan"))
    result = builder.analyse()
    assert not result.emission_complete
    assert not result.report.complete
    assert result.graph is None
    assert result.partial_graph is not None
    assert "warmup-missing-component" in codes(result)
    assert result.report.rule_outcomes[0].status == "unavailable"


def test_partial_rule_budget_preserves_equal_findings_from_distinct_boundaries():
    calls = []

    def first(context):
        calls.append(context.boundary)
        yield next(context.graph.walk()).issue("same-policy", "Same public message")

    def second(context):
        yield from first(context)
        while True:
            yield BuildIssue("warning", IssueSeverity.warning, "Repeated budget work")

    builder = ContainerBuilder().set_provider_roots(())
    for name, rule in (("a", first), ("b", second)):
        boundary = builder.create_boundary(name)
        boundary.register(Leaf)
        boundary.add_validation_rule(rule)
    result = builder.analyse(budget=CompilationBudget(preparation_operations=30))
    assert calls == ["a", "b"]
    findings = [issue for issue in result.report.errors if issue.code == "same-policy"]
    assert len(findings) == 2 and findings[0] == findings[1]
    assert {issue._origin.boundary for issue in findings} == {"a", "b"}
    assert result.graph is not None and result.emission_complete
    assert not result.report.complete
    assert not result.selection_census().complete
    triage = result.triage_report()
    assert triage._issue_boundary(0) == ("a", True)
    assert triage._issue_boundary(1) == ("b", True)
    assert triage.report is result.report
    for _ in range(3):
        assert result.triage_report().to_json() == triage.to_json()
        assert result.selection_census().to_json() == result.selection_census().to_json()
        assert result.report.to_sarif()
    with result.create_runtime() as runtime:
        assert runtime.components == ()
    assert calls == ["a", "b"]


def test_bounded_generic_decorator_audit_uses_authored_contract_and_rejects_concrete_mismatch():
    from typing import Generic, TypeVar

    class Command:
        pass

    class Specific(Command):
        pass

    class Other(Command):
        pass

    T = TypeVar("T", bound=Command)

    class Handler(Generic[T]):
        pass

    class Forwarder(Handler[Command]):
        pass

    class Wrapper(Generic[T]):
        def __init__(self, handler: Handler[T]):
            self.handler = handler

    class WrongWrapper(Generic[T]):
        def __init__(self, handler: Handler[Other]):
            self.handler = handler

    def compose(wrapper):
        builder = ContainerBuilder()
        builder.register(Handler[Specific], Forwarder)
        builder.register_decorator(Handler, wrapper, decorated_arg="handler")
        return builder

    result = compose(Wrapper).analyse()
    result.report.assert_valid()
    assert isinstance(result.create_runtime().resolve(Handler[Specific]).handler, Forwarder)
    invalid = compose(WrongWrapper).analyse()
    assert any(issue.code == "invalid-decorator" for issue in invalid.report.errors)
    assert isinstance(compose(WrongWrapper).build().resolve(Handler[Specific]).handler, Forwarder)


def test_completed_analysis_preserves_equal_findings_from_distinct_boundaries():
    calls = []

    def rule(context):
        calls.append(context.boundary)
        yield next(context.graph.walk()).issue("same-policy", "Same public message")

    builder = ContainerBuilder().set_provider_roots(())
    for name in ("a", "b"):
        boundary = builder.create_boundary(name)
        boundary.register(Leaf)
        boundary.add_validation_rule(rule)
    result = builder.analyse()
    assert result.report.complete and result.emission_complete
    findings = result.report.errors
    assert len(findings) == 2 and findings[0] == findings[1]
    assert {issue._origin.boundary for issue in findings} == {"a", "b"}
    triage = result.triage_report()
    assert triage._issue_boundary(0) == ("a", True)
    assert triage._issue_boundary(1) == ("b", True)
    before = list(calls)
    for _ in range(3):
        result.report.to_sarif()
        result.selection_census().to_json()
        result.triage_report().to_json()
    assert calls == before == ["a", "b"]
