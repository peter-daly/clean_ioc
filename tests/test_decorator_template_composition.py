from collections.abc import Iterator
from contextlib import contextmanager
from typing import Generic, TypeVar

import pytest

from clean_ioc import (
    BoundaryAlias,
    ContainerBuilder,
    ContainerBuildError,
    DecoratorTemplate,
    DerivedServices,
    Expose,
    RuntimeOwnerKind,
    ServiceGroup,
    Use,
    select,
)
from clean_ioc import component_filters as cf


class Source:
    pass


class OtherSource(Source):
    pass


class Target:
    pass


class NewTarget(Target):
    pass


class Wrapper(Target):
    def __init__(self, inner: Target, source: Source, label: str = "base"):
        self.inner, self.source, self.label = inner, source, label


def unwrap(value):
    layers = []
    while isinstance(value, Wrapper):
        layers.append((value.label, value.source))
        value = value.inner
    return layers, value


def template_for(services, label="base", calls=None):
    def template(source):
        if calls is not None:
            calls.append(source.id)
        return DecoratorTemplate(
            services,
            Wrapper,
            arguments={"source": select(cf.with_id(source.id)), "label": label},
        )

    return template


@pytest.mark.parametrize("derived", [False, True])
def test_inherited_templates_expand_new_sources_targets_and_nested_plans_with_preview(derived):
    group = ServiceGroup("targets", service_type=Target)
    services = DerivedServices(Target) if derived else group
    calls, validations = [], []
    builder = ContainerBuilder()
    first, second, third = Source(), Source(), Source()
    builder.register(Source, instance=first, name="first")
    original_id = builder.register(Target, groups=[group])
    template_id = builder.register_decorator_template(for_each=Source, template=template_for(services, calls=calls))

    def validate(_):
        validations.append(True)
        return ()

    builder.add_validation_rule(validate)
    with builder.build() as root:
        assert unwrap(root.resolve(Target))[0] == [("base", first)]
        overlay = root.new_scope_builder()
        overlay.register(Source, instance=second, name="second")
        added_id = overlay.register(NewTarget, groups=[group])
        assert overlay.get_component_ids(Target, filter=lambda c: len(c.decorators) == 2) == [original_id]
        assert overlay.get_component_id(NewTarget, filter=lambda c: len(c.decorators) == 2) == added_id
        assert validations == [True]
        with overlay.build() as child:
            for service in (Target, NewTarget):
                assert unwrap(child.resolve(service))[0] == [("base", second), ("base", first)]
            nested = child.new_scope_builder()
            nested.register(Source, instance=third, name="third")
            assert nested.has_component(NewTarget, filter=lambda c: len(c.decorators) == 3)
            with nested.build() as grandchild:
                assert unwrap(grandchild.resolve(NewTarget))[0] == [("base", third), ("base", second), ("base", first)]
                candidates = grandchild._plan.blueprint.generated_decorators
                assert len(candidates) == len({c.id for c in candidates}) == 3
                assert {c.declaration.id for c in candidates} == {template_id}
                assert sum(len(layer.decorator_templates) for layer in grandchild._plan.blueprint.layers) == 1
                callback_count = len(calls)
                with grandchild.new_scope() as plain:
                    assert unwrap(plain.resolve(NewTarget))[0] == unwrap(grandchild.resolve(NewTarget))[0]
                    _ = plain.graph.ownership_report()
                assert len(calls) == callback_count
        assert validations == [True, True, True]
        assert unwrap(root.resolve(Target))[0] == [("base", first)]


