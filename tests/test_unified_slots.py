"""Unified inputs freeze binding selection independently of supplied instances."""

import pytest
from typing_extensions import TypeAliasType

from clean_ioc import (
    AsyncManagedProvider,
    AsyncProvider,
    ContainerBuilder,
    ContainerBuildError,
    Expose,
    ManagedProvider,
    Provider,
    ScopeBuilder,
    ScopeClosedError,
    ScopeProvisionError,
    Tag,
    UndeclaredScopeSlotError,
    Use,
    WarmupPlan,
    WarmupTarget,
)
from clean_ioc import component_filters as cf
from clean_ioc.arguments import select
from clean_ioc.components import all_components


class Value:
    pass


class Request:
    pass


class Worker:
    def __init__(self, value: Value, request: Request):
        self.value = value
        self.request = request


@pytest.fixture(params=["build", "verify"])
def compile_runtime(request):
    def compile_builder(builder):
        if request.param == "build":
            return builder.build()
        report = builder.verify()
        report.assert_valid()
        return report.create_runtime()

    return compile_builder


def test_both_lifetimes_are_available_in_normal_builds(compile_runtime):
    builder = ContainerBuilder()
    builder.declare_slot(Value, target="container")
    builder.declare_slot(Request, target="scoped")
    builder.register(Worker)
    container = compile_runtime(builder)
    value, request = Value(), Request()
    container.provide(Value, value)
    container.check_ready()
    assert container.has_slot(Value)
    assert not container.has_scope_slot(Value)
    parent = container.new_scope().provide(Request, request)
    assert parent.resolve(Worker).value is value
    assert parent.resolve(Worker).request is request
    assert parent.new_scope().resolve(Worker).request is request
    override = Request()
    child = parent.new_scope().provide(Request, override)
    assert child.resolve(Worker).request is override
    assert child.resolve(Worker).value is value
    with pytest.raises(ScopeProvisionError, match="owning container"):
        child.provide(Value, Value())
    with pytest.raises(ScopeProvisionError, match="locked"):
        container.provide(Value, Value())
    with pytest.raises(ScopeProvisionError, match="locked"):
        parent.provide(Request, Request())


def test_child_resolution_does_not_lock_root_scoped_provisions():
    builder = ContainerBuilder()
    builder.declare_slot(Request, target="scoped")
    builder.register(Value)
    container = builder.build()
    container.new_scope().resolve(Value)
    value = Request()
    container.provide(Request, value)
    assert container.new_scope().resolve(Request) is value


def test_readiness_aggregates_required_inputs_before_any_activation(compile_runtime):
    calls = []

    class Config:
        pass

    class Startup:
        def __init__(self, value: Value, config: Config):
            calls.append("activated")

    builder = ContainerBuilder()
    builder.declare_slot(Value, target="container", binding="external.client")
    builder.declare_slot(Config, target="container", binding="application.config")
    builder.declare_slot(Request, target="scoped")
    builder.register(Startup, lifespan="singleton")
    builder.add_warmup_plan(WarmupPlan("startup", [WarmupTarget(Startup)]))
    container = compile_runtime(builder)
    for operation in (
        container.check_ready,
        lambda: container.new_scope().resolve(Startup),
        lambda: container.warmup("startup"),
    ):
        with pytest.raises(ScopeProvisionError) as failure:
            operation()
        assert "external.client" in str(failure.value)
        assert "application.config" in str(failure.value)
        assert "Request" not in str(failure.value)
    assert not calls
    container.provide(Value, Value(), binding="external.client")
    container.provide(Config, Config(), binding="application.config")
    assert container.warmup("startup").is_valid
    assert calls == ["activated"]


def test_conditional_slots_select_distinct_stable_bindings_without_callback_replay(compile_runtime):
    class Payment:
        def __init__(self, client: Value):
            self.client = client

    class Refund:
        def __init__(self, client: Value):
            self.client = client

    calls = []

    def condition(parent_type):
        def matches(component):
            calls.append(component)
            return cf.parent(cf.service_type_is(parent_type))(component)

        return matches

    builder = ContainerBuilder()
    for consumer, binding in ((Payment, "payment.client"), (Refund, "refund.client")):
        builder.declare_slot(
            Value, target="container", name="primary", tags=[Tag("external")], binding=binding, when=condition(consumer)
        )
        builder.register(consumer, arguments={"client": select(cf.has_tag("external"))})
    container = compile_runtime(builder)
    frozen_calls = len(calls)
    with pytest.raises(ScopeProvisionError, match="specify binding"):
        container.provide(Value, Value(), name="primary")
    payment, refund = Value(), Value()
    container.provide(Value, payment, binding="payment.client")
    container.provide(Value, refund, binding="refund.client")
    assert container.resolve(Payment).client is payment
    assert container.new_scope().resolve(Refund).client is refund
    assert len(calls) == frozen_calls


