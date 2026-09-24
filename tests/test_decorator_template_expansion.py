"""M04 internal expansion tests; generated target activation is assigned to M05."""

from dataclasses import FrozenInstanceError, replace
from typing import Generic, TypeVar
from uuid import UUID, uuid5

import pytest
from typing_extensions import TypeAliasType

from clean_ioc import (
    Boundary,
    ContainerBuilder,
    ContainerBuildError,
    DerivedServices,
    Expose,
    ServiceGroup,
    Tag,
    Use,
    select,
)
from clean_ioc import component_filters as cf
from clean_ioc._decorator_templates import DecoratorTemplate, RegistrationInfo
from clean_ioc.container import (
    _Blueprint,
    _check_template_boundary_visibility,
    _Compiler,
    _normalize_blueprint_aliases,
)


class Target:
    pass


class Decorator:
    def __init__(self, inner: Target):
        raise AssertionError("Expansion must never activate decorators")


def specification(source):
    return DecoratorTemplate(DerivedServices(Target), Decorator, arguments={"source": select(cf.with_id(source.id))})


def snapshot(builder):
    return _normalize_blueprint_aliases(_Blueprint((builder._layer(),), tuple(builder._boundaries)))


def test_zero_sources_and_no_public_unusable_entrypoints():
    builder = ContainerBuilder()
    template_id = builder._register_decorator_template(for_each=Target, template=specification)
    result = builder._expand_decorator_templates()
    assert result.candidates == result.selections == ()
    assert result.blueprint.layers[0].decorator_templates[0].id == template_id
    assert not hasattr(builder, "register_decorator_template")
    assert not hasattr(builder, "patch_decorator_template")
    assert not hasattr(builder, "remove_decorator_template")


def test_distinct_same_class_sources_deterministic_ids_shared_order_and_immutable_evidence():
    class Source:
        def __init__(self):
            raise AssertionError("Source must not activate")

    builder = ContainerBuilder()
    first = builder.register(Source, name="same")
    second = builder.register(Source, name="same")
    seen = []
    builder.register_decorator(Target, Decorator)
    template_id = builder._register_decorator_template(
        for_each=Source, template=lambda source: (seen.append(source.id), specification(source))[1]
    )
    builder.register_decorator(Target, Decorator)
    other_id = builder._register_decorator_template(for_each=Source, template=specification)
    original = tuple(builder._decorator_templates)
    a, b = builder._expand_decorator_templates(), builder._expand_decorator_templates()
    assert seen == [first, second, first, second]  # Declaration order, independent of lookup precedence.
    assert len(a.candidates) == 4
    assert [item.id for item in a.candidates] == [item.id for item in b.candidates]
    assert [item.order for item in a.candidates] == [1, 1, 3, 3]
    assert [item.source_order for item in a.candidates] == [0, 1, 0, 1]
    assert [item.order for item in a.blueprint.layers[0].decorators] == [0, 2]
    assert tuple(builder._decorator_templates) == original
    assert len(a.blueprint.layers[0].decorators) == 2
    for candidate in a.candidates:
        assert candidate.id == str(uuid5(UUID(candidate.declaration.id), candidate.source.id))
        assert candidate.declaration.id in (template_id, other_id)
        assert candidate.source_owner_token == candidate.declaration_owner_token == builder._owner_token
        assert candidate.source_area is candidate.declaration_area is None
        with pytest.raises(FrozenInstanceError):
            candidate.source_order = 99  # ty: ignore[invalid-assignment]
    assert [item.generated_id for item in a.selections] == [item.id for item in a.candidates]
    with pytest.raises(FrozenInstanceError):
        a.selections[0].selected = False  # ty: ignore[invalid-assignment]


