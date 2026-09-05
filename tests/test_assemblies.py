from __future__ import annotations

from contextlib import asynccontextmanager, contextmanager
from dataclasses import dataclass
from typing import Generic, Protocol, TypeVar

import pytest

from clean_ioc import (
    Assembly,
    ContainerBuilder,
    ContainerBuildError,
    Expose,
    Provider,
    Tag,
    Use,
    ValidationContext,
    select,
)
from clean_ioc import component_filters as cf
from clean_ioc.bundles import BaseBundle, OnlyRunOncePerInstanceBundle


@dataclass(frozen=True)
class Settings:
    value: str


class Gateway(Protocol):
    pass


class Sdk:
    def __init__(self, settings: Settings):
        self.settings = settings


class StripeGateway(Gateway):
    def __init__(self, sdk: Sdk):
        self.sdk = sdk


class Repository:
    pass


class PlaceOrder:
    def __init__(self, repository: Repository, gateway: Gateway):
        self.repository = repository
        self.gateway = gateway


class FirstMarker:
    pass


class SecondMarker:
    pass


class FirstStructuralGateway(Gateway):
    def __init__(self, marker: FirstMarker):
        self.marker = marker


class SecondStructuralGateway(Gateway):
    def __init__(self, marker: SecondMarker):
        self.marker = marker


TItem = TypeVar("TItem")


class GenericDependency(Generic[TItem]):
    pass


class IntGenericDependency(GenericDependency[int]):
    pass


class GenericProduct(Generic[TItem]):
    def __init__(self, dependency: GenericDependency[TItem]):
        self.dependency = dependency


class GenericConsumer:
    def __init__(self, product: GenericProduct[int]):
        self.product = product


class DiscoveredService:
    pass


class DiscoveredImplementation(DiscoveredService):
    pass


def payments_bundle(builder):
    builder.register(Sdk, lifespan="singleton")
    builder.register(Gateway, StripeGateway, lifespan="singleton")


def orders_bundle(builder):
    builder.register(Repository, lifespan="scoped")
    builder.register(PlaceOrder, lifespan="scoped")
    builder.mark_entrypoint(PlaceOrder)


def application_builder() -> ContainerBuilder:
    builder = ContainerBuilder()
    builder.register(Settings, instance=Settings("secret"))
    builder.install_assembly(
        Assembly(
            "payments",
            payments_bundle,
            uses=(Use.root(Settings),),
            exposes=(Expose(Gateway),),
        )
    )
    builder.install_assembly(
        Assembly(
            "orders",
            orders_bundle,
            uses=(Use("payments", Gateway),),
            exposes=(Expose(PlaceOrder),),
        )
    )
    return builder


def issue_code(builder) -> str:
    with pytest.raises(ContainerBuildError) as captured:
        builder.build()
    assert captured.value.report is not None
    return captured.value.report.errors[0].code


def test_private_by_default_exposed_at_root_and_used_explicitly():
    container = application_builder().build()

    with container.new_scope() as scope:
        order = scope.resolve(PlaceOrder)
        assert isinstance(order.gateway, StripeGateway)
        assert order.gateway.sdk.settings.value == "secret"
        assert scope.resolve(Gateway) is order.gateway

    assert not container.has_component(Sdk)
    assert not container.has_component(Repository)
    assert container.has_component(Gateway)
    assert container.has_component(PlaceOrder)
    assert {root.component.assembly for root in container.graph.entrypoints} == {"orders"}


