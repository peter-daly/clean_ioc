import sys
from dataclasses import dataclass
from types import ModuleType
from typing import assert_type

import pytest

from clean_ioc import (
    BoundaryBuilder,
    BuilderAlreadyBuiltError,
    BuildIssue,
    CompilationProfiler,
    ComponentBuilder,
    ContainerBuilder,
    ContainerBuildError,
    Expose,
    IssueSeverity,
    Use,
    ValidationContext,
)
from clean_ioc import component_filters as cf
from clean_ioc.bundles import BaseBundle, OnlyRunOncePerInstanceBundle


@dataclass(frozen=True)
class Settings:
    value: str


class Clock:
    pass


class WaitPolicy:
    pass


class CustomWaitPolicy(WaitPolicy):
    def __init__(self, clock: Clock):
        self.clock = clock


class ObservedWaitPolicy(WaitPolicy):
    def __init__(self, inner: WaitPolicy):
        self.inner = inner


class HealthPolicy:
    pass


class Worker:
    def __init__(self, wait_policy: WaitPolicy, health_policy: HealthPolicy, settings: Settings):
        self.wait_policy = wait_policy
        self.health_policy = health_policy
        self.settings = settings


class StandardWorkerBundle(BaseBundle):
    def apply(self, builder: ComponentBuilder):
        builder.register(Worker, name="outbox")
        builder.register(WaitPolicy)
        builder.register(HealthPolicy, lifespan="singleton")


class CustomWaitBundle(BaseBundle):
    def apply(self, builder: ComponentBuilder):
        builder.register(Clock)
        builder.register(WaitPolicy, CustomWaitPolicy)
        builder.register_decorator(WaitPolicy, ObservedWaitPolicy, decorated_arg="inner")


def test_boundary_accepts_incremental_bundles_with_private_policy_dependencies_and_decorators():
    builder = ContainerBuilder()
    settings = Settings("outbox")
    builder.register(Settings, instance=settings)
    boundary = builder.create_boundary(
        "outbox",
        uses=(Use.root(Settings),),
        exposes=(Expose(Worker, filter=cf.with_name("outbox")), Expose(HealthPolicy)),
    )
    assert_type(boundary, BoundaryBuilder)
    boundary.apply_bundle(StandardWorkerBundle())

    def root_policy(root: ComponentBuilder):
        root.register(WaitPolicy)

    builder.apply_bundle(root_policy)
    boundary.apply_bundle(CustomWaitBundle())

    container = builder.build()
    worker = container.resolve(Worker, filter=cf.with_name("outbox"))
    assert isinstance(worker.wait_policy, ObservedWaitPolicy)
    assert isinstance(worker.wait_policy.inner, CustomWaitPolicy)
    assert isinstance(worker.wait_policy.inner.clock, Clock)
    assert worker.health_policy is container.resolve(HealthPolicy)
    assert worker.settings is settings
    assert type(container.resolve(WaitPolicy)) is WaitPolicy
    assert not container.has_component(Clock)
    assert boundary.name == "outbox"


def test_boundary_owning_bundle_can_publish_its_composition_handle():
    class SubsystemBundle(BaseBundle):
        boundary: BoundaryBuilder

        def apply(self, builder: ComponentBuilder):
            self.boundary = builder.create_boundary("subsystem", exposes=(Expose(CustomWaitPolicy),))
            self.boundary.register(CustomWaitPolicy)

    bundle = SubsystemBundle()
    builder = ContainerBuilder()
    builder.apply_bundle(bundle)

    def clock_bundle(private: ComponentBuilder):
        private.register(Clock)

    bundle.boundary.apply_bundle(clock_bundle)
    container = builder.build()
    assert isinstance(container.resolve(CustomWaitPolicy).clock, Clock)
    assert not container.has_component(Clock)


