from contextlib import asynccontextmanager
from uuid import uuid4

import pytest
from fastapi import FastAPI, Request, WebSocket
from fastapi.responses import StreamingResponse
from fastapi.testclient import TestClient

import clean_ioc.component_filters as cf
from clean_ioc import ContainerBuilder, ContainerBuildError
from clean_ioc.ext.fastapi import (
    FastAPIBundle,
    FastAPIIntegrationError,
    RequestHeaderReader,
    Resolve,
    ResponseHeaderWriter,
    install_fastapi,
)


def test_fastapi_bundle_runs_once_per_class_for_root_and_overlay_builders():
    root = ContainerBuilder().build()

    for builder in (ContainerBuilder(), root.new_scope_builder()):
        builder.apply_bundle(FastAPIBundle())
        builder.apply_bundle(FastAPIBundle())
        scope = builder.build()

        assert scope.has_scope_slot(Request)
        assert scope.has_scope_slot(WebSocket)
        assert scope.has_component(RequestHeaderReader)
        assert len([component for component in scope.components if component.service_type is RequestHeaderReader]) == 1


def test_response_writer_writes_a_header_to_response():
    class MyDependency:
        HEADER_NAME = "X-Action"
        HEADER_VALUE = "my-action"

        def __init__(self, header_writer: ResponseHeaderWriter):
            self.header_writer = header_writer

        def do_action(self):
            self.header_writer.write(self.HEADER_NAME, self.HEADER_VALUE)

    builder = ContainerBuilder()
    builder.apply_bundle(FastAPIBundle())
    builder.register(MyDependency)
    app = FastAPI()

    @app.get("/")
    def read_root(my_dependency: MyDependency = Resolve(MyDependency)):
        my_dependency.do_action()
        return {"message": "Hello World"}

    install_fastapi(app, builder.build())

    with TestClient(app) as test_client:
        response = test_client.get("/")
        assert response.status_code == 200
        assert response.headers["X-Action"] == "my-action"


def test_request_scope_slot_rejects_singleton_capture_during_build():
    class SingletonService:
        def __init__(self, request: Request):
            self.request = request

    builder = ContainerBuilder()
    builder.apply_bundle(FastAPIBundle())
    builder.register(SingletonService, lifespan="singleton")

    with pytest.raises(ContainerBuildError) as raised:
        builder.build()

    report = raised.value.report
    assert report is not None
    issue = next(issue for issue in report.errors if issue.root and issue.root.endswith("SingletonService"))
    assert issue.code == "captive-runtime-scope"
    assert issue.path[-1].endswith("Request")


def test_request_header_reader_reads_headers():
    class MyDependency:
        HEADER_NAME = "X-Action"

        def __init__(self, header_reader: RequestHeaderReader):
            self.header_reader = header_reader

        def do_action(self) -> str:
            return self.header_reader.read(self.HEADER_NAME)

    builder = ContainerBuilder()
    builder.apply_bundle(FastAPIBundle())
    builder.register(MyDependency)
    app = FastAPI()

    @app.get("/")
    def read_root(my_dependency: MyDependency = Resolve(MyDependency)):
        header_value = my_dependency.do_action()
        return {"action": header_value}

    install_fastapi(app, builder.build())

    with TestClient(app) as test_client:
        response = test_client.get("/", headers={"X-Action": "my-action"})
        body = response.json()
        assert response.status_code == 200
        assert body["action"] == "my-action"


def test_with_async_generator_dependency():
    class MyDependency:
        HEADER_NAME = "X-Action"

        def __init__(self, header_reader: RequestHeaderReader):
            self.header_reader = header_reader

        def do_action(self) -> str:
            return self.header_reader.read(self.HEADER_NAME)

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return self

    async def my_dependency_factory(header_reader: RequestHeaderReader):
        async with MyDependency(header_reader=header_reader) as dep:
            yield dep

    builder = ContainerBuilder()
    builder.apply_bundle(FastAPIBundle())
    builder.register(MyDependency, factory=my_dependency_factory)
    app = FastAPI()

    @app.get("/")
    async def read_root(my_dependency: MyDependency = Resolve(MyDependency)):
        header_value = my_dependency.do_action()
        return {"action": header_value}

    install_fastapi(app, builder.build())

    with TestClient(app) as test_client:
        response = test_client.get("/", headers={"X-Action": "my-action"})
        body = response.json()
        assert response.status_code == 200
        assert body["action"] == "my-action"


def test_scope_is_unique_per_request():
    class MyDependency:
        def __init__(self):
            self.uid = str(uuid4())

        def do_thing(self) -> str:
            return self.uid

    builder = ContainerBuilder()
    builder.register(MyDependency, lifespan="scoped")
    app = FastAPI()

    @app.get("/")
    async def read_root(my_dependency: MyDependency = Resolve(MyDependency)):
        uid = my_dependency.do_thing()
        return {"uid": uid}

    install_fastapi(app, builder.build())

    with TestClient(app) as test_client:
        response_1 = test_client.get("/")
        response_2 = test_client.get("/")

        body_1 = response_1.json()
        body_2 = response_2.json()

        assert body_1["uid"] != body_2["uid"]