def test_exposure_and_use_preserve_named_tagged_singleton_identity():
    def payments(builder):
        builder.register(Sdk, instance=Sdk(Settings("x")))
        builder.register(
            Gateway,
            StripeGateway,
            lifespan="singleton",
            name="stripe",
            tags=(Tag("region", "global"),),
        )

    class Checkout:
        def __init__(self, gateway: Gateway):
            self.gateway = gateway

    def checkout(builder):
        builder.register(Checkout, arguments={"gateway": select(cf.with_name("stripe"))})

    builder = ContainerBuilder()
    builder.install_assembly(
        Assembly(
            "payments",
            payments,
            exposes=(Expose(Gateway, filter=cf.with_name("stripe")),),
        )
    )
    builder.install_assembly(
        Assembly(
            "checkout",
            checkout,
            uses=(Use("payments", Gateway, filter=cf.with_name("stripe")),),
            exposes=(Expose(Checkout),),
        )
    )
    container = builder.build()

    named = container.resolve(Gateway, filter=cf.with_name("stripe"))
    tagged = container.resolve(Gateway, filter=cf.has_tag("region", "global"))
    assert named is tagged is container.resolve(Checkout).gateway
    assert not container.has_component(Gateway)


def test_assembly_install_order_does_not_change_resolution_or_manifest():
    first = application_builder().build()
    second_builder = ContainerBuilder()
    second_builder.register(Settings, instance=Settings("secret"))
    second_builder.install_assembly(
        Assembly(
            "orders",
            orders_bundle,
            uses=(Use("payments", Gateway),),
            exposes=(Expose(PlaceOrder),),
        )
    )
    second_builder.install_assembly(
        Assembly(
            "payments",
            payments_bundle,
            uses=(Use.root(Settings),),
            exposes=(Expose(Gateway),),
        )
    )
    second = second_builder.build()

    assert isinstance(second.resolve(PlaceOrder).gateway, StripeGateway)
    assert first.graph.manifest(all_roots=True).to_json() == second.graph.manifest(all_roots=True).to_json()


def test_exposure_filters_inspect_the_original_compiled_component_subtree():
    def bundle(builder):
        builder.register(FirstMarker)
        builder.register(SecondMarker)
        builder.register(Gateway, FirstStructuralGateway)
        builder.register(Gateway, SecondStructuralGateway)

    builder = ContainerBuilder()
    builder.install_assembly(
        Assembly(
            "feature",
            bundle,
            exposes=(Expose(Gateway, filter=cf.has_descendant(cf.service_type_is(FirstMarker))),),
        )
    )
    assert isinstance(builder.build().resolve(Gateway), FirstStructuralGateway)


def test_missing_visibility_reports_private_source_and_boundary_decisions():
    builder = ContainerBuilder()
    builder.register(Settings, instance=Settings("x"))
    builder.install_assembly(Assembly("payments", payments_bundle, uses=(Use.root(Settings),)))
    builder.install_assembly(Assembly("orders", orders_bundle, exposes=(Expose(PlaceOrder),)))

    with pytest.raises(ContainerBuildError) as captured:
        builder.build()
    assert captured.value.report is not None
    assert {issue.code for issue in captured.value.report.errors} == {"assembly-private-component"}
    assert "payments" in captured.value.report.errors[0].message
    assert any(
        "rejected-not-exposed" in decision.reason_codes
        for explanation in captured.value.explanations
        for decision in explanation.rejected
    )


@pytest.mark.parametrize(
    ("assembly", "expected"),
    [
        (Assembly("root", lambda builder: None), "assembly-invalid-name"),
        (Assembly("Bad.Name", lambda builder: None), "assembly-invalid-name"),
    ],
)
def test_invalid_names_are_structured(assembly, expected):
    builder = ContainerBuilder()
    builder.install_assembly(assembly)
    assert issue_code(builder) == expected


