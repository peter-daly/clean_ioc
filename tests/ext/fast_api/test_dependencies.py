from fastapi.testclient import TestClient
import pytest
from fastapi import FastAPI, Depends
from clean_ioc import Container
from clean_ioc.ext.fastapi import add_container_to_app, Resolve
from clean_ioc.ext.fastapi.dependencies import add_request_header_reader_to_scope, add_response_header_writer_to_scope, ResponseHeaderWriter, RequestHeaderReader


def test_response_writer_writes_a_header_to_response():

    class MyDependency:
        HEADER_NAME = "X-Action"
        HEADER_VALUE = "my-action"
        def __init__(self, header_writer: ResponseHeaderWriter):
            self.header_writer = header_writer

        def do_action(self):
            self.header_writer.write(self.HEADER_NAME, self.HEADER_VALUE)

    container = Container()
    container.register(MyDependency)
    app = FastAPI(dependencies=[Depends(add_response_header_writer_to_scope)])
    add_container_to_app(app, container)
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

    container = Container()
    container.register(MyDependency)
    app = FastAPI(dependencies=[Depends(add_request_header_reader_to_scope)])
    add_container_to_app(app, container)
    @app.get("/")
    def read_root(my_dependency: MyDependency = Resolve(MyDependency)):
        header_value = my_dependency.do_action()
        return {"action": header_value}

    with TestClient(app) as test_client:
        response = test_client.get("/", headers={"X-Action": "my-action"})
        body = response.json()
        assert response.status_code == 200
        assert body["action"] == "my-action"