import inspect

from theutilitybelt.functional.predicate import predicate


def named(name: str):
    """
    A function that takes a string 'name' and returns a predicate function that checks if the input type's
    name matches the given 'name'.
    """

    def _named(t: type):
        return t.__name__ == name

    return predicate(_named)


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
