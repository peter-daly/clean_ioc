"""Before/after probes for existing runtime paths (100 operations per batch).

This module uses public APIs available at the managed-provider baseline and can
be run unchanged against that checkout. Builds and target warm-up are excluded.
"""

from collections.abc import Iterator
from typing import Protocol

from benchbro import Case, system

from clean_ioc import ContainerBuilder, Provider


class Resource:
    pass


def resource() -> Iterator[Resource]:
    yield Resource()


class Operation(Protocol):
    def process(self) -> None: ...


class Implementation:
    def __init__(self, resource: Resource):
        self.resource = resource

    def process(self) -> None:
        pass


@system(scope="session")
def targets() -> Iterator[dict]:
    singleton = ContainerBuilder()
    singleton.register(Resource, lifespan="singleton")
    call = ContainerBuilder()
    call.register(Resource, factory=resource, lifespan="scoped")
    call.register(Operation, Implementation, scope="per_call")
    with singleton.build() as root, call.build() as operations:
        provider = root.resolve(Provider[Resource])
        provider()
        yield {
            "resolve": lambda: root.resolve(Resource),
            "provider": provider,
            "scope": root.new_scope,
            "per-call": operations.resolve(Operation).process,
        }


case = Case(name="managed-existing-runtime-regression", min_iterations=1000)


@case.benchmark(name="batch-of-100")
@case.parametrize("path", ["resolve", "provider", "scope", "per-call"])
def probe(targets: dict, path: str):
    target = targets[path]
    for _ in range(100):
        result = target()
        if path == "scope":
            result.__exit__()
    return result