def test_specification_and_source_views_defensively_copy_collections():
    arguments = {"value": 1}
    tags = [Tag("a", "one")]
    spec = DecoratorTemplate(ServiceGroup("targets", service_type=Target), Decorator, arguments=arguments, tags=tags)
    info = RegistrationInfo("source", Target, Target, tags=tuple(tags))
    arguments["value"] = 2
    tags.append(Tag("b"))
    assert spec.arguments == {"value": 1}
    assert spec.tags == info.tags == (Tag("a", "one"),)
    with pytest.raises(TypeError):
        spec.arguments["value"] = 3  # ty: ignore[invalid-assignment]
    with pytest.raises(FrozenInstanceError):
        info.name = "new"  # ty: ignore[invalid-assignment]
    with pytest.raises(TypeError, match="ServiceGroup or DerivedServices"):
        DecoratorTemplate(Target, Decorator)  # ty: ignore[invalid-argument-type]


def test_real_recursive_source_filters_conditions_build_args_and_no_activation():
    class Marker:
        pass

    class Resource:
        def __init__(self):
            raise AssertionError("No resource activation")

    class Source:
        def __init__(self, resource: Resource):
            raise AssertionError("No source activation")

    class ResourceDecorator:
        def __init__(self, inner: Resource, marker: Marker):
            raise AssertionError("No decorator activation")

    builder = ContainerBuilder()
    chosen_resource = builder.register(
        Resource,
        tags=[Tag("resource", "chosen")],
        lifespan="singleton",
        when=cf.parent(cf.implementation_type_is(Source)),
    )
    builder.register(Marker)
    builder.register_decorator(Resource, ResourceDecorator, decorated_arg="inner")
    source_id = builder.register(
        Source,
        name="chosen",
        tags=[Tag("family", "store")],
        lifespan="singleton",
        when=cf.parent(cf.implementation_type_is(Decorator)),
    )
    rejected = builder.register(Source, name="other")
    calls = []

    def source_filter(component):
        calls.append(component.id)
        assert component.parent is None
        assert component.argument is None
        assert component.dependencies[0].id == chosen_resource
        assert component.build_args["mode"] == "preview"
        assert component._graph._records is not None
        return (
            cf.with_name("chosen")
            & cf.has_tag("family", "store")
            & cf.has_descendant(cf.has_tag("resource", "chosen"))
            & ~cf.has_descendant(cf.implementation_type_is(Marker))
            & ~cf.parent(cf.all_components)
            & (lambda item: item.lifespan == "singleton")
        )(component)

    builder._register_decorator_template(for_each=Source, source_filter=source_filter, template=specification)
    result = builder._expand_decorator_templates(build_args={"mode": "preview"})
    assert calls == [source_id, rejected]
    assert [item.source.id for item in result.candidates] == [source_id]
    assert [item.selected for item in result.selections] == [True, False]
    assert result.selections[1].generated_id is None
    assert result.selections[1].component.decorators == ()
    assert result.selections[1].component.dependencies[0].decorators == ()


def test_generic_implementation_aliases_generated_classes_and_same_name_variable_identity():
    SourceT = TypeVar("T")  # ty: ignore[mismatched-type-name]
    OtherT = TypeVar("T")  # ty: ignore[mismatched-type-name]

    class Source:
        pass

    class Backend(Source, Generic[SourceT]):
        pass

    class Other(Generic[OtherT]):
        pass

    class Generated(Backend[str], Other[bytes]):
        pass

    class Grandchild(Generated):
        pass

    builder = ContainerBuilder()
    direct = builder.register(Source, Backend[int], name="one")
    repeated = builder.register(Source, Backend[int], name="two")
    generated = builder.register(Source, Grandchild)
    open_impl = builder.register(Source, Backend)
    builder._register_decorator_template(for_each=Source, template=specification)
    by_id = {item.source.id: item.source for item in builder._expand_decorator_templates().candidates}
    assert by_id[direct].implementation_type == by_id[repeated].implementation_type == Backend[int]
    assert by_id[direct].implementation_bindings(Backend) == {SourceT: int}
    assert by_id[generated].implementation_type is Grandchild
    assert by_id[generated].implementation_bindings(Backend) == {SourceT: str}
    assert by_id[generated].implementation_bindings(Other) == {OtherT: bytes}
    assert by_id[open_impl].implementation_bindings(Backend) == {SourceT: SourceT}
    assert by_id[direct].implementation_bindings(Other) is None
    bindings = by_id[generated].implementation_bindings(Backend)
    with pytest.raises(TypeError):
        bindings[SourceT] = float  # ty: ignore[invalid-assignment]


