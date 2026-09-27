from collections.abc import Mapping
from dataclasses import FrozenInstanceError
from functools import partial
from itertools import permutations
from typing import Any, Generic, TypeVar, cast

import pytest

from clean_ioc import (
    AsyncProvider,
    BuilderAlreadyBuiltError,
    ComponentPreference,
    ContainerBuilder,
    ContainerBuildError,
    Expose,
    Provider,
    Tag,
    Undefined,
    prefer,
    select,
)
from clean_ioc import component_filters as cf


class Policy:
    pass


class A(Policy):
    pass


class B(Policy):
    pass


class C(Policy):
    pass


class Client:
    def __init__(self, policy: Policy):
        self.policy = policy


class Deferred:
    def __init__(self, policy: Provider[Policy]):
        self.policy = policy


class AsyncDeferred:
    def __init__(self, policy: AsyncProvider[Policy]):
        self.policy = policy


def never(_):
    return False


def explode(_):
    raise RuntimeError("SECRET CALLBACK PAYLOAD")


def build_pair(*, consumer=None, first=None, second=None, precedence=0, filter=cf.all_components, target=Client):
    builder = ContainerBuilder()
    builder.register(Policy, A, prefer=first, parent_precedence=precedence)
    builder.register(Policy, B, prefer=second)
    builder.register(target, arguments={"policy": select(filter, prefer=consumer)})
    builder.mark_entrypoint(target)
    return builder


def dependency_explanation(container, target=Client):
    root = next(root.component for root in container.graph.roots if root.component.service_type is target)
    return container.graph.explain(root.dependencies[0])


def test_immutable_chain_and_default_argument_contract():
    first = prefer(cf.is_named)
    second = first.then(cf.all_components)
    assert isinstance(first, ComponentPreference)
    assert first.predicates == (cf.is_named,)
    assert second.predicates == (cf.is_named, cf.all_components)
    assert select(prefer=first).filter is cf.default_component_filter
    with pytest.raises(FrozenInstanceError):
        cast(Any, first).predicates = ()
    with pytest.raises(TypeError):
        cast(Any, prefer)()
    with pytest.raises(TypeError):
        cast(Any, ComponentPreference)()


async def coroutine(_):
    return True


def generator(_):
    yield True


async def async_generator(_):
    yield True


class AsyncCallable:
    async def __call__(self, _):
        return True


class GeneratorCallable:
    def __call__(self, _):
        yield True


@pytest.mark.parametrize(
    "invalid",
    [
        None,
        1,
        [],
        coroutine,
        generator,
        async_generator,
        AsyncCallable(),
        GeneratorCallable(),
        partial(coroutine),
        partial(generator),
        partial(async_generator),
    ],
)
def test_invalid_stages_rejected_before_use(invalid):
    with pytest.raises(TypeError):
        prefer(invalid)
    chain = prefer(cf.all_components)
    with pytest.raises(TypeError):
        chain.then(invalid)
    assert len(chain.predicates) == 1


@pytest.mark.parametrize(
    "surface",
    ["register", "register_pattern", "register_subclasses", "register_generic_subclasses", "patch_component", "select"],
)
def test_wrong_chain_type_rejected_atomically(surface):
    builder = ContainerBuilder()
    component_id = builder.register(Policy, A)
    with pytest.raises(TypeError, match="ComponentPreference"):
        if surface == "select":
            select(prefer=cast(Any, cf.all_components))
        elif surface == "patch_component":
            builder.patch_component(Policy, component_id, tags=[Tag("changed")], prefer=cast(Any, False))
        elif surface == "register_pattern":
            builder.register_pattern(Policy, factory=A, prefer=cast(Any, False))
        else:
            getattr(builder, surface)(Policy, prefer=False)
    assert builder.get_component_ids(Policy) == [component_id]


@pytest.mark.parametrize("order", list(permutations((A, B, C))))
def test_ordered_consumer_stages_choose_all_matches_then_narrow(order):
    observations = []
    builder = ContainerBuilder()
    tags = {A: [Tag("primary"), Tag("region", "eu")], B: [Tag("primary")], C: [Tag("region", "eu")]}
    for implementation in order:
        builder.register(Policy, implementation, tags=tags[implementation])

    def stage(label, predicate):
        def evaluate(component):
            observations.append((label, component.implementation))
            return predicate(component)

        return evaluate

    chain = prefer(stage("primary", cf.has_tag("primary"))).then(stage("eu", cf.has_tag("region", "eu"))).then(explode)
    builder.register(Client, arguments={"policy": select(prefer=chain)})
    builder.mark_entrypoint(Client)
    container = builder.build()
    assert type(container.resolve(Client).policy) is A
    assert observations == [("primary", item) for item in reversed(order)] + [
        ("eu", item) for item in reversed(order) if item in (A, B)
    ]
    explanation = dependency_explanation(container)
    assert not any(issue.code == "ambiguous-selection" for issue in container.build_report.warnings)
    assert explanation.selected[0].preferences[-1].reason == "not-reached"
    assert all("preference-eliminated" in item.reason_codes for item in explanation.rejected)


