"""Explicit provider roots reduce physical preparation without changing injection."""

from collections.abc import AsyncIterator, Mapping
from typing import Generic, TypeVar

import pytest
from typing_extensions import TypeAliasType

from clean_ioc import (
    AsyncManagedProvider,
    AsyncProvider,
    CannotResolveError,
    CompilationBudget,
    CompilationProfiler,
    ContainerBuilder,
    ContainerBuildError,
    Instrumentation,
    ManagedProvider,
    Provider,
    ResolutionContext,
    ResolutionProfiler,
)
from clean_ioc import component_filters as cf


class Resource:
    pass


FAMILIES = (Provider, AsyncProvider, ManagedProvider, AsyncManagedProvider)
FORMS = (Resource, list[Resource], tuple[Resource, ...], set[Resource])


@pytest.mark.parametrize("family", FAMILIES)
@pytest.mark.parametrize("target", FORMS)
@pytest.mark.parametrize("diagnostics", [False, True])
async def test_declared_family_and_form_are_the_only_public_provider_roots(family, target, diagnostics):
    builder = ContainerBuilder()
    builder.register(Resource)
    annotation = family[target]
    async with builder.build(provider_roots=[annotation], diagnostics=diagnostics) as container:
        assert tuple(container._plan.provider_roots) == (annotation,)
        assert container.has_component(annotation)
        handle = container.resolve(annotation)
        if family is ManagedProvider:
            with handle() as value:
                assert isinstance(value, Resource if target is Resource else target.__origin__)
        elif family is AsyncManagedProvider:
            async with handle() as value:
                assert isinstance(value, Resource if target is Resource else target.__origin__)
        elif family is AsyncProvider:
            value = await handle()
            assert isinstance(value, Resource if target is Resource else target.__origin__)
        else:
            value = handle()
            assert isinstance(value, Resource if target is Resource else target.__origin__)
        for other_family in FAMILIES:
            for other_target in FORMS:
                other = other_family[other_target]
                if other != annotation:
                    assert not container.has_component(other)
                    with pytest.raises(CannotResolveError):
                        container.resolve(other)


def test_empty_declaration_preserves_injected_handles_provider_maps_and_default_collections(monkeypatch):
    class Consumer:
        def __init__(self, resource: Provider[Resource]):
            self.resource = resource

    builder = ContainerBuilder()
    builder.register(Resource)
    builder.register(Consumer)
    builder.register_provider_map(Resource, key=lambda component: component.id)
    container = builder.build(provider_roots=())
    monkeypatch.setattr(ContainerBuilder, "build", lambda *a, **kw: pytest.fail("runtime compilation"))
    assert isinstance(container.resolve(Consumer).resource(), Resource)
    assert len(container.resolve(list[Resource])) == 1
    assert container.resolve(list[Provider[Resource]]) == []
    assert not container._plan.provider_roots
    assert not container._plan.managed_provider_roots
    assert isinstance(next(iter(container.resolve(Mapping[str, Provider[Resource]]).values()))(), Resource)
    with pytest.raises(CannotResolveError):
        container.resolve(AsyncManagedProvider[Resource])
    container.__exit__()


@pytest.mark.parametrize("lookup", [Resource, list[Resource], AsyncProvider[Resource], AsyncProvider[list[Resource]]])
@pytest.mark.parametrize("observed", [False, True])
async def test_managed_context_uses_private_frozen_targets_and_closes_resources(lookup, observed, monkeypatch):
    events = []

    async def resource() -> AsyncIterator[Resource]:
        value = Resource()
        events.append("open")
        try:
            yield value
        finally:
            events.append("closed")

    async def target(context: ResolutionContext) -> object:
        result = await context.resolve_async(lookup)
        return await result() if lookup in (AsyncProvider[Resource], AsyncProvider[list[Resource]]) else result

    builder = ContainerBuilder()
    resource_id = builder.register(Resource, factory=resource, lifespan="scoped")
    builder.register(object, factory=target)
    profiler = ResolutionProfiler() if observed else None
    requested = (
        (AsyncManagedProvider[object], lookup)
        if lookup in (AsyncProvider[Resource], AsyncProvider[list[Resource]])
        else (AsyncManagedProvider[object],)
    )
    async with builder.build(
        provider_roots=requested, instrumentation=Instrumentation(profiler) if profiler is not None else None
    ) as container:
        monkeypatch.setattr(ContainerBuilder, "build", lambda *a, **kw: pytest.fail("runtime compilation"))
        async with container.resolve(AsyncManagedProvider[object])() as result:
            assert isinstance(result, list if lookup in (list[Resource], AsyncProvider[list[Resource]]) else Resource)
            assert events == ["open"]
        assert events == ["open", "closed"]
        assert not container.has_component(AsyncManagedProvider[Resource])
        if profiler is not None:
            assert any(record.registration == resource_id and record.completed for record in profiler.report().records)


