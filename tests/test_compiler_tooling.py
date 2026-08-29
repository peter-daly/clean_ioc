import json
import subprocess
import sys
from pathlib import Path

import pytest

from clean_ioc import (
    EMPTY,
    BuildReport,
    ComponentKind,
    ContainerBuilder,
    ContainerBuildError,
    DependencySettings,
    GraphManifest,
    ResolutionContext,
    Scope,
)
from clean_ioc.cli import main


def test_build_report_aggregates_independent_errors_and_failed_builder_is_reusable():
    class FirstMissing:
        pass

    class SecondMissing:
        pass

    class First:
        def __init__(self, missing: FirstMissing):
            self.missing = missing

    class Second:
        def __init__(self, missing: SecondMissing):
            self.missing = missing

    builder = ContainerBuilder()
    builder.register(First)
    builder.register(Second)

    with pytest.raises(ContainerBuildError) as raised:
        builder.build()

    report = raised.value.report
    assert isinstance(report, BuildReport)
    assert [issue.code for issue in report.errors] == ["missing-component", "missing-component"]
    assert "FirstMissing" in report.errors[0].message
    assert "SecondMissing" in report.errors[1].message
    assert report.errors[0].path[-1].endswith("FirstMissing")
    assert report.errors[1].path[-1].endswith("SecondMissing")

    builder.register(FirstMissing)
    builder.register(SecondMissing)
    assert builder.build().build_report.is_valid


def test_complete_component_graph_includes_special_injection_edges_and_redacts_values():
    class Request:
        pass

    class Application:
        def __init__(
            self,
            request: Request,
            context: ResolutionContext,
            scope: Scope,
            configured: str,
            defaulted: str = "top-secret",
        ):
            self.request = request
            self.context = context
            self.scope = scope
            self.configured = configured
            self.defaulted = defaulted

    def configured_value(default, context):
        return "runtime-secret" if default is EMPTY else default

    builder = ContainerBuilder()
    builder.declare_scope_slot(Request)
    builder.register(
        Application,
        dependency_config={"configured": DependencySettings(value_factory=configured_value)},
    )
    builder.mark_entrypoint(Application)
    container = builder.build()
    application = next(root.component for root in container.graph.entrypoints)

    assert {component.kind for component in application.dependencies} == {
        ComponentKind.scope_slot,
        ComponentKind.runtime_context,
        ComponentKind.value_provider,
        ComponentKind.value,
    }
    manifest = container.graph.manifest().to_json()
    assert "top-secret" not in manifest
    assert "runtime-secret" not in manifest
    assert '"activation": "supplied"' in manifest


def test_semantic_manifests_are_process_independent_and_diff_wiring_changes():
    class Dependency:
        pass

    class FirstDependency(Dependency):
        pass

    class SecondDependency(Dependency):
        pass

    class Application:
        def __init__(self, dependency: Dependency):
            self.dependency = dependency

    def build(implementation):
        builder = ContainerBuilder()
        builder.register(Dependency, implementation)
        builder.register(Application)
        builder.mark_entrypoint(Application)
        return builder.build()

    first = build(FirstDependency).graph.manifest()
    equivalent = build(FirstDependency).graph.manifest()
    changed = build(SecondDependency).graph.manifest()

    assert first.to_json() == equivalent.to_json()
    assert first.fingerprint == equivalent.fingerprint
    assert equivalent.diff(first).is_empty
    difference = changed.diff(first)
    assert not difference.is_empty
    assert any(change.path.endswith("dependency:dependency:0") for change in difference.changed)
    assert GraphManifest.from_json(first.to_json()).to_json() == first.to_json()


