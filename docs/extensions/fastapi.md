# FastAPI integration

FastAPI's dependency system is well suited to HTTP concerns such as authentication, request parsing, headers, and
authorization. Clean IoC complements it with a compiled container for the application service graph. The integration owns
one child scope for each complete HTTP request or WebSocket connection while application services remain independent of
FastAPI.

## Installation

```bash
pip install "clean_ioc[fastapi]"
```

Clean IoC V2 supports FastAPI 0.121 and newer.

## When to use both

| Concern | Native FastAPI | FastAPI with Clean IoC |
| --- | --- | --- |
| HTTP parameters, security, and authorization | `Depends`, `Security`, `Header`, `Query`, and related APIs | Continue using FastAPI APIs |
| Route-level application service | `Depends(provider_function)` | `Resolve(Service)` |
| Deep application dependencies | Nested provider functions or FastAPI annotations in application constructors | Standard constructor annotations compiled from registrations |
| Request reuse | Dependency callable cache, enabled by default | `once_per_graph` or request-owned `scoped` components |
| Application singleton | Application lifespan state or another application-managed cache | `lifespan="singleton"` |
| Application graph validation | FastAPI validates the route dependency model | Clean IoC validates component selection, cycles, generic plans, decorators, and lifespan ownership |

FastAPI supports [arbitrarily deep sub-dependencies](https://fastapi.tiangolo.com/tutorial/dependencies/sub-dependencies/)
and caches repeated dependency callables within a request. Clean IoC does not replace those capabilities. It provides a
separate composition model for application services that need to remain portable across HTTP handlers, workers, CLIs,
message consumers, and tests.

## `Resolve` at the route boundary

At a route signature, `Resolve` occupies the same dependency-marker position as `Depends`:

```python
# Native FastAPI provider
async def endpoint(service: Service = Depends(provide_service)):
    return await service.run()


# Compiled Clean IoC component
async def endpoint(service: Service = Resolve(Service)):
    return await service.run()
```

After `install_fastapi(app, container)`, replacing a route-level application provider is normally a one-line change.
`Resolve` always calls `resolve_async`, so the selected plan may contain both synchronous and asynchronous activation.
Keep using native FastAPI dependencies for transport-specific values and security policies.

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

`install_fastapi` owns the container for the application lifespan and an ordinary child scope for the full ASGI
operation.

## Deep application dependency chains

Deep dependency chains are valid in native FastAPI. Keeping the application classes independent of FastAPI, however,
requires a provider function for each layer:

```python
from typing import Annotated

from fastapi import Depends


async def provide_database_session() -> DatabaseSession:
    return DatabaseSession()


async def provide_order_repository(
    session: Annotated[DatabaseSession, Depends(provide_database_session)],
) -> OrderRepository:
    return OrderRepository(session)


async def provide_unit_of_work(
    repository: Annotated[OrderRepository, Depends(provide_order_repository)],
) -> UnitOfWork:
    return UnitOfWork(repository)


async def provide_place_order(
    unit_of_work: Annotated[UnitOfWork, Depends(provide_unit_of_work)],
) -> PlaceOrder:
    return PlaceOrder(unit_of_work)


async def provide_order_endpoint_service(
    place_order: Annotated[PlaceOrder, Depends(provide_place_order)],
) -> OrderEndpointService:
    return OrderEndpointService(place_order)
```

FastAPI resolves this chain correctly and caches each provider result for the request. The provider layer becomes larger
as the application graph grows. Putting `Depends` directly in application constructors removes some providers, but makes
those classes depend on FastAPI.

With Clean IoC, the same graph is defined by ordinary constructors and the composition root:

```python
builder = ContainerBuilder()
builder.register(DatabaseSession, lifespan="scoped")
builder.register(OrderRepository)
builder.register(UnitOfWork)
builder.register(PlaceOrder)
builder.register(OrderEndpointService)

container = builder.build()
install_fastapi(app, container)


@app.post("/orders")
async def create_order(service: OrderEndpointService = Resolve(OrderEndpointService)):
    return await service.run()
```

`OrderRepository`, `UnitOfWork`, `PlaceOrder`, and `OrderEndpointService` use the default `once_per_graph` lifespan. The
database session is shared by every consumer in the request scope. The same compiled entry point can be resolved from a
worker or CLI without recreating the FastAPI provider chain.

## Lifecycle behavior

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

`install_fastapi` is the only lifecycle integration. It keeps request, streaming-response, WebSocket, background-work, and cleanup ownership inside one ASGI boundary.

## Lifespans and application singletons

FastAPI's dependency cache reuses a provider result within one request. Application-wide resources with startup and
shutdown work are normally managed through the
[FastAPI application lifespan](https://fastapi.tiangolo.com/advanced/events/):

```python
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request


@asynccontextmanager
async def lifespan(app: FastAPI):
    client = HttpClient()
    await client.open()
    app.state.http_client = client
    try:
        yield
    finally:
        await client.close()


app = FastAPI(lifespan=lifespan)


def provide_http_client(request: Request) -> HttpClient:
    return request.app.state.http_client
```

Clean IoC keeps the ownership policy with the component registration:

```python
from contextlib import asynccontextmanager


@asynccontextmanager
async def http_client_factory():
    client = HttpClient()
    await client.open()
    try:
        yield client
    finally:
        await client.close()


builder.register(
    HttpClient,
    factory=http_client_factory,
    lifespan="singleton",
)
```

| Clean IoC lifespan | Ownership in a FastAPI application |
| --- | --- |
| `transient` | New activation for each dependency edge |
| `once_per_graph` | Shared within one top-level application-service resolution |
| `scoped` | Shared for the complete HTTP request or WebSocket connection |
| `singleton` | Shared by the application container and finalized at shutdown |

Singleton activation is lazy by default. Resolve a singleton from a custom application lifespan when eager initialization
is required. The compiler rejects a singleton that directly or transitively captures request-scoped state.

## Build and startup validation

The integration has two validation points:

1. `ContainerBuilder.build()` compiles every visible application component plan and rejects missing components, cycles,
   invalid generic specialization, decorator or pre-configuration errors, and captive lifespan paths.
2. During ASGI startup, `install_fastapi` verifies that every route-level `Resolve` service and filter exists in the
   frozen container.

Every `Resolve` dependency records its requested service type and component filter. Before FastAPI starts accepting traffic, the integration checks those requests against the frozen container.

```python
import clean_ioc.component_filters as cf


@app.get("/primary")
async def primary(service: Service = Resolve(Service, filter=cf.with_name("primary"))):
    return service
```

If the `primary` component does not exist, application startup raises `FastAPIIntegrationError` with the route and missing service. The first request is not used as validation.

FastAPI also performs early validation: it builds its native dependency model while routes are registered and validates
the parameter declarations it owns. The distinction is scope. FastAPI validates the HTTP dependency tree; Clean IoC
validates the separately registered application component graph and its ownership rules.

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

The installed application owns and closes the overlay. For request-specific values, use the slots installed by
`configure_fastapi`. Ordinary request scopes reuse the existing plan; an overlay compiles a new plan.

## Complete example

See [`examples/fastapi_clean_architecture`](https://github.com/peter-daly/clean_ioc/tree/main/examples/fastapi_clean_architecture) for a framework-independent use case, scoped repository, singleton adapters, an audit decorator, startup validation, and endpoint resolution.
