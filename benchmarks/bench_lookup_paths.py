"""Existing non-alias lookup paths affected by alias normalization.

Run this exact file against the pre-change and post-change packages. All keys and
filters are prepared outside the measured boundary. Systems warm singleton caches.
"""

from collections.abc import Iterator
from typing import Generic, TypeVar

from benchbro import Case, system

from clean_ioc import Container, ContainerBuilder, Provider
from clean_ioc import component_filters as cf


class Leaf:
    pass


class AlternateLeaf:
    pass


T = TypeVar("T")


class Repository(Generic[T]):
    pass


GENERIC_KEY = Repository[int]
UNION_KEY = Leaf | AlternateLeaf
PROVIDER_KEY = Provider[Leaf]
COLLECTION_KEY = list[Leaf]
NAMED_FILTER = cf.with_name("named")


@system(scope="session")
def lookup_container() -> Iterator[Container]:
    builder = ContainerBuilder()
    builder.register(Leaf, lifespan="singleton")
    builder.register(Leaf, name="named", lifespan="singleton")
    builder.register(GENERIC_KEY, lifespan="singleton")
    builder.register(UNION_KEY, instance=Leaf())
    container = builder.build()
    with container:
        for key in (Leaf, GENERIC_KEY, UNION_KEY, PROVIDER_KEY, COLLECTION_KEY):
            container.resolve(key)
        container.resolve(Leaf, NAMED_FILTER)
        yield container


lookup = Case(
    name="existing-lookup-paths",
    tags=["runtime", "alias-regression-check"],
    min_iterations=20_000,
    setup_timing="exclude",
    teardown_timing="exclude",
)


@lookup.benchmark(name="cached-class-default")
def cached_class_default(lookup_container: Container) -> object:
    return lookup_container.resolve(Leaf)


@lookup.benchmark(name="cached-class-filtered")
def cached_class_filtered(lookup_container: Container) -> object:
    return lookup_container.resolve(Leaf, NAMED_FILTER)


@lookup.benchmark(name="cached-closed-generic")
def cached_closed_generic(lookup_container: Container) -> object:
    return lookup_container.resolve(GENERIC_KEY)


@lookup.benchmark(name="cached-union")
def cached_union(lookup_container: Container) -> object:
    return lookup_container.resolve(UNION_KEY)


@lookup.benchmark(name="provider-root")
def provider_root(lookup_container: Container) -> object:
    return lookup_container.resolve(PROVIDER_KEY)


@lookup.benchmark(name="collection-root")
def collection_root(lookup_container: Container) -> object:
    return lookup_container.resolve(COLLECTION_KEY)


@lookup.benchmark(name="has-component-class")
def has_component_class(lookup_container: Container) -> bool:
    return lookup_container.has_component(Leaf)