def test_factories_and_instances_preserve_only_static_evidence():
    T = TypeVar("T")

    class Source:
        pass

    class Backend(Source, Generic[T]):
        pass

    def broad() -> Source:
        raise AssertionError("No broad factory activation")

    def concrete() -> Backend[int]:
        raise AssertionError("No concrete factory activation")

    def unknown():
        raise AssertionError("No untyped factory activation")

    builder = ContainerBuilder()
    broad_id = builder.register(Source, factory=broad)
    concrete_id = builder.register(Source, factory=concrete)
    unknown_id = builder.register(Source, factory=unknown)
    instance_id = builder.register(Source, instance=Backend[str]())
    builder._register_decorator_template(for_each=Source, template=specification)
    infos = {item.source.id: item.source for item in builder._expand_decorator_templates().candidates}
    assert infos[broad_id].implementation_type is Source
    assert infos[broad_id].implementation_bindings(Backend) is None
    assert infos[concrete_id].implementation_type == Backend[int]
    assert infos[concrete_id].implementation_bindings(Backend) == {T: int}
    assert infos[unknown_id].implementation_type is None
    assert infos[unknown_id].implementation_bindings(Backend) is None
    assert infos[instance_id].implementation_type == Backend[str]
    assert infos[instance_id].implementation_bindings(Backend) == {T: str}


def test_exact_canonical_closed_service_key_and_no_implementation_or_open_enumeration():
    T = TypeVar("T")

    class Source(Generic[T]):
        pass

    Alias = TypeAliasType("Alias", Source[int])  # noqa: N806
    builder = ContainerBuilder()
    expected = builder.register(Alias)
    builder.register(Source[str])
    builder.register(Source)
    builder._register_decorator_template(for_each=Alias, template=specification)
    result = builder._expand_decorator_templates()
    assert [item.source.id for item in result.candidates] == [expected]
    assert result.candidates[0].source.service_type == Source[int]
    template_id = builder._register_decorator_template(for_each=Source, template=specification)
    with pytest.raises(ContainerBuildError) as caught:
        builder._expand_decorator_templates()
    assert caught.value.code == "template-source-open-generic"
    builder._remove_decorator_template(template_id)

    class Implementation:
        pass

    other = ContainerBuilder()
    other.register(Target, Implementation)
    other._register_decorator_template(for_each=Implementation, template=specification)
    assert other._expand_decorator_templates().candidates == ()


def test_discovery_is_complete_and_source_identity_stable_across_expansion_attempts():
    class Source:
        pass

    class First(Source):
        pass

    builder = ContainerBuilder()
    builder._register_decorator_template(for_each=Source, template=specification)
    explicit = builder.register(Source, First)
    builder.register_subclasses(Source)

    class Late(Source):
        pass

    a, b = builder._expand_decorator_templates(), builder._expand_decorator_templates()
    assert [item.id for item in a.candidates] == [item.id for item in b.candidates]
    assert len(a.candidates) == 3
    assert a.candidates[0].source.id == explicit
    assert [item.source.implementation_type for item in a.candidates] == [First, First, Late]


