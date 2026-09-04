"""End-to-end FastAPI request benchmarks for a five-layer dependency chain."""

from collections.abc import Iterator
from typing import Annotated

from benchbro import Case, system
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from clean_ioc import ContainerBuilder
from clean_ioc.ext.fastapi import Resolve, install_fastapi


class LayerOne:
    def __init__(self):
        self.value = 1


class LayerTwo:
    def __init__(self, layer_one: LayerOne):
        self.value = layer_one.value + 1


class LayerThree:
    def __init__(self, layer_two: LayerTwo):
        self.value = layer_two.value + 1


class LayerFour:
    def __init__(self, layer_three: LayerThree):
        self.value = layer_three.value + 1


class LayerFive:
    def __init__(self, layer_four: LayerFour):
        self.value = layer_four.value + 1


async def provide_layer_one() -> LayerOne:
    return LayerOne()


async def provide_layer_two(
    layer_one: Annotated[LayerOne, Depends(provide_layer_one, use_cache=True)],
) -> LayerTwo:
    return LayerTwo(layer_one)


async def provide_layer_three(
    layer_two: Annotated[LayerTwo, Depends(provide_layer_two, use_cache=True)],
) -> LayerThree:
    return LayerThree(layer_two)


async def provide_layer_four(
    layer_three: Annotated[LayerThree, Depends(provide_layer_three, use_cache=True)],
) -> LayerFour:
    return LayerFour(layer_three)


async def provide_layer_five(
    layer_four: Annotated[LayerFour, Depends(provide_layer_four, use_cache=True)],
) -> LayerFive:
    return LayerFive(layer_four)


def create_native_fastapi_app() -> FastAPI:
    app = FastAPI()

    @app.get("/chain")
    async def read_chain(
        layer_five: Annotated[LayerFive, Depends(provide_layer_five, use_cache=True)],
    ) -> int:
        return layer_five.value

    return app


def create_clean_ioc_fastapi_app() -> FastAPI:
    builder = ContainerBuilder()
    for service_type in (LayerOne, LayerTwo, LayerThree, LayerFour, LayerFive):
        builder.register(service_type, lifespan="once_per_graph")

    app = FastAPI()

    @app.get("/chain")
    async def read_chain(layer_five: LayerFive = Resolve(LayerFive)) -> int:
        return layer_five.value

    install_fastapi(app, builder.build())
    return app


def validate_client(client: TestClient) -> None:
    response = client.get("/chain")
    if response.status_code != 200 or response.json() != 5:
        raise RuntimeError(f"Unexpected benchmark response: {response.status_code} {response.text!r}")


@system(scope="benchmark")
def native_fastapi_client() -> Iterator[TestClient]:
    with TestClient(create_native_fastapi_app()) as client:
        validate_client(client)
        yield client


@system(scope="benchmark")
def clean_ioc_fastapi_client() -> Iterator[TestClient]:
    with TestClient(create_clean_ioc_fastapi_app()) as client:
        validate_client(client)
        yield client


fastapi_requests = Case(
    name="fastapi-five-layer-request",
    tags=["fastapi", "integration", "request"],
    gc_control="inherit",
    setup_timing="exclude",
    teardown_timing="exclude",
    adaptive=True,
    min_repeats=7,
    repeats=30,
    min_iterations=500,
    min_time_s=0.5,
    max_time_s=15.0,
    target_relative_margin_pct=3.0,
)


@fastapi_requests.benchmark(name="native-depends")
def native_depends(native_fastapi_client: TestClient) -> bytes:
    return native_fastapi_client.get("/chain").content


@fastapi_requests.benchmark(name="clean-ioc")
def clean_ioc(clean_ioc_fastapi_client: TestClient) -> bytes:
    return clean_ioc_fastapi_client.get("/chain").content