@pytest.mark.parametrize(
    "first,second,winner",
    [
        ((False, True), (False,), A),
        ((True,), (False, True, True), A),
        ((False,), (), B),
        ((False, False), (False,), B),
        ((True,), (True,), B),
    ],
)
def test_registration_stages_missing_rules_and_exhaustion(first, second, winner):
    def chain(values):
        result = None
        for value in values:

            def predicate(_, value=value):
                return value

            result = prefer(predicate) if result is None else result.then(predicate)
        return result

    container = build_pair(first=chain(first), second=chain(second)).build()
    assert type(container.resolve(Client).policy) is winner
    assert any(issue.code == "ambiguous-selection" for issue in container.build_report.warnings) == (winner is B)


def test_all_false_falls_through_and_earlier_true_cannot_be_outweighed():
    container = build_pair(consumer=prefer(never).then(cf.implementation_type_is(A))).build()
    assert type(container.resolve(Client).policy) is A
    container = build_pair(consumer=prefer(cf.implementation_type_is(A)).then(explode).then(explode)).build()
    assert type(container.resolve(Client).policy) is A


@pytest.mark.parametrize("precedence,winner", [(0, B), (10, A), (-1, B)])
def test_numeric_then_consumer_then_registration_order(precedence, winner):
    container = build_pair(
        consumer=prefer(cf.implementation_type_is(B)), first=prefer(explode), precedence=precedence
    ).build()
    assert type(container.resolve(Client).policy) is winner


def test_filter_and_default_name_constraints_cannot_be_undone():
    container = build_pair(consumer=prefer(explode), filter=cf.implementation_type_is(A)).build()
    assert type(container.resolve(Client).policy) is A
    builder = ContainerBuilder()
    builder.register(Policy, A)
    builder.register(Policy, B, name="named")
    builder.register(Client, arguments={"policy": select(prefer=prefer(cf.is_named))})
    assert type(builder.build().resolve(Client).policy) is A


@pytest.mark.parametrize("target", [Deferred, AsyncDeferred])
@pytest.mark.parametrize("unique", [False, True])
def test_provider_final_tie_and_unique_choice(target, unique):
    builder = build_pair(consumer=prefer(cf.implementation_type_is(A) if unique else cf.all_components), target=target)
    if unique:
        container = builder.build()
        explanation = dependency_explanation(container, target)
        assert len(explanation.selected) == 1
        assert "preference-final-ambiguous" not in explanation.to_json()
        if target is Deferred:
            assert type(container.resolve(Deferred).policy()) is A
    else:
        with pytest.raises(ContainerBuildError) as caught:
            builder.build()
        explanations = [
            item
            for item in caught.value.explanations
            if any("preference-final-ambiguous" in d.reason_codes for d in item.rejected)
        ]
        assert explanations and not explanations[0].selected


@pytest.mark.asyncio
async def test_async_provider_activation_and_synthetic_parent():
    builder = build_pair(first=prefer(cf.parent(cf.service_type_is(AsyncProvider[Policy]))), target=AsyncDeferred)
    async with builder.build() as container:
        result = await container.resolve_async(AsyncDeferred)
        assert type(await result.policy()) is A
    builder = build_pair(first=prefer(cf.parent(cf.service_type_is(Client))), target=Deferred)
    with pytest.raises(ContainerBuildError):
        builder.build()


@pytest.mark.parametrize("phase", ["consumer", "registration"])
def test_reached_failure_redacted_and_failed_builder_repairable(phase):
    builder = ContainerBuilder()
    component_id = builder.register(Policy, A, prefer=prefer(explode) if phase == "registration" else None)
    builder.register(Policy, B)
    client_id = builder.register(
        Client, arguments={"policy": select(prefer=prefer(explode) if phase == "consumer" else None)}
    )
    with pytest.raises(ContainerBuildError) as caught:
        builder.build()
    error = caught.value
    assert "SECRET" not in str(error)
    assert phase in str(error)
    assert "stage 0" in str(error)
    assert any("failed" in item.to_json() for item in error.explanations)
    builder.patch_component(Policy, component_id, prefer=None)
    builder.patch_component(
        Client, client_id, arguments={"policy": select(prefer=prefer(cf.implementation_type_is(A)))}
    )
    assert type(builder.build().resolve(Client).policy) is A
    with pytest.raises(BuilderAlreadyBuiltError):
        builder.patch_component(Policy, component_id, prefer=None)


