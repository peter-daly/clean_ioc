"""Factory declarations are validated without activating their products."""

import json
from collections.abc import AsyncIterator, Callable, Iterator, Sequence
from contextlib import asynccontextmanager, contextmanager
from functools import partial, wraps
from typing import Annotated, Any, Generic, Literal, Never, NewType, Protocol, TypeVar, cast

import pytest
from typing_extensions import TypeAliasType

import clean_ioc.cli as cli
from clean_ioc import AsyncProvider, ContainerBuilder, ContainerBuildError, Expose, Provider, ScopeBuilder
from clean_ioc.tooling import qualified_name

T = TypeVar("T")
T_co = TypeVar("T_co", covariant=True)
T_contra = TypeVar("T_contra", contravariant=True)


class Service:
    pass


class Implementation(Service):
    pass


class Repository(Generic[T]):
    pass


class IntRepository(Repository[int]):
    pass


class StrRepository(Repository[str]):
    pass


class Source(Generic[T_co]):
    pass


class Sink(Generic[T_contra]):
    pass


class ServiceProtocol(Protocol):
    def perform(self) -> None: ...


UserId = NewType("UserId", int)
OtherId = NewType("OtherId", int)
SpecialUserId = NewType("SpecialUserId", UserId)
ServiceAlias = TypeAliasType("ServiceAlias", Service)


def factory_with_annotation(annotation: Any) -> Callable[..., Any]:
    def factory():
        raise AssertionError("Factory body must not run during build or validation")

    factory.__annotations__["return"] = annotation
    return factory


def rejected(builder: ContainerBuilder | ScopeBuilder):
    with pytest.raises(ContainerBuildError) as raised:
        builder.build()
    return raised.value


@pytest.mark.parametrize(
    ("service", "result"),
    [
        (Service, str),
        (Implementation, Service),
        (Service, Service | str),
        (Service | int, str),
        (Service, Service | None),
        (Service, None),
        (Repository[int], Repository[str]),
        (Repository[int], Repository[bool]),
        (Repository[int], StrRepository),
        (list[int], list[str]),
        (list[int], list[bool]),
        (Sequence[int], Sequence[str]),
        (Source[int], Source[str]),
        (Sink[int], Sink[str]),
        (tuple[int, ...], tuple[int, str]),
        (tuple[int, str], tuple[int, ...]),
        (UserId, int),
        (UserId, OtherId),
        (Literal[True], Literal[1]),
        (int, Literal["wrong"]),
        (ServiceAlias, str),
        (Service, Annotated[str, "description"]),
    ],
)
def test_definite_annotation_mismatches_fail_build_without_activation(service, result):
    builder = ContainerBuilder()
    builder.register(service, factory=factory_with_annotation(result))
    error = rejected(builder)
    assert error.report is not None
    assert {issue.code for issue in error.report.errors} == {"factory-return-type-mismatch"}
    issue = error.report.errors[0]
    canonical_service = Service if service is ServiceAlias else service
    assert "incompatible with registered service" in issue.message
    assert qualified_name(canonical_service) in issue.message
    assert issue.root == qualified_name(canonical_service)
    assert issue.path == (qualified_name(canonical_service),)
    assert error.compiled_graph is not None


