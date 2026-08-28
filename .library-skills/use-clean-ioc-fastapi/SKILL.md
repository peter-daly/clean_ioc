---
name: use-clean-ioc-fastapi
description: Use Clean IoC with FastAPI to configure application lifespan integration, per-request scopes, Resolve dependencies, registration filters, request and response helpers, async resource cleanup, and integration tests. Use when building, modifying, debugging, reviewing, or testing applications that combine fastapi with clean_ioc.ext.fastapi.
---

# Use Clean IoC with FastAPI

Attach one root Clean IoC container to the FastAPI application lifespan and let each request receive one child scope. Resolve endpoint services from that request scope with `Resolve(...)`.

## Install the integration

Install the FastAPI extra when adding Clean IoC to an application:

```bash
pip install "clean_ioc[fastapi]"
```

Treat the installed package as the source of truth. Inspect `clean_ioc.ext.fastapi` before using helpers not covered here.

## Configure the application lifespan

Create and register the root container inside an async lifespan. Keep `add_container_to_app(...)` active across the lifespan yield so singleton resources are owned and cleaned up correctly:

```python
from contextlib import asynccontextmanager

from fastapi import FastAPI

from clean_ioc import Container, Lifespan
from clean_ioc.ext.fastapi import Resolve, add_container_to_app


class Settings:
    def __init__(self, app_name: str):
        self.app_name = app_name


class UserRepository:
    pass


class UserService:
    def __init__(self, repository: UserRepository, settings: Settings):
        self.repository = repository
        self.settings = settings


@asynccontextmanager
async def app_lifespan(app: FastAPI):
    container = Container()
    container.register(
        Settings,
        factory=lambda: Settings("users-api"),
        lifespan=Lifespan.singleton,
    )
    container.register(UserRepository, lifespan=Lifespan.scoped)
    container.register(UserService)
    container.validate(UserService)

    async with add_container_to_app(app, container):
        yield


app = FastAPI(lifespan=app_lifespan)


@app.get("/users/{user_id}")
async def get_user(
    user_id: str,
    service: UserService = Resolve(UserService),
):
    return {"id": user_id, "app": service.settings.app_name}
```

Do not wrap `Resolve(...)` in `Depends(...)`; it already returns a FastAPI dependency marker. Internally it awaits `scope.resolve_async(...)`, so it supports graphs containing both sync and async factories.

Call `container.validate(...)` for the route services, handlers, and other application
entry points before yielding from the lifespan. The check does not construct resources,
and it turns missing registrations, dependency cycles, and singleton-to-request-scope
captures into startup failures with complete paths. Leave `allow_async=True` because
`Resolve(...)` uses `scope.resolve_async(...)`.

## Let FastAPI drive request resolution

Treat `Resolve(Service)` as the framework adapter at the endpoint composition boundary:

- FastAPI invokes the generated dependency resolver;
- `get_scope` creates or reuses one child scope for the request;
- Clean IoC resolves the requested root service with `scope.resolve_async(...)`;
- the endpoint receives the constructed service without accessing the container;
- request completion exits the child scope and runs scoped cleanup.

Keep route functions focused on transport concerns and application-service calls. Do not inject `Container` into endpoints or manually call `container.resolve(...)` when `Resolve(...)` can express the dependency. Use `get_scope` directly only for FastAPI dependencies that must add request-local values before service resolution.

## Map lifespans to web ownership

Choose lifespans according to the web resource boundary:

| Clean IoC lifespan | FastAPI behavior | Typical use |
| --- | --- | --- |
| `singleton` | One instance for the application lifespan | Settings, database/Redis pools, `httpx.AsyncClient` |
| `scoped` | One instance per request scope | Sessions, request state, units of work |
| `once_per_graph` | Reused only inside one `Resolve(...)` graph | Ordinary service graph dependencies |
| `transient` | New instance at every dependency edge | Disposable operations or graph-sensitive values |

Do not assume `once_per_graph` is request-scoped. Separate `Resolve(...)` dependencies can create separate graphs; use `scoped` when all resolutions in one request must share an instance.

