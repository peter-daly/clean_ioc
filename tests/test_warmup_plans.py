"""Startup declarations select frozen roots and preserve ordinary runtime ownership."""

import asyncio
import json
from collections.abc import AsyncIterator, Iterator
from concurrent.futures import ThreadPoolExecutor
from dataclasses import FrozenInstanceError
from typing import Any, Generic, TypeVar, cast

import pytest
from typing_extensions import TypeAliasType

from clean_ioc import (
    AsyncManagedProvider,
    ContainerBuilder,
    ContainerBuildError,
    Instrumentation,
    ManagedProvider,
    Provider,
    ResolutionProfiler,
    ScopeClosedError,
    WarmupError,
    WarmupPlan,
    WarmupTarget,
)


class Resource:
    pass


class Other:
    pass


T = TypeVar("T")


class GenericResource(Generic[T]):
    pass


def plan(builder, *targets, name="startup"):
    builder.add_warmup_plan(WarmupPlan(name, [t if isinstance(t, WarmupTarget) else WarmupTarget(t) for t in targets]))
    return builder


def test_immutable_capture_lazy_order_cache_and_inspection(monkeypatch):
    calls = []
    builder = ContainerBuilder()
    builder.register(Resource, factory=lambda: calls.append("resource") or Resource(), lifespan="singleton")
    builder.register(Other, factory=lambda: calls.append("other") or Other(), lifespan="singleton")
    targets = [WarmupTarget(Other), WarmupTarget(Resource)]
    declaration = WarmupPlan("startup", targets)
    targets.clear()
    with pytest.raises(FrozenInstanceError):
        setattr(declaration, "name", "changed")
    builder.add_warmup_plan(declaration)
    with builder.build() as container:
        assert calls == []
        assert container.warmup_plans == container.graph.warmup_plans
        assert [t.service for t in container.warmup_plans[0].targets] == [f"{__name__}.Other", f"{__name__}.Resource"]
        monkeypatch.setattr(ContainerBuilder, "build", lambda *a, **kw: pytest.fail("runtime compiled"))
        report = container.warmup("startup")
        assert report.is_valid
        assert calls == ["other", "resource"]
        assert all(r.status == "succeeded" for r in report.results)
        with container.new_scope() as child:
            assert child.warmup("startup").is_valid
        assert calls == ["other", "resource"]
        assert report.to_json() == report.to_json()
        report.assert_valid()
        report.raise_for_errors()
        assert report.graph_fingerprint == container.graph.manifest(all_roots=True).fingerprint


@pytest.mark.parametrize("lifespan", ["transient", "scoped", "per_resolution"])
def test_reject_non_singleton_and_repair(lifespan):
    builder = plan(ContainerBuilder(), Resource)
    builder.register(Resource, lifespan=lifespan)
    with pytest.raises(ContainerBuildError) as caught:
        builder.build()
    assert caught.value.report is not None
    assert caught.value.report.errors[0].code == "warmup-non-singleton-target"
    builder.remove_warmup_plan("startup")
    plan(builder, Other)
    builder.register(Other, lifespan="singleton")
    assert builder.build().warmup("startup").is_valid


@pytest.mark.parametrize(
    "key",
    [
        list[Resource],
        Provider[Resource],
        ManagedProvider[Resource],
        AsyncManagedProvider[Resource],
        GenericResource,
        12,
        [],
        None,
    ],
)
def test_invalid_target_keys_are_structured(key):
    builder = plan(ContainerBuilder(), key)
    with pytest.raises(ContainerBuildError) as caught:
        builder.build()
    assert caught.value.report is not None
    assert caught.value.report.errors[0].code == "warmup-invalid-target"
    assert "test_warmup_plans.py" in caught.value.report.to_sarif()
    builder.remove_warmup_plan("startup")
    builder.build()


@pytest.mark.parametrize("name", ["", "   ", None, 42])
def test_invalid_names_fail_build_and_can_be_removed(name):
    builder = plan(ContainerBuilder(), name=name)
    with pytest.raises(ContainerBuildError) as caught:
        builder.build()
    assert caught.value.report is not None
    assert caught.value.report.errors[0].code == "warmup-invalid-target"
    builder.remove_warmup_plan(name)
    builder.build()