@pytest.mark.parametrize("operation", ["build", "verify"])
def test_ambiguous_contextual_slots_fail_compilation_with_binding_origins(operation):
    class Consumer:
        def __init__(self, client: Value):
            pass

    builder = ContainerBuilder()
    for binding in ("one", "two"):
        builder.declare_slot(Value, target="container", binding=binding, when=cf.parent(cf.service_type_is(Consumer)))
    builder.register(Consumer)
    if operation == "build":
        with pytest.raises(ContainerBuildError) as failure:
            builder.build()
        assert failure.value.code == "ambiguous-slot"
        message = str(failure.value)
    else:
        report = builder.verify()
        assert not report.is_valid
        assert any(issue.code == "ambiguous-slot" for issue in report.issues)
        message = " ".join(issue.message for issue in report.issues)
    for text in ("Consumer", "client", "one", "two", "test_unified_slots.py"):
        assert text in message


def test_conditional_slot_requires_explicit_binding():
    with pytest.raises(ValueError, match="explicit binding"):
        ContainerBuilder().declare_slot(Value, target="scoped", when=all_components)


@pytest.mark.parametrize("scope", ["scoped", "container"])
def test_duplicate_implicit_identity_fails_even_with_different_tags(scope):
    builder = ContainerBuilder()
    builder.declare_slot(Value, target=scope, tags=[Tag("one")])
    builder.declare_slot(Value, target=scope, tags=[Tag("two")])
    with pytest.raises(ContainerBuildError, match="Duplicate implicit"):
        builder.build()


@pytest.mark.parametrize("other_type, other_scope", [(Request, "container"), (Value, "scoped")])
def test_binding_contract_rejects_incompatible_types_or_lifetimes(other_type, other_scope):
    builder = ContainerBuilder()
    builder.declare_slot(Value, target="container", binding="shared")
    builder.declare_slot(other_type, target=other_scope, binding="shared", name="other")
    with pytest.raises(ContainerBuildError, match="Incompatible slot binding"):
        builder.build()


def test_duplicate_unconditional_explicit_view_is_an_error():
    builder = ContainerBuilder()
    for _ in range(2):
        builder.declare_slot(Value, target="scoped", binding="shared", name="same")
    with pytest.raises(ContainerBuildError, match="Duplicate slot view"):
        builder.build()


def test_compatible_named_tagged_views_share_one_binding_and_collection_member(compile_runtime):
    class Values:
        def __init__(self, values: list[Value]):
            self.values = values

    builder = ContainerBuilder()
    builder.declare_slot(Value, target="container", binding="shared", name="one", tags=[Tag("view", "one")])
    builder.declare_slot(Value, target="container", binding="shared", name="two", tags=[Tag("view", "two")])
    builder.register(Values, arguments={"values": select(all_components)})
    container = compile_runtime(builder)
    value = Value()
    container.provide(Value, value, "two")
    assert container.resolve(Value, cf.with_name("one")) is value
    assert container.resolve(Value, cf.with_name("two")) is value
    assert container.resolve(Value, cf.has_tag("view", "two")) is value
    assert container.resolve(Values).values == [value]
    assert container.resolve(list[Value], all_components) == [value]
    assert container.has_provision(Value, binding="shared")
    with pytest.raises(ScopeProvisionError, match="already provided|locked"):
        container.provide(Value, Value(), binding="shared")


