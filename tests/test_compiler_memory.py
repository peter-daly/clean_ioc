import gc
import tracemalloc
from collections.abc import Mapping
from typing import Any, Generic, TypeVar, cast

import pytest

from clean_ioc import (
    AsyncManagedProvider,
    AsyncProvider,
    CompilationBudget,
    CompilationProfiler,
    ContainerBuilder,
    ContainerBuildError,
    Expose,
    ManagedProvider,
    Provider,
    ProviderMapGroup,
    Use,
    select,
)
from clean_ioc import component_filters as cf
from clean_ioc.container import _Compiler
from clean_ioc.tooling import CompiledGraph


class Leaf:
    pass


class Middle:
    def __init__(self, leaf: Leaf):
        self.leaf = leaf


class Root:
    def __init__(self, middle: Middle):
        self.middle = middle


def chain_builder():
    builder = ContainerBuilder()
    for service in (Leaf, Middle, Root):
        builder.register(service)
    return builder


@pytest.mark.parametrize("family", [Provider, AsyncProvider, ManagedProvider, AsyncManagedProvider])
@pytest.mark.parametrize("form", [None, list, tuple, set])
def test_automatic_provider_views_keep_target_parent_and_do_not_copy_records(family, form, monkeypatch):
    target = Root if form is None else tuple[Root, ...] if form is tuple else form[Root]
    annotation = family[target]
    builder = chain_builder()
    builder.mark_entrypoint(annotation)
    owner = builder.build(diagnostics=True)
    graph = owner._plan.graph
    records_before = len(graph._records)
    provider = owner._plan.provider_roots[annotation][0].component
    target_component = provider.dependencies[0]
    member = target_component if form is None else target_component.dependencies[0]
    assert member.parent.occurrence_id == (provider if form is None else target_component).occurrence_id
    assert member.dependencies[0].parent.occurrence_id == member.occurrence_id
    assert member.dependencies[0].dependencies[0].parent.occurrence_id == member.dependencies[0].occurrence_id
    assert member.implementation_type is Root
    calls = []
    original = CompiledGraph._component_paths

    def record(self, *, all_roots):
        calls.append(all_roots)
        return original(self, all_roots=all_roots)

    monkeypatch.setattr(CompiledGraph, "_component_paths", record)
    for _ in range(3):
        explanation = owner.graph.explain(member)
        assert explanation.selected
        assert explanation.path[0].startswith(f"root:{family.__module__}.{family.__qualname__}[")
        arguments = owner.graph.explain_arguments(member)
        assert "dependency:middle" in arguments[0].selected_components[0]
        assert owner.graph.explain(member.dependencies[0]).path[:-1] == explanation.path
    assert calls == [False, True]
    assert owner.graph.ownership_report().records
    assert owner.graph.manifest(all_roots=True).to_json()
    assert len(graph._records) == records_before == 90
    assert len(graph._views) == 48
    assert len(owner._plan.provider_roots) == 48
    owner.__exit__()


def test_runtime_provider_requests_cannot_reenter_compiler(monkeypatch):
    owner = chain_builder().build()

    def fail(*args, **kwargs):
        raise AssertionError("Runtime reentered the compiler")

    monkeypatch.setattr(_Compiler, "_compile_candidates", fail)
    assert isinstance(owner.resolve(Provider[Root])().middle.leaf, Leaf)
    assert len(owner.resolve(Provider[list[Root]])()) == 1
    with owner.resolve(ManagedProvider[Root])() as root:
        assert isinstance(root.middle.leaf, Leaf)
    owner.__exit__()


def test_physical_provider_growth_is_independent_of_target_subtree_size():
    def build(length):
        builder = ContainerBuilder()
        previous = Leaf
        builder.register(previous, root_policy="dependency_only")
        for index in range(length):

            def init(self, child):
                self.child = child

            init.__annotations__ = {"child": previous}
            service = type(f"Node{index}", (), {"__init__": init})
            builder.register(service, root_policy="resolvable" if index == length - 1 else "dependency_only")
            previous = service
        return builder.build()

    for length in (4, 8, 16, 32):
        with build(length) as owner:
            assert len(owner._plan.graph._records) == length + 1 + 28
            assert len(owner._plan.graph._views) == 16
            assert len(owner._plan.provider_roots) == 16


