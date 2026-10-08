"""Registration templates compile ordinary registrations from exact sources."""

from dataclasses import FrozenInstanceError
from typing import Generic, TypeVar

import pytest

from clean_ioc import (
    BuilderAlreadyBuiltError,
    CannotResolveError,
    ContainerBuilder,
    ContainerBuildError,
    DecoratorTemplate,
    DerivedServices,
    Expose,
    RegistrationTemplate,
    ServiceGroup,
    Tag,
    Use,
    select,
)
from clean_ioc import component_filters as cf


class Source:
    pass


class Target:
    def __init__(self, source: Source):
        self.source = source


def target_for(source):
    return RegistrationTemplate(Target, arguments={"source": select(cf.with_id(source.id))})


def test_each_registration_gets_a_target_bound_to_its_exact_source_without_build_activation():
    created = []

    class ConstructedSource(Source):
        def __init__(self):
            created.append(self)

    builder = ContainerBuilder()
    first = builder.register(Source, ConstructedSource, name="first", lifespan="singleton")
    second = builder.register(Source, ConstructedSource, name="second", lifespan="singleton")
    calls = []

    def template(source):
        calls.append(source)
        return target_for(source)

    template_id = builder.register_registration_template(for_each=Source, template=template)
    with builder.build() as container:
        assert created == []
        assert [source.id for source in calls] == [first, second]
        targets = container.resolve(list[Target])
        assert len(targets) == 2
        assert targets[0].source is container.resolve(Source, filter=cf.with_id(second))
        assert targets[1].source is container.resolve(Source, filter=cf.with_id(first))
        decisions = container.graph.explain_template_sources(template_id)
        assert [item.source_registration_id for item in decisions] == [first, second]
        assert all(item.selected and item.generated_definition_id for item in decisions)
        container.graph.manifest(all_roots=True).to_json()
        container.resolve(list[Target])
        assert len(calls) == 2
    with pytest.raises(BuilderAlreadyBuiltError):
        builder.remove_registration_template(template_id)


def test_sources_are_exact_service_keys_and_source_filters_skip_factories():
    class Derived(Source):
        pass

    builder = ContainerBuilder()
    builder.register(Derived)
    selected = builder.register(Source, name="selected", tags=[Tag("enabled")])
    rejected = builder.register(Source, name="rejected")
    seen = []

    def template(source):
        seen.append(source.id)
        return target_for(source)

    template_id = builder.register_registration_template(
        for_each=Source,
        source_filter=cf.has_tag("enabled"),
        template=template,
    )
    with builder.build() as container:
        assert seen == [selected]
        assert len(container.resolve(list[Target])) == 1
        assert [
            (item.source_registration_id, item.selected)
            for item in container.graph.explain_template_sources(template_id)
        ] == [(selected, True), (rejected, False)]


def test_metadata_can_generate_a_registration_without_injecting_the_source():
    builder = ContainerBuilder()
    builder.register(Source, name="one")
    builder.register_registration_template(
        for_each=Source,
        template=lambda source: RegistrationTemplate(str, instance=source.name),
    )
    with builder.build() as container:
        assert container.resolve(str) == "one"


def test_generated_outputs_are_not_sources_even_in_overlays():
    builder = ContainerBuilder()
    builder.register(Source)
    builder.register_registration_template(for_each=Source, template=target_for)
    builder.register_registration_template(
        for_each=Target, template=lambda _: RegistrationTemplate(bytes, instance=b"bad")
    )
    with builder.build() as container:
        assert len(container.resolve(list[Target])) == 1
        with pytest.raises(CannotResolveError):
            container.resolve(bytes)
        with container.new_scope_builder().build() as overlay:
            assert len(overlay.resolve(list[Target])) == 1
            with pytest.raises(CannotResolveError):
                overlay.resolve(bytes)


def test_discovery_precedes_expansion_and_generated_targets_receive_decorators():
    class Discovered(Source):
        pass

    class Wrapped(Target):
        def __init__(self, inner: Target):
            self.inner = inner

    group = ServiceGroup("targets", service_type=Target)
    builder = ContainerBuilder()
    builder.register_registration_template(
        for_each=Source,
        template=lambda source: RegistrationTemplate(
            Target,
            arguments={"source": select(cf.with_id(source.id))},
            groups=[group],
        ),
    )
    builder.register_subclasses(Source, subclass_type_filter=lambda cls: cls is Discovered)
    builder.register_decorator_template(
        for_each=Source,
        template=lambda _: DecoratorTemplate(group, Wrapped),
    )
    with builder.build() as container:
        target = container.resolve(Target)
        assert isinstance(target, Wrapped)
        assert isinstance(target.inner.source, Discovered)