@pytest.mark.parametrize(
    ("service", "result"),
    [
        (Service, Service),
        (Service, Implementation),
        (object, Service),
        (Service | str, Service),
        (Service | str, Implementation | str),
        (Service | None, None),
        (Repository[int], Repository[int]),
        (Repository[int], IntRepository),
        (Repository[int], Repository[Any]),
        (Repository[int], Repository),
        (Repository[list[int]], Repository[list]),
        (Repository[Callable[[str], int]], Repository[Callable[[Any], int]]),
        (Source[int], Source[bool]),
        (Sink[bool], Sink[int]),
        (Sequence[int], Sequence[bool]),
        (Sequence[int], list[int]),
        (tuple[int, ...], tuple[int, bool]),
        (tuple[int, object], tuple[int, str]),
        (int, Literal[1, 2]),
        (Literal[1, 2], Literal[1]),
        (int, UserId),
        (UserId, SpecialUserId),
        (UserId, UserId),
        (float, int),
        (float, bool),
        (complex, bool),
        (complex, float),
        (Service, Annotated[Implementation, "description"]),
        (ServiceAlias, Implementation),
        (Service, Any),
        (Service, Never),
        (ServiceProtocol, str),
    ],
)
def test_compatible_and_unknown_annotations_remain_accepted(service, result):
    builder = ContainerBuilder()
    builder.register(service, factory=factory_with_annotation(result))
    with builder.build() as container:
        assert container.build_report.is_valid
        assert container.validation_report().is_valid


def test_unannotated_factories_and_constructor_or_instance_registrations_are_unaffected():
    def factory():
        raise AssertionError("No activation")

    builder = ContainerBuilder()
    builder.register(Service, factory=factory)
    builder.register(Implementation)
    builder.register(str, instance="value")
    assert builder.build().build_report.is_valid


def test_return_rule_does_not_reject_an_unresolved_annotation():
    factory = factory_with_annotation(Any)
    builder = ContainerBuilder()
    builder.register(Service, factory=factory)
    # Registration already resolves signatures and may reject unresolved names.
    # This checks the return rule's fallback when metadata later becomes unknown.
    factory.__annotations__["return"] = "UnresolvableType"
    assert builder.build().build_report.is_valid


@pytest.mark.parametrize("kind", ["async", "generator", "async_generator", "context_manager", "async_context_manager"])
def test_async_and_resource_factories_validate_the_product_annotation(kind):
    async def asynchronous() -> str:
        raise AssertionError("No activation")

    def generator() -> Iterator[str]:
        raise AssertionError("No acquisition or cleanup")
        yield "unreachable"

    async def asynchronous_generator() -> AsyncIterator[str]:
        raise AssertionError("No acquisition or cleanup")
        yield "unreachable"

    factories = {
        "async": asynchronous,
        "generator": generator,
        "async_generator": asynchronous_generator,
        "context_manager": contextmanager(generator),
        "async_context_manager": asynccontextmanager(asynchronous_generator),
    }
    builder = ContainerBuilder()
    builder.register(Service, factory=factories[kind])
    assert rejected(builder).report.errors[0].code == "factory-return-type-mismatch"


def test_a_sync_factory_returning_an_iterator_is_checked_as_an_iterator_product():
    def iterator_factory() -> Iterator[str]:
        raise AssertionError("No activation")

    builder = ContainerBuilder()
    builder.register(Iterator[str], factory=iterator_factory)
    assert builder.build().build_report.is_valid


@pytest.mark.parametrize("kind", ["callable", "partial", "wrapped"])
def test_callable_objects_partials_and_wrapped_functions_resolve_forward_annotations(kind):
    def function() -> "Implementation":
        raise AssertionError("No activation")

    class Factory:
        def __call__(self) -> "Implementation":
            raise AssertionError("No activation")

    @wraps(function)
    def wrapper():
        raise AssertionError("No activation")

    factory = {"callable": Factory(), "partial": partial(function), "wrapped": wrapper}[kind]
    builder = ContainerBuilder()
    builder.register(Service, factory=factory)
    assert builder.build().build_report.is_valid
    invalid = ContainerBuilder()
    invalid.register(str, factory=factory)
    assert rejected(invalid).report.errors[0].code == "factory-return-type-mismatch"


def test_closed_generic_factory_uses_the_compilers_resolved_result_binding():
    def factory() -> Repository[T]:
        raise AssertionError("No activation")

    builder = ContainerBuilder()
    builder.register(Repository, factory=factory)
    builder.mark_entrypoint(Repository[int])
    builder.mark_entrypoint(Repository[str])
    assert builder.build().build_report.is_valid