def test_entrypoint_markers_focus_graphs_without_weakening_validation():
    class Dependency:
        pass

    class Application:
        def __init__(self, dependency: Dependency):
            self.dependency = dependency

    class Unused:
        pass

    builder = ContainerBuilder()
    builder.register(Dependency)
    builder.register(Application)
    builder.register(Unused)
    builder.mark_entrypoint(Application)
    container = builder.build()

    assert [issue.code for issue in container.build_report.warnings] == ["unreachable-component"]
    assert len(container.graph.manifest().data["roots"]) == 1
    assert len(container.graph.manifest(all_roots=True).data["roots"]) == 3
    assert container.resolve(Unused).__class__ is Unused


def test_missing_and_ambiguous_entrypoints_have_structured_findings():
    class Missing:
        pass

    missing_builder = ContainerBuilder()
    missing_builder.mark_entrypoint(Missing)
    with pytest.raises(ContainerBuildError) as raised:
        missing_builder.build()
    report = raised.value.report
    assert report is not None
    assert report.errors[0].code == "missing-entrypoint"

    class Service:
        pass

    class First(Service):
        pass

    class Second(Service):
        pass

    ambiguous_builder = ContainerBuilder()
    ambiguous_builder.register(Service, First)
    ambiguous_builder.register(Service, Second)
    ambiguous_builder.mark_entrypoint(Service)
    report = ambiguous_builder.build().build_report
    assert any(issue.code == "ambiguous-selection" for issue in report.warnings)


def test_collection_entrypoint_marks_every_matching_member():
    class Handler:
        pass

    class First(Handler):
        pass

    class Second(Handler):
        pass

    builder = ContainerBuilder()
    builder.register(Handler, First)
    builder.register(Handler, Second)
    builder.mark_entrypoint(list[Handler])
    container = builder.build()

    assert len(container.graph.entrypoints) == 2
    assert not container.build_report.warnings

    missing_builder = ContainerBuilder()
    missing_builder.mark_entrypoint(list[Handler])
    with pytest.raises(ContainerBuildError) as raised:
        missing_builder.build()
    report = raised.value.report
    assert report is not None
    assert report.errors[0].code == "missing-entrypoint"


def test_overlay_anchors_parent_singletons_and_starts_a_fresh_scoped_cache():
    class Dependency:
        pass

    class RootDependency(Dependency):
        pass

    class OverlayDependency(Dependency):
        pass

    class SingletonService:
        def __init__(self, dependency: Dependency):
            self.dependency = dependency

    class ScopedService:
        def __init__(self, dependency: Dependency):
            self.dependency = dependency

    class OverlaySingletonDecorator:
        def __init__(self, child: SingletonService, dependency: Dependency):
            self.child = child
            self.dependency = dependency

    builder = ContainerBuilder()
    builder.register(Dependency, RootDependency, lifespan="singleton")
    builder.register(SingletonService, lifespan="singleton")
    builder.register(ScopedService, lifespan="scoped")
    container = builder.build()
    parent_scoped = container.resolve(ScopedService)

    overlay_builder = container.new_scope_builder()
    overlay_builder.register(Dependency, OverlayDependency, lifespan="scoped")
    overlay_builder.register_decorator(
        SingletonService,
        OverlaySingletonDecorator,
        decorated_arg="child",
    )
    overlay = overlay_builder.build()
    overlay_singleton = overlay.resolve(SingletonService)
    overlay_scoped = overlay.resolve(ScopedService)

    assert isinstance(overlay_singleton.dependency, RootDependency)
    assert overlay_singleton is container.resolve(SingletonService)
    assert overlay_scoped is not parent_scoped
    assert isinstance(overlay_scoped.dependency, OverlayDependency)


