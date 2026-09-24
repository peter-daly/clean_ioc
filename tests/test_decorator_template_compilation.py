import sys
from collections.abc import AsyncIterator, Iterator
from typing import Any, Generic, TypeVar, cast

import pytest
from typing_extensions import TypeVar as ExtensionTypeVar

from clean_ioc import (
    Boundary,
    ContainerBuilder,
    ContainerBuildError,
    DecoratorTemplate,
    DerivedServices,
    Expose,
    RegistrationInfo,
    ServiceGroup,
    Use,
    select,
)
from clean_ioc import component_filters as cf


class Source:
    pass


class FirstSource(Source):
    pass


class SecondSource(Source):
    pass


class FirstResource:
    pass


class SecondResource:
    pass


class Target:
    pass


class FirstTarget(Target):
    def __init__(self, resource: FirstResource):
        self.resource = resource


class SecondTarget(Target):
    def __init__(self, resource: SecondResource):
        self.resource = resource


class BothTarget(Target):
    def __init__(self, first: FirstResource, second: SecondResource):
        self.first, self.second = first, second


class Wrapper(Target):
    def __init__(self, inner: Target, source: Source):
        self.inner, self.source = inner, source


def unwrap(value):
    sources = []
    while isinstance(value, Wrapper):
        sources.append(value.source)
        value = value.inner
    return sources, value


@pytest.mark.parametrize("reverse", [False, True])
@pytest.mark.parametrize("derived", [False, True])
def test_two_families_exact_instances_resource_filters_membership_and_order(reverse, derived):
    builder = ContainerBuilder()
    group = ServiceGroup("targets", service_type=Target)
    selector = DerivedServices(Target) if derived else group
    calls = []
    first, second = FirstSource(), SecondSource()
    sources = [first, second]
    if reverse:
        sources.reverse()
    for index, source in enumerate(sources):
        builder.register(Source, instance=source, name=str(index))
    builder.register(FirstResource)
    builder.register(SecondResource)
    for name, implementation in [
        ("first", FirstTarget),
        ("second", SecondTarget),
        ("both", BothTarget),
        ("neither", Target),
    ]:
        builder.register(Target, implementation, name=name, groups=[group, group])
    builder.register(Target, FirstTarget, name="nonmember")
    builder.register(Target, BothTarget, name="optout", groups=[group])

    def install(family, resource):
        def template(source: RegistrationInfo):
            calls.append(source.id)
            return DecoratorTemplate(
                selector,
                Wrapper,
                arguments={"source": select(cf.with_id(source.id))},
                when=lambda component: component.name != "optout" and component.has_dependant_service_type(resource),
            )

        builder.register_decorator_template(
            for_each=Source, source_filter=cf.implementation_type_is(family), template=template
        )

    install(FirstSource, FirstResource)
    install(SecondSource, SecondResource)
    container = builder.build()
    assert len(calls) == 2
    for name, expected in [
        ("first", [first]),
        ("second", [second]),
        ("both", [first, second]),
        ("neither", []),
        ("optout", []),
        ("nonmember", [first] if derived else []),
    ]:
        actual, core = unwrap(container.resolve(Target, filter=cf.with_name(name)))
        assert actual == expected
        assert isinstance(core, Target)
    assert len(calls) == 2
    assert len(container._plan.blueprint.generated_decorators) == 2
    assert len(container._plan.blueprint.template_selections) == 4