def test_duplicate_names_targets_missing_ambiguous_and_dependency_only():
    for code, configure in [
        ("warmup-duplicate-plan", lambda b: plan(b, name="startup")),
        ("warmup-duplicate-target", lambda b: None),
        ("warmup-missing-component", lambda b: None),
        ("warmup-ambiguous-component", lambda b: b.register(Resource, lifespan="singleton")),
        ("warmup-missing-component", lambda b: None),
    ]:
        builder = ContainerBuilder()
        if code != "warmup-missing-component" or configure is not None:
            builder.register(
                Resource,
                lifespan="singleton",
                root_policy="dependency_only" if code == "warmup-missing-component" else "resolvable",
            )
        plan(builder, Resource, *([Resource] if code == "warmup-duplicate-target" else []))
        configure(builder)
        with pytest.raises(ContainerBuildError) as caught:
            builder.build()
        assert caught.value.report is not None
        assert caught.value.report.errors[0].code == code


def test_named_default_filters_and_fallback_are_frozen():
    calls = []
    builder = ContainerBuilder()
    builder.register(Resource, factory=lambda: calls.append("default") or Resource(), lifespan="singleton")
    builder.register(
        Resource, factory=lambda: calls.append("named") or Resource(), lifespan="singleton", name="primary"
    )
    selector_calls = []

    def selector(component):
        selector_calls.append(component.name)
        return component.name == "primary"

    plan(builder, Resource, WarmupTarget(Resource, filter=selector))
    with builder.build() as container:
        captured = len(selector_calls)
        container.warmup("startup").assert_valid()
        assert len(selector_calls) == captured
        assert calls == ["default", "named"]


def test_failure_aggregation_retry_safe_exports_and_no_rollback():
    events = []
    secret = "password=never-export"  # noqa: S105

    class SecretError(Exception):
        def __str__(self):
            pytest.fail("exception string evaluated")

        def __repr__(self):
            pytest.fail("exception repr evaluated")

    def bad():
        events.append("bad")
        raise SecretError(secret)

    def good() -> Iterator[Other]:
        events.append("good")
        try:
            yield Other()
        finally:
            events.append("closed")

    builder = ContainerBuilder()
    builder.register(Resource, factory=bad, lifespan="singleton")
    builder.register(Other, factory=good, lifespan="singleton")
    plan(builder, Resource, Other)
    with builder.build() as container:
        report = container.warmup("startup")
        assert [r.status for r in report.results] == ["failed", "succeeded"]
        assert events == ["bad", "good"]
        for rendered in (report.to_json(), report.to_sarif(), report.to_text()):
            assert secret not in rendered
            assert "SecretError" in rendered
        with pytest.raises(WarmupError) as caught:
            report.raise_for_errors()
        assert caught.value.report is report
        with pytest.raises(AssertionError, match="warmup-activation-failed"):
            report.assert_valid()
        container.warmup("startup")
        assert events == ["bad", "good", "bad"]
    assert events[-1] == "closed"
    assert json.loads(report.to_sarif())["runs"][0]["properties"]["graphFingerprint"] == report.graph_fingerprint


@pytest.mark.asyncio
async def test_whole_plan_preflight_async_dependency_and_cleanup():
    calls = []

    async def resource() -> AsyncIterator[Resource]:
        calls.append("resource")
        try:
            yield Resource()
        finally:
            calls.append("closed")

    class Consumer:
        def __init__(self, resource: Resource):
            self.resource = resource

    builder = ContainerBuilder()
    builder.register(Resource, factory=resource, lifespan="transient")
    builder.register(Consumer, lifespan="singleton")
    builder.register(Other, factory=lambda: calls.append("other") or Other(), lifespan="singleton")
    plan(builder, Other, Consumer)
    async with builder.build() as container:
        report = container.warmup("startup")
        assert not report.is_valid
        assert [r.status for r in report.results] == ["not_executed", "not_executed"]
        assert calls == []
        assert container.warmup_plans[0].requires_async
        (await container.warmup_async("startup")).assert_valid()
        assert calls == ["other", "resource"]
    assert calls == ["other", "resource", "closed"]


@pytest.mark.parametrize("signal", [KeyboardInterrupt, SystemExit])
def test_base_exception_stops_later_targets(signal):
    calls = []

    def abort():
        raise signal()

    builder = ContainerBuilder()
    builder.register(Resource, factory=abort, lifespan="singleton")
    builder.register(Other, factory=lambda: calls.append("later") or Other(), lifespan="singleton")
    plan(builder, Resource, Other)
    with builder.build() as container:
        with pytest.raises(signal):
            container.warmup("startup")
        assert calls == []