@pytest.mark.parametrize("callback", [lambda c: coroutine(c), lambda c: generator(c), lambda c: async_generator(c)])
def test_unexpected_deferred_return_is_not_truthy(callback):
    with pytest.raises(ContainerBuildError, match="preference stage 0 failed"):
        build_pair(consumer=prefer(callback)).build()


def test_one_candidate_numeric_and_hard_filter_skip_all_callbacks():
    builder = ContainerBuilder()
    builder.register(Policy, A, prefer=prefer(explode))
    builder.register(Client, arguments={"policy": select(prefer=prefer(explode))})
    assert type(builder.build().resolve(Client).policy) is A
    assert (
        type(build_pair(consumer=prefer(explode), first=prefer(explode), precedence=10).build().resolve(Client).policy)
        is A
    )


def test_invalid_losing_graph_is_still_compiled():
    class Missing:
        pass

    class Invalid(Policy):
        def __init__(self, dependency: Missing):
            pass

    builder = ContainerBuilder()
    builder.register(Policy, Invalid)
    builder.register(Policy, A)
    builder.register(Client, arguments={"policy": select(prefer=prefer(cf.implementation_type_is(A)))})
    with pytest.raises(ContainerBuildError):
        builder.build()


def test_collections_roots_previews_maps_and_duplicate_keys_ignore_preferences():
    class Collections:
        def __init__(
            self,
            items: list[Policy],
            ordered: tuple[Policy, ...],
            unique: set[Policy],
            deferred: Provider[list[Policy]],
        ):
            self.items, self.ordered, self.unique, self.deferred = items, ordered, unique, deferred

    builder = ContainerBuilder()
    builder.register(Policy, A, prefer=prefer(explode))
    builder.register(Policy, B, prefer=prefer(explode))
    builder.register(
        Collections,
        arguments={key: select(prefer=prefer(explode)) for key in ("items", "ordered", "unique", "deferred")},
    )
    builder.register_provider_map(Policy, key=lambda c: c.implementation.__name__)
    assert builder.has_component(Policy)
    assert len(builder.get_component_ids(Policy)) == 2
    with builder.build() as container:
        result = container.resolve(Collections)
        assert [type(item) for item in result.items] == [B, A]
        assert [type(item) for item in result.ordered] == [B, A]
        assert {type(item) for item in result.unique} == {A, B}
        assert [type(item) for item in result.deferred()] == [B, A]
        assert list(container.resolve(Mapping[str, Provider[Policy]])) == ["B", "A"]
        assert type(container.resolve(Policy)) is B
    duplicate = ContainerBuilder()
    duplicate.register(Policy, A, prefer=prefer(explode))
    duplicate.register(Policy, B, prefer=prefer(explode))
    duplicate.register_provider_map(Policy, key=lambda _: "duplicate")
    with pytest.raises(ContainerBuildError) as caught:
        duplicate.build()
    assert caught.value.report is not None
    assert any(issue.code == "provider-map-duplicate-key" for issue in caught.value.report.errors)


def test_boundary_context_masking_and_strict_cardinality():
    builder = ContainerBuilder()
    source = builder.create_boundary("source", exposes=(Expose(Policy),))
    source.register(Policy, A, prefer=prefer(explode))
    builder.register(Policy, B)
    builder.register(Client)
    with builder.build() as container:
        assert type(container.resolve(Client).policy) is B
        explanation = dependency_explanation(container)
        assert any(
            stage.reason == "masked-context"
            for decision in (*explanation.selected, *explanation.rejected)
            for stage in decision.preferences
        )
    invalid = ContainerBuilder()
    source = invalid.create_boundary("source", exposes=(Expose(Policy),))
    source.register(Policy, A, prefer=prefer(explode))
    source.register(Policy, B)
    with pytest.raises(ContainerBuildError):
        invalid.build()