@pytest.mark.parametrize("owner_lifespan", ["singleton", "scoped"])
def test_long_lived_components_cannot_transitively_capture_once_per_graph(owner_lifespan):
    class GraphLocal:
        pass

    class TransientWrapper:
        def __init__(self, graph_local: GraphLocal):
            self.graph_local = graph_local

    class Owner:
        def __init__(self, wrapper: TransientWrapper):
            self.wrapper = wrapper

    builder = ContainerBuilder()
    builder.register(GraphLocal)
    builder.register(TransientWrapper, lifespan="transient")
    builder.register(Owner, lifespan=owner_lifespan)

    with pytest.raises(ContainerBuildError) as raised:
        builder.build()

    report = raised.value.report
    assert report is not None
    issue = next(issue for issue in report.errors if issue.root and issue.root.endswith("Owner"))
    assert issue.code == "captive-dependency"
    assert tuple(part.rsplit(".", 1)[-1] for part in issue.path) == (
        "Owner",
        "TransientWrapper",
        "GraphLocal",
    )
    assert "once-per-graph" in issue.message


@pytest.mark.parametrize("owner_lifespan", ["singleton", "scoped"])
@pytest.mark.parametrize(
    "edge",
    ["constructor", "factory", "decorator", "collection", "provider-fallback", "pre-configuration"],
)
def test_once_per_graph_capture_is_rejected_across_compiled_edge_types(owner_lifespan, edge):
    class GraphLocal:
        pass

    class Service:
        pass

    builder = ContainerBuilder()
    builder.register(GraphLocal)

    if edge == "constructor":

        class ConstructorService(Service):
            def __init__(self, graph_local: GraphLocal):
                self.graph_local = graph_local

        builder.register(Service, ConstructorService, lifespan=owner_lifespan)
    elif edge == "factory":

        def create_service(graph_local: GraphLocal) -> Service:
            return Service()

        builder.register(Service, factory=create_service, lifespan=owner_lifespan)
    elif edge == "decorator":

        class ServiceDecorator(Service):
            def __init__(self, child: Service, graph_local: GraphLocal):
                self.child = child
                self.graph_local = graph_local

        builder.register(Service, lifespan=owner_lifespan)
        builder.register_decorator(Service, ServiceDecorator, decorated_arg="child")
    elif edge == "collection":

        class CollectionService(Service):
            def __init__(self, graph_locals: list[GraphLocal]):
                self.graph_locals = graph_locals

        builder.register(Service, CollectionService, lifespan=owner_lifespan)
    elif edge == "provider-fallback":

        class ProviderService(Service):
            def __init__(self, graph_local: GraphLocal):
                self.graph_local = graph_local

        def use_fallback(default, context):
            return EMPTY

        builder.register(
            Service,
            ProviderService,
            lifespan=owner_lifespan,
            dependency_config={"graph_local": DependencySettings(value_factory=use_fallback)},
        )
    else:

        def configure(graph_local: GraphLocal) -> None:
            pass

        builder.register(Service, lifespan=owner_lifespan)
        builder.pre_configure(Service, configure)

    with pytest.raises(ContainerBuildError) as raised:
        builder.build()

    report = raised.value.report
    assert report is not None
    issue = next(issue for issue in report.errors if issue.root and issue.root.endswith("Service"))
    assert issue.code == "captive-dependency"
    assert issue.path[0].endswith("Service")
    assert issue.path[-1].endswith("GraphLocal")


@pytest.mark.parametrize("owner_lifespan", ["singleton", "scoped"])
def test_long_lived_components_may_capture_plain_transients(owner_lifespan):
    class Logger:
        pass

    class Service:
        def __init__(self, logger: Logger):
            self.logger = logger

    builder = ContainerBuilder()
    builder.register(Logger, lifespan="transient")
    builder.register(Service, lifespan=owner_lifespan)
    container = builder.build()

    first = container.resolve(Service)
    second = container.resolve(Service)

    assert first is second
    assert first.logger is second.logger


@pytest.mark.parametrize("dependency_lifespan", ["scoped", "singleton"])
def test_once_per_graph_components_may_depend_on_longer_lived_components(dependency_lifespan):
    class LongLived:
        pass

    class GraphLocal:
        def __init__(self, long_lived: LongLived):
            self.long_lived = long_lived

    builder = ContainerBuilder()
    builder.register(LongLived, lifespan=dependency_lifespan)
    builder.register(GraphLocal)
    container = builder.build()

    first = container.resolve(GraphLocal)
    second = container.resolve(GraphLocal)

    assert first is not second
    assert first.long_lived is second.long_lived


