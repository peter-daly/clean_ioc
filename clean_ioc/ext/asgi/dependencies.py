from __future__ import annotations

from collections.abc import Callable, MutableMapping
from typing import Any

from clean_ioc import ComponentBuilder
from clean_ioc.bundles import OnlyRunOncePerClassBundle
from clean_ioc.functional_utils import constant

from .core import ASGIConnection


class RequestHeaderReader:
    """Read HTTP or WebSocket headers without depending on a web framework."""

    def __init__(self, connection: ASGIConnection):
        self.connection = connection

    def read(self, key: str, default_value: str = "") -> str:
        expected = key.lower().encode("latin-1")
        for header_key, value in self.connection.scope.get("headers", ()):
            if header_key.lower() == expected:
                return value.decode("latin-1")
        return default_value

    def header_exists(self, key: str) -> bool:
        expected = key.lower().encode("latin-1")
        return any(header_key.lower() == expected for header_key, _ in self.connection.scope.get("headers", ()))

    def __iter__(self):
        return (header_key.decode("latin-1") for header_key, _ in self.connection.scope.get("headers", ()))

    def as_dict(self, filter_keys: Callable[[str], bool] = constant(True)) -> dict[str, str]:
        headers: dict[str, str] = {}
        for header_key, header_value in self.connection.scope.get("headers", ()):
            key = header_key.decode("latin-1")
            if filter_keys(key):
                headers[key] = header_value.decode("latin-1")
        return headers


class ResponseHeaderWriter:
    """Write headers to an HTTP response or WebSocket acceptance message."""

    def __init__(self):
        self._headers: dict[bytes, tuple[bytes, bytes]] = {}

    def write(self, key: str, value: str) -> None:
        encoded_key = key.lower().encode("latin-1")
        self._headers[encoded_key] = (encoded_key, value.encode("latin-1"))

    def apply(self, message: MutableMapping[str, Any]) -> None:
        if not self._headers:
            return
        replaced_keys = self._headers.keys()
        headers = [(key, value) for key, value in message.get("headers", ()) if key.lower() not in replaced_keys]
        headers.extend(self._headers.values())
        message["headers"] = headers


class ASGIBundle(OnlyRunOncePerClassBundle):
    """Declare the boundary components supplied by ``CleanIocMiddleware``."""

    def apply(self, builder: ComponentBuilder) -> None:
        builder.declare_scope_slot(ASGIConnection)
        builder.declare_scope_slot(ResponseHeaderWriter)
        builder.register(RequestHeaderReader, lifespan="scoped")


__all__ = [
    "ASGIBundle",
    "RequestHeaderReader",
    "ResponseHeaderWriter",
]
