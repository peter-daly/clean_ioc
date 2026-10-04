"""Budgets count admitted compiler work, including hidden provider expansion."""

import dataclasses
import json
from typing import Any, Generic, TypeVar, cast

import pytest

from clean_ioc import (
    BuildIssue,
    BuildMatrix,
    BuildVariant,
    CompilationBudget,
    CompilationProfiler,
    ContainerBuilder,
    ContainerBuildError,
    DecoratorTemplate,
    DerivedServices,
    Expose,
    IssueSeverity,
    RegistrationTemplate,
)
from clean_ioc.cli import _filtered_report


class Leaf:
    activations = 0

    def __init__(self):
        Leaf.activations += 1


class MissingRoot:
    def __init__(self, value: str):
        self.value = value


class Worker:
    def __init__(self, leaf: Leaf):
        self.leaf = leaf


class WrappedLeaf(Leaf):
    def __init__(self, inner: Leaf):
        self.inner = inner


T = TypeVar("T")


class Box(Generic[T]):
    pass


def box() -> Box[T]:
    return Box()


def leaf_builder():
    builder = ContainerBuilder()
    builder.register(Leaf)
    return builder


def failure(builder, budget, *, profile=None):
    with pytest.raises(ContainerBuildError) as caught:
        builder.build(budget=budget, profile=profile)
    error = caught.value
    assert error.compiled_graph is None
    assert error.report is not None and not error.report.is_valid
    assert error.partial_graph is not None and error.partial_graph.truncated
    issue = next(issue for issue in error.report.errors if issue.code == "compilation-budget-exceeded")
    assert issue.budget is not None
    assert issue.budget.attempted > issue.budget.maximum
    return error, issue.budget


@pytest.mark.parametrize("field", [field.name for field in dataclasses.fields(CompilationBudget)])
@pytest.mark.parametrize("value", [True, False, -1, 0.1, "1", object()])
def test_limits_reject_non_builtin_nonnegative_integers(field, value):
    with pytest.raises(ValueError):
        CompilationBudget(**{field: value})


def test_hostile_int_subclass_is_rejected_without_comparison():
    class Unchecked(int):
        def __lt__(self, other):
            raise AssertionError("comparison must not run")

    with pytest.raises(ValueError):
        CompilationBudget(graph_occurrences=Unchecked(0))
    with pytest.raises(dataclasses.FrozenInstanceError):
        cast(Any, CompilationBudget()).graph_occurrences = 1
    with pytest.raises(TypeError, match="budget must be"):
        leaf_builder().build(budget=cast(Any, {"graph_occurrences": 0}))


def test_occurrence_exact_threshold_includes_eager_provider_clones_and_no_activation():
    before = Leaf.activations
    profile = CompilationProfiler(max_records=0)
    with leaf_builder().build(budget=CompilationBudget(graph_occurrences=45), profile=profile) as owner:
        assert len(owner.graph.roots) == 1
    assert Leaf.activations == before
    assert dict(profile.report().budget_usage or ()) == {
        "graph_occurrences": 45,
        "active_dependency_depth": 3,
        "specialization_materializations": 0,
        "generated_template_outputs": 0,
        "diagnostic_attempts": 0,
        "preparation_operations": 1,
    }
    profile = CompilationProfiler()
    _, limit = failure(leaf_builder(), CompilationBudget(graph_occurrences=44), profile=profile)
    assert (limit.admitted, limit.attempted) == (44, 45)
    assert profile.report().counters.to_dict()["graph occurrences"] == 44
    assert profile.report().state == "failed"
    assert all(span.state != "interrupted" for span in profile.report().spans)


def test_zero_is_not_unlimited_and_refused_depth_does_not_admit_occurrence():
    profile = CompilationProfiler()
    error, fact = failure(leaf_builder(), CompilationBudget(active_dependency_depth=0), profile=profile)
    assert fact.admitted == 0 and fact.attempted == 1
    assert dict(fact.usage)["graph_occurrences"] == 0
    assert "graph occurrences" not in profile.report().counters.to_dict()
    assert error.partial_graph is not None and error.partial_graph.total_attempts == 1
    _, fact = failure(leaf_builder(), CompilationBudget(graph_occurrences=0))
    assert dict(fact.usage)["active_dependency_depth"] == 0