@pytest.mark.parametrize("reverse_policies", [False, True])
@pytest.mark.parametrize("derived", [False, True])
def test_family_templates_keep_distinct_decorators_positions_and_resource_filters(reverse_policies, derived):
    class FirstPolicy(Wrapper):
        pass

    class SecondPolicy(Wrapper):
        pass

    builder = ContainerBuilder()
    group = ServiceGroup("targets", service_type=Target)
    selector = DerivedServices(Target) if derived else group
    first, second = FirstSource(), SecondSource()
    first_id = builder.register(Source, instance=first, name="shared")
    second_id = builder.register(Source, instance=second, name="shared")
    builder.register(FirstResource)
    builder.register(SecondResource)
    for name, implementation in (
        ("first", FirstTarget),
        ("second", SecondTarget),
        ("both", BothTarget),
        ("neither", Target),
    ):
        builder.register(Target, implementation, name=name, groups=[group])

    calls = []
    policies = (
        (FirstSource, FirstResource, FirstPolicy, -7, first_id),
        (SecondSource, SecondResource, SecondPolicy, 19, second_id),
    )
    if reverse_policies:
        policies = tuple(reversed(policies))
    for family, resource, decorator, position, expected_id in policies:

        def template(source, *, resource=resource, decorator=decorator, position=position, expected_id=expected_id):
            calls.append(source.id)
            assert source.id == expected_id
            return DecoratorTemplate(
                selector,
                decorator,
                arguments={"source": select(cf.with_id(source.id))},
                when=cf.has_descendant(cf.service_type_is(resource)),
                position=position,
            )

        builder.register_decorator_template(
            for_each=Source,
            source_filter=cf.implementation_type_is(family),
            template=template,
        )

    container = builder.build()
    assert calls == ([second_id, first_id] if reverse_policies else [first_id, second_id])
    for name, expected in (
        ("first", [(FirstPolicy, first)]),
        ("second", [(SecondPolicy, second)]),
        ("both", [(SecondPolicy, second), (FirstPolicy, first)]),
        ("neither", []),
    ):
        result = container.resolve(Target, filter=cf.with_name(name))
        actual = []
        while isinstance(result, Wrapper):
            actual.append((type(result), result.source))
            result = result.inner
        assert actual == expected
        assert isinstance(result, Target)
    assert len(calls) == 2


def test_same_class_sources_shared_order_additive_templates_and_public_edits():
    builder = ContainerBuilder()
    first, second = Source(), Source()
    builder.register(Source, instance=first, name="first")
    builder.register(Source, instance=second, name="second")
    core = Target()
    builder.register(Target, instance=core)

    def template(source):
        return DecoratorTemplate(DerivedServices(Target), Wrapper, arguments={"source": select(cf.with_id(source.id))})

    removed = builder.register_decorator_template(for_each=Source, template=template)
    builder.remove_decorator_template(removed)
    with pytest.raises(KeyError):
        builder.remove_decorator_template(removed)
    first_template = builder.register_decorator_template(for_each=Source, template=template)
    builder.patch_decorator_template(first_template, source_filter=cf.all_components)
    ordinary = Source()
    builder.register_decorator(Target, Wrapper, arguments={"source": ordinary})
    builder.register_decorator_template(for_each=Source, template=template)
    container = builder.build()
    sources, actual_core = unwrap(container.resolve(Target))
    assert sources == [first, second, ordinary, first, second]
    assert actual_core is core


T = TypeVar("T")
R = TypeVar("R")
OtherT = TypeVar("T")  # ty: ignore[mismatched-type-name]


class Operation(Generic[T, R]):
    pass


class Child(Operation[T, str], Generic[T]):
    pass


class Backend(Source, Generic[OtherT]):
    pass


class GenericWrapper(Operation[T, R], Generic[T, R, OtherT]):
    def __init__(self, inner: Operation[T, R], source: Source, resource: OtherT):
        self.inner, self.source, self.resource = inner, source, resource


@pytest.mark.parametrize("target_kind", ["constructor", "factory", "instance", "pattern", "open"])
@pytest.mark.parametrize("derived", [False, True])
def test_projected_generics_partial_source_alias_distinct_same_name_variables(target_kind, derived):
    builder = ContainerBuilder()
    backend = Backend[FirstResource]()
    builder.register(Source, instance=backend)
    resource = FirstResource()
    builder.register(FirstResource, instance=resource)
    core = Child[int]()
    group = ServiceGroup("generic-targets", service_type=Operation)
    if target_kind == "constructor":
        builder.register(Child[int], groups=[group])
    elif target_kind == "factory":

        def factory() -> Child[int]:
            return core

        builder.register(Child[int], factory=factory, groups=[group])
    elif target_kind == "instance":
        builder.register(Child[int], instance=core, groups=[group])
    else:

        def pattern() -> Child[T]:
            return Child()

        if target_kind == "open":
            builder.register(Child, groups=[group])
        else:
            builder.register_pattern(Child[T], factory=pattern, groups=[group])

        class Consumer:
            def __init__(self, child: Child[int]):
                self.child = child

        builder.register(Consumer)

    def template(source):
        bindings = source.implementation_bindings(Backend)
        assert bindings is not None and bindings[OtherT] is FirstResource
        return DecoratorTemplate(
            DerivedServices(Operation) if derived else group,
            cast(Any, GenericWrapper)[T, R, bindings[OtherT]],
            arguments={"source": select(cf.with_id(source.id))},
        )

    builder.register_decorator_template(for_each=Source, template=template)
    container = builder.build()
    wrapped = container.resolve(Consumer).child if target_kind == "open" else container.resolve(Child[int])
    assert isinstance(wrapped, GenericWrapper)
    assert isinstance(wrapped.inner, Child)
    assert wrapped.source is backend and wrapped.resource is resource
    if target_kind in ("instance", "factory"):
        assert wrapped.inner is core


