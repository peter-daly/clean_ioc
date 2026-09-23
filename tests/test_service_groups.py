"""Explicit service membership before decorator-template selection is available."""

import inspect
from collections.abc import Mapping
from dataclasses import FrozenInstanceError
from typing import Generic, TypeVar, cast

import pytest
from typing_extensions import TypeAliasType

from clean_ioc import ComponentBuilder, ContainerBuilder, Provider, ProviderMapGroup, ServiceGroup
from clean_ioc import component_filters as cf
from clean_ioc.container import _Compiler

T = TypeVar("T")


def memberships(builder: ContainerBuilder) -> Mapping[str, frozenset[ServiceGroup]]:
    return builder._layer().service_groups


def test_public_builder_protocol_and_concrete_methods_accept_groups():
    for builder_type in (ComponentBuilder, ContainerBuilder):
        for method in ("register", "register_pattern", "register_subclasses", "register_generic_subclasses"):
            assert "groups" in inspect.signature(getattr(builder_type, method)).parameters


def test_identity_immutability_and_per_registration_membership_across_builders():
    class Service:
        pass

    first = ServiceGroup("same", service_type=Service)
    second = ServiceGroup("same", service_type=Service)
    assert first is not second and first != second
    with pytest.raises(FrozenInstanceError):
        setattr(first, "name", "changed")

    def once():
        yield first
        yield first
        yield second

    builder = ContainerBuilder()
    grouped = builder.register(Service, name="grouped", groups=once())
    other = builder.register(Service, name="other", groups=[second])
    plain = builder.register(Service, name="plain")
    assert memberships(builder)[grouped] == frozenset({first, second})
    assert memberships(builder)[other] == frozenset({second})
    assert memberships(builder)[plain] == frozenset()

    container = builder.build()
    definition = container._plan.blueprint.registration_definition(grouped)
    assert definition is not None
    assert definition[1].service_groups[grouped] == frozenset({first, second})
    assert isinstance(container.resolve(Service, cf.with_name("grouped")), Service)
    assert isinstance(container.resolve(Service, cf.with_name("other")), Service)

    independent = ContainerBuilder()
    independent_id = independent.register(Service, groups=[first])
    assert memberships(independent)[independent_id] == frozenset({first})
    assert len(memberships(independent)) == 1
    assert isinstance(independent.build().resolve(Service), Service)


def test_factory_instance_and_provider_map_metadata_remain_independent():
    class Service:
        pass

    group = ServiceGroup("members", service_type=Service)
    provider_group = ProviderMapGroup("providers", str, Service)
    instance = Service()
    builder = ContainerBuilder()
    factory_id = builder.register(Service, factory=Service, name="factory", groups=iter([group]))
    instance_id = builder.register(Service, instance=instance, name="instance", groups=[group])
    builder.register_provider_map(provider_group)
    provider_id = builder.register(Service, name="provider", contributes={provider_group: "provider"})

    container = builder.build()
    assert memberships(builder)[factory_id] == memberships(builder)[instance_id] == frozenset({group})
    assert memberships(builder)[provider_id] == frozenset()
    assert container.resolve(Service, cf.with_name("instance")) is instance
    assert isinstance(container.resolve(Service, cf.with_name("factory")), Service)
    assert list(container.resolve(Mapping[str, Provider[Service]])) == ["provider"]


def test_known_contract_failures_are_transactional_and_use_registered_service():
    class Service:
        pass

    class Other:
        pass

    class Implementation(Service):
        pass

    service_group = ServiceGroup("services", service_type=Service)
    other_group = ServiceGroup("other", service_type=Other)
    builder = ContainerBuilder()
    with pytest.raises(TypeError, match="service group 'other'.*Other"):
        builder.register(Service, Implementation, groups=(group for group in (service_group, other_group)))
    with pytest.raises(TypeError, match="service group 'services'"):
        builder.register(Other, factory=Implementation, groups=[service_group])
    with pytest.raises(TypeError, match="ServiceGroup"):
        builder.register(Service, groups=cast(list[ServiceGroup], [object()]))
    assert not any(builder._composition._registry.get_registrations(Service))
    assert not any(builder._composition._registry.get_registrations(Other))
    assert not memberships(builder)

    valid = builder.register(Service, Implementation, groups=[service_group])
    assert memberships(builder)[valid] == frozenset({service_group})
    assert isinstance(builder.build().resolve(Service), Implementation)


def test_generic_projection_rejects_closed_conflicts_and_keeps_open_constraints():
    class Contract(Generic[T]):
        pass

    class Child(Contract[T]):
        pass

    class IntChild(Contract[int]):
        pass

    int_group = ServiceGroup("integers", service_type=Contract[int])
    bare_group = ServiceGroup("all", service_type=Contract)
    builder = ContainerBuilder()
    with pytest.raises(TypeError, match="integers"):
        builder.register(Contract[str], factory=Contract, groups=[int_group])
    with pytest.raises(TypeError, match="integers"):
        builder.register(Child[str], factory=Child, groups=[int_group])
    nested_group = ServiceGroup("nested", service_type=Contract[list[int]])
    with pytest.raises(TypeError, match="nested"):
        builder.register(Contract[list[str]], factory=Contract, groups=[nested_group])
    assert not memberships(builder)

    open_id = builder.register(Child[T], factory=Child, groups=[int_group, bare_group])
    closed_id = builder.register(IntChild, groups=[int_group, bare_group])
    assert memberships(builder)[open_id] == memberships(builder)[closed_id] == frozenset({int_group, bare_group})


