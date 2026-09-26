"""Per-call declarations compile a deferred, isolated operation plan."""

import inspect
import typing
from abc import ABC, abstractmethod
from collections.abc import Callable, Iterable, Iterator, Mapping
from functools import cached_property
from typing import Annotated, ClassVar, Generic, Literal, Protocol, TypeVar, cast

import pytest
from typing_extensions import Protocol as ExtensionsProtocol
from typing_extensions import Self

from clean_ioc import (
    ComponentKind,
    ContainerBuilder,
    ContainerBuildError,
    DecoratorTemplate,
    Expose,
    LifespanPolicy,
    Provider,
    ProviderMapGroup,
    Scope,
    ScopeClosedError,
    ScopePolicy,
    ScopeProvisionError,
    ServiceGroup,
)


class Operation(Protocol):
    def run(self, value: str, *, _method: str = "ordinary") -> tuple[str, int]: ...


class Resource:
    pass


class OperationImpl:
    created = 0
    resources: ClassVar[list[Resource]] = []

    def __init__(self, resource: Resource):
        self.resource = resource
        type(self).created += 1
        type(self).resources.append(resource)

    def run(self, value: str, *, _method: str = "ordinary") -> tuple[str, int]:
        return value + _method, id(self.resource)


def test_deferred_activation_and_all_keywords_forward_unchanged() -> None:
    OperationImpl.created = 0
    OperationImpl.resources = []
    builder = ContainerBuilder()
    builder.register(Resource, lifespan="scoped")
    builder.register(Operation, OperationImpl, scope="per_call")
    with builder.build() as container:
        handle = container.resolve(Operation)
        assert callable(handle.run)
        assert OperationImpl.created == 0
        assert str(inspect.signature(handle.run)) == "(value: str, *, _method: str = 'ordinary') -> tuple[str, int]"
        first = handle.run("a", _method="one")
        second = handle.run("b", _method="two")
        assert first[0] == "aone"
        assert second[0] == "btwo"
        assert OperationImpl.resources[0] is not OperationImpl.resources[1]
        assert first[1] == id(OperationImpl.resources[0])
        assert second[1] == id(OperationImpl.resources[1])
        assert OperationImpl.created == 2


def test_literal_self_keyword_is_forwarded_to_kwargs_contract() -> None:
    class Service(Protocol):
        def run(self, /, **kwargs: str) -> str: ...

    class Impl:
        def run(self, /, **kwargs: str) -> str:
            return kwargs["self"]

    builder = ContainerBuilder()
    builder.register(Service, Impl, scope="per_call")
    with builder.build() as container:
        assert container.resolve(Service).run(self="kept") == "kept"


@pytest.mark.parametrize(
    ("lifespan", "scope", "expected"),
    [
        ("auto", "current", "per_resolution"),
        ("scoped", "current", "scoped"),
        ("auto", "per_call", "scoped"),
        ("scoped", "per_call", "scoped"),
    ],
)
def test_policy_matrix(lifespan: LifespanPolicy, scope: ScopePolicy, expected: str) -> None:
    builder = ContainerBuilder()
    builder.register(Operation, OperationImpl, lifespan=lifespan, scope=scope)
    builder.register(Resource, lifespan="scoped")
    with builder.build() as container:
        root = next(root for root in container.graph.roots if root.requested_type is Operation)
        assert root.component.lifespan == expected


@pytest.mark.parametrize("lifespan", ["transient", "per_resolution", "singleton", None, "misspelled"])
def test_invalid_per_call_lifespan_rejected(lifespan: object) -> None:
    builder = ContainerBuilder()
    with pytest.raises(ValueError):
        builder.register(Operation, OperationImpl, lifespan=cast(LifespanPolicy, lifespan), scope="per_call")


def test_patch_policy_is_atomic_and_can_restore_current_scope() -> None:
    builder = ContainerBuilder()
    builder.register(Resource, lifespan="scoped")
    component_id = builder.register(Operation, OperationImpl)
    with pytest.raises(ValueError):
        builder.patch_component(Operation, component_id, scope="per_call", lifespan="singleton")
    builder.patch_component(Operation, component_id, scope="per_call", lifespan="auto")
    with builder.build() as container:
        root = next(root for root in container.graph.roots if root.requested_type is Operation)
        assert root.component.kind is ComponentKind.per_call_handle


