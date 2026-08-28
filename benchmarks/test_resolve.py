"""Resolution benchmarks.

Each benchmark isolates one cost in the resolve path so that a change to that
path shows up in one place. Registration happens outside the measured callable,
so the numbers cover resolution only. The exception is
``test_registration_of_many_types``, which measures registration on purpose.

Run with ``make bench``. Compare two revisions on the same machine with
``make bench-compare``; numbers from different machines are not comparable.
"""

from __future__ import annotations

import asyncio
import types
from collections.abc import Iterator

import pytest

from benchmarks.graphs import make_chain, make_class, make_fan_out, make_implementations
from clean_ioc import Container, Lifespan
from clean_ioc.registration_filters import with_name

CHAIN_DEPTH = 10
FAN_OUT_WIDTH = 50
IMPLEMENTATION_COUNT = 10
DECORATOR_COUNT = 3


@pytest.fixture
def loop() -> Iterator[asyncio.AbstractEventLoop]:
    """A loop reused across every round of an async benchmark.

    Loop creation is far more expensive than a resolve, so it must sit outside
    the measured callable. ``run_until_complete`` still adds a fixed overhead to
    the async numbers, which is why they are only ever compared to each other.
    """
    loop = asyncio.new_event_loop()
    try:
        yield loop
    finally:
        loop.close()


@pytest.mark.benchmark(group="single")
def test_transient_with_no_dependencies(benchmark):
    """Floor for the resolve path: one registration, one lookup, one construction."""
    a = make_class("A")
    container = Container()
    container.register(a, lifespan=Lifespan.transient)

    benchmark(container.resolve, a)


@pytest.mark.benchmark(group="single")
def test_singleton_already_cached(benchmark):
    """Warm cache hit. Should approach the cost of the registration lookup alone."""
    a = make_class("A")
    container = Container()
    container.register(a, lifespan=Lifespan.singleton)
    container.resolve(a)

    benchmark(container.resolve, a)


@pytest.mark.benchmark(group="shape")
def test_deep_transient_graph(benchmark):
    """A ten-level chain. Scales with recursion depth and per-node work."""
    chain = make_chain(CHAIN_DEPTH)
    container = Container()
    for cls in chain:
        container.register(cls, lifespan=Lifespan.transient)

    benchmark(container.resolve, chain[0])


@pytest.mark.benchmark(group="shape")
def test_wide_transient_graph(benchmark):
    """One root with fifty flat dependencies. Scales with node count, not depth."""
    root, siblings = make_fan_out(FAN_OUT_WIDTH)
    container = Container()
    container.register(root, lifespan=Lifespan.transient)
    for cls in siblings:
        container.register(cls, lifespan=Lifespan.transient)

    benchmark(container.resolve, root)


@pytest.mark.benchmark(group="shape")
def test_collection_dependency(benchmark):
    """``list[Base]`` with ten registrations behind it."""
    base, implementations = make_implementations(IMPLEMENTATION_COUNT)
    # Built through GenericAlias rather than ``list[base]`` so that the
    # subscript reads as a value expression, not a type expression.
    root = make_class("CollectionRoot", {"items": types.GenericAlias(list, (base,))})

    container = Container()
    for implementation in implementations:
        container.register(base, implementation, lifespan=Lifespan.transient)
    container.register(root, lifespan=Lifespan.transient)

    benchmark(container.resolve, root)


@pytest.mark.benchmark(group="lookup")
def test_filtered_lookup_over_many_registrations(benchmark):
    """Named lookup against ten registrations of the same service type.

    Isolates the registration scan and the filter call per candidate.
    """
    base, implementations = make_implementations(IMPLEMENTATION_COUNT)
    container = Container()
    for index, implementation in enumerate(implementations):
        container.register(base, implementation, name=f"impl-{index}", lifespan=Lifespan.transient)

    target = with_name(f"impl-{IMPLEMENTATION_COUNT - 1}")
    benchmark(lambda: container.resolve(base, filter=target))


@pytest.mark.benchmark(group="lookup")
def test_decorator_chain(benchmark):
    """Three decorators over one registration.

    Isolates the decorator scan and the extra node per decorator.
    """
    base = make_class("Decorated")
    container = Container()
    container.register(base, lifespan=Lifespan.transient)
    for index in range(DECORATOR_COUNT):
        container.register_decorator(base, make_class(f"Decorator{index}", {"inner": base}))

    benchmark(container.resolve, base)


@pytest.mark.benchmark(group="scope")
def test_scoped_resolve_in_root_scope(benchmark):
    """Baseline for the scoped path, one level below the container."""
    chain = make_chain(CHAIN_DEPTH)
    container = Container()
    container.register(chain[0], lifespan=Lifespan.scoped)
    for cls in chain[1:]:
        container.register(cls, lifespan=Lifespan.transient)

    with container.new_scope() as scope:
        benchmark(scope.resolve, chain[0])


@pytest.mark.benchmark(group="scope")
def test_scoped_resolve_in_nested_scope(benchmark):
    """The same resolve three scopes deep.

    Registration lookup walks to the parent scope for every dependency, so the
    gap between this and the previous benchmark is the cost of scope nesting.
    """
    chain = make_chain(CHAIN_DEPTH)
    container = Container()
    container.register(chain[0], lifespan=Lifespan.scoped)
    for cls in chain[1:]:
        container.register(cls, lifespan=Lifespan.transient)

    with container.new_scope() as outer, outer.new_scope() as middle, middle.new_scope() as inner:
        benchmark(inner.resolve, chain[0])


@pytest.mark.benchmark(group="async")
def test_async_deep_transient_graph(benchmark, loop):
    """The deep-graph benchmark through ``resolve_async``.

    The sync and async paths are written separately, so both need cover to keep
    them from drifting in performance as well as in behaviour.
    """
    chain = make_chain(CHAIN_DEPTH)
    container = Container()
    for cls in chain:
        container.register(cls, lifespan=Lifespan.transient)

    benchmark(lambda: loop.run_until_complete(container.resolve_async(chain[0])))


@pytest.mark.benchmark(group="registration")
def test_registration_of_many_types(benchmark):
    """Registration cost for a hundred types.

    Constructor introspection happens here rather than at resolve, so work moved
    out of the resolve path should land in this number.
    """
    classes = [make_class(f"Reg{index}") for index in range(100)]

    def register_all() -> None:
        container = Container()
        for cls in classes:
            container.register(cls, lifespan=Lifespan.transient)

    benchmark(register_all)