def test_patch_undefined_replace_clear_and_discovery_persistence():
    builder = ContainerBuilder()
    first = builder.register(Policy, A, prefer=prefer(cf.all_components))
    builder.register(Policy, B)
    builder.patch_component(Policy, first, prefer=Undefined)
    assert builder._layer().registration_preferences[first] is not None
    builder.patch_component(Policy, first, prefer=None)
    assert builder._layer().registration_preferences[first] is None
    builder.patch_component(Policy, first, prefer=prefer(cf.all_components))
    builder.register(Client)
    assert type(builder.build().resolve(Client).policy) is A
    discovered = ContainerBuilder()
    discovered.register_subclasses(Policy, subclass_type_filter=lambda cls: cls in (A, B, C), prefer=prefer(explode))
    ids = discovered.get_component_ids(Policy)
    for component_id in ids:
        discovered.patch_component(Policy, component_id, prefer=None)
    discovered.register(Client)
    assert discovered.build().resolve(Client).policy is not None


def test_frozen_overlay_singleton_keeps_original_choice():
    class Frozen(Client):
        pass

    builder = ContainerBuilder()
    builder.register(Policy, A, prefer=prefer(cf.all_components), lifespan="singleton")
    builder.register(Policy, B, lifespan="singleton")
    builder.register(Frozen, lifespan="singleton")
    builder.register(Client)
    parent = builder.build()
    original = parent.resolve(Frozen)
    child = parent.new_scope_builder()
    child.register(Policy, C, prefer=prefer(cf.all_components), parent_precedence=1, lifespan="singleton")
    overlay = child.build()
    assert type(original.policy) is A
    assert overlay.resolve(Frozen) is original
    assert type(overlay.resolve(Client).policy) is C


def test_factory_decorator_preconfiguration_dependencies_apply_preferences():
    class Service:
        pass

    class Decorator(Service):
        def __init__(self, decorated: Service, policy: Policy):
            self.policy = policy

    configured = []

    def configure(policy: Policy):
        configured.append(type(policy))

    def create(policy: Policy) -> Client:
        return Client(policy)

    builder = ContainerBuilder()
    builder.register(Policy, A, prefer=prefer(cf.all_components), lifespan="singleton")
    builder.register(Policy, B, lifespan="singleton")
    builder.register(Client, factory=create)
    builder.register(Service)
    builder.register_decorator(Service, Decorator)
    builder.pre_configure(Service, configure)
    container = builder.build()
    assert type(container.resolve(Client).policy) is A
    result = container.resolve(Service)
    assert isinstance(result, Decorator)
    assert type(result.policy) is A
    assert configured == [A]


def test_generic_exact_tier_and_binding_predicate():
    T = TypeVar("T")

    class Service(Generic[T]):
        pass

    class First(Service[T]):
        pass

    class Second(Service[T]):
        pass

    class Consumer:
        def __init__(self, service: Service[int]):
            self.service = service

    builder = ContainerBuilder()
    builder.register(Service, First, prefer=prefer(cf.has_generic_arg(T, int)))
    builder.register(Service, Second)
    builder.register(Consumer)
    assert type(builder.build().resolve(Consumer).service) is First
    exact = ContainerBuilder()
    exact.register(Service, First, prefer=prefer(explode))
    exact.register(Service[int], Second[int])
    exact.register(Consumer)
    assert type(exact.build().resolve(Consumer).service) is Second


def test_diagnostics_census_profile_and_runtime_do_not_replay_callbacks():
    from clean_ioc import CompilationProfiler

    calls = []

    def choose(component):
        calls.append(component.implementation)
        return component.implementation is A

    profile = CompilationProfiler(max_records=10000)
    first = build_pair(consumer=prefer(choose)).build(profile=profile)
    before = list(calls)
    explanation = dependency_explanation(first)
    assert len(explanation.selected) == 1
    assert explanation.rejected[0].reason_codes == ("preference-eliminated",)
    census = first.graph.selection_census()
    assert any(item.eligible_not_selected for item in census.definitions)
    assert all(
        "first-eligible-wins" not in use.reason_codes
        for item in census.definitions
        for use in item.examples
        if "preference-eliminated" in use.reason_codes
    )
    report = profile.report()
    assert dict(report.counters.values)["consumer preference callback calls"] == len(calls)
    assert any(span.operation == "preference callback" and span.attempt == "primary" for span in report.spans)
    encoded = (explanation.to_json(), census.to_json(), report.to_json())
    for _ in range(3):
        assert encoded == (explanation.to_json(), census.to_json(), profile.report().to_json())
        first.graph.manifest().to_json()
        first.resolve(Client)
        with first.new_scope() as scope:
            scope.resolve(Client)
    assert calls == before
    second = build_pair(consumer=prefer(cf.implementation_type_is(A)).then(explode)).build()
    changed = build_pair(consumer=prefer(cf.implementation_type_is(B))).build()
    assert first.graph.manifest().fingerprint == second.graph.manifest().fingerprint
    assert first.graph.manifest().fingerprint != changed.graph.manifest().fingerprint