def test_generated_registrations_can_be_decorator_template_sources():
    class Marker:
        pass

    class Wrapped(Marker):
        def __init__(self, inner: Marker, target: Target):
            self.target = target

    builder = ContainerBuilder()
    builder.register(Source)
    builder.register(Marker)
    builder.register_registration_template(for_each=Source, template=target_for)
    builder.register_decorator_template(
        for_each=Target,
        template=lambda source: DecoratorTemplate(
            DerivedServices(Marker),
            Wrapped,
            arguments={"target": select(cf.with_id(source.id))},
        ),
    )
    with builder.build() as container:
        marker = container.resolve(Marker)
        assert isinstance(marker, Wrapped)
        assert isinstance(marker.target.source, Source)


def test_preview_ids_are_stable_and_edits_apply_before_build():
    builder = ContainerBuilder()
    builder.register(Source)
    template_id = builder.register_registration_template(for_each=Source, template=target_for)
    first = builder.get_component_ids(Target)
    assert len(first) == 1
    assert builder.get_component_ids(Target) == first
    builder.patch_registration_template(template_id, template=lambda _: RegistrationTemplate(str, instance="changed"))
    with builder.build() as container:
        assert container.resolve(str) == "changed"
        with pytest.raises(CannotResolveError):
            container.resolve(Target)


def test_removal_and_unknown_template_ids():
    builder = ContainerBuilder()
    template_id = builder.register_registration_template(for_each=Source, template=target_for)
    builder.remove_registration_template(template_id)
    with pytest.raises(KeyError):
        builder.patch_registration_template(template_id, template=target_for)
    with pytest.raises(KeyError):
        builder.remove_registration_template(template_id)
    with builder.build():
        pass


def test_overlays_extend_templates_and_keep_parent_singletons_anchored():
    builder = ContainerBuilder()
    parent_source = Source()
    builder.register(Source, instance=parent_source)
    template_id = builder.register_registration_template(
        for_each=Source,
        template=lambda source: RegistrationTemplate(
            Target,
            arguments={"source": select(cf.with_id(source.id))},
            lifespan="singleton",
        ),
    )
    with builder.build() as container:
        original = container.resolve(Target)
        overlay = container.new_scope_builder()
        child_source = Source()
        overlay.register(Source, instance=child_source)
        with overlay.build() as scope:
            targets = scope.resolve(list[Target])
            assert len(targets) == 2
            assert targets[1] is original
            assert targets[0].source is child_source
        removed = container.new_scope_builder()
        removed.remove_registration_template(template_id)
        with removed.build() as scope:
            with pytest.raises(CannotResolveError):
                scope.resolve(Target)
        patched = container.new_scope_builder()
        patched.patch_registration_template(
            template_id, template=lambda _: RegistrationTemplate(str, instance="overlay")
        )
        with patched.build() as scope:
            assert scope.resolve(str) == "overlay"
            with pytest.raises(CannotResolveError):
                scope.resolve(Target)
        assert container.resolve(Target) is original


def test_boundary_generates_private_targets_and_can_expose_them():
    builder = ContainerBuilder()
    private = builder.create_boundary("workers", exposes=[Expose(Target)])
    private.register(Source)
    private.register_registration_template(for_each=Source, template=target_for)
    root_id = builder.register_registration_template(for_each=Source, template=lambda _: RegistrationTemplate(bytes))
    with builder.build() as container:
        assert isinstance(container.resolve(Target).source, Source)
        assert container.graph.explain_template_sources(root_id) == ()
        with pytest.raises(CannotResolveError):
            container.resolve(Source)


def test_boundary_template_can_use_an_explicitly_imported_source():
    builder = ContainerBuilder()
    source = Source()
    builder.register(Source, instance=source)
    private = builder.create_boundary("workers", uses=[Use(None, Source)], exposes=[Expose(Target)])
    private.register_registration_template(for_each=Source, template=target_for)
    with builder.build() as container:
        assert container.resolve(Target).source is source