@pytest.mark.asyncio
async def test_cancellation_stops_later_targets_and_retry_uses_same_owner():
    started = asyncio.Event()
    calls = []

    async def resource():
        calls.append("resource")
        started.set()
        await asyncio.sleep(100)
        return Resource()

    builder = ContainerBuilder()
    builder.register(Resource, factory=resource, lifespan="singleton")
    builder.register(Other, factory=lambda: calls.append("later") or Other(), lifespan="singleton")
    plan(builder, Resource, Other)
    async with builder.build() as container:
        task = asyncio.create_task(container.warmup_async("startup"))
        await started.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert calls == ["resource"]


def test_concurrent_warmup_and_ordinary_resolution_share_singleton():
    calls = []
    builder = ContainerBuilder()
    builder.register(Resource, factory=lambda: calls.append(1) or Resource(), lifespan="singleton")
    plan(builder, Resource)
    plan(builder, Resource, name="second")
    with builder.build() as container, ThreadPoolExecutor(max_workers=8) as executor:
        outcomes = list(
            executor.map(lambda i: container.resolve(Resource) if i % 2 else container.warmup("startup"), range(64))
        )
        assert len(outcomes) == 64
        container.warmup("second").assert_valid()
        assert calls == [1]


def test_alias_generic_demand_and_duplicate_canonical_target():
    alias = TypeAliasType("alias", Resource)
    builder = ContainerBuilder()
    builder.register(Resource, lifespan="singleton")
    builder.register(GenericResource, lifespan="singleton")
    plan(builder, alias, GenericResource[int])
    with builder.build() as container:
        container.warmup("startup").assert_valid()
        assert isinstance(container.resolve(GenericResource[int]), GenericResource)
    duplicate = ContainerBuilder()
    duplicate.register(Resource, lifespan="singleton")
    plan(duplicate, Resource, alias)
    with pytest.raises(ContainerBuildError) as caught:
        duplicate.build()
    assert caught.value.report is not None
    assert caught.value.report.errors[0].code == "warmup-duplicate-target"


def test_overlay_reselection_anchors_parent_and_child_scopes_reuse():
    calls = []
    builder = ContainerBuilder()
    builder.register(Resource, factory=lambda: calls.append("parent") or Resource(), lifespan="singleton")
    plan(builder, Resource)
    with builder.build() as parent:
        overlay_builder = parent.new_scope_builder()
        with overlay_builder.build() as inherited:
            inherited.warmup("startup").assert_valid()
            assert inherited.resolve(Resource) is parent.resolve(Resource)
        override = parent.new_scope_builder()
        override.register(Resource, factory=lambda: calls.append("overlay") or Resource(), lifespan="singleton")
        with override.build() as overlay:
            overlay.warmup("startup").assert_valid()
            assert overlay.resolve(Resource) is not parent.resolve(Resource)
            with overlay.new_scope() as child:
                child.warmup("startup").assert_valid()
        assert calls == ["parent", "overlay"]
        duplicate = parent.new_scope_builder()
        plan(duplicate, Resource)
        with pytest.raises(ContainerBuildError) as caught:
            duplicate.build()
        assert caught.value.report is not None
        assert caught.value.report.errors[0].code == "warmup-duplicate-plan"


def test_unknown_and_closed_runtime_reject_before_activation():
    calls = []
    builder = ContainerBuilder()
    builder.register(Resource, factory=lambda: calls.append(1) or Resource(), lifespan="singleton")
    plan(builder, Resource)
    with builder.build() as container:
        with pytest.raises(KeyError):
            container.warmup("unknown")
        assert calls == []
    with pytest.raises(ScopeClosedError):
        container.warmup("startup")


def test_declaration_only_changes_preserve_fingerprint_and_no_entrypoints():
    def build(declare):
        b = ContainerBuilder()
        b.register(Resource, lifespan="singleton")
        if declare:
            plan(b, Resource)
        return b.build()

    with build(False) as plain, build(True) as declared:
        assert plain.graph.manifest().fingerprint == declared.graph.manifest().fingerprint
        assert declared.graph.entrypoints == ()


def test_missing_registration_and_invalid_sync_filters_remain_repairable():
    builder = plan(ContainerBuilder(), Resource)
    with pytest.raises(ContainerBuildError) as caught:
        builder.build()
    assert caught.value.report is not None
    assert caught.value.report.errors[0].code == "warmup-missing-component"
    builder.register(Resource, lifespan="singleton")
    builder.build().warmup("startup").assert_valid()

    async def asynchronous(component):
        return True

    for predicate in (None, 12, asynchronous, lambda component: 1 / 0):
        builder = ContainerBuilder()
        builder.register(Resource, lifespan="singleton")
        plan(builder, WarmupTarget(Resource, filter=cast(Any, predicate)))
        with pytest.raises(ContainerBuildError) as caught:
            builder.build()
        assert caught.value.report is not None
        assert caught.value.report.errors[0].code == "warmup-invalid-target"


