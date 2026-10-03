"""Independent acceptance scenarios for transparent operation scopes."""

import asyncio
import threading
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator, Iterator
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Protocol

import pytest

from clean_ioc import ContainerBuilder, ContainerBuildError, ScopeClosedError


def test_long_lived_consumer_has_isolated_calls_after_first_resolving_child_closes(monkeypatch):
    class Resource:
        closed = False

    created: list[Resource] = []

    def resource_factory() -> Iterator[Resource]:
        resource = Resource()
        created.append(resource)
        try:
            yield resource
        finally:
            resource.closed = True

    class Processor(Protocol):
        def process(self, value: str, *, suffix: str = "!") -> tuple[str, int]: ...

    class Implementation:
        def __init__(self, left: Resource, right: Resource):
            assert left is right
            self.resource = left

        def process(self, value: str, *, suffix: str = "!") -> tuple[str, int]:
            assert not self.resource.closed
            return value + suffix, id(self.resource)

    class Consumer:
        def __init__(self, processor: Processor):
            self.processor = processor

    builder = ContainerBuilder()
    builder.register(Resource, factory=resource_factory, lifespan="scoped")
    builder.register(Processor, Implementation, scope="per_call")
    builder.register(Consumer, lifespan="singleton")

    with builder.build() as container:
        parent_resource = container.resolve(Resource)
        with container.new_scope() as child:
            consumer = child.resolve(Consumer)
        assert created == [parent_resource]

        def no_compilation(*args, **kwargs):
            pytest.fail("An invocation must execute its frozen plan without rebuilding")

        monkeypatch.setattr(ContainerBuilder, "build", no_compilation)
        first = consumer.processor.process("first")
        second = consumer.processor.process("second", suffix="?")
        assert first[0] == "first!"
        assert second[0] == "second?"
        assert len({id(parent_resource), first[1], second[1]}) == 3
        assert not parent_resource.closed
        assert [resource.closed for resource in created[1:]] == [True, True]
    assert all(resource.closed for resource in created)


async def test_concurrent_calls_and_cancellation_keep_resource_ownership_separate():
    class Resource:
        closed = False

    created: list[Resource] = []
    tasks_seen: dict[str, object] = {}
    ready = {name: asyncio.Event() for name in ("cancel", "complete")}
    release = asyncio.Event()

    async def resource_factory() -> AsyncIterator[Resource]:
        resource = Resource()
        created.append(resource)
        try:
            yield resource
        finally:
            await asyncio.sleep(0)
            resource.closed = True

    class Processor(Protocol):
        async def process(self, name: str) -> int: ...

    class Implementation:
        def __init__(self, resource: Resource):
            self.resource = resource

        async def process(self, name: str) -> int:
            tasks_seen[name] = asyncio.current_task()
            ready[name].set()
            await release.wait()
            assert not self.resource.closed
            return id(self.resource)

    builder = ContainerBuilder()
    builder.register(Resource, factory=resource_factory, lifespan="scoped")
    builder.register(Processor, Implementation, scope="per_call")
    async with builder.build() as container:
        processor = container.resolve(Processor)
        assert not created
        cancelled = asyncio.create_task(processor.process("cancel"))
        completed = asyncio.create_task(processor.process("complete"))
        try:
            await asyncio.wait_for(asyncio.gather(*(event.wait() for event in ready.values())), timeout=5)
            assert len(created) == 2
            assert tasks_seen == {"cancel": cancelled, "complete": completed}
            cancelled.cancel()
            with pytest.raises(asyncio.CancelledError):
                await cancelled
            assert sum(resource.closed for resource in created) == 1
            release.set()
            result = await asyncio.wait_for(completed, timeout=5)
            assert result in {id(resource) for resource in created}
            assert all(resource.closed for resource in created)
        finally:
            release.set()
            for task in (cancelled, completed):
                if not task.done():
                    task.cancel()
            await asyncio.gather(cancelled, completed, return_exceptions=True)