def test_callable_decorator_result_uses_projected_base_contract():
    builder = ContainerBuilder()
    source = Source()
    builder.register(Source, instance=source)
    builder.register(Child[int])

    def wrapper(inner: Operation[T, R], source: Source) -> Operation[T, R]:
        return GenericWrapper(inner, source, None)

    builder.register_decorator_template(
        for_each=Source,
        template=lambda info: DecoratorTemplate(
            DerivedServices(Operation),
            wrapper,
            arguments={"source": select(cf.with_id(info.id))},
        ),
    )
    result = builder.build().resolve(Child[int])
    assert isinstance(result, GenericWrapper)
    assert isinstance(result.inner, Child)
    assert result.source is source


@pytest.mark.parametrize("declaration", ["use", "expose"])
@pytest.mark.parametrize("derived", [False, True])
@pytest.mark.parametrize("ambiguous", [False, True])
def test_actual_generated_boundary_effect_rejected_once_with_cause(declaration, derived, ambiguous):
    builder = ContainerBuilder()
    group = ServiceGroup("boundary-targets", service_type=Target)
    calls = []

    class Added:
        def __init__(self, inner: Target, marker: FirstResource):
            pass

    def selection(component):
        decorated = component.has_dependant_service_type(FirstResource)
        return (component.name == "one" or decorated) if ambiguous else ((component.name == "one") != decorated)

    ids = []

    def compose(private):
        ids.extend(
            [private.register(Target, name="one", groups=[group]), private.register(Target, name="two", groups=[group])]
        )
        private.register(Source)
        private.register(FirstResource)
        private.register_decorator_template(
            for_each=Source,
            template=lambda source: (
                calls.append(source.id),
                DecoratorTemplate(
                    DerivedServices(Target) if derived else group,
                    Added,
                ),
            )[1],
        )

    if declaration == "use":
        compose(builder)
        builder.install_boundary(Boundary("consumer", lambda _: None, uses=(Use(None, Target, filter=selection),)))
    else:
        builder.install_boundary(Boundary("provider", compose, exposes=(Expose(Target, filter=selection),)))
    with pytest.raises(ContainerBuildError) as caught:
        builder.build()
    error = caught.value
    assert error.report is not None
    assert error.report.errors[0].code == "template-visibility-cycle"
    assert len(calls) == 1
    assert any(calls[0] in piece for piece in error.report.errors[0].path)
    if ambiguous:
        assert isinstance(error.__cause__, ContainerBuildError)
        assert isinstance(error.__cause__.__cause__, ContainerBuildError)
        assert error.__cause__.__cause__.code == f"boundary-{declaration}-ambiguous"


def test_exact_source_condition_has_no_fallback_and_runtime_callbacks_do_not_replay():
    builder = ContainerBuilder()
    calls = []
    rejected = builder.register(Source, when=cf.parent(cf.implementation_type_is(Target)))
    builder.register(Source)
    builder.register(Target)
    builder.register_decorator_template(
        for_each=Source,
        source_filter=cf.with_id(rejected),
        template=lambda source: (
            calls.append(source.id),
            DecoratorTemplate(
                DerivedServices(Target),
                Wrapper,
                arguments={"source": select(cf.with_id(source.id))},
            ),
        )[1],
    )
    with pytest.raises(ContainerBuildError):
        builder.build()
    assert calls == [rejected]


