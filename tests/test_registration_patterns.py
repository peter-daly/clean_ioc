import json
import sys
import types
from collections.abc import Callable, Iterator, Mapping
from contextlib import asynccontextmanager, contextmanager
from typing import Any, Generic, Literal, NewType, Protocol, TypeVar, cast
from typing import List as TypingList

import pytest
from typing_extensions import TypeAliasType

from clean_ioc import (
    AsyncProvider,
    BoundaryAlias,
    CannotResolveError,
    ContainerBuilder,
    ContainerBuildError,
    Expose,
    Provider,
    Tag,
    Use,
    generic_arg,
    select,
)
from clean_ioc import component_filters as cf
from clean_ioc import registration_patterns as patterns

T = TypeVar("T")
U = TypeVar("U")


class Serializer(Generic[T]):
    def __init__(self, label: str = "leaf", child: Any = None):
        self.label, self.child = label, child

    def serialize(self, value):
        if self.child is None:
            return str(value)
        return "[" + ", ".join(self.child.serialize(item) for item in value) + "]"


class PublicSerializer(Generic[T]):
    pass


def make_list_serializer(item_serializer: Serializer[T]) -> Serializer[list[T]]:
    return Serializer("list", item_serializer)


def make_dict_serializer(item_serializer: Serializer[T]) -> Serializer[dict[str, T]]:
    return Serializer("dict", item_serializer)


def request(builder, annotation, *, arguments=None):
    class Root:
        def __init__(self, value: annotation):
            self.value = value

    builder.register(Root, arguments=arguments)
    return Root


def error_codes(error):
    return {issue.code for issue in error.value.report.errors}


def test_real_nested_list_example_and_frozen_public_closed_roots(monkeypatch):
    builder = ContainerBuilder()
    builder.register(Serializer[int], factory=Serializer)
    component_id = builder.register_pattern(Serializer[list[T]], factory=make_list_serializer)
    root = request(builder, Serializer[list[list[int]]])
    container = builder.build()
    assert isinstance(component_id, str)
    assert container.resolve(root).value.serialize([[1, 2], [3]]) == "[[1, 2], [3]]"
    assert container.resolve(Serializer[list[int]]).serialize([1]) == "[1]"
    assert container.resolve(Serializer[list[list[int]]]).serialize([[1]]) == "[[1]]"
    with pytest.raises(CannotResolveError):
        container.resolve(Serializer[list[str]])

    def forbidden(*args, **kwargs):
        pytest.fail("runtime performed pattern matching")

    monkeypatch.setattr(patterns, "match", forbidden)
    assert container.resolve(root).value.serialize([[3]]) == "[[3]]"
    assert container.resolve(Provider[Serializer[list[int]]])().serialize([4]) == "[4]"


def test_template_alone_neither_activates_nor_enumerates_roots():
    def forbidden():
        pytest.fail("factory activated")

    builder = ContainerBuilder()
    builder.register_pattern(Serializer[list[T]], factory=forbidden)
    container = builder.build()
    assert not container.has_component(Serializer[list[int]])
    assert not container.has_component(Serializer[list[T]])


@pytest.mark.parametrize(
    ("pattern", "closed", "matches"),
    [
        (Serializer[dict[str, T]], Serializer[dict[str, int]], True),
        (Serializer[dict[str, T]], Serializer[dict[int, str]], False),
        (Serializer[tuple[T, T]], Serializer[tuple[int, int]], True),
        (Serializer[tuple[T, T]], Serializer[tuple[int, str]], False),
        (Serializer[tuple[int, T]], Serializer[tuple[bool, str]], False),
    ],
)
def test_concrete_and_repeated_positions(pattern, closed, matches):
    builder = ContainerBuilder()
    builder.register_pattern(pattern, factory=Serializer)
    root = request(builder, closed)
    if matches:
        assert isinstance(builder.build().resolve(root).value, Serializer)
    else:
        with pytest.raises(ContainerBuildError):
            builder.build()