def test_depth_is_a_path_peak_across_roots_including_synthetic_metadata():
    builder = leaf_builder()
    builder.register(Worker)
    profile = CompilationProfiler()
    with builder.build(budget=CompilationBudget(), profile=profile):
        pass
    depth = dict(profile.report().budget_usage or ())["active_dependency_depth"]
    assert depth == 4
    builder = leaf_builder()
    builder.register(Worker)
    with builder.build(budget=CompilationBudget(active_dependency_depth=depth)):
        pass
    builder = leaf_builder()
    builder.register(Worker)
    _, fact = failure(builder, CompilationBudget(active_dependency_depth=depth - 1))
    assert fact.attempted == depth


def test_budget_fingerprint_and_disabled_profile_compatibility():
    with leaf_builder().build() as plain, leaf_builder().build(budget=CompilationBudget()) as limited:
        assert plain.graph.manifest().fingerprint == limited.graph.manifest().fingerprint
    profile = CompilationProfiler()
    with leaf_builder().build(profile=profile):
        pass
    assert "budget" not in profile.report().to_dict()


def test_exhaustion_exports_are_stable_redacted_source_linked_and_cannot_be_ignored():
    builder = leaf_builder()
    profile = CompilationProfiler()
    with pytest.raises(ContainerBuildError) as caught:
        builder.build(
            budget=CompilationBudget(graph_occurrences=0), build_args={"secret": "PRIVATE-VALUE"}, profile=profile
        )
    error = caught.value
    assert error.report is not None and error.partial_graph is not None
    assert not _filtered_report(error.report, {"compilation-budget-exceeded"}).is_valid
    assert error.report.to_json() == error.report.to_json()
    result = json.loads(error.to_sarif())["runs"][0]["results"][0]
    assert result["properties"]["compilationBudget"]["maximum"] == 0
    assert result["locations"][0]["physicalLocation"]["artifactLocation"]["uri"].endswith("test_compilation_budget.py")
    exports = (
        error.report.to_text(),
        error.report.to_json(),
        error.to_sarif(),
        error.partial_graph.to_json(),
        error.triage_report().to_json(),
        profile.report().to_json(),
    )
    assert all("PRIVATE-VALUE" not in value and builder._owner_token not in value for value in exports)
    assert "omitted" in error.triage_report().to_text()


def test_failed_builder_can_rebuild_with_a_fresh_allowance():
    builder = leaf_builder()
    failure(builder, CompilationBudget(graph_occurrences=44))
    with builder.build(budget=CompilationBudget(graph_occurrences=45)) as owner:
        assert isinstance(owner.resolve(Leaf), Leaf)


def test_diagnostic_zero_retains_primary_missing_finding_and_no_retry():
    builder = ContainerBuilder()
    builder.register(MissingRoot)
    profile = CompilationProfiler()
    error, fact = failure(builder, CompilationBudget(diagnostic_attempts=0), profile=profile)
    assert fact.phase == "diagnostic root retries"
    assert [issue.code for issue in error.report.errors] == ["missing-component", "compilation-budget-exceeded"]
    assert dict(fact.usage)["graph_occurrences"] == 1
    assert "diagnostic root attempts" not in profile.report().counters.to_dict()
    assert error.partial_graph.total_attempts == 1
    assert error.partial_graph.omitted_roots == 1
    builder.register(str, instance="repaired")
    with builder.build(budget=CompilationBudget(diagnostic_attempts=0)) as owner:
        assert owner.resolve(MissingRoot).value == "repaired"


def test_occurrence_allowance_survives_retry_and_preserves_original():
    builder = ContainerBuilder()
    builder.register(MissingRoot)
    profile = CompilationProfiler()
    error, fact = failure(builder, CompilationBudget(graph_occurrences=1), profile=profile)
    assert fact.phase == "diagnostic root retries"
    assert [issue.code for issue in error.report.errors] == ["missing-component", "compilation-budget-exceeded"]
    assert dict(fact.usage)["diagnostic_attempts"] == 1
    assert profile.report().counters.to_dict()["graph occurrences"] == 1
    assert error.partial_graph.total_attempts == 2


def test_materializations_count_cache_misses_and_refuse_before_registration_creation():
    builder = ContainerBuilder()
    builder.register(Box, factory=box)
    builder.mark_entrypoint(Box[int])
    profile = CompilationProfiler()
    _, fact = failure(builder, CompilationBudget(specialization_materializations=0), profile=profile)
    assert fact.kind == "specialization_materializations"
    assert fact.admitted == 0
    assert "factory specialization materializations" not in profile.report().counters.to_dict()
    builder = ContainerBuilder()
    builder.register(Box, factory=box)
    builder.mark_entrypoint(Box[int])
    profile = CompilationProfiler()
    with builder.build(budget=CompilationBudget(specialization_materializations=1), profile=profile):
        pass
    assert dict(profile.report().budget_usage or ())["specialization_materializations"] == 1


