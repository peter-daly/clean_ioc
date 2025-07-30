from collections.abc import Callable

from clean_ioc.core import Scope
from clean_ioc.functional_utils import constant
from fastapi import Depends, Request, Response

from .core import get_scope


class RequestHeaderReader:
    def __init__(self, request: Request):
        self.request = request

    def read(self, key: str, default_value: str = "") -> str:
        return self.request.headers.get(key, default_value)

    def header_exists(self, key: str) -> bool:
        return key in self.request.headers

    def __iter__(self):
        return self.request.headers.__iter__()

    def as_dict(self, filter_keys: Callable[[str], bool] = constant(True)) -> dict:
        return {k: v for k, v in self.request.headers.items() if filter_keys(k)}


class ResponseHeaderWriter:
    def __init__(self, response: Response):
        self.response = response

    def write(self, key: str, value: str):
        self.response.headers[key] = value


def add_request_to_scope(request: Request, scope: Scope = Depends(get_scope)):
    scope.register(Request, instance=request)


def add_response_to_scope(response: Response, scope: Scope = Depends(get_scope)):
    scope.register(Response, instance=response)


def add_request_header_reader_to_scope(request: Request, scope: Scope = Depends(get_scope)):
    reader = RequestHeaderReader(request)
    scope.register(RequestHeaderReader, instance=reader)


def add_response_header_writer_to_scope(response: Response, scope: Scope = Depends(get_scope)):
    writer = ResponseHeaderWriter(response)
    scope.register(ResponseHeaderWriter, instance=writer)
