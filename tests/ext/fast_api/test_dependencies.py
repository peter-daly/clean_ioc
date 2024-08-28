from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel

import clean_ioc.registration_filters as rf
from clean_ioc import Container
from clean_ioc.bundles import RunOnceBundle
from clean_ioc.core import DependencySettings
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


def test_with_filtered_dependencies():
    class GenericDep:
        def __init__(self, name: str):
            self.name = name

        def get_name(self) -> str:
            return self.name

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return self

    def get_first_generic_dep():
        with GenericDep(name="dep_1") as dep:
            yield dep

    def get_second_generic_dep():
        with GenericDep(name="dep_2") as dep:
            yield dep

    def get_third_generic_dep():
        with GenericDep(name="dep_3") as dep:
            yield dep

    def get_fourth_generic_dep():
        with GenericDep(name="dep_4") as dep:
            yield dep

    class MyDependencyConfig(BaseModel):
        name: str

    class MyDependency:
        def __init__(self, config: MyDependencyConfig):
            self.name = config.name

        def get_name(self) -> str:
            return self.name

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return self

    class RegisterMyDependencyBundle(RunOnceBundle):
        def __init__(
            self,
            *,
            md_config: MyDependencyConfig,
            filter_name: str,
        ):
            self.md_config = md_config
            self.filter_name = filter_name

        def get_bundle_identifier(self) -> str:
            return f"{self.__class__.__name__}::{self.filter_name}"

        def apply(self, container: Container):
            reg_filter = rf.with_name(self.filter_name)
            filter_dependency_settings = DependencySettings(filter=reg_filter)

            container.register(MyDependencyConfig, name=self.filter_name, instance=self.md_config)

            container.register(
                MyDependency,
                name=self.filter_name,
                dependency_config={"config": filter_dependency_settings},
            )

    @asynccontextmanager
    async def lifespan(a):
        with Container() as container:
            container.apply_bundle(
                RegisterMyDependencyBundle(
                    md_config=MyDependencyConfig(name="value-1"),
                    filter_name="test-filter-1",
                ),
            )
            container.apply_bundle(
                RegisterMyDependencyBundle(
                    md_config=MyDependencyConfig(name="value-2"),
                    filter_name="test-filter-2",
                ),
            )
            async with add_container_to_app(a, container):
                yield

    app = FastAPI(lifespan=lifespan)

    @app.get("/")
    async def _(
        dep_1: MyDependency = Resolve(
            MyDependency,
            filter=rf.with_name("test-filter-1"),
        ),
        dep_2: MyDependency = Resolve(
            MyDependency,
            filter=rf.with_name("test-filter-2"),
        ),
        dep_3_1: GenericDep = Depends(get_first_generic_dep),
        dep_3_2: GenericDep = Depends(get_second_generic_dep),
        dep_3_3: GenericDep = Depends(get_third_generic_dep),
        dep_3_4: GenericDep = Depends(get_fourth_generic_dep),
    ):
        return {
            "one": dep_1.get_name(),
            "two": dep_2.get_name(),
            "three_1": dep_3_1.get_name(),
            "three_2": dep_3_2.get_name(),
            "three_3": dep_3_3.get_name(),
            "three_4": dep_3_4.get_name(),
        }

    with TestClient(app) as test_client:
        response = test_client.get("/")
        body = response.json()
        assert response.status_code == 200
        assert body["one"] == "value-1"
        assert body["two"] == "value-2"
        assert body["three_1"] == "dep_1"
        assert body["three_2"] == "dep_2"
        assert body["three_3"] == "dep_3"
        assert body["three_4"] == "dep_4"