@pytest.mark.parametrize("membership", [False, True])
def test_named_override_has_only_its_explicit_membership(membership):
    group = ServiceGroup("targets", service_type=Target)
    source = Source()
    builder = ContainerBuilder()
    builder.register(Source, instance=source)
    parent_core, override_core = Target(), NewTarget()
    original = builder.register(Target, instance=parent_core, name="selected", groups=[group])
    builder.register_decorator_template(for_each=Source, template=template_for(group))
    with builder.build() as root:
        overlay = root.new_scope_builder()
        override = overlay.register(
            Target, instance=override_core, name="selected", groups=[group] if membership else []
        )
        with overlay.build() as child:
            layers, core = unwrap(child.resolve(Target, filter=cf.with_name("selected")))
            assert core is override_core
            assert layers == ([("base", source)] if membership else [])
            assert unwrap(child.resolve(Target, filter=cf.with_id(original)))[1] is parent_core
            assert child._plan.blueprint.layers[0].service_groups.get(override, frozenset()) == (
                frozenset([group]) if membership else frozenset()
            )


def test_overlay_patch_remove_and_repatch_preserve_ids_ordinals_and_other_family():
    builder = ContainerBuilder()
    first, second = Source(), OtherSource()
    builder.register(Source, instance=first, name="first")
    builder.register(Source, instance=second, name="second")
    builder.register(Target)
    first_id = builder.register_decorator_template(
        for_each=Source,
        source_filter=cf.implementation_type_is(Source),
        template=template_for(DerivedServices(Target), "A"),
    )
    second_id = builder.register_decorator_template(
        for_each=Source,
        source_filter=cf.implementation_type_is(OtherSource),
        template=template_for(DerivedServices(Target), "B"),
    )
    with builder.build() as root:
        originals = {d.id: d for d in root._plan.blueprint.layers[0].decorator_templates}
        overlay = root.new_scope_builder()
        overlay.patch_decorator_template(first_id, template=template_for(DerivedServices(Target), "patched"))
        with overlay.build() as child:
            assert unwrap(child.resolve(Target))[0] == [("B", second), ("patched", first)]
            patched = child._plan.blueprint.layers[0].decorator_templates[0]
            assert (patched.id, patched.order) == (first_id, originals[first_id].order)
            assert {c.id for c in child._plan.blueprint.generated_decorators} == {
                c.id for c in root._plan.blueprint.generated_decorators
            }
            nested = child.new_scope_builder()
            nested.remove_decorator_template(first_id)
            with pytest.raises(KeyError):
                nested.patch_decorator_template(first_id, source_filter=cf.all_components)
            with pytest.raises(KeyError):
                nested.remove_decorator_template(first_id)
            with nested.build() as grandchild:
                assert unwrap(grandchild.resolve(Target))[0] == [("B", second)]
                assert {c.declaration.id for c in grandchild._plan.blueprint.generated_decorators} == {second_id}
                further = grandchild.new_scope_builder()
                with pytest.raises(KeyError):
                    further.patch_decorator_template(first_id)
                with further.build() as final:
                    assert unwrap(final.resolve(Target))[0] == [("B", second)]
        assert unwrap(root.resolve(Target))[0] == [("A", first), ("B", second)]


@pytest.mark.parametrize("local_kind", ["template", "ordinary"])
def test_patched_inherited_ordinal_collision_keeps_template_sources_together(local_kind):
    builder = ContainerBuilder()
    first, second, ordinary = Source(), Source(), Source()
    builder.register(Source, instance=first, name="one")
    builder.register(Source, instance=second, name="two")
    builder.register(Target)
    inherited = builder.register_decorator_template(
        for_each=Source, template=template_for(DerivedServices(Target), "B")
    )
    with builder.build() as root:
        overlay = root.new_scope_builder()
        if local_kind == "template":
            overlay.register_decorator_template(for_each=Source, template=template_for(DerivedServices(Target), "A"))
        else:
            overlay.register_decorator(Target, Wrapper, arguments={"source": ordinary, "label": "A"})
        overlay.patch_decorator_template(inherited, template=template_for(DerivedServices(Target), "B2"))
        # Replacing an existing local shadow must not change its traversal tie-break.
        overlay.patch_decorator_template(inherited, template=template_for(DerivedServices(Target), "B3"))
        with overlay.build() as child:
            expected = [("B3", first), ("B3", second)]
            expected += [("A", first), ("A", second)] if local_kind == "template" else [("A", ordinary)]
            assert unwrap(child.resolve(Target))[0] == expected
            assert {d.order for d in child._plan.blueprint.layers[0].decorator_templates} == {0}