def test_duplicate_names_missing_sources_and_cycles_are_structured():
    duplicate = ContainerBuilder()
    duplicate.install_assembly(Assembly("same", lambda builder: None))
    duplicate.install_assembly(Assembly("same", lambda builder: None))
    assert issue_code(duplicate) == "assembly-duplicate-name"

    missing = ContainerBuilder()
    missing.install_assembly(Assembly("consumer", lambda builder: None, uses=(Use("missing", Gateway),)))
    assert issue_code(missing) == "assembly-use-source-not-found"

    cycle = ContainerBuilder()
    cycle.install_assembly(Assembly("first", lambda builder: None, uses=(Use("second", Gateway),)))
    cycle.install_assembly(Assembly("second", lambda builder: None, uses=(Use("first", Gateway),)))
    with pytest.raises(ContainerBuildError) as captured:
        cycle.build()
    assert captured.value.report is not None
    assert captured.value.report.errors[0].code == "assembly-use-cycle"
    assert captured.value.report.errors[0].path == ("first", "second", "first")


def test_expose_and_use_cardinality_and_reexport_are_validated():
    missing_exposure = ContainerBuilder()
    missing_exposure.install_assembly(Assembly("empty", lambda builder: None, exposes=(Expose(Gateway),)))
    assert issue_code(missing_exposure) == "assembly-expose-not-found"

    ambiguous_exposure = ContainerBuilder()

    def duplicate_gateways(builder):
        builder.register(Gateway)
        builder.register(Gateway)

    ambiguous_exposure.install_assembly(
        Assembly(
            "payments",
            duplicate_gateways,
            exposes=(Expose(Gateway),),
        )
    )
    assert issue_code(ambiguous_exposure) == "assembly-expose-ambiguous"

    reexport = ContainerBuilder()
    reexport.register(Gateway)
    reexport.install_assembly(
        Assembly(
            "adapter",
            lambda builder: None,
            uses=(Use.root(Gateway),),
            exposes=(Expose(Gateway),),
        )
    )
    assert issue_code(reexport) == "assembly-reexport-unsupported"


def test_local_entrypoint_requires_local_exposure_and_cannot_mark_a_use():
    private = ContainerBuilder()

    def private_bundle(builder):
        builder.register(Repository)
        builder.mark_entrypoint(Repository)

    private.install_assembly(Assembly("orders", private_bundle))
    assert issue_code(private) == "assembly-entrypoint-not-exposed"

    imported = ContainerBuilder()
    imported.register(Settings, instance=Settings("x"))

    def imported_bundle(builder):
        builder.mark_entrypoint(Settings)

    imported.install_assembly(Assembly("orders", imported_bundle, uses=(Use.root(Settings),)))
    assert issue_code(imported) == "assembly-entrypoint-not-local"


def test_decorators_do_not_cross_boundaries_and_explicit_cross_attempt_is_rejected():
    class DecoratedGateway(Gateway):
        def __init__(self, decorated: Gateway):
            self.decorated = decorated

    def bundle(builder):
        builder.register(Gateway, instance=StripeGateway(Sdk(Settings("x"))))
        builder.register_decorator(Gateway, DecoratedGateway)

    local = ContainerBuilder()
    local.install_assembly(Assembly("payments", bundle, exposes=(Expose(Gateway),)))
    assert isinstance(local.build().resolve(Gateway), DecoratedGateway)

    cross = ContainerBuilder()

    def gateway_bundle(builder):
        builder.register(Gateway)

    cross.install_assembly(Assembly("payments", gateway_bundle, exposes=(Expose(Gateway),)))
    cross.register_decorator(Gateway, DecoratedGateway)
    assert issue_code(cross) == "assembly-cross-boundary-decoration"


def test_typed_provider_uses_the_defining_assembly_visibility():
    class Deferred:
        def __init__(self, gateway: Provider[Gateway]):
            self.gateway = gateway

    def bundle(builder):
        builder.register(Gateway, instance=StripeGateway(Sdk(Settings("x"))))
        builder.register(Deferred)

    builder = ContainerBuilder()
    builder.install_assembly(Assembly("feature", bundle, exposes=(Expose(Deferred),)))
    container = builder.build()
    assert container.resolve(Deferred).gateway() is container.resolve(Deferred).gateway()
    assert not container.has_component(Gateway)


