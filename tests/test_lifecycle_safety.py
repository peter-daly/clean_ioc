import asyncio
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest

from clean_ioc.core import (
    CaptiveDependencyError,
    CircularDependencyError,
    Container,
    Lifespan,
)


class _CircularA:
    def __init__(self, dependency: "_CircularB"):
        self.dependency = dependency


class _CircularB:
    def __init__(self, dependency: _CircularA):
        self.dependency = dependency


def test_circular_dependencies_raise_a_diagnostic_error():
    container = Container()
    container.register(_CircularA)
    container.register(_CircularB)

    with pytest.raises(CircularDependencyError) as raised:
        container.resolve(_CircularA)

    assert raised.value.message == "Circular dependency detected: _CircularA -> _CircularB -> _CircularA"


def test_singleton_cannot_capture_a_scoped_dependency():
    class RequestState:
        pass

    class ApplicationService:
        def __init__(self, request_state: RequestState):
            self.request_state = request_state

    container = Container()
    container.register(RequestState, lifespan=Lifespan.scoped)
    container.register(ApplicationService, lifespan=Lifespan.singleton)

    with container.new_scope() as scope:
        with pytest.raises(CaptiveDependencyError) as raised:
            scope.resolve(ApplicationService)

    assert "ApplicationService cannot depend on scoped RequestState" in str(raised.value)


def test_singleton_cannot_capture_an_instance_owned_by_a_child_scope():
    class RequestState:
        pass

    class ApplicationService:
        def __init__(self, request_state: RequestState):
            self.request_state = request_state

    container = Container()
    container.register(ApplicationService, lifespan=Lifespan.singleton)

    with container.new_scope() as scope:
        scope.register(RequestState, instance=RequestState())
        with pytest.raises(CaptiveDependencyError):
            scope.resolve(ApplicationService)


def test_singleton_can_use_a_prebuilt_instance_owned_by_the_root_container():
    class Settings:
        pass

    class ApplicationService:
        def __init__(self, settings: Settings):
            self.settings = settings

    settings = Settings()
    container = Container()
    container.register(Settings, instance=settings)
    container.register(ApplicationService, lifespan=Lifespan.singleton)

    assert container.resolve(ApplicationService).settings is settings


def test_concurrent_threads_build_one_singleton():
    class Client:
        pass

    calls = 0
    calls_lock = threading.Lock()
    started = threading.Event()
    release = threading.Event()

    def create_client() -> Client:
        nonlocal calls
        with calls_lock:
            calls += 1
        started.set()
        release.wait(timeout=2)
        return Client()

    container = Container()
    container.register(Client, factory=create_client, lifespan=Lifespan.singleton)

    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = [executor.submit(container.resolve, Client) for _ in range(8)]
        assert started.wait(timeout=2)
        release.set()
        clients = [future.result(timeout=2) for future in futures]

    assert calls == 1
    assert len({id(client) for client in clients}) == 1


def test_falsey_singleton_is_cached():
    calls = 0

    def create_number() -> int:
        nonlocal calls
        calls += 1
        return 0

    container = Container()
    container.register(int, factory=create_number, lifespan=Lifespan.singleton)

    assert container.resolve(int) == 0
    assert container.resolve(int) == 0
    assert calls == 1


@pytest.mark.asyncio
async def test_concurrent_async_resolutions_build_one_singleton():
    class Client:
        pass

    calls = 0

    async def create_client() -> Client:
        nonlocal calls
        calls += 1
        await asyncio.sleep(0)
        return Client()

    container = Container()
    container.register(Client, factory=create_client, lifespan=Lifespan.singleton)

    clients = await asyncio.gather(*(container.resolve_async(Client) for _ in range(20)))

    assert calls == 1
    assert len({id(client) for client in clients}) == 1


@pytest.mark.asyncio
async def test_concurrent_async_resolutions_build_one_instance_per_scope():
    class RequestState:
        pass

    calls = 0

    async def create_request_state() -> RequestState:
        nonlocal calls
        calls += 1
        await asyncio.sleep(0)
        return RequestState()

    container = Container()
    container.register(RequestState, factory=create_request_state, lifespan=Lifespan.scoped)

    async with container.new_scope() as first_scope:
        first_results = await asyncio.gather(*(first_scope.resolve_async(RequestState) for _ in range(10)))
    async with container.new_scope() as second_scope:
        second_results = await asyncio.gather(*(second_scope.resolve_async(RequestState) for _ in range(10)))

    assert calls == 2
    assert len({id(item) for item in first_results}) == 1
    assert len({id(item) for item in second_results}) == 1
    assert first_results[0] is not second_results[0]


@pytest.mark.asyncio
async def test_failed_shared_build_can_be_retried():
    class Client:
        pass

    calls = 0

    async def create_client() -> Client:
        nonlocal calls
        calls += 1
        await asyncio.sleep(0)
        if calls == 1:
            raise RuntimeError("temporary failure")
        return Client()

    container = Container()
    container.register(Client, factory=create_client, lifespan=Lifespan.singleton)

    first_results = await asyncio.gather(
        *(container.resolve_async(Client) for _ in range(5)),
        return_exceptions=True,
    )
    client = await container.resolve_async(Client)

    assert all(isinstance(result, RuntimeError) for result in first_results)
    assert calls == 2
    assert isinstance(client, Client)