def test_failure_discards_partial_expansion_and_patch_remove_are_transactional():
    builder = ContainerBuilder()
    first = builder.register(Target)
    second = builder.register(Target)
    calls = []

    def factory(source):
        calls.append(source.id)
        if source.id == second:
            raise ValueError("broken callback")
        return specification(source)

    template_id = builder._register_decorator_template(for_each=Target, template=factory)
    for _ in range(2):
        with pytest.raises(ContainerBuildError) as caught:
            builder._expand_decorator_templates()
        assert caught.value.code == "template-expansion"
        assert caught.value.path[:2] == (template_id, second)
        assert isinstance(caught.value.__cause__, ValueError)
    assert calls == [first, second, first, second]
    assert builder._decorators == []
    assert len(builder._decorator_templates) == 1
    original = builder._decorator_templates[0]
    with pytest.raises(TypeError):
        builder._patch_decorator_template(template_id, template=3)
    assert builder._decorator_templates[0] is original
    builder._patch_decorator_template(template_id, template=specification)
    repaired = builder._expand_decorator_templates()
    assert len(repaired.candidates) == 2
    assert all(item.declaration.id == template_id and item.order == original.order for item in repaired.candidates)
    builder._remove_decorator_template(template_id)
    assert builder._expand_decorator_templates().candidates == ()
    with pytest.raises(KeyError):
        builder._remove_decorator_template(template_id)
    with pytest.raises(KeyError):
        builder._patch_decorator_template(template_id, template=specification)


@pytest.mark.parametrize("operation", ["register", "build", "preview", "expand", "patch", "remove"])
@pytest.mark.parametrize("phase", ["filter", "factory"])
def test_callbacks_cannot_mutate_build_preview_or_reenter_and_guard_recovers(operation, phase):
    builder = ContainerBuilder()
    builder.register(Target)
    template_id = ""

    def callback(_):
        if operation == "register":
            builder.register(Target)
        elif operation == "build":
            builder.build()
        elif operation == "preview":
            builder.has_component(Target)
        elif operation == "expand":
            builder._expand_decorator_templates()
        elif operation == "patch":
            builder._patch_decorator_template(template_id, template=specification)
        else:
            builder._remove_decorator_template(template_id)
        raise AssertionError("Reentry should fail")

    template_id = builder._register_decorator_template(
        for_each=Target,
        source_filter=callback if phase == "filter" else cf.all_components,
        template=callback if phase == "factory" else specification,
    )
    with pytest.raises(ContainerBuildError) as caught:
        builder._expand_decorator_templates()
    assert caught.value.code == "template-expansion-reentry"
    assert len(builder._composition._registry.get_registrations(Target)) == 1
    builder._patch_decorator_template(template_id, template=specification, source_filter=cf.all_components)
    assert len(builder._expand_decorator_templates().candidates) == 1


def test_visible_sources_from_root_and_boundary_declaration_areas():
    class Source:
        pass

    builder = ContainerBuilder()
    root_id = builder.register(Source, name="root")
    ids = {}

    def provider(private):
        ids["exposed"] = private.register(Source, name="public")
        ids["hidden"] = private.register(Source, name="private")
        ids["provider-template"] = private._register_decorator_template(for_each=Source, template=specification)

    def consumer(private):
        ids["consumer-template"] = private._register_decorator_template(for_each=Source, template=specification)

    builder.install_boundary(Boundary("provider", provider, exposes=(Expose(Source, filter=cf.with_name("public")),)))
    builder.install_boundary(
        Boundary("consumer", consumer, uses=(Use("provider", Source, filter=cf.with_name("public")),))
    )
    root_template = builder._register_decorator_template(for_each=Source, template=specification)
    expansion = builder._expand_decorator_templates()
    by_template = {}
    for item in expansion.candidates:
        by_template.setdefault(item.declaration.id, set()).add(item.source.id)
    assert by_template[root_template] == {root_id, ids["exposed"]}
    assert by_template[ids["consumer-template"]] == {ids["exposed"]}
    assert by_template[ids["provider-template"]] == {ids["exposed"], ids["hidden"]}
    imported = next(item for item in expansion.candidates if item.declaration.id == ids["consumer-template"])
    assert imported.declaration_area == "consumer"
    assert imported.source_area == "provider"
    assert imported.source.service_type is Source


