"""Portable M01 compiler probes; these do not expose the template API yet."""

from dataclasses import replace
from typing import Generic, TypeVar, cast, get_args

import pytest

from clean_ioc import ContainerBuilder, ContainerBuildError, Expose, Tag, Use, select
from clean_ioc import component_filters as cf
from clean_ioc.components import _undecorated_component_view
from clean_ioc.container import (
    _anchored_pre_configurations,
    _anchored_singletons,
    _Blueprint,
    _Compiler,
    _normalize_blueprint_aliases,
    _prepare_boundary_visibility,
)
from clean_ioc.generic_utils import _project_service_type


def _snapshot(builder):
    blueprint, _ = builder._compilation_snapshot(None)
    return _normalize_blueprint_aliases(blueprint)


def _prepared(builder):
    return _prepare_boundary_visibility(_snapshot(builder), build_args={})


def _core(blueprint, registration_id, service_type, **compiler_options):
    return _Compiler(blueprint, **compiler_options)._compile_source_core(registration_id, service_type)


def test_completed_source_core_excludes_all_decorator_branches_without_activation():
    calls = []

    class Resource:
        def __init__(self):
            calls.append("resource")

    class DecoratorOnly:
        def __init__(self):
            calls.append("decorator-only")

    class Target:
        def __init__(self, resource: Resource):
            calls.append("target")
            self.resource = resource

    class Source:
        def __init__(self, target: Target):
            calls.append("source")
            self.target = target

    class Decorator:
        def __init__(self, inner: Target, marker: DecoratorOnly):
            calls.append("decorator")
            self.inner = inner

    def decorator_filter(component):
        calls.append("decorator-filter")
        return True

    builder = ContainerBuilder()
    builder.register(Resource, tags=[Tag("resource", "primary")])
    builder.register(DecoratorOnly)
    builder.register(Target)
    source_id = builder.register(Source, tags=[Tag("family", "database")])
    builder.register_decorator(Target, Decorator, decorated_arg="inner", when=decorator_filter)
    compiler = _Compiler(_prepared(builder))
    source = compiler._compile_source_core(source_id, Source)
    source_filter = (
        cf.has_tag("family", "database")
        & cf.has_descendant(cf.has_tag("resource", "primary"))
        & ~cf.parent(cf.all_components)
    )
    assert source_filter(source)
    assert [item.service_type for item in source.descendants()] == [Target, Resource]
    assert source.parent is None
    assert calls == []
    assert source._graph._records is not None
    assert source._graph._drafts == {}
    with pytest.raises(RuntimeError, match="cannot publish"):
        compiler.compile()
    with pytest.raises(RuntimeError, match="fresh compiler"):
        compiler._compile_source_core(source_id, Source)

    container = builder.build()
    assert calls and all(call == "decorator-filter" for call in calls)
    source_instance = container.resolve(Source)
    assert isinstance(source_instance.target, Decorator)
    assert calls[-1] == "source"


def test_source_factory_and_instance_are_inspected_without_running_the_factory():
    class Source:
        pass

    def factory() -> Source:
        raise AssertionError("Source factory must never run during compilation")

    builder = ContainerBuilder()
    factory_id = builder.register(Source, factory=factory, name="factory", tags=[Tag("backend", "opaque")])
    instance_id = builder.register(Source, instance=Source(), name="instance")
    blueprint = _prepared(builder)
    factory_core = _core(blueprint, factory_id, Source)
    instance_core = _core(blueprint, instance_id, Source)
    assert cf.has_tag("backend", "opaque")(factory_core)
    assert factory_core.implementation_type is Source
    assert instance_core.implementation_type is Source
    assert factory_core.id != instance_core.id


def test_source_core_requires_exact_closed_definition_key():
    T = TypeVar("T")

    class Source(Generic[T]):
        pass

    builder = ContainerBuilder()
    closed_id = builder.register(Source[int])
    open_id = builder.register(Source)
    blueprint = _prepared(builder)
    assert _core(blueprint, closed_id, Source[int]).service_type == Source[int]
    with pytest.raises(ValueError, match="exact closed service key"):
        _core(blueprint, closed_id, Source[str])
    with pytest.raises(ValueError, match="exact closed service key"):
        _core(blueprint, open_id, Source)