def test_generated_activation_cycle_retains_code_and_provenance():
    class CyclicSource(Source):
        def __init__(self, target: Target):
            pass

    builder = ContainerBuilder()
    source = builder.register(Source, CyclicSource)
    builder.register(Target)
    template = builder.register_decorator_template(
        for_each=Source,
        template=lambda info: DecoratorTemplate(
            DerivedServices(Target),
            Wrapper,
            arguments={"source": select(cf.with_id(info.id))},
        ),
    )
    with pytest.raises(ContainerBuildError) as caught:
        builder.build()
    assert caught.value.report is not None
    errors = caught.value.report.errors
    assert any(error.code == "circular-dependency" for error in errors)
    assert any(template in error.path and source in error.path for error in errors)


@pytest.mark.parametrize("fail", [False, True])
def test_sync_cleanup_and_failure_cleanup(fail):
    events = []

    def resource() -> Iterator[Source]:
        events.append("source-open")
        try:
            yield Source()
        finally:
            events.append("source-close")

    def wrapper(inner: Target, source: Source) -> Iterator[Target]:
        events.append("wrapper-open")
        if fail:
            raise ValueError("failure")
        try:
            yield Wrapper(inner, source)
        finally:
            events.append("wrapper-close")

    builder = ContainerBuilder()
    builder.register(Source, factory=resource)
    builder.register(Target)
    builder.register_decorator_template(
        for_each=Source,
        template=lambda info: DecoratorTemplate(
            DerivedServices(Target),
            wrapper,
            arguments={"source": select(cf.with_id(info.id))},
        ),
    )
    with builder.build() as container:
        if fail:
            with pytest.raises(ValueError):
                container.resolve(Target)
        else:
            assert isinstance(container.resolve(Target), Wrapper)
    assert events == ["source-open", "wrapper-open", *([] if fail else ["wrapper-close"]), "source-close"]


@pytest.mark.asyncio
@pytest.mark.parametrize("fail", [False, True])
async def test_async_cleanup_and_failure_cleanup(fail):
    events = []

    async def resource() -> AsyncIterator[Source]:
        events.append("source-open")
        try:
            yield Source()
        finally:
            events.append("source-close")

    async def wrapper(inner: Target, source: Source) -> AsyncIterator[Target]:
        events.append("wrapper-open")
        if fail:
            raise ValueError("failure")
        try:
            yield Wrapper(inner, source)
        finally:
            events.append("wrapper-close")

    builder = ContainerBuilder()
    builder.register(Source, factory=resource)
    builder.register(Target)
    builder.register_decorator_template(
        for_each=Source,
        template=lambda info: DecoratorTemplate(
            DerivedServices(Target),
            wrapper,
            arguments={"source": select(cf.with_id(info.id))},
        ),
    )
    async with builder.build() as container:
        if fail:
            with pytest.raises(ValueError):
                await container.resolve_async(Target)
        else:
            assert isinstance(await container.resolve_async(Target), Wrapper)
    assert events == ["source-open", "wrapper-open", *([] if fail else ["wrapper-close"]), "source-close"]


def test_when_snapshot_reused_recursive_undecoration_parent_context_and_scale(monkeypatch):
    import clean_ioc.container as implementation

    class Dependency:
        pass

    class DecoratedDependency:
        def __init__(self, inner: Dependency, resource: SecondResource):
            self.inner = inner

    class DependentTarget(Target):
        def __init__(self, dependency: Dependency, resource: FirstResource):
            pass

    class Consumer:
        def __init__(self, target: Target):
            pass

    builder = ContainerBuilder()
    # Unrelated completed roots must not leak into an occurrence snapshot.
    for index in range(80):
        builder.register(Source, name=str(index))
    builder.register(FirstResource)
    builder.register(SecondResource)
    builder.register(Dependency)
    builder.register_decorator(Dependency, DecoratedDependency)
    target_id = builder.register(Target, DependentTarget)
    builder.register(Consumer)
    views = []
    original = implementation._undecorated_component_view
    snapshots = []

    def snapshot(core):
        value = original(core)
        snapshots.append(value)
        return value

    monkeypatch.setattr(implementation, "_undecorated_component_view", snapshot)

    def predicate(component):
        views.append(component)
        assert component.id == target_id
        assert component.has_dependant_service_type(FirstResource)
        assert not component.has_dependant_service_type(SecondResource)
        assert all(not node.decorators for node in component.descendants())
        if component.parent is not None:
            assert component.parent.implementation_type is Consumer
            assert component.argument == "target"
        assert len(component._graph._records) < 12
        return False

    for _ in range(2):
        builder.register_decorator_template(
            for_each=Source,
            source_filter=cf.with_name("0"),
            template=lambda _: DecoratorTemplate(
                DerivedServices(Target),
                Wrapper,
                when=predicate,
            ),
        )
    ordinary_saw = []
    builder.register_decorator(
        Target,
        Wrapper,
        arguments={"source": Source()},
        when=lambda core: ordinary_saw.append(core.has_dependant_service_type(SecondResource)) or False,
    )
    container = builder.build()
    assert snapshots
    assert len(views) == 2 * len(snapshots)
    assert all(views[index] is views[index + 1] for index in range(0, len(views), 2))
    assert any(view.parent is not None for view in snapshots)
    assert all(ordinary_saw)
    before = len(views)
    container.resolve(Consumer)
    _ = container.graph.roots
    assert len(views) == before


