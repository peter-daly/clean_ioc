"""Structural compilation versus explicit registration, and frozen resolution.

Build includes declaration, complete compilation, and close. Runtime excludes
fixture construction, alias construction, and singleton warmup. Both variants
compile the same finite list nesting and use the same ordinary activation steps.
"""

from collections.abc import Iterator
from typing import Any, Generic, TypeVar

from benchbro import Case, system

from clean_ioc import Container, ContainerBuilder

T = TypeVar("T")


class Serializer(Generic[T]):
    def __init__(self, child: object = None):
        self.child = child


class Root(Generic[T]):
    def __init__(self, serializer: Serializer[T]):
        self.serializer = serializer


def list_factory(child: Serializer[T]) -> Serializer[list[T]]:
    return Serializer(child)


def closed_factory(child_type):
    def factory(child):
        return Serializer(child)

    factory.__annotations__ = {"child": child_type}
    return factory


def make_container(depth: int, mode: str, overlap: int = 0, lifespan="transient") -> tuple[Container, Any]:
    builder = ContainerBuilder()
    builder.register(Serializer[int], factory=Serializer, lifespan=lifespan)
    if mode == "pattern":
        builder.register_pattern(Serializer[list[T]], factory=list_factory, lifespan=lifespan)
        # Incomparable unmatched templates exercise origin indexing and matching
        # without changing the winning nested-list factory.
        for index in range(overlap):
            marker = type(f"Marker{index}", (), {})
            builder.register_pattern(Serializer[dict[marker, T]], factory=Serializer, lifespan=lifespan)
    annotation = int
    for _ in range(depth):
        child = Serializer[annotation]
        annotation = list[annotation]
        if mode == "explicit":
            builder.register(Serializer[annotation], factory=closed_factory(child), lifespan=lifespan)
    builder.register(Root[annotation])
    return builder.build(), Serializer[annotation]


build = Case(name="registration-pattern-build", tags=["build", "registration-pattern"], min_iterations=10)


@build.benchmark(name="nested")
@build.parametrize("depth", [1, 3, 6])
@build.parametrize("mode", ["pattern", "explicit"])
def build_nested(depth, mode):
    container, _ = make_container(depth, mode)
    with container:
        pass


@build.benchmark(name="overlapping-origin")
@build.parametrize("overlap", [0, 5, 20])
def build_overlapping(overlap):
    container, _ = make_container(3, "pattern", overlap)
    with container:
        pass


@build.benchmark(name="matching-specificity-set")
@build.parametrize("count", [1, 5, 20])
def build_specificity(count):
    builder = ContainerBuilder()
    template, concrete = T, int
    for _ in range(count):
        template, concrete = list[template], list[concrete]
        builder.register_pattern(Serializer[template], factory=Serializer)
    builder.register(Root[concrete])
    with builder.build():
        pass


@system(scope="session")
def pattern_fixtures() -> Iterator[dict]:
    fixtures = {
        (mode, lifespan): make_container(3, mode, lifespan=lifespan)
        for mode in ("pattern", "explicit")
        for lifespan in ("transient", "singleton")
    }
    for container, key in fixtures.values():
        container.resolve(key)
    try:
        yield fixtures
    finally:
        for container, _ in fixtures.values():
            with container:
                pass


runtime = Case(
    name="registration-pattern-runtime",
    tags=["runtime", "registration-pattern"],
    min_iterations=20_000,
    setup_timing="exclude",
    teardown_timing="exclude",
)


@runtime.benchmark(name="frozen-resolve")
@runtime.parametrize("mode", ["pattern", "explicit"])
@runtime.parametrize("lifespan", ["transient", "singleton"])
def frozen_resolve(pattern_fixtures, mode, lifespan):
    container, key = pattern_fixtures[(mode, lifespan)]
    return container.resolve(key)