def test_exact_pattern_open_precedence_and_filter_tiers():
    builder = ContainerBuilder()
    builder.register(Serializer, factory=lambda: Serializer("open"))
    builder.register_pattern(Serializer[T], factory=lambda: Serializer("broad"))
    builder.register_pattern(Serializer[list[T]], factory=lambda: Serializer("list"))
    builder.register(Serializer[list[int]], factory=lambda: Serializer("exact"), name="exact")
    exact = request(builder, Serializer[list[int]], arguments={"value": select(cf.with_name("exact"))})
    nested = request(builder, Serializer[list[str]])
    general = request(builder, Serializer[int])
    container = builder.build()
    assert container.resolve(exact).value.label == "exact"
    assert container.resolve(nested).value.label == "list"
    assert container.resolve(general).value.label == "broad"
    with pytest.raises(CannotResolveError):
        container.resolve(Serializer[list[int]], cf.with_name("pattern"))

    builder = ContainerBuilder()
    builder.register(Serializer[list[int]], factory=Serializer, name="exact")
    builder.register_pattern(Serializer[list[T]], factory=Serializer, name="pattern")
    request(builder, Serializer[list[int]], arguments={"value": select(cf.with_name("pattern"))})
    with pytest.raises(ContainerBuildError):
        builder.build()


def test_open_fallback_when_pattern_mismatches():
    builder = ContainerBuilder()
    builder.register(Serializer, factory=lambda: Serializer("open"))
    builder.register_pattern(Serializer[dict[str, T]], factory=Serializer)
    root = request(builder, Serializer[dict[int, str]])
    assert builder.build().resolve(root).value.label == "open"


@pytest.mark.parametrize("reverse", [False, True])
def test_incomparable_patterns_fail_independently_of_order_and_filters(reverse):
    templates = [Serializer[tuple[int, T]], Serializer[tuple[U, str]]]
    builder = ContainerBuilder()
    for template in reversed(templates) if reverse else templates:
        builder.register_pattern(template, factory=Serializer, when=lambda component: False)
    request(builder, Serializer[tuple[int, str]])
    with pytest.raises(ContainerBuildError) as error:
        builder.build()
    assert "pattern-ambiguous" in error_codes(error)


def test_specificity_relation_includes_nested_structure_repetition_and_domains():
    number = TypeVar("number", bound=int)
    small = TypeVar("small", bool, int)
    text_or_number = TypeVar("text_or_number", str, int)
    assert patterns.more_specific(Serializer[list[list[T]]], Serializer[list[U]])
    assert patterns.more_specific(Serializer[tuple[T, T]], Serializer[tuple[T, U]])
    assert patterns.more_specific(Serializer[number], Serializer[T])
    assert patterns.more_specific(Serializer[small], Serializer[text_or_number])
    assert not patterns.more_specific(Serializer[tuple[int, T]], Serializer[tuple[U, str]])
    assert not patterns.more_specific(Serializer[tuple[U, str]], Serializer[tuple[int, T]])
    assert not patterns.more_specific(Serializer[list[T]], Serializer[list[U]])


def test_bounds_constraints_and_bound_specificity():
    number = TypeVar("number", bound=int)
    text = TypeVar("text", str, bytes)
    builder = ContainerBuilder()
    builder.register_pattern(Serializer[T], factory=lambda: Serializer("any"))
    builder.register_pattern(Serializer[number], factory=lambda: Serializer("number"))
    builder.register_pattern(Serializer[text], factory=lambda: Serializer("text"))
    roots = [request(builder, Serializer[value]) for value in (bool, str, list[int])]
    container = builder.build()
    assert [container.resolve(root).value.label for root in roots] == ["number", "text", "any"]


@pytest.mark.parametrize("kind", ["parameterized", "protocol"])
def test_unsupported_typevar_bounds_are_diagnosed_at_build_even_unused(kind):
    class Interface(Protocol):
        def run(self): ...

    bound = list[int] if kind == "parameterized" else Interface
    variable = TypeVar("variable", bound=bound)
    builder = ContainerBuilder()
    builder.register_pattern(Serializer[variable], factory=Serializer)
    with pytest.raises(ContainerBuildError) as error:
        builder.build()
    assert "pattern-unsupported-form" in error_codes(error)


@pytest.mark.parametrize(
    "template",
    [
        Serializer[int],
        Serializer,
        Serializer[T | None],
        Serializer[tuple[T, ...]],
        Serializer[Callable[[T], str]],
        Serializer[tuple[Literal["x"], T]],
        Serializer[Any],
    ],
)
def test_invalid_or_unsupported_templates(template):
    builder = ContainerBuilder()
    builder.register_pattern(template, factory=Serializer)
    with pytest.raises(ContainerBuildError) as error:
        builder.build()
    assert error_codes(error) & {"pattern-invalid", "pattern-unsupported-form"}


