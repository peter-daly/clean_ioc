from itertools import permutations
from typing import Any, cast

import pytest

from clean_ioc import AsyncProvider, ContainerBuilder, ContainerBuildError, Provider, select
from clean_ioc import component_filters as cf


class Policy:
    pass


class Default(Policy):
    pass


class Preferred(Policy):
    pass


class Application(Policy):
    pass


class Consumer:
    def __init__(self, policy: Policy, policies: list[Policy]):
        self.policy = policy
        self.policies = policies


class Deferred:
    def __init__(self, policy: Provider[Policy]):
        self.policy = policy


class AsyncDeferred:
    def __init__(self, policy: AsyncProvider[Policy]):
        self.policy = policy


@pytest.mark.parametrize("order", list(permutations(((Default, 0), (Preferred, 10)))))
def test_contextual_choice_preserves_roots_previews_collections_and_hard_filters(order):
    builder = ContainerBuilder()
    for implementation, value in order:
        builder.register(Policy, implementation, parent_precedence=value)
    builder.register(Consumer)
    builder.register(Consumer, name="filtered", arguments={"policy": select(cf.implementation_type_is(Default))})
    preview = builder.get_component_id(Policy)
    with builder.build() as container:
        result = container.resolve(Consumer)
        assert isinstance(result.policy, Preferred)
        assert [type(item) for item in result.policies] == [item[0] for item in reversed(order)]
        assert type(container.resolve(Policy)) is order[-1][0]
        assert container.graph is not None
        assert preview is not None
        assert isinstance(container.resolve(Consumer, filter=cf.with_name("filtered")).policy, Default)


@pytest.mark.parametrize("values", [(0, 0), (-100, -5), (10**100, 10**100 + 1)])
def test_signed_values_and_ordinary_ties(values):
    builder = ContainerBuilder()
    builder.register(Policy, Default, parent_precedence=values[0])
    builder.register(Policy, Preferred, parent_precedence=values[1])
    builder.register(Consumer)
    with builder.build() as container:
        assert isinstance(container.resolve(Consumer).policy, Preferred)
        warnings = [issue for issue in container.build_report.warnings if "policy" in issue.message]
        assert bool(warnings) == (values[0] == values[1])


@pytest.mark.parametrize("bad", [True, False, 1.5, "10", None, lambda: 1])
@pytest.mark.parametrize("method", ["register", "register_subclasses", "register_fallback", "register_pattern"])
def test_invalid_declarations_are_atomic(method, bad):
    builder = ContainerBuilder()
    kwargs: dict[str, Any] = {"parent_precedence": bad}
    if method == "register_pattern":
        kwargs["factory"] = Default
    with pytest.raises(TypeError, match="parent_precedence"):
        getattr(builder, method)(Policy, **kwargs)
    assert builder.get_component_ids(Policy) == []
    builder.register(Policy, Default)
    assert isinstance(builder.build().resolve(Policy), Default)


def test_patch_validation_reset_immutability_and_discovered_metadata():
    builder = ContainerBuilder()
    builder.register_subclasses(Policy, subclass_type_filter=lambda cls: cls is Preferred, parent_precedence=10)
    discovered = builder.get_component_id(Policy)
    assert discovered is not None
    fallback = builder.register(Policy, Default)
    with pytest.raises(TypeError, match="parent_precedence"):
        builder.patch_component(Policy, fallback, parent_precedence=True, tags=())
    builder.patch_component(Policy, discovered, parent_precedence=-2)
    builder.patch_component(Policy, fallback, parent_precedence=0)
    builder.register(Consumer)
    container = builder.build()
    assert isinstance(container.resolve(Consumer).policy, Default)
    with pytest.raises(Exception):
        builder.patch_component(Policy, fallback, parent_precedence=100)
    layer = container._plan.blueprint.layers[0]
    with pytest.raises(TypeError):
        cast(Any, layer.registration_parent_precedence)[fallback] = 99