def test_open_source_rejected_and_closed_generic_source_supported():
    t = TypeVar("t")

    class GenericSource(Generic[t]):
        pass

    builder = ContainerBuilder()
    template_id = builder.register_registration_template(
        for_each=GenericSource, template=lambda _: RegistrationTemplate(str, instance="ok")
    )
    with pytest.raises(ContainerBuildError) as error:
        builder.build()
    assert error.value.report is not None
    assert error.value.report.errors[0].code == "template-source-open-generic"
    builder.patch_registration_template(template_id, for_each=GenericSource[int])
    builder.register(GenericSource[int])
    with builder.build() as container:
        assert container.resolve(str) == "ok"


@pytest.mark.parametrize("result", [None, [], object()])
def test_invalid_factory_result_fails_build_and_can_be_repaired(result):
    builder = ContainerBuilder()
    builder.register(Source)
    template_id = builder.register_registration_template(for_each=Source, template=lambda _: result)
    with pytest.raises(ContainerBuildError) as error:
        builder.build()
    assert error.value.report is not None
    assert error.value.report.errors[0].code == "template-expansion"
    assert template_id in error.value.report.errors[0].path
    builder.patch_registration_template(template_id, template=target_for)
    with builder.build() as container:
        assert isinstance(container.resolve(Target).source, Source)


def test_callbacks_cannot_mutate_or_reenter_the_builder():
    for callback in (lambda b: b.register(Source), lambda b: b.build()):
        builder = ContainerBuilder()
        builder.register(Source)
        builder.register_registration_template(for_each=Source, template=lambda _: callback(builder))
        with pytest.raises(ContainerBuildError) as error:
            builder.build()
        assert error.value.report is not None
        assert error.value.report.errors[0].code == "template-expansion-reentry"


def test_async_template_rejected():
    async def template(_):
        return RegistrationTemplate(Source)

    builder = ContainerBuilder()
    with pytest.raises(TypeError, match="synchronous"):
        builder.register_registration_template(for_each=Source, template=template)  # ty: ignore[invalid-argument-type]


def test_generated_dependencies_receive_normal_validation():
    class Missing:
        pass

    class Invalid:
        def __init__(self, missing: Missing):
            pass

    builder = ContainerBuilder()
    builder.register(Source)
    template_id = builder.register_registration_template(
        for_each=Source, template=lambda _: RegistrationTemplate(Invalid)
    )
    with pytest.raises(ContainerBuildError):
        builder.build()
    builder.patch_registration_template(template_id, template=target_for)
    with builder.build() as container:
        assert isinstance(container.resolve(Target), Target)


def test_registration_specification_snapshots_mutable_options():
    arguments = {"source": select()}
    tags = [Tag("a")]
    specification = RegistrationTemplate(Target, arguments=arguments, tags=tags)
    arguments.clear()
    tags.clear()
    assert specification.arguments is not None
    assert len(specification.arguments) == 1
    assert tuple(specification.tags) == (Tag("a"),)
    with pytest.raises(FrozenInstanceError):
        specification.name = "changed"  # ty: ignore[invalid-assignment]


def test_generated_factory_cleanup_and_scoped_identity():
    events = []

    def make_target(source: Source):
        events.append("created")
        yield Target(source)
        events.append("closed")

    builder = ContainerBuilder()
    builder.register(Source, lifespan="singleton")
    builder.register_registration_template(
        for_each=Source,
        template=lambda source: RegistrationTemplate(
            Target,
            factory=make_target,
            lifespan="scoped",
            arguments={"source": select(cf.with_id(source.id))},
        ),
    )
    with builder.build() as container:
        assert events == []
        with container.new_scope() as scope:
            target = scope.resolve(Target)
            assert scope.resolve(Target) is target
            assert events == ["created"]
        assert events == ["created", "closed"]


def test_generated_provider_map_contributions_and_dependency_only_roots():
    from collections.abc import Mapping

    from clean_ioc import Provider, ProviderMapGroup

    group = ProviderMapGroup("workers", key_type=str, service_type=Target)
    builder = ContainerBuilder()
    builder.register(Source, name="orders")
    builder.register(Source, name="payments")
    builder.register_provider_map(group)
    builder.register_registration_template(
        for_each=Source,
        template=lambda source: RegistrationTemplate(
            Target,
            arguments={"source": select(cf.with_id(source.id))},
            contributes={group: source.name},
            root_policy="dependency_only",
        ),
    )
    with builder.build() as container:
        providers = container.resolve(Mapping[str, Provider[Target]])
        assert set(providers) == {"orders", "payments"}
        assert isinstance(providers["orders"]().source, Source)
        with pytest.raises(CannotResolveError):
            container.resolve(Target)