def test_canonical_source_does_not_apply_root_condition_but_exact_injection_does():
    class Source:
        pass

    class Target:
        pass

    class Decorator:
        def __init__(self, inner: Target, source: Source):
            self.source = source

    builder = ContainerBuilder()
    selected_id = builder.register(Source, when=cf.parent(cf.implementation_type_is(Decorator)))
    builder.register(Source)  # Exact source selection must not choose this fallback.
    builder.register(Target)
    inspected = _core(_prepared(builder), selected_id, Source)
    assert inspected.parent is None
    builder.register_decorator(
        Target, Decorator, decorated_arg="inner", arguments={"source": select(cf.with_id(selected_id))}
    )
    assert isinstance(cast(Decorator, builder.build().resolve(Target)).source, Source)

    rejected = ContainerBuilder()
    unavailable = rejected.register(Source, when=cf.parent(cf.implementation_type_is(Target)))
    rejected.register(Source)
    rejected.register(Target)
    assert _core(_prepared(rejected), unavailable, Source).id == unavailable
    rejected.register_decorator(
        Target, Decorator, decorated_arg="inner", arguments={"source": select(cf.with_id(unavailable))}
    )
    with pytest.raises(ContainerBuildError):
        rejected.build()


@pytest.mark.parametrize("matching", [False, True])
def test_source_to_target_is_safe_in_core_phase_and_actual_activation_cycle_is_deterministic(matching):
    class Target:
        pass

    class Source:
        def __init__(self, target: Target):
            self.target = target

    class Decorator:
        def __init__(self, inner: Target, source: Source):
            self.inner = inner
            self.source = source

    builder = ContainerBuilder()
    builder.register(Target)
    source_id = builder.register(Source)
    source = _core(_prepared(builder), source_id, Source)
    assert [item.service_type for item in source.descendants()] == [Target]
    builder.register_decorator(
        Target,
        Decorator,
        decorated_arg="inner",
        arguments={"source": select(cf.with_id(source_id))},
        when=lambda _: matching,
    )
    if not matching:
        assert isinstance(builder.build().resolve(Source).target, Target)
        return
    failures = []
    for _ in range(2):
        with pytest.raises(ContainerBuildError) as captured:
            builder.build()
        report = captured.value.report
        assert report is not None
        failures.append(tuple((issue.code, issue.path) for issue in report.errors))
    assert failures[0] == failures[1]
    assert all(code == "circular-dependency" for code, _ in failures[0])


def test_source_core_respects_boundary_local_dependencies_and_visibility():
    class Resource:
        pass

    class Source:
        def __init__(self, resource: Resource):
            self.resource = resource

    ids = {}

    def private(builder):
        builder.register(Resource, tags=[Tag("area", "private")])
        ids["source"] = builder.register(Source)

    builder = ContainerBuilder()
    builder.register(Resource, tags=[Tag("area", "root")])
    builder.create_boundary("private").apply_bundle(private)
    blueprint = _prepared(builder)
    assert blueprint.registrations(Source) == []
    visible = blueprint.registrations(Source, "private")
    assert [registration.id for registration, _ in visible] == [ids["source"]]
    source = _core(blueprint, ids["source"], Source)
    assert source.boundary == "private"
    assert cf.has_descendant(cf.has_tag("area", "private"))(source)
    assert not cf.has_descendant(cf.has_tag("area", "root"))(source)

    exported = ContainerBuilder()
    exported.create_boundary("provider", exposes=(Expose(Source),)).apply_bundle(private)
    exported.create_boundary("consumer", uses=(Use("provider", Source),)).apply_bundle(lambda _: None)
    blueprint = _prepared(exported)
    assert [registration.id for registration, _ in blueprint.registrations(Source, "consumer")] == [ids["source"]]
    source = _core(blueprint, ids["source"], Source)
    assert source.boundary == "provider"
    assert source.parent is None