def test_install_fastapi_provides_request_and_header_adapters_without_global_dependencies():
    class BoundaryAwareService:
        def __init__(
            self,
            request: Request,
            header_reader: RequestHeaderReader,
            header_writer: ResponseHeaderWriter,
        ):
            self.request = request
            self.header_reader = header_reader
            self.header_writer = header_writer

        def run(self) -> dict[str, str]:
            self.header_writer.write("X-Clean-IoC", "installed")
            return {
                "path": self.request.url.path,
                "request-id": self.header_reader.read("X-Request-ID"),
            }

    builder = ContainerBuilder()
    builder.apply_bundle(FastAPIBundle())
    builder.register(BoundaryAwareService)
    container = builder.build()

    app = FastAPI()
    install_fastapi(app, container)

    @app.get("/boundary")
    async def boundary(service: BoundaryAwareService = Resolve(BoundaryAwareService)):
        return service.run()

    with TestClient(app) as client:
        response = client.get("/boundary", headers={"X-Request-ID": "abc-123"})

    assert response.status_code == 200
    assert response.json() == {"path": "/boundary", "request-id": "abc-123"}
    assert response.headers["X-Clean-IoC"] == "installed"


def test_install_fastapi_supports_websocket_connection_scopes():
    class WebSocketService:
        def __init__(
            self,
            websocket: WebSocket,
            headers: RequestHeaderReader,
            response_headers: ResponseHeaderWriter,
        ):
            self.websocket = websocket
            self.headers = headers
            response_headers.write("X-Connection", "accepted")

        def message(self) -> str:
            return f"{self.websocket.url.path}:{self.headers.read('X-Client')}"

    builder = ContainerBuilder()
    builder.apply_bundle(FastAPIBundle())
    builder.register(WebSocketService)
    container = builder.build()

    app = FastAPI()
    install_fastapi(app, container)

    @app.websocket("/socket")
    async def socket(websocket: WebSocket, service: WebSocketService = Resolve(WebSocketService)):
        await websocket.accept()
        await websocket.send_text(service.message())
        await websocket.close()

    with TestClient(app) as client:
        with client.websocket_connect("/socket", headers={"X-Client": "browser"}) as websocket:
            message = websocket.receive_text()
            response_headers = websocket.extra_headers

    assert message == "/socket:browser"
    assert response_headers is not None
    assert (b"x-connection", b"accepted") in response_headers


def test_request_scope_closes_after_streaming_response_finishes():
    events: list[str] = []

    class StreamResource:
        pass

    async def stream_resource_factory():
        events.append("created")
        try:
            yield StreamResource()
        finally:
            events.append("closed")

    builder = ContainerBuilder()
    builder.register(StreamResource, factory=stream_resource_factory, lifespan="scoped")
    container = builder.build()

    app = FastAPI()
    install_fastapi(app, container)

    @app.get("/stream")
    async def stream(resource: StreamResource = Resolve(StreamResource)):
        async def body():
            assert isinstance(resource, StreamResource)
            events.append("streamed")
            yield b"complete"

        return StreamingResponse(body())

    with TestClient(app) as client:
        response = client.get("/stream")

    assert response.content == b"complete"
    assert events == ["created", "streamed", "closed"]


def test_request_scope_closes_when_route_raises():
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

    app = FastAPI()
    install_fastapi(app, container)

    @app.get("/failure")
    async def failure(resource: Resource = Resolve(Resource)):
        assert isinstance(resource, Resource)
        raise RuntimeError("route failed")

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get("/failure")

    assert response.status_code == 500
    assert events == ["created", "closed"]


def test_install_fastapi_wraps_custom_app_lifespan_and_closes_singletons():
    events: list[str] = []

    class SingletonResource:
        pass

    async def singleton_factory():
        events.append("singleton-created")
        try:
            yield SingletonResource()
        finally:
            events.append("singleton-closed")

    builder = ContainerBuilder()
    builder.register(SingletonResource, factory=singleton_factory, lifespan="singleton")
    container = builder.build()

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        events.append("app-started")
        yield
        events.append("app-stopped")

    app = FastAPI(lifespan=lifespan)
    install_fastapi(app, container)

    @app.get("/")
    async def root(resource: SingletonResource = Resolve(SingletonResource)):
        assert isinstance(resource, SingletonResource)
        return {"ok": True}

    with TestClient(app) as client:
        assert client.get("/").json() == {"ok": True}

    assert events == ["app-started", "singleton-created", "app-stopped", "singleton-closed"]


def test_install_fastapi_rejects_unresolvable_route_filter_at_startup():
    class Service:
        pass

    builder = ContainerBuilder()
    builder.register(Service, name="available")
    container = builder.build()

    app = FastAPI()
    install_fastapi(app, container)

    @app.get("/missing")
    async def missing(service: Service = Resolve(Service, filter=cf.with_name("missing"))):
        return service

    with pytest.raises(FastAPIIntegrationError, match=r"GET /missing.*Service"):
        with TestClient(app):
            pass


def test_install_fastapi_cannot_be_applied_twice():
    container = ContainerBuilder().build()
    app = FastAPI()

    install_fastapi(app, container)

    with pytest.raises(FastAPIIntegrationError, match="already installed"):
        install_fastapi(app, container)
