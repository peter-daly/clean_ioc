"""Importable composition targets used by CLI tests."""

from clean_ioc import BuildIssue, Container, ContainerBuilder, IssueSeverity, ValidationContext


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


def organization_warning(_: ValidationContext):
    return (
        BuildIssue(
            code="example-organization-warning",
            severity=IssueSeverity.warning,
            message="Example organization policy warning",
        ),
    )


def custom_warning_builder() -> ContainerBuilder:
    builder = ContainerBuilder()
    builder.register(Application)
    builder.register(Dependency)
    builder.add_validation_rule(organization_warning)
    return builder


def strict_warning_builder() -> ContainerBuilder:
    builder = ContainerBuilder()
    builder.register(Application)
    builder.register(Dependency)

    def expensive_rule(_: ValidationContext):
        return (
            BuildIssue(
                code="example-expensive-warning",
                severity=IssueSeverity.warning,
                message="Example expensive policy warning",
            ),
        )

    builder.add_validation_rule(expensive_rule, strict_only=True)
    return builder


def strict_warning_container_factory() -> Container:
    return strict_warning_builder().build()
