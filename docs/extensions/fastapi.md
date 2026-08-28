# FastAPI integration

Clean IoC compiles the application container at startup and creates a lightweight child scope per request. Application services remain ordinary Python classes with no FastAPI dependency.

Install the optional dependency:

```bash
pip install "clean_ioc[fastapi]"
```

## Minimal application

```python
from contextlib import asynccontextmanager

from fastapi import FastAPI

from clean_ioc import ContainerBuilder, Lifespan
from clean_ioc.ext.fastapi import Resolve, add_container_to_app


class Repository:
    pass


class Service:
    def __init__(self, repository: Repository):
        self.repository = repository


builder = ContainerBuilder()
builder.register(Repository, lifespan=Lifespan.scoped)
builder.register(Service)
container = builder.build()


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with add_container_to_app(app, container):
        yield


app = FastAPI(lifespan=lifespan)


@app.get("/")
async def endpoint(service: Service = Resolve(Service)):
    return {"repository": type(service.repository).__name__}
```

`Resolve(Service)` is a normal FastAPI dependency. It retrieves the request scope and calls `resolve_async`, so a plan may mix sync and async activation.

## Request scope lifecycle

The extension stores the immutable root container on `app.state`. For the first Clean IoC dependency in a request, it creates `root_scope.new_scope()`, reuses that scope for the rest of the request, and exits it after the response.

This means:

- `scoped` services are shared within one request and isolated between requests;
- singleton services belong to the application container;
- generators, context managers, and teardown callbacks run at the correct boundary;
- no dependency plan is compiled during an ordinary request.

## Request and response helpers use declared slots

FastAPI creates `Request` and `Response` values after the container is built. Declare those late values before build:

```python
from fastapi import Depends, FastAPI

from clean_ioc import ContainerBuilder
from clean_ioc.ext.fastapi.dependencies import (
    RequestHeaderReader,
    add_request_header_reader_to_scope,
    register_fastapi_scope_slots,
)


class HeaderAwareService:
    def __init__(self, headers: RequestHeaderReader):
        self.headers = headers


builder = ContainerBuilder()
register_fastapi_scope_slots(builder)
builder.register(HeaderAwareService)
container = builder.build()

app = FastAPI(dependencies=[Depends(add_request_header_reader_to_scope)])
```

`register_fastapi_scope_slots` declares slots for:

- `fastapi.Request`;
- `fastapi.Response`;
- `RequestHeaderReader`;
- `ResponseHeaderWriter`.

The matching FastAPI dependency calls `scope.provide(...)`. It does not register a component or mutate the plan.

Available helpers:

```python
from clean_ioc.ext.fastapi.dependencies import (
    add_request_header_reader_to_scope,
    add_request_to_scope,
    add_response_header_writer_to_scope,
    add_response_to_scope,
)
```

Add only the dependencies your application needs, while declaring all slots through the helper before `build()`.

## Filtering endpoint services

`Resolve` accepts a component filter:

```python
import clean_ioc.component_filters as cf


@app.get("/primary")
async def primary(service: Service = Resolve(Service, filter=cf.with_name("primary"))):
    return service
```

Root filters select among already-compiled component occurrences.

## Async resources

```python
from contextlib import asynccontextmanager

import httpx


@asynccontextmanager
async def http_client_factory():
    async with httpx.AsyncClient() as client:
        yield client


builder = ContainerBuilder()
builder.register(httpx.AsyncClient, factory=http_client_factory, lifespan=Lifespan.singleton)
builder.register(ExternalApi, lifespan=Lifespan.scoped)
container = builder.build()
```

Use `async with add_container_to_app(...)` so application-owned async singletons are finalized at shutdown. Request-owned async resources are finalized when their request scope exits.

## Testing overrides

For one test or tenant, compile a child overlay without changing the application root:

```python
test_builder = container.new_scope_builder()
test_builder.register(PaymentGateway, FakePaymentGateway)

async with test_builder.build() as test_scope:
    app.state.root_scope = test_scope
    # run the test client
```

For request-specific values, prefer a declared slot and `provide` because ordinary scope creation is much cheaper than compiling an overlay.

## Complete example

See [`examples/fastapi_clean_architecture`](https://github.com/peter-daly/clean_ioc/tree/main/examples/fastapi_clean_architecture) for a framework-independent use case, scoped repository, singleton adapters, an audit decorator, application startup, and endpoint resolution.