@pytest.mark.parametrize("activate_parent_first", [False, True])
def test_parent_singleton_wrappers_sources_resources_and_cleanup_stay_anchored(activate_parent_first):
    class Resource:
        pass

    class ResourceSource(Source):
        def __init__(self, resource: Resource):
            self.resource = resource

    events = []

    @contextmanager
    def resource():
        value = Resource()
        events.append(("enter-resource", value))
        yield value
        events.append(("exit-resource", value))

    def wrapper(inner: Target, source: Source) -> Iterator[Target]:
        value = Wrapper(inner, source)
        events.append(("enter-wrapper", value))
        yield value
        events.append(("exit-wrapper", value))

    calls = []
    builder = ContainerBuilder()
    resource_id = builder.register(Resource, factory=resource, lifespan="transient")
    source_id = builder.register(Source, ResourceSource, lifespan="singleton")
    target_id = builder.register(Target, lifespan="singleton")

    def template(source):
        calls.append(source.id)
        return DecoratorTemplate(DerivedServices(Target), wrapper, arguments={"source": select(cf.with_id(source.id))})

    policy_id = builder.register_decorator_template(for_each=Source, template=template)
    with builder.build() as root:
        existing = root.resolve(Target) if activate_parent_first else None
        overlay = root.new_scope_builder()
        overlay_resource = Resource()
        overlay.register(Resource, instance=overlay_resource)
        added_source = Source()
        overlay.register(Source, instance=added_source, name="added")
        overlay.register(NewTarget, lifespan="singleton")
        overlay.patch_decorator_template(policy_id, template=template_for(DerivedServices(Target), "overlay"))
        assert overlay.has_component(Target, filter=lambda c: len(c.decorators) == 1)
        inspection = overlay._expand_decorator_templates()
        inherited_source = next(s.component for s in inspection.selections if s.source.id == source_id)
        assert inherited_source.dependencies[0].id == resource_id
        with overlay.build() as child:
            with child.new_scope() as plain:
                anchored = plain.resolve(Target)
                assert existing is None or anchored is existing
                assert anchored is root.resolve(Target)
                assert unwrap(anchored)[0] == [("base", root.resolve(Source))]
                assert isinstance(anchored, Wrapper)
                assert isinstance(anchored.source, ResourceSource)
                assert anchored.source.resource is not overlay_resource
                new = plain.resolve(NewTarget)
                assert unwrap(new)[0] == [("overlay", added_source), ("overlay", anchored.source)]
                report = plain.graph.ownership_report()
                target_record = next(
                    r for r in report.records if r.component.id == target_id and r.component.parent is None
                )
                assert target_record.cache_owner is RuntimeOwnerKind.singleton
                assert target_record.cleanup_owner is RuntimeOwnerKind.singleton
                assert target_record.owner_component is None
                source_records = [r for r in report.records if r.component.id == source_id]
                assert source_records and all(r.cache_owner is RuntimeOwnerKind.singleton for r in source_records)
                resources = [
                    r for r in report.records if r.component.id == resource_id and r.component.parent is not None
                ]
                assert resources and all(r.cleanup_owner is RuntimeOwnerKind.singleton for r in resources)
                assert all(r.owner_component is not None and r.owner_component.id == source_id for r in resources)
                wrappers = [r for r in report.records if r.component.implementation is wrapper]
                assert wrappers and all(r.cleanup_owner is RuntimeOwnerKind.singleton for r in wrappers)
                assert all(r.owner_component is not None and r.owner_component.id == target_id for r in wrappers)
                assert len([event for event in events if event[0] == "enter-wrapper"]) == 1
            assert not any(event[0].startswith("exit") for event in events)
        assert not any(event[0].startswith("exit") for event in events)
    assert [event[0] for event in events] == ["enter-resource", "enter-wrapper", "exit-wrapper", "exit-resource"]


