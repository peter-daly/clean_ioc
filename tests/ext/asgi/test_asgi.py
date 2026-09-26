import asyncio
from typing import Any

import pytest

from clean_ioc import ContainerBuilder, ScopeClosedError
from clean_ioc.ext.asgi import (
    ASGIBundle,
    ASGIConnection,
    ASGIIntegrationError,
    CleanIocMiddleware,
    RequestHeaderReader,
    ResponseHeaderWriter,
    get_scope,
)


def _http_scope(path: str, *, method: str = "GET", headers=()) -> dict[str, Any]:
    return {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": method,
        "scheme": "http",
        "path": path,
        "raw_path": path.encode("ascii"),
        "query_string": b"",
        "headers": list(headers),
        "server": ("testserver", 80),
        "client": ("testclient", 50000),
        "root_path": "",
    }


async def _request(app, path: str, *, method: str = "GET", headers=()) -> list[dict[str, Any]]:
    messages: list[dict[str, Any]] = []

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message):
        messages.append(dict(message))

    await app(_http_scope(path, method=method, headers=headers), receive, send)
    return messages


class _LifespanSession:
    def __init__(self, app):
        self.app = app
        self.received: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self.sent: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self.task: asyncio.Task | None = None

    async def start(self) -> None:
        async def run():
            await self.app(
                {"type": "lifespan", "asgi": {"version": "3.0"}, "state": {}},
                self.received.get,
                self.sent.put,
            )

        self.task = asyncio.create_task(run())
        await self.received.put({"type": "lifespan.startup"})
        assert await self.sent.get() == {"type": "lifespan.startup.complete"}

    async def stop(self) -> None:
        assert self.task is not None
        await self.received.put({"type": "lifespan.shutdown"})
        assert await self.sent.get() == {"type": "lifespan.shutdown.complete"}
        await self.task


def test_asgi_bundle_runs_once_and_declares_framework_independent_boundary_types():
    builder = ContainerBuilder()
    builder.apply_bundle(ASGIBundle())
    builder.apply_bundle(ASGIBundle())
    container = builder.build()

    assert container.has_scope_slot(ASGIConnection)
    assert container.has_scope_slot(ResponseHeaderWriter)
    assert container.has_component(RequestHeaderReader)
    assert len([component for component in container.components if component.service_type is RequestHeaderReader]) == 1


@pytest.mark.asyncio
async def test_middleware_provides_unique_operation_scopes_and_header_adapters():
    scope_ids: list[str] = []

    class BoundaryService:
        def __init__(
            self,
            connection: ASGIConnection,
            request_headers: RequestHeaderReader,
            response_headers: ResponseHeaderWriter,
        ):
            self.connection = connection
            self.request_headers = request_headers
            self.response_headers = response_headers

    builder = ContainerBuilder()
    builder.apply_bundle(ASGIBundle())
    builder.register(BoundaryService)
    container = builder.build()

    async def endpoint(scope, receive, send):
        operation_scope = get_scope(scope)
        scope_ids.append(operation_scope.id)
        service = await operation_scope.resolve_async(BoundaryService)
        assert service.connection.scope is scope
        service.response_headers.write("X-Request-ID", service.request_headers.read("X-Request-ID"))
        await send({"type": "http.response.start", "status": 204, "headers": []})
        await send({"type": "http.response.body", "body": b""})

    app = CleanIocMiddleware(endpoint, root_scope=container)
    first = await _request(app, "/", headers=[(b"x-request-id", b"first")])
    second = await _request(app, "/", headers=[(b"x-request-id", b"second")])

    assert scope_ids[0] != scope_ids[1]
    assert (b"x-request-id", b"first") in first[0]["headers"]
    assert (b"x-request-id", b"second") in second[0]["headers"]


@pytest.mark.asyncio
async def test_operation_scope_closes_after_the_complete_response():
    events: list[str] = []

    class Resource:
        pass

    async def resource_factory():
        events.append("created")
        try:
            yield Resource()
        finally:
            events.append("closed")

    builder = ContainerBuilder()
    builder.register(Resource, factory=resource_factory, lifespan="scoped")
    container = builder.build()

    async def endpoint(scope, receive, send):
        resource = await get_scope(scope).resolve_async(Resource)
        assert isinstance(resource, Resource)
        await send({"type": "http.response.start", "status": 204, "headers": []})
        await send({"type": "http.response.body", "body": b""})

    await _request(CleanIocMiddleware(endpoint, root_scope=container), "/")

    assert events == ["created", "closed"]


@pytest.mark.asyncio
async def test_lifespan_owns_root_singletons_until_shutdown():
    events: list[str] = []

    class SingletonResource:
        pass

    async def singleton_factory():
        events.append("created")
        try:
            yield SingletonResource()
        finally:
            events.append("closed")

    builder = ContainerBuilder()
    builder.register(SingletonResource, factory=singleton_factory, lifespan="singleton")
    container = builder.build()

    async def endpoint(scope, receive, send):
        await get_scope(scope).resolve_async(SingletonResource)
        await send({"type": "http.response.start", "status": 204, "headers": []})
        await send({"type": "http.response.body", "body": b""})

    async def lifespan_aware_app(scope, receive, send):
        if scope["type"] == "lifespan":
            while True:
                message = await receive()
                if message["type"] == "lifespan.startup":
                    await send({"type": "lifespan.startup.complete"})
                elif message["type"] == "lifespan.shutdown":
                    await send({"type": "lifespan.shutdown.complete"})
                    return
        else:
            await endpoint(scope, receive, send)

    app = CleanIocMiddleware(lifespan_aware_app, root_scope=container)
    lifespan = _LifespanSession(app)
    await lifespan.start()
    await _request(app, "/")

    assert events == ["created"]

    await lifespan.stop()

    assert events == ["created", "closed"]
    with pytest.raises(ScopeClosedError):
        container.new_scope()


def test_get_scope_rejects_an_unwrapped_application():
    with pytest.raises(ASGIIntegrationError, match="Clean IoC operation scope"):
        get_scope(_http_scope("/"))
