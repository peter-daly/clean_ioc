import types
from collections.abc import Callable
from queue import Queue
from typing import (  # type: ignore
    Generic,
    Protocol,
    TypeVar,
    _GenericAlias,
    _SpecialGenericAlias,
    get_type_hints,
)

TypingGenericAlias = (_GenericAlias, _SpecialGenericAlias, types.GenericAlias)


class GenericTypeMap:
    def __init__(self, initial_map: dict[TypeVar | str, type | TypeVar] = {}):
        self.inner_map: dict[str, TypeVar | type] = {}

        for k, v in initial_map.items():
            self[k] = v

    @staticmethod
    def from_type(type_cls: type):
        generic_definitions = get_open_generic_aliases(type_cls)

        generic_implementations = get_generic_aliases(type_cls)

        generic_implementations = generic_implementations[: len(generic_definitions)]

        generic_definitions.reverse()
        generic_implementations.reverse()

        mapping = {}

        for idx, definition in enumerate(generic_definitions):
            implementation = generic_implementations[idx]
            additions = dict(zip(definition.__args__, implementation.__args__))
            mapping = {**mapping, **additions}

        return GenericTypeMap(mapping)

    @classmethod
    def _lookup_key(cls, key: TypeVar | str) -> str:
        if isinstance(key, TypeVar):
            return key.__name__
        return key

    def is_generic_mapping_open(self):
        for k, v in self.inner_map.items():
            if isinstance(v, TypeVar):
                return True
        return False

    def is_generic_mapping_closed(self):
        return not self.is_generic_mapping_open()

    def __getitem__(self, key: TypeVar | str):
        return self.inner_map[self._lookup_key(key)]

    def __setitem__(self, key: TypeVar | str, value: type | TypeVar):
        self.inner_map[self._lookup_key(key)] = value

    def values(self):
        return self.inner_map.values()

    def get(self, key: TypeVar | str, default=None):
        return self.inner_map.get(self._lookup_key(key), default)

    def items(self):
        return self.inner_map.items()

    def __eq__(self, __value: object) -> bool:
        if not isinstance(__value, GenericTypeMap):
            return False
        return self.inner_map == __value.inner_map


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
    m = GenericTypeMap.from_type(cls)
    return m.is_generic_mapping_closed()


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

    return isinstance(tp, type) and issubclass(tp, Generic) or isinstance(tp, TypingGenericAlias)


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


## NEW
def get_open_generic_aliases(cls: type):
    queue = Queue()
    queue.put(cls)
    aliases = []

    if root_origin := (getattr(cls, "__origin__", None)):
        queue.put(root_origin)

    while not queue.empty():
        type_check = queue.get()
        if getattr(type_check, "__origin__", None) in (Generic, Protocol):
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


def get_generic_types(cls: type):
    mapping = GenericTypeMap.from_type(cls)
    return tuple(mapping.values())


def try_to_complete_generic(open_type: _GenericAlias, closed_type: type) -> type:
    if not getattr(open_type, "__args__", None):
        return open_type
    if is_generic_type_closed(open_type):
        return open_type

    mapping = GenericTypeMap.from_type(closed_type)
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