def test_aliases_and_nominal_newtypes():
    nominal = NewType("nominal", int)
    alias = TypeAliasType("alias", Serializer[list[T]], type_params=(T,))
    builder = ContainerBuilder()
    builder.register(Serializer[nominal], factory=lambda: Serializer("nominal"))
    builder.register_pattern(alias, factory=make_list_serializer)
    root = request(builder, alias[nominal])
    container = builder.build()
    assert container.resolve(root).value.child.label == "nominal"
    assert container.has_component(Serializer[list[nominal]])
    assert not container.has_component(Serializer[list[int]])


def test_same_named_variables_and_unbound_factory_variables_are_rejected():
    other_t = TypeVar("T")  # ty: ignore[mismatched-type-name]

    def bad(child: Serializer[other_t]):
        return child

    for template, factory in ((Serializer[tuple[T, other_t]], Serializer), (Serializer[T], bad)):
        builder = ContainerBuilder()
        builder.register_pattern(template, factory=factory)
        request(builder, Serializer[int] if template == Serializer[T] else Serializer[tuple[int, int]])
        with pytest.raises(ContainerBuildError) as error:
            builder.build()
        assert "pattern-incompatible-binding" in error_codes(error)

    def unbound(child: Serializer[U]):
        return child

    builder = ContainerBuilder()
    builder.register_pattern(Serializer[T], factory=unbound)
    request(builder, Serializer[int])
    with pytest.raises(ContainerBuildError) as error:
        builder.build()
    assert "pattern-incompatible-binding" in error_codes(error)


def test_conflicting_factory_result_is_rejected():
    def bad() -> Serializer[dict[str, T]]:
        return Serializer()

    builder = ContainerBuilder()
    builder.register_pattern(Serializer[list[T]], factory=bad)
    request(builder, Serializer[list[int]])
    with pytest.raises(ContainerBuildError) as error:
        builder.build()
    assert "pattern-incompatible-binding" in error_codes(error)


def test_canonical_multibindings_names_order_tags_and_conditions():
    def factory(label: str):
        return Serializer(label)

    builder = ContainerBuilder()
    for label in ("old", "new", "hidden"):
        builder.register_pattern(
            Serializer[list[T]],
            factory=factory,
            name=label,
            arguments={"label": label},
            tags=[Tag("group", "test")],
            when=lambda c: c.name != "hidden",
        )
    root = request(builder, list[Serializer[list[int]]], arguments={"value": select(cf.all_components)})
    container = builder.build()
    assert [item.label for item in container.resolve(root).value] == ["new", "old"]
    assert container.resolve(Serializer[list[int]], cf.with_name("old")).label == "old"
    assert [item.label for item in container.resolve(list[Serializer[list[int]]], cf.all_components)] == ["new", "old"]


@pytest.mark.parametrize("lifespan", ["transient", "per_resolution", "scoped", "singleton"])
def test_specialization_cache_identity_and_lifespans(lifespan):
    class Pair:
        def __init__(self, left: Serializer[int], right: Serializer[int], other: Serializer[str]):
            self.left, self.right, self.other = left, right, other

    builder = ContainerBuilder()
    builder.register_pattern(Serializer[T], factory=Serializer, lifespan=lifespan)
    builder.register(Pair)
    with builder.build() as container:
        with container.new_scope() as scope:
            pair = scope.resolve(Pair)
            assert (pair.left is pair.right) == (lifespan != "transient")
            assert pair.left is not pair.other
            assert (scope.resolve(Pair).left is pair.left) == (lifespan in ("scoped", "singleton"))


def test_service_metadata_is_separate_from_structural_factory_binding():
    seen = []

    def factory(child: Serializer[T], item_type: type) -> Serializer[list[T]]:
        seen.append(item_type)
        return Serializer(child=child)

    builder = ContainerBuilder()
    builder.register(Serializer[int], factory=Serializer)
    builder.register_pattern(Serializer[list[T]], factory=factory, arguments={"item_type": generic_arg(T)})
    root = request(builder, Serializer[list[int]])
    container = builder.build()
    assert not seen
    assert container.resolve(root).value.child is not None
    assert seen == [list[int]]


def test_sync_resource_patterns_and_preconfiguration():
    events = []

    @contextmanager
    def factory() -> Iterator[Serializer[T]]:
        events.append("open")
        yield Serializer()
        events.append("close")

    builder = ContainerBuilder()
    builder.register_pattern(Serializer[T], factory=factory, lifespan="singleton")
    builder.pre_configure(Serializer, lambda: events.append("configure"))
    root = request(builder, Serializer[int])
    with builder.build() as container:
        assert not events
        container.resolve(root)
        assert events == ["configure", "open"]
    assert events == ["configure", "open", "close"]