def test_overlay_direct_calls_follow_overlay_but_inherited_singleton_keeps_root_plan():
    class Label:
        def __init__(self, value: str):
            self.value = value

    class Operation(Protocol):
        def __call__(self) -> str: ...

    class Implementation:
        def __init__(self, label: Label):
            self.label = label

        def __call__(self) -> str:
            return self.label.value

    class Consumer:
        def __init__(self, operation: Operation):
            self.operation = operation

    builder = ContainerBuilder()
    builder.register(Label, instance=Label("root"))
    builder.register(Operation, Implementation, scope="per_call")
    builder.register(Consumer, lifespan="singleton")

    with builder.build() as container:
        overlay_builder = container.new_scope_builder()
        overlay_builder.register(Label, instance=Label("overlay"))
        with overlay_builder.build() as overlay:
            direct = overlay.resolve(Operation)
            consumer = overlay.resolve(Consumer)
            assert direct() == "overlay"
            assert consumer.operation() == "root"
        assert consumer.operation() == "root"
        with pytest.raises(ScopeClosedError):
            direct()


def test_direct_child_handle_inherits_scope_slots_and_expires_with_child():
    class Request:
        def __init__(self, name: str):
            self.name = name

    class Operation(Protocol):
        def __call__(self) -> str: ...

    class Implementation:
        def __init__(self, request: Request):
            self.request = request

        def __call__(self) -> str:
            return self.request.name

    builder = ContainerBuilder()
    builder.declare_scope_slot(Request)
    builder.register(Operation, Implementation, scope="per_call")

    with builder.build() as container:
        with container.new_scope() as child:
            child.provide(Request, Request("request-one"))
            operation = child.resolve(Operation)
            assert operation() == "request-one"
        with pytest.raises(ScopeClosedError):
            operation()


def test_simultaneous_sync_calls_do_not_share_parent_or_each_others_state():
    class State:
        label = "unused"
        closed = False

    created: list[State] = []
    rendezvous = threading.Barrier(2)

    def state_factory() -> Iterator[State]:
        state = State()
        created.append(state)
        try:
            yield state
        finally:
            state.closed = True

    class Operation(Protocol):
        def run(self, label: str) -> str: ...

    class Implementation:
        def __init__(self, state: State):
            self.state = state

        def run(self, label: str) -> str:
            self.state.label = label
            rendezvous.wait(timeout=5)
            assert not self.state.closed
            return self.state.label

    builder = ContainerBuilder()
    builder.register(State, factory=state_factory, lifespan="scoped")
    builder.register(Operation, Implementation, scope="per_call")
    with builder.build() as container:
        parent_state = container.resolve(State)
        operation = container.resolve(Operation)
        with ThreadPoolExecutor(max_workers=2) as executor:
            first = executor.submit(operation.run, "first")
            second = executor.submit(operation.run, "second")
            assert (first.result(timeout=5), second.result(timeout=5)) == ("first", "second")
        assert parent_state.label == "unused"
        assert not parent_state.closed
        assert len(created) == 3
        assert all(state.closed for state in created if state is not parent_state)
    assert all(state.closed for state in created)


def test_inherited_name_mangled_abstract_helper_runs_only_on_the_scoped_implementation():
    class Resource:
        closed = False

    created: list[Resource] = []

    def resource_factory() -> Iterator[Resource]:
        resource = Resource()
        created.append(resource)
        try:
            yield resource
        finally:
            resource.closed = True

    class Base(ABC):
        @abstractmethod
        def __init__(self, resource: Resource): ...

        def run(self, value: str) -> str:
            return self.__execute(value)

        @abstractmethod
        def __execute(self, value: str) -> str: ...

    class Service(Base):
        pass

    class Implementation(Service):
        def __init__(self, resource: Resource):
            self.resource = resource

        def _Base__execute(self, value: str) -> str:  # noqa: N802
            assert not self.resource.closed
            return value.upper()

    builder = ContainerBuilder()
    builder.register(Resource, factory=resource_factory, lifespan="scoped")
    builder.register(Service, Implementation, scope="per_call")
    with builder.build() as container:
        service = container.resolve(Service)
        assert isinstance(service, Service)
        assert created == []
        with pytest.raises(RuntimeError, match="_Base__execute"):
            getattr(service, "_Base__execute")("forbidden")
        assert created == []
        assert service.run("first") == "FIRST"
        assert service.run("second") == "SECOND"
        assert len(created) == 2
        assert created[0] is not created[1]
        assert all(resource.closed for resource in created)