def test_no_eligible_generated_candidate_skips_snapshot(monkeypatch):
    import clean_ioc.container as implementation

    def forbidden(_):
        raise AssertionError("No eligible target may make a snapshot")

    monkeypatch.setattr(implementation, "_undecorated_component_view", forbidden)
    builder = ContainerBuilder()
    builder.register(Source)
    builder.register(Target)
    group = ServiceGroup("no-members", service_type=Target)
    builder.register_decorator_template(for_each=Source, template=lambda _: DecoratorTemplate(group, Wrapper))
    assert isinstance(builder.build().resolve(Target), Target)


@pytest.mark.parametrize("templates_first", [False, True])
def test_source_target_declaration_permutations_and_preview(templates_first):
    builder = ContainerBuilder()
    calls = []

    def template(source):
        calls.append(source.id)
        return DecoratorTemplate(DerivedServices(Target), Wrapper, arguments={"source": select(cf.with_id(source.id))})

    if templates_first:
        builder.register_decorator_template(for_each=Source, template=template)
    builder.register(Target)
    source_id = builder.register(Source)
    if not templates_first:
        builder.register_decorator_template(for_each=Source, template=template)
    assert builder.has_component(Target, filter=lambda component: len(component.decorators) == 1)
    assert calls == [source_id]
    runtime = builder.build()
    assert calls == [source_id, source_id]
    assert isinstance(runtime.resolve(Target), Wrapper)
    assert calls == [source_id, source_id]


def test_exact_source_arguments_and_lifespan_retained():
    class ConfiguredSource(Source):
        def __init__(self, resource: FirstResource):
            self.resource = resource

    builder = ContainerBuilder()
    chosen, ignored = FirstResource(), FirstResource()
    builder.register(FirstResource, instance=chosen, name="chosen")
    builder.register(FirstResource, instance=ignored)
    source_id = builder.register(
        Source, ConfiguredSource, lifespan="singleton", arguments={"resource": select(cf.with_name("chosen"))}
    )
    builder.register(Target, lifespan="transient")
    builder.register_decorator_template(
        for_each=Source,
        template=lambda info: DecoratorTemplate(
            DerivedServices(Target),
            Wrapper,
            arguments={"source": select(cf.with_id(info.id))},
        ),
    )
    container = builder.build()
    first, second = container.resolve(Target), container.resolve(Target)
    assert isinstance(first, Wrapper) and isinstance(second, Wrapper)
    assert first is not second
    assert first.source is second.source is container.resolve(Source, filter=cf.with_id(source_id))
    assert isinstance(first.source, ConfiguredSource) and first.source.resource is chosen


@pytest.mark.parametrize("invalid", ["ambiguous", "missing", "conflicting", "unknown", "unbound"])
def test_generated_argument_validation_and_provenance(invalid):
    class Ambiguous:
        def __init__(self, left: Target, right: Target):
            pass

    class Conflicting:
        def __init__(self, inner: Source):
            pass

    class Unbound(Generic[T]):
        def __init__(self, inner: Target, other: T):
            pass

    builder = ContainerBuilder()
    source_id = builder.register(Source)
    builder.register(Target)
    options: dict[str, dict[str, Any]] = {
        "ambiguous": {"decorator_type": Ambiguous},
        "missing": {"decorator_type": Wrapper, "decorated_arg": "absent"},
        "conflicting": {"decorator_type": Conflicting, "decorated_arg": "inner"},
        "unknown": {"decorator_type": Wrapper, "arguments": {"absent": 1}},
        "unbound": {"decorator_type": Unbound},
    }
    template_id = builder.register_decorator_template(
        for_each=Source,
        template=lambda _: DecoratorTemplate(
            services=DerivedServices(Target),
            **options[invalid],
        ),
    )
    with pytest.raises(ContainerBuildError) as caught:
        builder.build()
    assert caught.value.report is not None
    issue = caught.value.report.errors[0]
    assert issue.code == "invalid-decorator"
    assert source_id in issue.path and template_id in issue.path