def test_declared_alias_names_filters_fallback_and_overlay_singleton_anchor():
    alias = TypeAliasType("alias", Resource)
    builder = ContainerBuilder()
    builder.register_fallback(Resource)
    builder.register(Resource, name="named", lifespan="singleton")
    container = builder.build(provider_roots=[Provider[alias], Provider[Resource]])
    assert tuple(container._plan.provider_roots) == (Provider[Resource],)
    assert isinstance(container.resolve(Provider[alias])(), Resource)
    named = container.resolve(Provider[alias], filter=cf.with_name("named"))()
    assert container.resolve(list[Provider[Resource]]) == []
    handles = container.resolve(list[Provider[Resource]], filter=cf.with_name("named"))
    assert len(handles) == 1 and handles[0]() is named
    overlay_builder = container.new_scope_builder()
    overlay_builder.register(Resource, name="named")
    with overlay_builder.build(provider_roots=[Provider[Resource]]) as overlay:
        assert overlay.resolve(Provider[Resource], filter=cf.with_name("named"))() is not named
    assert container.resolve(Provider[Resource], filter=cf.with_name("named"))() is named
    container.__exit__()


def test_provider_entrypoint_is_automatically_declared():
    builder = ContainerBuilder()
    builder.register(Resource)
    builder.mark_entrypoint(Provider[list[Resource]])
    with builder.build(provider_roots=()) as container:
        assert len(container.resolve(Provider[list[Resource]])()) == 1
        assert tuple(container._plan.provider_roots) == (Provider[list[Resource]],)


@pytest.mark.parametrize("invalid", [(Resource,), (None,), 3])
def test_invalid_option_does_not_consume_builder(invalid):
    builder = ContainerBuilder()
    builder.register(Resource)
    with pytest.raises(TypeError):
        builder.build(provider_roots=invalid)
    assert isinstance(builder.build(provider_roots=()).resolve(Resource), Resource)


def test_missing_declared_provider_fails_at_build_and_builder_can_be_repaired():
    builder = ContainerBuilder()
    with pytest.raises(ContainerBuildError) as caught:
        builder.build(provider_roots=[Provider[Resource]])
    assert caught.value.report is not None
    assert "provider-missing-component" in {issue.code for issue in caught.value.report.errors}
    builder.register(Resource)
    assert isinstance(builder.build(provider_roots=[Provider[Resource]]).resolve(Provider[Resource])(), Resource)


def test_all_ordinary_roots_remain_validated_with_empty_provider_declaration():
    class Invalid:
        def __init__(self, missing: Resource):
            pass

    builder = ContainerBuilder()
    builder.register(Invalid)
    with pytest.raises(ContainerBuildError) as caught:
        builder.build(provider_roots=())
    assert caught.value.report is not None
    assert "missing-component" in {issue.code for issue in caught.value.report.errors}


def test_declared_closed_generic_target_is_compiled_during_build():
    item = TypeVar("item")

    class GenericResource(Generic[item]):
        pass

    builder = ContainerBuilder()
    builder.register(GenericResource)
    with builder.build(provider_roots=[Provider[GenericResource[int]]]) as container:
        assert isinstance(container.resolve(Provider[GenericResource[int]])(), GenericResource)


def test_private_managed_closure_is_counted_in_physical_budget_and_profile():
    class Consumer:
        def __init__(self, resource: ManagedProvider[Resource]):
            self.resource = resource

    builder = ContainerBuilder()
    builder.register(Resource)
    builder.register(Consumer)
    profile = CompilationProfiler(max_records=0)
    with builder.build(provider_roots=(), profile=profile, budget=CompilationBudget(graph_occurrences=8)) as container:
        assert len(container._plan.graph._records or {}) == 6
        assert len(container._plan.graph._views) == 2
        assert profile.report().counters.to_dict()["provider adapters"] == 2
    builder = ContainerBuilder()
    builder.register(Resource)
    with pytest.raises(ContainerBuildError) as caught:
        builder.build(provider_roots=(), budget=CompilationBudget(graph_occurrences=0))
    assert caught.value.report is not None
    assert "compilation-budget-exceeded" in {issue.code for issue in caught.value.report.errors}


def test_full_mode_shares_managed_roots_and_keeps_every_form():
    builder = ContainerBuilder()
    builder.register(Resource)
    with builder.build() as container:
        assert len(container._plan.provider_roots) == 16
        for target in FORMS:
            annotation = AsyncManagedProvider[target]
            assert container._plan.managed_provider_roots[annotation] is container._plan.provider_roots[annotation]


