# FastAPI integration

Clean IoC compiles the application container before startup and owns one lightweight child scope for each complete HTTP request or WebSocket connection. Application services remain ordinary Python classes with no FastAPI dependency.

Install the optional dependency:

```bash
pip install "clean_ioc[fastapi]"
```

Clean IoC V2 supports FastAPI 0.121 and newer.

## Minimal application

```python
from fastapi import FastAPI

from clean_ioc import ContainerBuilder
from clean_ioc.ext.fastapi import Resolve, install_fastapi


class Repository:
    pass


class Service:
    def __init__(self, repository: Repository):
        self.repository = repository


builder = ContainerBuilder()
builder.register(Repository, lifespan="scoped")
builder.register(Service)
container = builder.build()

app = FastAPI()
install_fastapi(app, container)


@app.get("/")
async def endpoint(service: Service = Resolve(Service)):
    return {"repository": type(service.repository).__name__}
```

`Resolve(Service)` always calls `resolve_async`, so the compiled plan may mix sync and async activation. `install_fastapi` owns the container for the application lifespan and an ordinary child scope for the full ASGI operation.

## Lifecycle guarantees

The integration uses pure ASGI middleware rather than a `yield` dependency to own scopes. This means:

- `scoped` services are shared within one request or WebSocket connection and isolated between operations;
- singleton services belong to the application container;
- streaming responses and background work finish before request-owned resources are finalized;
- WebSocket resources live until the connection handler exits;
- exceptions still close the request scope;
- no dependency plan is compiled during a request.

Custom FastAPI lifespans continue to work. The middleware enters the container around FastAPI's own lifespan:

```python
app = FastAPI(lifespan=application_lifespan)
install_fastapi(app, container)
```

`add_container_to_app` and the individual `add_*_to_scope` dependencies remain available for compatibility, but new V2 applications should use `install_fastapi`.

## Route validation at startup

Every `Resolve` dependency records its requested service type and component filter. Before FastAPI starts accepting traffic, the integration checks those requests against the frozen container.

```python
import clean_ioc.component_filters as cf


@app.get("/primary")
async def primary(service: Service = Resolve(Service, filter=cf.with_name("primary"))):
    return service
```

If the `primary` component does not exist, application startup raises `FastAPIIntegrationError` with the route and missing service. The first request is not used as validation.

## Request and response boundary values

Call `configure_fastapi` before `build()` when application components consume HTTP connection information or the framework-light header adapters:

```python
from clean_ioc.ext.fastapi import (
    RequestHeaderReader,
    ResponseHeaderWriter,
    configure_fastapi,
)


class HeaderAwareService:
    def __init__(self, headers: RequestHeaderReader, response_headers: ResponseHeaderWriter):
        self.headers = headers
        self.response_headers = response_headers

    def run(self) -> str:
        self.response_headers.write("X-Clean-IoC", "active")
        return self.headers.read("X-Request-ID")


builder = ContainerBuilder()
configure_fastapi(builder)
builder.register(HeaderAwareService)
container = builder.build()

app = FastAPI()
install_fastapi(app, container)
```

No global `dependencies=[Depends(...)]` list is required. The configuration bundle:

- declares slots for `HTTPConnection`, `Request`, `WebSocket`, and `ResponseHeaderWriter`;
- registers `RequestHeaderReader` as an ordinary scoped component;
- lets the middleware provide the current boundary values before resolution.

Application code can inject `fastapi.Request` or `fastapi.WebSocket` directly when framework coupling is intentional. Prefer `RequestHeaderReader` and `ResponseHeaderWriter` in portable application services.

## WebSockets

`Resolve` uses Starlette's shared `HTTPConnection` boundary, so the same API works for HTTP and WebSocket routes:

```python
from fastapi import WebSocket


@app.websocket("/events")
async def events(websocket: WebSocket, handler: EventHandler = Resolve(EventHandler)):
    await websocket.accept()
    await handler.run(websocket)
```

One Clean IoC scope is retained for the entire connection. `ResponseHeaderWriter` values written before `websocket.accept()` are added to the handshake headers.

## Async resources

```python
from contextlib import asynccontextmanager

import httpx


@asynccontextmanager
async def http_client_factory():
    async with httpx.AsyncClient() as client:
        yield client


builder = ContainerBuilder()
builder.register(httpx.AsyncClient, factory=http_client_factory, lifespan="singleton")
builder.register(ExternalApi, lifespan="scoped")
container = builder.build()
```

Application-owned async singletons are finalized at FastAPI shutdown. Request-owned async resources are finalized after the HTTP response, stream, background work, or WebSocket handler completes.

## Testing overrides

Keep application construction injectable so a compiled overlay can become the test root without mutating the production container:

```python
from fastapi.testclient import TestClient

from clean_ioc import Scope


def create_app(root_scope: Scope) -> FastAPI:
    app = FastAPI()
    install_fastapi(app, root_scope)
    return app


test_builder = container.new_scope_builder()
test_builder.register(PaymentGateway, FakePaymentGateway)
test_scope = test_builder.build()

with TestClient(create_app(test_scope)) as client:
    response = client.post("/checkout")
```

The installed application owns and closes the overlay. For request-specific values, prefer the slots installed by `configure_fastapi`; ordinary request scopes remain much cheaper than compiling an overlay.

## Complete example

See [`examples/fastapi_clean_architecture`](https://github.com/peter-daly/clean_ioc/tree/main/examples/fastapi_clean_architecture) for a framework-independent use case, scoped repository, singleton adapters, an audit decorator, startup validation, and endpoint resolution.