def test_abc_inheritance_and_implementation_override() -> None:
    class Base(ABC):
        @abstractmethod
        def run(self, value: int) -> int: ...

    class Service(Base):
        pass

    class Impl(Service):
        def run(self, value: int) -> int:
            return value + 3

    builder = ContainerBuilder()
    builder.register(Service, Impl, scope="per_call")
    with builder.build() as container:
        service = container.resolve(Service)
        assert isinstance(service, Service)
        assert service.run(4) == 7


def test_private_abstract_helper_is_stubbed_only_on_the_handle() -> None:
    class Service(ABC):
        def execute(self, value: int) -> int:
            return self._execute(value)

        @abstractmethod
        def _execute(self, value: int) -> int: ...

    class Impl(Service):
        def _execute(self, value: int) -> int:
            return value + 3

    builder = ContainerBuilder()
    builder.register(Service, Impl, scope="per_call")
    with builder.build() as container:
        handle = container.resolve(Service)
        assert handle.execute(4) == 7
        with pytest.raises(NotImplementedError, match="_execute"):
            handle._execute(4)
        assert handle.execute(5) == 8


@pytest.mark.asyncio
async def test_async_private_abstract_helper_is_stubbed_only_on_the_handle() -> None:
    class Service(ABC):
        async def execute(self, value: int) -> int:
            return await self._execute(value)

        @abstractmethod
        async def _execute(self, value: int) -> int: ...

    class Impl(Service):
        async def _execute(self, value: int) -> int:
            return value + 3

    builder = ContainerBuilder()
    builder.register(Service, Impl, scope="per_call")
    async with builder.build() as container:
        handle = container.resolve(Service)
        assert await handle.execute(4) == 7
        with pytest.raises(NotImplementedError, match="_execute"):
            await handle._execute(4)
        assert await handle.execute(5) == 8


def test_private_abstract_property_and_static_class_helpers_keep_descriptor_behavior() -> None:
    class Service(ABC):
        def execute(self) -> str:
            return self._value + self._suffix() + self._prefix()

        @property
        @abstractmethod
        def _value(self) -> str: ...

        @staticmethod
        @abstractmethod
        def _suffix() -> str: ...

        @classmethod
        @abstractmethod
        def _prefix(cls) -> str: ...

    class Impl(Service):
        @property
        def _value(self) -> str:
            return "value"

        @staticmethod
        def _suffix() -> str:
            return "!"

        @classmethod
        def _prefix(cls) -> str:
            return cls.__name__

    builder = ContainerBuilder()
    builder.register(Service, Impl, scope="per_call")
    with builder.build() as container:
        handle = container.resolve(Service)
        assert handle.execute() == "value!Impl"
        with pytest.raises(NotImplementedError, match="_value"):
            _ = handle._value
        with pytest.raises(NotImplementedError, match="_suffix"):
            handle._suffix()
        with pytest.raises(NotImplementedError, match="_prefix"):
            handle._prefix()


def test_private_abstract_setter_and_deleter_keep_their_descriptor_modes() -> None:
    events: list[str] = []

    class Service(ABC):
        def execute(self) -> str:
            self._value = "changed"
            del self._deleted
            return self._value

        @property
        def _value(self) -> str:
            return "real"

        @_value.setter
        @abstractmethod
        def _value(self, value: str) -> None: ...

        @property
        def _deleted(self) -> str:
            return "real"

        @_deleted.deleter
        @abstractmethod
        def _deleted(self) -> None: ...

    class Impl(Service):
        @Service._value.setter
        def _value(self, value: str) -> None:
            events.append(value)

        @Service._deleted.deleter
        def _deleted(self) -> None:
            events.append("deleted")

    builder = ContainerBuilder()
    builder.register(Service, Impl, scope="per_call")
    with builder.build() as container:
        handle = container.resolve(Service)
        assert handle.execute() == "real"
        assert events == ["changed", "deleted"]
        with pytest.raises(NotImplementedError, match="_value"):
            handle._value = "wrong"
        with pytest.raises(NotImplementedError, match="_deleted"):
            del handle._deleted
        assert events == ["changed", "deleted"]