def test_retained_boundary_builder_also_obeys_expansion_guard():
    builder = ContainerBuilder()
    retained = []

    def bundle(private):
        retained.append(private)
        private.register(Target)
        private._register_decorator_template(for_each=Target, template=lambda _: private.register(Target))

    builder.install_boundary(Boundary("private", bundle))
    with pytest.raises(ContainerBuildError) as caught:
        builder._expand_decorator_templates()
    assert caught.value.code == "template-expansion-reentry"
    assert len(retained[0]._composition._registry.get_registrations(Target)) == 1


def test_source_to_target_edge_is_legal_and_real_source_cycle_is_stable():
    class Source:
        def __init__(self, target: Target):
            raise AssertionError("No activation")

    builder = ContainerBuilder()
    builder.register(Target)
    builder.register(Source)
    builder._register_decorator_template(for_each=Source, template=specification)
    assert len(builder._expand_decorator_templates().candidates) == 1

    class Recursive:
        pass

    def recursive(value: Recursive) -> Recursive:
        raise AssertionError("No activation")

    cyclic = ContainerBuilder()
    source_id = cyclic.register(Recursive, factory=recursive)
    template_id = cyclic._register_decorator_template(for_each=Recursive, template=specification)
    errors = []
    for _ in range(2):
        with pytest.raises(ContainerBuildError) as caught:
            cyclic._expand_decorator_templates()
        errors.append(caught.value)
    assert errors[0].code == errors[1].code == "circular-dependency"
    assert errors[0].path == errors[1].path
    assert errors[0].path[:2] == (template_id, source_id)


def test_overlay_expansion_preserves_anchored_source_resources_and_original_arguments():
    class Resource:
        pass

    class Source:
        def __init__(self, resource: Resource):
            self.resource = resource

    builder = ContainerBuilder()
    parent_resource = builder.register(Resource, lifespan="singleton", name="parent")
    source_id = builder.register(
        Source, lifespan="singleton", arguments={"resource": select(cf.with_id(parent_resource))}
    )
    parent = builder.build()
    existing = parent.resolve(Source)
    overlay = parent.new_scope_builder()
    overlay.register(Resource, lifespan="singleton", name="overlay")
    overlay._register_decorator_template(for_each=Source, template=specification)
    expanded = overlay._expand_decorator_templates()
    assert expanded.candidates[0].source.id == source_id
    assert expanded.candidates[0].source_owner_token == builder._owner_token
    assert expanded.selections[0].component.dependencies[0].id == parent_resource
    assert overlay.build().resolve(Source) is existing


def test_visibility_consistency_primitive_stable_changed_and_newly_invalid():
    class Source:
        pass

    class Marker:
        pass

    class Added:
        def __init__(self, inner: Source, marker: Marker):
            pass

    def private(builder):
        builder.register(Source, name="one")
        builder.register(Source, name="two")
        builder.register(Marker)

    for ambiguous in (False, True):

        def selection(component):
            has_marker = cf.has_descendant(cf.implementation_type_is(Marker))(component)
            return (component.name == "one" or has_marker) if ambiguous else ((component.name == "one") != has_marker)

        builder = ContainerBuilder()
        builder.install_boundary(Boundary("provider", private, exposes=(Expose(Source, filter=selection),)))
        builder._register_decorator_template(for_each=Source, template=specification)
        initial = builder._expand_decorator_templates()
        normalized = snapshot(builder)
        stable = _check_template_boundary_visibility(initial.blueprint, normalized, candidates=initial.candidates)
        assert stable.boundaries[0].resolved_exposes == initial.blueprint.boundaries[0].resolved_exposes
        synthetic = ContainerBuilder()
        synthetic.register_decorator(Source, Added, decorated_arg="inner")
        expanded = replace(
            normalized,
            boundaries=(
                replace(
                    normalized.boundaries[0],
                    layer=replace(normalized.boundaries[0].layer, decorators=synthetic._layer().decorators),
                ),
            ),
        )
        with pytest.raises(ContainerBuildError) as caught:
            _check_template_boundary_visibility(initial.blueprint, expanded, candidates=initial.candidates)
        assert caught.value.code == "template-visibility-cycle"
        assert "provider" in caught.value.path
        assert f"{initial.candidates[0].declaration.id}:{initial.candidates[0].source.id}" in caught.value.path
        if ambiguous:
            assert isinstance(caught.value.__cause__, ContainerBuildError)
            assert caught.value.__cause__.code == "boundary-expose-ambiguous"
        else:
            assert caught.value.__cause__ is None