def test_registrations_keep_scalar_and_collection_precedence(compile_runtime):
    class Consumer:
        def __init__(self, value: Value, values: list[Value]):
            self.value, self.values = value, values

    builder = ContainerBuilder()
    builder.register(Value)
    builder.declare_slot(Value, target="scoped", tags=[Tag("external")])
    builder.register(Consumer)
    container = compile_runtime(builder)
    supplied = Value()
    container.provide(Value, supplied)
    consumer = container.resolve(Consumer)
    assert consumer.value is not supplied
    assert len(consumer.values) == 1 and consumer.values[0] is not supplied
    assert len(container.resolve(list[Value])) == 1
    assert container.resolve(Value, cf.has_tag("external")) is supplied


@pytest.mark.parametrize("provider_type", [Provider, AsyncProvider, ManagedProvider])
async def test_provider_slot_targets_are_frozen_in_the_wrapper_context(provider_type, compile_runtime):
    class Consumer:
        def __init__(self, value):
            self.value = value

    Consumer.__init__.__annotations__["value"] = provider_type[Value]
    builder = ContainerBuilder()
    builder.declare_slot(
        Value, target="container", binding="provider.value", when=cf.parent(cf.service_type_is(provider_type[Value]))
    )
    builder.register(Consumer, lifespan="singleton")
    container = compile_runtime(builder)
    with pytest.raises(ScopeProvisionError, match="provider.value"):
        container.resolve(Consumer)
    value = Value()
    container.provide(Value, value, binding="provider.value")
    provider = container.resolve(Consumer).value
    if provider_type is AsyncProvider:
        assert await provider() is value
    elif provider_type is ManagedProvider:
        with provider() as provided:
            assert provided is value
    else:
        assert provider() is value
    root = container.resolve(provider_type[Value])
    if provider_type is AsyncProvider:
        assert await root() is value
    elif provider_type is ManagedProvider:
        with root() as provided:
            assert provided is value
    else:
        assert root() is value


def test_collection_wrapper_is_the_real_slot_parent(compile_runtime):
    class Consumer:
        def __init__(self, values: list[Value]):
            self.values = values

    builder = ContainerBuilder()
    builder.declare_slot(
        Value, target="scoped", binding="collection.value", when=cf.parent(cf.service_type_is(list[Value]))
    )
    builder.register(Consumer)
    value = Value()
    container = compile_runtime(builder).provide(Value, value, binding="collection.value")
    assert container.resolve(Consumer).values == [value]
    assert container.resolve(Provider[list[Value]])() == [value]


def test_container_slots_are_valid_singleton_dependencies_but_scoped_slots_are_captive():
    class Singleton:
        def __init__(self, value: Value):
            self.value = value

    for scope in ("container", "scoped"):
        builder = ContainerBuilder()
        builder.declare_slot(Value, target=scope)
        builder.register(Singleton, lifespan="singleton")
        report = builder.verify()
        assert report.is_valid == (scope == "container")
        if scope == "scoped":
            assert any(issue.code == "captive-runtime-scope" for issue in report.issues)
        else:
            runtime = report.create_runtime()
            supplied = Value()
            runtime.provide(Value, supplied)
            assert runtime.new_scope().resolve(Singleton).value is supplied
            assert runtime.resolve(Singleton).value is supplied


def test_supplied_values_are_caller_owned_in_sync_and_async_cleanup(compile_runtime):
    class Resource:
        def __enter__(self):
            pytest.fail("provided objects must not be entered")

        def __exit__(self, *_):
            pytest.fail("provided objects must not be exited")

        def close(self):
            pytest.fail("provided objects must not be closed")

    builder = ContainerBuilder()
    builder.declare_slot(Resource, target="container")
    value = Resource()
    with compile_runtime(builder) as container:
        container.provide(Resource, value)
        assert container.resolve(Resource) is value
    with pytest.raises(ScopeClosedError):
        container.provide(Resource, value)


@pytest.mark.parametrize("activated", [False, True])
def test_overlays_inherit_container_inputs_and_add_scoped_inputs(activated, compile_runtime):
    builder = ContainerBuilder()
    builder.declare_slot(Value, target="container")
    composition = builder.retain_composition()
    container = compile_runtime(builder)
    value = Value()
    container.provide(Value, value)
    if activated:
        container.resolve(Value)
    overlay = ScopeBuilder(container, composition=composition)
    overlay.declare_slot(Request, target="scoped")
    overlay.register(Worker)
    scope = compile_runtime(overlay)
    request = Request()
    scope.provide(Request, request)
    assert scope.resolve(Worker).value is value
    assert scope.resolve(Worker).request is request
    with pytest.raises(UndeclaredScopeSlotError):
        container.provide(Request, request)
    with pytest.raises(ScopeProvisionError, match="owning container"):
        scope.provide(Value, Value())