def test_abstract_special_method_is_rejected_at_build() -> None:
    class Service(ABC):
        def run(self) -> str:
            return "ok"

        @abstractmethod
        def __str__(self) -> str: ...

    class Impl(Service):
        def __str__(self) -> str:
            return "real"

    builder = ContainerBuilder()
    builder.register(Service, Impl, scope="per_call")
    with pytest.raises(ContainerBuildError, match="unsupported abstract special method '__str__'"):
        builder.build()


def test_provider_in_singleton_captures_safe_handle() -> None:
    class Consumer:
        def __init__(self, operation: Provider[Operation]):
            self.operation = operation

    builder = ContainerBuilder()
    builder.register(Resource, lifespan="scoped")
    builder.register(Operation, OperationImpl, scope="per_call")
    builder.register(Consumer, lifespan="singleton")
    with builder.build() as container:
        with container.new_scope() as child:
            consumer = child.resolve(Consumer)
        assert consumer.operation().run("a")[0] == "aordinary"
        assert consumer.operation().run("b")[0] == "bordinary"


def test_direct_handle_expires_with_its_scope() -> None:
    builder = ContainerBuilder()
    builder.register(Resource, lifespan="scoped")
    builder.register(Operation, OperationImpl, scope="per_call")
    with builder.build() as container:
        with container.new_scope() as child:
            handle = child.resolve(Operation)
            assert handle.run("a")[0] == "aordinary"
        with pytest.raises(ScopeClosedError):
            handle.run("b")


@pytest.mark.parametrize(
    ("contract", "implementation"),
    [
        (type("DataContract", (Protocol,), {"__annotations__": {"value": str}}), object),
        (type("PropertyContract", (), {"value": property(lambda self: 1)}), object),
        (type("StaticContract", (), {"run": staticmethod(lambda: None)}), object),
    ],
)
def test_unsupported_contracts_fail_at_build(contract: type, implementation: type) -> None:
    builder = ContainerBuilder()
    builder.register(contract, implementation, scope="per_call")
    with pytest.raises(ContainerBuildError, match="per-call-unsupported"):
        builder.build()


def test_generator_operation_is_rejected() -> None:
    class Stream(Protocol):
        def read(self) -> Iterator[str]: ...

    class Impl:
        def read(self) -> Iterator[str]:
            yield "value"

    builder = ContainerBuilder()
    builder.register(Stream, Impl, scope="per_call")
    with pytest.raises(ContainerBuildError, match="stream result"):
        builder.build()


def test_graph_marks_invocation_boundary_without_activation() -> None:
    OperationImpl.created = 0
    builder = ContainerBuilder()
    builder.register(Resource, lifespan="scoped")
    builder.register(Operation, OperationImpl, scope="per_call")
    with builder.build() as container:
        root = next(root for root in container.graph.roots if root.requested_type is Operation)
        assert root.component.kind is ComponentKind.per_call_handle
        manifest = container.graph.manifest().to_dict()
        assert "per_call" in str(manifest)
        report = container.graph.activation_report(Operation)
        assert any(item.kind == "per_call_handle" for item in report.immediate_obligations)
        assert any(item.kind == "construction" for item in report.potential_acquisitions)
        assert all(item.phase == "deferred" for item in report.potential_acquisitions)
        sharing = container.graph.sharing_report(Operation)
        assert any("each method call" in " ".join(item.conditions) for item in sharing.groups)
        assert OperationImpl.created == 0


def test_explicit_and_generated_decorators_activate_inside_each_call() -> None:
    events: list[str] = []

    class Service(Protocol):
        def run(self) -> str: ...

    class Impl:
        def run(self) -> str:
            events.append("core")
            return "core"

    class Wrapper:
        def __init__(self, child: Service):
            events.append("construct wrapper")
            self.child = child

        def run(self) -> str:
            events.append("wrapper")
            return self.child.run() + "!"

    class Marker:
        pass

    group = ServiceGroup("services", service_type=Service)
    builder = ContainerBuilder()
    builder.register(Marker)
    builder.register(Service, Impl, scope="per_call", groups=(group,))
    builder.register_decorator(Service, Wrapper)
    builder.register_decorator_template(
        for_each=Marker,
        template=lambda _source: DecoratorTemplate(group, Wrapper),
    )
    with builder.build() as container:
        handle = container.resolve(Service)
        assert events == []
        assert handle.run() == "core!!"
        assert handle.run() == "core!!"
        assert events.count("construct wrapper") == 4
        assert events.count("core") == 2