def test_source_condition_still_enforced_by_exact_generated_equivalent_dependency():
    class Source:
        pass

    class Added:
        def __init__(self, inner: Target, source: Source):
            self.source = source

    builder = ContainerBuilder()
    selected = builder.register(Source, when=cf.parent(cf.implementation_type_is(Target)))
    builder.register(Source)  # Must not substitute this eligible source.
    builder.register(Target)
    builder._register_decorator_template(for_each=Source, source_filter=cf.with_id(selected), template=specification)
    expansion = builder._expand_decorator_templates()
    assert expansion.candidates[0].source.id == selected
    synthetic = ContainerBuilder()
    synthetic.register_decorator(
        Target, Added, decorated_arg="inner", arguments=expansion.candidates[0].specification.arguments
    )
    layer = replace(expansion.blueprint.layers[0], decorators=synthetic._layer().decorators)
    with pytest.raises(ContainerBuildError):
        _Compiler(replace(expansion.blueprint, layers=(layer,))).compile()


def test_instance_family_filter_uses_static_class_without_changing_ordinary_components():
    class Source:
        pass

    class Backend(Source):
        pass

    instance = Backend()
    builder = ContainerBuilder()
    source_id = builder.register(Source, instance=instance)
    template_id = builder._register_decorator_template(
        for_each=Source,
        source_filter=cf.implementation_type_is(Backend),
        template=specification,
    )
    expansion = builder._expand_decorator_templates()
    assert expansion.candidates[0].source.id == source_id
    assert expansion.selections[0].component.implementation_type is Backend
    builder._remove_decorator_template(template_id)
    runtime = builder.build()
    assert (
        next(root.component for root in runtime.graph.roots if root.component.id == source_id).implementation_type
        is Source
    )
    assert runtime.resolve(Source) is instance


def test_generic_discovery_enumerates_only_exact_closed_source_key():
    T = TypeVar("T")

    class Source(Generic[T]):
        pass

    class One(Source[int]):
        pass

    builder = ContainerBuilder()
    builder._register_decorator_template(for_each=Source[int], template=specification)
    builder.register_generic_subclasses(Source)

    class Late(Source[int]):
        pass

    class Other(Source[str]):
        pass

    expansion = builder._expand_decorator_templates()
    assert [item.source.implementation_type for item in expansion.candidates] == [One, Late]
    assert all(item.source.service_type == Source[int] for item in expansion.candidates)
    assert [item.source_order for item in expansion.candidates] == [0, 1]


def test_synchronous_factory_contract_and_invalid_result_retry():
    builder = ContainerBuilder()
    builder.register(Target)

    async def asynchronous(source):
        return specification(source)

    with pytest.raises(TypeError, match="synchronous"):
        builder._register_decorator_template(
            for_each=Target,
            template=asynchronous,  # ty: ignore[invalid-argument-type]
        )
    template_id = builder._register_decorator_template(
        for_each=Target,
        template=lambda _: None,  # ty: ignore[invalid-argument-type]
    )
    with pytest.raises(ContainerBuildError) as caught:
        builder._expand_decorator_templates()
    assert isinstance(caught.value.__cause__, TypeError)
    assert builder._decorators == []
    builder._patch_decorator_template(template_id, template=specification)
    assert len(builder._expand_decorator_templates().candidates) == 1


