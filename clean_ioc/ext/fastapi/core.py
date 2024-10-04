import logging
from contextlib import asynccontextmanager
from typing import Annotated, AsyncGenerator

from clean_ioc.core import (
    Container,
    RegistrationFilter,
    Scope,
    TService,
    default_registration_filter,
)
from fastapi import Depends, FastAPI, Request, params

logger = logging.getLogger(__name__)


@asynccontextmanager
async def add_container_to_app(app: FastAPI, container: Container):
    """
    Adds a container to the given FastAPI app.

    Args:
        app (FastAPI): The FastAPI app to add the container to.
        container (Container): The container to be added.
    """
    async with add_root_scope_to_app(app, container):
        yield


@asynccontextmanager
async def add_root_scope_to_app(app: FastAPI, root_scope: Scope):
    """
    Adds the root scope to the given FastAPI app.

    Args:
        app (FastAPI): The FastAPI app to add the container to.
        root_scope (Scope): The scope to be added.
    """
    async with root_scope:
        logger.debug("adding root scope to the fast api app")
        app.state.root_scope = root_scope
        yield
        logger.debug("releasing root scope from the fast api app")


def get_root_scope_from_app(app: FastAPI) -> Scope:
    return app.state.root_scope


async def get_scope(
    request: Request,
) -> AsyncGenerator[Scope, None]:
    root_scope: Scope = get_root_scope_from_app(request.app)

    if "current_scope" in request.state._state:
        yield request.state.current_scope
    else:
        async with root_scope.new_scope() as scope:
            request.state.current_scope = scope
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