def test_template_metadata_occurrences_and_lazy_inspection_share_allowance():
    calls = []
    builder = leaf_builder()

    def predicate(source):
        calls.append("filter")
        return bool(source.dependencies) or True

    builder.register_registration_template(
        for_each=Leaf, source_filter=predicate, template=lambda source: RegistrationTemplate(Worker)
    )
    profile = CompilationProfiler()
    _, fact = failure(builder, CompilationBudget(graph_occurrences=1), profile=profile)
    assert fact.phase == "registration-template expansion"
    assert calls == ["filter"]
    assert dict(fact.usage)["graph_occurrences"] == 1
    assert profile.report().counters.to_dict().get("graph occurrences", 0) == 0


@pytest.mark.parametrize("decorator", [False, True])
def test_template_zero_output_prevents_factory_and_recovery(decorator):
    calls = []
    builder = leaf_builder()

    def template(source):
        calls.append("factory")
        return DecoratorTemplate(DerivedServices(Leaf), WrappedLeaf) if decorator else RegistrationTemplate(Worker)

    if decorator:
        builder.register_decorator_template(for_each=Leaf, template=template)
    else:
        builder.register_registration_template(for_each=Leaf, template=template)
    _, fact = failure(builder, CompilationBudget(generated_template_outputs=0))
    assert fact.kind == "generated_template_outputs" and fact.admitted == 0
    assert calls == []


def test_first_exhaustion_survives_callback_catching_control_signal_and_throwing_again():
    calls = []
    builder = leaf_builder()

    def predicate(source):
        calls.append("filter")
        try:
            _ = source.dependencies
        except BaseException:
            raise ValueError("PRIVATE-EXCEPTION") from None
        return True

    builder.register_registration_template(
        for_each=Leaf, source_filter=predicate, template=lambda source: RegistrationTemplate(Worker)
    )
    error, fact = failure(builder, CompilationBudget(graph_occurrences=1))
    assert fact.phase == "registration-template expansion"
    assert calls == ["filter"] and "PRIVATE-EXCEPTION" not in error.report.to_json()


def test_discovery_zero_stops_before_filter_and_is_repairable():
    class Base:
        pass

    class Child(Base):
        pass

    calls = []
    builder = ContainerBuilder()
    builder.register_subclasses(Base, subclass_type_filter=lambda child: calls.append(child) or True)
    _, fact = failure(builder, CompilationBudget(preparation_operations=0))
    assert fact.phase == "subclass discovery" and calls == []
    with builder.build(budget=CompilationBudget()) as owner:
        assert isinstance(owner.resolve(Base), Child)


def test_boundary_preparation_uses_same_allowance_and_phase():
    builder = ContainerBuilder()
    boundary = builder.create_boundary("area", exposes=(Expose(Leaf),))
    boundary.register(Leaf)
    _, fact = failure(builder, CompilationBudget(graph_occurrences=0))
    assert fact.phase == "boundary preparation"
    assert dict(fact.usage)["diagnostic_attempts"] == 0


def test_validation_iterator_advances_are_bounded_and_prior_findings_retained():
    builder = leaf_builder()
    calls = []

    def findings(context):
        calls.append("rule")
        while True:
            calls.append("next")
            yield BuildIssue("declared-finding", IssueSeverity.error, "Already observed")

    builder.add_validation_rule(findings)
    # one ordinary root-selection callback + rule entry + first next = three.
    error, fact = failure(builder, CompilationBudget(preparation_operations=3))
    assert fact.phase == "final validation" and calls == ["rule", "next"]
    assert [issue.code for issue in error.report.errors] == ["declared-finding", "compilation-budget-exceeded"]


def test_overlay_budgets_actual_clones_and_matrix_budgets_reset_per_variant():
    builder = ContainerBuilder()
    builder.register(Leaf, lifespan="singleton")
    with builder.build() as parent:
        overlay = parent.new_scope_builder()
        failure(overlay, CompilationBudget(graph_occurrences=0))
        profile = CompilationProfiler()
        with overlay.build(budget=CompilationBudget(), profile=profile) as child:
            assert child.resolve(Leaf) is parent.resolve(Leaf)
        assert profile.report().counters.to_dict()["anchored parent plan reuses"] > 0
        assert dict(profile.report().budget_usage or ())["graph_occurrences"] > 0
    matrix = BuildMatrix(
        [
            BuildVariant("bounded", leaf_builder, budget=CompilationBudget(graph_occurrences=0)),
            BuildVariant("valid", leaf_builder, budget=CompilationBudget(graph_occurrences=45)),
        ],
        reference="valid",
    )
    report = matrix.check()
    assert not report.is_valid
    fact = report.variants[0].build_report.errors[0].budget
    assert fact is not None and fact.kind == "graph_occurrences"
    assert report.variants[1].is_valid