def test_overlay_patch_replaces_same_service_without_reusing_parent_singleton():
    builder = ContainerBuilder()
    builder.register(Source, lifespan="singleton")
    template_id = builder.register_registration_template(
        for_each=Source,
        template=lambda source: RegistrationTemplate(
            Target,
            arguments={"source": select(cf.with_id(source.id))},
            lifespan="singleton",
        ),
    )
    with builder.build() as container:
        parent = container.resolve(Target)
        overlay = container.new_scope_builder()
        overlay.patch_registration_template(template_id, template=target_for)
        with overlay.build() as scope:
            assert len(scope.resolve(list[Target])) == 1
            assert scope.resolve(Target) is not parent
        assert container.resolve(Target) is parent


def test_inherited_outputs_keep_frozen_selection_when_overlay_build_arguments_change():
    builder = ContainerBuilder()
    builder.register(Source)
    template_id = builder.register_registration_template(
        for_each=Source,
        template=target_for,
        source_filter=lambda component: component.build_args["enabled"],
    )
    with builder.build(build_args={"enabled": True}) as container:
        with container.new_scope_builder().build(build_args={"enabled": False}) as scope:
            assert len(scope.resolve(list[Target])) == 1
            assert scope.graph.explain_template_sources(template_id)[0].selected


def test_generated_captive_dependency_is_rejected():
    builder = ContainerBuilder()
    builder.register(Source, lifespan="scoped")
    builder.register_registration_template(
        for_each=Source,
        template=lambda source: RegistrationTemplate(
            Target,
            arguments={"source": select(cf.with_id(source.id))},
            lifespan="singleton",
        ),
    )
    with pytest.raises(ContainerBuildError, match="[Cc]aptive"):
        builder.build()


def test_generated_registration_census_records_source_and_template():
    builder = ContainerBuilder()
    builder.register(Source)
    builder.register_registration_template(for_each=Source, template=target_for)
    with builder.build(diagnostics=True) as container:
        census = container.graph.selection_census(all_roots=True).to_dict()
        definitions = [item["definition"] for item in census["definitions"]]
        generated = next(item for item in definitions if item["kind"] == "generated-registration")
        source = next(item for item in definitions if item["kind"] == "registration")
        template = next(item for item in definitions if item["kind"] == "registration-template")
        assert generated["source"] == source["reference"]
        assert generated["template"] == template["reference"]


def test_source_visibility_cannot_change_as_a_result_of_expansion():
    class Added:
        pass

    class BoundarySource(Source):
        def __init__(self, generated: list[Added]):
            pass

    builder = ContainerBuilder()
    private = builder.create_boundary(
        "sources",
        uses=[Use(None, Added)],
        exposes=[Expose(Source, filter=lambda c: (c.name == "a") != cf.has_descendant(cf.service_type_is(Added))(c))],
    )
    private.register(Source, BoundarySource, name="a")
    private.register(Source, BoundarySource, name="b")
    builder.register_registration_template(for_each=Source, template=lambda _: RegistrationTemplate(Added))
    with pytest.raises(ContainerBuildError, match="template-source-visibility-changed"):
        builder.build()


def test_inherited_private_boundary_does_not_generate_new_parent_owned_singletons():
    builder = ContainerBuilder()
    private = builder.create_boundary("workers")
    private.register(Source, lifespan="singleton")
    template_id = private.register_registration_template(
        for_each=Source,
        source_filter=lambda c: c.build_args["enabled"],
        template=lambda source: RegistrationTemplate(
            Target,
            lifespan="singleton",
            arguments={"source": select(cf.with_id(source.id))},
        ),
    )
    with builder.build(build_args={"enabled": False}) as container:
        with container.new_scope_builder().build(build_args={"enabled": True}) as scope:
            assert not scope.graph.explain_template_sources(template_id)[0].selected