def test_failed_once_per_graph_capture_build_remains_reusable():
    class GraphLocal:
        pass

    class SingletonService:
        def __init__(self, graph_local: GraphLocal):
            self.graph_local = graph_local

    builder = ContainerBuilder()
    component_id = builder.register(GraphLocal)
    builder.register(SingletonService, lifespan="singleton")

    with pytest.raises(ContainerBuildError):
        builder.build()

    builder.patch_component(GraphLocal, component_id, lifespan="singleton")
    assert isinstance(builder.build().resolve(SingletonService).graph_local, GraphLocal)


@pytest.mark.parametrize("dependency_lifespan", ["once_per_graph", "scoped"])
def test_singleton_pre_configuration_dependencies_are_validated_against_the_initializer(
    dependency_lifespan,
):
    class ConfigurationDependency:
        pass

    class TransientTarget:
        pass

    def configure(dependency: ConfigurationDependency) -> None:
        pass

    builder = ContainerBuilder()
    builder.register(ConfigurationDependency, lifespan=dependency_lifespan)
    builder.register(TransientTarget, lifespan="transient")
    builder.pre_configure(TransientTarget, configure)

    with pytest.raises(ContainerBuildError) as raised:
        builder.build()

    report = raised.value.report
    assert report is not None
    issue = next(issue for issue in report.errors if issue.root and issue.root.endswith("TransientTarget"))
    assert issue.code == "captive-dependency"
    assert tuple(part.rsplit(".", 1)[-1] for part in issue.path) == (
        "TransientTarget",
        "configure",
        "ConfigurationDependency",
    )


def test_missing_pre_configuration_dependency_is_reported_at_build():
    class MissingDependency:
        pass

    class Service:
        pass

    def configure(dependency: MissingDependency) -> None:
        pass

    builder = ContainerBuilder()
    builder.register(Service)
    builder.pre_configure(Service, configure)

    with pytest.raises(ContainerBuildError) as raised:
        builder.build()

    report = raised.value.report
    assert report is not None
    issue = next(issue for issue in report.errors if issue.root and issue.root.endswith("Service"))
    assert issue.code == "missing-component"
    assert tuple(part.rsplit(".", 1)[-1] for part in issue.path) == (
        "Service",
        "configure",
        "MissingDependency",
    )


def test_shared_pre_configuration_dependency_cannot_trigger_the_same_definition():
    class First:
        pass

    class Second:
        pass

    def configure(second: Second) -> None:
        pass

    builder = ContainerBuilder()
    builder.register(First)
    builder.register(Second, lifespan="singleton")
    builder.pre_configure((First, Second), configure)

    with pytest.raises(ContainerBuildError) as raised:
        builder.build()

    report = raised.value.report
    assert report is not None
    issue = next(
        issue
        for issue in report.errors
        if issue.code == "circular-dependency" and "Circular pre-configuration trigger" in issue.message
    )
    assert "Circular pre-configuration trigger" in issue.message
    assert tuple(part.rsplit(".", 1)[-1] for part in issue.path) == (
        "First",
        "configure",
        "Second",
        "configure",
    )


def test_inherited_pre_configuration_keeps_its_frozen_parent_dependency_plan():
    class Dependency:
        pass

    class OverlayDependency(Dependency):
        pass

    class Service:
        pass

    configured_with: list[type] = []

    def configure(dependency: Dependency) -> None:
        configured_with.append(type(dependency))

    builder = ContainerBuilder()
    builder.register(Dependency, lifespan="singleton")
    builder.register(Service, lifespan="transient")
    builder.pre_configure(Service, configure)
    container = builder.build()

    overlay_builder = container.new_scope_builder()
    overlay_builder.register(Dependency, OverlayDependency, lifespan="singleton")
    overlay = overlay_builder.build()

    overlay.resolve(Service)

    assert configured_with == [Dependency]