@pytest.mark.parametrize("activated", [False, True])
def test_overlay_rejects_new_container_bindings_without_reopening_ancestor(activated):
    builder = ContainerBuilder()
    builder.register(Request)
    composition = builder.retain_composition()
    container = builder.build()
    if activated:
        container.resolve(Request)
    overlay = ScopeBuilder(container, composition=composition)
    overlay.declare_slot(Value, target="container")
    with pytest.raises(ContainerBuildError) as failure:
        overlay.build()
    assert failure.value.code == "overlay-container-slot-unsupported"


def test_aliases_normalize_slot_contract_and_provision_lookup(compile_runtime):
    alias = TypeAliasType("alias", Value)
    builder = ContainerBuilder()
    builder.declare_slot(alias, target="container", binding="alias")
    container = compile_runtime(builder)
    value = Value()
    container.provide(Value, value, binding="alias")
    assert container.resolve(alias) is value
    assert container.has_provision(alias, binding="alias")


def test_boundary_uses_import_unconditional_container_inputs(compile_runtime):
    class Consumer:
        def __init__(self, value: Value):
            self.value = value

    builder = ContainerBuilder()
    builder.declare_slot(Value, target="container", binding="boundary.input", tags=[Tag("external")])
    boundary = builder.create_boundary("feature", uses=[Use.root(Value, filter=cf.has_tag("external"))])
    boundary.register(Consumer)
    boundary.exposes = [Expose(Consumer)]
    container = compile_runtime(builder)
    value = Value()
    container.provide(Value, value, binding="boundary.input")
    assert container.resolve(Consumer).value is value


def test_boundary_conditional_import_fails_clearly():
    builder = ContainerBuilder()
    builder.declare_slot(Value, target="container", binding="contextual", when=all_components)
    builder.create_boundary("feature", uses=[Use.root(Value)])
    with pytest.raises(ContainerBuildError) as failure:
        builder.build()
    assert failure.value.code == "boundary-conditional-slot-unsupported"


def test_graph_inspection_preserves_binding_and_input_ownership_without_values():
    builder = ContainerBuilder()
    builder.declare_slot(Value, target="container", binding="application.value", tags=[Tag("external")])
    report = builder.verify()
    report.assert_valid()
    graph = report.graph
    assert graph is not None
    runtime = report.create_runtime()
    component = next(c for c in runtime.components if c.service_type is Value)
    assert component.slot_binding == "application.value"
    assert component.lifespan == "singleton"
    assert component.cache_owner.value == "supplied"
    assert component.cleanup_owner.value == "none"
    assert component.tags == (Tag("external"),)
    supplied = Value()
    runtime.provide(Value, supplied, binding="application.value")
    assert repr(supplied) not in graph.manifest().to_json()


@pytest.mark.parametrize("asynchronous", [False, True])
async def test_provider_maps_freeze_named_slot_targets_and_real_wrapper_parents(asynchronous, compile_runtime):
    from collections.abc import Mapping

    provider_type = AsyncProvider if asynchronous else Provider
    builder = ContainerBuilder()
    for name in ("first", "second"):
        builder.declare_slot(
            Value,
            target="container",
            name=name,
            binding=name,
            tags=[Tag("external")],
            when=cf.parent(cf.service_type_is(provider_type[Value])),
        )
    builder.register_provider_map(
        Value, key=lambda component: component.name, asynchronous=asynchronous, component_filter=cf.has_tag("external")
    )
    container = compile_runtime(builder)
    first, second = Value(), Value()
    container.provide(Value, first, binding="first")
    container.provide(Value, second, binding="second")
    values = container.resolve(Mapping[str, provider_type[Value]])
    assert list(values) == ["first", "second"]
    if asynchronous:
        assert await values["first"]() is first
        assert await values["second"]() is second
    else:
        assert values["first"]() is first
        assert values["second"]() is second


