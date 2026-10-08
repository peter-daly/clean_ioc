"""Importable synthetic application for the local compiled-artifact experiment.

Importing this module defines types; it does not register or construct services.
Each root has a binary tree of 255 dependencies (256 occurrences with the root).
"""

from typing import Any

ACTIVATIONS = 0
MAX_ROOTS = 512


class Leaf:
    __slots__ = ("payload",)

    def __init__(self):
        global ACTIVATIONS
        ACTIVATIONS += 1
        self.payload = bytearray(128)


class Pair:
    __slots__ = ("left", "right")

    def __init__(self, left: Leaf, right: Leaf):
        global ACTIVATIONS
        ACTIVATIONS += 1
        self.left = left
        self.right = right


def _node_type(name: str, dependency: type) -> type:
    def init(self, left, right):
        global ACTIVATIONS
        ACTIVATIONS += 1
        self.left, self.right = left, right

    init.__annotations__ = {"left": dependency, "right": dependency}
    return type(name, (), {"__module__": __name__, "__slots__": ("left", "right"), "__init__": init})


def _root_type(name: str, dependency: type) -> type:
    def init(self, dependency):
        global ACTIVATIONS
        ACTIVATIONS += 1
        self.dependency = dependency

    init.__annotations__ = {"dependency": dependency}
    return type(name, (), {"__module__": __name__, "__slots__": ("dependency",), "__init__": init})


NODES = [Leaf]
for _level in range(1, 8):
    _name = f"Node{_level}"
    globals()[_name] = _node_type(_name, NODES[-1])
    NODES.append(globals()[_name])

ROOTS = []
for _index in range(MAX_ROOTS):
    _name = f"Root{_index}"
    globals()[_name] = _root_type(_name, NODES[-1])
    ROOTS.append(globals()[_name])


def build(root_count: int):
    # The load process never calls this function.
    from clean_ioc import ContainerBuilder

    if not 1 <= root_count <= MAX_ROOTS:
        raise ValueError(f"roots must be between 1 and {MAX_ROOTS}")
    builder = ContainerBuilder()
    for node in NODES:
        builder.register(node, lifespan="transient", root_policy="dependency_only")
    for root in ROOTS[:root_count]:
        builder.register(root, lifespan="transient")
    return builder.build(
        diagnostics=False,
        provider_roots=(),
        allow_scope_builders=False,
        check_unreachable=False,
        aggregate_errors=False,
    )


def inspect_instances(roots: list[Any]) -> dict[str, int]:
    """Check every constructed node, including identity and leaf payloads."""
    seen: set[int] = set()
    leaves = 0
    pending = list(roots)
    while pending:
        node = pending.pop()
        if id(node) in seen:
            raise AssertionError("The transient fixture unexpectedly shared an instance")
        seen.add(id(node))
        if isinstance(node, Leaf):
            if len(node.payload) != 128 or any(node.payload):
                raise AssertionError("Incorrect leaf payload")
            leaves += 1
        elif hasattr(node, "dependency"):
            pending.append(node.dependency)
        else:
            pending.extend((node.left, node.right))
    expected = len(roots) * 256
    if len(seen) != expected or leaves != len(roots) * 128:
        raise AssertionError("Incorrect resolved graph topology")
    return {"objects": len(seen), "leaves": leaves, "payload_bytes": leaves * 128}
