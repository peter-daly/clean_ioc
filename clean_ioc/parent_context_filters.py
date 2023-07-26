from . import ParentContext
from .functional_utils import constant

yes = constant(True)


def parent_implementation_is(cls: type):
    def predicate(context: ParentContext):
        return context.parent.implementation == cls

    return predicate


def parent_service_type_is(cls: type):
    def predicate(context: ParentContext):
        return context.parent.service_type == cls

    return predicate
