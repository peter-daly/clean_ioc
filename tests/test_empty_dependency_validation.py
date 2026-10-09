"""Repeated parameterless infrastructure must not repeatedly parse builtin signatures."""

import inspect
from typing import Any, Generic, TypeVar, cast

import pytest

from clean_ioc import ContainerBuilder, ContainerBuildError
from clean_ioc.container import _validate_dependency_names


class Clock:
    pass


class Prefix:
    pass


class QueueName:
    pass


class Infrastructure:
    def __init__(self, clock: Clock, prefix: Prefix, queue: QueueName):
        self.clock, self.prefix, self.queue = clock, prefix, queue


T = TypeVar("T")


class GenericLeaf(Generic[T]):
    pass


@pytest.mark.parametrize("routes", [4, 32])
@pytest.mark.parametrize("diagnostics", [False, True])
def test_contextual_multi_route_infrastructure_bounds_builtin_signature_parsing(routes, diagnostics, monkeypatch):
    parses = []
    original = getattr(inspect, "_signature_fromstr")

    def count_builtin_parse(*args, **kwargs):
        if args[1] is object:
            parses.append(args[2])
        return original(*args, **kwargs)

    monkeypatch.setattr(inspect, "_signature_fromstr", count_builtin_parse)
    selected, activated = [], []

    def contextual(component):
        # An opaque context-dependent filter must run for every occurrence;
        # repeated helper validation still precedes invariant subplan reuse.
        selected.append((component.parent.parent.service_type, component.argument))
        return True

    builder = ContainerBuilder()
    for leaf in (Clock, Prefix, QueueName):
        builder.register(leaf, when=contextual, lifespan="transient", root_policy="dependency_only")
    builder.register(Infrastructure, lifespan="transient", root_policy="dependency_only")
    route_types: list[Any] = []
    for index in range(routes):

        def route_init(self, left, right):
            activated.append(type(self))
            self.left, self.right = left, right

        route_init.__annotations__ = {"left": Infrastructure, "right": Infrastructure}
        route = type(f"Route{index}", (), {"__init__": route_init})
        builder.register(route)
        route_types.append(route)
    # Registration must still inspect each builtin constructor once to extract
    # its dependencies. Build need not inspect it again for name validation.
    assert len(parses) == 3
    with builder.build(provider_roots=(), diagnostics=diagnostics, allow_scope_builders=False) as owner:
        assert len(parses) == 3
        assert activated == []
        assert selected == [
            (route, argument) for route in route_types for _ in range(2) for argument in ("clock", "prefix", "queue")
        ]
        for route in route_types:
            value = owner.resolve(route)
            assert isinstance(value.left.clock, Clock)
            assert isinstance(value.right.prefix, Prefix)
            assert isinstance(value.left.queue, QueueName)
            assert value.left.clock is not value.right.clock
        assert activated == route_types
        assert len(parses) == 3
        assert owner.graph.manifest(all_roots=True).to_json()


@pytest.mark.parametrize("kind", ["constructor", "generic", "factory"])
def test_invalid_configured_argument_is_rejected_and_builder_can_be_repaired(kind):
    builder = ContainerBuilder()
    service: Any = GenericLeaf[str] if kind == "generic" else Clock
    activated = []

    def factory():
        activated.append(True)
        return Clock()

    options = {"factory": factory} if kind == "factory" else {}
    component_id = builder.register(service, arguments={"typo": 1}, **options)
    with pytest.raises(ContainerBuildError, match="no argument named 'typo'") as raised:
        builder.build(provider_roots=(), aggregate_errors=False)
    assert raised.value.report is not None
    assert raised.value.report.errors[0].code == "invalid-argument"
    assert activated == []
    from clean_ioc import REMOVE

    builder.patch_component(service, component_id, arguments={"typo": REMOVE})
    with builder.build(provider_roots=()) as owner:
        assert activated == []
        assert isinstance(owner.resolve(service), GenericLeaf if kind == "generic" else Clock)
        assert activated == ([True] if kind == "factory" else [])


@pytest.mark.parametrize("kind", ["constructor", "factory", "pre-configuration", "decorator"])
def test_required_dependencies_still_fail_build_without_activation(kind):
    activated = []

    class Missing:
        pass

    class Required:
        def __init__(self, missing: Missing):
            activated.append(True)

    def factory(missing: Missing):
        activated.append(True)
        return Clock()

    def configure(missing: Missing):
        activated.append(True)

    class Decorator:
        def __init__(self, inner: Clock, missing: Missing):
            activated.append(True)
            self.inner = inner

    builder = ContainerBuilder()
    if kind == "constructor":
        builder.register(Required)
    elif kind == "factory":
        builder.register(Clock, factory=factory)
    else:
        builder.register(Clock)
        if kind == "pre-configuration":
            builder.pre_configure(Clock, configure)
        else:
            builder.register_decorator(Clock, Decorator, decorated_arg="inner")
    with pytest.raises(ContainerBuildError, match="Missing"):
        builder.build(provider_roots=(), aggregate_errors=False)
    assert activated == []
    builder.register(Missing, lifespan="singleton")
    with builder.build(provider_roots=()) as owner:
        assert activated == []
        owner.resolve(Required if kind == "constructor" else Clock)
        assert activated == [True]


def test_parameterless_factory_and_pre_configuration_stay_dormant_through_scope_builds():
    activated = []

    def factory():
        activated.append("factory")
        return Clock()

    def configure():
        activated.append("configure")

    builder = ContainerBuilder()
    builder.register(Clock, factory=factory, lifespan="transient")
    builder.pre_configure(Clock, configure)
    with builder.build(provider_roots=()) as owner:
        assert activated == []
        overlay_builder = owner.new_scope_builder()
        overlay_builder.register(Prefix)
        with overlay_builder.build(provider_roots=()) as overlay:
            assert activated == []
            assert isinstance(overlay.resolve(Clock), Clock)
        assert activated == ["configure", "factory"]
        with owner.new_scope() as scope:
            assert isinstance(scope.resolve(Clock), Clock)
        assert activated == ["configure", "factory", "factory"]


@pytest.mark.parametrize("kind", ["factory", "generic"])
def test_configured_extra_arguments_still_work_with_kwargs(kind):
    activated = []

    class Flexible(Generic[T]):
        def __init__(self, **kwargs: Any):
            activated.append(kwargs)

    def factory(**kwargs: Any):
        activated.append(kwargs)
        return Clock()

    builder = ContainerBuilder()
    if kind == "factory":
        builder.register(Clock, factory=factory, arguments={"extra": 7})
    else:
        builder.register(Flexible[str], arguments={"extra": 7})
    with builder.build(provider_roots=()) as owner:
        assert activated == []
        owner.resolve(Clock if kind == "factory" else Flexible[str])
        assert activated == [{"extra": 7}]


@pytest.mark.parametrize("error", [TypeError, ValueError])
def test_uninspectable_nonempty_target_keeps_best_effort_name_validation(error, monkeypatch):
    def uninspectable(target):
        raise error("No signature available")

    monkeypatch.setattr(inspect, "signature", uninspectable)
    # This existing fallback applies only to name validation. Registration's
    # dependency extraction retains its own independent signature checks.
    _validate_dependency_names(Clock, cast(Any, {"configured": object()}))
