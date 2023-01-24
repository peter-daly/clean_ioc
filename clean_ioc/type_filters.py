import inspect


def named(name: str):
    def predicate(t: type):
        return t.__name__ == name

    return predicate


def name_starts_with(name: str):
    def predicate(t: type):
        return t.__name__.startswith(name)

    return predicate


def name_end_with(name: str):
    def predicate(t: type):
        return t.__name__.endswith(name)

    return predicate


def is_in_module(*module_names: str):
    def predicate(t: type):
        return any([t.__module__ == m for m in module_names])

    return predicate


def is_abstract(t: type):
    return inspect.isabstract(t)
