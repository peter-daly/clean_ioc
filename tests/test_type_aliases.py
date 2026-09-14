"""Modern type aliases are transparent service-key spellings."""

from __future__ import annotations

import sys
import types
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any, Callable, Generic, NewType, ParamSpec, cast

import pytest
from typing_extensions import TypeAliasType, TypeVar

from clean_ioc import Boundary, ContainerBuilder, ContainerBuildError, Expose, Provider, Use
from clean_ioc import component_filters as cf

T = TypeVar("T")
U = TypeVar("U")


class Repository(Generic[T]):
    pass


Repo = TypeAliasType("Repo", Repository[T], type_params=(T,))
Nested = TypeAliasType("Nested", dict[U, Repo[T]], type_params=(T, U))
IntRepository = TypeAliasType("IntRepository", Repo[int])


class Checkout:
    def __init__(self, repository: IntRepository, provider: Provider[Repo[int]]):
        self.repository = repository
        self.provider = provider


@pytest.mark.parametrize("registered, requested", [(IntRepository, Repository[int]), (Repository[int], IntRepository)])
def test_alias_and_target_are_interchangeable_and_share_singleton(registered, requested):
    builder = ContainerBuilder()
    component_id = builder.register(registered, lifespan="singleton")
    builder.register(Checkout)

    assert builder.has_component(requested)
    assert builder.get_component_id(IntRepository) == component_id
    with builder.build() as container:
        value = container.resolve(requested)
        checkout = container.resolve(Checkout)
        assert checkout.repository is value
        assert checkout.provider() is value
        assert container.resolve(IntRepository) is value
        assert container.has_component(Repo[int])
        assert cf.service_type_is(IntRepository)(
            next(component for component in container.components if component.id == component_id)
        )
        checkout_component = next(component for component in container.components if component.service_type is Checkout)
        repository_dependency = next(
            dependency for dependency in checkout_component.dependencies if dependency.argument == "repository"
        )
        assert "IntRepository ->" in container.graph.explain(repository_dependency).subject


def test_nested_and_reordered_generic_alias_parameters_use_identity_bindings():
    assert Nested[str, int].__origin__ is Nested
    builder = ContainerBuilder()
    builder.register(dict[int, Repository[str]], instance={1: Repository[str]()})
    with builder.build() as container:
        assert container.resolve(Nested[str, int]) is container.resolve(dict[int, Repository[str]])


def test_independent_same_named_parameters_and_defaults_do_not_collide():
    inner_parameter = TypeVar("Value")  # ty: ignore[mismatched-type-name]
    outer_parameter = TypeVar("Value")  # ty: ignore[mismatched-type-name]
    default_parameter = TypeVar("DefaultValue", default=str)  # ty: ignore[mismatched-type-name]
    inner = TypeAliasType("inner", list[inner_parameter], type_params=(inner_parameter,))
    outer = TypeAliasType(
        "outer",
        tuple[outer_parameter, inner[str]],
        type_params=(outer_parameter,),
    )
    defaulted = TypeAliasType("defaulted", Repository[default_parameter], type_params=(default_parameter,))
    builder = ContainerBuilder()
    pair = (1, ["value"])
    repository = Repository[str]()
    builder.register(tuple[int, list[str]], instance=pair)
    builder.register(Repository[str], instance=repository)
    with builder.build() as container:
        assert container.resolve(outer[int]) is pair
        assert container.resolve(defaulted) is repository


def test_alias_around_provider_is_a_runtime_spelling_of_the_frozen_provider_root():
    ProviderAlias = TypeAliasType("ProviderAlias", Provider[IntRepository])  # noqa: N806
    builder = ContainerBuilder()
    builder.register(Repository[int], lifespan="singleton")
    with builder.build() as container:
        provider = container.resolve(ProviderAlias)
        assert provider() is container.resolve(IntRepository)


def test_union_collection_factory_and_decorator_type_positions_are_normalized():
    class First:
        pass

    class Second:
        pass

    service_key = First | Second
    ServiceAlias = TypeAliasType("ServiceAlias", service_key)  # noqa: N806
    Services = TypeAliasType("Services", list[ServiceAlias])  # noqa: N806

    class Consumer:
        def __init__(self, services: Services):
            self.services = services

    Consumer.__init__.__annotations__["services"] = Services

    class Decorator:
        def __init__(self, child: ServiceAlias):
            self.child = child

    Decorator.__init__.__annotations__["child"] = ServiceAlias
    DecoratorAlias = TypeAliasType("DecoratorAlias", Decorator)  # noqa: N806

    def factory() -> ServiceAlias:
        return First()

    factory.__annotations__["return"] = ServiceAlias
    builder = ContainerBuilder()
    component_id = builder.register(ServiceAlias, factory=factory)
    builder.patch_component(service_key, component_id, lifespan="singleton")
    decorator_id = builder.register_decorator(ServiceAlias, DecoratorAlias)
    builder.patch_decorator(service_key, decorator_id, position=5)
    builder.register(Consumer)
    with builder.build() as container:
        decorated = container.resolve(service_key)
        assert isinstance(decorated, Decorator)
        assert isinstance(decorated.child, First)
        assert container.resolve(Consumer).services[0] is decorated


