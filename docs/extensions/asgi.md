# ASGI integration

The `clean_ioc.ext.asgi` package connects a compiled Clean IoC runtime to any ASGI 3 application without depending on
FastAPI, Starlette, or an ASGI server package.

It has two responsibilities:

- enter and close the root runtime around the application's ASGI lifespan;
- create and close one ordinary child scope around each complete HTTP request or WebSocket connection.

Routing, request parsing, response serialization, and health-check policy remain application concerns.

## Wrap an application

Use `get_scope()` at the transport boundary to resolve an application entry point:

```python
from clean_ioc import ContainerBuilder
from clean_ioc.ext.asgi import CleanIocMiddleware, get_scope


class Handler:
    async def __call__(self) -> bytes:
        return b"hello"


builder = ContainerBuilder()
builder.register(Handler)
container = builder.build()


async def application(asgi_scope, receive, send):
    handler = await get_scope(asgi_scope).resolve_async(Handler)
    body = await handler()
    await send(
        {
            "type": "http.response.start",
            "status": 200,
            "headers": [(b"content-length", str(len(body)).encode("ascii"))],
        }
    )
    await send({"type": "http.response.body", "body": body})


app = CleanIocMiddleware(application, root_scope=container)
```

Run the wrapped callable with a lifespan-capable ASGI server. Application singletons remain alive until lifespan
shutdown. Scoped resources remain alive until the complete response stream or WebSocket application returns.

ASGI scope types other than `lifespan`, `http`, and `websocket` pass through unchanged.

## Boundary values and headers

Apply `ASGIBundle` before `build()` when application services need raw connection data or the framework-independent
header adapters:

```python
from clean_ioc.ext.asgi import (
    ASGIBundle,
    ASGIConnection,
    RequestHeaderReader,
    ResponseHeaderWriter,
)

builder.apply_bundle(ASGIBundle())
```

The bundle declares `ASGIConnection` and `ResponseHeaderWriter` as scope slots and registers `RequestHeaderReader` as a
scoped component. `CleanIocMiddleware` supplies them before resolution starts. Singleton components cannot capture
these operation-local values; invalid captures fail during `build()`.

`ASGIConnection` exposes the raw ASGI `scope`, `receive`, and wrapped `send` callables. Prefer the header adapters when
that is all an application service requires.

## Health-check example

Health routes are deliberately not built into the extension. The
[minimal ASGI health server](../examples/asgi-health-checks.md) implements `/health/liveness`,
`/health/readiness`, and `/health/startup` as ordinary application routes over this boundary.

Framework bundles declare scoped inputs with `declare_slot(..., target="scoped")`.
Their once-per-class guard permits repeated application on one builder. Overlays
inherit existing inputs and adapters; do not reapply the bundle in an overlay
that already inherits it, or manually redeclare those inputs. Duplicate implicit
slot declarations fail compilation. An overlay over a root without the bundle
can install it normally.
