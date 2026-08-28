from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from clean_ioc import Scope
from clean_ioc.ext.fastapi import Resolve, add_container_to_app
from clean_ioc.ext.fastapi.core import get_scope
from clean_ioc.ext.fastapi.dependencies import (
    RequestHeaderReader,
    add_request_header_reader_to_scope,
)
from experiments.compiled_container import CompiledChildScope, CompiledContainer
from experiments.compiled_fastapi import prepare_fastapi_scope_slots


def test_fastapi_request_local_registration_keeps_compiled_plan_eligible():
    class HeaderHandler:
        def __init__(self, headers: RequestHeaderReader):
            self.headers = headers

        def action(self) -> str:
            return self.headers.read("X-Action")

    observed_scopes: list[Scope] = []

    def observe_scope(scope: Scope = Depends(get_scope)) -> None:
        observed_scopes.append(scope)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        container = prepare_fastapi_scope_slots(CompiledContainer())
        container.register(HeaderHandler)
        report = container.seal()
        assert HeaderHandler in container._compiled_roots
        assert HeaderHandler not in {fallback.service_type for fallback in report.fallbacks}
        async with add_container_to_app(app, container):
            yield

    app = FastAPI(
        lifespan=lifespan,
        dependencies=[Depends(add_request_header_reader_to_scope), Depends(observe_scope)],
    )

    @app.get("/")
    async def read_root(handler: HeaderHandler = Resolve(HeaderHandler)):
        return {"action": handler.action()}

    with TestClient(app) as client:
        response = client.get("/", headers={"X-Action": "compiled"})

    assert response.status_code == 200
    assert response.json() == {"action": "compiled"}
    assert len(observed_scopes) == 1
    assert isinstance(observed_scopes[0], CompiledChildScope)
    assert observed_scopes[0]._compiled_eligible