def test_inherited_pre_configuration_requires_a_frozen_parent_plan():
    class ExistingService:
        pass

    class OverlayService:
        pass

    def configure() -> None:
        pass

    builder = ContainerBuilder()
    builder.register(ExistingService)
    builder.pre_configure(OverlayService, configure)
    container = builder.build()

    overlay_builder = container.new_scope_builder()
    overlay_builder.register(OverlayService)

    with pytest.raises(ContainerBuildError) as raised:
        overlay_builder.build()

    report = raised.value.report
    assert report is not None
    issue = next(issue for issue in report.errors if issue.root and issue.root.endswith("OverlayService"))
    assert issue.code == "overlay-pre-configuration"
    assert "has no frozen parent plan" in issue.message


def test_graph_text_mermaid_and_json_renderers_are_available():
    class Service:
        pass

    builder = ContainerBuilder()
    builder.register(Service)
    container = builder.build()

    assert "Resolve" in container.graph.to_text()
    assert container.graph.to_mermaid().startswith("flowchart TD")
    assert json.loads(container.graph.manifest().to_json())["schema_version"] == 1


def test_graph_renderers_show_decorator_positions_outside_to_inside():
    class Service:
        pass

    class Inner:
        def __init__(self, child: Service):
            self.child = child

    class Outer:
        def __init__(self, child: Service):
            self.child = child

    builder = ContainerBuilder()
    builder.register(Service)
    builder.register_decorator(Service, Inner, position=100)
    builder.register_decorator(Service, Outer, position=1000)
    graph = builder.build().graph

    text = graph.to_text()
    assert text.index("Outer") < text.index("Inner")
    assert "position=1000" in text
    decorators = graph.manifest().data["roots"][0]["decorators"]
    assert [item["implementation"].split(".")[-1] for item in decorators] == ["Outer", "Inner"]
    assert [item["position"] for item in decorators] == [1000, 100]


def test_cli_check_graph_and_diff_contract(tmp_path: Path, capsys):
    target = "tests.tooling_targets:valid_builder"
    assert main(["check", target]) == 0
    assert "unreachable-component" in capsys.readouterr().out

    assert main(["check", target, "--strict"]) == 1
    capsys.readouterr()
    assert main(["check", target, "--strict", "--ignore", "unreachable-component"]) == 0
    capsys.readouterr()

    baseline = tmp_path / "graph.json"
    assert main(["graph", target, "--format", "json", "--output", str(baseline)]) == 0
    assert GraphManifest.from_json(baseline.read_text()).data["schema_version"] == 1
    capsys.readouterr()

    assert main(["diff", target, str(baseline)]) == 0
    assert "unchanged" in capsys.readouterr().out
    assert main(["diff", "tests.tooling_targets:changed_builder", str(baseline)]) == 1
    assert "changed" in capsys.readouterr().out


def test_cli_manifest_is_stable_across_processes():
    command = [
        sys.executable,
        "-m",
        "clean_ioc.cli",
        "graph",
        "tests.tooling_targets:valid_builder",
        "--format",
        "json",
    ]

    first = subprocess.run(command, check=True, capture_output=True, text=True)  # noqa: S603
    second = subprocess.run(command, check=True, capture_output=True, text=True)  # noqa: S603

    assert json.loads(first.stdout) == json.loads(second.stdout)
    assert " at 0x" not in first.stdout


def test_cli_reports_invalid_builds_and_bad_targets(capsys):
    assert main(["check", "tests.tooling_targets:invalid_builder"]) == 1
    assert "missing-component" in capsys.readouterr().err
    assert main(["check", "not-a-locator"]) == 2
    assert "module:object" in capsys.readouterr().err


def test_manifest_rejects_unknown_schema():
    with pytest.raises(ValueError, match="Unsupported graph manifest schema"):
        GraphManifest.from_json('{"schema_version": 99, "roots": []}')
