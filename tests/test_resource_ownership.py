"""Acceptance coverage for compiled resource ownership proofs."""

import asyncio
import json
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager, contextmanager

import pytest

from clean_ioc import (
    ContainerBuilder,
    ContainerBuildError,
    GraphManifest,
    ResolutionContext,
    RuntimeOwnerKind,
    Scope,
    ScopeClosedError,
    all_components,
)
from clean_ioc.cli import main


def test_ownership_report_proves_each_lifespan_and_transient_promotion():
    class TransientResource:
        pass

    class GraphResource:
        pass

    class ScopedResource:
        pass

    class SingletonResource:
        pass

    class PromotedResource:
        pass

    class SingletonHost:
        def __init__(self, resource: PromotedResource):
            self.resource = resource

    def resource_factory(service_type):
        @contextmanager
        def factory():
            yield service_type()

        return factory

    builder = ContainerBuilder()
    for service_type, lifespan in (
        (TransientResource, "transient"),
        (GraphResource, "once_per_graph"),
        (ScopedResource, "scoped"),
        (SingletonResource, "singleton"),
    ):
        builder.register(service_type, factory=resource_factory(service_type), lifespan=lifespan)
    builder.register(PromotedResource, factory=resource_factory(PromotedResource), lifespan="transient")
    builder.register(SingletonHost, lifespan="singleton")
    container = builder.build()

    report = container.graph.ownership_report()
    assert report is container.graph.ownership_report()
    assert report.is_valid
    by_type = {record.component.service_type: record for record in report.records if record.component.parent is None}
    assert (by_type[TransientResource].cache_owner, by_type[TransientResource].cleanup_owner) == (
        RuntimeOwnerKind.none,
        RuntimeOwnerKind.scope,
    )
    assert (by_type[GraphResource].cache_owner, by_type[GraphResource].cleanup_owner) == (
        RuntimeOwnerKind.resolution,
        RuntimeOwnerKind.scope,
    )
    assert (by_type[ScopedResource].cache_owner, by_type[ScopedResource].cleanup_owner) == (
        RuntimeOwnerKind.scope,
        RuntimeOwnerKind.scope,
    )
    assert (by_type[SingletonResource].cache_owner, by_type[SingletonResource].cleanup_owner) == (
        RuntimeOwnerKind.singleton,
        RuntimeOwnerKind.singleton,
    )
    promoted = next(
        record
        for record in report.records
        if record.component.service_type is PromotedResource
        and record.component.parent is not None
        and record.component.parent.service_type is SingletonHost
    )
    assert promoted.cleanup_owner is RuntimeOwnerKind.singleton
    assert promoted.owner_component is not None
    assert promoted.owner_component.service_type is SingletonHost


def test_transient_cleanup_follows_inherited_root_singleton_owner_from_overlay_descendant():
    class Resource:
        pass

    class SingletonHost:
        def __init__(self, resource: Resource):
            self.resource = resource

    events: list[str] = []

    @contextmanager
    def resource_factory():
        events.append("enter")
        try:
            yield Resource()
        finally:
            events.append("exit")

    builder = ContainerBuilder()
    builder.register(Resource, factory=resource_factory, lifespan="transient")
    builder.register(SingletonHost, lifespan="singleton")
    container = builder.build()
    overlay_builder = container.new_scope_builder()

    class OverlayMarker:
        pass

    overlay_builder.register(OverlayMarker)
    overlay = overlay_builder.build()
    nested = overlay.new_scope()

    nested.resolve(SingletonHost)
    nested._close()
    overlay._close()
    assert events == ["enter"]
    container._close()
    assert events == ["enter", "exit"]


def test_transient_cleanup_follows_overlay_singleton_owner_from_nested_scope():
    class Resource:
        pass

    class OverlayHost:
        def __init__(self, resource: Resource):
            self.resource = resource

    events: list[str] = []

    @contextmanager
    def resource_factory():
        events.append("enter")
        try:
            yield Resource()
        finally:
            events.append("exit")

    root = ContainerBuilder().build()
    builder = root.new_scope_builder()
    builder.register(Resource, factory=resource_factory, lifespan="transient")
    builder.register(OverlayHost, lifespan="singleton")
    overlay = builder.build()
    nested = overlay.new_scope()

    nested.resolve(OverlayHost)
    nested._close()
    root._close()
    assert events == ["enter"]
    overlay._close()
    assert events == ["enter", "exit"]