def test_overlay_source_core_preserves_anchored_dependencies_and_skips_frozen_decorators():
    class Resource:
        pass

    class Marker:
        pass

    class Source:
        def __init__(self, resource: Resource):
            self.resource = resource

    class Decorator:
        def __init__(self, inner: Source, marker: Marker):
            self.inner = inner

    class Consumer:
        def __init__(self, source: Source):
            self.source = source

    builder = ContainerBuilder()
    builder.register(Consumer)
    parent_resource = builder.register(Resource, lifespan="singleton", tags=[Tag("area", "parent")])
    builder.register(Marker, lifespan="singleton")
    source_id = builder.register(Source, lifespan="singleton")
    builder.register_decorator(Source, Decorator, decorated_arg="inner")
    parent = builder.build()
    existing = parent.resolve(Source)
    overlay = parent.new_scope_builder()
    overlay.register(Resource, lifespan="singleton", tags=[Tag("area", "overlay")])
    blueprint = _Blueprint((overlay._layer(), *parent._plan.blueprint.layers))
    anchors = _anchored_singletons(parent._plan)
    anchored = next(step for step in anchors.values() if step.component.id == source_id)
    assert anchored.component.argument == "source"
    source = _core(
        blueprint,
        source_id,
        Source,
        anchored_singletons=anchors,
        anchored_pre_configurations=_anchored_pre_configurations(parent._plan),
        anchored_owner_tokens=frozenset(parent._owners),
    )
    assert source.decorators == ()
    assert source.parent is None
    assert source.argument is None
    assert source.dependencies[0].argument == "resource"
    assert source.cache_owner == anchored.component.cache_owner
    assert source.cleanup_owner == anchored.component.cleanup_owner
    assert anchored.component.argument == "source"
    assert [item.id for item in source.descendants()] == [parent_resource]
    assert cf.has_descendant(cf.has_tag("area", "parent"))(source)
    assert not cf.has_descendant(cf.has_tag("area", "overlay"))(source)
    scope = overlay.build()
    assert scope.resolve(Source) is existing
    assert len(next(root.component for root in parent.graph.roots if root.component.id == source_id).decorators) == 1


def test_generated_target_view_hides_nested_decorators_and_preserves_occurrence_context():
    class Marker:
        pass

    class Dependency:
        pass

    class DependencyDecorator:
        def __init__(self, inner: Dependency, marker: Marker):
            self.inner = inner

    class Target:
        def __init__(self, dependency: Dependency):
            self.dependency = dependency

    class Consumer:
        def __init__(self, target: Target):
            self.target = target

    class TargetDecorator:
        def __init__(self, inner: Target):
            self.inner = inner

    captured = []

    def ordinary_when(component):
        # Normal compilation has already decorated this target's dependencies.
        # Generated-template predicates must see a separate recursive core view.
        assert cf.has_descendant(cf.implementation_type_is(Marker))(component)
        view = _undecorated_component_view(component)
        assert not cf.has_descendant(cf.implementation_type_is(Marker))(view)
        assert view.id == component.id
        assert view.occurrence_id == component.occurrence_id
        assert view.argument == component.argument
        assert view.dependencies[0].id == component.dependencies[0].id
        assert view.dependencies[0].argument == "dependency"
        assert view.dependencies[0].name == "chosen"
        assert view.cache_owner == component.cache_owner
        if component.parent is not None:
            assert view.parent is not None
            assert view.parent.occurrence_id == component.parent.occurrence_id
            assert view.parent.implementation_type is Consumer
            assert cf.parent(cf.implementation_type_is(Consumer))(view)
        captured.append(view)
        return True

    builder = ContainerBuilder()
    builder.register(Consumer)
    builder.register(Marker)
    builder.register(Dependency, name="chosen")
    builder.register(Dependency, name="other")
    target_id = builder.register(Target, arguments={"dependency": select(cf.with_name("chosen"))})
    builder.register_decorator(Dependency, DependencyDecorator, decorated_arg="inner")
    builder.register_decorator(Target, TargetDecorator, decorated_arg="inner", when=ordinary_when)
    container = builder.build()
    assert len(captured) == 2
    assert any(view.parent is not None for view in captured)
    # The snapshots remain undecorated after runtime compilation adds pipelines.
    assert all(view.decorators == () and view.dependencies[0].decorators == () for view in captured)
    assert all(view._graph._records is not None and not view._graph._drafts for view in captured)
    frozen_target = next(root.component for root in container.graph.roots if root.component.id == target_id)
    assert len(frozen_target.decorators) == len(frozen_target.dependencies[0].decorators) == 1
    frozen_view = _undecorated_component_view(frozen_target)
    assert not cf.has_descendant(cf.implementation_type_is(Marker))(frozen_view)
    assert isinstance(container.resolve(Consumer).target, TargetDecorator)


