"""Compact runtimes preserve frozen execution and discard overlay composition."""

import gc
import weakref
from collections.abc import AsyncIterator, Iterator

import pytest
from typing_extensions import TypeAliasType

from clean_ioc import (
    AsyncManagedProvider,
    BuilderAlreadyBuiltError,
    ContainerBuilder,
    ContainerBuildError,
    Expose,
    Instrumentation,
    ManagedProvider,
    ResolutionProfiler,
    ScopeBuilder,
    WarmupPlan,
    WarmupTarget,
)
from clean_ioc import component_filters as cf


class Service:
    pass


class Resource:
    def __init__(self):
        self.closed = False


class Product:
    def __init__(self, resource: Resource):
        self.resource = resource


class Runner:
    def __init__(self, products: ManagedProvider[Product]):
        self.products = products


def test_execution_drops_composition_filters_but_preserves_catalogue():
    class Eligibility:
        def __call__(self, component):
            return True

    builder = ContainerBuilder().set_provider_roots(())
    eligibility = Eligibility()
    reference = weakref.ref(eligibility)
    builder.register(Service, when=eligibility, candidate_when=eligibility)
    with builder.build() as container:
        del builder, eligibility
        gc.collect()
        assert reference() is None
        assert not hasattr(container._plan, "_blueprint")
        assert not hasattr(container, "graph")
        with pytest.raises(TypeError, match="composition"):
            ScopeBuilder(container)  # ty: ignore[missing-argument]  # Deliberately invalid input.
        assert container.has_component(Service, cf.implementation_type_is(Service))
        assert container.selected_registrations[0].implementation_type is Service
        assert isinstance(container.resolve(Service), Service)
    builder = ContainerBuilder().set_provider_roots(())
    builder.register(Service)
    with builder.analyse() as result:
        assert result.graph.manifest(all_roots=True).fingerprint
        assert result.graph.to_text(all_roots=True)
        assert result.graph.to_mermaid(all_roots=True)
        assert result.graph.ownership_report()
        assert result.report.is_valid
        assert result.selection_census(all_roots=True)


@pytest.mark.parametrize("diagnostics", [False, True])
@pytest.mark.parametrize("observed", [False, True])
def test_compact_slots_aliases_warmup_managed_private_targets_and_cleanup(diagnostics, observed, monkeypatch):
    slot_alias = TypeAliasType("slot_alias", str)
    events = []

    class SlotConsumer:
        def __init__(self, value: slot_alias):
            self.value = value

    def resource() -> Iterator[Resource]:
        value = Resource()
        try:
            yield value
        finally:
            value.closed = True
            events.append("closed")

    builder = ContainerBuilder()
    builder.declare_scope_slot(slot_alias)
    builder.register(SlotConsumer)
    private = builder.create_boundary("private", exposes=[Expose(Runner)])
    private.register(Resource, factory=resource, lifespan="scoped")
    private.register(Product, lifespan="scoped")
    private.register(Runner, lifespan="singleton")
    builder.register(Service, lifespan="singleton")
    builder.add_warmup_plan(WarmupPlan("startup", [WarmupTarget(Service)]))
    instrumentation = Instrumentation(ResolutionProfiler()) if observed else None
    builder.set_provider_roots(())
    with builder.build(instrumentation=instrumentation, build_args={"mode": "compact"}) as container:
        monkeypatch.setattr(ContainerBuilder, "build", lambda *a, **kw: pytest.fail("unexpected compilation"))
        monkeypatch.setattr(ScopeBuilder, "build", lambda *a, **kw: pytest.fail("unexpected compilation"))
        assert container.build_args == {"mode": "compact"}
        assert container.has_scope_slot(slot_alias)
        assert container.has_scope_slot(str)
        assert container.warmup("startup").results[0].status == "succeeded"
        with container.new_scope() as scope:
            scope.provide(slot_alias, "outer")
            assert scope.has_provision(str)
            with scope.new_scope() as nested:
                assert nested.resolve(SlotConsumer).value == "outer"
                assert nested.resolve(Service) is container.resolve(Service)
                runner = nested.resolve(Runner)
                with runner.products() as product:
                    assert not product.resource.closed
                assert product.resource.closed
                assert not hasattr(nested, "new_scope_builder")
                assert nested.selected_registrations is container.selected_registrations
    assert events == ["closed"]


@pytest.mark.parametrize("operation", ["build", "analyse"])
def test_execution_rules_detach_and_analysis_retains_external_composition(operation):
    class Rule:
        def __init__(self):
            self.calls = 0

        def __call__(self, context):
            self.calls += 1
            assert context.graph.roots
            return ()

    first, second = Rule(), Rule()
    references = weakref.ref(first), weakref.ref(second)
    builder = ContainerBuilder().set_provider_roots(())
    builder.register_subclasses(Service, ensure_import_modules="collections")
    builder.register(Service)
    builder.add_validation_rule(first)
    builder.add_validation_rule(second)
    if operation == "analyse":
        result = builder.analyse()
        container = result.create_runtime()
        assert (first.calls, second.calls) == (1, 1)
        assert result.report.is_valid
        assert result.report.is_valid
        assert (first.calls, second.calls) == (1, 1)
    else:
        container = builder.build()
        assert (first.calls, second.calls) == (0, 0)
    del first, second, builder
    gc.collect()
    assert container.ensured_import_modules == ("collections",)
    assert not hasattr(container._plan, "_blueprint")
    assert not hasattr(container._plan, "validation_rules")
    assert isinstance(container.resolve(Service), Service)
    if operation == "analyse":
        assert all(reference() is not None for reference in references)
        result.close()
        del result
    else:
        container.__exit__()
    gc.collect()
    assert all(reference() is None for reference in references)