@pytest.mark.parametrize("consumer_area", ["root", "boundary"])
@pytest.mark.parametrize("alias", [False, True])
def test_exposed_and_used_sources_bind_exact_original_identity_and_deduplicate_aliases(consumer_area, alias):
    class PublicSource(Source):
        pass

    class PublicWrapper(Target):
        def __init__(self, inner: Target, source: PublicSource):
            self.inner, self.source = inner, source

    source = Source()
    fallback = PublicSource() if alias else Source()
    source_type = PublicSource if alias else Source
    wrapper_type = PublicWrapper if alias else Wrapper
    original_ids, calls = [], []
    group = ServiceGroup("shared", service_type=Target)

    def provider(builder):
        original_ids.append(builder.register(Source, instance=source, name="internal", lifespan="singleton"))
        builder.register(Source, name="private")

    def consumer(builder):
        builder.register(source_type, instance=fallback, name="fallback")
        builder.register(Target, groups=[group])

        def template(info):
            calls.append(info)
            return DecoratorTemplate(group, wrapper_type, arguments={"source": select(cf.with_id(info.id))})

        builder.register_decorator_template(
            for_each=source_type,
            source_filter=cf.with_id(original_ids[0]),
            template=template,
        )

    exposures = (Expose(Source, filter=cf.with_name("internal")),)
    public_name = "internal"
    if alias:
        exposures = (
            Expose(Source, filter=cf.with_name("internal"), alias=BoundaryAlias(PublicSource, name="public")),
            Expose(Source, filter=cf.with_name("internal"), alias=BoundaryAlias(PublicSource, name="alternate")),
        )
        public_name = "public"
    builder = ContainerBuilder()
    builder.create_boundary("provider", exposes=exposures).apply_bundle(provider)
    if consumer_area == "root":
        consumer(builder)
    else:
        uses = [Use("provider", source_type, filter=cf.with_name(public_name))]
        if alias:
            uses.append(Use("provider", source_type, filter=cf.with_name("alternate")))
        builder.create_boundary("consumer", uses=tuple(uses), exposes=(Expose(Target),)).apply_bundle(consumer)
    assert builder.has_component(Target, filter=lambda c: len(c.decorators) == 1)
    with builder.build() as root:
        value = root.resolve(Target)
        assert isinstance(value, (Wrapper, PublicWrapper))
        assert value.source is source
        assert value.source is root.resolve(source_type, filter=cf.with_name(public_name))
        assert calls and all(info.id == original_ids[0] for info in calls)
        assert all(info.name == "internal" and info.service_type is Source for info in calls)
        assert len(root._plan.blueprint.generated_decorators) == 1
        overlay = root.new_scope_builder()
        assert overlay.has_component(Target, filter=lambda c: len(c.decorators) == 1)
        with overlay.build() as child:
            child_value = child.resolve(Target)
            assert isinstance(child_value, (Wrapper, PublicWrapper))
            assert child_value.source is source
            nested = child.new_scope_builder()
            with nested.build() as grandchild:
                nested_value = grandchild.resolve(Target)
                assert isinstance(nested_value, (Wrapper, PublicWrapper))
                assert nested_value.source is source
                assert len(grandchild._plan.blueprint.generated_decorators) == 1


def test_shared_group_grants_neither_private_source_visibility_nor_cross_area_decoration_or_edits():
    group = ServiceGroup("shared", service_type=Target)
    private_source, root_source = Source(), Source()
    private_ids, source_calls = [], []

    def private(builder):
        builder.register(Source, instance=private_source)
        builder.register(Target, groups=[group])
        private_ids.append(
            builder.register_decorator_template(for_each=Source, template=template_for(group, "private"))
        )

    builder = ContainerBuilder()
    builder.register(Source, instance=root_source)
    builder.register(Target, name="root", groups=[group])
    root_policy = builder.register_decorator_template(
        for_each=Source, template=template_for(group, "root", source_calls)
    )
    builder.create_boundary("private", exposes=(Expose(Target),)).apply_bundle(private)
    for edit in (builder.patch_decorator_template, builder.remove_decorator_template):
        with pytest.raises(KeyError):
            edit(private_ids[0])
    with builder.build() as root:
        assert unwrap(root.resolve(Target))[0] == [("private", private_source)]
        assert unwrap(root.resolve(Target, filter=cf.with_name("root")))[0] == [("root", root_source)]
        assert len(source_calls) == 1
        overlay = root.new_scope_builder()
        overlay.remove_decorator_template(root_policy)
        for edit in (overlay.patch_decorator_template, overlay.remove_decorator_template):
            with pytest.raises(KeyError):
                edit(private_ids[0])
        with overlay.build() as child:
            assert unwrap(child.resolve(Target))[0] == [("private", private_source)]
            assert unwrap(child.resolve(Target, filter=cf.with_name("root")))[0] == []


