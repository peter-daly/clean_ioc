from collections.abc import Callable
from typing import TypeVar

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


def _predicate_and(left: Callable, right: Callable):
    return lambda *args, **kwargs: left(*args, **kwargs) and right(*args, **kwargs)


def _predicate_or(left: Callable, right: Callable):
    return lambda *args, **kwargs: left(*args, **kwargs) or right(*args, **kwargs)


def _predicate_xor(left: Callable, right: Callable):
    return lambda *args, **kwargs: left(*args, **kwargs) ^ right(*args, **kwargs)


def _predicate_not(func: Callable):
    return lambda *args, **kwargs: not func(*args, **kwargs)


class Predicate:
    def __init__(self, func: Callable[..., bool]):
        self.func = func

    def __call__(self, *args, **kwargs):
        return self.func(*args, **kwargs)

    def __and__(self, other: Callable[..., bool]):
        return Predicate(_predicate_and(self.func, other))

    def __rand__(self, other: Callable[..., bool]):
        return Predicate(_predicate_and(other, self.func))

    def __or__(self, other: Callable[..., bool]):
        return Predicate(_predicate_or(self.func, other))

    def __ror__(self, other: Callable[..., bool]):
        return Predicate(_predicate_or(other, self.func))

    def __xor__(self, other: Callable[..., bool]):
        return Predicate(_predicate_xor(self.func, other))

    def __rxor__(self, other: Callable[..., bool]):
        return Predicate(_predicate_xor(other, self.func))

    def __invert__(self):
        return Predicate(_predicate_not(self.func))


def predicate(func: Callable[..., bool]):
    if isinstance(func, Predicate):
        return func
    return Predicate(func)


always_false = predicate(constant(False))
always_true = predicate(constant(True))