def test_class_valued_service_and_implementation_aliases_construct_the_canonical_class():
    class Contract:
        pass

    class Implementation(Contract):
        pass

    ContractAlias = TypeAliasType("ContractAlias", Contract)  # noqa: N806
    ImplementationAlias = TypeAliasType("ImplementationAlias", Implementation)  # noqa: N806
    builder = ContainerBuilder()
    builder.register(ContractAlias, ImplementationAlias, lifespan="singleton")
    with builder.build() as container:
        value = container.resolve(Contract)
        assert type(value) is Implementation
        assert container.resolve(ContractAlias) is value
        assert cf.implementation_type_is(ImplementationAlias)(container.components[0])


def test_generator_factory_alias_result_and_cleanup_ownership():
    class Resource:
        pass

    ResourceAlias = TypeAliasType("ResourceAlias", Resource)  # noqa: N806
    ResourceIterator = TypeAliasType("ResourceIterator", Iterator[ResourceAlias])  # noqa: N806
    events = []

    @contextmanager
    def resource() -> ResourceIterator:
        events.append("open")
        try:
            yield Resource()
        finally:
            events.append("close")

    cast(Any, resource).__wrapped__.__annotations__["return"] = ResourceIterator
    resource.__annotations__["return"] = ResourceIterator
    builder = ContainerBuilder()
    builder.register(ResourceAlias, factory=resource, lifespan="singleton")
    with builder.build() as container:
        assert isinstance(container.resolve(Resource), Resource)
        assert events == ["open"]
    assert events == ["open", "close"]


def test_alias_and_canonical_compositions_have_identical_semantic_manifests():
    class Service:
        pass

    Alias = TypeAliasType("Alias", Service)  # noqa: N806

    def manifest(key):
        builder = ContainerBuilder()
        builder.register(key)
        builder.mark_entrypoint(key)
        return builder.build().graph.manifest()

    canonical = manifest(Service)
    aliased = manifest(Alias)
    assert canonical.to_json() == aliased.to_json()
    assert canonical.fingerprint == aliased.fingerprint

    builder = ContainerBuilder()
    builder.register(Service)
    explanation = builder.build().graph.explain(Alias)
    assert "Alias ->" in explanation.subject
    assert explanation.subject.endswith("Service")


def test_aliases_work_for_scope_slots_and_boundary_contracts():
    class Request:
        pass

    RequestAlias = TypeAliasType("RequestAlias", Request)  # noqa: N806

    class Handler:
        def __init__(self, request: RequestAlias):
            self.request = request

    Handler.__init__.__annotations__["request"] = RequestAlias

    HandlerAlias = TypeAliasType("HandlerAlias", Handler)  # noqa: N806

    def feature(builder):
        builder.register(HandlerAlias)

    boundary = Boundary(
        "feature",
        feature,
        uses=(Use.root(RequestAlias),),
        exposes=(Expose(HandlerAlias),),
    )
    builder = ContainerBuilder()
    builder.declare_scope_slot(Request)
    builder.install_boundary(boundary)
    with builder.build() as container, container.new_scope() as scope:
        request = Request()
        scope.provide(RequestAlias, request)
        assert scope.has_scope_slot(RequestAlias)
        assert scope.has_provision(Request)
        assert scope.resolve(Handler).request is request


def test_new_type_is_nominal_and_alias_of_new_type_keeps_that_identity():
    DatabaseUrl = NewType("DatabaseUrl", str)
    ApiUrl = NewType("ApiUrl", str)
    DatabaseAlias = TypeAliasType("DatabaseAlias", DatabaseUrl)  # noqa: N806

    builder = ContainerBuilder()
    with pytest.raises(TypeError, match="NewType service .* requires"):
        builder.register(DatabaseAlias)
    database = DatabaseUrl("database")
    api = ApiUrl("api")
    builder.register(DatabaseUrl, instance=database)
    builder.register(ApiUrl, instance=api)
    with builder.build() as container:
        assert container.resolve(DatabaseAlias) == database
        assert container.resolve(ApiUrl) == api
        assert not container.has_component(str)