@pytest.mark.parametrize("name", [None, "internal"])
def test_dependency_only_provider_map_is_compiled_only_when_consumed(name):
    group = ProviderMapGroup("leaves", str, Leaf)
    annotation = Mapping[str, Provider[Leaf]]
    builder = ContainerBuilder()
    builder.register(Leaf, contributes={group: "leaf"}, root_policy="dependency_only")
    builder.register_provider_map(group, name=name, root_policy="dependency_only")
    with builder.build() as unused:
        assert not unused._plan.provider_roots
        assert not unused.graph.roots

    class Consumer:
        def __init__(self, entries: Mapping[str, Provider[Leaf]]):
            self.entries = entries

    builder = ContainerBuilder()
    builder.register(Leaf, contributes={group: "leaf"}, root_policy="dependency_only")
    builder.register_provider_map(group, name=name, root_policy="dependency_only")
    builder.register(Consumer, arguments={"entries": select(cf.with_name(name))})
    with builder.build() as used:
        assert isinstance(used.resolve(Consumer).entries["leaf"](), Leaf)
        assert annotation not in used._plan.provider_roots
        assert Provider[annotation] not in used._plan.provider_roots
        assert all(root.component.service_type != annotation for root in used.graph.roots)


def test_dependency_only_provider_map_still_validates_selected_contribution():
    class Missing:
        pass

    class Broken:
        def __init__(self, missing: Missing):
            pass

    class Consumer:
        def __init__(self, entries: Mapping[str, Provider[Broken]]):
            pass

    group = ProviderMapGroup("broken", str, Broken)
    builder = ContainerBuilder()
    builder.register(Broken, contributes={group: "broken"}, root_policy="dependency_only")
    builder.register_provider_map(group, root_policy="dependency_only")
    with builder.build() as unused:
        assert not unused.graph.roots
    builder = ContainerBuilder()
    builder.register(Broken, contributes={group: "broken"}, root_policy="dependency_only")
    builder.register_provider_map(group, root_policy="dependency_only")
    builder.register(Consumer)
    with pytest.raises(ContainerBuildError) as error:
        builder.build()
    assert "Missing" in str(error.value)
    assert "missing" in str(error.value)


def test_provider_map_root_policy_default_entrypoint_and_invalid():
    group = ProviderMapGroup("leaves", str, Leaf)
    builder = ContainerBuilder()
    builder.register(Leaf, contributes={group: "leaf"}, root_policy="dependency_only")
    builder.register_provider_map(group)
    with builder.build() as owner:
        assert isinstance(owner.resolve(Mapping[str, Provider[Leaf]])["leaf"](), Leaf)
    with pytest.raises(ValueError, match="root_policy"):
        ContainerBuilder().register_provider_map(group, root_policy=cast(Any, "invalid"))
    builder = ContainerBuilder()
    builder.register(Leaf, contributes={group: "leaf"}, root_policy="dependency_only")
    builder.register_provider_map(group, root_policy="entrypoint")
    with builder.build() as owner:
        assert owner.graph.entrypoints


def test_dependency_only_provider_maps_across_boundary_and_nested_overlay():
    group = ProviderMapGroup("leaves", str, Leaf)
    annotation = Mapping[str, Provider[Leaf]]

    class Consumer:
        def __init__(self, entries: Mapping[str, Provider[Leaf]]):
            self.entries = entries

    builder = ContainerBuilder()
    boundary = builder.create_boundary("entries", exposes=(Expose(annotation),))
    boundary.register(Leaf, contributes={group: "first"}, root_policy="dependency_only")
    boundary.register_provider_map(group, root_policy="dependency_only")
    consumer = builder.create_boundary("consumer", uses=(Use("entries", annotation),), exposes=(Expose(Consumer),))
    consumer.register(Consumer)
    with builder.build() as parent:
        assert list(parent.resolve(Consumer).entries) == ["first"]

    builder = ContainerBuilder()
    builder.register(Leaf, contributes={group: "first"}, root_policy="dependency_only")
    builder.register_provider_map(group, root_policy="dependency_only")
    builder.register(Consumer)
    with builder.build() as parent:
        overlay = parent.new_scope_builder()
        overlay.register(Leaf, name="second", contributes={group: "second"}, root_policy="dependency_only")
        with overlay.build() as child:
            assert list(child.resolve(Consumer).entries) == ["second", "first"]
            with child.new_scope_builder().build() as nested:
                assert list(nested.resolve(Consumer).entries) == ["second", "first"]


