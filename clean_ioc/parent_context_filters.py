from . import ParentContext
from .functional_utils import constant, predicate

yes = constant(True)


def parent_implementation_is(cls: type):
    def inner(context: ParentContext):
        return context.parent.implementation == cls

    return predicate(inner)


def parent_service_type_is(cls: type):
    def inner(context: ParentContext):
        return context.parent.service_type == cls

    return predicate(inner)