@pytest.mark.parametrize("missing_contract", ["expose", "use"])
def test_private_sources_are_not_enumerated_without_complete_visibility_contract(missing_contract):
    calls = []
    builder = ContainerBuilder()
    group = ServiceGroup("shared", service_type=Target)

    def provider(private):
        private.register(Source)

    builder.create_boundary("provider", exposes=(Expose(Source),) if missing_contract == "use" else ()).apply_bundle(
        provider
    )

    def consumer(private):
        private.register(Target, groups=[group])
        private.register_decorator_template(for_each=Source, template=template_for(group, calls=calls))

    if missing_contract == "expose":
        consumer(builder)
    else:
        builder.create_boundary("consumer", exposes=(Expose(Target),)).apply_bundle(consumer)
    with builder.build() as container:
        assert unwrap(container.resolve(Target))[0] == []
        assert calls == []


@pytest.mark.parametrize("invisible", [False, True])
def test_exact_source_selection_cannot_fall_back_to_an_eligible_visible_source(invisible):
    selected_ids = []
    calls = []
    group = ServiceGroup("targets", service_type=Target)
    builder = ContainerBuilder()
    if invisible:

        def private(local):
            selected_ids.append(local.register(Source, name="same"))

        builder.create_boundary("private").apply_bundle(private)
    else:
        selected_ids.append(builder.register(Source, name="same", when=lambda component: component.parent is None))
    visible_id = builder.register(Source, name="same")
    builder.register(Target, groups=[group])

    def template(info):
        calls.append(info.id)
        # An application selecting an unavailable private ID must not bypass visibility.
        exact_id = selected_ids[0] if invisible else info.id
        return DecoratorTemplate(group, Wrapper, arguments={"source": select(cf.with_id(exact_id))})

    template_id = builder.register_decorator_template(
        for_each=Source,
        source_filter=cf.with_id(visible_id if invisible else selected_ids[0]),
        template=template,
    )
    for attempt in range(2):
        with pytest.raises(ContainerBuildError) as caught:
            builder.build()
        assert caught.value.report is not None
        assert caught.value.report.errors
        assert len(calls) == attempt + 1
        assert builder._decorator_templates[0].id == template_id
    builder.remove_decorator_template(template_id)
    with builder.build() as repaired:
        assert type(repaired.resolve(Target)) is Target


