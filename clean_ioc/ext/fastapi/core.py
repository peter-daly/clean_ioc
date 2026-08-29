from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Annotated, AsyncGenerator, TypeVar, cast

from starlette.requests import HTTPConnection
from starlette.types import ASGIApp, Receive, Send
from starlette.types import Scope as ASGIScope

from clean_ioc import ComponentFilter, Container, Scope, default_component_filter
from fastapi import Depends, FastAPI, Request, WebSocket, params

logger = logging.getLogger(__name__)
TService = TypeVar("TService")

_SCOPE_KEY = "clean_ioc.scope"
_CONNECTION_PROVIDED_KEY = "clean_ioc.connection_provided"
_ROOT_SCOPE_STATE_KEY = "clean_ioc_root_scope"
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


class CleanIocMiddleware:
    """Own the root runtime and one child scope per HTTP/WebSocket operation."""

    def __init__(self, app: ASGIApp, *, root_scope: Scope, fastapi_app: FastAPI):
        self.app = app
        self.root_scope = root_scope
        self.fastapi_app = fastapi_app

    async def __call__(self, scope: ASGIScope, receive: Receive, send: Send) -> None:
        scope_type = scope["type"]
        if scope_type == "lifespan":
            validate_fastapi_routes(self.fastapi_app, self.root_scope)
            async with self.root_scope:
                await self.app(scope, receive, send)
            return

        if scope_type not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return

        # Imported lazily to keep the public dependency module free to import get_scope.
        from .dependencies import ResponseHeaderWriter

        async with self.root_scope.new_scope() as request_scope:
            scope[_SCOPE_KEY] = request_scope
            header_writer = ResponseHeaderWriter()
            if request_scope.has_scope_slot(ResponseHeaderWriter):
                request_scope.provide(ResponseHeaderWriter, header_writer)

            async def send_with_headers(message):
                if message["type"] in ("http.response.start", "websocket.accept"):
                    header_writer.apply(message)
                await send(message)

            try:
                await self.app(scope, receive, send_with_headers)
            finally:
                scope.pop(_SCOPE_KEY, None)
                scope.pop(_CONNECTION_PROVIDED_KEY, None)


def install_fastapi(app: FastAPI, root_scope: Scope) -> FastAPI:
    """Install Clean IoC lifecycle and request-scope management on ``app``."""

    if getattr(app.state, _INSTALLED_STATE_KEY, False):
        raise FastAPIIntegrationError("Clean IoC is already installed on this FastAPI application")
    setattr(app.state, _INSTALLED_STATE_KEY, True)
    app.add_middleware(CleanIocMiddleware, root_scope=root_scope, fastapi_app=app)
    return app


@asynccontextmanager
async def add_container_to_app(app: FastAPI, container: Container):
    """Compatibility lifespan helper; prefer :func:`install_fastapi`."""

    async with add_root_scope_to_app(app, container):
        yield


@asynccontextmanager
async def add_root_scope_to_app(app: FastAPI, root_scope: Scope):
    """Compatibility lifespan helper for applications with custom composition."""

    async with root_scope:
        logger.debug("adding root scope to the FastAPI app")
        setattr(app.state, _ROOT_SCOPE_STATE_KEY, root_scope)
        try:
            yield
        finally:
            delattr(app.state, _ROOT_SCOPE_STATE_KEY)
            logger.debug("releasing root scope from the FastAPI app")


def get_root_scope_from_app(app: FastAPI) -> Scope:
    # ``root_scope`` remains a fallback for applications using the pre-V2 helper
    # and for existing test overrides.
    root_scope = getattr(app.state, "root_scope", None)
    if root_scope is None:
        root_scope = getattr(app.state, _ROOT_SCOPE_STATE_KEY, None)
    if root_scope is None:
        raise FastAPIIntegrationError(
            "Clean IoC is not installed. Call install_fastapi(app, container) or use add_container_to_app()."
        )
    return cast(Scope, root_scope)


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


async def get_scope(connection: HTTPConnection) -> AsyncGenerator[Scope, None]:
    """Return the operation scope installed for an HTTP request or WebSocket."""

    existing_scope = connection.scope.get(_SCOPE_KEY)
    if existing_scope is not None:
        request_scope = cast(Scope, existing_scope)
        _provide_connection_values(request_scope, connection)
        yield request_scope
        return

    # Compatibility path for add_container_to_app(). The middleware path above
    # owns the scope through the complete ASGI operation instead.
    root_scope = get_root_scope_from_app(connection.app)
    async with root_scope.new_scope() as request_scope:
        connection.scope[_SCOPE_KEY] = request_scope
        _provide_connection_values(request_scope, connection)
        try:
            yield request_scope
        finally:
            connection.scope.pop(_SCOPE_KEY, None)
            connection.scope.pop(_CONNECTION_PROVIDED_KEY, None)


def Resolve(  # noqa: N802
    service_type: type[TService],
    filter: ComponentFilter = default_component_filter,
) -> Annotated[TService, params.Depends]:
    """Create a FastAPI dependency that resolves ``service_type`` asynchronously."""

    async def resolver(scope: Annotated[Scope, Depends(get_scope, scope="request")]):
        return await scope.resolve_async(service_type, filter=filter)

    setattr(resolver, _RESOLVE_METADATA_KEY, _ResolveRequest(service_type, filter))
    return Depends(resolver)


__all__ = [
    "CleanIocMiddleware",
    "FastAPIIntegrationError",
    "Resolve",
    "add_container_to_app",
    "add_root_scope_to_app",
    "get_root_scope_from_app",
    "get_scope",
    "install_fastapi",
    "validate_fastapi_routes",
]
