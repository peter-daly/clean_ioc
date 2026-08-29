from __future__ import annotations

from collections.abc import Callable, MutableMapping
from typing import Any

from starlette.datastructures import MutableHeaders
from starlette.requests import HTTPConnection

from clean_ioc import ComponentBuilder, Lifespan, Scope
from clean_ioc.functional_utils import constant
from fastapi import Depends, Request, Response, WebSocket

from .core import get_scope


class RequestHeaderReader:
    """Framework-light access to HTTP or WebSocket connection headers."""

    def __init__(self, connection: HTTPConnection):
        self.connection = connection

    @property
    def request(self) -> HTTPConnection:
        """Compatibility alias for the connection used by earlier releases."""

        return self.connection

    def read(self, key: str, default_value: str = "") -> str:
        return self.connection.headers.get(key, default_value)

    def header_exists(self, key: str) -> bool:
        return key in self.connection.headers

    def __iter__(self):
        return iter(self.connection.headers)

    def as_dict(self, filter_keys: Callable[[str], bool] = constant(True)) -> dict[str, str]:
        return {key: value for key, value in self.connection.headers.items() if filter_keys(key)}


class ResponseHeaderWriter:
    """Write response or WebSocket-accept headers without coupling services to FastAPI."""

    def __init__(self, response: Response | None = None):
        self.response = response
        self._headers: dict[str, tuple[str, str]] = {}

    def write(self, key: str, value: str) -> None:
        if self.response is not None:
            self.response.headers[key] = value
            return
        self._headers[key.lower()] = (key, value)

    def apply(self, message: MutableMapping[str, Any]) -> None:
        if not self._headers:
            return
        headers = MutableHeaders(scope=message)
        for key, value in self._headers.values():
            headers[key] = value


def configure_fastapi(builder: ComponentBuilder) -> None:
    """Add the compiled boundary components supplied by :func:`install_fastapi`."""

    builder.declare_scope_slot(HTTPConnection)
    builder.declare_scope_slot(Request)
    builder.declare_scope_slot(WebSocket)
    builder.declare_scope_slot(ResponseHeaderWriter)
    builder.register(RequestHeaderReader, lifespan=Lifespan.scoped)


def add_request_to_scope(request: Request, scope: Scope = Depends(get_scope, scope="request")) -> None:
    """Compatibility dependency; ``install_fastapi`` provides requests automatically."""

    if not scope.has_provision(Request):
        scope.provide(Request, request)


def add_response_to_scope(response: Response, scope: Scope = Depends(get_scope, scope="request")) -> None:
    if not scope.has_provision(Response):
        scope.provide(Response, response)


def add_request_header_reader_to_scope(
    request: Request,
    scope: Scope = Depends(get_scope, scope="request"),
) -> None:
    if not scope.has_provision(RequestHeaderReader):
        scope.provide(RequestHeaderReader, RequestHeaderReader(request))


def add_response_header_writer_to_scope(
    response: Response,
    scope: Scope = Depends(get_scope, scope="request"),
) -> None:
    if not scope.has_provision(ResponseHeaderWriter):
        scope.provide(ResponseHeaderWriter, ResponseHeaderWriter(response))


def register_fastapi_scope_slots(builder: ComponentBuilder) -> None:
    """Declare slots used by the compatibility FastAPI dependencies."""

    builder.declare_scope_slot(Request)
    builder.declare_scope_slot(Response)
    builder.declare_scope_slot(RequestHeaderReader)
    builder.declare_scope_slot(ResponseHeaderWriter)


__all__ = [
    "RequestHeaderReader",
    "ResponseHeaderWriter",
    "add_request_header_reader_to_scope",
    "add_request_to_scope",
    "add_response_header_writer_to_scope",
    "add_response_to_scope",
    "configure_fastapi",
    "register_fastapi_scope_slots",
]