def test_decorator_may_delegate_forwarded_method_through_getattr() -> None:
    class Service(Protocol):
        def run(self) -> str: ...

    class Impl:
        def run(self) -> str:
            return "ok"

    class ForwardingDecorator:
        def __init__(self, child: Service):
            self.child = child

        def __getattr__(self, name: str):
            return getattr(self.child, name)

    builder = ContainerBuilder()
    builder.register(Service, Impl, scope="per_call")
    builder.register_decorator(Service, ForwardingDecorator)
    with builder.build() as container:
        assert container.resolve(Service).run() == "ok"


T = TypeVar("T")


class GenericOperation(Generic[T]):
    def run(self, value: T) -> str:
        return str(value)


class IntOperation(GenericOperation[int]):
    def run(self, value: int) -> str:
        return f"int:{value}"


def test_closed_generic_discovery_and_pattern_propagate_scope_policy() -> None:
    builder = ContainerBuilder()
    builder.register_generic_subclasses(GenericOperation, scope="per_call")
    with builder.build() as container:
        assert container.resolve(GenericOperation[int]).run(3) == "int:3"

    class Consumer:
        def __init__(self, operation: GenericOperation[list[int]]):
            self.operation = operation

    builder = ContainerBuilder()
    builder.register_pattern(GenericOperation[list[T]], factory=GenericOperation, scope="per_call")
    builder.register(Consumer)
    with builder.build() as container:
        assert container.resolve(Consumer).operation.run([1, 2]) == "[1, 2]"


def test_provider_map_and_boundary_expose_one_public_per_call_registration() -> None:
    class Service(Protocol):
        def run(self) -> str: ...

    class Impl:
        def run(self) -> str:
            return "inside"

    group = ProviderMapGroup("services", str, Service)

    def bundle(builder):
        builder.register(Service, Impl, scope="per_call", contributes={group: "one"})
        builder.register_provider_map(group)

    builder = ContainerBuilder()
    builder.create_boundary("private", exposes=(Expose(Service), Expose(Mapping[str, Provider[Service]]))).apply_bundle(
        bundle
    )
    with builder.build() as container:
        assert container.resolve(Service).run() == "inside"
        providers = container.resolve(Mapping[str, Provider[Service]])
        assert list(providers) == ["one"]
        assert providers["one"]().run() == "inside"
        assert len({root.component.id for root in container.graph.roots if root.requested_type is Service}) == 1


def test_transitive_captive_dependency_and_cycle_still_fail() -> None:
    class Short:
        pass

    class Middle:
        def __init__(self, short: Short):
            self.short = short

    class Service(Protocol):
        def run(self) -> None: ...

    class Impl:
        def __init__(self, middle: Middle):
            self.middle = middle

        def run(self) -> None:
            pass

    builder = ContainerBuilder()
    builder.register(Short)
    builder.register(Middle, lifespan="transient")
    builder.register(Service, Impl, scope="per_call")
    with pytest.raises(ContainerBuildError, match="captive-dependency"):
        builder.build()

    class CyclicImpl:
        def __init__(self, service: Service):
            self.service = service

        def run(self) -> None:
            pass

    builder = ContainerBuilder()
    builder.register(Service, CyclicImpl, scope="per_call")
    with pytest.raises(ContainerBuildError, match="circular-dependency"):
        builder.build()


def test_activation_and_method_failures_finalize_invocation_scope() -> None:
    closed: list[str] = []

    class Service(Protocol):
        def run(self, *, fail: bool = False) -> None: ...

    def resource() -> Iterator[Resource]:
        try:
            yield Resource()
        finally:
            closed.append("closed")

    class Impl:
        attempts = 0

        def __init__(self, resource: Resource):
            del resource
            type(self).attempts += 1
            if type(self).attempts == 1:
                raise ValueError("activation")

        def run(self, *, fail: bool = False) -> None:
            if fail:
                raise ValueError("method")

    builder = ContainerBuilder()
    builder.register(Resource, factory=resource, lifespan="scoped")
    builder.register(Service, Impl, scope="per_call")
    with builder.build() as container:
        handle = container.resolve(Service)
        with pytest.raises(ValueError, match="activation"):
            handle.run()
        with pytest.raises(ValueError, match="method"):
            handle.run(fail=True)
        handle.run()
    assert closed == ["closed", "closed", "closed"]