@pytest.mark.parametrize("overlay_build", [False, True])
def test_failed_build_diagnostic_retries_and_repair_do_not_accumulate_generated_candidates(overlay_build):
    class Missing:
        pass

    class Broken(Target):
        def __init__(self, missing: Missing):
            self.missing = missing

    calls = []
    builder = ContainerBuilder()
    source = Source()
    builder.register(Source, instance=source)
    builder.register(Target)
    template_id = builder.register_decorator_template(
        for_each=Source, template=template_for(DerivedServices(Target), calls=calls)
    )
    root = builder.build() if overlay_build else None
    current = root.new_scope_builder() if root is not None else builder
    current.register(Broken)
    baseline_calls = len(calls)
    failures = []
    for attempt in range(2):
        with pytest.raises(ContainerBuildError) as caught:
            current.build()
        failures.append(caught.value)
        assert len(calls) == baseline_calls + attempt + 1
        assert caught.value.partial_graph is not None
        assert len(caught.value.partial_graph.attempts) > 1
        assert all(
            not layer.decorators for layer in ([current._layer()] if root is None else root._plan.blueprint.layers)
        )
    assert failures[0].report is not None and failures[1].report is not None
    assert [issue.code for issue in failures[0].report.errors] == [issue.code for issue in failures[1].report.errors]
    resource = Missing()
    current.register(Missing, instance=resource)
    assert current.has_component(Broken, filter=lambda c: len(c.decorators) == 1)
    with current.build() as repaired:
        layers, core = unwrap(repaired.resolve(Broken))
        assert layers == [("base", source)]
        assert core.missing is resource
        assert len(repaired._plan.blueprint.generated_decorators) == 1
        assert repaired._plan.blueprint.generated_decorators[0].declaration.id == template_id
        assert sum(len(layer.decorator_templates) for layer in repaired._plan.blueprint.layers) == 1
    if root is not None:
        root._close()


T = TypeVar("T")


class GenericSource(Source, Generic[T]):
    pass


def test_inherited_generic_source_metadata_is_preserved_after_patch_and_nested_overlay():
    class ConcreteSource(GenericSource[int]):
        pass

    calls = []
    source = ConcreteSource()
    builder = ContainerBuilder()
    builder.register(Source, instance=source)
    builder.register(Target)

    def template(info):
        calls.append(info.implementation_bindings(GenericSource))
        return DecoratorTemplate(DerivedServices(Target), Wrapper, arguments={"source": select(cf.with_id(info.id))})

    policy = builder.register_decorator_template(for_each=Source, template=template)
    with builder.build() as root:
        overlay = root.new_scope_builder()
        overlay.patch_decorator_template(policy, source_filter=cf.implementation_type_is(ConcreteSource))
        with overlay.build() as child:
            nested = child.new_scope_builder()
            nested.register(NewTarget)
            with nested.build() as grandchild:
                assert unwrap(grandchild.resolve(NewTarget))[0] == [("base", source)]
    assert calls == [{T: int}] * 3


@pytest.mark.parametrize("contract", ["use", "expose", "alias-use"])
def test_boundary_metadata_recheck_uses_parent_singleton_anchor(contract):
    class PublicTarget:
        pass

    builder = ContainerBuilder()

    def compose(local):
        local.register(Target, lifespan="singleton")
        local.register(Source, lifespan="singleton")
        local.register_decorator_template(
            for_each=Source,
            template=lambda source: DecoratorTemplate(
                DerivedServices(Target),
                Wrapper,
                arguments={"source": select(cf.with_id(source.id))},
                when=lambda component: component.build_args.get("decorate", False),
            ),
        )

    if contract == "use":
        builder.register(Target, lifespan="singleton")
    else:
        builder.create_boundary(
            "provider", exposes=(Expose(Target, filter=lambda c: not c.decorators, alias=BoundaryAlias(PublicTarget)),)
        ).apply_bundle(compose)
    service = Target if contract == "use" else PublicTarget
    with builder.build() as root:
        original = root.resolve(service)
        overlay = root.new_scope_builder()
        if contract == "use":
            overlay.register(Source, lifespan="singleton")
            overlay.register_decorator_template(for_each=Source, template=template_for(DerivedServices(Target)))
            overlay.create_boundary(
                "consumer", uses=(Use.root(Target, filter=lambda c: not c.decorators),)
            ).apply_bundle(lambda _: None)
        elif contract == "alias-use":
            overlay.create_boundary(
                "consumer", uses=(Use("provider", PublicTarget, filter=lambda c: not c.decorators),)
            ).apply_bundle(lambda _: None)
        # New policy applies to newly compiled plans, not to the parent singleton.
        assert overlay.has_component(service, filter=lambda c: not c.decorators, build_args={"decorate": True})
        with overlay.build(build_args={"decorate": True}) as child:
            assert child.resolve(service) is original
            nested = child.new_scope_builder()
            assert nested.has_component(service, filter=lambda c: not c.decorators)
            with nested.build() as grandchild:
                assert grandchild.resolve(service) is original