def test_failed_stage_census_preserves_prior_elimination_without_selected_winner():
    from clean_ioc import CompilationProfiler

    builder = ContainerBuilder()
    builder.register(Policy, A)
    builder.register(Policy, B)
    builder.register(Policy, C)
    builder.register(
        Client, arguments={"policy": select(prefer=prefer(lambda c: c.implementation is not C).then(explode))}
    )
    profile = CompilationProfiler(max_records=10000)
    with pytest.raises(ContainerBuildError) as caught:
        builder.build(profile=profile)
    error = caught.value
    explanation = next(
        item
        for item in error.explanations
        if any("preference-evaluation-failed" in d.reason_codes for d in item.rejected)
    )
    assert not explanation.selected
    assert all(d.outcome.value == "rejected" for d in explanation.rejected)
    assert {d.reason_codes[0] for d in explanation.rejected} == {
        "preference-eliminated",
        "preference-evaluation-failed",
        "preference-not-examined",
    }
    census = error.selection_census()
    uses = [use for d in census.definitions for use in d.examples if "Client" in use.path]
    assert not any(use.outcome == "attempt-selected" for use in uses)
    assert any(d.failed_requests for d in census.definitions)
    assert any(d.not_examined_requests for d in census.definitions)
    assert any(d.eligible_not_selected for d in census.definitions)
    assert "SECRET" not in explanation.to_json() + census.to_json() + profile.report().to_json()
    assert any(
        span.attempt and span.attempt.startswith("retry:")
        for span in profile.report().spans
        if span.operation == "preference callback"
    )


def test_unreachable_tail_evidence_is_compact():
    chain = prefer(cf.implementation_type_is(A))
    for _ in range(100):
        chain = chain.then(explode)
    container = build_pair(consumer=chain).build()
    explanation = dependency_explanation(container)
    for decision in (*explanation.selected, *explanation.rejected):
        assert len(decision.preferences) == 2
        assert decision.preferences[-1].stage == 1
        assert decision.preferences[-1].through_stage == 100


def test_registration_when_runs_once_and_independent_children_choose_separately():
    calls = []

    class Leaf:
        pass

    class First(Leaf):
        pass

    class Last(Leaf):
        pass

    class Branch(Policy):
        def __init__(self, leaf: Leaf):
            self.leaf = leaf

    builder = ContainerBuilder()
    builder.register(Leaf, First)
    builder.register(Leaf, Last)

    def eligible(c):
        if c.parent is not None:
            calls.append(c.parent.service_type)
        return True

    builder.register(Policy, Branch, when=eligible, prefer=prefer(cf.all_components))
    builder.register(Policy, B)
    builder.register(Client)
    result = builder.build().resolve(Client)
    assert isinstance(result.policy, Branch)
    assert type(result.policy.leaf) is Last
    assert calls == [Client]


def test_declared_context_helpers_and_slots_keep_root_selection():
    from clean_ioc import ResolutionContext
    from clean_ioc.factories import use_component

    class Alias:
        pass

    def forward(context: ResolutionContext) -> Alias:
        return cast(Any, context.resolve(Policy))

    builder = ContainerBuilder()
    builder.register(Policy, A, prefer=prefer(explode))
    builder.register(Policy, B, prefer=prefer(explode))
    builder.register(Alias, factory=use_component(Policy))
    builder.register(Alias, factory=forward, name="context")
    container = builder.build()
    assert type(container.resolve(Alias)) is B
    assert type(container.resolve(Alias, filter=cf.with_name("context"))) is B
    slots = ContainerBuilder()
    slots.declare_scope_slot(Policy)
    slots.register(Policy, A, when=never, prefer=prefer(explode))
    slots.register(Deferred, arguments={"policy": select(prefer=prefer(explode))})
    with slots.build().new_scope().provide(Policy, B()) as scope:
        assert type(scope.resolve(Deferred).policy()) is B


