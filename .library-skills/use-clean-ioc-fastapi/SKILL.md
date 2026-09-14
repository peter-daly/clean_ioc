---
name: use-clean-ioc-fastapi
description: Use Clean IoC 2 with FastAPI to compile an application container, attach it to lifespan, resolve endpoint services from per-request scopes, declare and provide request/response slots, select components, own async resources, and test cleanup. Use when code combines fastapi with clean_ioc.ext.fastapi.
---

# Use Clean IoC with FastAPI

Compile one immutable application container, attach it for the full FastAPI lifespan, and let the integration create one lightweight child scope per request.

```python
from contextlib import asynccontextmanager

from fastapi import FastAPI

from clean_ioc import ContainerBuilder
from clean_ioc.ext.fastapi import Resolve, add_container_to_app


builder = ContainerBuilder()
builder.register(Repository, lifespan="scoped")
builder.register(Service)
container = builder.build()


@asynccontextmanager
async def app_lifespan(app: FastAPI):
    async with add_container_to_app(app, container):
        yield


app = FastAPI(lifespan=app_lifespan)


@app.get("/")
async def endpoint(service: Service = Resolve(Service)):
    return await service.run()
```

Do not wrap `Resolve(...)` in `Depends(...)`; it already returns a dependency marker. It calls `scope.resolve_async(...)`, so compiled paths may contain sync and async activation.

## Map ownership correctly

- `singleton`: application lifespan resources such as settings, pools, and `httpx.AsyncClient`;
- `scoped`: one per request, such as sessions and units of work;
- `once_per_graph`: one endpoint-root resolve only;
- `transient`: every dependency edge.

Keep `add_container_to_app(...)` active across the lifespan yield and use async context management when any singleton cleanup is async.

## Declare late FastAPI values before build

Request and response objects do not exist during application compilation. Declare their slots before `build()`:

```python
from clean_ioc.ext.fastapi.dependencies import register_fastapi_scope_slots

builder = ContainerBuilder()
register_fastapi_scope_slots(builder)
builder.register(RequestAwareService)
container = builder.build()
```

Then add only the FastAPI dependencies that provide values your services need:

```python
from fastapi import Depends
from clean_ioc.ext.fastapi.dependencies import add_request_to_scope

app = FastAPI(
    lifespan=app_lifespan,
    dependencies=[Depends(add_request_to_scope)],
)
```

Available providers cover `Request`, `Response`, `RequestHeaderReader`, and `ResponseHeaderWriter`. They call `scope.provide(...)`; they do not mutate or recompile the container.

For an application-specific late value, declare it on the builder and provide it in a FastAPI dependency before `Resolve(...)` runs:

```python
builder.declare_scope_slot(TenantId)


def provide_tenant(request: Request, scope: Scope = Depends(get_scope)):
    scope.provide(TenantId, TenantId(request.headers["x-tenant-id"]))
```

Provisioning locks at the scope's first resolution, so dependency ordering must ensure providers run first.

## Component selection

Pass a component filter directly to `Resolve`:

```python
import clean_ioc.component_filters as cf

gateway: Gateway = Resolve(Gateway, filter=cf.with_name("stripe"))
```

The filter selects among frozen root occurrences; it does not inspect runtime instances.

## Test through lifespan

Use `TestClient` as a context manager. Verify that two dependencies in one request share scoped state, different requests do not, singleton infrastructure is reused, provided request values are visible, and async cleanup happens at request/application exit.

## Avoid common mistakes

- Do not instantiate `Container()`; compose with `ContainerBuilder()` and call `build()`.
- Do not register on a request scope; declare a slot and call `provide()`.
- Do not compile a `ScopeBuilder` per ordinary request.
- Do not resolve request-scoped services from the root container.
- Do not model mutable request state as a singleton.
- Do not create a container inside each endpoint.
- Do not set `app.state.root_scope` manually outside a deliberate test override.