def test_scoped_component_owns_transient_cleanup_at_scope_boundary():
    class Resource:
        pass

    class Repository:
        def __init__(self, resource: Resource):
            self.resource = resource

    events: list[str] = []

    @contextmanager
    def resource_factory():
        events.append("enter")
        try:
            yield Resource()
        finally:
            events.append("exit")

    builder = ContainerBuilder()
    builder.register(Resource, factory=resource_factory, lifespan="transient")
    builder.register(Repository, lifespan="scoped")
    container = builder.build()

    with container.new_scope() as scope:
        scope.resolve(Repository)
        assert events == ["enter"]
    assert events == ["enter", "exit"]


@pytest.mark.asyncio
async def test_async_transient_cleanup_is_promoted_to_singleton_owner():
    class Resource:
        pass

    class Host:
        def __init__(self, resource: Resource):
            self.resource = resource

    events: list[str] = []

    @asynccontextmanager
    async def resource_factory():
        events.append("enter")
        try:
            yield Resource()
        finally:
            events.append("exit")

    builder = ContainerBuilder()
    builder.register(Resource, factory=resource_factory, lifespan="transient")
    builder.register(Host, lifespan="singleton")
    container = builder.build()
    child = container.new_scope()
    await child.resolve_async(Host)
    await child._close_async()
    assert events == ["enter"]
    await container._close_async()
    assert events == ["enter", "exit"]


@pytest.mark.asyncio
async def test_concurrent_async_root_activation_uses_each_compiled_singleton_owner():
    class Service:
        pass

    events: list[str] = []

    def service_factory(label):
        @asynccontextmanager
        async def factory():
            events.append(f"enter:{label}")
            try:
                yield Service()
            finally:
                events.append(f"exit:{label}")

        return factory

    root_builder = ContainerBuilder()
    root_builder.register(Service, factory=service_factory("root"), lifespan="singleton", name="root")
    root = root_builder.build()
    overlay_builder = root.new_scope_builder()
    overlay_builder.register(Service, factory=service_factory("overlay"), lifespan="singleton", name="overlay")
    overlay = overlay_builder.build()
    child = overlay.new_scope()

    services = await child.resolve_async(list[Service], filter=all_components)
    assert len(services) == 2
    await child._close_async()
    await overlay._close_async()
    assert "exit:overlay" in events
    assert "exit:root" not in events
    await root._close_async()
    assert events[-1] == "exit:root"


@pytest.mark.parametrize(
    ("dependency", "lifespan", "code"),
    (
        (ResolutionContext, "scoped", "captive-resolution-context"),
        (ResolutionContext, "singleton", "captive-resolution-context"),
        (Scope, "singleton", "captive-runtime-scope"),
    ),
)
def test_runtime_context_capture_has_specific_diagnostic(dependency, lifespan, code):
    class Service:
        def __init__(self, runtime: dependency):
            self.runtime = runtime

    builder = ContainerBuilder()
    builder.register(Service, lifespan=lifespan)

    with pytest.raises(ContainerBuildError) as raised:
        builder.build()

    report = raised.value.report
    assert report is not None
    issue = report.errors[0]
    assert issue.code == code
    assert issue.path[0].endswith("Service")
    assert issue.path[-1].endswith(dependency.__name__)


@pytest.mark.parametrize("edge", ("transient", "decorator", "collection", "pre_configuration"))
def test_resolution_context_capture_is_transitively_validated_across_edges(edge):
    class ContextUser:
        def __init__(self, context: ResolutionContext):
            self.context = context

    class Service:
        pass

    builder = ContainerBuilder()
    if edge == "transient":

        class Host(Service):
            def __init__(self, user: ContextUser):
                self.user = user

        builder.register(ContextUser, lifespan="transient")
        builder.register(Service, Host, lifespan="singleton")
    elif edge == "decorator":

        class Decorator(Service):
            def __init__(self, child: Service, context: ResolutionContext):
                self.child = child
                self.context = context

        builder.register(Service, lifespan="scoped")
        builder.register_decorator(Service, Decorator, decorated_arg="child")
    elif edge == "collection":

        class Host(Service):
            def __init__(self, users: list[ContextUser]):
                self.users = users

        builder.register(ContextUser, lifespan="transient")
        builder.register(Service, Host, lifespan="singleton")
    else:

        def configure(context: ResolutionContext) -> None:
            del context

        builder.register(Service, lifespan="transient")
        builder.pre_configure(Service, configure)

    with pytest.raises(ContainerBuildError) as raised:
        builder.build()
    report = raised.value.report
    assert report is not None
    assert report.errors[0].code == "captive-resolution-context"


