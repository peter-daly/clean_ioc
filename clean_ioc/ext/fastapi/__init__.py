from typing import Annotated, AsyncGenerator

from clean_ioc import (
    Container,
    RegistrationFilter,
    Scope,
    ContainerScope,
    TService,
    _default_registration_filter,
)
from fastapi import Depends, FastAPI, Request, params


class FastAPIScope(ContainerScope):
    def __init__(self, container: Container, request: Request):
        super().__init__(container)
        self.request = request


def add_container_to_app(
    app: FastAPI,
    container: Container,
    default_scope_cls: type[FastAPIScope] = FastAPIScope,
):
    app.state.clean_ioc_container = container
    app.state.clean_ioc_scope_cls = default_scope_cls


async def get_scope(
    request: Request,
) -> AsyncGenerator[Scope, None]:
    container: Container = request.app.state.clean_ioc_container
    scope_cls: type[FastAPIScope] = request.app.state.clean_ioc_scope_cls
    async with container.new_scope(ScopeClass=scope_cls, request=request) as scope:
        yield scope


def Resolve(
    cls: type[TService],
    filter: RegistrationFilter = _default_registration_filter,
) -> Annotated[TService, params.Depends]:
    async def resolver(scope: Annotated[Scope, Depends(get_scope)]):
        return scope.resolve(cls, filter=filter)

    return Depends(resolver)
