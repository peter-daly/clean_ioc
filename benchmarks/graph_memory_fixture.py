"""Large runtime-memory fixture with templates, deferred edges and keyed fanout.

No instance registrations. The parked artifact serializer is intentionally not
used: this fixture exercises the real compiler and its complete runtime plans.
"""

from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from clean_ioc import (
    AsyncManagedProvider,
    AsyncProvider,
    Container,
    ContainerBuilder,
    DecoratorTemplate,
    DerivedServices,
    ManagedProvider,
    Provider,
    ProviderMapGroup,
    RegistrationInfo,
    RegistrationTemplate,
    Scope,
    ServiceGroup,
    select,
)
from clean_ioc import component_filters as cf

ACTIVATIONS: Counter[str] = Counter()
TEMPLATE_CALLS: Counter[str] = Counter()
TREE_DEPTH = 5


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


class Leaf:
    __slots__ = ("payload",)

    def __init__(self):
        ACTIVATIONS["leaf"] += 1
        self.payload = bytearray(128)


def _branch_type(name: str, dependency: type) -> type:
    def init(self, left, right):
        ACTIVATIONS["branch"] += 1
        self.left, self.right = left, right

    init.__annotations__ = {"left": dependency, "right": dependency}
    return type(name, (), {"__module__": __name__, "__slots__": ("left", "right"), "__init__": init})


TREE_TYPES = [Leaf]
for _level in range(1, TREE_DEPTH + 1):
    _name = f"Branch{_level}"
    globals()[_name] = _branch_type(_name, TREE_TYPES[-1])
    TREE_TYPES.append(globals()[_name])


class RouteDependency:
    def __init__(self, owner_id: str):
        ACTIVATIONS["route_dependency"] += 1
        self.owner_id = owner_id


class RouteSource:
    def __init__(self, key: str, dependency: RouteDependency):
        ACTIVATIONS["route_source"] += 1
        self.key, self.dependency = key, dependency


class ScopedState:
    def __init__(self):
        ACTIVATIONS["state"] += 1


class Policy:
    def __init__(self, label: str):
        ACTIVATIONS["policy"] += 1
        self.label = label


class Worker:
    def __init__(self, source: RouteSource, state: ScopedState, tree: Any):
        ACTIVATIONS["worker"] += 1
        self.source, self.state, self.tree = source, state, tree


Worker.__init__.__annotations__["tree"] = TREE_TYPES[-1]


class WorkerDecorator(Worker):
    def __init__(self, inner: Worker, policy: Policy):
        ACTIVATIONS["worker_decorator"] += 1
        self.inner, self.policy = inner, policy


WORKERS = ServiceGroup("memory-workers", service_type=Worker)
WORKER_MAP = ProviderMapGroup("memory-worker-map", str, Worker)


class Endpoint:
    def __init__(
        self,
        key: str,
        source: RouteSource,
        worker: Provider[Worker],
        async_worker: AsyncProvider[Worker],
        managed_worker: ManagedProvider[Worker],
        async_managed_worker: AsyncManagedProvider[Worker],
        workers: Mapping[str, Provider[Worker]],
        sources: Mapping[str, AsyncProvider[RouteSource]],
    ):
        ACTIVATIONS["endpoint"] += 1
        self.key, self.source = key, source
        self.worker, self.async_worker = worker, async_worker
        self.managed_worker, self.async_managed_worker = managed_worker, async_managed_worker
        self.workers, self.sources = workers, sources


class EndpointDecorator(Endpoint):
    def __init__(self, inner: Endpoint, audit_worker: Provider[Worker]):
        ACTIVATIONS["endpoint_decorator"] += 1
        self.inner, self.audit_worker = inner, audit_worker


def dependency_for(source: RegistrationInfo) -> RegistrationTemplate:
    TEMPLATE_CALLS["source_to_generated_dependency"] += 1
    return RegistrationTemplate(
        RouteDependency,
        arguments={"owner_id": source.id},
        when=cf.parent(cf.with_id(source.id)),
        lifespan="transient",
        root_policy="dependency_only",
    )


def worker_for(source: RegistrationInfo) -> RegistrationTemplate:
    TEMPLATE_CALLS["generated_worker_to_source"] += 1
    return RegistrationTemplate(
        Worker,
        name=source.name,
        arguments={"source": select(cf.with_id(source.id))},
        lifespan="transient",
        groups=[WORKERS],
        contributes={WORKER_MAP: source.name},
    )