@pytest.mark.parametrize("tied", [False, True])
def test_provider_unique_maximum_and_tied_maximum(tied):
    builder = ContainerBuilder()
    builder.register(Policy, Default, parent_precedence=-1)
    builder.register(Policy, Preferred, parent_precedence=10)
    if tied:
        builder.register(Policy, Application, parent_precedence=10)
    builder.register(Deferred)
    if tied:
        with pytest.raises(ContainerBuildError) as caught:
            builder.build()
        assert caught.value.report is not None
        assert any(issue.code == "provider-ambiguous-component" for issue in caught.value.report.errors)
        explanations = [
            item
            for item in caught.value.explanations
            if any("equal-parent-precedence-ambiguous" in decision.reason_codes for decision in item.rejected)
        ]
        assert explanations and not explanations[0].selected
    else:
        with builder.build() as container:
            assert isinstance(container.resolve(Deferred).policy(), Preferred)


@pytest.mark.asyncio
async def test_async_provider_target_is_frozen():
    builder = ContainerBuilder()
    builder.register(Policy, Preferred, parent_precedence=10)
    builder.register(Policy, Default)
    builder.register(AsyncDeferred)
    async with builder.build() as container:
        consumer = await container.resolve_async(AsyncDeferred)
        assert isinstance(await consumer.policy(), Preferred)


def test_evidence_census_and_fingerprint_do_not_replay_callbacks():
    calls = []

    def predicate(component):
        calls.append(component.id)
        return True

    def build(value):
        builder = ContainerBuilder()
        builder.register(Policy, Preferred, parent_precedence=value, when=predicate)
        builder.register(Policy, Default)
        builder.register(Consumer)
        builder.mark_entrypoint(Consumer)
        return builder.build()

    first = build(10)
    second = build(20)
    before = len(calls)
    assert first.graph.manifest().fingerprint == second.graph.manifest().fingerprint
    census = first.graph.selection_census()
    assert any(item.eligible_not_selected for item in census.definitions)
    assert "lower-parent-precedence" in census.to_json()
    for definition in census.definitions:
        for use in definition.examples:
            if "lower-parent-precedence" in use.reason_codes:
                assert "first-eligible-wins" not in use.reason_codes
    for _ in range(3):
        first.resolve(Consumer)
        first.graph.selection_census().to_json()
        first.graph.manifest().to_json()
    assert len(calls) == before


def test_losing_invalid_candidate_is_not_hidden_and_failed_builder_can_be_repaired():
    class Missing:
        pass

    class Broken(Policy):
        def __init__(self, missing: Missing):
            self.missing = missing

    builder = ContainerBuilder()
    builder.register(Policy, Broken, parent_precedence=-10)
    builder.register(Policy, Preferred, parent_precedence=10)
    builder.register(Consumer)
    with pytest.raises(ContainerBuildError):
        builder.build()
    builder.register(Missing)
    assert isinstance(builder.build().resolve(Consumer).policy, Preferred)


def test_overlay_new_choices_do_not_rewire_anchored_singletons():
    class Frozen:
        def __init__(self, policy: Policy):
            self.policy = policy

    builder = ContainerBuilder()
    builder.register(Policy, Preferred, parent_precedence=10, lifespan="singleton")
    builder.register(Consumer)
    builder.register(Frozen, lifespan="singleton")
    parent = builder.build()
    original = parent.resolve(Frozen)
    overlay_builder = parent.new_scope_builder()
    overlay_builder.register(Policy, Application, parent_precedence=30, lifespan="singleton")
    overlay = overlay_builder.build()
    assert isinstance(overlay.resolve(Consumer).policy, Application)
    assert overlay.resolve(Frozen) is original
    assert isinstance(original.policy, Preferred)
    assert isinstance(parent.new_scope().resolve(Consumer).policy, Preferred)


def test_boundary_definition_side_masks_preference_and_cardinality_stays_strict():
    from clean_ioc import Expose

    builder = ContainerBuilder()
    source = builder.create_boundary("source", exposes=(Expose(Policy),))
    source.register(Policy, Preferred, parent_precedence=100)
    builder.register(Policy, Default)
    builder.register(Consumer)
    container = builder.build()
    assert isinstance(container.resolve(Consumer).policy, Default)

    invalid = ContainerBuilder()
    source = invalid.create_boundary("source", exposes=(Expose(Policy),))
    source.register(Policy, Preferred, parent_precedence=100)
    source.register(Policy, Default)
    with pytest.raises(ContainerBuildError):
        invalid.build()


