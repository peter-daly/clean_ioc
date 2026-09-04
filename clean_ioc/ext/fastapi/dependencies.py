from __future__ import annotations

from collections.abc import Callable, MutableMapping
from typing import Any

from starlette.datastructures import MutableHeaders
from starlette.requests import HTTPConnection

from clean_ioc import ComponentBuilder
from clean_ioc.bundles import OnlyRunOncePerClassBundle
from clean_ioc.functional_utils import constant
from fastapi import Request, WebSocket


class RequestHeaderReader:
    """Framework-light access to HTTP or WebSocket connection headers."""

    def __init__(self, connection: HTTPConnection):
        self.connection = connection

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

    def __init__(self):
        self._headers: dict[str, tuple[str, str]] = {}

    def write(self, key: str, value: str) -> None:
        self._headers[key.lower()] = (key, value)

    def apply(self, message: MutableMapping[str, Any]) -> None:
        if not self._headers:
            return
        headers = MutableHeaders(scope=message)
        for key, value in self._headers.values():
            headers[key] = value


class FastAPIBundle(OnlyRunOncePerClassBundle):
    """Declare the compiled boundary components supplied by ``install_fastapi``."""

    def apply(self, builder: ComponentBuilder) -> None:
        builder.declare_scope_slot(HTTPConnection)
        builder.declare_scope_slot(Request)
        builder.declare_scope_slot(WebSocket)
        builder.declare_scope_slot(ResponseHeaderWriter)
        builder.register(RequestHeaderReader, lifespan="scoped")


__all__ = [
    "FastAPIBundle",
    "RequestHeaderReader",
    "ResponseHeaderWriter",
]
