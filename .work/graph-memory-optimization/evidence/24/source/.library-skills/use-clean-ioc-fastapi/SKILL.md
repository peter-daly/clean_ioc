---
name: use-clean-ioc-fastapi
description: Use Clean IoC 2 with FastAPI to build an application runtime, install lifespan and request scope ownership, declare request slots, resolve endpoint services, analyse composition separately, and test cleanup. Use when code combines fastapi with clean_ioc.ext.fastapi.
---

# Use Clean IoC with FastAPI

Build one immutable application runtime and install it on the FastAPI application. The integration owns application cleanup and creates one ordinary scope per HTTP request or WebSocket connection.

```python
from fastapi import FastAPI
from clean_ioc import ContainerBuilder
from clean_ioc.ext.fastapi import FastAPIBundle, Resolve, install_fastapi


def application_builder():
    builder = ContainerBuilder()
    builder.apply_bundle(FastAPIBundle())
    builder.register(Repository, lifespan="scoped")
    builder.register(Service)
    return builder


app = FastAPI()
install_fastapi(app, application_builder().build())


@app.get("/")
async def endpoint(service: Service = Resolve(Service)):
    return await service.run()
```

`Resolve(...)` is already a FastAPI dependency marker; do not wrap it in `Depends(...)`. It resolves asynchronously so the selected path can include async activation and cleanup. FastAPI startup checks route selections against the emitted runtime. That integration check does not replace full compiler analysis.

## Separate production and validation

`build()` emits execution instructions without custom validation rules or safety-policy checks. In CI or development, call `application_builder().analyse()` on a fresh builder with the intended composition inputs. Review its completed report, including errors, warnings and coverage. No compiler validation runs implicitly during application build.

Use `result.create_runtime()` when a test needs the analysed plan and resolution without compiling again. Keep the analysis result alive around the test application and close it afterward; it owns its created test runtimes. Every admitted build or analysis attempt consumes the builder, even on failure.

## Map ownership correctly

- `singleton`: application lifespan resources such as settings, pools and HTTP clients;
- `scoped`: request or connection state, such as sessions and units of work;
- `per_resolution`: one endpoint-root resolution;
- `transient`: each dependency edge.

Analysis reports captive dependencies, such as a singleton retaining request state. Runtime scope and cleanup guards remain active. Use async lifespan/context management when any resource has async cleanup.

## Declare late values before compilation

Apply `FastAPIBundle()` before build or analysis when components use `Request`, `WebSocket`, `RequestHeaderReader` or `ResponseHeaderWriter`. It declares the framework slots and supporting components. The integration provides connection values automatically; removed V1 `add_*_to_scope` dependencies and `add_container_to_app` are not needed.

For application-specific values, declare a scope slot, then provide it before the first resolution. A FastAPI dependency can obtain the middleware-created scope with `clean_ioc.ext.asgi.get_scope(request.scope)`. Ensure dependency ordering provides the value before `Resolve(...)` runs. Do not register new components on a request scope.

## Component selection

Pass a component filter directly to `Resolve`:

```python
import clean_ioc.component_filters as cf

gateway: Gateway = Resolve(Gateway, filter=cf.with_name("stripe"))
```

The filter selects among compiled roots and does not inspect runtime instances.

## Test through lifespan

Use `TestClient` as a context manager. Verify scoped sharing within one request, separation between requests, singleton reuse, late-value visibility, and request/application cleanup.

When test composition differs, retain declarations separately with `builder.retain_composition()` before build, or use `analysis.composition`. Create `ScopeBuilder(parent, composition=handle)`, register overrides, then build its runtime and install that scope on a separate test application. Keep the matching parent alive. Ordinary per-request scopes need no composition handle and never compile. The external handle retains declaration memory and has no close lifecycle.

Never construct `Container()` directly, rebuild a container per endpoint, or compile an overlay per ordinary request.
