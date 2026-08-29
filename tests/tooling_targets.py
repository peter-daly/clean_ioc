"""Importable composition targets used by CLI tests."""

from clean_ioc import ContainerBuilder


class Dependency:
    pass


class AlternateDependency(Dependency):
    pass


class Application:
    def __init__(self, dependency: Dependency):
        self.dependency = dependency


class Unused:
    pass


class Missing:
    pass


class InvalidApplication:
    def __init__(self, missing: Missing):
        self.missing = missing


def valid_builder() -> ContainerBuilder:
    builder = ContainerBuilder()
    builder.register(Dependency)
    builder.register(Application)
    builder.register(Unused)
    builder.mark_entrypoint(Application)
    return builder


def changed_builder() -> ContainerBuilder:
    builder = ContainerBuilder()
    builder.register(Dependency, AlternateDependency)
    builder.register(Application)
    builder.mark_entrypoint(Application)
    return builder


def invalid_builder() -> ContainerBuilder:
    builder = ContainerBuilder()
    builder.register(InvalidApplication)
    return builder