def test_exposed_boundary_and_private_service_selection():
    from clean_ioc import Expose

    builder = ContainerBuilder()
    boundary = builder.create_boundary("resources", exposes=[Expose(Resource)])
    boundary.register(Resource, lifespan="singleton")
    boundary.register(Other, lifespan="singleton")
    plan(builder, Resource)
    with builder.build() as container:
        container.warmup("startup").assert_valid()
        assert container.warmup_plans[0].targets[0].path.startswith("root:")
    private = ContainerBuilder()
    private.create_boundary("private").register(Resource, lifespan="singleton")
    plan(private, Resource)
    with pytest.raises(ContainerBuildError) as caught:
        private.build()
    assert caught.value.report is not None
    assert caught.value.report.errors[0].code == "warmup-missing-component"


def test_closed_pattern_explicit_demand_and_fallback():
    calls = []
    builder = ContainerBuilder()
    builder.register_pattern(
        GenericResource[list[T]], factory=lambda: calls.append("pattern") or GenericResource(), lifespan="singleton"
    )
    plan(builder, GenericResource[list[int]])
    with builder.build() as container:
        assert calls == []
        container.warmup("startup").assert_valid()
        assert calls == ["pattern"]
    builder = ContainerBuilder()
    builder.register_fallback(Resource, factory=lambda: calls.append("fallback") or Resource(), lifespan="singleton")
    builder.register(Resource, factory=lambda: calls.append("ordinary") or Resource(), lifespan="singleton")
    plan(builder, Resource)
    with builder.build() as container:
        container.warmup("startup").assert_valid()
        assert calls[-1] == "ordinary"
    fallback = ContainerBuilder()
    fallback.register_fallback(Resource, lifespan="singleton")
    plan(fallback, Resource)
    fallback.build().warmup("startup").assert_valid()


def test_decorators_preconfiguration_and_promoted_resource_cleanup():
    calls = []

    def resource() -> Iterator[Resource]:
        calls.append("acquire")
        try:
            yield Resource()
        finally:
            calls.append("close")

    def configure():
        calls.append("configure")

    class Consumer:
        def __init__(self, resource: Resource):
            self.resource = resource
            calls.append("consumer")

    class Decorated(Consumer):
        def __init__(self, inner: Consumer):
            self.inner = inner
            calls.append("decorate")

    builder = ContainerBuilder()
    builder.register(Resource, factory=resource, lifespan="transient")
    builder.register(Consumer, lifespan="singleton")
    builder.pre_configure(Consumer, configure)
    builder.register_decorator(Consumer, Decorated)
    plan(builder, Consumer)
    with builder.build() as container:
        container.warmup("startup").assert_valid()
        assert calls == ["configure", "acquire", "consumer", "decorate"]
        assert isinstance(container.resolve(Consumer), Decorated)
    assert calls[-1] == "close"


def test_shared_failing_dependency_is_retried_for_later_target():
    calls = []

    def resource():
        calls.append("dependency")
        if len(calls) == 1:
            raise RuntimeError("private")
        return Resource()

    class First:
        def __init__(self, resource: Resource):
            self.resource = resource

    class Second:
        def __init__(self, resource: Resource):
            self.resource = resource

    builder = ContainerBuilder()
    builder.register(Resource, factory=resource, lifespan="singleton")
    builder.register(First, lifespan="singleton")
    builder.register(Second, lifespan="singleton")
    plan(builder, First, Second)
    with builder.build() as container:
        report = container.warmup("startup")
        assert [r.status for r in report.results] == ["failed", "succeeded"]
        assert calls == ["dependency", "dependency"]
        container.warmup("startup").assert_valid()
        assert calls == ["dependency", "dependency"]


