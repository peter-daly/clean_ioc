"""Private graph sidecars with bounded compact integer storage.

General mapping operations permanently delegate to one native dictionary. Borrowed
keys and values retain identity; public live views never detach from their backing.
This is not a general-purpose dictionary replacement or public persistence format.
"""

# Exact type identity must not invoke application __class__ or metaclass equality.
# ruff: noqa: E721
import sys
from collections.abc import MutableMapping
from typing import Any, TypeVar

_V = TypeVar("_V")
_MISSING = object()


class _CompactIndex(MutableMapping[int, _V]):
    """Private typed index: bounded dense storage with native mapping adapters."""

    __slots__ = ("_values", "_keys", "_sparse", "_dict", "_eligible")
    LIMIT = 1 << 20
    THRESHOLD = 128

    def __init__(self):
        self._values: Any = None
        self._keys: Any = None
        self._sparse: Any = None
        self._dict: Any = {}
        self._eligible = self.THRESHOLD

    def raw_items(self):
        if self._dict is not None:
            yield from self._dict.items()
        else:
            for key in self._keys:
                yield key, self[key]

    def promote(self):
        self._eligible = False
        if self._dict is None:
            self._dict = dict(self.raw_items())
            self._values = self._keys = self._sparse = None
        return self._dict

    def _consider_compact(self):
        mapping = self._dict
        if len(mapping) < self._eligible:
            return
        checkpoint = self._eligible
        self._eligible = False
        minimum, maximum = min(mapping), max(mapping)
        if minimum < 0 or maximum >= min(self.LIMIT, 2 * len(mapping)):
            if checkpoint < 4096:
                self._eligible = checkpoint * 2
            return
        self._keys = list(mapping)
        self._values = [_MISSING] * (maximum + 1)
        self._sparse = {}
        for key, value in mapping.items():
            self._values[key] = value
        self._dict = None

    def __getitem__(self, key, /):
        if type(key) is not int:
            return self.promote()[key]
        if self._dict is not None:
            return self._dict[key]
        if 0 <= key < len(self._values):
            value = self._values[key]
            if value is not _MISSING:
                return value
        return self._sparse[key]

    def get(self, key, default=None, /):
        if type(key) is not int:
            return self.promote().get(key, default)
        if self._dict is not None:
            return self._dict.get(key, default)
        if 0 <= key < len(self._values):
            value = self._values[key]
            if value is not _MISSING:
                return value
        return self._sparse.get(key, default)

    def __contains__(self, key, /):
        if type(key) is not int:
            return key in self.promote()
        if self._dict is not None:
            return key in self._dict
        return self.get(key, _MISSING) is not _MISSING

    def __setitem__(self, key, value, /):
        # Lock backing before application hashing/equality can reenter this index.
        if type(key) is not int:
            self.promote()[key] = value
            return
        if self._dict is not None:
            self._dict[key] = value
            if self._eligible:
                self._consider_compact()
            return
        previous = self.get(key, _MISSING)
        if previous is not _MISSING:
            if 0 <= key < len(self._values) and self._values[key] is not _MISSING:
                self._values[key] = value
            else:
                self._sparse[key] = value
            return
        self._keys.append(key)
        if 0 <= key < min(self.LIMIT, 2 * len(self._keys)):
            if key >= len(self._values):
                self._values.extend([_MISSING] * (key + 1 - len(self._values)))
            self._values[key] = value
        else:
            self._sparse[key] = value
            if len(self._sparse) > max(32, len(self._keys) // 8):
                self.promote()

    def __delitem__(self, key, /):
        del self.promote()[key]

    def __iter__(self, /):
        return iter(self.promote())

    def keys(self, /):
        return self.promote().keys()

    def values(self, /):
        return self.promote().values()

    def items(self, /):
        return self.promote().items()

    def __reversed__(self, /):
        return reversed(self.promote())

    def __len__(self, /):
        return len(self._dict) if self._dict is not None else len(self._keys)

    def popitem(self, /):
        return self.promote().popitem()

    def clear(self, /):
        return self.promote().clear()

    def setdefault(self, key, default=None, /):
        return self.promote().setdefault(key, default)

    def pop(self, key, /, *default):
        return self.promote().pop(key, *default)

    def copy(self, /):
        return self.promote().copy()

    def __eq__(self, other, /):
        if type(other) is _CompactIndex:
            other = other.promote()
        return self.promote().__eq__(other)

    def update(self, /, *arguments, **keywords):
        if len(arguments) == 1 and type(arguments[0]) is _CompactIndex:
            arguments = (arguments[0].promote(),)
        return self.promote().update(*arguments, **keywords)

    def __or__(self, other, /):
        if type(other) is _CompactIndex:
            other = other.promote()
        return self.promote().__or__(other)

    def __ror__(self, other, /):
        if type(other) is _CompactIndex:
            other = other.promote()
        return self.promote().__ror__(other)

    def __ior__(self, other, /):
        if type(other) is _CompactIndex:
            other = other.promote()
        self.promote().__ior__(other)
        return self

    def capacity(self):
        return {
            "entries": len(self),
            "dense_length": len(self._values or ()),
            "sparse_entries": len(self._sparse or ()),
            "promoted": self._dict is not None,
            "eligible": self._eligible,
            "shallow_bytes": sys.getsizeof(self)
            + sum(
                sys.getsizeof(value)
                for value in (self._values, self._keys, self._sparse, self._dict)
                if value is not None
            ),
        }
