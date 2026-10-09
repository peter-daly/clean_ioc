"""Compact runtimes preserve frozen execution and discard overlay composition."""

import gc
import weakref
from collections.abc import AsyncIterator, Iterator

import pytest
from typing_extensions import TypeAliasType

from clean_ioc import (
    AsyncManagedProvider,
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


@pytest.mark.parametrize("diagnostics", [False, True])
def test_compact_drops_composition_filters_but_preserves_graph_and_catalogue(diagnostics):
    class Eligibility:
        def __call__(self, component):
            return True

    builder = ContainerBuilder()
    eligibility = Eligibility()
    reference = weakref.ref(eligibility)
    builder.register(Service, when=eligibility, candidate_when=eligibility)
    container = builder.build(allow_scope_builders=False, provider_roots=(), diagnostics=diagnostics)
    del builder, eligibility
    gc.collect()
    assert reference() is None
    assert container._plan._blueprint is None
    assert not container.allow_scope_builders
    with pytest.raises(RuntimeError, match="allow_scope_builders=False"):
        container.new_scope_builder()
    with pytest.raises(RuntimeError, match="allow_scope_builders=False"):
        ScopeBuilder(container)
    assert container.has_component(Service, cf.implementation_type_is(Service))
    assert container.selected_registrations[0].implementation_type is Service
    assert container.graph.manifest(all_roots=True).fingerprint
    assert container.graph.to_text(all_roots=True)
    assert container.graph.to_mermaid(all_roots=True)
    assert container.graph.ownership_report()
    assert container.validation_report().is_valid
    if diagnostics:
        assert container.graph.selection_census(all_roots=True)
    assert isinstance(container.resolve(Service), Service)


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
    with builder.build(
        allow_scope_builders=False,
        provider_roots=(),
        diagnostics=diagnostics,
        instrumentation=instrumentation,
        build_args={"mode": "compact"},
    ) as container:
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
                assert not nested.allow_scope_builders
                assert nested.selected_registrations is container.selected_registrations
    assert events == ["closed"]


@pytest.mark.parametrize("diagnostics", [False, True])
def test_compact_validation_only_rules_remain_live_build_rules_and_import_facts_detach(diagnostics):
    class Rule:
        def __init__(self):
            self.calls = 0

        def __call__(self, context):
            self.calls += 1
            assert context.graph.roots
            return ()

    build_rule = Rule()
    validation_rule = Rule()
    build_ref = weakref.ref(build_rule)
    validation_ref = weakref.ref(validation_rule)
    builder = ContainerBuilder()
    builder.register_subclasses(Service, ensure_import_modules="collections")
    builder.register(Service)
    builder.add_validation_rule(build_rule)
    builder.add_validation_rule(validation_rule, mode="validation")
    container = builder.build(allow_scope_builders=False, diagnostics=diagnostics, provider_roots=())
    assert build_rule.calls == 1
    del build_rule, validation_rule, builder
    gc.collect()
    assert build_ref() is None
    assert validation_ref() is not None
    assert container.ensured_import_modules == ("collections",)
    assert container.validation_report().is_valid
    assert container.validation_report().is_valid
    retained_rule = validation_ref()
    assert retained_rule is not None
    assert retained_rule.calls == 2


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
    with builder.build(provider_roots=()) as container:
        assert container.allow_scope_builders
        overlay = container.new_scope_builder()
        overlay.register(Local, factory=local_resource, lifespan="singleton")
        with overlay.build(allow_scope_builders=False, provider_roots=()) as child:
            assert child._plan._blueprint is None
            root = child.resolve(Resource)
            local = child.resolve(Local)
            with child.new_scope() as nested:
                assert nested.resolve(Resource) is root
                assert nested.resolve(Local) is local
                for scope in (child, nested):
                    with pytest.raises(RuntimeError, match="allow_scope_builders=False"):
                        scope.new_scope_builder()
                    with pytest.raises(RuntimeError, match="allow_scope_builders=False"):
                        ScopeBuilder(scope)
        assert events == ["local"]
        assert container.resolve(Resource) is root
        with container.new_scope_builder().build(provider_roots=()) as sibling:
            assert sibling.allow_scope_builders
            assert sibling.resolve(Resource) is root
    assert events == ["local", "root"]


@pytest.mark.parametrize("overlay", [False, True])
@pytest.mark.parametrize("invalid", [None, 0, 1, "false", ()])
def test_invalid_flag_rejected_before_discovery_or_builder_consumption(overlay, invalid):
    parent = ContainerBuilder().build(provider_roots=())
    builder = parent.new_scope_builder() if overlay else ContainerBuilder()
    builder.register(Service)
    with pytest.raises(TypeError, match="allow_scope_builders must be a bool"):
        builder.build(allow_scope_builders=invalid)
    builder.register(str, instance="still reusable")
    with builder.build(allow_scope_builders=False, provider_roots=()) as runtime:
        assert runtime.resolve(str) == "still reusable"
    parent.__exit__()


def test_compact_build_still_validates_and_failed_builder_is_reusable():
    class Missing:
        pass

    class Consumer:
        def __init__(self, missing: Missing):
            self.missing = missing

    builder = ContainerBuilder()
    builder.register(Consumer)
    with pytest.raises(ContainerBuildError):
        builder.build(allow_scope_builders=False, provider_roots=())
    builder.register(Missing)
    with builder.build(allow_scope_builders=False, provider_roots=()) as container:
        assert isinstance(container.resolve(Consumer).missing, Missing)


@pytest.mark.parametrize("diagnostics", [False, True])
def test_compact_and_compatible_keep_identical_execution_manifest(diagnostics):
    def compose(allow_scope_builders):
        builder = ContainerBuilder()
        builder.register_fallback(Service, Service)
        builder.mark_entrypoint(Service)
        return builder.build(allow_scope_builders=allow_scope_builders, diagnostics=diagnostics, provider_roots=())

    with compose(True) as compatible, compose(False) as compact:
        assert compact.graph.manifest(all_roots=True).to_dict() == compatible.graph.manifest(all_roots=True).to_dict()
        assert compact.build_report.to_dict() == compatible.build_report.to_dict()
        assert [i.implementation_type for i in compact.selected_registrations] == [
            i.implementation_type for i in compatible.selected_registrations
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
    async with builder.build(
        allow_scope_builders=False, provider_roots=(), diagnostics=diagnostics, instrumentation=instrumentation
    ) as container:
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
            assert not nested.allow_scope_builders
    assert events == ["closed", "closed"]