def worker_decorator_for(policy: RegistrationInfo) -> DecoratorTemplate:
    TEMPLATE_CALLS["policy_to_worker_decorator"] += 1
    return DecoratorTemplate(
        WORKERS,
        WorkerDecorator,
        arguments={"policy": select(cf.with_id(policy.id))},
        position=0 if policy.name == "metrics" else 1,
    )


def endpoint_decorator_for(worker: RegistrationInfo) -> DecoratorTemplate:
    # Generated registrations are also sources for decorator templates.
    TEMPLATE_CALLS["generated_worker_to_endpoint_decorator"] += 1
    return DecoratorTemplate(
        DerivedServices(Endpoint),
        EndpointDecorator,
        arguments={"audit_worker": select(cf.with_id(worker.id))},
        when=cf.with_name(worker.name),
    )


@dataclass
class Fixture:
    runtime: Container
    source_ids: dict[str, str]
    template_ids: dict[str, str]
    callbacks_after_build: dict[str, int]
    retained_builder: ContainerBuilder | None = None


def build(
    routes: int,
    *,
    diagnostics: bool = False,
    explain_metadata: bool = True,
    allow_scope_builders: bool = False,
    retain_builder: bool = False,
) -> Fixture:
    if not 1 <= routes <= 128:
        raise ValueError("routes must be between 1 and 128")
    ACTIVATIONS.clear()
    TEMPLATE_CALLS.clear()
    builder = ContainerBuilder()
    for tree_type in TREE_TYPES:
        builder.register(tree_type, lifespan="transient", root_policy="dependency_only")
    builder.register(ScopedState, lifespan="scoped", root_policy="dependency_only")
    for label in ("metrics", "tracing"):
        builder.register(Policy, name=label, arguments={"label": label}, lifespan="singleton")
    source_ids = {}
    for index in range(routes):
        key = f"route-{index:03d}"
        source_ids[key] = builder.register(RouteSource, name=key, arguments={"key": key}, lifespan="scoped")
        builder.register(
            Endpoint,
            name=key,
            lifespan="transient",
            arguments={
                "key": key,
                "source": select(cf.with_id(source_ids[key])),
                **{
                    name: select(cf.with_name(key))
                    for name in ("worker", "async_worker", "managed_worker", "async_managed_worker")
                },
            },
        )
    template_ids = {
        "dependency": builder.register_registration_template(for_each=RouteSource, template=dependency_for),
        "worker": builder.register_registration_template(for_each=RouteSource, template=worker_for),
        "worker_decorator": builder.register_decorator_template(for_each=Policy, template=worker_decorator_for),
        "endpoint_decorator": builder.register_decorator_template(for_each=Worker, template=endpoint_decorator_for),
    }
    builder.register_provider_map(WORKER_MAP, root_policy="dependency_only")
    builder.register_provider_map(
        RouteSource, key=lambda component: component.name, asynchronous=True, root_policy="dependency_only"
    )
    runtime = builder.build(
        diagnostics=diagnostics,
        explain_metadata=explain_metadata,
        provider_roots=(Provider[Worker], AsyncProvider[Worker], ManagedProvider[Worker], AsyncManagedProvider[Worker]),
        allow_scope_builders=allow_scope_builders,
        check_unreachable=False,
        aggregate_errors=False,
    )
    require(not ACTIVATIONS, "Compilation activated application constructors")
    require(
        dict(TEMPLATE_CALLS)
        == {
            "source_to_generated_dependency": routes,
            "generated_worker_to_source": routes,
            "policy_to_worker_decorator": 2,
            "generated_worker_to_endpoint_decorator": routes,
        },
        "Unexpected template expansion counts",
    )
    return Fixture(runtime, source_ids, template_ids, dict(TEMPLATE_CALLS), builder if retain_builder else None)


def unwrap_worker(value: Worker) -> tuple[Worker, list[Policy]]:
    policies = []
    while isinstance(value, WorkerDecorator):
        policies.append(value.policy)
        value = value.inner
    return value, policies


@dataclass
class Resolved:
    scope: Scope
    endpoints: list[EndpointDecorator]
    workers: list[tuple[str, str, Worker]]
    sources: list[tuple[str, RouteSource]]
    lazy_counts: dict[str, int]


