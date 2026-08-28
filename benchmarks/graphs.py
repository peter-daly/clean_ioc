"""Builders for the object graphs the benchmarks resolve.

The shapes here are generated rather than written out by hand so that depth and
width are parameters of the benchmark instead of constants baked into source.
Every generated class is a real class with a real ``__init__`` signature, so the
container introspects it exactly as it would introspect application code.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, cast

_CLASS_TEMPLATE = """\
class {name}:
    def __init__(self{params}):
{body}
"""


def make_class(name: str, dependencies: Mapping[str, Any] | None = None) -> type:
    """Build a class whose ``__init__`` takes one annotated parameter per dependency.

    Args:
        name: Class name. Only used in error messages and reprs.
        dependencies: Parameter name to annotation. Annotations are ``Any``
            rather than ``type`` because a generic alias such as ``list[T]`` is a
            valid annotation and is not a class. An empty mapping or ``None``
            produces a class with no dependencies.

    Returns:
        The generated class.
    """
    dependencies = dependencies or {}

    params = "".join(f", {parameter}" for parameter in dependencies)
    body = "\n".join(f"        self.{p} = {p}" for p in dependencies) or "        pass"
    source = _CLASS_TEMPLATE.format(name=name, params=params, body=body)

    namespace: dict[str, object] = {}
    exec(source, namespace)  # noqa: S102 - generating real classes is the point
    cls = cast(type, namespace[name])

    # Annotate with the type objects directly. ``get_type_hints`` passes
    # non-string annotations straight through, so there is nothing to resolve.
    cls.__init__.__annotations__ = dict(dependencies)
    return cls


def make_chain(depth: int, prefix: str = "Chain") -> list[type]:
    """Build a chain of classes where each depends on the next.

    Returns:
        The chain from root to leaf. Index 0 is the root, so resolving it walks
        the full depth. All of them need registering.
    """
    leaf = make_class(f"{prefix}Leaf")
    chain = [leaf]
    for level in range(depth - 1):
        chain.append(make_class(f"{prefix}{level}", {"dep": chain[-1]}))
    chain.reverse()
    return chain


def make_fan_out(width: int, prefix: str = "Fan") -> tuple[type, list[type]]:
    """Build one class that depends on ``width`` siblings, none of which nest.

    Returns:
        The root class, and the sibling classes it depends on. All of them need
        registering.
    """
    siblings = [make_class(f"{prefix}Leaf{index}") for index in range(width)]
    root = make_class(prefix, {f"dep{index}": cls for index, cls in enumerate(siblings)})
    return root, siblings


def make_implementations(count: int, prefix: str = "Impl") -> tuple[type, list[type]]:
    """Build a base class and ``count`` subclasses of it.

    Returns:
        The base class and its subclasses. Used for collection resolution and
        for filtered lookups over a service type with many registrations.
    """
    base = make_class(prefix)
    implementations: list[type] = [type(f"{prefix}{index}", (base,), {}) for index in range(count)]
    return base, implementations
