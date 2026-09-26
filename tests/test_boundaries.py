from __future__ import annotations

from contextlib import asynccontextmanager, contextmanager
from dataclasses import dataclass
from typing import Any, Generic, Protocol, TypeVar, cast

import pytest

from clean_ioc import (
    AsyncProvider,
    BoundaryAlias,
    ContainerBuilder,
    ContainerBuildError,
    Expose,
    GraphManifest,
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


class PublicGateway(Protocol):
    pass


class AlternateGateway(Protocol):
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


class PublicGenericProduct(Generic[TItem]):
    pass


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
    builder.create_boundary("payments", uses=(Use.root(Settings),), exposes=(Expose(Gateway),)).apply_bundle(
        payments_bundle
    )
    builder.create_boundary("orders", uses=(Use("payments", Gateway),), exposes=(Expose(PlaceOrder),)).apply_bundle(
        orders_bundle
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
    assert {root.component.boundary for root in container.graph.entrypoints} == {"orders"}


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
    builder.create_boundary("payments", exposes=(Expose(Gateway, filter=cf.with_name("stripe")),)).apply_bundle(
        payments
    )
    builder.create_boundary(
        "checkout", uses=(Use("payments", Gateway, filter=cf.with_name("stripe")),), exposes=(Expose(Checkout),)
    ).apply_bundle(checkout)
    container = builder.build()

    named = container.resolve(Gateway, filter=cf.with_name("stripe"))
    tagged = container.resolve(Gateway, filter=cf.has_tag("region", "global"))
    assert named is tagged is container.resolve(Checkout).gateway
    assert not container.has_component(Gateway)


def test_exposure_alias_can_publish_a_complete_public_identity():
    source_policy_views = []

    def source_policy(component):
        source_policy_views.append((component.service_type, component.name, component.tags))
        return component.name == "stripe" and component.tags == (Tag("internal", "payments"),)

    def payments(builder):
        builder.register(Sdk, instance=Sdk(Settings("x")))
        builder.register(
            Gateway,
            StripeGateway,
            lifespan="singleton",
            name="stripe",
            tags=(Tag("internal", "payments"),),
            when=source_policy,
        )

    class Checkout:
        def __init__(self, gateway: PublicGateway):
            self.gateway = gateway

    def checkout(builder):
        builder.register(Checkout, arguments={"gateway": select(cf.has_tag("audience", "public"))})

    builder = ContainerBuilder()
    builder.create_boundary(
        "payments",
        exposes=(
            Expose(
                Gateway,
                filter=cf.with_name("stripe"),
                alias=BoundaryAlias(
                    PublicGateway,
                    name="primary",
                    tags=(Tag("audience", "public"),),
                ),
            ),
            Expose(
                Gateway,
                filter=cf.with_name("stripe"),
                alias=BoundaryAlias(AlternateGateway, name="backup"),
            ),
        ),
    ).apply_bundle(payments)
    builder.create_boundary(
        "checkout", uses=(Use("payments", PublicGateway, filter=cf.with_name("primary")),), exposes=(Expose(Checkout),)
    ).apply_bundle(checkout)
    container = builder.build()

    exposed = container.resolve(PublicGateway, filter=cf.with_name("primary"))
    alternate = container.resolve(AlternateGateway, filter=cf.with_name("backup"))
    assert exposed is alternate is container.resolve(Checkout).gateway
    assert source_policy_views
    assert {name for _, name, _ in source_policy_views} == {"stripe"}
    assert {tags for _, _, tags in source_policy_views} == {(Tag("internal", "payments"),)}
    assert not {PublicGateway, AlternateGateway}.intersection(service for service, _, _ in source_policy_views)
    assert not container.has_component(Gateway, filter=cf.with_name("stripe"))
    assert container.has_component(PublicGateway, filter=cf.has_tag("audience", "public"))
    assert not container.has_component(PublicGateway, filter=cf.has_tag("internal", "payments"))

    gateway_roots = [
        root
        for root in container.graph.roots
        if root.component.service_type in (Gateway, PublicGateway, AlternateGateway)
    ]
    assert {(root.area, root.component.service_type, root.component.name) for root in gateway_roots} == {
        (None, PublicGateway, "primary"),
        (None, AlternateGateway, "backup"),
        ("payments", Gateway, "stripe"),
    }
    assert len({root.component.id for root in gateway_roots}) == 1

    contracts = {item["name"]: item for item in container.graph.manifest(all_roots=True).data["boundaries"]}
    public = next(exposure for exposure in contracts["payments"]["exposures"] if exposure["name"] == "primary")
    assert public["service"].endswith(".PublicGateway")
    assert public["source_service"].endswith(".Gateway")
    assert public["source_name"] == "stripe"
    assert public["source_tags"] == [{"name": "internal", "value": "payments"}]
    assert contracts["checkout"]["uses"][0]["name"] == "primary"


def test_boundary_alias_can_publish_a_named_source_as_the_unnamed_default():
    class Internal:
        pass

    class Public:
        pass

    def source(builder):
        builder.register(Internal, name="private", tags=(Tag("side", "source"),))

    builder = ContainerBuilder()
    builder.create_boundary(
        "source",
        exposes=(
            Expose(
                Internal,
                filter=cf.with_name("private"),
                alias=BoundaryAlias(Public),
            ),
        ),
    ).apply_bundle(source)
    container = builder.build()

    assert isinstance(container.resolve(Public), Internal)
    assert container.has_component(Public)
    assert not container.has_component(Public, filter=cf.with_name("private"))
    public = next(root.component for root in container.graph.roots if root.component.service_type is Public)
    private = next(
        root.component
        for root in container.graph.roots
        if root.area == "source" and root.component.service_type is Internal
    )
    assert (public.name, public.tags) == (None, ())
    assert (private.name, private.tags) == ("private", (Tag("side", "source"),))


def test_duplicate_public_exposure_identity_is_rejected():
    def payments(builder):
        builder.register(Gateway, StripeGateway, name="stripe")

    alias = BoundaryAlias(PublicGateway, name="primary")
    builder = ContainerBuilder()
    builder.create_boundary(
        "payments",
        exposes=(
            Expose(Gateway, filter=cf.with_name("stripe"), alias=alias),
            Expose(Gateway, filter=cf.with_name("stripe"), alias=alias),
        ),
    ).apply_bundle(payments)
    assert issue_code(builder) == "boundary-expose-ambiguous"


@pytest.mark.parametrize(
    ("alias", "message"),
    [
        ("public", "Expose alias must be a BoundaryAlias or None"),
        (BoundaryAlias(PublicGateway, name=cast(Any, 1)), "BoundaryAlias name must be a string or None"),
        (
            BoundaryAlias(PublicGateway, tags=cast(Any, [Tag("public")])),
            "BoundaryAlias tags must be a tuple of Tag values",
        ),
        (
            BoundaryAlias(PublicGateway, tags=cast(Any, (object(),))),
            "BoundaryAlias tags must be a tuple of Tag values",
        ),
    ],
)
def test_boundary_alias_declaration_shapes_are_validated(alias, message):
    def source(builder):
        builder.register(Gateway, instance=StripeGateway(Sdk(Settings("x"))))

    builder = ContainerBuilder()
    builder.create_boundary("source", exposes=(Expose(Gateway, alias=alias),)).apply_bundle(source)
    with pytest.raises(TypeError, match=message):
        builder.build()


def test_alias_projects_only_after_the_complete_source_plan_is_compiled():
    class SourceDependency:
        pass

    class InternalService:
        def __init__(self, dependency: SourceDependency):
            self.dependency = dependency

    class PublicService:
        pass

    class SourceDecorator(InternalService):
        def __init__(self, decorated: InternalService):
            self.decorated = decorated

    InternalService.__init__.__annotations__["dependency"] = SourceDependency
    SourceDecorator.__init__.__annotations__["decorated"] = InternalService

    policy_views = []
    configured = []

    def source_policy(component):
        policy_views.append((component.service_type, component.name, component.tags))
        return component.service_type is InternalService

    def configure():
        configured.append("configured")

    def source(builder):
        builder.register(
            SourceDependency,
            lifespan="singleton",
            when=cf.parent(cf.service_type_is(InternalService)),
        )
        builder.register(
            InternalService,
            lifespan="singleton",
            name="internal",
            tags=(Tag("side", "source"),),
            when=source_policy,
        )
        builder.register_decorator(InternalService, SourceDecorator, when=source_policy)
        builder.pre_configure(InternalService, configure, when=source_policy)

    builder = ContainerBuilder()
    builder.create_boundary(
        "source",
        exposes=(
            Expose(
                InternalService,
                filter=cf.with_name("internal"),
                alias=BoundaryAlias(
                    PublicService,
                    name="public",
                    tags=(Tag("side", "public"),),
                ),
            ),
        ),
    ).apply_bundle(source)
    container = builder.build()

    resolved = container.resolve(PublicService, filter=cf.with_name("public"))
    assert isinstance(resolved, SourceDecorator)
    assert isinstance(resolved.decorated.dependency, SourceDependency)
    assert configured == ["configured"]
    assert policy_views
    assert {service_type for service_type, _, _ in policy_views} == {InternalService}
    assert {name for _, name, _ in policy_views} == {"internal"}
    assert {tags for _, _, tags in policy_views} == {(Tag("side", "source"),)}

    with container.new_scope_builder().build() as overlay:
        assert overlay.resolve(PublicService, filter=cf.with_name("public")) is resolved


@pytest.mark.asyncio
async def test_boundary_alias_preserves_async_resource_acquisition_and_cleanup():
    class InternalResource:
        pass

    class PublicResource:
        pass

    events: list[str] = []

    @asynccontextmanager
    async def create_resource():
        events.append("enter")
        yield InternalResource()
        events.append("exit")

    def source(builder):
        builder.register(InternalResource, factory=create_resource, lifespan="scoped")

    builder = ContainerBuilder()
    builder.create_boundary(
        "resources", exposes=(Expose(InternalResource, alias=BoundaryAlias(PublicResource)),)
    ).apply_bundle(source)
    container = builder.build()

    async with container.new_scope() as scope:
        resource = await scope.resolve_async(PublicResource)
        assert isinstance(resource, InternalResource)
        assert events == ["enter"]
    assert events == ["enter", "exit"]


@pytest.mark.asyncio
async def test_boundary_alias_supports_sync_and_async_typed_providers_at_root_and_through_use():
    class InternalSync:
        pass

    class PublicSync:
        pass

    class InternalAsync:
        pass

    class PublicAsync:
        pass

    async def create_async() -> InternalAsync:
        return InternalAsync()

    create_async.__annotations__["return"] = InternalAsync

    class Consumer:
        def __init__(self, sync: Provider[PublicSync], async_service: AsyncProvider[PublicAsync]):
            self.sync = sync
            self.async_service = async_service

    Consumer.__init__.__annotations__ = {
        "sync": Provider[PublicSync],
        "async_service": AsyncProvider[PublicAsync],
    }

    def source(builder):
        builder.register(InternalSync)
        builder.register(InternalAsync, factory=create_async)

    def consumer(builder):
        builder.register(Consumer)

    builder = ContainerBuilder()
    builder.create_boundary(
        "source",
        exposes=(
            Expose(InternalSync, alias=BoundaryAlias(PublicSync)),
            Expose(InternalAsync, alias=BoundaryAlias(PublicAsync)),
        ),
    ).apply_bundle(source)
    builder.create_boundary(
        "consumer", uses=(Use("source", PublicSync), Use("source", PublicAsync)), exposes=(Expose(Consumer),)
    ).apply_bundle(consumer)
    container = builder.build()

    resolved = container.resolve(Consumer)
    assert isinstance(resolved.sync(), InternalSync)
    assert isinstance(await resolved.async_service(), InternalAsync)
    assert isinstance(container.resolve(Provider[PublicSync])(), InternalSync)
    root_async_provider = container.resolve(AsyncProvider[PublicAsync])
    assert isinstance(await root_async_provider(), InternalAsync)
    assert not container.has_component(InternalSync)
    assert not container.has_component(InternalAsync)


def test_boundary_alias_duplicate_identity_canonicalizes_tag_order():
    class Internal:
        pass

    class Public:
        pass

    def source(builder):
        builder.register(Internal)

    manifest_builder = ContainerBuilder()
    manifest_builder.create_boundary(
        "source",
        exposes=(
            Expose(
                Internal,
                alias=BoundaryAlias(Public, tags=(Tag("same", ""), Tag("same"))),
            ),
        ),
    ).apply_bundle(source)
    exposure = manifest_builder.build().graph.manifest().data["boundaries"][0]["exposures"][0]
    assert exposure["tags"] == [
        {"name": "same", "value": None},
        {"name": "same", "value": ""},
    ]

    builder = ContainerBuilder()
    builder.create_boundary(
        "source",
        exposes=(
            Expose(
                Internal,
                alias=BoundaryAlias(Public, tags=(Tag("same"), Tag("same", ""))),
            ),
            Expose(
                Internal,
                alias=BoundaryAlias(Public, tags=(Tag("same", ""), Tag("same"))),
            ),
        ),
    ).apply_bundle(source)
    assert issue_code(builder) == "boundary-expose-ambiguous"


def test_boundary_install_order_does_not_change_resolution_or_manifest():
    first = application_builder().build()
    second_builder = ContainerBuilder()
    second_builder.register(Settings, instance=Settings("secret"))
    second_builder.create_boundary(
        "orders", uses=(Use("payments", Gateway),), exposes=(Expose(PlaceOrder),)
    ).apply_bundle(orders_bundle)
    second_builder.create_boundary("payments", uses=(Use.root(Settings),), exposes=(Expose(Gateway),)).apply_bundle(
        payments_bundle
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
    builder.create_boundary(
        "feature", exposes=(Expose(Gateway, filter=cf.has_descendant(cf.service_type_is(FirstMarker))),)
    ).apply_bundle(bundle)
    assert isinstance(builder.build().resolve(Gateway), FirstStructuralGateway)


def test_missing_visibility_reports_private_source_and_boundary_decisions():
    builder = ContainerBuilder()
    builder.register(Settings, instance=Settings("x"))
    builder.create_boundary("payments", uses=(Use.root(Settings),)).apply_bundle(payments_bundle)
    builder.create_boundary("orders", exposes=(Expose(PlaceOrder),)).apply_bundle(orders_bundle)

    with pytest.raises(ContainerBuildError) as captured:
        builder.build()
    assert captured.value.report is not None
    assert {issue.code for issue in captured.value.report.errors} == {"boundary-private-component"}
    assert "payments" in captured.value.report.errors[0].message
    assert any(
        "rejected-not-exposed" in decision.reason_codes
        for explanation in captured.value.explanations
        for decision in explanation.rejected
    )


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("root", "boundary-invalid-name"),
        ("Bad.Name", "boundary-invalid-name"),
    ],
)
def test_invalid_names_are_structured(name, expected):
    builder = ContainerBuilder()
    with pytest.raises(ContainerBuildError) as captured:
        builder.create_boundary(name)
    assert captured.value.code == expected
    assert builder.build().graph.boundaries == ()


def test_duplicate_names_missing_sources_and_cycles_are_structured():
    duplicate = ContainerBuilder()
    duplicate.create_boundary("same").apply_bundle(lambda builder: None)
    with pytest.raises(ContainerBuildError) as captured:
        duplicate.create_boundary("same")
    assert captured.value.code == "boundary-duplicate-name"

    missing = ContainerBuilder()
    missing.create_boundary("consumer", uses=(Use("missing", Gateway),)).apply_bundle(lambda builder: None)
    assert issue_code(missing) == "boundary-use-source-not-found"

    cycle = ContainerBuilder()
    cycle.create_boundary("first", uses=(Use("second", Gateway),)).apply_bundle(lambda builder: None)
    cycle.create_boundary("second", uses=(Use("first", Gateway),)).apply_bundle(lambda builder: None)
    with pytest.raises(ContainerBuildError) as captured:
        cycle.build()
    assert captured.value.report is not None
    assert captured.value.report.errors[0].code == "boundary-use-cycle"
    assert captured.value.report.errors[0].path == ("first", "second", "first")


def test_expose_and_use_cardinality_and_reexport_are_validated():
    missing_exposure = ContainerBuilder()
    missing_exposure.create_boundary("empty", exposes=(Expose(Gateway),)).apply_bundle(lambda builder: None)
    assert issue_code(missing_exposure) == "boundary-expose-not-found"

    ambiguous_exposure = ContainerBuilder()

    def duplicate_gateways(builder):
        builder.register(Gateway)
        builder.register(Gateway)

    ambiguous_exposure.create_boundary("payments", exposes=(Expose(Gateway),)).apply_bundle(duplicate_gateways)
    assert issue_code(ambiguous_exposure) == "boundary-expose-ambiguous"

    reexport = ContainerBuilder()
    reexport.register(Gateway)
    reexport.create_boundary("adapter", uses=(Use.root(Gateway),), exposes=(Expose(Gateway),)).apply_bundle(
        lambda builder: None
    )
    assert issue_code(reexport) == "boundary-reexport-unsupported"


def test_local_entrypoint_requires_local_exposure_and_cannot_mark_a_use():
    private = ContainerBuilder()

    def private_bundle(builder):
        builder.register(Repository)
        builder.mark_entrypoint(Repository)

    private.create_boundary("orders").apply_bundle(private_bundle)
    assert issue_code(private) == "boundary-entrypoint-not-exposed"

    imported = ContainerBuilder()
    imported.register(Settings, instance=Settings("x"))

    def imported_bundle(builder):
        builder.mark_entrypoint(Settings)

    imported.create_boundary("orders", uses=(Use.root(Settings),)).apply_bundle(imported_bundle)
    assert issue_code(imported) == "boundary-entrypoint-not-local"


def test_root_entrypoint_can_select_a_boundary_alias_by_its_public_identity():
    class Internal:
        pass

    class Public:
        pass

    def source(builder):
        builder.register(Internal, name="internal", tags=(Tag("side", "source"),))

    builder = ContainerBuilder()
    builder.create_boundary(
        "source",
        exposes=(
            Expose(
                Internal,
                filter=cf.with_name("internal"),
                alias=BoundaryAlias(Public, name="public", tags=(Tag("side", "public"),)),
            ),
        ),
    ).apply_bundle(source)
    builder.mark_entrypoint(Public, filter=cf.has_tag("side", "public"))
    container = builder.build()

    assert len(container.graph.entrypoints) == 1
    entrypoint = container.graph.entrypoints[0]
    assert entrypoint.requested_type is Public
    assert entrypoint.area is None
    assert entrypoint.component.service_type is Public
    assert entrypoint.component.name == "public"
    assert entrypoint.component.tags == (Tag("side", "public"),)
    assert entrypoint.component.boundary == "source"
    assert container.graph.manifest().data["roots"][0]["service"].endswith(".Public")


def test_decorators_do_not_cross_boundaries_and_explicit_cross_attempt_is_rejected():
    class DecoratedGateway(Gateway):
        def __init__(self, decorated: Gateway):
            self.decorated = decorated

    def bundle(builder):
        builder.register(Gateway, instance=StripeGateway(Sdk(Settings("x"))))
        builder.register_decorator(Gateway, DecoratedGateway)

    local = ContainerBuilder()
    local.create_boundary("payments", exposes=(Expose(Gateway),)).apply_bundle(bundle)
    assert isinstance(local.build().resolve(Gateway), DecoratedGateway)

    cross = ContainerBuilder()

    def gateway_bundle(builder):
        builder.register(Gateway)

    cross.create_boundary("payments", exposes=(Expose(Gateway),)).apply_bundle(gateway_bundle)
    cross.register_decorator(Gateway, DecoratedGateway)
    assert issue_code(cross) == "boundary-cross-boundary-decoration"


def test_typed_provider_uses_the_defining_boundary_visibility():
    class Deferred:
        def __init__(self, gateway: Provider[Gateway]):
            self.gateway = gateway

    def bundle(builder):
        builder.register(Gateway, instance=StripeGateway(Sdk(Settings("x"))))
        builder.register(Deferred)

    builder = ContainerBuilder()
    builder.create_boundary("feature", exposes=(Expose(Deferred),)).apply_bundle(bundle)
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
    builder.create_boundary("feature", uses=(Use.root(Request),), exposes=(Expose(Handler),)).apply_bundle(bundle)
    container = builder.build()
    request = Request()
    assert container.new_scope().provide(Request, request).resolve(Handler).request is request

    private = ContainerBuilder()
    private.create_boundary("feature").apply_bundle(
        lambda boundary_builder: boundary_builder.declare_scope_slot(Request)
    )
    assert issue_code(private) == "boundary-scope-slot-unsupported"


def test_overlay_can_add_a_boundary_use_parent_exposure_but_cannot_reopen_it():
    parent = application_builder().build()

    class Refund:
        def __init__(self, gateway: Gateway):
            self.gateway = gateway

    overlay_builder = parent.new_scope_builder()

    def refund_bundle(builder):
        builder.register(Refund)

    overlay_builder.create_boundary(
        "refunds", uses=(Use("payments", Gateway),), exposes=(Expose(Refund),)
    ).apply_bundle(refund_bundle)
    overlay = overlay_builder.build()
    assert overlay.resolve(Refund).gateway is parent.resolve(Gateway)

    reopened = parent.new_scope_builder()
    with pytest.raises(ContainerBuildError) as captured:
        reopened.create_boundary("payments")
    assert captured.value.code == "overlay-boundary-reopened"


def test_manifest_provenance_rendering_and_semantic_diff_include_boundaries():
    container = application_builder().build()
    graph = container.graph
    manifest = graph.manifest(all_roots=True)

    assert "schema_version" not in manifest.data
    assert [item["name"] for item in manifest.data["boundaries"]] == ["orders", "payments"]
    assert any(node["boundary"] == "orders" for node in manifest.data["roots"])
    assert "assemblies" not in manifest.data
    order_node = next(node for node in manifest.data["roots"] if node["service"].endswith(".PlaceOrder"))
    gateway_node = next(node for node in order_node["dependencies"] if node["argument"] == "gateway")
    assert gateway_node["boundary"] == "payments"
    assert gateway_node["source_boundary"] == "payments"
    assert "source_assembly" not in gateway_node
    assert "assembly" not in gateway_node
    restored = GraphManifest.from_json(manifest.to_json())
    assert restored.to_dict() == manifest.to_dict()
    assert restored.fingerprint == manifest.fingerprint
    assert restored.diff(manifest).is_empty
    assert "boundary=orders" in graph.to_text(all_roots=True)
    assert "boundary:payments" in graph.to_mermaid(all_roots=True)
    order = next(root.component for root in graph.roots if root.component.service_type is PlaceOrder)
    explanation = graph.explain(order)
    assert explanation.selected[0].origin.boundary == "orders"
    origin = explanation.selected[0].origin.to_dict()
    assert origin["boundary"] == "orders"
    assert "assembly" not in origin
    assert {root.boundary for root in graph.entrypoints} == {"orders"}
    assert {visit.boundary for visit in graph.walk()} == {None, "orders", "payments"}
    ownership = graph.ownership_report().to_dict()
    assert {record["boundary"] for record in ownership["records"]} == {None, "orders", "payments"}
    assert all("assembly" not in record for record in ownership["records"])
    assert "selected-use" in next(
        graph.explain(child).selected[0].reason_codes for child in order.dependencies if child.service_type is Gateway
    )

    without = ContainerBuilder().build().graph.manifest(all_roots=True)
    changes = manifest.diff(without).semantic_changes
    assert {change.category for change in changes} >= {"boundary-added"}
    assert {change.category for change in without.diff(manifest).semantic_changes} == {"boundary-removed"}


def test_semantic_diff_reports_removed_boundary_access_and_bypasses():
    baseline = application_builder().build().graph.manifest(all_roots=True)
    data = baseline.to_dict()
    orders = next(boundary for boundary in data["boundaries"] if boundary["name"] == "orders")
    orders["uses"] = []
    orders["exposures"] = []
    changed = GraphManifest(data)

    changes = changed.diff(baseline).semantic_changes
    assert {(change.category, change.risk) for change in changes} == {
        ("boundary-use-removed", "high"),
        ("boundary-exposure-removed", "high"),
        ("boundary-bypassed", "critical"),
    }
    assert {(change.category, change.risk) for change in baseline.diff(changed).semantic_changes} == {
        ("boundary-use-added", "high"),
        ("boundary-exposure-added", "medium"),
    }


@pytest.mark.parametrize(
    "changed_alias",
    [
        BoundaryAlias(AlternateGateway, name="primary", tags=(Tag("audience", "public"),)),
        BoundaryAlias(PublicGateway, name="preferred", tags=(Tag("audience", "public"),)),
        BoundaryAlias(PublicGateway, name="primary", tags=(Tag("audience", "partner"),)),
    ],
    ids=("service", "name", "tags"),
)
def test_semantic_diff_reports_boundary_alias_contract_changes(changed_alias):
    baseline_alias = BoundaryAlias(
        PublicGateway,
        name="primary",
        tags=(Tag("audience", "public"),),
    )

    def manifest(alias):
        def source(builder):
            builder.register(
                Gateway,
                instance=StripeGateway(Sdk(Settings("x"))),
                name="stripe",
                tags=(Tag("side", "source"),),
            )

        builder = ContainerBuilder()
        builder.create_boundary(
            "source", exposes=(Expose(Gateway, filter=cf.with_name("stripe"), alias=alias),)
        ).apply_bundle(source)
        return builder.build().graph.manifest(all_roots=True)

    baseline = manifest(baseline_alias)
    changed = manifest(changed_alias)
    exposure_changes = [
        change for change in changed.diff(baseline).semantic_changes if change.category.startswith("boundary-exposure-")
    ]

    assert {(change.category, change.risk) for change in exposure_changes} == {
        ("boundary-exposure-added", "medium"),
        ("boundary-exposure-removed", "high"),
    }
    assert all((change.before or change.after)["source_service"].endswith(".Gateway") for change in exposure_changes)


def test_semantic_diff_reports_a_component_moving_between_boundaries():
    def bundle(builder):
        builder.register(Repository)

    def manifest(name):
        builder = ContainerBuilder()
        builder.create_boundary(name, exposes=(Expose(Repository),)).apply_bundle(bundle)
        builder.mark_entrypoint(Repository)
        return builder.build().graph.manifest()

    changes = manifest("reporting").diff(manifest("orders")).semantic_changes
    moved = [change for change in changes if change.category == "boundary-component-moved"]
    assert len(moved) == 1
    assert moved[0].before == {"boundary": "orders"}
    assert moved[0].after == {"boundary": "reporting"}
    assert moved[0].risk == "high"


def test_root_and_local_validation_rules_receive_the_promised_graph_views():
    seen: list[tuple[str | None, set[str | None]]] = []

    def validate(context: ValidationContext):
        seen.append((context.boundary, {root.area for root in context.graph.roots}))
        return ()

    builder = application_builder()
    builder.add_validation_rule(validate)

    def local_bundle(boundary_builder):
        boundary_builder.register(Repository)
        boundary_builder.add_validation_rule(validate)

    builder.create_boundary("reporting").apply_bundle(local_bundle)
    builder.build()

    root_view = next(areas for boundary, areas in seen if boundary is None)
    local_view = next(areas for boundary, areas in seen if boundary == "reporting")
    assert root_view >= {None, "orders", "payments", "reporting"}
    assert local_view == {"reporting"}


def test_bundle_failure_keeps_partial_composition_and_nested_boundaries_are_rejected():
    calls = 0

    def broken(builder):
        nonlocal calls
        calls += 1
        builder.register(Repository)
        raise RuntimeError("stop")

    builder = ContainerBuilder()
    boundary = builder.create_boundary("broken")
    with pytest.raises(RuntimeError, match="stop"):
        boundary.apply_bundle(broken)
    assert calls == 1
    boundary.exposes = (Expose(Repository),)
    assert isinstance(builder.build().resolve(Repository), Repository)

    def nested(private_builder):
        with pytest.raises(ValueError, match="Nested boundaries"):
            private_builder.create_boundary("nested")
        assert not hasattr(private_builder, "build")

    nested_builder = ContainerBuilder()
    nested_builder.create_boundary("outer").apply_bundle(nested)
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
    builder.create_boundary("feature", exposes=(Expose(Repository), Expose(PlaceOrder))).apply_bundle(outer)
    container = builder.build()
    assert isinstance(container.resolve(Repository), Repository)
    assert isinstance(container.resolve(PlaceOrder), PlaceOrder)
    assert calls == ["inner", "once"]


@pytest.mark.asyncio
async def test_sync_async_and_cleanup_factories_compile_inside_a_boundary():
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
    builder.create_boundary(
        "resources",
        exposes=(
            Expose(SyncResource),
            Expose(AsyncResource),
            Expose(ContextResource),
            Expose(AsyncContextResource),
        ),
    ).apply_bundle(bundle)
    container = builder.build()
    async with container.new_scope() as scope:
        assert isinstance(scope.resolve(SyncResource), SyncResource)
        assert isinstance(await scope.resolve_async(AsyncResource), AsyncResource)
        assert isinstance(scope.resolve(ContextResource), ContextResource)
        assert isinstance(await scope.resolve_async(AsyncContextResource), AsyncContextResource)
    assert events == ["context-enter", "async-enter", "async-exit", "context-exit"]


def test_generics_discovery_and_preconfigurations_stay_local_to_a_boundary():
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
    builder.create_boundary(
        "generic_feature", exposes=(Expose(GenericConsumer), Expose(DiscoveredService))
    ).apply_bundle(bundle)
    container = builder.build()
    assert isinstance(container.resolve(GenericConsumer).product.dependency, IntGenericDependency)
    assert isinstance(container.resolve(DiscoveredService), DiscoveredImplementation)
    assert configured == ["configured"]
    assert not container.has_component(GenericDependency[int])


def test_open_generic_factory_alias_specializes_the_source_service():
    def create_product(dependency: GenericDependency[TItem]) -> GenericProduct[TItem]:
        return GenericProduct(dependency)

    class Consumer:
        def __init__(self, product: PublicGenericProduct[int]):
            self.product = product

    Consumer.__init__.__annotations__["product"] = PublicGenericProduct[int]

    def source(builder):
        builder.register(GenericDependency[int], IntGenericDependency)
        builder.register(GenericProduct, factory=create_product)

    def consumer(builder):
        builder.register(Consumer)

    builder = ContainerBuilder()
    builder.create_boundary(
        "generic_source",
        exposes=(
            Expose(
                GenericProduct[TItem],
                alias=BoundaryAlias(PublicGenericProduct[TItem]),
            ),
        ),
    ).apply_bundle(source)
    builder.create_boundary(
        "generic_consumer",
        uses=(
            Use(
                "generic_source",
                PublicGenericProduct[int],
                filter=cf.service_type_is(PublicGenericProduct[int]),
            ),
        ),
        exposes=(Expose(Consumer),),
    ).apply_bundle(consumer)
    container = builder.build()

    product = container.resolve(PublicGenericProduct[int])
    assert isinstance(product, GenericProduct)
    assert isinstance(product.dependency, IntGenericDependency)
    public_root = next(root for root in container.graph.roots if root.requested_type == PublicGenericProduct[int])
    assert public_root.component.service_type == PublicGenericProduct[int]
    assert container.resolve(Consumer).product is not product


def test_open_generic_alias_singleton_anchors_by_source_specialization_in_overlay():
    def create_product(dependency: GenericDependency[TItem]) -> GenericProduct[TItem]:
        return GenericProduct(dependency)

    class ParentConsumer:
        def __init__(self, product: PublicGenericProduct[int]):
            self.product = product

    class OverlayConsumer:
        def __init__(self, product: PublicGenericProduct[int]):
            self.product = product

    ParentConsumer.__init__.__annotations__["product"] = PublicGenericProduct[int]
    OverlayConsumer.__init__.__annotations__["product"] = PublicGenericProduct[int]

    def source(builder):
        builder.register(GenericDependency[int], IntGenericDependency, lifespan="singleton")
        builder.register(GenericProduct, factory=create_product, lifespan="singleton")

    def parent_bundle(private):
        private.register(ParentConsumer)

    builder = ContainerBuilder()
    builder.create_boundary(
        "generic_source",
        exposes=(
            Expose(
                GenericProduct[TItem],
                alias=BoundaryAlias(PublicGenericProduct[TItem]),
            ),
        ),
    ).apply_bundle(source)
    builder.create_boundary(
        "parent_consumer", uses=(Use("generic_source", PublicGenericProduct[int]),), exposes=(Expose(ParentConsumer),)
    ).apply_bundle(parent_bundle)
    parent = builder.build()
    parent_product = parent.resolve(ParentConsumer).product

    overlay_builder = parent.new_scope_builder()

    def overlay_bundle(private):
        private.register(OverlayConsumer)

    overlay_builder.create_boundary(
        "overlay_consumer", uses=(Use("generic_source", PublicGenericProduct[int]),), exposes=(Expose(OverlayConsumer),)
    ).apply_bundle(overlay_bundle)
    overlay = overlay_builder.build()
    assert overlay.resolve(OverlayConsumer).product is parent_product
    assert overlay.resolve(PublicGenericProduct[int]) is parent_product


def test_boundary_alias_rejects_unconstrained_public_generic_variable():
    def source(builder):
        builder.register(GenericProduct[int], instance=GenericProduct(IntGenericDependency()))

    builder = ContainerBuilder()
    builder.create_boundary(
        "generic_source",
        exposes=(
            Expose(
                GenericProduct[int],
                alias=BoundaryAlias(PublicGenericProduct[TItem]),
            ),
        ),
    ).apply_bundle(source)
    assert issue_code(builder) == "boundary-alias-incompatible"