def test_generic_discovery_fallback_patch_and_exact_pattern_tier():
    from typing import Generic, TypeVar

    T = TypeVar("T")

    class Service(Generic[T]):
        pass

    class Open(Service[T]):
        pass

    class Closed(Service[int]):
        pass

    class GenericConsumer:
        def __init__(self, service: Service[int]):
            self.service = service

    builder = ContainerBuilder()
    builder.register_subclasses(Service, parent_precedence=10)
    builder.register_fallback(Service, Open, parent_precedence=10)
    discovered = builder.get_component_id(Service[int])
    assert discovered is not None
    builder.patch_component(Service[int], discovered, parent_precedence=-10)
    builder.register_pattern(Service[T], factory=Open, parent_precedence=100)
    builder.register(GenericConsumer)
    assert isinstance(builder.build().resolve(GenericConsumer).service, Closed)


def test_collection_members_dependencies_rank_independently_without_score_inheritance():
    class Leaf:
        pass

    class Earlier(Leaf):
        pass

    class Later(Leaf):
        pass

    class Branch(Policy):
        def __init__(self, leaf: Leaf):
            self.leaf = leaf

    builder = ContainerBuilder()
    builder.register(Leaf, Earlier)
    builder.register(Leaf, Later)
    builder.register(Policy, Branch, parent_precedence=100)
    builder.register(Policy, Default)
    builder.register(Consumer)
    result = builder.build().resolve(Consumer)
    assert isinstance(result.policy, Branch)
    assert isinstance(result.policy.leaf, Later)
    assert [type(item) for item in result.policies] == [Default, Branch]


def test_provider_map_retains_members_and_duplicate_keys():
    from collections.abc import Mapping

    builder = ContainerBuilder()
    builder.register(Policy, Preferred, parent_precedence=10)
    builder.register(Policy, Default)
    builder.register_provider_map(Policy, key=lambda component: component.implementation.__name__)
    result = builder.build().resolve(Mapping[str, Provider[Policy]])
    assert list(result) == ["Default", "Preferred"]
    assert isinstance(result["Preferred"](), Preferred)
    duplicate = ContainerBuilder()
    duplicate.register(Policy, Preferred, parent_precedence=10)
    duplicate.register(Policy, Default)
    duplicate.register_provider_map(Policy, key=lambda component: "same")
    with pytest.raises(ContainerBuildError) as caught:
        duplicate.build()
    assert caught.value.report is not None
    assert any(issue.code == "provider-map-duplicate-key" for issue in caught.value.report.errors)


def test_tuple_set_and_deferred_collection_membership_ignores_values():
    class Collections:
        def __init__(self, ordered: tuple[Policy, ...], unique: set[Policy], deferred: Provider[list[Policy]]):
            self.ordered, self.unique, self.deferred = ordered, unique, deferred

    builder = ContainerBuilder()
    builder.register(Policy, Preferred, parent_precedence=10)
    builder.register(Policy, Default)
    builder.register(Collections)
    result = builder.build().resolve(Collections)
    assert [type(item) for item in result.ordered] == [Default, Preferred]
    assert {type(item) for item in result.unique} == {Default, Preferred}
    assert [type(item) for item in result.deferred()] == [Default, Preferred]


def test_decorator_and_preconfiguration_dependencies_rank_but_applicability_stays_boolean():
    configured = []

    class Service:
        pass

    class Decorator(Service):
        def __init__(self, decorated: Service, policy: Policy):
            self.decorated, self.policy = decorated, policy

    def configure(policy: Policy):
        configured.append(type(policy))

    builder = ContainerBuilder()
    builder.register(Policy, Preferred, parent_precedence=10, lifespan="singleton")
    builder.register(Policy, Default, lifespan="singleton")
    builder.register(Service)
    builder.register_decorator(Service, Decorator)
    builder.register_decorator(Service, Decorator)
    builder.pre_configure(Service, configure)
    builder.pre_configure(Service, configure)
    result = builder.build().resolve(Service)
    assert isinstance(result, Decorator)
    assert isinstance(result.policy, Preferred)
    assert isinstance(result.decorated, Decorator)
    assert isinstance(result.decorated.policy, Preferred)
    assert configured == [Preferred, Preferred]


