"""Runtime discovery follows selected plans without creating public roots."""

from collections.abc import Mapping
from dataclasses import FrozenInstanceError
from typing import Generic, TypeVar

import pytest
from typing_extensions import TypeAliasType

from clean_ioc import (
    BoundaryAlias,
    ContainerBuilder,
    Expose,
    Provider,
    ProviderMapGroup,
    RegistrationInfo,
    Tag,
)

T = TypeVar("T")


@pytest.mark.parametrize("diagnostics", [False, True])
def test_selected_dependency_only_registration_is_frozen_and_provider_views_deduplicate(diagnostics):
    class Route:
        pass

    class ClosedRoute(Route, Generic[T]):
        pass

    group = ProviderMapGroup("routes", str, Route)

    class Dispatcher:
        def __init__(self, routes: Mapping[str, Provider[Route]], again: Mapping[str, Provider[Route]]):
            self.routes = routes
            self.again = again

    builder = ContainerBuilder()
    route_id = builder.register(
        Route,
        ClosedRoute[int],
        name="selected",
        tags=[Tag("route", "one")],
        root_policy="dependency_only",
        contributes={group: "one"},
    )
    dead = builder.register(Route, ClosedRoute[str], root_policy="dependency_only")
    rejected = builder.register(Route, ClosedRoute[bytes], when=lambda _: False, root_policy="dependency_only")
    builder.register_provider_map(group, root_policy="dependency_only")
    builder.register(Dispatcher)
    container = builder.build(provider_roots=(), diagnostics=diagnostics)
    catalogue = container.selected_registrations
    assert catalogue is container.selected_registrations
    assert isinstance(catalogue, tuple)
    assert all(isinstance(info, RegistrationInfo) for info in catalogue)
    assert not container.has_component(Route)
    assert [item.id for item in catalogue if item.service_type is Route] == [route_id]
    route = next(item for item in catalogue if item.id == route_id)
    assert route.implementation_type == ClosedRoute[int]
    assert route.name == "selected"
    assert route.tags == (Tag("route", "one"),)
    assert route.implementation_bindings(ClosedRoute) == {T: int}
    assert dead not in {item.id for item in catalogue}
    assert rejected not in {item.id for item in catalogue}
    with pytest.raises(FrozenInstanceError):
        setattr(route, "name", "changed")
    with container.new_scope() as scope:
        assert scope.selected_registrations is catalogue
        dispatcher = scope.resolve(Dispatcher)
        assert isinstance(dispatcher.routes["one"](), ClosedRoute)
        assert isinstance(dispatcher.again["one"](), ClosedRoute)


@pytest.mark.parametrize("diagnostics", [False, True])
def test_catalogue_contains_selected_decorator_and_its_private_dependency_only(diagnostics):
    class Service:
        pass

    class Extra:
        pass

    class Wrapper:
        def __init__(self, child: Service, extra: Extra):
            self.child = child
            self.extra = extra

    builder = ContainerBuilder()
    core = builder.register(Service)
    extra = builder.register(Extra, root_policy="dependency_only")
    wrapper = builder.register_decorator(Service, Wrapper, decorated_arg="child", tags=[Tag("selected")])
    rejected = builder.register_decorator(Service, Wrapper, decorated_arg="child", when=lambda _: False)
    container = builder.build(provider_roots=(), diagnostics=diagnostics)
    assert [item.id for item in container.selected_registrations] == [core, wrapper, extra]
    assert rejected not in {item.id for item in container.selected_registrations}
    assert isinstance(container.resolve(Service), Wrapper)


def test_catalogue_normalizes_type_aliases_and_tracks_only_exposed_boundary_execution():
    class Hidden:
        pass

    class Service:
        pass

    class Public:
        pass

    alias = TypeAliasType("alias", Service)
    builder = ContainerBuilder()
    boundary = builder.create_boundary("local", exposes=(Expose(alias, alias=BoundaryAlias(Public)),))
    hidden = boundary.register(Hidden)
    exposed = boundary.register(alias, Service, tags=[Tag("local")])
    container = builder.build(provider_roots=())
    catalogue = container.selected_registrations
    assert hidden not in {item.id for item in catalogue}
    visible = [item for item in catalogue if item.id == exposed]
    assert visible
    assert {item.service_type for item in visible} == {Public}
    assert visible[0].implementation_type is Service
    assert isinstance(container.resolve(Public), Service)