async def test_async_resolution_and_cleanup_preserve_caller_ownership(compile_runtime):
    class Resource:
        async def __aenter__(self):
            pytest.fail("provided object must not be entered")

        async def __aexit__(self, *_):
            pytest.fail("provided object must not be finalized")

    builder = ContainerBuilder()
    builder.declare_slot(Resource, target="container")
    value = Resource()
    async with compile_runtime(builder) as container:
        container.provide(Resource, value)
        async with container.new_scope() as scope:
            assert await scope.resolve_async(Resource) is value


def test_unused_contextual_bindings_remain_optional_until_a_new_overlay_context_needs_them():
    class OptionalConsumer:
        def __init__(self, value: Value):
            self.value = value

    builder = ContainerBuilder()
    composition = builder.retain_composition()
    builder.declare_slot(
        Value, target="container", binding="optional", when=cf.parent(cf.service_type_is(OptionalConsumer))
    )
    builder.register(Request)
    container = builder.build()
    container.check_ready()
    container.resolve(Request)
    overlay = ScopeBuilder(container, composition=composition)
    overlay.register(OptionalConsumer)
    with pytest.raises(ContainerBuildError) as failure:
        overlay.build()
    assert failure.value.code == "overlay-missing-container-slot"
    with pytest.raises(ScopeProvisionError, match="locked"):
        container.provide(Value, Value(), binding="optional")


def test_overlay_new_context_is_checked_for_compiled_slot_ambiguity():
    class Consumer:
        def __init__(self, value: Value):
            pass

    builder = ContainerBuilder()
    composition = builder.retain_composition()
    for binding in ("one", "two"):
        builder.declare_slot(Value, target="scoped", binding=binding, when=cf.parent(cf.service_type_is(Consumer)))
    container = builder.build()
    overlay = ScopeBuilder(container, composition=composition)
    overlay.register(Consumer)
    with pytest.raises(ContainerBuildError) as failure:
        overlay.build()
    assert failure.value.code == "ambiguous-slot"


def test_named_providers_retain_shared_binding_views_and_registration_collection_precedence(compile_runtime):
    builder = ContainerBuilder()
    builder.declare_slot(Value, target="scoped", binding="shared", name="first")
    builder.declare_slot(Value, target="scoped", binding="shared", name="second")
    container = compile_runtime(builder)
    value = Value()
    container.provide(Value, value, binding="shared")
    assert container.resolve(Provider[Value], cf.with_name("first"))() is value
    assert container.resolve(Provider[Value], cf.with_name("second"))() is value
    assert len(container.resolve(list[Provider[Value]], all_components)) == 1

    builder = ContainerBuilder()
    builder.register(Value)
    builder.declare_slot(Value, target="scoped", tags=[Tag("external")])
    container = compile_runtime(builder)
    container.provide(Value, value)
    providers = container.resolve(list[Provider[Value]], all_components)
    assert len(providers) == 1
    assert providers[0]() is not value


def test_decorator_and_preconfiguration_arguments_use_frozen_slot_bindings(compile_runtime):
    class Service:
        pass

    class Decorated(Service):
        def __init__(self, inner: Service, value: Value):
            self.inner, self.value = inner, value

    configured = []

    def configure(value: Value):
        configured.append(value)

    builder = ContainerBuilder()
    builder.declare_slot(Value, target="container", binding="external")
    builder.register(Service)
    builder.pre_configure(Service, configure)
    builder.register_decorator(Service, Decorated)
    container = compile_runtime(builder)
    value = Value()
    container.provide(Value, value, binding="external")
    assert container.resolve(Service).value is value
    assert configured == [value]


def test_declared_provider_surface_restricts_optional_container_input_requirements():
    builder = ContainerBuilder()
    builder.set_provider_roots([])
    builder.declare_slot(
        Value, target="container", binding="deferred.only", when=cf.parent(cf.service_type_is(Provider[Value]))
    )
    builder.register(Request)
    container = builder.build()
    container.check_ready()
    container.resolve(Request)


async def test_async_slot_predicates_are_rejected_without_retaining_coroutines():
    async def invalid(component):
        return True

    builder = ContainerBuilder()
    builder.declare_slot(Value, target="scoped", binding="async", when=invalid)  # ty: ignore[invalid-argument-type]
    with pytest.raises(ContainerBuildError) as failure:
        builder.build()
    assert failure.value.code == "invalid-slot-predicate"


