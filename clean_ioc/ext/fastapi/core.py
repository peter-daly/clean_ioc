from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated, AsyncGenerator, TypeVar, cast

from starlette.requests import HTTPConnection

from clean_ioc import ComponentFilter, Scope, default_component_filter
from clean_ioc.ext.asgi import (
    ASGIApp,
    ASGIIntegrationError,
    ASGIScope,
    CleanIocMiddleware,
    Receive,
    Send,
    get_scope,
)
from fastapi import Depends, FastAPI, Request, WebSocket, params

TService = TypeVar("TService")

_CONNECTION_PROVIDED_KEY = "clean_ioc.connection_provided"
_INSTALLED_STATE_KEY = "clean_ioc_installed"
_RESOLVE_METADATA_KEY = "__clean_ioc_resolve__"


class FastAPIIntegrationError(RuntimeError):
    """Raised when the FastAPI application and compiled container disagree."""


@dataclass(frozen=True, slots=True)
class _ResolveRequest:
    service_type: type
    filter: ComponentFilter


def _route_resolve_requests(app: FastAPI):
    for route in app.routes:
        dependant = getattr(route, "dependant", None)
        if dependant is None:
            continue
        stack = list(getattr(dependant, "dependencies", ()))
        seen: set[int] = set()
        while stack:
            dependency = stack.pop()
            if id(dependency) in seen:
                continue
            seen.add(id(dependency))
            request = getattr(getattr(dependency, "call", None), _RESOLVE_METADATA_KEY, None)
            if request is not None:
                yield route, cast(_ResolveRequest, request)
            stack.extend(getattr(dependency, "dependencies", ()))


def validate_fastapi_routes(app: FastAPI, root_scope: Scope) -> None:
    """Validate every ``Resolve`` dependency against the frozen root plan."""

    missing: list[str] = []
    for route, request in _route_resolve_requests(app):
        if root_scope.has_component(request.service_type, request.filter):
            continue
        methods = getattr(route, "methods", None)
        method_label = ",".join(sorted(methods)) if methods else "WEBSOCKET"
        path = getattr(route, "path", "<unknown route>")
        missing.append(f"{method_label} {path}: {request.service_type!r}")
    if missing:
        details = "\n".join(f"- {item}" for item in missing)
        raise FastAPIIntegrationError(f"FastAPI routes contain unresolved Clean IoC entry points:\n{details}")


class _CleanIocMiddleware(CleanIocMiddleware):
    """Add FastAPI route validation to the shared ASGI lifecycle boundary."""

    def __init__(self, app: ASGIApp, *, root_scope: Scope, fastapi_app: FastAPI):
        super().__init__(app, root_scope=root_scope)
        self.fastapi_app = fastapi_app

    async def __call__(self, scope: ASGIScope, receive: Receive, send: Send) -> None:
        scope_type = scope["type"]
        if scope_type == "lifespan":
            validate_fastapi_routes(self.fastapi_app, self.root_scope)
        try:
            await super().__call__(scope, receive, send)
        finally:
            if scope_type in ("http", "websocket"):
                scope.pop(_CONNECTION_PROVIDED_KEY, None)


def install_fastapi(app: FastAPI, root_scope: Scope) -> FastAPI:
    """Install Clean IoC lifecycle and request-scope management on ``app``."""

    if getattr(app.state, _INSTALLED_STATE_KEY, False):
        raise FastAPIIntegrationError("Clean IoC is already installed on this FastAPI application")
    setattr(app.state, _INSTALLED_STATE_KEY, True)
    app.add_middleware(_CleanIocMiddleware, root_scope=root_scope, fastapi_app=app)
    return app


def _provide_connection_values(scope: Scope, connection: HTTPConnection) -> None:
    if connection.scope.get(_CONNECTION_PROVIDED_KEY):
        return
    if scope.has_scope_slot(HTTPConnection):
        scope.provide(HTTPConnection, connection)
    if isinstance(connection, Request) and scope.has_scope_slot(Request):
        scope.provide(Request, connection)
    if isinstance(connection, WebSocket) and scope.has_scope_slot(WebSocket):
        scope.provide(WebSocket, connection)
    connection.scope[_CONNECTION_PROVIDED_KEY] = True


async def _get_scope(connection: HTTPConnection) -> AsyncGenerator[Scope, None]:
    """Return the operation scope installed for an HTTP request or WebSocket."""

    try:
        request_scope = get_scope(connection.scope)
    except ASGIIntegrationError:
        raise FastAPIIntegrationError("No Clean IoC request scope; call install_fastapi(app, container)")
    _provide_connection_values(request_scope, connection)
    yield request_scope


def Resolve(  # noqa: N802
    service_type: type[TService],
    filter: ComponentFilter = default_component_filter,
) -> Annotated[TService, params.Depends]:
    """Create a FastAPI dependency that resolves ``service_type`` asynchronously."""

    async def resolver(scope: Annotated[Scope, Depends(_get_scope, scope="request")]):
        return await scope.resolve_async(service_type, filter=filter)

    setattr(resolver, _RESOLVE_METADATA_KEY, _ResolveRequest(service_type, filter))
    return Depends(resolver)


__all__ = [
    "FastAPIIntegrationError",
    "Resolve",
    "install_fastapi",
    "validate_fastapi_routes",
]