def transport_builder(count, *, early):
    class Transport:
        pass

    builder = ContainerBuilder()
    builder.register(Leaf, root_policy="dependency_only")
    builder.register(Middle, root_policy="dependency_only")
    routes = []
    for index in range(count):

        def sender_init(self, transport):
            self.transport = transport

        sender_init.__annotations__ = {"transport": Transport}
        sender = type(f"Sender{index}", (), {"__init__": sender_init})
        routes.append(sender)
        sender_id = builder.register(sender)

        def transport_init(self, middle):
            self.middle = middle

        transport_init.__annotations__ = {"middle": Middle}
        implementation = type(f"Transport{index}", (Transport,), {"__init__": transport_init})
        policy = cf.parent(cf.with_id(sender_id))
        builder.register(
            Transport,
            implementation,
            root_policy="dependency_only",
            **{
                "candidate_when" if early else "when": policy,
            },
        )
    return builder, routes


@pytest.mark.parametrize("count", [2, 4, 8, 16, 32])
@pytest.mark.parametrize("diagnostics", [False, True])
def test_many_sender_transport_eligibility_avoids_unrelated_subtree_compilation(count, diagnostics, monkeypatch):
    builder, routes = transport_builder(count, early=True)
    profile = CompilationProfiler(max_records=0)
    allocated = []
    original = _Compiler._draft

    def draft(self, **kwargs):
        result = original(self, **kwargs)
        allocated.append(result[0].occurrence_id)
        return result

    monkeypatch.setattr(_Compiler, "_draft", draft)
    with builder.build(profile=profile, diagnostics=diagnostics) as owner:
        records = len(owner._plan.graph._records or ())
        assert records == len(allocated)
        # Only the diagnostic mode physically retains the excluded cross-product.
        assert records == count * 32 + (count * (count - 1) if diagnostics else 0)
        assert [type(owner.resolve(route).transport).__name__ for route in routes] == [
            f"Transport{index}" for index in range(count)
        ]
    counters = profile.report().counters.to_dict()
    assert counters["candidate compilation attempts"] == count * 3 + 1
    assert counters["early excluded candidates"] == count * (count - 1)
    assert counters.get("retained early rejection records", 0) == (count * (count - 1) if diagnostics else 0)
    assert counters["physical component records"] == records
    assert counters["unique activation templates"] == count * 2 + 2
    assert counters.get("reused activation templates", 0) == 0
    assert counters["invariant subplan cache hits"] == count - 1
    assert counters["registration subplans compiled"] == count * 2 + 2
    assert counters["parameter processing attempts"] == count * 2 + 1
    assert profile.report().definition_counts
    assert profile.report().root_counts
    assert profile.report().registration_counts
    assert not profile.report().spans


def test_early_exclusion_saves_retained_and_peak_allocations_with_equal_runtime_graphs():
    def measure(diagnostics):
        builder, _ = transport_builder(32, early=True)
        gc.collect()
        tracemalloc.start()
        try:
            with builder.build(diagnostics=diagnostics) as owner:
                gc.collect()
                retained, peak = tracemalloc.get_traced_memory()
                tracemalloc.stop()
                return retained, peak, owner.graph.manifest(all_roots=True).fingerprint
        finally:
            tracemalloc.stop()

    # Reflection warmup is outside both measurements; builder composition is
    # also excluded. Physical allocation is independently bounded above.
    transport_builder(32, early=True)[0].build().__exit__()
    plain, rich = measure(False), measure(True)
    assert plain[2] == rich[2]
    assert rich[0] - plain[0] > 32 * 31 * 200
    assert rich[1] - plain[1] > 32 * 31 * 200


def test_occurrence_budget_counts_only_physically_allocated_early_rejections():
    builder, _ = transport_builder(4, early=True)
    profile = CompilationProfiler(max_records=0)
    with builder.build(budget=CompilationBudget(graph_occurrences=192), profile=profile) as owner:
        assert len(owner._plan.graph._records or ()) == 128
        assert len(owner._plan.graph._views) == 64
    usage = profile.report().budget_usage
    assert usage is not None
    assert dict(usage)["graph_occurrences"] == 192
    builder, _ = transport_builder(4, early=True)
    with pytest.raises(ContainerBuildError) as caught:
        builder.build(budget=CompilationBudget(graph_occurrences=192), diagnostics=True)
    assert caught.value.code == "compilation-budget-exceeded"