def test_implicit_input_cannot_be_hidden_by_an_explicit_binding_with_the_same_provision_identity():
    builder = ContainerBuilder()
    builder.declare_slot(Value, target="scoped")
    builder.declare_slot(Value, target="scoped", binding="explicit", when=lambda _: False)
    with pytest.raises(ContainerBuildError) as failure:
        builder.build()
    assert failure.value.code == "slot-implicit-binding-conflict"


def test_container_input_can_be_a_direct_warmup_target(compile_runtime):
    builder = ContainerBuilder()
    builder.declare_slot(Value, target="container", binding="startup.value")
    builder.add_warmup_plan(WarmupPlan("startup", [WarmupTarget(Value)]))
    container = compile_runtime(builder)
    value = Value()
    container.provide(Value, value, binding="startup.value")
    assert container.warmup("startup").is_valid
    assert container.resolve(Value) is value


def test_observed_descendant_resolution_checks_readiness_and_seals_container_inputs():
    from clean_ioc import Instrumentation, ResolutionProfiler

    builder = ContainerBuilder()
    builder.declare_slot(Value, target="container", binding="observed")
    container = builder.build(instrumentation=Instrumentation(ResolutionProfiler()))
    child = container.new_scope()
    with pytest.raises(ScopeProvisionError, match="observed"):
        child.resolve(Value)
    value = Value()
    container.provide(Value, value, binding="observed")
    assert child.resolve(Value) is value
    with pytest.raises(ScopeProvisionError, match="locked"):
        container.provide(Value, Value(), binding="observed")


def test_implicit_identity_conflict_is_checked_against_later_shared_binding_views():
    builder = ContainerBuilder()
    builder.declare_slot(Value, target="scoped", binding="shared", name="first")
    builder.declare_slot(Value, target="scoped", binding="shared", name="second")
    builder.declare_slot(Value, target="scoped", name="second")
    with pytest.raises(ContainerBuildError) as failure:
        builder.build()
    assert failure.value.code == "slot-implicit-binding-conflict"
    assert failure.value.path
    assert "second" in str(failure.value)
    assert "test_unified_slots.py" in str(failure.value)


@pytest.mark.parametrize("operation", ["build", "verify"])
def test_observed_provider_views_preserve_registration_precedence_and_shared_input_dedup(operation):
    from clean_ioc import Instrumentation, ResolutionProfiler

    def compile_observed(builder):
        instrumentation = Instrumentation(ResolutionProfiler())
        if operation == "build":
            return builder.build(instrumentation=instrumentation)
        report = builder.verify()
        report.assert_valid()
        return report.create_runtime(instrumentation=instrumentation)

    builder = ContainerBuilder()
    builder.register(Value)
    builder.declare_slot(Value, target="scoped", binding="external")
    container = compile_observed(builder)
    value = Value()
    container.provide(Value, value, binding="external")
    providers = container.resolve(list[Provider[Value]], all_components)
    assert len(providers) == 1
    assert providers[0]() is not value

    builder = ContainerBuilder()
    builder.declare_slot(Value, target="scoped", binding="shared", name="first")
    builder.declare_slot(Value, target="scoped", binding="shared", name="second")
    container = compile_observed(builder)
    container.provide(Value, value, binding="shared")
    providers = container.resolve(list[Provider[Value]], all_components)
    assert len(providers) == 1
    assert providers[0]() is value


@pytest.mark.parametrize("conditional", [False, True])
def test_boundary_imports_keep_registration_precedence_over_slots(conditional, compile_runtime):
    class Consumer:
        def __init__(self, value: Value):
            self.value = value

    builder = ContainerBuilder()
    builder.register(Value)
    builder.declare_slot(Value, target="container", binding="external", when=all_components if conditional else None)
    boundary = builder.create_boundary("feature", uses=[Use.root(Value)], exposes=[Expose(Consumer)])
    boundary.register(Consumer)
    container = compile_runtime(builder)
    value = Value()
    container.provide(Value, value, binding="external")
    assert container.resolve(Consumer).value is not value


def test_private_architecture_roots_do_not_make_conservative_managed_adapters_required(compile_runtime):
    builder = ContainerBuilder()
    builder.set_provider_roots([])
    builder.declare_slot(
        Value, target="container", binding="optional", when=cf.parent(cf.service_type_is(AsyncManagedProvider[Value]))
    )
    boundary = builder.create_boundary("private")
    boundary.register(Request)
    container = compile_runtime(builder)
    container.check_ready()