def test_aliases_normalize_without_changing_membership_identity():
    class Service:
        pass

    alias = TypeAliasType("alias", Service)
    group = ServiceGroup("alias", service_type=alias)
    builder = ContainerBuilder()
    component_id = builder.register(alias, groups=[group])
    container = builder.build()
    definition = container._plan.blueprint.registration_definition(component_id)
    assert definition is not None
    registration, layer = definition
    assert registration.service_type is Service
    assert layer.service_groups[component_id] == frozenset({group})
    assert isinstance(container.resolve(Service), Service)


def test_subclass_and_generic_discovery_include_fallback_membership():
    class Service:
        pass

    class Found(Service):
        pass

    class GenericService(Generic[T]):
        pass

    class Command:
        pass

    class FoundGeneric(GenericService[Command]):
        pass

    class Fallback(GenericService[T]):
        pass

    simple_group = ServiceGroup("simple", service_type=Service)
    generic_group = ServiceGroup("generic", service_type=GenericService)
    builder = ContainerBuilder()
    builder.register_subclasses(Service, groups=(x for x in (simple_group, simple_group)))
    builder.register_generic_subclasses(GenericService, fallback_type=Fallback, groups=(x for x in (generic_group,)))
    layer = builder._layer()
    simple_ids = [item.id for item in layer.registry.get_registrations(Service) if item.id not in layer.internal_ids]
    generic_ids = [item.id for item in layer.registry.get_registrations(GenericService[Command])]
    fallback_ids = [item.id for item in layer.registry.get_registrations(GenericService)]
    assert simple_ids and all(layer.service_groups[item] == frozenset({simple_group}) for item in simple_ids)
    assert generic_ids and all(layer.service_groups[item] == frozenset({generic_group}) for item in generic_ids)
    assert fallback_ids and all(layer.service_groups[item] == frozenset({generic_group}) for item in fallback_ids)
    container = builder.build()
    assert isinstance(container.resolve(Service), Found)
    assert isinstance(container.resolve(GenericService[Command]), FoundGeneric)


def test_discovery_rejects_incompatible_groups_before_queue_mutation():
    class Service:
        pass

    class Other:
        pass

    wrong = ServiceGroup("wrong", service_type=Other)
    builder = ContainerBuilder()
    with pytest.raises(TypeError, match="wrong"):
        builder.register_subclasses(Service, groups=[wrong])
    with pytest.raises(TypeError, match="wrong"):
        builder.register_generic_subclasses(Service, groups=[wrong])
    assert builder._registration_discoveries == []


def test_discovered_closed_generic_conflict_does_not_publish_partial_cache():
    class Service(Generic[T]):
        pass

    class Accepted(Service[int]):
        pass

    class Rejected(Service[str]):
        pass

    allowed = {Accepted, Rejected}
    group = ServiceGroup("integers", service_type=Service[int])
    builder = ContainerBuilder()
    builder.register_generic_subclasses(Service, groups=[group], subclass_type_filter=lambda item: item in allowed)
    rule = builder._registration_discoveries[0]
    with pytest.raises(TypeError, match="integers"):
        builder.build()
    assert rule.registrations == {}
    assert rule.fallback_registration is None

    allowed.remove(Rejected)
    container = builder.build()
    assert isinstance(container.resolve(Service[int]), Accepted)
    registered = container._plan.blueprint.layers[0].service_groups
    assert len([members for members in registered.values() if group in members]) == 1


def test_overlay_keeps_inherited_membership_and_does_not_infer_it_for_override():
    class Service:
        pass

    group = ServiceGroup("services", service_type=Service)
    root_builder = ContainerBuilder()
    root_id = root_builder.register(Service, name="root", groups=[group])
    container = root_builder.build()

    overlay_builder = container.new_scope_builder()
    override_id = overlay_builder.register(Service, name="override")
    scope = overlay_builder.build()
    inherited = scope._plan.blueprint.registration_definition(root_id)
    override = scope._plan.blueprint.registration_definition(override_id)
    assert inherited is not None and override is not None
    assert inherited[1].service_groups[root_id] == frozenset({group})
    assert override[1].service_groups[override_id] == frozenset()
    assert isinstance(scope.resolve(Service, cf.with_name("override")), Service)


def test_pattern_specialization_retains_membership_by_new_definition_id():
    class Service(Generic[T]):
        pass

    def make_service() -> Service[list[T]]:
        return Service()

    group = ServiceGroup("services", service_type=Service)
    builder = ContainerBuilder()
    template_id = builder.register_pattern(Service[list[T]], factory=make_service, groups=iter([group]))
    compiler = _Compiler(builder.build()._plan.blueprint)
    definition = compiler.blueprint.registration_definition(template_id)
    assert definition is not None
    registration, normalized_layer = definition
    specialized = compiler._specialize_factory(registration, normalized_layer, Service[list[int]])
    assert specialized.id != template_id
    assert specialized.service_type == Service[list[int]]
    assert compiler._service_groups_for(specialized, normalized_layer) == frozenset({group})