@pytest.mark.parametrize("lifespan", ["transient", "scoped", "singleton"])
def test_source_can_depend_on_its_own_generated_registration(lifespan):
    class Configuration:
        def __init__(self, label: str):
            self.label = label

    class Consumer:
        def __init__(self, configuration: Configuration):
            self.configuration = configuration

    calls = []
    builder = ContainerBuilder()
    first = builder.register(Consumer, name="first", lifespan=lifespan)
    second = builder.register(Consumer, name="second", lifespan=lifespan)

    def template(source):
        calls.append(source.id)
        return RegistrationTemplate(
            Configuration,
            arguments={"label": source.name},
            lifespan=lifespan,
            when=cf.parent(cf.with_id(source.id)),
            root_policy="dependency_only",
        )

    template_id = builder.register_registration_template(
        for_each=Consumer,
        source_filter=cf.service_type_is(Consumer),
        template=template,
    )
    preview_ids = builder.get_component_ids(Consumer, filter=cf.all_components)
    assert set(preview_ids) == {first, second}
    calls.clear()
    with builder.build() as container:
        with container.new_scope() as scope:
            assert scope.resolve(Consumer, filter=cf.with_id(first)).configuration.label == "first"
            assert scope.resolve(Consumer, filter=cf.with_id(second)).configuration.label == "second"
            assert calls == [first, second]
            assert len(scope.graph.explain_template_sources(template_id)) == 2
            with pytest.raises(CannotResolveError):
                scope.resolve(Configuration)


def test_both_dependency_directions_can_be_used_in_the_same_composition():
    class Configuration:
        def __init__(self, label: str):
            self.label = label

    class Consumer:
        def __init__(self, configuration: Configuration):
            self.configuration = configuration

    class Adapter:
        def __init__(self, consumer: Consumer):
            self.consumer = consumer

    builder = ContainerBuilder()
    builder.register(Consumer, name="a")
    builder.register(Consumer, name="b")
    # Declare the outward edge first, before the registration it needs exists.
    builder.register_registration_template(
        for_each=Consumer,
        template=lambda source: RegistrationTemplate(
            Adapter,
            arguments={"consumer": select(cf.with_id(source.id))},
        ),
    )
    builder.register_registration_template(
        for_each=Consumer,
        template=lambda source: RegistrationTemplate(
            Configuration,
            arguments={"label": source.name},
            when=cf.parent(cf.with_id(source.id)),
            root_policy="dependency_only",
        ),
    )
    with builder.build() as container:
        assert [item.consumer.configuration.label for item in container.resolve(list[Adapter])] == ["b", "a"]


def test_metadata_source_filter_runs_before_missing_dependencies_are_compiled():
    class Configuration:
        def __init__(self, label: str):
            self.label = label

    class Consumer:
        def __init__(self, configuration: Configuration):
            self.configuration = configuration

    builder = ContainerBuilder()
    builder.register(Configuration, arguments={"label": "default"})
    selected = builder.register(Consumer, name="selected", tags=[Tag("generate")])
    rejected = builder.register(Consumer, name="rejected")
    calls = []

    def template(source):
        calls.append(source.id)
        return RegistrationTemplate(
            Configuration,
            arguments={"label": source.name},
            when=cf.parent(cf.with_id(source.id)),
            root_policy="dependency_only",
        )

    builder.register_registration_template(for_each=Consumer, source_filter=cf.has_tag("generate"), template=template)
    with builder.build() as container:
        assert container.resolve(Consumer, filter=cf.with_id(selected)).configuration.label == "selected"
        assert container.resolve(Consumer, filter=cf.with_id(rejected)).configuration.label == "default"
        assert calls == [selected]


def test_structural_source_filters_keep_the_complete_undecorated_source_view():
    class Leaf:
        pass

    class NestedSource(Source):
        def __init__(self, leaf: Leaf):
            raise AssertionError("Build must not activate sources")

    class Wrapper(Source):
        def __init__(self, inner: Source):
            raise AssertionError("Build must not activate decorators")

    captured = []

    def source_filter(component):
        captured.append(component)
        assert component.parent is None
        assert component.has_descendant(cf.service_type_is(Leaf))
        assert component.decorators == ()
        assert len(component.dependencies) == 1
        return True

    builder = ContainerBuilder()
    builder.register(Leaf)
    builder.register(Source, NestedSource)
    builder.register_decorator(Source, Wrapper)
    builder.register_registration_template(for_each=Source, source_filter=source_filter, template=target_for)
    with builder.build():
        # The requested source graph was frozen during filtering.
        assert len(captured[0].dependencies) == 1