async def resolve_workload(fixture: Fixture) -> Resolved:
    scope = fixture.runtime.new_scope()
    held = Resolved(scope, [], [], [], {})
    try:
        for key in fixture.source_ids:
            endpoint = scope.resolve(Endpoint, cf.with_name(key))
            if not isinstance(endpoint, EndpointDecorator):
                raise AssertionError("Endpoint decorator missing")
            held.endpoints.append(endpoint)
        held.lazy_counts = dict(ACTIVATIONS)
        require(ACTIVATIONS["worker"] == 0 and ACTIVATIONS["leaf"] == 0, "Providers eagerly constructed workers")
        for wrapped in held.endpoints:
            endpoint = wrapped.inner
            key = endpoint.key
            held.workers.extend((key, "ordinary", endpoint.worker()) for _ in range(2))
            held.workers.append((key, "ordinary", await endpoint.async_worker()))
            held.workers.append((key, "ordinary", wrapped.audit_worker()))
            for _ in range(2):
                with endpoint.managed_worker() as value:
                    held.workers.append((key, "managed", value))
            async with endpoint.async_managed_worker() as value:
                held.workers.append((key, "managed", value))
            held.workers.extend((target, "ordinary", provider()) for target, provider in endpoint.workers.items())
            for target, provider in endpoint.sources.items():
                held.sources.append((target, await provider()))
        key = next(iter(fixture.source_ids))
        held.workers.append((key, "ordinary", scope.resolve(Provider[Worker], cf.with_name(key))()))
        held.workers.append((key, "ordinary", await scope.resolve(AsyncProvider[Worker], cf.with_name(key))()))
        with scope.resolve(ManagedProvider[Worker], cf.with_name(key))() as value:
            held.workers.append((key, "managed", value))
        async with scope.resolve(AsyncManagedProvider[Worker], cf.with_name(key))() as value:
            held.workers.append((key, "managed", value))
        return held
    except BaseException:
        await scope.__aexit__(None, None, None)
        raise


def validate(fixture: Fixture, held: Resolved) -> dict[str, int]:
    expected_keys = set(fixture.source_ids)
    expected_workers = len(expected_keys) * (len(expected_keys) + 7) + 4
    require(len(held.workers) == expected_workers, "Wrong provider invocation count")
    require(TEMPLATE_CALLS == fixture.callbacks_after_build, "Runtime reran a template callback")
    endpoints = {wrapped.inner.key: wrapped.inner for wrapped in held.endpoints}
    for endpoint in endpoints.values():
        require(set(endpoint.workers) == expected_keys, "Worker map keys differ from generated registrations")
        require(set(endpoint.sources) == expected_keys, "Source map keys differ from source registrations")
    ordinary_states, managed_states, cores, trees = set(), set(), set(), set()
    policy_ids: dict[str, set[int]] = {"metrics": set(), "tracing": set()}
    leaf_count = 0
    for key, mode, decorated in held.workers:
        worker, policies = unwrap_worker(decorated)
        require([policy.label for policy in policies] == ["tracing", "metrics"], "Decorator order or binding changed")
        for policy in policies:
            policy_ids[policy.label].add(id(policy))
        require(id(worker) not in cores, "Transient workers unexpectedly share identity")
        cores.add(id(worker))
        require(worker.source.key == key, "Generated worker selected another route's source")
        require(
            worker.source.dependency.owner_id == fixture.source_ids[key], "Source selected another generated dependency"
        )
        if mode == "ordinary":
            require(worker.source is endpoints[key].source, "Scoped source identity changed")
            ordinary_states.add(id(worker.state))
        else:
            require(worker.source is not endpoints[key].source, "Managed acquisition reused the parent source")
            require(id(worker.state) not in managed_states, "Managed acquisitions shared a scope")
            managed_states.add(id(worker.state))
        pending = [worker.tree]
        while pending:
            node = pending.pop()
            require(id(node) not in trees, "Transient tree nodes unexpectedly share identity")
            trees.add(id(node))
            if isinstance(node, Leaf):
                require(len(node.payload) == 128 and not any(node.payload), "Incorrect leaf payload")
                leaf_count += 1
            else:
                pending.extend((node.left, node.right))
    for key, source in held.sources:
        require(source is endpoints[key].source, "Async source map lost scoped identity")
    require(len(ordinary_states) == 1 and ordinary_states.isdisjoint(managed_states), "Incorrect scope ownership")
    require(all(len(ids) == 1 for ids in policy_ids.values()), "Singleton policies were recreated")
    require(leaf_count == expected_workers * 2**TREE_DEPTH, "Incorrect tree size")
    require(ACTIVATIONS["worker"] == expected_workers, "Missing or hidden worker activations")
    require(ACTIVATIONS["worker_decorator"] == 2 * expected_workers, "Incorrect decorator count")
    return {
        "workers": len(cores),
        "tree_objects": len(trees),
        "leaves": leaf_count,
        "payload_bytes": leaf_count * 128,
        "ordinary_scopes": len(ordinary_states),
        "managed_scopes": len(managed_states),
        "source_map_calls": len(held.sources),
    }
