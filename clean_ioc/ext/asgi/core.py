from __future__ import annotations

from collections.abc import Awaitable, Callable, MutableMapping
from dataclasses import dataclass
from typing import Any, TypeAlias

from clean_ioc import Scope

ASGIMessage = MutableMapping[str, Any]
ASGIScope = MutableMapping[str, Any]
Receive = Callable[[], Awaitable[ASGIMessage]]
Send = Callable[[ASGIMessage], Awaitable[None]]

_SCOPE_KEY = "clean_ioc.scope"


ASGIApp: TypeAlias = Callable[[ASGIScope, Receive, Send], Awaitable[None]]


class ASGIIntegrationError(RuntimeError):
    """Raised when an ASGI application is used outside its Clean IoC boundary."""


@dataclass(frozen=True, slots=True)
class ASGIConnection:
    """The raw ASGI values for one HTTP request or WebSocket connection."""

    scope: ASGIScope
    receive: Receive
    send: Send


def get_scope(asgi_scope: ASGIScope) -> Scope:
    """Return the Clean IoC operation scope attached by ``CleanIocMiddleware``."""

    request_scope = asgi_scope.get(_SCOPE_KEY)
    if not isinstance(request_scope, Scope):
        raise ASGIIntegrationError("No Clean IoC operation scope; wrap the application with CleanIocMiddleware")
    return request_scope


class CleanIocMiddleware:
    """Own the root runtime and one child scope per HTTP/WebSocket operation."""

    def __init__(self, app: ASGIApp, *, root_scope: Scope):
        self.app = app
        self.root_scope = root_scope

    async def __call__(self, scope: ASGIScope, receive: Receive, send: Send) -> None:
        scope_type = scope["type"]
        if scope_type == "lifespan":
            async with self.root_scope:
                await self.app(scope, receive, send)
            return

        if scope_type not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return

        # Imported lazily to keep the protocol types and bundle definitions acyclic.
        from .dependencies import ResponseHeaderWriter

        async with self.root_scope.new_scope() as operation_scope:
            scope[_SCOPE_KEY] = operation_scope
            operation_send = send
            if operation_scope.has_scope_slot(ResponseHeaderWriter):
                header_writer = ResponseHeaderWriter()
                operation_scope.provide(ResponseHeaderWriter, header_writer)

                async def send_with_headers(message: ASGIMessage) -> None:
                    if message["type"] in ("http.response.start", "websocket.accept"):
                        header_writer.apply(message)
                    await send(message)

                operation_send = send_with_headers

            if operation_scope.has_scope_slot(ASGIConnection):
                operation_scope.provide(
                    ASGIConnection,
                    ASGIConnection(scope=scope, receive=receive, send=operation_send),
                )

            try:
                await self.app(scope, receive, operation_send)
            finally:
                scope.pop(_SCOPE_KEY, None)


__all__ = [
    "ASGIApp",
    "ASGIConnection",
    "ASGIIntegrationError",
    "ASGIMessage",
    "ASGIScope",
    "CleanIocMiddleware",
    "Receive",
    "Send",
    "get_scope",
]