def test_root_scope_slot_can_be_used_but_private_slots_are_rejected():
    class Request:
        pass

    class Handler:
        def __init__(self, request: Request):
            self.request = request

    Handler.__init__.__annotations__["request"] = Request

    def bundle(builder):
        builder.register(Handler)

    builder = ContainerBuilder()
    builder.declare_scope_slot(Request)
    builder.install_assembly(Assembly("feature", bundle, uses=(Use.root(Request),), exposes=(Expose(Handler),)))
    container = builder.build()
    request = Request()
    assert container.new_scope().provide(Request, request).resolve(Handler).request is request

    private = ContainerBuilder()
    private.install_assembly(Assembly("feature", lambda assembly_builder: assembly_builder.declare_scope_slot(Request)))
    assert issue_code(private) == "assembly-scope-slot-unsupported"


def test_overlay_can_add_an_assembly_use_parent_exposure_but_cannot_reopen_it():
    parent = application_builder().build()

    class Refund:
        def __init__(self, gateway: Gateway):
            self.gateway = gateway

    overlay_builder = parent.new_scope_builder()

    def refund_bundle(builder):
        builder.register(Refund)

    overlay_builder.install_assembly(
        Assembly(
            "refunds",
            refund_bundle,
            uses=(Use("payments", Gateway),),
            exposes=(Expose(Refund),),
        )
    )
    overlay = overlay_builder.build()
    assert overlay.resolve(Refund).gateway is parent.resolve(Gateway)

    reopened = parent.new_scope_builder()
    reopened.install_assembly(Assembly("payments", lambda builder: None))
    assert issue_code(reopened) == "overlay-assembly-reopened"


def test_manifest_provenance_rendering_and_semantic_diff_include_assemblies():
    container = application_builder().build()
    graph = container.graph
    manifest = graph.manifest(all_roots=True)

    assert manifest.data["schema_version"] == 3
    assert [item["name"] for item in manifest.data["assemblies"]] == ["orders", "payments"]
    assert any(node["assembly"] == "orders" for node in manifest.data["roots"])
    assert "assembly=orders" in graph.to_text(all_roots=True)
    assert "boundary:payments" in graph.to_mermaid(all_roots=True)
    order = next(root.component for root in graph.roots if root.component.service_type is PlaceOrder)
    explanation = graph.explain(order)
    assert explanation.selected[0].origin.assembly == "orders"
    assert "selected-use" in next(
        graph.explain(child).selected[0].reason_codes for child in order.dependencies if child.service_type is Gateway
    )

    without = ContainerBuilder().build().graph.manifest(all_roots=True)
    changes = manifest.diff(without).semantic_changes
    assert {change.category for change in changes} >= {"assembly-added"}


def test_root_and_local_validation_rules_receive_the_promised_graph_views():
    seen: list[tuple[str | None, set[str | None]]] = []

    def validate(context: ValidationContext):
        seen.append((context.assembly, {root.area for root in context.graph.roots}))
        return ()

    builder = application_builder()
    builder.add_validation_rule(validate)

    def local_bundle(assembly_builder):
        assembly_builder.register(Repository)
        assembly_builder.add_validation_rule(validate)

    builder.install_assembly(Assembly("reporting", local_bundle))
    builder.build()

    root_view = next(areas for assembly, areas in seen if assembly is None)
    local_view = next(areas for assembly, areas in seen if assembly == "reporting")
    assert root_view >= {None, "orders", "payments", "reporting"}
    assert local_view == {"reporting"}


def test_bundle_failure_is_transactional_and_bundle_cannot_install_nested_assembly():
    calls = 0

    def broken(builder):
        nonlocal calls
        calls += 1
        builder.register(Repository)
        raise RuntimeError("stop")

    builder = ContainerBuilder()
    with pytest.raises(RuntimeError, match="stop"):
        builder.install_assembly(Assembly("broken", broken))
    assert calls == 1
    assert builder.build().graph.assemblies == ()

    def nested(private_builder):
        assert not hasattr(private_builder, "install_assembly")

    nested_builder = ContainerBuilder()
    nested_builder.install_assembly(Assembly("outer", nested))
    nested_builder.build()


