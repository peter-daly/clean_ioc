"""Fresh builder declarations without compilation, plus an empty build control.

Class definitions are prepared once outside the timed work. Each invocation
creates a new builder so registrations never accumulate across samples.
"""

from benchbro import Case

from clean_ioc import ContainerBuilder


class Service:
    pass


DISTINCT_SERVICES = tuple(type(f"Service{index}", (), {}) for index in range(1000))

declarations = Case(name="registration-declarations", min_iterations=1, gc_control="inherit")


@declarations.benchmark()
@declarations.parametrize("count", [100, 1000, 5000])
def repeated_factory(count: int):
    builder = ContainerBuilder()
    for _ in range(count):
        builder.register(Service, factory=Service)


@declarations.benchmark()
def distinct_concrete():
    builder = ContainerBuilder()
    for service in DISTINCT_SERVICES:
        builder.register(service)


@declarations.benchmark(min_iterations=100)
def empty_build():
    with ContainerBuilder().build():
        pass