@pytest.mark.asyncio
async def test_async_resources_providers_and_maps_compile_without_activation(monkeypatch):
    events = []

    @asynccontextmanager
    async def factory():
        events.append("open")
        yield Serializer()
        events.append("close")

    builder = ContainerBuilder()
    builder.register_pattern(Serializer[T], factory=factory, name="a", lifespan="scoped")
    builder.register_provider_map(Serializer[list[int]], key=lambda c: c.name, asynchronous=True)
    root = request(builder, AsyncProvider[Serializer[str]], arguments={"value": select(cf.with_name("a"))})
    async with builder.build() as container:
        assert not events

        def forbidden(*args, **kwargs):
            pytest.fail("runtime matching")

        monkeypatch.setattr(patterns, "match", forbidden)
        values = await container.resolve_async(Mapping[str, AsyncProvider[Serializer[list[int]]]])
        provider = (await container.resolve_async(root)).value
        assert not events
        assert isinstance(await values["a"](), Serializer)
        assert isinstance(await provider(), Serializer)
    assert events == ["open", "open", "close", "close"]


def test_missing_provider_map_pattern_dependency_fails_even_if_never_called():
    builder = ContainerBuilder()
    builder.register_pattern(Serializer[list[T]], factory=make_list_serializer)
    builder.register_provider_map(Serializer[list[int]], key=lambda c: "a")
    with pytest.raises(ContainerBuildError):
        builder.build()
    builder.register(Serializer[int], factory=Serializer)
    assert builder.build().resolve(Mapping[str, Provider[Serializer[list[int]]]])["a"]().serialize([1]) == "[1]"


def test_growing_and_ordinary_cycles_have_different_codes():
    def growing(child: Serializer[list[T]]) -> Serializer[T]:
        return Serializer(child=child)

    def circular(child: Serializer[T]) -> Serializer[T]:
        return child

    for factory, code in ((growing, "pattern-non-terminating-expansion"), (circular, "circular-dependency")):
        builder = ContainerBuilder()
        builder.register_pattern(Serializer[T], factory=factory)
        request(builder, Serializer[int])
        with pytest.raises(ContainerBuildError) as error:
            builder.build()
        assert code in error_codes(error)
        assert "RecursionError" not in str(error.value)


def test_closed_and_open_aliased_boundary_pattern_exposures_compile_source_specializations():
    def bundle(builder):
        builder.register(Serializer[int], factory=lambda: Serializer("private"))
        builder.register_pattern(Serializer[list[T]], factory=make_list_serializer)

    builder = ContainerBuilder()
    builder.create_boundary("serialization", exposes=(Expose(Serializer[list[int]]),)).apply_bundle(bundle)
    root = request(builder, Serializer[list[int]])
    container = builder.build()
    assert container.resolve(root).value.child.label == "private"
    assert not container.has_component(Serializer[int])
    assert not container.has_component(Serializer[list[str]])

    class Consumer:
        def __init__(self, value: PublicSerializer[list[int]]):
            self.value = value

    Consumer.__init__.__annotations__["value"] = PublicSerializer[list[int]]

    def consumer_bundle(private):
        private.register(Consumer)

    builder = ContainerBuilder()
    builder.create_boundary(
        "serialization",
        exposes=(
            Expose(
                Serializer[list[T]],
                alias=BoundaryAlias(PublicSerializer[list[T]]),
            ),
        ),
    ).apply_bundle(bundle)
    builder.create_boundary(
        "consumer", uses=(Use("serialization", PublicSerializer[list[T]]),), exposes=(Expose(Consumer),)
    ).apply_bundle(consumer_bundle)
    container = builder.build()
    assert cast(Any, container.resolve(Consumer).value).child.label == "private"
    assert cast(Any, container.resolve(PublicSerializer[list[int]])).child.label == "private"
    assert not container.has_component(PublicSerializer[list[str]])