def test_overlay_catalogue_preserves_child_precedence_and_parent_public_alternatives():
    class Service:
        pass

    class Parent(Service):
        pass

    class Child(Service):
        pass

    builder = ContainerBuilder()
    parent_id = builder.register(Service, Parent)
    container = builder.build(provider_roots=())
    overlay = container.new_scope_builder()
    child_id = overlay.register(Service, Child)
    child = overlay.build(provider_roots=())
    assert [item.id for item in container.selected_registrations if item.service_type is Service] == [parent_id]
    assert [item.id for item in child.selected_registrations if item.service_type is Service] == [child_id, parent_id]
    assert isinstance(child.resolve(Service), Child)


def test_unhashable_factory_has_static_metadata_without_retaining_instance_values():
    class Service:
        pass

    class Factory:
        __hash__ = None

        def __call__(self) -> Service:
            return Service()

    builder = ContainerBuilder()
    factory_id = builder.register(Service, factory=Factory())
    container = builder.build(provider_roots=())
    info = next(item for item in container.selected_registrations if item.id == factory_id)
    assert info.implementation_type is Service
    assert isinstance(container.resolve(Service), Service)


def test_catalogue_uses_context_and_fallback_selections_without_repeating_callbacks():
    class Service:
        pass

    class Ordinary:
        pass

    class Fallback:
        pass

    class First:
        def __init__(self, service: Service):
            self.service = service

    class Second:
        def __init__(self, service: Service):
            self.service = service

    calls = []

    def eligible(component):
        calls.append(component.parent.service_type)
        return component.parent.service_type is First

    builder = ContainerBuilder()
    ordinary = builder.register(Service, Ordinary, when=eligible, root_policy="dependency_only")
    fallback = builder.register_fallback(Service, Fallback, root_policy="dependency_only")
    builder.register(First)
    builder.register(Second)
    container = builder.build(provider_roots=(), diagnostics=True)
    callback_count = len(calls)
    assert callback_count > 0
    selections = [item for item in container.selected_registrations if item.service_type is Service]
    assert [item.id for item in selections] == [ordinary, fallback]
    assert isinstance(container.resolve(First).service, Ordinary)
    assert isinstance(container.resolve(Second).service, Fallback)
    assert container.selected_registrations is container.selected_registrations
    assert len(calls) == callback_count


def test_catalogue_includes_warmup_and_anchored_parent_singleton_dependencies_in_overlay():
    from clean_ioc import WarmupPlan, WarmupTarget

    class Dependency:
        pass

    class ParentDependency:
        pass

    class ChildDependency:
        pass

    activated = []

    class Service:
        def __init__(self, dependency: Dependency):
            activated.append(dependency)
            self.dependency = dependency

    builder = ContainerBuilder()
    parent = builder.register(Dependency, ParentDependency, root_policy="dependency_only", lifespan="singleton")
    service = builder.register(Service, lifespan="singleton")
    builder.add_warmup_plan(WarmupPlan("start", [WarmupTarget(Service)]))
    container = builder.build(provider_roots=())
    assert activated == []
    overlay = container.new_scope_builder()
    child_dependency = overlay.register(
        Dependency, ChildDependency, root_policy="dependency_only", lifespan="singleton"
    )
    child = overlay.build(provider_roots=())
    assert activated == []
    assert {item.id for item in child.selected_registrations} == {parent, service}
    assert child_dependency not in {item.id for item in child.selected_registrations}
    assert child.warmup("start").is_valid
    assert isinstance(child.resolve(Service).dependency, ParentDependency)
    assert len(activated) == 1


def test_catalogue_unknown_factory_annotation_does_not_reject_a_valid_build(monkeypatch):
    import clean_ioc.container as implementation

    class Service:
        pass

    def factory():
        return Service()

    # Exercise optional discovery's fallback independently of activation
    # signature parsing: result metadata must never become a build requirement.
    def unsupported(_):
        raise ValueError("No inspectable static result")

    original_catalogue = implementation._selected_registration_catalogue

    def unavailable_catalogue_metadata(plan):
        with monkeypatch.context() as patch:
            patch.setattr(implementation, "_factory_result_annotation", unsupported)
            return original_catalogue(plan)

    monkeypatch.setattr(implementation, "_selected_registration_catalogue", unavailable_catalogue_metadata)
    builder = ContainerBuilder()
    registration = builder.register(Service, factory=factory)
    container = builder.build(provider_roots=())
    info = next(item for item in container.selected_registrations if item.id == registration)
    assert info.implementation_type is None
    assert isinstance(container.resolve(Service), Service)