def test_runtime_contexts_remain_valid_for_short_lived_components():
    class Target:
        pass

    class GraphLocal:
        def __init__(self, context: ResolutionContext):
            self.context = context
            self.target = context.resolve(Target)

    class ScopedLocal:
        def __init__(self, scope: Scope):
            self.scope = scope

    builder = ContainerBuilder()
    builder.register(Target, lifespan="transient")
    builder.register(GraphLocal, lifespan="once_per_graph")
    builder.register(ScopedLocal, lifespan="scoped")
    container = builder.build()
    scope = container.new_scope()

    graph_local = scope.resolve(GraphLocal)
    assert isinstance(graph_local.target, Target)
    with pytest.raises(ScopeClosedError):
        graph_local.context.resolve(Target)
    assert scope.resolve(ScopedLocal).scope is scope


def test_cleanup_attempts_every_finalizer_and_aggregates_in_finalization_order():
    class First:
        pass

    class Second:
        pass

    events: list[str] = []

    def failing_factory(service_type, label):
        def factory():
            try:
                yield service_type()
            finally:
                events.append(label)
                raise ValueError(label)

        return factory

    builder = ContainerBuilder()
    builder.register(First, factory=failing_factory(First, "first"), lifespan="scoped")
    builder.register(Second, factory=failing_factory(Second, "second"), lifespan="scoped")
    scope = builder.build().new_scope()
    scope.resolve(First)
    scope.resolve(Second)

    with pytest.raises(ExceptionGroup) as raised:
        scope._close()
    assert events == ["second", "first"]
    assert [str(error) for error in raised.value.exceptions] == ["second", "first"]
    scope._close()


def test_one_cleanup_failure_is_reraised_unchanged():
    class Resource:
        pass

    failure = ValueError("same object")

    def resource_factory():
        try:
            yield Resource()
        finally:
            raise failure

    builder = ContainerBuilder()
    builder.register(Resource, factory=resource_factory, lifespan="scoped")
    scope = builder.build().new_scope()
    scope.resolve(Resource)

    with pytest.raises(ValueError) as raised:
        scope._close()
    assert raised.value is failure


@pytest.mark.asyncio
async def test_async_cleanup_attempts_every_finalizer_and_aggregates():
    class First:
        pass

    class Second:
        pass

    events: list[str] = []

    def failing_factory(service_type, label):
        @asynccontextmanager
        async def factory():
            try:
                yield service_type()
            finally:
                await asyncio.sleep(0)
                events.append(label)
                raise ValueError(label)

        return factory

    builder = ContainerBuilder()
    builder.register(First, factory=failing_factory(First, "first"), lifespan="scoped")
    builder.register(Second, factory=failing_factory(Second, "second"), lifespan="scoped")
    scope = builder.build().new_scope()
    await scope.resolve_async(First)
    await scope.resolve_async(Second)

    with pytest.raises(ExceptionGroup) as raised:
        await scope._close_async()
    assert events == ["second", "first"]
    assert [str(error) for error in raised.value.exceptions] == ["second", "first"]


@pytest.mark.asyncio
async def test_sync_close_reports_async_cleanup_and_continues_sync_cleanup():
    class SyncResource:
        pass

    class AsyncResource:
        pass

    events: list[str] = []

    @contextmanager
    def sync_factory():
        try:
            yield SyncResource()
        finally:
            events.append("sync")

    @asynccontextmanager
    async def async_factory():
        try:
            yield AsyncResource()
        finally:
            events.append("async")

    builder = ContainerBuilder()
    builder.register(SyncResource, factory=sync_factory, lifespan="scoped")
    builder.register(AsyncResource, factory=async_factory, lifespan="scoped")
    scope = builder.build().new_scope()
    scope.resolve(SyncResource)
    await scope.resolve_async(AsyncResource)

    with pytest.raises(RuntimeError, match="Async finalizer requires async context management"):
        scope._close()
    assert events == ["sync"]