def test_legacy_when_preserves_full_subtree_validation_and_early_policy_is_opt_in():
    class Missing:
        pass

    class Broken:
        def __init__(self, missing: Missing):
            pass

    class Service:
        pass

    class Consumer:
        def __init__(self, service: Service):
            self.service = service

    for early in (False, True):
        builder = ContainerBuilder()
        builder.register(Consumer)
        builder.register(Service, root_policy="dependency_only")
        builder.register(
            Service,
            Broken,
            root_policy="dependency_only",
            **{
                "candidate_when" if early else "when": cf.with_name("excluded"),
            },
        )
        if early:
            with builder.build() as owner:
                assert isinstance(owner.resolve(Consumer).service, Service)
        else:
            with pytest.raises(ContainerBuildError) as error:
                builder.build()
            assert "Missing" in str(error.value)

        # Independently required public roots still receive full validation.
        required = ContainerBuilder()
        required.register(Broken, candidate_when=cf.with_name(None) if early else None)
        with pytest.raises(ContainerBuildError) as error:
            required.build()
        assert "Missing" in str(error.value)


@pytest.mark.parametrize("operator", ["and", "or", "not", "descendant"])
def test_early_unknown_expressions_keep_callbacks_and_short_circuit_order(operator):
    calls = []

    def callback(component):
        calls.append(tuple(child.service_type for child in component.dependencies))
        return True

    builder = chain_builder()
    if operator == "and":
        policy = cf.create_filter(callback) & cf.with_name("excluded")
    elif operator == "or":
        policy = cf.create_filter(callback) | cf.with_name(None)
    elif operator == "not":
        policy = ~cf.create_filter(callback)
    else:
        policy = cf.has_descendant(cf.create_filter(callback))
    builder.register(Root, name="extra", candidate_when=policy)
    with builder.build():
        assert calls == [(Middle,)] if operator != "descendant" else [(Leaf,)]


def test_known_false_and_unknown_excludes_without_running_callback():
    def fail(component):
        raise AssertionError("Short-circuited callback ran")

    builder = chain_builder()
    builder.register(Root, name="extra", candidate_when=cf.with_name("different") & cf.create_filter(fail))
    with builder.build(diagnostics=True) as owner:
        explanation = owner.graph.explain(Root)
        assert any("rejected-candidate-when" in item.reason_codes for item in explanation.rejected)


@pytest.mark.parametrize("lifespan", ["transient", "per_resolution", "scoped", "singleton"])
def test_shared_activation_templates_preserve_runtime_lifespan_identity(lifespan):
    class Pair:
        def __init__(self, left: Leaf, right: Leaf):
            self.left, self.right = left, right

    builder = ContainerBuilder()
    builder.register(Leaf, lifespan=lifespan, root_policy="dependency_only")
    builder.register(Pair)
    with builder.build() as parent:
        first, second = parent.resolve(Pair), parent.resolve(Pair)
        assert (first.left is first.right) is (lifespan != "transient")
        assert (first.left is second.left) is (lifespan in ("scoped", "singleton"))
        with parent.new_scope_builder().build() as child:
            third = child.resolve(Pair)
            assert (first.left is third.left) is (lifespan == "singleton")


def test_closed_generic_templates_keep_separate_bindings_and_provider_explanations():
    T = TypeVar("T")

    class Value(Generic[T]):
        pass

    class Consumer(Generic[T]):
        def __init__(self, value: Value[T]):
            self.value = value

    builder = ContainerBuilder()
    builder.register(Value)
    builder.register(Consumer[int])
    builder.register(Consumer[str])
    builder.mark_entrypoint(Provider[Consumer[int]])
    with builder.build(diagnostics=True) as owner:
        assert owner._plan.roots[Consumer[int]][0].step is not owner._plan.roots[Consumer[str]][0].step
        component = owner._plan.provider_roots[Provider[Consumer[int]]][0].component.dependencies[0]
        assert component.generic_mapping[T] is int
        assert component.dependencies[0].generic_mapping[T] is int
        assert owner.graph.explain_specialization(component).to_dict()
        source = owner._plan.roots[Consumer[int]][0].component
        assert dict(component.generic_mapping.items()) == dict(source.generic_mapping.items())
        with pytest.raises(ValueError, match="Cannot set"):
            component.generic_mapping[T] = str
        assert source.generic_mapping[T] is int


