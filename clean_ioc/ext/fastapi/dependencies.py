from clean_ioc.core import Scope
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


class ResponseHeaderWriter:
    def __init__(self, response: Response):
        self.response = response

    def write(self, key: str, value: str):
        self.response.headers[key] = value


def _add_request_header_reader_to_scope(request: Request, scope: Scope = Depends(get_scope)):
    reader = RequestHeaderReader(request)
    scope.register(RequestHeaderReader, instance=reader)


def _add_response_header_writer_to_scope(response: Response, scope: Scope = Depends(get_scope)):
    writer = ResponseHeaderWriter(response)
    scope.register(ResponseHeaderWriter, instance=writer)


add_request_header_reader_to_scope = Depends(_add_request_header_reader_to_scope)
add_response_header_writer_to_scope = Depends(_add_response_header_writer_to_scope)