def test_default_overlays_can_make_compact_child_with_anchored_singleton_ownership():
    events = []

    def root_resource() -> Iterator[Resource]:
        yield Resource()
        events.append("root")

    class Local:
        pass

    def local_resource() -> Iterator[Local]:
        yield Local()
        events.append("local")

    builder = ContainerBuilder()
    builder.register(Resource, factory=root_resource, lifespan="singleton")
    builder.set_provider_roots(())
    container_composition = builder.retain_composition()
    with builder.build() as container:
        assert container_composition.is_ready
        overlay = ScopeBuilder(container, composition=container_composition)
        overlay.register(Local, factory=local_resource, lifespan="singleton")
        overlay.set_provider_roots(())
        with overlay.build() as child:
            assert not hasattr(child._plan, "_blueprint")
            root = child.resolve(Resource)
            local = child.resolve(Local)
            with child.new_scope() as nested:
                assert nested.resolve(Resource) is root
                assert nested.resolve(Local) is local
                for scope in (child, nested):
                    assert not hasattr(scope, "new_scope_builder")
                    with pytest.raises(TypeError, match="composition"):
                        ScopeBuilder(scope)  # ty: ignore[missing-argument]  # Deliberately invalid input.
        assert events == ["local"]
        assert container.resolve(Resource) is root
        composition_builder_213 = ScopeBuilder(container, composition=container_composition)
        composition_builder_213.set_provider_roots(())
        with composition_builder_213.build() as sibling:
            assert not hasattr(sibling, "new_scope_builder")
            assert sibling.resolve(Resource) is root
    assert events == ["local", "root"]


@pytest.mark.parametrize("overlay", [False, True])
@pytest.mark.parametrize("invalid", [None, 0, 1, "false", ()])
def test_invalid_flag_rejected_before_discovery_or_builder_consumption(overlay, invalid):
    composition_builder_222 = ContainerBuilder()
    composition_builder_222.set_provider_roots(())
    parent_composition = composition_builder_222.retain_composition()
    parent = composition_builder_222.build()
    builder = ScopeBuilder(parent, composition=parent_composition) if overlay else ContainerBuilder()
    builder.register(Service)
    with pytest.raises(TypeError, match="allow_scope_builders"):
        builder.build(allow_scope_builders=invalid)  # ty: ignore[unknown-argument]  # Deliberately invalid input.
    builder.register(str, instance="still reusable")
    builder.set_provider_roots(())
    with builder.build() as runtime:
        assert runtime.resolve(str) == "still reusable"
    parent.__exit__()


def test_impossible_binding_consumes_builder_and_fresh_composition_can_repair_it():
    class Missing:
        pass

    class Consumer:
        def __init__(self, missing: Missing):
            self.missing = missing

    def composition():
        builder = ContainerBuilder().set_provider_roots(())
        builder.register(Consumer)
        return builder

    builder = composition()
    with pytest.raises(ContainerBuildError):
        builder.build()
    with pytest.raises(BuilderAlreadyBuiltError):
        builder.register(Missing)
    builder = composition()
    builder.register(Missing)
    with builder.build() as container:
        assert isinstance(container.resolve(Consumer).missing, Missing)


def test_retained_composition_does_not_change_analysis_manifest_or_execution_catalogue():
    def compose(retain):
        builder = ContainerBuilder().set_provider_roots(())
        builder.register_fallback(Service, Service)
        builder.mark_entrypoint(Service)
        if retain:
            builder.retain_composition()
        return builder.analyse()

    with compose(True) as retained, compose(False) as automatic:
        assert retained.graph.manifest(all_roots=True).to_dict() == automatic.graph.manifest(all_roots=True).to_dict()
        assert retained.report.to_dict() == automatic.report.to_dict()
        assert [i.implementation_type for i in retained.selected_registrations] == [
            i.implementation_type for i in automatic.selected_registrations
        ]


@pytest.mark.asyncio
@pytest.mark.parametrize("diagnostics", [False, True])
@pytest.mark.parametrize("observed", [False, True])
async def test_compact_async_private_managed_acquisition_and_nested_cleanup(diagnostics, observed, monkeypatch):
    events = []

    async def resource() -> AsyncIterator[Resource]:
        value = Resource()
        try:
            yield value
        finally:
            value.closed = True
            events.append("closed")

    class AsyncRunner:
        def __init__(self, products: AsyncManagedProvider[Product]):
            self.products = products

    builder = ContainerBuilder()
    private = builder.create_boundary("async-private", exposes=[Expose(AsyncRunner)])
    private.register(Resource, factory=resource, lifespan="scoped")
    private.register(Product, lifespan="scoped")
    private.register(AsyncRunner, lifespan="singleton")
    instrumentation = Instrumentation(ResolutionProfiler()) if observed else None
    builder.set_provider_roots(())
    async with builder.build(instrumentation=instrumentation) as container:
        monkeypatch.setattr(ContainerBuilder, "build", lambda *a, **kw: pytest.fail("unexpected compilation"))
        monkeypatch.setattr(ScopeBuilder, "build", lambda *a, **kw: pytest.fail("unexpected compilation"))
        async with container.new_scope() as scope, scope.new_scope() as nested:
            runner = await nested.resolve_async(AsyncRunner)
            async with runner.products() as first:
                async with runner.products() as second:
                    assert first.resource is not second.resource
                    assert not first.resource.closed and not second.resource.closed
                assert second.resource.closed and not first.resource.closed
            assert first.resource.closed
            assert not hasattr(nested, "new_scope_builder")
    assert events == ["closed", "closed"]