def test_view_contexts_count_as_physical_budget_work_and_full_depth_is_checked():
    profile = CompilationProfiler(max_records=0)
    with chain_builder().build(budget=CompilationBudget(graph_occurrences=138), profile=profile):
        pass
    counters = profile.report().counters.to_dict()
    assert counters["physical component records"] == 90
    assert counters["provider target views"] == 48
    assert dict(profile.report().budget_usage or ())["graph_occurrences"] == 138
    assert dict(profile.report().budget_usage or ())["active_dependency_depth"] == 5
    with pytest.raises(ContainerBuildError):
        chain_builder().build(budget=CompilationBudget(graph_occurrences=137))
    with pytest.raises(ContainerBuildError):
        chain_builder().build(budget=CompilationBudget(active_dependency_depth=4))


@pytest.mark.asyncio
async def test_shared_managed_adapter_memo_keeps_each_collection_form():
    builder = ContainerBuilder()
    services = [type(f"Service{index}", (), {}) for index in range(24)]
    for service in services:
        builder.register(service)
    with builder.build() as owner:
        for service in services:
            for form in (list, tuple, set):
                target: Any = tuple[service, ...] if form is tuple else form[service]
                with owner.resolve(ManagedProvider[target])() as values:
                    assert type(values) is form
                    assert len(values) == 1
                    assert type(next(iter(values))) is service
                async with owner.resolve(AsyncManagedProvider[target])() as values:
                    assert type(values) is form
                    assert len(values) == 1
                    assert type(next(iter(values))) is service


def test_early_parent_eligibility_hides_external_boundary_consumer():
    class Service:
        pass

    class Consumer:
        def __init__(self, service: Service):
            pass

    builder = ContainerBuilder()
    consumer_id = builder.register(Consumer)
    boundary = builder.create_boundary("service", exposes=(Expose(Service),))
    boundary.register(Service, candidate_when=cf.parent(cf.with_id(consumer_id)), root_policy="dependency_only")
    with pytest.raises(ContainerBuildError) as error:
        builder.build(diagnostics=True)
    assert "Service" in str(error.value)
    assert any(
        "rejected-candidate-when" in decision.reason_codes
        for explanation in error.value.explanations
        for decision in explanation.rejected
    )


def test_all_applicable_operation_executors_remain_in_the_collection():
    activated = []

    class Executor:
        pass

    class First(Executor):
        def __init__(self):
            activated.append("first")

    class Second(Executor):
        def __init__(self):
            activated.append("second")

    class Operation:
        def __init__(self, executors: list[Executor]):
            self.executors = executors

    builder = ContainerBuilder()
    operation_id = builder.register(Operation)
    for implementation in (First, Second):
        builder.register(
            Executor,
            implementation,
            candidate_when=cf.parent(cf.parent(cf.with_id(operation_id))),
            root_policy="dependency_only",
        )
    with builder.build() as owner:
        assert not activated
        operation = owner.resolve(Operation)
        assert {type(executor) for executor in operation.executors} == {First, Second}
        assert set(activated) == {"first", "second"}


def test_reusing_activation_templates_does_not_skip_opaque_when_callbacks():
    calls = []

    def observe(component):
        calls.append(component.parent.service_type if component.parent else None)
        return True

    class Pair:
        def __init__(self, left: Leaf, right: Leaf):
            self.left, self.right = left, right

    builder = ContainerBuilder()
    builder.register(Leaf, when=observe)
    builder.register(Pair)
    with builder.build() as owner:
        assert calls == [None, Pair, Pair]
        assert owner.resolve(Pair).left is not owner.resolve(Pair).right


def test_unknown_generic_binding_cannot_justify_early_rejection():
    from clean_ioc.component_filters import _early_match
    from clean_ioc.container import _EligibilityPreview

    T = TypeVar("T")

    class GenericService(Generic[T]):
        pass

    policy = cf.has_generic_arg(T, int)
    unresolved = _EligibilityPreview("generic", GenericService, None, (), None)
    closed = _EligibilityPreview("generic", GenericService[str], None, (), None)
    assert _early_match(policy, cast(Any, unresolved)) is None
    assert _early_match(policy, cast(Any, closed)) is False
