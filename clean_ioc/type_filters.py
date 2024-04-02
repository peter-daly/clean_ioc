import inspect

from .functional_utils import predicate


def named(name: str):
    def inner(t: type):
        return t.__name__ == name

    return predicate(inner)


def name_starts_with(name: str):
    def inner(t: type):
        return t.__name__.startswith(name)

    return predicate(inner)


def name_end_with(name: str):
    def inner(t: type):
        return t.__name__.endswith(name)

    return predicate(inner)


def is_in_module(*module_names: str):
    def inner(t: type):
        return any([t.__module__ == m for m in module_names])

    return predicate(inner)


def _is_abstract(t: type):
    return inspect.isabstract(t)


is_abstract = predicate(_is_abstract)


def is_subclass_of(cls: type):
    def inner(t: type):
        return issubclass(t, cls)

    return predicate(inner)