def test_repatch_keeps_stable_traversal_among_multiple_inherited_ordinal_collisions():
    first, second = Source(), Source()
    builder = ContainerBuilder()
    builder.register(Source, instance=first, name="first")
    builder.register(Source, instance=second, name="second")
    builder.register(Target)
    original = builder.register_decorator_template(
        for_each=Source, template=template_for(DerivedServices(Target), "root")
    )
    with builder.build() as root:
        overlay = root.new_scope_builder()
        middle = overlay.register_decorator_template(
            for_each=Source, template=template_for(DerivedServices(Target), "middle")
        )
        with overlay.build() as child:
            nested = child.new_scope_builder()
            nested.patch_decorator_template(original, template=template_for(DerivedServices(Target), "root-patched"))
            nested.patch_decorator_template(middle, template=template_for(DerivedServices(Target), "middle-patched"))
            nested.patch_decorator_template(original, source_filter=cf.all_components)
            with nested.build() as grandchild:
                assert unwrap(grandchild.resolve(Target))[0] == [
                    ("middle-patched", first),
                    ("middle-patched", second),
                    ("root-patched", first),
                    ("root-patched", second),
                ]
                assert [(d.id, d.order) for d in grandchild._plan.blueprint.layers[0].decorator_templates] == [
                    (original, 0),
                    (middle, 0),
                ]


def test_overlay_patch_can_replace_source_service_and_filter_without_changing_sibling_policy():
    first, second = Source(), OtherSource()
    builder = ContainerBuilder()
    builder.register(Source, instance=first)
    builder.register(OtherSource, instance=second)
    builder.register(Target)
    original = builder.register_decorator_template(for_each=Source, template=template_for(DerivedServices(Target), "A"))
    builder.register_decorator_template(for_each=Source, template=template_for(DerivedServices(Target), "B"))

    class OtherWrapper(Target):
        def __init__(self, inner: Target, source: OtherSource):
            self.inner, self.source = inner, source

    with builder.build() as root:
        overlay = root.new_scope_builder()
        overlay.patch_decorator_template(
            original,
            for_each=OtherSource,
            source_filter=cf.implementation_type_is(OtherSource),
            template=lambda info: DecoratorTemplate(
                DerivedServices(Target), OtherWrapper, arguments={"source": select(cf.with_id(info.id))}
            ),
        )
        with overlay.build() as child:
            result = child.resolve(Target)
            assert isinstance(result, Wrapper) and result.label == "B" and result.source is first
            assert isinstance(result.inner, OtherWrapper) and result.inner.source is second
            assert type(result.inner.inner) is Target
        assert unwrap(root.resolve(Target))[0] == [("A", first), ("B", first)]