def test_public_alias_patterns_with_one_origin_route_by_complete_structure():
    class Consumer:
        def __init__(
            self,
            list_value: PublicSerializer[list[int]],
            dict_value: PublicSerializer[dict[str, int]],
        ):
            self.list_value = list_value
            self.dict_value = dict_value

    Consumer.__init__.__annotations__["list_value"] = PublicSerializer[list[int]]
    Consumer.__init__.__annotations__["dict_value"] = PublicSerializer[dict[str, int]]

    def source(builder):
        builder.register(Serializer[int], factory=lambda: Serializer("leaf"))
        builder.register_pattern(Serializer[list[T]], factory=make_list_serializer)
        builder.register_pattern(Serializer[dict[str, T]], factory=make_dict_serializer)

    def consumer(builder):
        builder.register(Consumer)

    builder = ContainerBuilder()
    builder.create_boundary(
        "serialization",
        exposes=(
            Expose(
                Serializer[list[T]],
                alias=BoundaryAlias(PublicSerializer[list[T]]),
            ),
            Expose(
                Serializer[dict[str, T]],
                alias=BoundaryAlias(PublicSerializer[dict[str, T]]),
            ),
        ),
    ).apply_bundle(source)
    builder.create_boundary(
        "consumer",
        uses=(
            Use(
                "serialization",
                PublicSerializer[list[int]],
                filter=cf.service_type_is(PublicSerializer[list[int]]),
            ),
            Use(
                "serialization",
                PublicSerializer[dict[str, int]],
                filter=cf.service_type_is(PublicSerializer[dict[str, int]]),
            ),
        ),
        exposes=(Expose(Consumer),),
    ).apply_bundle(consumer)
    container = builder.build()
    resolved = container.resolve(Consumer)
    assert cast(Any, resolved.list_value).label == "list"
    assert cast(Any, resolved.dict_value).label == "dict"
    assert container.has_component(PublicSerializer[list[int]])
    assert container.has_component(PublicSerializer[dict[str, int]])


def test_boundary_closed_use_and_private_patterns():
    def source(builder):
        builder.register_pattern(Serializer[T], factory=Serializer)

    class Consumer:
        def __init__(self, value: Serializer[int]):
            self.value = value

    def consumer_bundle(builder):
        builder.register(Consumer)

    for declare_use in (True, False):
        builder = ContainerBuilder()
        builder.create_boundary("source", exposes=(Expose(Serializer[int]),)).apply_bundle(source)
        builder.create_boundary(
            "consumer", exposes=(Expose(Consumer),), uses=(Use("source", Serializer[int]),) if declare_use else ()
        ).apply_bundle(consumer_bundle)
        if declare_use:
            assert isinstance(builder.build().resolve(Consumer).value, Serializer)
        else:
            with pytest.raises(ContainerBuildError):
                builder.build()


def test_overlay_patterns_and_anchored_parent_singletons():
    class Parent:
        def __init__(self, value: Serializer[int]):
            self.value = value

    builder = ContainerBuilder()
    builder.register_pattern(Serializer[T], factory=lambda: Serializer("parent"), lifespan="singleton")
    builder.register(Parent, lifespan="singleton")
    with builder.build() as container:
        overlay_builder = container.new_scope_builder()
        overlay_builder.register_pattern(Serializer[T], factory=lambda: Serializer("child"), lifespan="singleton")
        root = request(overlay_builder, Serializer[int])
        with overlay_builder.build() as overlay:
            assert overlay.resolve(root).value.label == "child"
            assert overlay.resolve(Parent).value.label == "parent"

        invalid = container.new_scope_builder()
        request(invalid, Serializer[str])
        with pytest.raises(ContainerBuildError) as error:
            invalid.build()
        assert "overlay-singleton" in error_codes(error)


def test_graph_explain_redaction_fingerprints_and_original_factory():
    def build(secret):
        builder = ContainerBuilder()
        builder.register(Serializer[int], factory=Serializer)
        builder.register_pattern(Serializer[T], factory=lambda: Serializer("general"))
        builder.register_pattern(Serializer[dict[str, T]], factory=Serializer)
        builder.register_pattern(Serializer[list[T]], factory=make_list_serializer)
        root = request(builder, Serializer[list[int]])
        return builder.build(build_args={"secret": secret}), root

    first, root = build("private-one")
    second, _ = build("private-two")
    assert first.graph.manifest().fingerprint == second.graph.manifest().fingerprint
    output = json.dumps(first.graph.manifest().to_dict())
    assert "private-one" not in output
    explanation = first.graph.explain(Serializer[list[int]])
    codes = {code for decision in explanation.rejected for code in decision.reason_codes}
    assert {"pattern-mismatch", "pattern-less-specific"} <= codes
    assert "selected-registration-pattern" in explanation.selected[0].reason_codes
    components = [component for component in first.components if component.service_type == Serializer[list[int]]]
    assert components[0].implementation is make_list_serializer
    assert components[0].generic_mapping[T] == list[int]
    assert first.resolve(root).value.child is not None