@pytest.mark.parametrize("ambiguous", [False, True])
def test_use_visibility_recheck_is_one_shot_and_never_replays_template_callbacks(ambiguous):
    class Source:
        pass

    class Marker:
        pass

    class Added:
        def __init__(self, inner: Source, marker: Marker):
            pass

    calls = []
    predicate_calls = []

    def selection(component):
        predicate_calls.append(component.id)
        decorated = cf.has_descendant(cf.implementation_type_is(Marker))(component)
        return (component.name == "one" or decorated) if ambiguous else ((component.name == "one") != decorated)

    builder = ContainerBuilder()
    builder.register(Source, name="one")
    builder.register(Source, name="two")
    builder.register(Marker)
    builder.install_boundary(Boundary("consumer", lambda _: None, uses=(Use(None, Source, filter=selection),)))
    builder._register_decorator_template(
        for_each=Source, template=lambda source: (calls.append(source.id), specification(source))[1]
    )
    expansion = builder._expand_decorator_templates()
    assert len(calls) == len(predicate_calls) == 2
    normalized = snapshot(builder)
    synthetic = ContainerBuilder()
    synthetic.register_decorator(Source, Added, decorated_arg="inner")
    expanded = replace(normalized, layers=(replace(normalized.layers[0], decorators=synthetic._layer().decorators),))
    with pytest.raises(ContainerBuildError) as caught:
        _check_template_boundary_visibility(expansion.blueprint, expanded, candidates=expansion.candidates)
    assert caught.value.code == "template-visibility-cycle"
    assert len(calls) == 2
    assert len(predicate_calls) == 4  # One initial preparation, exactly one recheck.
    if ambiguous:
        assert isinstance(caught.value.__cause__, ContainerBuildError)
        assert caught.value.__cause__.code == "boundary-use-ambiguous"


def test_failed_source_dependency_does_not_call_filter_or_factory_or_leave_guard_active():
    class Missing:
        pass

    class Source:
        def __init__(self, missing: Missing):
            pass

    calls = []
    builder = ContainerBuilder()
    builder.register(Source)
    builder._register_decorator_template(
        for_each=Source,
        source_filter=lambda _: calls.append("filter") or True,
        template=lambda source: (calls.append("factory"), specification(source))[1],
    )
    with pytest.raises(ContainerBuildError):
        builder._expand_decorator_templates()
    assert calls == []
    builder.register(Missing)
    assert len(builder._expand_decorator_templates().candidates) == 1
    assert calls == ["filter", "factory"]


def test_internal_overlay_edit_shadows_declaration_and_reexpands_new_sources():
    builder = ContainerBuilder()
    parent_source = builder.register(Target)
    inherited_id = builder._register_decorator_template(for_each=Target, template=specification)
    retained_id = builder._register_decorator_template(for_each=Target, template=specification)
    # M04 stores original declarations in plans; this is not an activation test.
    parent = builder.build()
    overlay = parent.new_scope_builder()
    local_source = overlay.register(Target)
    overlay._patch_decorator_template(inherited_id, source_filter=cf.with_id(local_source))
    expansion = overlay._expand_decorator_templates()
    assert [item.source.id for item in expansion.candidates if item.declaration.id == inherited_id] == [local_source]
    assert [item.source.id for item in expansion.candidates if item.declaration.id == retained_id] == [
        local_source,
        parent_source,
    ]
    assert parent._plan.blueprint.layers[0].decorator_templates[0].source_filter is cf.all_components
    overlay._remove_decorator_template(inherited_id)
    assert {item.declaration.id for item in overlay._expand_decorator_templates().candidates} == {retained_id}