def test_configured_entrypoint_decisions_preserve_labels_and_fingerprint():
    def make():
        builder = leaf_builder()
        builder.mark_entrypoint(Leaf)
        return builder

    with make().build() as plain, make().build(budget=CompilationBudget()) as limited:
        assert plain.graph.manifest().fingerprint == limited.graph.manifest().fingerprint
        assert plain.build_report.to_dict() == limited.build_report.to_dict()
        ordinary = plain.graph.explain(Leaf).selected[0]
        configured = limited.graph.explain(Leaf).selected[0]
        assert ordinary.reason_codes == configured.reason_codes
        assert ordinary.reason == configured.reason


def test_invalid_validation_returns_preserve_normal_labels_and_close_coroutines():
    async def wrong():
        pass

    def rule(context):
        return wrong()

    reports = []
    for budget in (None, CompilationBudget()):
        builder = leaf_builder()
        builder.add_validation_rule(rule)
        with pytest.raises(ContainerBuildError) as caught:
            builder.build(budget=budget)
        assert caught.value.report is not None
        reports.append(caught.value.report.to_dict())
    assert reports[0] == reports[1]
    assert "rule failed" in reports[0]["issues"][0]["message"]


def test_prior_validation_exception_is_redacted_when_later_budget_exhausts():
    def faulty(context):
        raise RuntimeError("PRIVATE-EXCEPTION")

    def endless(context):
        while True:
            yield BuildIssue("finding", IssueSeverity.error, "Public finding")

    builder = leaf_builder()
    builder.add_validation_rule(faulty)
    builder.add_validation_rule(endless)
    error, _ = failure(builder, CompilationBudget(preparation_operations=4))
    assert "validation-rule-error" in [issue.code for issue in error.report.errors]
    assert "PRIVATE-EXCEPTION" not in error.report.to_json()
    assert "PRIVATE-EXCEPTION" not in error.to_sarif()
    assert "physicalLocation" in error.to_sarif()


def test_wide_roots_use_work_occurrences_instead_of_public_graph_size():
    builder = ContainerBuilder()
    for index in range(24):
        builder.register(type(f"Wide{index}", (Leaf,), {}))
    profile = CompilationProfiler()
    with builder.build(
        budget=CompilationBudget(graph_occurrences=1080, active_dependency_depth=3), profile=profile
    ) as owner:
        assert len(owner.graph.roots) == 24
    assert dict(profile.report().budget_usage or ())["graph_occurrences"] == 1080


def test_provider_map_key_callback_is_refused_at_its_own_boundary():
    calls = []
    builder = leaf_builder()
    builder.register_provider_map(Leaf, key=lambda component: calls.append("key") or "a")
    _, fact = failure(builder, CompilationBudget(preparation_operations=2))
    assert fact.kind == "preparation_operations" and (fact.admitted, fact.attempted) == (2, 3)
    assert calls == []


def test_warmup_filter_admission_has_source_and_does_not_activate():
    from clean_ioc import WarmupPlan, WarmupTarget

    calls = []
    before = Leaf.activations
    builder = ContainerBuilder()
    builder.register(Leaf, lifespan="singleton")
    builder.add_warmup_plan(
        WarmupPlan("startup", [WarmupTarget(Leaf, filter=lambda component: calls.append("filter") or True)])
    )
    error, fact = failure(builder, CompilationBudget(preparation_operations=1))
    assert fact.phase == "warm-up compilation" and calls == []
    assert Leaf.activations == before
    assert "physicalLocation" in error.to_sarif()


def test_structural_nontermination_guard_is_mandatory_with_unlimited_budget():
    def expanding(child: Box[list[T]]) -> Box[T]:
        return Box()

    builder = ContainerBuilder()

    class Root:
        def __init__(self, child: Box[int]):
            self.child = child

    builder.register_pattern(Box[T], factory=expanding)
    builder.register(Root)
    with pytest.raises(ContainerBuildError) as caught:
        builder.build(budget=CompilationBudget())
    assert caught.value.report is not None
    assert "pattern-non-terminating-expansion" in [issue.code for issue in caught.value.report.errors]
    assert "RecursionError" not in str(caught.value)


