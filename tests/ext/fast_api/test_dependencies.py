from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from clean_ioc import Container
from clean_ioc.core import Lifespan
from clean_ioc.ext.fastapi import Resolve, add_container_to_app
from clean_ioc.ext.fastapi.dependencies import (
    RequestHeaderReader,
    ResponseHeaderWriter,
    add_request_header_reader_to_scope,
    add_response_header_writer_to_scope,
)


def test_response_writer_writes_a_header_to_response():
    class MyDependency:
        HEADER_NAME = "X-Action"
        HEADER_VALUE = "my-action"

        def __init__(self, header_writer: ResponseHeaderWriter):
            self.header_writer = header_writer

        def do_action(self):
            self.header_writer.write(self.HEADER_NAME, self.HEADER_VALUE)

    @asynccontextmanager
    async def lifespan(a):
        with Container() as container:
            container.register(MyDependency)
            async with add_container_to_app(a, container):
                yield

    app = FastAPI(lifespan=lifespan, dependencies=[Depends(add_response_header_writer_to_scope)])

    @app.get("/")
    def read_root(my_dependency: MyDependency = Resolve(MyDependency)):
        my_dependency.do_action()
        return {"message": "Hello World"}

    with TestClient(app) as test_client:
        response = test_client.get("/")
        assert response.status_code == 200
        assert response.headers["X-Action"] == "my-action"


def test_request_header_reader_reads_headers():
    class MyDependency:
        HEADER_NAME = "X-Action"

        def __init__(self, header_reader: RequestHeaderReader):
            self.header_reader = header_reader

        def do_action(self) -> str:
            return self.header_reader.read(self.HEADER_NAME)

    @asynccontextmanager
    async def lifespan(a):
        with Container() as container:
            container.register(MyDependency)
            async with add_container_to_app(a, container):
                yield

    app = FastAPI(lifespan=lifespan, dependencies=[Depends(add_request_header_reader_to_scope)])

    @app.get("/")
    def read_root(my_dependency: MyDependency = Resolve(MyDependency)):
        header_value = my_dependency.do_action()
        return {"action": header_value}

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

    @asynccontextmanager
    async def lifespan(a):
        with Container() as container:
            container.register(MyDependency, factory=my_dependency_factory)
            async with add_container_to_app(a, container):
                yield

    app = FastAPI(lifespan=lifespan, dependencies=[Depends(add_request_header_reader_to_scope)])

    @app.get("/")
    async def read_root(my_dependency: MyDependency = Resolve(MyDependency)):
        header_value = my_dependency.do_action()
        return {"action": header_value}

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

    @asynccontextmanager
    async def lifespan(a):
        with Container() as container:
            container.register(MyDependency, lifespan=Lifespan.scoped)
            async with add_container_to_app(a, container):
                yield

    app = FastAPI(lifespan=lifespan)

    @app.get("/")
    async def read_root(my_dependency: MyDependency = Resolve(MyDependency)):
        uid = my_dependency.do_thing()
        return {"uid": uid}

    with TestClient(app) as test_client:
        response_1 = test_client.get("/")
        response_2 = test_client.get("/")

        body_1 = response_1.json()
        body_2 = response_2.json()

        assert body_1["uid"] != body_2["uid"]
