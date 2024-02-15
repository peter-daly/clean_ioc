from fastapi import Request, Response, Depends
from .core import get_scope
from clean_ioc.core import Scope

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

def add_request_header_reader_to_scope(request: Request, scope: Scope = Depends(get_scope)):
    reader = RequestHeaderReader(request)
    scope.register(RequestHeaderReader, instance=reader)

def add_response_header_writer_to_scope(response: Response, scope: Scope = Depends(get_scope)):
    writer = ResponseHeaderWriter(response)
    scope.register(ResponseHeaderWriter, instance=writer)