def test_callable_decorator_rejects_conflicting_generic_result():
    def wrapper(inner: Operation[T, R]) -> Operation[bytes, float]:
        raise AssertionError("Must fail before activation")

    builder = ContainerBuilder()
    builder.register(Source)
    builder.register(Child[int])
    builder.register_decorator_template(
        for_each=Source,
        template=lambda _: DecoratorTemplate(
            DerivedServices(Operation),
            wrapper,
        ),
    )
    with pytest.raises(ContainerBuildError) as caught:
        builder.build()
    assert caught.value.report is not None
    assert caught.value.report.errors[0].code == "invalid-decorator"


def test_nested_resource_matching_produces_one_layer_and_preserves_position():
    class Nested:
        def __init__(self, first: FirstResource, again: FirstResource):
            pass

    class NestedTarget(Target):
        def __init__(self, nested: Nested):
            pass

    builder = ContainerBuilder()
    source = Source()
    builder.register(Source, instance=source)
    builder.register(FirstResource, lifespan="transient")
    builder.register(Nested)
    builder.register(Target, NestedTarget)
    before, after = Source(), Source()
    builder.register_decorator(Target, Wrapper, position=-10, arguments={"source": before})
    builder.register_decorator_template(
        for_each=Source,
        template=lambda info: DecoratorTemplate(
            DerivedServices(Target),
            Wrapper,
            when=cf.has_descendant(cf.service_type_is(FirstResource)),
            arguments={"source": select(cf.with_id(info.id))},
        ),
    )
    builder.register_decorator(Target, Wrapper, position=10, arguments={"source": after})
    sources, core = unwrap(builder.build().resolve(Target))
    assert sources == [after, source, before]
    assert isinstance(core, NestedTarget)


@pytest.mark.parametrize("overridden", [False, True])
@pytest.mark.parametrize("closed_alias", [False, True])
def test_constructor_annotation_scope_is_separate_from_implementation_scope(overridden, closed_alias):
    from clean_ioc.generic_utils import _project_service_type

    class Extra(Generic[T]):
        pass

    class Base(Generic[T]):
        def __init__(self, inner: Operation[T, str], extra: Extra[T]):
            self.inner, self.extra = inner, extra

    class Inherited(Base[list[T]], Generic[T]):
        pass

    class Overridden(Base[list[T]], Generic[T]):
        def __init__(self, inner: Operation[T, str], extra: Extra[T]):
            self.inner, self.extra = inner, extra

    wrapper = Overridden if overridden else Inherited
    decorator_type = wrapper[int] if closed_alias else wrapper
    target_type = Operation[int, str] if overridden else Operation[list[int], str]
    extra_type = Extra[int] if overridden else Extra[list[int]]
    core, extra = target_type(), extra_type()
    builder = ContainerBuilder()
    builder.register(Source)
    builder.register(target_type, instance=core)
    builder.register(extra_type, instance=extra)
    builder.register_decorator_template(
        for_each=Source,
        template=lambda _: DecoratorTemplate(DerivedServices(Operation), decorator_type),
    )
    result = builder.build().resolve(target_type)
    assert isinstance(result, wrapper)
    assert result.inner is core and result.extra is extra
    assert _project_service_type(type(result), wrapper) == wrapper[int]
    assert _project_service_type(type(result), Base) == Base[list[int]]