def test_known_async_mode_mismatch_fails_at_build() -> None:
    class Service(Protocol):
        def run(self) -> str: ...

    class AsyncImpl:
        async def run(self) -> str:
            return "late"

    builder = ContainerBuilder()
    builder.register(Service, AsyncImpl, scope="per_call")
    with pytest.raises(ContainerBuildError, match="per-call-method-mode"):
        builder.build()


def test_public_descriptor_and_implementation_property_fail_at_build() -> None:
    class DescriptorService:
        @cached_property
        def state(self) -> str:
            return "late"

        def run(self) -> str:
            return self.state

    builder = ContainerBuilder()
    builder.register(DescriptorService, scope="per_call")
    with pytest.raises(ContainerBuildError, match="descriptor 'state'"):
        builder.build()

    class Service(Protocol):
        def run(self) -> str: ...

    class PropertyImpl:
        @property
        def run(self) -> str:
            return "not callable"

    builder = ContainerBuilder()
    builder.register(Service, PropertyImpl, scope="per_call")
    with pytest.raises(ContainerBuildError, match="unsupported operation 'run'"):
        builder.build()


def test_declared_iterator_results_and_generator_decorator_fail_at_build() -> None:
    class Stream(Protocol):
        def read(self) -> Iterator[Resource]: ...

    class StreamImpl:
        def read(self) -> Iterator[Resource]:
            return iter((Resource(),))

    builder = ContainerBuilder()
    builder.register(Stream, StreamImpl, scope="per_call")
    with pytest.raises(ContainerBuildError, match="stream result"):
        builder.build()

    class OpaqueService(Protocol):
        def read(self) -> object: ...

    builder = ContainerBuilder()
    builder.register(OpaqueService, StreamImpl, scope="per_call")
    with pytest.raises(ContainerBuildError, match="unsupported operation 'read'"):
        builder.build()

    class Service(Protocol):
        def run(self) -> str: ...

    class Impl:
        def run(self) -> str:
            return "core"

    class GeneratorDecorator:
        def __init__(self, child: Service):
            self.child = child

        def run(self):
            yield self.child.run()

    builder = ContainerBuilder()
    builder.register(Service, Impl, scope="per_call")
    builder.register_decorator(Service, GeneratorDecorator)
    with pytest.raises(ContainerBuildError, match="unsupported operation 'run'"):
        builder.build()


def test_unknown_factory_stream_result_is_rejected_before_scope_closes() -> None:
    class Service(Protocol):
        def read(self) -> object: ...

    class Impl:
        def read(self):
            return iter(("value",))

    def factory():
        return Impl()

    builder = ContainerBuilder()
    builder.register(Service, factory=factory, scope="per_call")
    with builder.build() as container:
        with pytest.raises(RuntimeError, match="iterator that would outlive its scope"):
            container.resolve(Service).read()


def test_unknown_factory_awaitable_result_is_rejected_before_scope_closes() -> None:
    class Service(Protocol):
        def run(self) -> str: ...

    class Impl:
        async def run(self) -> str:
            return "late"

    def factory():
        return Impl()

    builder = ContainerBuilder()
    builder.register(Service, factory=factory, scope="per_call")
    with builder.build() as container:
        with pytest.raises(RuntimeError, match="awaitable that would outlive its scope"):
            container.resolve(Service).run()


@pytest.mark.parametrize("during_construction", [False, True])
def test_invocation_scope_provisions_lock_before_target_activation(during_construction: bool) -> None:
    class Request:
        pass

    class Service(Protocol):
        def run(self) -> None: ...

    class Impl:
        def __init__(self, scope: Scope):
            self.scope = scope
            if during_construction:
                self.scope.provide(Request, Request())

        def run(self) -> None:
            self.scope.provide(Request, Request())

    builder = ContainerBuilder()
    builder.declare_scope_slot(Request)
    builder.register(Service, Impl, scope="per_call")
    with builder.build() as container:
        with pytest.raises(ScopeProvisionError, match="locked"):
            container.resolve(Service).run()