@pytest.mark.parametrize("overlay", [False, True])
@pytest.mark.parametrize("profiled", [False, True])
def test_successful_build_freezes_every_retained_boundary_handle(overlay, profiled):
    builder = ContainerBuilder().build().new_scope_builder() if overlay else ContainerBuilder()
    boundary = builder.create_boundary("feature", exposes=(Expose(Clock),))
    component_id = boundary.register(Clock)
    container = builder.build(profile=CompilationProfiler() if profiled else None)

    def health_bundle(private: ComponentBuilder):
        private.register(HealthPolicy)

    mutations = [
        lambda: boundary.register(Settings, instance=Settings("late")),
        lambda: boundary.apply_bundle(health_bundle),
        lambda: boundary.patch_component(Clock, component_id, lifespan="singleton"),
        lambda: boundary.register_decorator(WaitPolicy, ObservedWaitPolicy),
        lambda: boundary.mark_entrypoint(Clock),
        lambda: boundary.add_validation_rule(lambda context: ()),
        lambda: setattr(boundary, "uses", (Use.root(Settings),)),
        lambda: setattr(boundary, "exposes", ()),
        lambda: builder.create_boundary("late"),
    ]
    for mutate in mutations:
        with pytest.raises(BuilderAlreadyBuiltError):
            mutate()
    assert isinstance(container.resolve(Clock), Clock)
    assert not container.has_component(HealthPolicy)
    assert not hasattr(boundary, "build")
    assert not hasattr(boundary, "resolve")


@pytest.mark.parametrize("overlay", [False, True])
def test_failed_build_can_be_repaired_through_boundary_and_parent_handles(overlay):
    builder = ContainerBuilder().build().new_scope_builder() if overlay else ContainerBuilder()
    boundary = builder.create_boundary("feature", uses=(Use.root(Settings),), exposes=(Expose(Worker),))
    boundary.register(Worker)
    boundary.register(HealthPolicy)
    with pytest.raises(ContainerBuildError):
        builder.build()

    builder.register(Settings, instance=Settings("repaired"))
    with pytest.raises(ContainerBuildError):
        builder.build()

    boundary.apply_bundle(CustomWaitBundle())
    container = builder.build()
    worker = container.resolve(Worker)
    assert worker.settings.value == "repaired"
    assert isinstance(worker.wait_policy, ObservedWaitPolicy)
    assert isinstance(worker.wait_policy.inner, CustomWaitPolicy)
    assert isinstance(worker.wait_policy.inner.clock, Clock)


def test_visibility_contracts_can_be_repaired_after_build_failure():
    builder = ContainerBuilder()
    consumer = builder.create_boundary("consumer", uses=(Use("source", Clock),))
    consumer.register(CustomWaitPolicy)
    source = builder.create_boundary("source")
    source.register(Clock, lifespan="singleton")
    with pytest.raises(ContainerBuildError):
        builder.build()

    source.exposes = (Expose(Clock),)
    consumer.exposes = (Expose(CustomWaitPolicy),)
    consumer.uses = (Use("source", Clock), Use.root(Settings))
    with pytest.raises(ContainerBuildError):
        builder.build()
    consumer.uses = (Use("source", Clock),)

    container = builder.build()
    assert container.resolve(CustomWaitPolicy).clock is container.resolve(Clock)


def test_boundary_queries_use_current_local_and_imported_components_and_leave_composition_mutable():
    builder = ContainerBuilder()
    builder.register(Settings, instance=Settings("root"))
    builder.register(HealthPolicy)
    boundary = builder.create_boundary("feature", uses=(Use.root(Settings),))
    component_id = boundary.register(Clock)
    assert boundary.get_component_ids(Clock) == [component_id]
    assert boundary.has_component(Settings)
    assert not boundary.has_component(HealthPolicy)
    assert not builder.has_component(Clock)

    with pytest.raises(ContainerBuildError) as captured:
        builder.patch_component(Clock, component_id, lifespan="singleton")
    assert captured.value.code == "boundary-private-component"
    boundary.patch_component(Clock, component_id, lifespan="singleton")
    boundary.register(CustomWaitPolicy)
    boundary.exposes = (Expose(CustomWaitPolicy),)
    container = builder.build()
    assert container.resolve(CustomWaitPolicy).clock is container.resolve(CustomWaitPolicy).clock
    assert not container.has_component(Clock)


def test_discovery_sees_classes_declared_after_boundary_creation_and_bundle_application():
    class Service:
        pass

    builder = ContainerBuilder()
    boundary = builder.create_boundary("feature", exposes=(Expose(Service),))
    boundary.apply_bundle(lambda private: private.register_subclasses(Service))

    class LateService(Service):
        pass

    assert isinstance(builder.build().resolve(Service), LateService)