def test_discovery_snapshot_identity_and_source_deduplication_survive_retries():
    class Source:
        pass

    class First(Source):
        pass

    builder = ContainerBuilder()
    explicit = builder.register(Source, First)
    builder.register_subclasses(Source)

    class Later(Source):
        pass

    snapshots = [_prepared(builder), _prepared(builder)]
    sequences = [[registration.id for registration, _ in snapshot.registrations(Source)] for snapshot in snapshots]
    assert sequences[0] == sequences[1]
    assert sequences[0][0] == explicit
    assert len(sequences[0]) == len(set(sequences[0])) == 3
    assert {_core(snapshots[0], source_id, Source).implementation_type for source_id in sequences[0]} == {First, Later}


def test_visibility_feedback_is_detectable_without_fixed_point_iteration():
    class Source:
        pass

    class Marker:
        pass

    class Decorator:
        def __init__(self, inner: Source, marker: Marker):
            pass

    def boundary(builder):
        builder.register(Source, name="first")
        builder.register(Source, name="second")
        builder.register(Marker)

    # A boundary predicate can observe decorator dependencies. Adding generated
    # decorators after selection can therefore invalidate the visibility seed.
    builder = ContainerBuilder()
    builder.create_boundary(
        "provider",
        exposes=(Expose(Source, filter=cf.with_name("first") | cf.has_descendant(cf.implementation_type_is(Marker))),),
    ).apply_bundle(boundary)
    seed = _snapshot(builder)
    prepared = _prepare_boundary_visibility(seed, build_args={})
    assert len(prepared.registrations(Source)) == 1
    generated = ContainerBuilder()
    generated.register_decorator(Source, Decorator, decorated_arg="inner")
    modified = replace(
        seed.boundaries[0], layer=replace(seed.boundaries[0].layer, decorators=generated._layer().decorators)
    )
    with pytest.raises(ContainerBuildError) as captured:
        _prepare_boundary_visibility(replace(seed, boundaries=(modified,)), build_args={})
    assert captured.value.code == "boundary-expose-ambiguous"


def test_generic_projection_preserves_independent_same_named_variables_and_generated_subclasses():
    # Deliberately identical names in distinct binding domains.
    SourceT = TypeVar("T")  # ty: ignore[mismatched-type-name]
    TargetT = TypeVar("T")  # ty: ignore[mismatched-type-name]
    ResultT = TypeVar("ResultT")

    class Source(Generic[SourceT]):
        pass

    class Operation(Generic[TargetT, ResultT]):
        pass

    class Command(Operation[TargetT, bool]):
        pass

    class Generated(Source[int]):
        pass

    class Grandchild(Generated):
        pass

    source_binding = get_args(_project_service_type(Grandchild, Source))
    target_binding = get_args(_project_service_type(Command[str], Operation))
    assert source_binding == (int,)
    assert target_binding == (str, bool)
    assert SourceT is not TargetT
    assert _project_service_type(Command, Operation) == Operation[TargetT, bool]
    assert _project_service_type(Source[int], Source) == Source[int]
    assert _project_service_type(str, Operation) is None
    assert _project_service_type(list[int], list) == list[int]


def test_source_compilation_keeps_closed_aliases_and_generated_implementation_bindings():
    T = TypeVar("T")

    class Port:
        pass

    class Source(Port, Generic[T]):
        pass

    class Generated(Source[str]):
        pass

    builder = ContainerBuilder()
    alias_id = builder.register(Port, Source[int], name="closed")
    generated_id = builder.register(Port, Generated, name="generated")
    blueprint = _prepared(builder)
    alias = _core(blueprint, alias_id, Port)
    generated = _core(blueprint, generated_id, Port)
    assert alias.implementation == Source[int]
    assert _project_service_type(alias.implementation, Source) == Source[int]
    assert generated.implementation is Generated
    assert _project_service_type(generated.implementation, Source) == Source[str]


def test_generic_projection_rejects_conflicting_paths_but_accepts_consistent_diamonds():
    T = TypeVar("T")

    class Base(Generic[T]):
        pass

    class Left(Base[int]):
        pass

    class Right(Base[str]):
        pass

    class Conflict(Left, Right):  # ty: ignore[invalid-generic-class]
        pass

    class Same(Base[int]):
        pass

    class Diamond(Left, Same):
        pass

    with pytest.raises(ValueError, match="Ambiguous service projection"):
        _project_service_type(Conflict, Base)
    assert _project_service_type(Diamond, Base) == Base[int]