def test_base_nested_and_run_once_bundles_keep_their_normal_behavior():
    calls: list[str] = []

    class Inner(BaseBundle):
        def apply(self, builder):
            calls.append("inner")
            builder.register(Repository)

    class Once(OnlyRunOncePerInstanceBundle):
        def apply(self, builder):
            calls.append("once")
            builder.register(PlaceOrder, instance=PlaceOrder(Repository(), StripeGateway(Sdk(Settings("x")))))

    inner = Inner()
    once = Once()

    def outer(builder):
        builder.apply_bundle(inner)
        builder.apply_bundle(once)
        builder.apply_bundle(once)

    builder = ContainerBuilder()
    builder.install_assembly(Assembly("feature", outer, exposes=(Expose(Repository), Expose(PlaceOrder))))
    container = builder.build()
    assert isinstance(container.resolve(Repository), Repository)
    assert isinstance(container.resolve(PlaceOrder), PlaceOrder)
    assert calls == ["inner", "once"]


@pytest.mark.asyncio
async def test_sync_async_and_cleanup_factories_compile_inside_an_assembly():
    class SyncResource:
        pass

    class AsyncResource:
        pass

    class ContextResource:
        pass

    class AsyncContextResource:
        pass

    events: list[str] = []

    def sync_factory():
        return SyncResource()

    async def async_factory():
        return AsyncResource()

    @contextmanager
    def context_factory():
        events.append("context-enter")
        yield ContextResource()
        events.append("context-exit")

    @asynccontextmanager
    async def async_context_factory():
        events.append("async-enter")
        yield AsyncContextResource()
        events.append("async-exit")

    def bundle(builder):
        builder.register(SyncResource, factory=sync_factory)
        builder.register(AsyncResource, factory=async_factory)
        builder.register(ContextResource, factory=context_factory, lifespan="scoped")
        builder.register(AsyncContextResource, factory=async_context_factory, lifespan="scoped")

    builder = ContainerBuilder()
    builder.install_assembly(
        Assembly(
            "resources",
            bundle,
            exposes=(
                Expose(SyncResource),
                Expose(AsyncResource),
                Expose(ContextResource),
                Expose(AsyncContextResource),
            ),
        )
    )
    container = builder.build()
    async with container.new_scope() as scope:
        assert isinstance(scope.resolve(SyncResource), SyncResource)
        assert isinstance(await scope.resolve_async(AsyncResource), AsyncResource)
        assert isinstance(scope.resolve(ContextResource), ContextResource)
        assert isinstance(await scope.resolve_async(AsyncContextResource), AsyncContextResource)
    assert events == ["context-enter", "async-enter", "async-exit", "context-exit"]


def test_generics_discovery_and_preconfigurations_stay_local_to_an_assembly():
    configured: list[str] = []

    def create_product(dependency: GenericDependency[TItem]) -> GenericProduct[TItem]:
        return GenericProduct(dependency)

    def configure():
        configured.append("configured")

    def bundle(builder):
        builder.register(GenericDependency[int], IntGenericDependency)
        builder.register(GenericProduct, factory=create_product)
        builder.register(GenericConsumer)
        builder.register_subclasses(DiscoveredService)
        builder.pre_configure(GenericConsumer, configure)

    builder = ContainerBuilder()
    builder.install_assembly(
        Assembly(
            "generic_feature",
            bundle,
            exposes=(Expose(GenericConsumer), Expose(DiscoveredService)),
        )
    )
    container = builder.build()
    assert isinstance(container.resolve(GenericConsumer).product.dependency, IntGenericDependency)
    assert isinstance(container.resolve(DiscoveredService), DiscoveredImplementation)
    assert configured == ["configured"]
    assert not container.has_component(GenericDependency[int])
