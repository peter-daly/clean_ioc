"""FastAPI preparation for the private compiled-container experiment."""

from fastapi import Request, Response

from clean_ioc.ext.fastapi.dependencies import RequestHeaderReader, ResponseHeaderWriter

from .compiled_container import CompiledContainer

_STANDARD_FASTAPI_SCOPE_TYPES = (
    Request,
    Response,
    RequestHeaderReader,
    ResponseHeaderWriter,
)


def prepare_fastapi_scope_slots(container: CompiledContainer) -> CompiledContainer:
    """Declare the request-local types supplied by Clean IoC's FastAPI helpers."""

    for service_type in _STANDARD_FASTAPI_SCOPE_TYPES:
        if not container.has_scope_slot(service_type):
            container.expect_to_be_scoped(service_type)
    return container