def test_entrypoint_marks_existing_pattern_request_without_granting_new_roots():
    builder = ContainerBuilder()
    builder.register_pattern(Serializer[T], factory=Serializer)
    builder.mark_entrypoint(Serializer[int])
    with pytest.raises(ContainerBuildError):
        builder.build()
    request(builder, Serializer[int])
    assert isinstance(builder.build().resolve(Serializer[int]), Serializer)


def test_more_specific_condition_rejection_does_not_fall_back():
    builder = ContainerBuilder()
    builder.register_pattern(Serializer[T], factory=Serializer)
    builder.register_pattern(Serializer[list[T]], factory=Serializer, when=lambda c: False)
    request(builder, Serializer[list[int]])
    with pytest.raises(ContainerBuildError):
        builder.build()


def test_unsupported_closed_annotation_is_rejected_even_at_variable_position():
    builder = ContainerBuilder()
    builder.register_pattern(Serializer[T], factory=Serializer)
    request(builder, Serializer[int | str])
    with pytest.raises(ContainerBuildError) as error:
        builder.build()
    assert "pattern-unsupported-form" in error_codes(error)


def test_unexported_private_template_is_diagnosed():
    def source(builder):
        builder.register_pattern(Serializer[T], factory=Serializer)

    builder = ContainerBuilder()
    builder.create_boundary("source").apply_bundle(source)
    request(builder, Serializer[int])
    with pytest.raises(ContainerBuildError) as error:
        builder.build()
    assert "boundary-private-component" in error_codes(error)


def test_decorators_wrap_pattern_specializations():
    class Wrapper(Serializer[T], Generic[T]):
        def __init__(self, child: Serializer[T]):
            super().__init__("decorated", child)

    builder = ContainerBuilder()
    builder.register_pattern(Serializer[T], factory=Serializer)
    builder.register_decorator(Serializer, Wrapper)
    root = request(builder, Serializer[list[int]])
    container = builder.build()
    assert container.resolve(root).value.label == "decorated"
    assert container.resolve(root).value.child.label == "leaf"


def test_pattern_lifetime_validation_rejects_scoped_dependency_below_singleton():
    builder = ContainerBuilder()
    builder.register(Serializer[int], factory=Serializer, lifespan="scoped")
    builder.register_pattern(Serializer[list[T]], factory=make_list_serializer, lifespan="singleton")
    request(builder, Provider[Serializer[list[int]]])
    with pytest.raises(ContainerBuildError) as error:
        builder.build()
    assert "captive-dependency" in error_codes(error)


def test_transient_resource_pattern_cleanup_is_promoted_to_parent_singleton():
    events = []

    @contextmanager
    def resource():
        yield Serializer()
        events.append("close")

    class Parent:
        def __init__(self, child: Serializer[int]):
            self.child = child

    builder = ContainerBuilder()
    builder.register_pattern(Serializer[T], factory=resource, lifespan="transient")
    builder.register(Parent, lifespan="singleton")
    with builder.build() as container:
        with container.new_scope() as scope:
            scope.resolve(Parent)
        assert not events
    assert events == ["close"]


def test_dictionary_factory_receives_value_binding_and_rejects_other_key_types():
    def dictionary(value: Serializer[T]) -> Serializer[dict[str, T]]:
        return Serializer("dict", value)

    builder = ContainerBuilder()
    builder.register(Serializer[int], factory=lambda: Serializer("int"))
    builder.register_pattern(Serializer[dict[str, T]], factory=dictionary)
    root = request(builder, Serializer[dict[str, int]])
    assert builder.build().resolve(root).value.child.label == "int"


def test_equal_alpha_renamed_patterns_keep_declaration_order():
    builder = ContainerBuilder()
    builder.register_pattern(Serializer[T], factory=lambda: Serializer("old"))
    builder.register_pattern(Serializer[U], factory=lambda: Serializer("new"))
    root = request(builder, list[Serializer[int]])
    assert [value.label for value in builder.build().resolve(root).value] == ["new", "old"]