def test_closed_scope_rejects_runtime_operations_and_saved_resolution_context():
    class Service:
        def __init__(self, context: ResolutionContext):
            self.context = context

    class Request:
        pass

    builder = ContainerBuilder()
    builder.declare_scope_slot(Request)
    builder.register(Service, lifespan="transient")
    scope = builder.build().new_scope().provide(Request, Request())
    context = scope.resolve(Service).context
    scope._close()

    operations = (
        lambda: scope.resolve(Service),
        lambda: asyncio.run(scope.resolve_async(Service)),
        lambda: scope.provide(Request, Request()),
        scope.new_scope,
        scope.new_scope_builder,
        lambda: context.resolve(Service),
        lambda: asyncio.run(context.resolve_async(Service)),
    )
    for operation in operations:
        with pytest.raises(ScopeClosedError):
            operation()
    scope._close()


def test_parent_close_does_not_close_an_independent_child_scope():
    class Service:
        pass

    container = ContainerBuilder()
    container.register(Service, lifespan="transient")
    parent = container.build()
    child = parent.new_scope()
    parent._close()

    assert isinstance(child.resolve(Service), Service)


def test_concurrent_singleton_activation_registers_one_promoted_finalizer():
    class Resource:
        pass

    class Host:
        def __init__(self, resource: Resource):
            self.resource = resource

    events: list[str] = []

    @contextmanager
    def resource_factory():
        events.append("enter")
        try:
            yield Resource()
        finally:
            events.append("exit")

    builder = ContainerBuilder()
    builder.register(Resource, factory=resource_factory, lifespan="transient")
    builder.register(Host, lifespan="singleton")
    container = builder.build()
    children = [container.new_scope() for _ in range(8)]
    with ThreadPoolExecutor(max_workers=8) as executor:
        values = list(executor.map(lambda scope: scope.resolve(Host), children))
    assert all(value is values[0] for value in values)
    assert events == ["enter"]
    container._close()
    assert events == ["enter", "exit"]


def test_manifest_v2_serializes_ownership_and_v1_is_readable_as_unknown():
    class Service:
        pass

    graph = ContainerBuilder()
    graph.register(Service, lifespan="singleton")
    container = graph.build()
    manifest = container.graph.manifest()
    equivalent = ContainerBuilder()
    equivalent.register(Service, lifespan="singleton")
    equivalent_container = equivalent.build()
    assert container.graph.ownership_report().to_json() == equivalent_container.graph.ownership_report().to_json()
    current = manifest.to_dict()
    assert current["schema_version"] == 3
    assert current["roots"][0]["cache_owner"] == "singleton"
    assert current["roots"][0]["cleanup_owner"] == "singleton"
    assert current["roots"][0]["owner_path"] is None

    def strip_ownership(node):
        for field in ("cache_owner", "cleanup_owner", "owner_path"):
            node.pop(field)
        for relationship in ("dependencies", "decorators", "pre_configurations"):
            for child in node[relationship]:
                strip_ownership(child)

    legacy = json.loads(json.dumps(current))
    legacy["schema_version"] = 1
    for root in legacy["roots"]:
        strip_ownership(root)
    baseline = GraphManifest.from_json(json.dumps(legacy))
    assert "cache_owner" not in baseline.data["roots"][0]
    difference = manifest.diff(baseline)
    assert [change.path for change in difference.changed] == [current["roots"][0]["path"]]


def test_reports_and_manifests_are_redacted_and_cli_renders_ownership(capsys):
    class Secret:
        pass

    class Service:
        def __init__(self, secret: Secret):
            self.secret = secret

    builder = ContainerBuilder()
    secret_id = builder.register(Secret, instance=Secret())
    service_id = builder.register(Service, arguments={"secret": "top-secret"})
    container = builder.build(build_args={"credential": "do-not-serialize"})

    rendered = container.graph.ownership_report().to_json()
    manifest = container.graph.manifest().to_json()
    for forbidden in (
        "top-secret",
        "credential",
        "do-not-serialize",
        "owner_token",
        "finalizer",
        secret_id,
        service_id,
    ):
        assert forbidden not in rendered
        assert forbidden not in manifest

    assert main(["ownership", "tests.tooling_targets:valid_builder", "--format", "json"]) == 0
    output = json.loads(capsys.readouterr().out)
    assert output["valid"] is True
    assert output["records"]