def test_failed_callback_is_not_hidden_by_precedence_and_build_can_be_repaired():
    state = {"fail": True}

    def conditional(component):
        if state["fail"]:
            raise ValueError("broken policy")
        return True

    builder = ContainerBuilder()
    builder.register(Policy, Default, when=conditional, parent_precedence=-100)
    builder.register(Policy, Preferred, parent_precedence=10)
    builder.register(Consumer)
    with pytest.raises(ContainerBuildError) as caught:
        builder.build()
    assert caught.value.report is not None
    assert any(
        "ValueError" in decision.reason
        for explanation in caught.value.explanations
        for decision in explanation.rejected
    )
    state["fail"] = False
    assert isinstance(builder.build().resolve(Consumer).policy, Preferred)


def test_scope_slot_fallback_and_per_call_target_use_frozen_plans():
    class Resource:
        def __init__(self):
            self.calls = 0

    class Operation:
        def run(self):
            raise NotImplementedError

    class PreferredOperation(Operation):
        def __init__(self, resource: Resource):
            self.resource = resource

        def run(self):
            self.resource.calls += 1
            return self.resource.calls

    class FallbackOperation(Operation):
        def run(self):
            return -1

    class Client:
        def __init__(self, operation: Operation):
            self.operation = operation

    builder = ContainerBuilder()
    builder.register(Resource, lifespan="scoped")
    builder.register(Operation, PreferredOperation, scope="per_call", parent_precedence=10)
    builder.register(Operation, FallbackOperation, scope="per_call")
    builder.register(Client, lifespan="singleton")
    with builder.build() as container:
        client = container.resolve(Client)
        assert client.operation.run() == client.operation.run() == 1

    slots = ContainerBuilder()
    slots.declare_scope_slot(Policy)
    slots.register(Policy, Preferred, parent_precedence=100, when=lambda component: False)
    slots.register(Deferred)
    with slots.build().new_scope().provide(Policy, Default()) as scope:
        assert isinstance(scope.resolve(Deferred).policy(), Default)


def test_tied_maximum_census_does_not_claim_first_eligible_won():
    builder = ContainerBuilder()
    builder.register(Policy, Preferred, parent_precedence=10)
    builder.register(Policy, Application, parent_precedence=10)
    builder.register(Policy, Default)
    builder.register(Consumer)
    builder.mark_entrypoint(Consumer)
    container = builder.build()
    assert isinstance(container.resolve(Consumer).policy, Application)
    uses = [use for item in container.graph.selection_census().definitions for use in item.examples]
    tie = next(use for use in uses if "equal-parent-precedence-order" in use.reason_codes)
    assert "first-eligible-wins" not in tie.reason_codes


@pytest.mark.parametrize("negative", [False, True])
def test_unbounded_integer_scores_build_and_serialize_without_decimal_conversion(negative):
    import json
    import sys

    value = -(10**5000) if negative else 10**5000
    original_limit = sys.get_int_max_str_digits()
    builder = ContainerBuilder()
    builder.register(Policy, Preferred, parent_precedence=value)
    builder.register(Policy, Default, parent_precedence=value - 1)
    builder.register(Consumer)
    container = builder.build()
    assert isinstance(container.resolve(Consumer).policy, Preferred)
    root = next(root for root in container.graph.roots if root.component.service_type is Consumer)
    dependency = next(item for item in root.component.dependencies if item.service_type is Policy)
    explanation = container.graph.explain(dependency)
    assert explanation.selected[0].parent_precedence == value
    encoded = json.loads(explanation.to_json())
    assert int(encoded["selected"][0]["parent_precedence"]["integer_hex"], 16) == value
    assert sys.get_int_max_str_digits() == original_limit