def test_failed_build_retains_successful_run_once_contributions():
    class Once(OnlyRunOncePerInstanceBundle):
        calls = 0

        def apply(self, builder: ComponentBuilder):
            self.calls += 1
            builder.register(CustomWaitPolicy)

    builder = ContainerBuilder()
    boundary = builder.create_boundary("feature", exposes=(Expose(CustomWaitPolicy),))
    bundle = Once()
    boundary.apply_bundle(bundle)
    with pytest.raises(ContainerBuildError):
        builder.build()
    boundary.apply_bundle(bundle)
    boundary.register(Clock)
    assert isinstance(builder.build().resolve(CustomWaitPolicy).clock, Clock)
    assert bundle.calls == 1


@pytest.mark.parametrize("profiled", [False, True])
def test_validation_failure_leaves_boundary_editable_until_successful_retry(profiled):
    def require_health_policy(context: ValidationContext):
        if not any(root.requested_type is HealthPolicy for root in context.graph.roots):
            yield BuildIssue("missing-health-policy", IssueSeverity.error, "A health policy is required")

    builder = ContainerBuilder()
    boundary = builder.create_boundary("feature", exposes=(Expose(Clock),))
    boundary.register(Clock)
    boundary.add_validation_rule(require_health_policy)
    profile = CompilationProfiler() if profiled else None
    with pytest.raises(ContainerBuildError) as captured:
        builder.build(profile=profile)
    assert captured.value.report is not None
    assert "missing-health-policy" in {issue.code for issue in captured.value.report.errors}

    boundary.register(HealthPolicy)
    container = builder.build(profile=CompilationProfiler() if profiled else None)
    assert isinstance(container.resolve(Clock), Clock)
    assert not container.has_component(HealthPolicy)
    with pytest.raises(BuilderAlreadyBuiltError):
        boundary.register(Settings, instance=Settings("too late"))


def test_boundary_discovery_imports_are_ready_before_root_and_other_boundary_snapshots(tmp_path, monkeypatch):
    class Service:
        pass

    class Consumer:
        def __init__(self, service: Service):
            self.service = service

    contract = ModuleType("boundary_discovery_contract")
    setattr(contract, "Service", Service)
    monkeypatch.setitem(sys.modules, contract.__name__, contract)
    monkeypatch.syspath_prepend(str(tmp_path))
    module_name = "boundary_discovery_plugin"
    (tmp_path / f"{module_name}.py").write_text(
        "from boundary_discovery_contract import Service\nclass Imported(Service):\n    pass\n"
    )
    builder = ContainerBuilder()
    builder.register_subclasses(Service)
    consumer = builder.create_boundary("consumer", exposes=(Expose(Consumer),))
    consumer.register_subclasses(Service)
    consumer.register(Consumer)
    importer = builder.create_boundary("importer")
    importer.register_subclasses(Service, ensure_import_modules=module_name)
    try:
        container = builder.build()
        assert type(container.resolve(Service)).__name__ == "Imported"
        assert type(container.resolve(Consumer).service).__name__ == "Imported"
    finally:
        sys.modules.pop(module_name, None)


def test_boundary_visibility_inputs_are_snapshotted_and_use_cycles_can_be_repaired():
    builder = ContainerBuilder()
    uses = [Use("second", HealthPolicy)]
    exposes = [Expose(Clock)]
    first = builder.create_boundary("first", uses=iter(uses), exposes=exposes)
    uses.clear()
    exposes.clear()
    first.register(Clock)
    second = builder.create_boundary("second", uses=(Use("first", Clock),), exposes=(Expose(HealthPolicy),))
    second.register(HealthPolicy)
    with pytest.raises(ContainerBuildError) as captured:
        builder.build()
    assert captured.value.report is not None
    assert captured.value.report.errors[0].code == "boundary-use-cycle"

    first.uses = ()
    assert first.exposes == (Expose(Clock),)
    container = builder.build()
    assert isinstance(container.resolve(HealthPolicy), HealthPolicy)
    assert isinstance(container.resolve(Clock), Clock)
