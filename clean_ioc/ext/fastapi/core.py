from typing import Annotated, AsyncGenerator

from clean_ioc.core import (
    Container,
    ContainerScope,
    RegistrationFilter,
    Scope,
    TService,
    default_registration_filter,
)
from fastapi import Depends, FastAPI, Request, Response, params


class FastAPIScope(ContainerScope):
    def __init__(self, container: Container, request: Request, response: Response):
        super().__init__(container)
        self.request = request
        self.response = response


def add_container_to_app(
    app: FastAPI,
    container: Container,
    default_scope_cls: type[FastAPIScope] = FastAPIScope,
):
    """
    Adds a container to the given FastAPI app.

    Args:
        app (FastAPI): The FastAPI app to add the container to.
        container (Container): The container to be added.
        default_scope_cls (type[FastAPIScope], optional): The default scope class. Defaults to FastAPIScope.
    """
    app.state.clean_ioc_container = container
    app.state.clean_ioc_scope_cls = default_scope_cls


async def get_scope(
    request: Request,
    response: Response,
) -> AsyncGenerator[Scope, None]:
    container: Container = request.app.state.clean_ioc_container
    scope_cls: type[FastAPIScope] = request.app.state.clean_ioc_scope_cls
    async with container.new_scope(ScopeClass=scope_cls, request=request, response=response) as scope:
        yield scope


def Resolve(  # noqa: N802
    service_type: type[TService],
    filter: RegistrationFilter = default_registration_filter,
) -> Annotated[TService, params.Depends]:
    """
    Resolve a type from the clean_ioc container, acts as a FastAPI dependency.
    This can be used as a drop in replacement for Depends in FastAPI routes.

    Args:
        service_type: The type of the service to resolve.
        filter: The registration filter to apply (default is the default registration filter).

    Returns:
        Annotated[TService, params.Depends]: A dependency resolver for the given service type and filter.
    """

    async def resolver(scope: Annotated[Scope, Depends(get_scope)]):
        return await scope.resolve_async(service_type, filter=filter)

    return Depends(resolver)