def test_explicit_hidden_generic_binding_is_used_by_return_check():
    def factory() -> Repository[T]:
        raise AssertionError("No activation")

    builder = ContainerBuilder()
    builder.register(object, factory=factory, factory_specialization=Repository[int])
    assert builder.build().build_report.is_valid


def test_closed_factory_result_mismatch_is_reported_beneath_a_provider():
    class Handler:
        def __init__(self, repository: Provider[Repository[int]]):
            raise AssertionError("No activation")

    builder = ContainerBuilder()
    builder.register(Repository[int], factory=factory_with_annotation(Repository[str]))
    builder.register(Handler)
    report = rejected(builder).report
    assert any(issue.root == qualified_name(Handler) and len(issue.path) == 3 for issue in report.errors)


def test_async_provider_targets_are_checked_too():
    class Handler:
        def __init__(self, service: AsyncProvider[Service]):
            raise AssertionError("No activation")

    builder = ContainerBuilder()
    builder.register(Service, factory=factory_with_annotation(str))
    builder.register(Handler)
    assert any(issue.root == qualified_name(Handler) for issue in rejected(builder).report.errors)


def test_multiple_mismatches_are_aggregated_and_failed_builder_can_be_repaired():
    first = factory_with_annotation(str)
    second = factory_with_annotation(int)
    builder = ContainerBuilder()
    builder.register(Service, factory=first)
    builder.register(Implementation, factory=second)
    report = rejected(builder).report
    assert len(report.errors) == 2
    first.__annotations__["return"] = Service
    second.__annotations__["return"] = Implementation
    assert builder.build().build_report.is_valid


def test_build_rule_applies_to_boundaries_and_overlays():
    builder = ContainerBuilder()
    boundary = builder.create_boundary("feature", exposes=(Expose(Service),))
    boundary.register(Service, factory=factory_with_annotation(str))
    assert rejected(builder).report.errors[0].code == "factory-return-type-mismatch"

    parent = ContainerBuilder()
    parent.register(Service, lifespan="singleton")
    with parent.build() as container:
        overlay = container.new_scope_builder()
        overlay.register(Service, factory=factory_with_annotation(str), lifespan="singleton")
        assert rejected(overlay).report.errors[0].code == "factory-return-type-mismatch"


def test_annotation_check_does_not_verify_actual_factory_returns():
    def factory() -> Service:
        return cast(Any, "oops")  # Application type checkers own factory body checks.

    builder = ContainerBuilder()
    builder.register(Service, factory=factory)
    assert builder.build().build_report.is_valid


def test_source_linked_sarif_and_assertions_include_the_build_finding():
    builder = ContainerBuilder()
    builder.register(Service, factory=factory_with_annotation(str))
    error = rejected(builder)
    run = json.loads(error.to_sarif())["runs"][0]
    result = run["results"][0]
    assert result["ruleId"] == "factory-return-type-mismatch"
    assert result["locations"][0]["physicalLocation"]["artifactLocation"]["uri"] == "tests/test_factory_return_types.py"
    with pytest.raises(AssertionError) as raised:
        error.report.assert_valid()
    assert json.loads(str(raised.value))["runs"][0]["results"][0]["ruleId"] == "factory-return-type-mismatch"


@pytest.mark.parametrize("format_name", ["text", "json", "sarif"])
def test_cli_reports_factory_return_mismatches_as_build_failures(monkeypatch, capsys, format_name):
    builder = ContainerBuilder()
    builder.register(Service, factory=factory_with_annotation(str))
    monkeypatch.setattr(cli, "_load_object", lambda _: builder)
    assert cli.main(["check", "app:builder", "--format", format_name, "--ignore", "factory-return-type-mismatch"]) == 1
    output = capsys.readouterr()
    assert "factory-return-type-mismatch" in output.out + output.err