def test_consumer_observes_boundary_alias_while_registration_context_is_masked():
    from clean_ioc import BoundaryAlias

    class Public:
        pass

    class PublicClient:
        def __init__(self, service: Public):
            self.service = service

    builder = ContainerBuilder()
    source = builder.create_boundary(
        "source", exposes=(Expose(Policy, alias=BoundaryAlias(Public, name="public", tags=(Tag("public"),))),)
    )
    source.register(Policy, A, prefer=prefer(explode), tags=[Tag("private")])
    builder.register(Public, instance=B())
    builder.register(
        PublicClient,
        arguments={
            "service": select(
                cf.all_components,
                prefer=prefer(cf.service_type_is(Public) & cf.with_name("public") & cf.has_tag("public")),
            )
        },
    )
    assert type(builder.build().resolve(PublicClient).service) is A


def test_id_predicate_has_no_privileged_tier_and_composition_short_circuits():
    builder = ContainerBuilder()
    first = builder.register(Policy, A)
    second = builder.register(Policy, B)
    chain = prefer(cf.with_id(first)).then(cf.with_id(second))
    builder.register(Client, arguments={"policy": select(prefer=chain)})
    assert type(builder.build().resolve(Client).policy) is A
    composed = cf.create_filter(never) & cf.create_filter(explode)
    assert (
        type(build_pair(consumer=prefer(composed).then(cf.implementation_type_is(A))).build().resolve(Client).policy)
        is A
    )


def test_collection_and_map_members_dependencies_choose_independently():
    class Item:
        def __init__(self, policy: Policy):
            self.policy = policy

    class Many:
        def __init__(self, items: list[Item]):
            self.items = items

    builder = ContainerBuilder()
    builder.register(Policy, A, prefer=prefer(cf.all_components))
    builder.register(Policy, B)
    builder.register(Item, prefer=prefer(explode))
    builder.register(Many)
    builder.register_provider_map(Item, key=lambda _: "item")
    with builder.build() as container:
        assert type(container.resolve(Many).items[0].policy) is A
        assert type(container.resolve(Mapping[str, Provider[Item]])["item"]().policy) is A


def test_alias_argument_transports_consumer_preferences():
    from typing_extensions import TypeAliasType

    Alias = TypeAliasType("Alias", Policy)  # noqa: N806

    class Aliased:
        def __init__(self, policy: Alias):
            self.policy = policy

    builder = ContainerBuilder()
    builder.register(Policy, A)
    builder.register(Policy, B)
    builder.register(Aliased, arguments={"policy": select(prefer=prefer(cf.implementation_type_is(A)))})
    assert type(builder.build().resolve(Aliased).policy) is A


def test_pattern_preference_transport_and_exact_tier_bypass():
    T = TypeVar("T")

    class Service(Generic[T]):
        pass

    class First(Service[T]):
        pass

    class Second(Service[T]):
        pass

    class Consumer:
        def __init__(self, service: Service[int]):
            self.service = service

    builder = ContainerBuilder()
    builder.register_pattern(Service[T], factory=First, prefer=prefer(cf.all_components))
    builder.register_pattern(Service[T], factory=Second)
    builder.register(Consumer)
    assert type(builder.build().resolve(Consumer).service) is First
    exact = ContainerBuilder()
    exact.register_pattern(Service[T], factory=First, prefer=prefer(explode))
    exact.register(Service[int], Second[int])
    exact.register(Consumer)
    assert type(exact.build().resolve(Consumer).service) is Second


def test_generic_discovery_preferences_and_patched_fallback_are_preserved():
    T = TypeVar("T")

    class Service(Generic[T]):
        pass

    class Open(Service[T]):
        pass

    class First(Service[int]):
        pass

    class Second(Service[int]):
        pass

    class Consumer:
        def __init__(self, service: Service[int]):
            self.service = service

    builder = ContainerBuilder()
    builder.register_generic_subclasses(Service, fallback_type=Open, prefer=prefer(cf.implementation_type_is(First)))
    ids = builder.get_component_ids(Service[int])
    assert len(ids) == 2
    rule = builder._registration_discoveries[0]
    assert rule.fallback_registration is not None
    fallback = rule.fallback_registration.id
    builder.patch_component(Service, fallback, prefer=None)
    builder.register(Consumer)
    assert type(builder.build().resolve(Consumer).service) is First


def test_missing_registration_rule_is_not_misreported_as_masked_context():
    container = build_pair(first=prefer(cf.all_components)).build()
    explanation = dependency_explanation(container)
    stage = explanation.rejected[0].preferences[0]
    assert stage.reason == "missing-rule"
    assert stage.outcome is None
    assert stage.eliminated