def test_scalar_literal_and_annotated_metadata_do_not_look_like_stream_types() -> None:
    class LiteralService(Protocol):
        def run(self) -> Literal["Iterator"]: ...

    class LiteralImpl:
        def run(self) -> Literal["Iterator"]:
            return "Iterator"

    class AnnotatedService(Protocol):
        def run(self) -> Annotated[str, "Iterator"]: ...

    class AnnotatedImpl:
        def run(self) -> Annotated[str, "Iterator"]:
            return "ordinary"

    class StringifiedService(Protocol):
        def run(self) -> "Annotated[str, 'Iterator']": ...

    class StringifiedImpl:
        def run(self) -> "Annotated[str, 'Iterator']":
            return "ordinary"

    builder = ContainerBuilder()
    builder.register(LiteralService, LiteralImpl, scope="per_call")
    builder.register(AnnotatedService, AnnotatedImpl, scope="per_call")
    builder.register(StringifiedService, StringifiedImpl, scope="per_call")
    with builder.build() as container:
        assert container.resolve(LiteralService).run() == "Iterator"
        assert container.resolve(AnnotatedService).run() == "ordinary"
        assert container.resolve(StringifiedService).run() == "ordinary"


def test_eager_iterable_and_callable_results_are_allowed() -> None:
    class Service(Protocol):
        def items(self) -> Iterable[int]: ...

        def callback(self) -> Callable[[int], int]: ...

    class Impl:
        def items(self) -> Iterable[int]:
            return [1, 2]

        def callback(self) -> Callable[[int], int]:
            return lambda value: value + 1

    builder = ContainerBuilder()
    builder.register(Service, Impl, scope="per_call")
    with builder.build() as container:
        handle = container.resolve(Service)
        assert handle.items() == [1, 2]
        assert handle.callback()(4) == 5


def test_typing_extensions_protocol_contract_works_on_supported_pythons() -> None:
    class Service(ExtensionsProtocol):
        def run(self) -> str: ...

    class Impl:
        def run(self) -> str:
            return "ok"

    builder = ContainerBuilder()
    builder.register(Service, Impl, scope="per_call")
    with builder.build() as container:
        assert container.resolve(Service).run() == "ok"


def test_effective_classvar_overrides_inherited_instance_annotation_and_callable() -> None:
    class Base:
        status: str

        def run(self) -> str:
            return self.status

    class Service(Base):
        status: ClassVar[str] = "ready"  # ty: ignore[invalid-attribute-override]
        formatter: ClassVar[Callable[[str], str]] = staticmethod(str.upper)

    class StringService(Base):
        status: "ClassVar[str]" = "stringified"  # ty: ignore[invalid-attribute-override]

    builder = ContainerBuilder()
    builder.register(Service, scope="per_call")
    builder.register(StringService, scope="per_call")
    with builder.build() as container:
        assert container.resolve(Service).run() == "ready"
        assert container.resolve(StringService).run() == "stringified"


def test_bare_and_outer_quoted_classvar_annotations_are_class_data() -> None:
    class BareService:
        status: ClassVar = "bare"

        def run(self) -> str:
            return self.status

    class QuotedService:
        # This is the runtime spelling produced by an explicitly quoted
        # annotation under ``from __future__ import annotations``.
        status: "'ClassVar[str]'" = "quoted"

        def run(self) -> str:
            return self.status

    class QualifiedService:
        status: "typing.ClassVar" = "qualified"

        def run(self) -> str:
            return self.status

    builder = ContainerBuilder()
    builder.register(BareService, scope="per_call")
    builder.register(QuotedService, scope="per_call")
    builder.register(QualifiedService, scope="per_call")
    with builder.build() as container:
        assert container.resolve(BareService).run() == "bare"
        assert container.resolve(QuotedService).run() == "quoted"
        assert container.resolve(QualifiedService).run() == "qualified"


@pytest.mark.parametrize("hook_name", ["__getattr__", "__delattr__", "__iter__"])
def test_inherited_unsupported_contract_hook_is_rejected(hook_name: str) -> None:
    base = type("HookBase", (), {hook_name: lambda self, *args: None})

    class Service(base):  # type: ignore[valid-type,misc]
        def run(self) -> str:
            return "ok"

    builder = ContainerBuilder()
    builder.register(Service, scope="per_call")
    with pytest.raises(ContainerBuildError, match=hook_name):
        builder.build()