Use async generator or async context-manager factories for resources that must close at application or request exit:

```python
from contextlib import asynccontextmanager

import httpx


@asynccontextmanager
async def http_client_factory():
    async with httpx.AsyncClient(timeout=5.0) as client:
        yield client


container.register(
    httpx.AsyncClient,
    factory=http_client_factory,
    lifespan=Lifespan.singleton,
)
```

Use `scoped_teardown=` as an alternative when cleanup should remain separate from construction.

## Resolve named or tagged registrations

Pass the registration filter directly to `Resolve(...)`:

```python
from clean_ioc.ext.fastapi import Resolve
from clean_ioc.registration_filters import with_name


@app.get("/payments")
async def payments(
    gateway: Gateway = Resolve(Gateway, filter=with_name("stripe")),
):
    return await gateway.list_payments()
```

The normal Clean IoC default filter selects unnamed registrations. Register and select names or tags deliberately.

## Inject request and response objects

Import scope helpers from their actual modules:

```python
from fastapi import Depends, FastAPI

from clean_ioc.ext.fastapi import get_scope
from clean_ioc.ext.fastapi.dependencies import (
    RequestHeaderReader,
    ResponseHeaderWriter,
    add_request_header_reader_to_scope,
    add_request_to_scope,
    add_response_header_writer_to_scope,
    add_response_to_scope,
)
```

Add only the helpers required by the application as global FastAPI dependencies. They register request-specific instances into the same child scope used by `Resolve(...)`:

```python
app = FastAPI(
    lifespan=app_lifespan,
    dependencies=[
        Depends(add_request_to_scope),
        Depends(add_response_to_scope),
    ],
)
```

After `add_request_to_scope`, inject `fastapi.Request` into Clean IoC services normally. After `add_response_to_scope`, inject `fastapi.Response`. Use the header helpers when services need only header access rather than the full framework objects:

```python
app = FastAPI(
    lifespan=app_lifespan,
    dependencies=[
        Depends(add_request_header_reader_to_scope),
        Depends(add_response_header_writer_to_scope),
    ],
)


class EndpointService:
    def __init__(
        self,
        reader: RequestHeaderReader,
        writer: ResponseHeaderWriter,
    ):
        self.reader = reader
        self.writer = writer
```

Use `get_scope` directly only when a FastAPI dependency must register additional request-local values:

```python
from fastapi import Depends, Request

from clean_ioc import Scope
from clean_ioc.ext.fastapi import get_scope


def add_tenant_to_scope(
    request: Request,
    scope: Scope = Depends(get_scope),
):
    scope.register(TenantId, instance=TenantId(request.headers["x-tenant-id"]))
```

Register framework objects on the request scope, never as root singletons.

## Test through the lifespan

Enter `TestClient` as a context manager so FastAPI runs startup, shutdown, and Clean IoC teardown:

```python
from fastapi.testclient import TestClient


with TestClient(app) as client:
    first = client.get("/probe")
    second = client.get("/probe")

assert first.status_code == 200
assert second.status_code == 200
assert first.json()["request_id"] != second.json()["request_id"]
```

Test these boundaries explicitly:

- two `Resolve(...)` operations in one request share a `scoped` dependency;
- two requests receive different scoped instances;
- singleton infrastructure is reused across requests;
- async generator cleanup runs at request or application exit;
- named/tagged endpoint dependencies use the intended registration;
- request/response helpers register into the current request scope.

## Avoid common mistakes

- Do not set `app.state.root_scope` manually; use `add_container_to_app(...)`.
- Do not create a fresh container or scope inside every endpoint.
- Do not resolve request services from the root container.
- Do not use `Depends(Resolve(Service))`; write `service: Service = Resolve(Service)`.
- Do not model request-specific sessions or mutable state as singletons.
- Do not recreate connection pools or reusable HTTP clients per request.
- Do not instantiate `TestClient` without a context manager when testing lifespan behavior.
- Do not register `Request`, `Response`, or header helpers unless the corresponding FastAPI dependency populates the request scope first.