def test_finite_shrinking_nesting_beyond_growth_budget():
    builder = ContainerBuilder()
    builder.register(Serializer[int], factory=Serializer)
    builder.register_pattern(Serializer[list[T]], factory=make_list_serializer)
    annotation = int
    for _ in range(20):
        annotation = list[annotation]
    root = request(builder, Serializer[annotation])
    value = builder.build().resolve(root).value
    for _ in range(20):
        value = value.child
    assert value.label == "leaf"


def test_mutual_pattern_growth_is_bounded():
    class Other(Generic[T]):
        pass

    def left(child: Other[list[T]]) -> Serializer[T]:
        return Serializer(child=child)

    def right(child: Serializer[list[T]]) -> Other[T]:
        return Other()

    builder = ContainerBuilder()
    builder.register_pattern(Serializer[T], factory=left)
    builder.register_pattern(Other[T], factory=right)
    request(builder, Serializer[int])
    with pytest.raises(ContainerBuildError) as error:
        builder.build()
    assert "pattern-non-terminating-expansion" in error_codes(error)


@pytest.mark.skipif(sys.version_info < (3, 12), reason="native type syntax requires Python 3.12")
def test_native_alias_pattern():
    namespace = {"Serializer": Serializer}
    exec("type Native[T] = Serializer[list[T]]", namespace)  # noqa: S102
    # An unannotated result allows the alias's own identity-bound variable;
    # this deliberately does not merge it with the module-level T.
    builder = ContainerBuilder()
    builder.register_pattern(namespace["Native"], factory=Serializer)
    root = request(builder, Serializer[list[int]])
    assert isinstance(builder.build().resolve(root).value, Serializer)


def test_unused_factory_binding_error_is_diagnosed_and_template_id_is_patchable():
    def unbound(value: Serializer[U]):
        return value

    builder = ContainerBuilder()
    builder.register_pattern(Serializer[T], factory=unbound)
    with pytest.raises(ContainerBuildError) as error:
        builder.build()
    assert "pattern-incompatible-binding" in error_codes(error)

    builder = ContainerBuilder()
    component_id = builder.register_pattern(Serializer[T], factory=Serializer)
    builder.patch_component(Serializer[T], component_id, arguments={"label": "patched"})
    root = request(builder, Serializer[int])
    assert builder.build().resolve(root).value.label == "patched"


def test_repeated_bindings_and_factory_result_use_canonical_origins():
    def factory() -> Serializer[tuple[T, T]]:
        return Serializer()

    builder = ContainerBuilder()
    builder.register_pattern(Serializer[tuple[T, T]], factory=factory)
    root = request(builder, Serializer[tuple[TypingList[int], list[int]]])
    assert isinstance(builder.build().resolve(root).value, Serializer)


def test_custom_bound_errors_are_redacted():
    class RaisingMeta(type):
        def __subclasscheck__(cls, subclass):
            raise ValueError("private-bound-secret")

    class Bound(metaclass=RaisingMeta):
        pass

    variable = TypeVar("variable", bound=Bound)
    builder = ContainerBuilder()
    builder.register_pattern(Serializer[variable], factory=Serializer)
    request(builder, Serializer[int])
    with pytest.raises(ContainerBuildError) as error:
        builder.build()
    assert "pattern-unsupported-form" in error_codes(error)
    assert "private-bound-secret" not in str(error.value)
    assert error.value.report is not None
    assert "private-bound-secret" not in error.value.report.to_json()


@pytest.mark.parametrize("template", [list[T], tuple[T], Provider[T], AsyncProvider[T]])
def test_synthetic_outer_patterns_are_explicitly_rejected(template):
    builder = ContainerBuilder()
    builder.register_pattern(template, factory=Serializer)
    with pytest.raises(ContainerBuildError) as error:
        builder.build()
    assert "pattern-unsupported-form" in error_codes(error)


def test_growth_through_many_distinct_templates_is_bounded():
    generic_base: Any = Generic[T]
    services: list[Any] = [types.new_class(f"Stage{index}", (generic_base,)) for index in range(40)]
    builder = ContainerBuilder()
    for index, service in enumerate(services):

        def factory(child):
            return child

        factory.__annotations__ = {"child": services[(index + 1) % len(services)][list[T]]}
        builder.register_pattern(service[T], factory=factory)
    request(builder, services[0][int])
    with pytest.raises(ContainerBuildError) as error:
        builder.build()
    assert "pattern-non-terminating-expansion" in error_codes(error)