@pytest.mark.parametrize(
    ("target", "code"),
    [
        (42, "type-alias-invalid"),
        ("MissingAliasTarget", "type-alias-unresolved"),
    ],
)
def test_invalid_and_unresolved_aliases_have_classified_repairable_build_errors(target, code):
    alias = TypeAliasType("alias", target)
    builder = ContainerBuilder()
    builder.register(alias, instance=object())
    with pytest.raises(ContainerBuildError) as raised:
        builder.build()
    assert raised.value.report is not None
    assert [issue.code for issue in raised.value.report.issues] == [code]


def test_recursive_alias_has_a_finite_classified_error():
    module = types.ModuleType("clean_ioc_recursive_alias_fixture")
    sys.modules[module.__name__] = module
    try:
        exec(  # noqa: S102 - isolated module fixture exercises lazy alias evaluation
            "from typing_extensions import TypeAliasType\nRecursive = TypeAliasType('Recursive', 'list[Recursive]')",
            module.__dict__,
        )
        builder = ContainerBuilder()
        builder.register(module.Recursive, instance=[])
        with pytest.raises(ContainerBuildError) as raised:
            builder.build()
        assert raised.value.report is not None
        assert raised.value.report.issues[0].code == "type-alias-recursive"
    finally:
        sys.modules.pop(module.__name__, None)


def test_independent_alias_errors_are_aggregated():
    first = TypeAliasType("first", 1)  # ty: ignore[invalid-type-form]
    second = TypeAliasType("second", "MissingSecond")  # ty: ignore[unresolved-reference]
    builder = ContainerBuilder()
    builder.register(first, instance=object())
    builder.register(second, instance=object())
    with pytest.raises(ContainerBuildError) as raised:
        builder.build()
    assert raised.value.report is not None
    assert {issue.code for issue in raised.value.report.issues} == {
        "type-alias-invalid",
        "type-alias-unresolved",
    }


def test_wrong_arity_and_unsupported_alias_parameters_are_classified():
    parameter = TypeVar("parameter")
    generic = TypeAliasType("generic", list[parameter], type_params=(parameter,))
    params = ParamSpec("params")
    callable_alias = TypeAliasType("callable_alias", Callable[params, int], type_params=(params,))

    for alias, code in (
        (generic[int, str], "type-alias-arguments"),  # ty: ignore[invalid-type-arguments]
        (callable_alias, "type-alias-unsupported-parameter"),
    ):
        builder = ContainerBuilder()
        builder.register(alias, instance=object())
        with pytest.raises(ContainerBuildError) as raised:
            builder.build()
        assert raised.value.report is not None
        assert raised.value.report.issues[0].code == code


def test_late_forward_alias_binding_and_failed_build_retry():
    module = types.ModuleType("clean_ioc_late_alias_fixture")
    sys.modules[module.__name__] = module
    try:
        exec(  # noqa: S102 - isolated module fixture exercises lazy alias evaluation
            "from typing_extensions import TypeAliasType\nLate = TypeAliasType('Late', 'Service')",
            module.__dict__,
        )
        builder = ContainerBuilder()
        builder.register(module.Late)
        with pytest.raises(ContainerBuildError) as raised:
            builder.build()
        assert raised.value.report is not None
        assert raised.value.report.issues[0].code == "type-alias-unresolved"
        exec("class Service: pass", module.__dict__)  # noqa: S102 - repairs the fixture namespace
        preview_type = module.Service
        assert builder.has_component(module.Late)
        exec("class Service: pass", module.__dict__)  # noqa: S102 - preview must not freeze a successful evaluation
        with builder.build() as container:
            assert isinstance(container.resolve(module.Late), module.Service)
            assert not isinstance(container.resolve(module.Late), preview_type)
    finally:
        sys.modules.pop(module.__name__, None)


@pytest.mark.skipif(sys.version_info < (3, 12), reason="native type statements require Python 3.12")
def test_native_type_statement_aliases_use_the_same_path():
    namespace = {"ContainerBuilder": ContainerBuilder, "Repository": Repository}
    exec(  # noqa: S102 - version-gated syntax must remain parseable on Python 3.11
        """
type NativeRepo[T] = Repository[T]
builder = ContainerBuilder()
builder.register(NativeRepo[int], lifespan="singleton")
with builder.build() as container:
    assert container.resolve(NativeRepo[int]) is container.resolve(Repository[int])
""",
        namespace,
    )