def test_source_graph_filter_fails_clearly_if_it_requires_generated_dependencies():
    class Configuration:
        pass

    class Consumer:
        def __init__(self, configuration: Configuration):
            self.configuration = configuration

    builder = ContainerBuilder()
    builder.register(Consumer)
    calls = []

    def template(source):
        calls.append(source.id)
        return RegistrationTemplate(
            Configuration,
            when=cf.parent(cf.with_id(source.id)),
            root_policy="dependency_only",
        )

    template_id = builder.register_registration_template(
        for_each=Consumer,
        template=template,
        source_filter=cf.has_descendant(cf.service_type_is(Configuration)),
    )
    with pytest.raises(ContainerBuildError, match="registration-template-source-graph"):
        builder.build()
    assert calls == []
    builder.patch_registration_template(template_id, source_filter=cf.all_components)
    with builder.build() as container:
        assert isinstance(container.resolve(Consumer).configuration, Configuration)


def test_saved_metadata_views_cannot_start_compilation_after_source_selection():
    captured = []
    builder = ContainerBuilder()
    builder.register(Source)
    builder.register_registration_template(
        for_each=Source,
        source_filter=lambda c: captured.append(c) or True,
        template=target_for,
    )
    with builder.build():
        assert captured[0].service_type is Source
        with pytest.raises(RuntimeError, match="only available during source_filter"):
            captured[0].dependencies


def test_parent_bound_generated_dependency_is_not_available_to_unrelated_consumers():
    class Configuration:
        pass

    class Consumer:
        def __init__(self, configuration: Configuration):
            pass

    class Unrelated:
        def __init__(self, configuration: Configuration):
            pass

    builder = ContainerBuilder()
    builder.register(Consumer)
    builder.register(Unrelated)
    builder.register_registration_template(
        for_each=Consumer,
        template=lambda source: RegistrationTemplate(
            Configuration,
            when=cf.parent(cf.with_id(source.id)),
            root_policy="dependency_only",
        ),
    )
    with pytest.raises(ContainerBuildError, match="missing-component"):
        builder.build()


def test_actual_dependency_cycle_is_rejected_after_expansion():
    class Consumer:
        pass

    class Configuration:
        def __init__(self, consumer: Consumer):
            pass

    class CyclicConsumer(Consumer):
        def __init__(self, configuration: Configuration):
            pass

    builder = ContainerBuilder()
    builder.register(Consumer, CyclicConsumer)
    builder.register_registration_template(
        for_each=Consumer,
        template=lambda source: RegistrationTemplate(
            Configuration,
            arguments={"consumer": select(cf.with_id(source.id))},
            when=cf.parent(cf.with_id(source.id)),
            root_policy="dependency_only",
        ),
    )
    with pytest.raises(ContainerBuildError, match="[Cc]ycle"):
        builder.build()


def test_parent_bound_generated_dependencies_work_in_boundaries_and_overlays():
    class Configuration:
        def __init__(self, label: str):
            self.label = label

    class Consumer:
        def __init__(self, configuration: Configuration):
            self.configuration = configuration

    def configure(source):
        return RegistrationTemplate(
            Configuration,
            arguments={"label": source.name},
            when=cf.parent(cf.with_id(source.id)),
            root_policy="dependency_only",
            lifespan="singleton",
        )

    builder = ContainerBuilder()
    private = builder.create_boundary("private", exposes=[Expose(Consumer, filter=cf.with_name("private"))])
    private.register(Consumer, name="private", lifespan="singleton")
    private.register_registration_template(for_each=Consumer, template=configure)
    builder.register(Consumer, name="root", lifespan="singleton")
    builder.register_registration_template(for_each=Consumer, template=configure)
    with builder.build() as container:
        root = container.resolve(Consumer, filter=cf.with_name("root"))
        assert container.resolve(Consumer, filter=cf.with_name("private")).configuration.label == "private"
        overlay = container.new_scope_builder()
        overlay.register(Consumer, name="overlay", lifespan="singleton")
        with overlay.build() as scope:
            assert scope.resolve(Consumer, filter=cf.with_name("root")) is root
            assert scope.resolve(Consumer, filter=cf.with_name("overlay")).configuration.label == "overlay"
            assert scope.resolve(Consumer, filter=cf.with_name("private")).configuration.label == "private"
