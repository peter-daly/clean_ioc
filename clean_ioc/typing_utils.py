from typing import _GenericAlias, _SpecialGenericAlias  # type: ignore
from typing import Generic, TypeVar
from collections.abc import Callable
from typing import get_type_hints
import types
from queue import Queue
import inspect

typingGenericAlias = (_GenericAlias, _SpecialGenericAlias, types.GenericAlias)


def get_subclasses(cls: type, filter: Callable[[type], bool] = lambda t: True):
    queue = Queue()
    queue.put(cls)
    items = []
    while not queue.empty():
        t = queue.get_nowait()

        for sub in t.__subclasses__():
            queue.put(sub)

            if filter(sub):
                items.append(sub)

    return items


def get_generic_bases(cls: type, filter: Callable[[type], bool] = lambda t: True):
    queue = Queue()
    queue.put(cls)
    items = []
    while not queue.empty():
        t = queue.get_nowait()

        for sub in getattr(t, "__orig_bases__", ()):
            queue.put(sub)
            if orig := getattr(sub, "__origin__", None):
                queue.put(orig)

            if filter(sub):
                items.append(sub)

    return items


def is_generic_type_closed(cls: type):
    m = get_typevar_to_type_mapping(cls)
    for k, v in m.items():
        if k == v:
            return False
    return True


def get_type_args(cls: type):
    return getattr(cls, "__args__", ())


def is_generic_type(tp: type):
    """Test if the given type is a generic type. This includes Generic itself, but
    excludes special typing constructs such as Union, Tuple, Callable, ClassVar.
    Examples::

        is_generic_type(int) == False
        is_generic_type(Union[int, str]) == False
        is_generic_type(Union[int, T]) == False
        is_generic_type(ClassVar[List[int]]) == False
        is_generic_type(Callable[..., T]) == False

        is_generic_type(Generic) == True
        is_generic_type(Generic[T]) == True
        is_generic_type(Iterable[int]) == True
        is_generic_type(Mapping) == True
        is_generic_type(MutableMapping[T, List[int]]) == True
        is_generic_type(Sequence[Union[str, bytes]]) == True
    """

    return (
        isinstance(tp, type)
        and issubclass(tp, Generic)
        or isinstance(tp, typingGenericAlias)
    )


def is_open_generic_type(cls: type):
    type_args = get_type_args(cls)
    if type_args:
        return any([isinstance(t, TypeVar) for t in type_args])
    else:
        return is_generic_type(cls)


def get_generic_type_args(type: type):
    queue = Queue()
    queue.put(type)

    while not queue.empty():
        type_check = queue.get()
        if getattr(type_check, "__origin__", None) == Generic:
            return type_check.__args__

        for base in getattr(type_check, "__orig_bases__", ()):
            queue.put(base)
            queue.put(base.__origin__)

    return ()


## OLD
def get_closed_open_generic_alias(cls: type):
    queue = Queue()
    queue.put(cls)

    while not queue.empty():
        type_check = queue.get()
        if type(type_check) == _GenericAlias:
            return type_check

        for base in getattr(type_check, "__orig_bases__", ()):
            queue.put(base)
            queue.put(base.__origin__)

    return None


def get_first_open_generic_alias(cls: type):
    queue = Queue()
    queue.put(cls)

    if root_origin := (getattr(cls, "__origin__", None)):
        queue.put(root_origin)

    while not queue.empty():
        type_check = queue.get()
        if getattr(type_check, "__origin__", None) == Generic:
            return type_check

        for base in getattr(type_check, "__orig_bases__", ()):
            queue.put(base)
            if orig := getattr(base, "__origin__", None):
                queue.put(orig)

    return None


## NEW
def get_open_generic_aliases(cls: type):
    queue = Queue()
    queue.put(cls)
    aliases = []

    if root_origin := (getattr(cls, "__origin__", None)):
        queue.put(root_origin)

    while not queue.empty():
        type_check = queue.get()
        if getattr(type_check, "__origin__", None) == Generic:
            aliases.append(type_check)

        for base in getattr(type_check, "__orig_bases__", ()):
            queue.put(base)
            if orig := getattr(base, "__origin__", None):
                queue.put(orig)

    return aliases


def get_generic_aliases(cls: type):
    queue = Queue()
    queue.put(cls)
    if orig := getattr(cls, "__origin__", None):
        queue.put(orig)

    aliases = []
    while not queue.empty():
        type_check = queue.get()
        if type(type_check) == _GenericAlias:
            aliases.append(type_check)

        for base in getattr(type_check, "__orig_bases__", ()):
            queue.put(base)
            if base_orig := getattr(base, "__origin__", None):
                queue.put(base_orig)

    return aliases


def get_typevar_to_type_mapping(cls: type) -> dict[type, type]:
    generic_definitions = get_open_generic_aliases(cls)
    generic_implementations = get_generic_aliases(cls)

    generic_implementations = generic_implementations[: len(generic_definitions)]

    generic_definitions.reverse()
    generic_implementations.reverse()

    mapping = {}

    for idx, definition in enumerate(generic_definitions):
        implementation = generic_implementations[idx]
        additions = dict(zip(definition.__args__, implementation.__args__))
        mapping = {**mapping, **additions}

    return mapping


def get_generic_types(cls: type):
    mapping = get_typevar_to_type_mapping(cls)
    return tuple(mapping.values())


def try_to_complete_generic(open_type: _GenericAlias, closed_type: type) -> type:
    if not getattr(open_type, "__args__", None):
        return open_type
    if is_generic_type_closed(open_type):
        return open_type

    mapping = get_typevar_to_type_mapping(closed_type)
    new_args = tuple([mapping.get(a, a) for a in open_type.__args__])
    return open_type[new_args]


def get_type_args_for_function(fn: Callable) -> dict[str, type]:
    return {k: v for k, v in get_type_hints(fn).items() if k != "return"}


def get_generic_type(obj):
    """Get the generic type of an object if possible, or runtime class otherwise.
    Examples::
        class Node(Generic[T]):
            ...
        type(Node[int]()) == Node
        get_generic_type(Node[int]()) == Node[int]
        get_generic_type(Node[T]()) == Node[T]
        get_generic_type(1) == int
    """

    gen_type = getattr(obj, "__orig_class__", None)
    return gen_type if gen_type is not None else type(obj)
