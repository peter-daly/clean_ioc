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

## Dependencies with dependencies: FastAPI only vs Clean IoC

### FastAPI without Clean IoC

In plain FastAPI, you usually wire every edge in the dependency chain with `Depends(...)`.

```python
from functools import lru_cache

from fastapi import Depends, FastAPI

app = FastAPI()


class Settings:
    def __init__(self, db_url: str):
        self.db_url = db_url


class DbSession:
    def __init__(self, settings: Settings):
        self.settings = settings


class UserRepository:
    def __init__(self, db: DbSession):
        self.db = db


class UserService:
    def __init__(self, repo: UserRepository):
        self.repo = repo

    def get_user(self, user_id: str) -> dict:
        return {"id": user_id}


@lru_cache
def get_settings() -> Settings:
    # Singleton-like dependency requires extra wiring/caching.
    return Settings(db_url="postgresql://localhost:5432/app")


def get_db(settings: Settings = Depends(get_settings)) -> DbSession:
    return DbSession(settings)


def get_user_repo(db: DbSession = Depends(get_db)) -> UserRepository:
    return UserRepository(db)


def get_user_service(repo: UserRepository = Depends(get_user_repo)) -> UserService:
    return UserService(repo)


@app.get("/users/{user_id}")
def get_user(user_id: str, service: UserService = Depends(get_user_service)):
    return service.get_user(user_id)
```

### FastAPI with Clean IoC

With Clean IoC, you declare classes and register types once. Constructor dependencies are resolved automatically.

```python
from contextlib import asynccontextmanager

from fastapi import FastAPI

from clean_ioc import Container, Lifespan
from clean_ioc.ext.fastapi import Resolve, add_container_to_app


class Settings:
    def __init__(self, db_url: str):
        self.db_url = db_url


class DbSession:
    def __init__(self, settings: Settings):
        self.settings = settings


class UserRepository:
    def __init__(self, db: DbSession):
        self.db = db


class UserService:
    def __init__(self, repo: UserRepository):
        self.repo = repo

    def get_user(self, user_id: str) -> dict:
        return {"id": user_id}


@asynccontextmanager
async def app_lifespan(app: FastAPI):
    container = Container()
    container.register(Settings, factory=lambda: Settings("postgresql://localhost:5432/app"), lifespan=Lifespan.singleton)
    container.register(DbSession, lifespan=Lifespan.scoped)
    container.register(UserRepository)
    container.register(UserService)

    async with add_container_to_app(app, container):
        yield


app = FastAPI(lifespan=app_lifespan)


@app.get("/users/{user_id}")
async def get_user(user_id: str, service: UserService = Resolve(UserService)):
    return service.get_user(user_id)
```

### Lifecycle model differences

- Plain FastAPI dependency functions are request-cached by default, so request scope is the natural model.
- Singleton-like dependencies in plain FastAPI are usually achieved with app state or caching patterns (`@lru_cache`, custom startup wiring).
- Clean IoC makes lifespan explicit at registration time (`transient`, `once_per_graph`, `scoped`, `singleton`), so lifetime is a first-class design decision.

#### Performance note: singleton placement matters

Using `singleton` for expensive, reusable infrastructure dependencies can significantly improve performance.

Examples:

- Database connection pools (SQLAlchemy engine/pool, async DB pool).
- Redis clients/pools.
- HTTP clients (`httpx.AsyncClient`) with connection pooling and TLS session reuse.

If you recreate these per request, you repeatedly pay setup costs.
For HTTP clients, that can include DNS lookup, TCP connect, and TLS handshake overhead.
Keeping a long-lived client instance allows connection reuse and reduces latency under load.

#### Plain FastAPI lifecycle example

```python
from functools import lru_cache
from uuid import uuid4

from fastapi import Depends, FastAPI

app = FastAPI()


class RequestTracker:
    def __init__(self):
        self.request_id = str(uuid4())


class Settings:
    def __init__(self, app_name: str):
        self.app_name = app_name


@lru_cache
def get_settings() -> Settings:
    # App-wide singleton-like dependency (manual pattern).
    return Settings("my-api")


def get_request_tracker() -> RequestTracker:
    # New instance per request (request cache still means one per request).
    return RequestTracker()


@app.get("/lifecycle")
def lifecycle(
    tracker_a: RequestTracker = Depends(get_request_tracker),
    tracker_b: RequestTracker = Depends(get_request_tracker),
    settings_a: Settings = Depends(get_settings),
    settings_b: Settings = Depends(get_settings),
):
    return {
        "request_scoped_same_instance": tracker_a is tracker_b,  # True per request
        "singleton_like_same_instance": settings_a is settings_b,  # True app-wide
    }
```

#### Clean IoC lifecycle example

```python
from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import FastAPI

from clean_ioc import Container, Lifespan
from clean_ioc.ext.fastapi import Resolve, add_container_to_app


class RequestTracker:
    def __init__(self):
        self.request_id = str(uuid4())


class OperationToken:
    def __init__(self):
        self.value = str(uuid4())


class Settings:
    def __init__(self, app_name: str):
        self.app_name = app_name


class LifecycleProbe:
    def __init__(
        self,
        tracker_a: RequestTracker,
        tracker_b: RequestTracker,
        token_a: OperationToken,
        token_b: OperationToken,
        settings_a: Settings,
        settings_b: Settings,
    ):
        self.tracker_a = tracker_a
        self.tracker_b = tracker_b
        self.token_a = token_a
        self.token_b = token_b
        self.settings_a = settings_a
        self.settings_b = settings_b


@asynccontextmanager
async def app_lifespan(app: FastAPI):
    container = Container()
    container.register(Settings, factory=lambda: Settings("my-api"), lifespan=Lifespan.singleton)
    container.register(RequestTracker, lifespan=Lifespan.scoped)
    container.register(OperationToken, lifespan=Lifespan.transient)
    container.register(LifecycleProbe)

    async with add_container_to_app(app, container):
        yield


app = FastAPI(lifespan=app_lifespan)


@app.get("/lifecycle")
async def lifecycle(probe: LifecycleProbe = Resolve(LifecycleProbe)):
    return {
        "scoped_same_instance": probe.tracker_a is probe.tracker_b,  # True within request scope
        "transient_same_instance": probe.token_a is probe.token_b,  # False (always new)
        "singleton_same_instance": probe.settings_a is probe.settings_b,  # True app-wide
    }
```

#### Example: singleton HTTPX client in Clean IoC

```python
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI

from clean_ioc import Container, Lifespan
from clean_ioc.ext.fastapi import Resolve, add_container_to_app


class ExternalApi:
    def __init__(self, client: httpx.AsyncClient):
        self.client = client

    async def health(self) -> dict:
        r = await self.client.get("https://example.com/health")
        r.raise_for_status()
        return r.json()


@asynccontextmanager
async def httpx_client_factory():
    # One client for app lifetime: reuses connections and TLS sessions.
    async with httpx.AsyncClient(timeout=5.0) as client:
        yield client


@asynccontextmanager
async def app_lifespan(app: FastAPI):
    container = Container()
    container.register(httpx.AsyncClient, factory=httpx_client_factory, lifespan=Lifespan.singleton)
    container.register(ExternalApi, lifespan=Lifespan.scoped)

    async with add_container_to_app(app, container):
        yield


app = FastAPI(lifespan=app_lifespan)


@app.get("/external-health")
async def external_health(api: ExternalApi = Resolve(ExternalApi)):
    return await api.health()
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