def test_overlay_owned_generated_resources_close_with_overlay_after_nested_activation():
    events = []
    root_source, overlay_source = Source(), Source()

    def source_factory(value, label):
        def factory() -> Iterator[Source]:
            events.append(("enter-source", label))
            yield value
            events.append(("exit-source", label))

        return factory

    def wrapper(inner: Target, source: Source) -> Iterator[Target]:
        value = Wrapper(inner, source)
        events.append(("enter-wrapper", value))
        yield value
        events.append(("exit-wrapper", value))

    builder = ContainerBuilder()
    builder.register(Source, factory=source_factory(root_source, "root"), name="root", lifespan="singleton")
    builder.register(Target, lifespan="singleton")
    builder.register_decorator_template(
        for_each=Source,
        template=lambda info: DecoratorTemplate(
            DerivedServices(Target), wrapper, arguments={"source": select(cf.with_id(info.id))}
        ),
    )
    with builder.build() as root:
        overlay = root.new_scope_builder()
        source_id = overlay.register(
            Source, factory=source_factory(overlay_source, "overlay"), name="overlay", lifespan="singleton"
        )
        target_id = overlay.register(NewTarget, lifespan="singleton")
        with overlay.build() as child:
            nested = child.new_scope_builder()
            with nested.build() as grandchild:
                with grandchild.new_scope() as plain:
                    value = plain.resolve(NewTarget)
                    assert unwrap(value)[0] == [("base", overlay_source), ("base", root_source)]
                    assert child.resolve(NewTarget) is value
                    assert unwrap(plain.resolve(Target))[0] == [("base", root_source)]
                    report = plain.graph.ownership_report()
                    assert report.is_valid
                    acquired_sources = [r for r in report.records if r.component.id == source_id]
                    assert acquired_sources and all(
                        r.cleanup_owner is RuntimeOwnerKind.singleton for r in acquired_sources
                    )
                    new_wrappers = [
                        r
                        for r in report.records
                        if r.component.implementation is wrapper
                        and r.owner_component is not None
                        and r.owner_component.id == target_id
                    ]
                    assert len(new_wrappers) == 2
                    assert all(r.cleanup_owner is RuntimeOwnerKind.singleton for r in new_wrappers)
            assert not any(kind.startswith("exit") for kind, _ in events)
        exits = [event for event in events if event[0].startswith("exit")]
        assert ("exit-source", "overlay") in exits
        assert ("exit-source", "root") not in exits
        assert len([event for event in exits if event[0] == "exit-wrapper"]) == 2
    assert events[-1] == ("exit-source", "root")
    assert len([event for event in events if event[0] == "exit-wrapper"]) == 3


@pytest.mark.parametrize("parent_kind", ["ordinary", "template"])
@pytest.mark.parametrize("local_kind", ["ordinary", "template"])
@pytest.mark.parametrize("patch_first", [False, True])
@pytest.mark.parametrize("source_count", [1, 2])
def test_shared_layer_tie_order_is_independent_of_decorator_kind_and_stable_on_repatch(
    parent_kind, local_kind, patch_first, source_count
):
    sources = [Source() for _ in range(source_count)]

    def register(builder, kind, label):
        if kind == "template":
            return builder.register_decorator_template(
                for_each=Source, template=template_for(DerivedServices(Target), label)
            )
        return builder.register_decorator(Target, Wrapper, arguments={"source": sources[0], "label": label})

    def patch(builder, kind, definition_id, label):
        if kind == "template":
            builder.patch_decorator_template(definition_id, template=template_for(DerivedServices(Target), label))
        else:
            builder.patch_decorator(Target, definition_id, arguments={"label": label})

    def layers(kind, label):
        return [(label, source) for source in (sources if kind == "template" else sources[:1])]

    builder = ContainerBuilder()
    for index, source in enumerate(sources):
        builder.register(Source, instance=source, name=str(index))
    builder.register(Target)
    inherited = register(builder, parent_kind, "parent")
    with builder.build() as root:
        overlay = root.new_scope_builder()
        if patch_first:
            patch(overlay, parent_kind, inherited, "patched")
        local = register(overlay, local_kind, "local")
        if not patch_first:
            patch(overlay, parent_kind, inherited, "patched")
        # Updating either kind in place preserves the first insertion into the layer.
        patch(overlay, parent_kind, inherited, "patched-again")
        patch(overlay, local_kind, local, "local-again")
        with overlay.build() as child:
            expected_parent = layers(parent_kind, "patched-again")
            expected_local = layers(local_kind, "local-again")
            expected = expected_local + expected_parent if patch_first else expected_parent + expected_local
            assert unwrap(child.resolve(Target))[0] == expected
            layer = child._plan.blueprint.layers[0]
            assert layer.decorator_declaration_ids == ((inherited, local) if patch_first else (local, inherited))
            assert {
                (definition.id, definition.order) for definition in (*layer.decorators, *layer.decorator_templates)
            } == {(inherited, 0), (local, 0)}
            nested = child.new_scope_builder()
            with nested.build() as grandchild:
                assert unwrap(grandchild.resolve(Target))[0] == expected
        assert unwrap(root.resolve(Target))[0] == layers(parent_kind, "parent")