@pytest.mark.skipif(sys.version_info < (3, 13), reason="TypeVar defaults require Python 3.13+")
@pytest.mark.parametrize("intermediate_argument", [False, True])
def test_dependent_defaults_are_transitive_and_independent_of_argument_order(intermediate_argument):
    DefaultT = TypeVar("DefaultT")
    DefaultU = TypeVar("DefaultU", default=DefaultT)  # ty: ignore[invalid-legacy-type-variable]
    DefaultV = TypeVar("DefaultV", default=DefaultU)  # ty: ignore[invalid-legacy-type-variable]
    calls = []

    def wrapper(
        inner: Operation[DefaultT, str],
        later: DefaultV,  # ty: ignore[invalid-type-variable-default]
        earlier: DefaultU,
    ) -> Operation[DefaultT, str]:
        calls.append((later, earlier))
        return inner

    def only_later(
        inner: Operation[DefaultT, str],
        later: DefaultV,  # ty: ignore[invalid-type-variable-default]
    ) -> Operation[DefaultT, str]:
        calls.append((later,))
        return inner

    builder = ContainerBuilder()
    builder.register(Source)
    core = Operation[int, str]()
    builder.register(Operation[int, str], instance=core)
    builder.register(int, instance=42)
    builder.register_decorator_template(
        for_each=Source,
        template=lambda _: DecoratorTemplate(
            DerivedServices(Operation), wrapper if intermediate_argument else only_later
        ),
    )
    assert builder.build().resolve(Operation[int, str]) is core
    assert calls == [(42, 42) if intermediate_argument else (42,)]


@pytest.mark.skipif(sys.version_info < (3, 13), reason="TypeVar defaults require Python 3.13+")
def test_cyclic_default_fails_clearly_before_activation():
    # The runtime permits arbitrary default objects. A mutable parameter-list
    # default lets us exercise cycle rejection without an endlessly recursive
    # inheritance substitution or a mutable fake TypeVar implementation.
    default: list[Any] = []
    Cyclic = TypeVar("Cyclic", default=default)  # ty: ignore[invalid-type-form, invalid-legacy-type-variable]
    default.append(Cyclic)

    def wrapper(inner: Target, value: Cyclic) -> Target:
        raise AssertionError("Cycle must fail before activation")

    builder = ContainerBuilder()
    builder.register(Source)
    builder.register(Target)
    builder.register_decorator_template(
        for_each=Source, template=lambda _: DecoratorTemplate(DerivedServices(Target), wrapper)
    )
    with pytest.raises(ContainerBuildError) as caught:
        builder.build()
    assert caught.value.report is not None
    assert caught.value.report.errors[0].code == "invalid-decorator"
    assert "Cyclic decorator TypeVar default" in str(caught.value)


def test_generated_predicate_failure_preserves_safe_provenance_and_original_cause():
    builder = ContainerBuilder()
    source_id = builder.register(Source)
    target_id = builder.register(Target)
    source_calls, factory_calls = [], []
    original = RuntimeError("private failure details")

    def predicate(_):
        raise original

    def source_filter(component):
        source_calls.append(component.id)
        return True

    def template(source):
        factory_calls.append(source.id)
        return DecoratorTemplate(DerivedServices(Target), Wrapper, when=predicate)

    template_id = builder.register_decorator_template(for_each=Source, source_filter=source_filter, template=template)
    with pytest.raises(ContainerBuildError) as caught:
        builder.build()
    assert caught.value.report is not None
    assert source_calls == factory_calls == [source_id]
    issues = caught.value.report.errors
    assert all(issue.code == "decorator-filter-failed" for issue in issues)
    assert all(template_id in issue.path and source_id in issue.path and target_id in issue.path for issue in issues)
    assert "private failure details" not in str(caught.value)
    cause = caught.value.__cause__
    while cause is not None and cause is not original:
        cause = cause.__cause__
    assert cause is original
    assert caught.value.partial_graph is not None
    assert all(
        template_id in attempt.witness_path and source_id in attempt.witness_path and target_id in attempt.witness_path
        for attempt in caught.value.partial_graph.attempts
        if not attempt.succeeded
    )


def test_extensions_typevar_without_default_remains_unresolved():
    ExternalT = ExtensionTypeVar("ExternalT")

    def wrapper(inner: Target, missing: ExternalT) -> Target:
        raise AssertionError("Missing binding must fail before activation")

    builder = ContainerBuilder()
    builder.register(Source)
    builder.register(Target)
    builder.register_decorator_template(
        for_each=Source, template=lambda _: DecoratorTemplate(DerivedServices(Target), wrapper)
    )
    with pytest.raises(ContainerBuildError) as caught:
        builder.build()
    assert caught.value.report is not None
    assert caught.value.report.errors[0].code == "invalid-decorator"
    assert "Unresolved decorator TypeVar(s): ExternalT" in str(caught.value)