def test_profiler_observes_existing_request_activation_cache_and_cleanup_identities():
    events = []

    def resource() -> Iterator[Resource]:
        events.append("created")
        try:
            yield Resource()
        finally:
            events.append("closed")

    builder = ContainerBuilder()
    builder.register(Resource, factory=resource, lifespan="singleton")
    plan(builder, Resource)
    profiler = ResolutionProfiler(sample_durations=1)
    with builder.build(instrumentation=Instrumentation(profiler)) as container:
        assert all(r.attempts == 0 for r in profiler.report().records)
        container.warmup("startup").assert_valid()
        container.warmup("startup").assert_valid()
        container.resolve(Resource)
        recording = profiler.report()
        request = next(r for r in recording.records if r.kind == "request" and r.attempts)
        registration = next(r for r in recording.records if r.registration and r.attempts)
        assert (request.attempts, request.completed) == (3, 3)
        assert (registration.attempts, registration.cache_misses, registration.cache_hits) == (1, 1, 2)
        assert registration.path == container.warmup_plans[0].targets[0].path
        assert recording.in_flight == 0
    assert events == ["created", "closed"]
    assert any("cleanup" in dict(r.durations) for r in profiler.report().records)


@pytest.mark.asyncio
async def test_async_concurrent_runs_and_resolves_initialize_once():
    calls = []

    async def resource():
        calls.append(1)
        await asyncio.sleep(0)
        return Resource()

    builder = ContainerBuilder()
    builder.register(Resource, factory=resource, lifespan="singleton")
    plan(builder, Resource)
    async with builder.build() as container:
        results = await asyncio.gather(
            *(container.resolve_async(Resource) if i % 2 else container.warmup_async("startup") for i in range(20))
        )
        assert len(results) == 20
        assert calls == [1]


def test_static_validation_matrix_manifest_diff_and_activation_never_initialize():
    from clean_ioc import BuildMatrix, BuildVariant

    calls = []

    def builder():
        b = ContainerBuilder()
        b.register(Resource, factory=lambda: calls.append(1) or Resource(), lifespan="singleton")
        return plan(b, Resource)

    with builder().build() as container:
        container.validation_report().assert_valid()
        manifest = container.graph.manifest()
        assert not container.graph.diff(manifest).changed
        container.graph.activation_report(Resource)
    BuildMatrix((BuildVariant("one", builder),), reference="one").check().assert_valid()
    assert calls == []


def test_nominal_newtype_and_union_closed_keys():
    from typing import NewType

    nominal = NewType("nominal", str)
    builder = ContainerBuilder()
    builder.register(nominal, factory=lambda: nominal("value"), lifespan="singleton")
    builder.register(Resource | Other, factory=Resource, lifespan="singleton")
    plan(builder, nominal, Resource | Other)
    with builder.build() as container:
        container.warmup("startup").assert_valid()
        assert container.resolve(nominal) == "value"
        assert isinstance(container.resolve(Resource | Other), Resource)


def test_entrypoint_focus_stays_separate_and_cli_never_warms(monkeypatch, capsys):
    from clean_ioc.cli import main

    calls = []

    def builder():
        b = ContainerBuilder()
        b.register(Resource, factory=lambda: calls.append(1) or Resource(), lifespan="singleton")
        b.register(Other, root_policy="entrypoint")
        return plan(b, Resource)

    monkeypatch.setattr(
        "clean_ioc.cli._load_object", lambda locator: Resource if locator.endswith(":Resource") else builder
    )
    assert main(["check", "app:builder", "--ignore", "unreachable-component"]) == 0
    assert main(["activation", "app:builder", "app:Resource"]) == 0
    with builder().build() as container:
        assert len(container.graph.entrypoints) == 1
        assert container.graph.entrypoints[0].component.service_type is Other
        assert container.warmup_plans[0].targets[0].service.endswith("Resource")
        assert container.graph.manifest().fingerprint != container.graph.manifest(all_roots=True).fingerprint
    assert calls == []
    assert capsys.readouterr().out


def test_template_decorated_closed_generic_demand_is_frozen():
    from clean_ioc import DecoratorTemplate, DerivedServices

    calls = []

    class Wrapper(GenericResource):
        def __init__(self, inner: GenericResource[int]):
            self.inner = inner
            calls.append("decorator")

    def template(source):
        calls.append("template")
        return DecoratorTemplate(DerivedServices(GenericResource), Wrapper)

    builder = ContainerBuilder()
    builder.register(Other, lifespan="singleton")
    builder.register(GenericResource, lifespan="singleton")
    builder.register_decorator_template(for_each=Other, template=template)
    plan(builder, GenericResource[int])
    with builder.build() as container:
        captured = list(calls)
        assert "decorator" not in captured
        container.warmup("startup").assert_valid()
        assert calls == [*captured, "decorator"]
        assert isinstance(container.resolve(GenericResource[int]), Wrapper)