@pytest.mark.parametrize("hook_name", ["__getattribute__", "__setattr__", "__del__", "__enter__"])
def test_unsupported_handle_hooks_fail_build_without_executing_user_code(hook_name):
    called: list[str] = []

    def hook(self, *args):
        called.append(hook_name)
        raise AssertionError("Unsupported hooks must not execute during build")

    def run(self) -> str:
        return "ok"

    service_type = type("HookedService", (), {hook_name: hook, "run": run})
    builder = ContainerBuilder()
    builder.register(service_type, scope="per_call")
    with pytest.raises(ContainerBuildError, match=hook_name):
        builder.build()
    assert called == []


def test_private_field_dataclass_handles_have_safe_object_behavior_without_activation():
    class Resource:
        pass

    created: list[Resource] = []

    def resource_factory() -> Resource:
        resource = Resource()
        created.append(resource)
        return resource

    @dataclass
    class Service:
        _resource: Resource

        def run(self) -> int:
            return id(self._resource)

    builder = ContainerBuilder()
    builder.register(Resource, factory=resource_factory, lifespan="scoped")
    builder.register(Service, scope="per_call")
    with builder.build() as container:
        first = container.resolve(Service)
        second = container.resolve(Service)
        assert isinstance(repr(first), str)
        assert isinstance(str(first), str)
        assert first == first
        assert first != second
        assert len({first, second}) == 2
        assert created == []
        assert first.run() == id(created[0])


@pytest.mark.parametrize("decorator_count", [0, 2])
@pytest.mark.parametrize("bound_method", [False, True])
def test_sync_target_and_bound_method_cannot_escape_through_decorators(decorator_count, bound_method):
    class Resource:
        closed = False

    created: list[Resource] = []

    def resource_factory() -> Iterator[Resource]:
        resource = Resource()
        created.append(resource)
        try:
            yield resource
        finally:
            resource.closed = True

    class Service(Protocol):
        def export(self) -> object: ...

    class Implementation:
        def __init__(self, resource: Resource):
            self._resource = resource

        def export(self) -> object:
            return self._read if bound_method else self

        def _read(self) -> bool:
            return self._resource.closed

    class Wrapper:
        def __init__(self, inner: Service):
            self._inner = inner

        def export(self) -> object:
            return self._inner.export()

    builder = ContainerBuilder()
    builder.register(Resource, factory=resource_factory, lifespan="scoped")
    builder.register(Service, Implementation, scope="per_call")
    for _ in range(decorator_count):
        builder.register_decorator(Service, Wrapper)
    with builder.build() as container:
        service = container.resolve(Service)
        assert created == []
        with pytest.raises(RuntimeError, match="scope"):
            service.export()
        assert len(created) == 1
        assert created[0].closed


@pytest.mark.parametrize("decorator_count", [0, 2])
@pytest.mark.parametrize("bound_method", [False, True])
async def test_async_target_and_bound_method_cannot_escape_through_decorators(decorator_count, bound_method):
    class Resource:
        closed = False

    created: list[Resource] = []

    async def resource_factory() -> AsyncIterator[Resource]:
        resource = Resource()
        created.append(resource)
        try:
            yield resource
        finally:
            await asyncio.sleep(0)
            resource.closed = True

    class Service(Protocol):
        async def export(self) -> object: ...

    class Implementation:
        def __init__(self, resource: Resource):
            self._resource = resource

        async def export(self) -> object:
            return self._read if bound_method else self

        def _read(self) -> bool:
            return self._resource.closed

    class Wrapper:
        def __init__(self, inner: Service):
            self._inner = inner

        async def export(self) -> object:
            return await self._inner.export()

    builder = ContainerBuilder()
    builder.register(Resource, factory=resource_factory, lifespan="scoped")
    builder.register(Service, Implementation, scope="per_call")
    for _ in range(decorator_count):
        builder.register_decorator(Service, Wrapper)
    async with builder.build() as container:
        service = container.resolve(Service)
        assert created == []
        with pytest.raises(RuntimeError, match="scope"):
            await service.export()
        assert len(created) == 1
        assert created[0].closed
