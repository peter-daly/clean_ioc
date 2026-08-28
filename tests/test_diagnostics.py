from contextlib import asynccontextmanager
from typing import Protocol

import pytest

from clean_ioc import (
    Container,
    ContainerValidationError,
    CurrentGraph,
    DependencyContext,
    DependencySettings,
    Lifespan,
)
from clean_ioc.registration_filters import with_name
from clean_ioc.value_factories import dont_use_default_value


class Repository:
    pass


class Service:
    def __init__(self, repository: Repository):
        self.repository = repository


class MissingDependency:
    pass


class BrokenService:
    def __init__(self, missing: MissingDependency):
        self.missing = missing


class CircularA:
    def __init__(self, dependency: "CircularB"):
        self.dependency = dependency


class CircularB:
    def __init__(self, dependency: CircularA):
        self.dependency = dependency


class Clock:
    pass


class TracedService:
    def __init__(self, wrapped: Service, clock: Clock):
        self.wrapped = wrapped
        self.clock = clock


def test_explain_builds_a_readable_plan_without_creating_instances():
    creations = 0

    def create_repository() -> Repository:
        nonlocal creations
        creations += 1
        return Repository()

    container = Container()
    container.register(Repository, factory=create_repository, lifespan=Lifespan.singleton)
    container.register(Clock, lifespan=Lifespan.singleton)
    container.register(Service, lifespan=Lifespan.singleton)
    container.register_decorator(Service, TracedService, decorated_arg="wrapped")

    plan = container.explain(Service)

    assert plan.is_valid
    assert creations == 0
    assert "Service [singleton]" in plan.to_text()
    assert "repository: Repository -> create_repository [singleton]" in plan.to_text()
    assert "Service -> TracedService [singleton, decorator]" in plan.to_text()
    assert plan.to_mermaid().startswith("flowchart TD")


def test_validate_reports_a_missing_registration():
    container = Container()
    container.register(BrokenService)

    with pytest.raises(ContainerValidationError) as raised:
        container.validate(BrokenService)

    assert raised.value.issues[0].code == "missing-registration"
    assert raised.value.issues[0].path == ("BrokenService", "MissingDependency")


def test_validate_reports_a_circular_dependency():
    container = Container()
    container.register(CircularA)
    container.register(CircularB)

    with pytest.raises(ContainerValidationError) as raised:
        container.validate(CircularA)

    assert raised.value.issues[0].code == "circular-dependency"
    assert "CircularA -> CircularB -> CircularA" in raised.value.issues[0].message


def test_validate_reports_a_captive_dependency():
    container = Container()
    container.register(Repository, lifespan=Lifespan.scoped)
    container.register(Service, lifespan=Lifespan.singleton)

    with pytest.raises(ContainerValidationError) as raised:
        container.validate(Service)

    assert raised.value.issues[0].code == "captive-dependency"
    assert "Singleton Service cannot depend on scoped Repository" in raised.value.issues[0].message


def test_validate_can_reject_async_only_graphs_for_sync_entrypoints():
    async def create_repository() -> Repository:
        return Repository()

    container = Container()
    container.register(Repository, factory=create_repository)

    with pytest.raises(ContainerValidationError) as raised:
        container.validate(Repository, allow_async=False)

    assert raised.value.issues[0].code == "async-required"
    assert container.validate(Repository).is_valid


def test_validate_rejects_async_context_manager_factories_for_sync_entrypoints():
    @asynccontextmanager
    async def create_repository():
        yield Repository()

    container = Container()
    container.register(Repository, factory=create_repository)

    with pytest.raises(ContainerValidationError) as raised:
        container.validate(Repository, allow_async=False)

    assert raised.value.issues[0].code == "async-required"


def test_custom_value_providers_are_treated_as_static_boundaries_without_being_called():
    calls = 0

    def provide_value(default, context):
        nonlocal calls
        calls += 1
        return "configured"

    class ConfiguredService:
        def __init__(self, value: str):
            self.value = value

    container = Container()
    container.register(
        ConfiguredService,
        dependency_config={"value": DependencySettings(value_factory=provide_value)},
    )

    plan = container.explain(ConfiguredService)

    assert plan.is_valid
    assert calls == 0
    assert "value: str [supplied value]" in plan.to_text()


def test_dont_use_default_value_still_validates_the_required_registration():
    class ConfiguredService:
        def __init__(self, value: str = "fallback"):
            self.value = value

    container = Container()
    container.register(
        ConfiguredService,
        dependency_config={"value": DependencySettings(value_factory=dont_use_default_value)},
    )

    with pytest.raises(ContainerValidationError) as raised:
        container.validate(ConfiguredService)

    assert raised.value.issues[0].code == "missing-registration"


def test_validate_without_roots_checks_every_visible_registration():
    container = Container()
    container.register(Repository)
    container.register(Service)

    report = container.validate()

    assert report.is_valid
    assert report.checked_roots >= 2


def test_explain_models_collections_preconfigurations_and_special_dependencies():
    class Plugin(Protocol):
        pass

    class FirstPlugin:
        pass

    class SecondPlugin:
        pass

    class SetupDependency:
        pass

    class Host:
        def __init__(
            self,
            plugins: list[Plugin],
            context: DependencyContext,
            graph: CurrentGraph,
        ):
            self.plugins = plugins
            self.context = context
            self.graph = graph

    calls = 0

    def configure(setup: SetupDependency) -> None:
        nonlocal calls
        calls += 1

    container = Container()
    container.register(Plugin, FirstPlugin)
    container.register(Plugin, SecondPlugin)
    container.register(SetupDependency)
    container.register(Host)
    container.pre_configure(Host, configure)

    plan = container.explain(Host)
    text = plan.to_text()

    assert plan.is_valid
    assert calls == 0
    assert "plugins: list[Plugin] -> list [transient, collection]" in text
    assert "Plugin -> FirstPlugin" in text
    assert "Plugin -> SecondPlugin" in text
    assert "Host -> configure [singleton, pre-configuration]" in text
    assert "setup: SetupDependency" in text
    assert "context: DependencyContext [transient, context]" in text
    assert "graph: CurrentGraph [transient, current graph]" in text


def test_explain_includes_the_selected_registration_name():
    container = Container()
    container.register(Repository, name="primary")

    plan = container.explain(Repository, filter=with_name("primary"))

    assert plan.is_valid
    assert 'Repository [once_per_graph, name="primary"]' in str(plan)