def test_successful_budget_state_releases_compiler_without_cyclic_gc(monkeypatch):
    import gc
    import weakref

    from clean_ioc.container import _Compiler

    references = []
    original = _Compiler.__init__

    def initialize(self, *args, **kwargs):
        original(self, *args, **kwargs)
        references.append(weakref.ref(self))

    monkeypatch.setattr(_Compiler, "__init__", initialize)
    was_enabled = gc.isenabled()
    gc.disable()
    try:
        with leaf_builder().build(budget=CompilationBudget()):
            assert references and all(reference() is None for reference in references)
    finally:
        if was_enabled:
            gc.enable()


def test_public_validation_findings_with_callback_error_code_are_preserved():
    builder = leaf_builder()

    def findings(context):
        while True:
            yield BuildIssue("validation-rule-error", IssueSeverity.error, "Intentional public declaration")

    builder.add_validation_rule(findings)
    error, _ = failure(builder, CompilationBudget(preparation_operations=3))
    assert error.report.errors[0].message == "Intentional public declaration"


def test_import_exhaustion_is_source_linked_before_import_callback(monkeypatch):
    import clean_ioc.container as module

    calls = []
    monkeypatch.setattr(module.importlib, "import_module", lambda name: calls.append(name))
    builder = ContainerBuilder()
    builder.register_subclasses(Leaf, ensure_import_modules="PRIVATE-MODULE")
    error, fact = failure(builder, CompilationBudget(preparation_operations=0))
    assert fact.phase == "discovery imports" and calls == []
    assert "physicalLocation" in error.to_sarif()
    assert "PRIVATE-MODULE" not in error.report.to_json()


def test_failed_budget_control_signal_does_not_retain_compiler(monkeypatch):
    import gc
    import weakref

    from clean_ioc.container import _Compiler

    references = []
    original = _Compiler.__init__

    def initialize(self, *args, **kwargs):
        original(self, *args, **kwargs)
        references.append(weakref.ref(self))

    monkeypatch.setattr(_Compiler, "__init__", initialize)
    was_enabled = gc.isenabled()
    gc.disable()
    try:
        error, _ = failure(leaf_builder(), CompilationBudget(graph_occurrences=0))
        assert error.partial_graph is not None
        assert references and all(reference() is None for reference in references)
    finally:
        if was_enabled:
            gc.enable()


def test_source_compiler_attempt_totals_agree_in_python_and_json():
    builder = ContainerBuilder()
    boundary = builder.create_boundary("area", exposes=(Expose(Leaf),))
    boundary.register(Leaf)
    error, _ = failure(builder, CompilationBudget(graph_occurrences=0))
    partial = error.partial_graph
    assert partial is not None
    assert partial.total_attempts == partial.retained_attempts == len(partial.attempts) == 1
    assert partial.to_dict()["total_attempts"] == partial.total_attempts


def test_final_entrypoint_refusal_retains_already_captured_missing_entrypoint():
    builder = leaf_builder()
    builder.mark_entrypoint(str)
    builder.mark_entrypoint(Leaf)
    error, fact = failure(builder, CompilationBudget(preparation_operations=1))
    assert fact.phase == "final validation"
    assert [issue.code for issue in error.report.errors] == ["missing-entrypoint", "compilation-budget-exceeded"]


def test_early_primary_refusal_preserves_previously_captured_compiler_issue():
    def wrong() -> str:
        return "PRIVATE-RETURN"

    builder = ContainerBuilder()
    builder.register(Leaf, factory=wrong)
    builder.register(Worker)
    error, _ = failure(builder, CompilationBudget(graph_occurrences=1))
    assert [issue.code for issue in error.report.errors] == [
        "factory-return-type-mismatch",
        "compilation-budget-exceeded",
    ]
    assert "PRIVATE-RETURN" not in error.report.to_json()
    assert "physicalLocation" in error.to_sarif()


def test_source_inspection_findings_survive_later_template_output_refusal():
    def wrong() -> str:
        return "PRIVATE-RETURN"

    builder = ContainerBuilder()
    builder.register(Leaf, factory=wrong)
    builder.register_registration_template(
        for_each=Leaf,
        source_filter=lambda source: bool(source.dependencies) or True,
        template=lambda source: RegistrationTemplate(Worker),
    )
    error, fact = failure(builder, CompilationBudget(generated_template_outputs=0))
    assert fact.phase == "registration-template expansion"
    assert [issue.code for issue in error.report.errors] == [
        "factory-return-type-mismatch",
        "compilation-budget-exceeded",
    ]