async def test_reachable_managed_context_requires_its_frozen_internal_root_inputs(compile_runtime):
    from clean_ioc import AsyncManagedProvider, ResolutionContext

    async def create(context: ResolutionContext) -> object:
        return await context.resolve_async(Value)

    builder = ContainerBuilder()
    builder.set_provider_roots([AsyncManagedProvider[object]])
    builder.declare_slot(
        Value, target="container", binding="dynamic", when=cf.parent(cf.service_type_is(AsyncManagedProvider[Value]))
    )
    builder.register(object, factory=create)
    container = compile_runtime(builder)
    with pytest.raises(ScopeProvisionError, match="dynamic"):
        container.check_ready()
    value = Value()
    container.provide(Value, value, binding="dynamic")
    async with container.resolve(AsyncManagedProvider[object])() as supplied:
        assert supplied is value


def test_implicit_binding_cannot_mix_container_and_scoped_lifetimes():
    builder = ContainerBuilder()
    builder.declare_slot(Value, target="container")
    builder.declare_slot(Value, target="scoped")
    with pytest.raises(ContainerBuildError) as failure:
        builder.build()
    assert failure.value.code == "slot-binding-incompatible"


@pytest.mark.parametrize("deferred", [False, True])
def test_root_slot_ambiguity_errors_include_every_binding_origin(deferred):
    builder = ContainerBuilder()
    condition = cf.parent(cf.service_type_is(Provider[Value])) if deferred else None
    for binding in ("one", "two", "three"):
        builder.declare_slot(Value, target="scoped", binding=binding, when=condition)
    with pytest.raises(ContainerBuildError) as failure:
        builder.build()
    assert failure.value.code == "ambiguous-slot"
    message = str(failure.value)
    assert message.count("test_unified_slots.py") == 3
    assert all(binding in message for binding in ("one", "two", "three"))
    assert failure.value.path


@pytest.mark.parametrize("builder_type", ["protocol", "container", "scope", "boundary"])
def test_slot_builder_signatures_require_target_and_expose_no_legacy_alias(builder_type):
    import inspect

    from clean_ioc import BoundaryBuilder, ComponentBuilder

    classes = {
        "protocol": ComponentBuilder,
        "container": ContainerBuilder,
        "scope": ScopeBuilder,
        "boundary": BoundaryBuilder,
    }
    cls = classes[builder_type]
    signature = inspect.signature(cls.declare_slot)
    assert "scope" not in signature.parameters
    assert signature.parameters["target"].kind is inspect.Parameter.KEYWORD_ONLY
    assert signature.parameters["target"].default is inspect.Parameter.empty
    assert not hasattr(cls, "declare_scope_slot")


@pytest.mark.parametrize("builder_type", ["container", "scope", "boundary"])
def test_slot_declaration_rejects_missing_target_and_old_scope_keyword(builder_type):
    root = ContainerBuilder()
    if builder_type == "container":
        builder = root
    elif builder_type == "scope":
        composition = root.retain_composition()
        builder = ScopeBuilder(root.build(), composition=composition)
    else:
        builder = root.create_boundary("private")
    declare = getattr(builder, "declare_slot")
    with pytest.raises(TypeError, match="target"):
        declare(Value)
    with pytest.raises(TypeError, match="scope"):
        declare(Value, scope="scoped")
    with pytest.raises(TypeError, match="scope"):
        declare(Value, target="scoped", scope="scoped")
    with pytest.raises(ValueError, match="slot target"):
        declare(Value, target="invalid")
    with pytest.raises(AttributeError):
        getattr(builder, "declare_scope_slot")
    assert declare(Value, target="scoped") is builder


def test_redeclaring_an_inherited_implicit_slot_is_a_duplicate(compile_runtime):
    builder = ContainerBuilder()
    composition = builder.retain_composition()
    builder.declare_slot(Value, target="scoped")
    container = compile_runtime(builder)
    overlay = ScopeBuilder(container, composition=composition)
    overlay.declare_slot(Value, target="scoped")
    with pytest.raises(ContainerBuildError) as failure:
        overlay.build()
    assert failure.value.code == "duplicate-slot"