def test_implementation_only_attribute_hook_is_allowed() -> None:
    class Service(Protocol):
        def run(self) -> str: ...

    class Impl:
        def __getattribute__(self, name: str) -> object:
            return object.__getattribute__(self, name)

        def run(self) -> str:
            return "ok"

    builder = ContainerBuilder()
    builder.register(Service, Impl, scope="per_call")
    with builder.build() as container:
        assert container.resolve(Service).run() == "ok"


@pytest.mark.parametrize("annotation", [Self, "Self", "Service", "'Self'", "'Service'"])
def test_fluent_contract_result_is_rejected_at_build(annotation: object) -> None:
    class Service(Protocol):
        def run(self) -> object: ...

    Service.run.__annotations__["return"] = annotation

    class Impl:
        def run(self) -> object:
            return self

    builder = ContainerBuilder()
    builder.register(Service, Impl, scope="per_call")
    with pytest.raises(ContainerBuildError, match="scoped target result"):
        builder.build()


def test_fluent_implementation_result_is_rejected_at_build() -> None:
    class Service(Protocol):
        def run(self) -> object: ...

    class Impl:
        def run(self) -> Self:
            return self

    builder = ContainerBuilder()
    builder.register(Service, Impl, scope="per_call")
    with pytest.raises(ContainerBuildError, match="scoped target result"):
        builder.build()


def test_fluent_names_nested_in_literal_metadata_and_callable_are_not_results() -> None:
    class Service(Protocol):
        def literal(self) -> Literal["Self"]: ...

        def tagged(self) -> Annotated[str, "Self"]: ...

        def callback(self) -> Callable[[], str]: ...

    class Impl:
        def literal(self) -> Literal["Self"]:
            return "Self"

        def tagged(self) -> Annotated[str, "Self"]:
            return "value"

        def callback(self) -> Callable[[], str]:
            return lambda: "value"

    builder = ContainerBuilder()
    builder.register(Service, Impl, scope="per_call")
    with builder.build() as container:
        handle = container.resolve(Service)
        assert handle.literal() == "Self"
        assert handle.tagged() == "value"
        assert handle.callback()() == "value"


def test_bound_builtin_method_cannot_escape_scoped_target() -> None:
    class Service(Protocol):
        def export(self) -> object: ...

    class Impl:
        def export(self) -> object:
            return self.__str__

    builder = ContainerBuilder()
    builder.register(Service, Impl, scope="per_call")
    with builder.build() as container:
        with pytest.raises(RuntimeError, match="scoped target or bound method"):
            container.resolve(Service).export()


def test_subclass_method_overrides_inherited_classvar_in_handle_shape() -> None:
    class Base:
        data: ClassVar[int] = 1

    class Service(Base):
        _value: int

        def data(self) -> int:
            return self._value

        def run(self) -> int:
            return self.data()

    class Impl(Service):
        def __init__(self) -> None:
            self._value = 7

    builder = ContainerBuilder()
    builder.register(Service, Impl, scope="per_call")
    with builder.build() as container:
        handle = container.resolve(Service)
        assert handle.run() == 7
        assert handle.data() == 7


def test_callable_object_attribute_hook_is_rejected_without_executing_it() -> None:
    events: list[str] = []

    class Hook:
        def __call__(self, *_args: object) -> object:
            events.append("called")
            raise AssertionError("hook must not run")

    service = type("Service", (), {"__getattribute__": Hook(), "run": lambda self: "ok"})
    builder = ContainerBuilder()
    builder.register(service, scope="per_call")
    with pytest.raises(ContainerBuildError, match="__getattribute__"):
        builder.build()
    assert events == []


@pytest.mark.parametrize("reserved_name", ["_per_call_scope", "_per_call_target"])
def test_reserved_handle_members_fail_with_named_build_error(reserved_name: str) -> None:
    service = type(
        "Service",
        (ABC,),
        {"__slots__": (reserved_name,), "run": lambda self: "ok"},
    )
    builder = ContainerBuilder()
    builder.register(service, scope="per_call")
    with pytest.raises(ContainerBuildError, match=reserved_name):
        builder.build()