@pytest.mark.parametrize("declared", [False, True])
@pytest.mark.parametrize("observed", [False, True])
async def test_managed_scalar_context_filter_observes_provider_parent_once(declared, observed):
    alias = TypeAliasType("alias", Resource)
    inspected = []

    def select_named(component):
        inspected.append(component)
        assert component.parent is not None
        assert component.parent.service_type == AsyncManagedProvider[Resource]
        assert component.occurrence_id != component._graph.view_source(component.occurrence_id)[1]
        return component.name == "selected"

    async def target(context: ResolutionContext) -> object:
        return await context.resolve_async(alias, filter=select_named)

    builder = ContainerBuilder()
    builder.register_fallback(Resource)
    selected_id = builder.register(Resource, name="selected")
    builder.register(Resource, name="skipped")
    builder.register(object, factory=target)
    with builder.build(
        provider_roots=[AsyncManagedProvider[object]] if declared else None,
        instrumentation=Instrumentation(ResolutionProfiler()) if observed else None,
    ) as container:
        async with container.resolve(AsyncManagedProvider[object])() as value:
            assert isinstance(value, Resource)
        assert [component.name for component in inspected] == ["skipped", "selected"]
        assert inspected[-1].id == selected_id


@pytest.mark.parametrize("observed", [False, True])
async def test_private_closure_survives_orphan_pruning_and_overlay_parent_anchor(observed):
    created = []

    class Dependency:
        pass

    class Product:
        def __init__(self, dependency: Dependency):
            self.dependency = dependency

    async def product(context: ResolutionContext) -> object:
        return await context.resolve_async(Product)

    builder = ContainerBuilder()
    builder.register(Dependency, root_policy="dependency_only", lifespan="singleton")
    builder.register(Product, lifespan="singleton")
    builder.register(object, factory=product)
    async with builder.build(
        provider_roots=[AsyncManagedProvider[object]],
        instrumentation=Instrumentation(ResolutionProfiler()) if observed else None,
    ) as container:
        async with container.resolve(AsyncManagedProvider[object])() as original:
            created.append(original)
        overlay_builder = container.new_scope_builder()
        overlay_builder.register(Dependency)
        async with overlay_builder.build(provider_roots=[AsyncManagedProvider[object]]) as overlay:
            async with overlay.resolve(AsyncManagedProvider[object])() as inherited:
                assert inherited is original
        assert Dependency in container._plan.blueprint.service_types()
        assert len(created) == 1


def test_absence_of_managed_handles_avoids_managed_conversion_and_private_graphs(monkeypatch):
    from clean_ioc.container import _Compiler

    monkeypatch.setattr(_Compiler, "_managed_adapter_target", lambda *a: pytest.fail("unneeded managed conversion"))
    builder = ContainerBuilder()
    builder.register(Resource)
    with builder.build(provider_roots=(), budget=CompilationBudget(graph_occurrences=1)) as container:
        assert len(container._plan.graph._records or {}) == 1
        assert not container._plan.graph._views
        assert not container._plan.managed_provider_roots
        assert isinstance(container.resolve(Resource), Resource)


@pytest.mark.parametrize("observed", [False, True])
async def test_injected_managed_handle_keeps_private_context_closure_without_public_provider_roots(observed):
    events = []

    async def resource() -> AsyncIterator[Resource]:
        events.append("open")
        try:
            yield Resource()
        finally:
            events.append("closed")

    async def product(context: ResolutionContext) -> object:
        return await context.resolve_async(Resource)

    class Consumer:
        def __init__(self, products: AsyncManagedProvider[object]):
            self.products = products

    builder = ContainerBuilder()
    builder.register(Resource, factory=resource, lifespan="scoped")
    builder.register(object, factory=product)
    builder.register(Consumer)
    async with builder.build(
        provider_roots=(), instrumentation=Instrumentation(ResolutionProfiler()) if observed else None
    ) as container:
        consumer = container.resolve(Consumer)
        assert not container._plan.provider_roots
        assert AsyncManagedProvider[Resource] in container._plan.managed_provider_roots
        async with consumer.products() as value:
            assert isinstance(value, Resource)
            assert events == ["open"]
        assert events == ["open", "closed"]


def test_declared_provider_root_keeps_boundary_exposure_and_private_service_hidden():
    from clean_ioc import Expose

    class Hidden:
        pass

    class Product:
        def __init__(self, hidden: Hidden):
            self.hidden = hidden

    builder = ContainerBuilder()
    boundary = builder.create_boundary("resources", exposes=[Expose(Product)])
    boundary.register(Hidden)
    boundary.register(Product)
    with builder.build(provider_roots=[Provider[Product]]) as container:
        assert isinstance(container.resolve(Provider[Product])().hidden, Hidden)
        assert not container.has_component(Hidden)
        assert not container.has_component(Provider[Hidden])


def test_declared_empty_collection_preserves_early_rejected_service_contract():
    builder = ContainerBuilder()
    builder.register(Resource, candidate_when=cf.parent(cf.service_type_is(object)))
    with builder.build(provider_roots=[Provider[list[Resource]]]) as container:
        assert container.resolve(Provider[list[Resource]])() == []
