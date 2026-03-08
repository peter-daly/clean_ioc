# FastAPI Extension

Clean IoC provides helpers for per-request scope integration with FastAPI.

```python
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Request

from clean_ioc import Container, Lifespan, Scope
from clean_ioc.ext.fastapi import Resolve, add_container_to_app, get_scope
```

## How it works

- A root scope is attached to the app during lifespan.
- Each request receives a child scope (`get_scope`).
- `Resolve(SomeType)` resolves from the request scope.

## Minimal setup

```python
class MyDependency:
    def do_action(self) -> str:
        return "done"


@asynccontextmanager
async def app_lifespan(app: FastAPI):
    container = Container()
    container.register(MyDependency)

    async with add_container_to_app(app, container):
        yield


app = FastAPI(lifespan=app_lifespan)


@app.get("/")
async def read_root(dep: MyDependency = Resolve(MyDependency)):
    return {"result": dep.do_action()}
```

## Inject FastAPI request objects into scope

```python
class RequestAwareDependency:
    def __init__(self, request: Request):
        self.request = request

    def user_agent(self) -> str:
        return self.request.headers.get("user-agent", "")


def add_request_to_scope(request: Request, scope: Scope = Depends(get_scope)):
    scope.register(Request, instance=request)


@asynccontextmanager
async def app_lifespan(app: FastAPI):
    container = Container()
    container.register(RequestAwareDependency, lifespan=Lifespan.scoped)

    async with add_container_to_app(app, container):
        yield


app = FastAPI(lifespan=app_lifespan, dependencies=[Depends(add_request_to_scope)])


@app.get("/ua")
async def user_agent(dep: RequestAwareDependency = Resolve(RequestAwareDependency)):
    return {"user_agent": dep.user_agent()}
```
