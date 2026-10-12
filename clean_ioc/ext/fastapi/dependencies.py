from __future__ import annotations

from starlette.requests import HTTPConnection

from clean_ioc import ComponentBuilder
from clean_ioc.bundles import OnlyRunOncePerClassBundle
from clean_ioc.ext.asgi import ASGIBundle, RequestHeaderReader, ResponseHeaderWriter
from fastapi import Request, WebSocket


class FastAPIBundle(OnlyRunOncePerClassBundle):
    """Declare the compiled boundary components supplied by ``install_fastapi``."""

    def apply(self, builder: ComponentBuilder) -> None:
        builder.apply_bundle(ASGIBundle())
        builder.declare_scope_slot(HTTPConnection)
        builder.declare_scope_slot(Request)
        builder.declare_scope_slot(WebSocket)


__all__ = [
    "FastAPIBundle",
    "RequestHeaderReader",
    "ResponseHeaderWriter",
]
