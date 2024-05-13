# Fast API

Clean IoC comes with helpers to help you easily integrate it woth Fast API. If you are using Clean IoC with other application types and wanting that same experience in Fast API development you can add it as a container to Fast API.


## How it works

The app works by giving you a Clean IoC scope with every FastAPI request allowing you to leverage scoped lifetimes. This makses it easy for you to have a single SqlAlchemy connection per app if you want to.


## Setting it up
Clean IoC comes with a simple utility function that wires up the container to the app.
It's best to the wiring up within a lifespan.

!!! note "Same word different meaning"
    ***Lifespan*** in Fast API refers to the ability to configure run sone setup and teardown during the lifetime of the app. ***Lifespan*** in Clean Ioc is a setting on a regiestered dependency on how long the registered dependency stays alive for.



When you want to access a dependnecy in your routes you can use the **Resolve** helper function.
This gives you a  very similar experience to using **Depends** in Fast API, the only difference is that you provider the type you want to resolve rather then the the resolver function.

||| note "add_container_to_app" is also asynccontextmanager"
    The **add_container_to_app** function will use the container as an ***asynccontextmanager***, meaning you won't have to manually do that yourself.

```python
from fastapi import FastAPI
from clean_ioc.ext.fastapi import Resolve, add_container_to_app

class MyDependency:
    def do_action(self) -> str:
        print('DO THE THING')

@asynccontextmanager
async def app_lifespan(a: FastAPI):
    container = Container()
    container.register(MyDependency)
    async with add_container_to_app(a, container):
        yield

app = FastAPI(lifespan=lifespan)

@app.post("/")
async def read_root(my_dependency: MyDependency = Resolve(MyDependency)):
    my_dependency.do_action()
```


## Accessinng Fast API objects inside container dependencies.

You can fast api Dependencies to the scope of the request using the **get_scope** helper.
Create a new function that depends on **get_scope** and add items to the scope.

```python
from fastapi import FastAPI, Request
from clean_ioc.ext.fastapi import Resolve, add_container_to_app, get_scope

class MyDependency:

    def __init__(self, request: Request):
        self.request = request
    def do_action(self) -> str:
        print('DO THE THING WITH REQUEST')

def add_request_to_scope(request: Request, scope: Scope = Depends(get_scope)):
    scope.register(Request, instance=request)

@asynccontextmanager
async def app_lifespan(a: FastAPI):
    container = Container()
    container.register(MyDependency)
    async with add_container_to_app(a, container):
        yield

app = FastAPI(lifespan=lifespan, dependencies=[Depends(add_request_to_scope)])

@app.post("/")
async def read_root(my_dependency: MyDependency = Resolve(MyDependency)):
    my_dependency.do_action()
```