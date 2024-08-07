from collections.abc import Callable
from typing import TypeVar

from theutilitybelt.functional.predicate import predicate

TArg = TypeVar("TArg")


def constant(val: TArg) -> Callable[..., TArg]:
    def fun(*_):
        return val

    return fun


def fn_not(func: Callable[..., bool]):
    def predicate(*args, **kwargs):
        return not func(*args, **kwargs)

    return predicate


def fn_and(*funcs: Callable[..., bool]):
    def predicate(*args, **kwargs):
        for func in funcs:
            if not func(*args, **kwargs):
                return False
        return True

    return predicate


def fn_or(*funcs: Callable[..., bool]):
    def predicate(*args, **kwargs):
        for func in funcs:
            if func(*args, **kwargs):
                return True
        return False

    return predicate


def fn_xor(*funcs: Callable[..., bool]):
    def predicate(*args, **kwargs):
        return len([f for f in funcs if f(*args, **kwargs)]) % 2 == 1

    return predicate


Predicate = predicate
