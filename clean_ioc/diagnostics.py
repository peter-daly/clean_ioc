"""Static container validation and human-readable dependency plans."""

from __future__ import annotations

import inspect
from dataclasses import dataclass, field
from html import escape
from typing import Any, Iterable, cast, get_args, get_origin

from .core import (
    EMPTY,
    AsyncFactoryActivator,
    AsyncGeneratorActivator,
    CurrentGraph,
    Dependency,
    DependencyContext,
    DependencyGraph,
    DependencyNode,
    DependencySettings,
    Lifespan,
    RegistrationFilter,
    Scope,
    _Registration,
    default_parameter_value_factory,
    default_registration_filter,
)
from .value_factories import dont_use_default_value, use_default_value


def _display_type(subject: Any) -> str:
    origin = get_origin(subject)
    arguments = get_args(subject)
    if origin is not None and arguments:
        return f"{_display_type(origin)}[{', '.join(_display_type(argument) for argument in arguments)}]"
    name = getattr(subject, "__name__", None)
    if name:
        return name
    return str(subject).replace("typing.", "")


def _implementation_name(subject: Any) -> str:
    return _display_type(subject)


def _requires_async(activator_class: type, implementation: Any) -> bool:
    if activator_class in (AsyncFactoryActivator, AsyncGeneratorActivator):
        return True
    wrapped = getattr(implementation, "__wrapped__", None)
    return wrapped is not None and (inspect.iscoroutinefunction(wrapped) or inspect.isasyncgenfunction(wrapped))


@dataclass(frozen=True)
class ValidationIssue:
    """One actionable problem found while statically inspecting a dependency graph."""

    code: str
    message: str
    path: tuple[str, ...]

    def __str__(self) -> str:
        path = " -> ".join(self.path)
        return f"[{self.code}] {self.message}" + (f" ({path})" if path else "")


@dataclass(frozen=True)
class DependencyPlanNode:
    """A single registration, decorator, collection, or supplied value in a plan."""

    service_type: Any
    implementation: Any | None
    lifespan: Lifespan | None
    kind: str = "registration"
    argument: str | None = None
    registration_id: str | None = None
    registration_name: str | None = None
    children: tuple[DependencyPlanNode, ...] = field(default_factory=tuple)

    @property
    def service_name(self) -> str:
        return _display_type(self.service_type)

    @property
    def implementation_name(self) -> str | None:
        if self.implementation is None:
            return None
        return _implementation_name(self.implementation)

    def describe(self) -> str:
        prefix = f"{self.argument}: " if self.argument else ""
        service = self.service_name
        implementation = self.implementation_name
        if implementation and implementation != service:
            service = f"{service} -> {implementation}"

        details = []
        if self.lifespan is not None:
            details.append(self.lifespan.name)
        if self.registration_name is not None:
            details.append(f'name="{self.registration_name}"')
        if self.kind != "registration":
            details.append(self.kind)

        suffix = f" [{', '.join(details)}]" if details else ""
        return f"{prefix}{service}{suffix}"


@dataclass(frozen=True)
class DependencyPlan:
    """A static explanation of how Clean IoC would assemble one requested service."""

    root: DependencyPlanNode
    issues: tuple[ValidationIssue, ...] = field(default_factory=tuple)

    @property
    def is_valid(self) -> bool:
        return not self.issues

    def to_text(self) -> str:
        lines: list[str] = []

        def visit(node: DependencyPlanNode, depth: int) -> None:
            branch = "└─ " if depth else ""
            lines.append(f"{'   ' * depth}{branch}{node.describe()}")
            for child in node.children:
                visit(child, depth + 1)

        visit(self.root, 0)
        if self.issues:
            lines.append("")
            lines.append("Problems:")
            lines.extend(f"- {issue}" for issue in self.issues)
        return "\n".join(lines)

    def to_mermaid(self) -> str:
        """Render this plan as a Mermaid flowchart for docs and pull requests."""

        lines = ["flowchart TD"]
        next_id = 0

        def visit(node: DependencyPlanNode, parent_id: str | None = None) -> None:
            nonlocal next_id
            node_id = f"n{next_id}"
            next_id += 1
            label = escape(node.describe(), quote=True).replace("\n", " ")
            lines.append(f'    {node_id}["{label}"]')
            if parent_id is not None:
                lines.append(f"    {parent_id} --> {node_id}")
            for child in node.children:
                visit(child, node_id)

        visit(self.root)
        return "\n".join(lines)

    def __str__(self) -> str:
        return self.to_text()


@dataclass(frozen=True)
class ValidationReport:
    """Successful validation result returned by :meth:`Scope.validate`."""

    plans: tuple[DependencyPlan, ...]

    @property
    def is_valid(self) -> bool:
        return all(plan.is_valid for plan in self.plans)

    @property
    def checked_roots(self) -> int:
        return len(self.plans)

    def __str__(self) -> str:
        noun = "root" if self.checked_roots == 1 else "roots"
        return f"Container is valid ({self.checked_roots} {noun} checked)."


class ContainerValidationError(Exception):
    """Raised when :meth:`Scope.validate` finds one or more graph problems."""

    def __init__(self, report: ValidationReport):
        self.report = report
        self.issues = tuple(dict.fromkeys(issue for plan in report.plans for issue in plan.issues))
        super().__init__(self._build_message())

    def _build_message(self) -> str:
        count = len(self.issues)
        noun = "problem" if count == 1 else "problems"
        details = "\n".join(f"- {issue}" for issue in self.issues)
        return f"Container validation failed with {count} {noun}:\n{details}"


class _Planner:
    def __init__(self, scope: Scope, *, allow_async: bool):
        self.scope = scope
        self.allow_async = allow_async
        self.issues: list[ValidationIssue] = []

    def explain(
        self,
        service_type: type,
        registration_filter: RegistrationFilter,
    ) -> DependencyPlan:
        graph_node = DependencyNode(
            service_type=service_type,
            implementation=DependencyGraph,
            lifespan=Lifespan.once_per_graph,
        )
        dependency = Dependency(
            name="__ROOT__",
            parent_implementation=DependencyGraph,
            service_type=service_type,
            settings=DependencySettings(filter=registration_filter),
            default_value=EMPTY,
        )
        root = self._plan_dependency(
            dependency,
            graph_node,
            argument=None,
            stack=(),
            path=(),
            active_singleton=None,
        )
        return DependencyPlan(root=root, issues=tuple(self.issues))

    def explain_registration(self, registration: _Registration) -> DependencyPlan:
        graph_node = DependencyNode(
            service_type=registration.service_type,
            implementation=DependencyGraph,
            lifespan=Lifespan.once_per_graph,
        )
        root = self._plan_registration(
            registration,
            graph_node,
            argument=None,
            stack=(),
            path=(),
            active_singleton=None,
        )
        return DependencyPlan(root=root, issues=tuple(self.issues))

    def _issue(self, code: str, message: str, path: tuple[str, ...]) -> None:
        issue = ValidationIssue(code=code, message=message, path=path)
        if issue not in self.issues:
            self.issues.append(issue)

    @staticmethod
    def _dependency_is_supplied(dependency: Dependency) -> bool:
        value_factory = dependency.settings.value_factory
        if value_factory is dont_use_default_value:
            return False
        if value_factory in (default_parameter_value_factory, use_default_value):
            return dependency.default_value is not EMPTY
        return True

    def _find_registrations(self, dependency: Dependency, parent_node: DependencyNode) -> list[_Registration]:
        service_type = dependency.service_type
        registrations = self.scope.find_registrations(
            service_type=service_type,
            filter=dependency.settings.filter,
            list_modifier=dependency.settings.list_modifier,
            parent_node=parent_node,
        )
        if registrations:
            return registrations

        origin = getattr(service_type, "__origin__", None)
        if origin is not None:
            return self.scope.find_registrations(
                service_type=origin,
                filter=dependency.settings.filter,
                list_modifier=dependency.settings.list_modifier,
                parent_node=parent_node,
            )
        return []

    def _plan_dependency(
        self,
        dependency: Dependency,
        parent_node: DependencyNode,
        *,
        argument: str | None,
        stack: tuple[_Registration, ...],
        path: tuple[str, ...],
        active_singleton: _Registration | None,
    ) -> DependencyPlanNode:
        dependency_name = _display_type(dependency.service_type)
        dependency_path = (*path, dependency_name)

        if self._dependency_is_supplied(dependency):
            return DependencyPlanNode(
                service_type=dependency.service_type,
                implementation=None,
                lifespan=None,
                kind="supplied value",
                argument=argument,
            )

        if dependency.is_dependency_context:
            return DependencyPlanNode(
                service_type=DependencyContext,
                implementation=DependencyContext,
                lifespan=Lifespan.transient,
                kind="context",
                argument=argument,
            )

        if dependency.is_current_graph:
            return DependencyPlanNode(
                service_type=CurrentGraph,
                implementation=CurrentGraph,
                lifespan=Lifespan.transient,
                kind="current graph",
                argument=argument,
            )

        if dependency.generic_collection_type:
            element_type = get_args(dependency.service_type)[0]
            element_dependency = Dependency(
                name=dependency.name,
                parent_implementation=dependency.parent_implementation,
                service_type=element_type,
                settings=dependency.settings,
                default_value=EMPTY,
            )
            collection_core_node = DependencyNode(
                service_type=cast(type, dependency.service_type),
                implementation=dependency.generic_collection_type,
                lifespan=Lifespan.transient,
            )
            parent_node.add_child(collection_core_node)
            registrations = self._find_registrations(element_dependency, parent_node)
            children = tuple(
                self._plan_registration(
                    registration,
                    collection_core_node,
                    argument=None,
                    stack=stack,
                    path=dependency_path,
                    active_singleton=active_singleton,
                )
                for registration in registrations
            )
            return DependencyPlanNode(
                service_type=dependency.service_type,
                implementation=dependency.generic_collection_type,
                lifespan=Lifespan.transient,
                kind="collection",
                argument=argument,
                children=children,
            )

        registrations = self._find_registrations(dependency, parent_node)
        registration = next(iter(registrations), None)
        if registration is None:
            self._issue(
                "missing-registration",
                f"No registration can supply {dependency_name}",
                dependency_path,
            )
            return DependencyPlanNode(
                service_type=dependency.service_type,
                implementation=None,
                lifespan=None,
                kind="missing",
                argument=argument,
            )

        return self._plan_registration(
            registration,
            parent_node,
            argument=argument,
            stack=stack,
            path=path,
            active_singleton=active_singleton,
        )

    def _plan_registration(
        self,
        registration: _Registration,
        parent_node: DependencyNode,
        *,
        argument: str | None,
        stack: tuple[_Registration, ...],
        path: tuple[str, ...],
        active_singleton: _Registration | None,
    ) -> DependencyPlanNode:
        service_name = _display_type(registration.service_type)
        registration_path = (*path, service_name)

        if registration in stack:
            cycle_start = stack.index(registration)
            cycle = (*stack[cycle_start:], registration)
            labels = tuple(_display_type(item.service_type) for item in cycle)
            self._issue(
                "circular-dependency",
                f"Circular dependency detected: {' -> '.join(labels)}",
                registration_path,
            )
            return DependencyPlanNode(
                service_type=registration.service_type,
                implementation=registration.implementation,
                lifespan=registration.lifespan,
                kind="cycle",
                argument=argument,
                registration_id=registration.id,
                registration_name=registration.name,
            )

        is_safe_root_instance = registration.is_instance and registration.is_root_owned_instance
        if active_singleton is not None and registration.lifespan == Lifespan.scoped and not is_safe_root_instance:
            singleton_name = _display_type(active_singleton.service_type)
            self._issue(
                "captive-dependency",
                f"Singleton {singleton_name} cannot depend on scoped {service_name}",
                registration_path,
            )

        if not self.allow_async and (
            _requires_async(registration.activator_class, registration.implementation)
            or inspect.iscoroutinefunction(registration.scoped_teardown)
        ):
            self._issue(
                "async-required",
                f"{service_name} requires resolve_async()",
                registration_path,
            )

        current_singleton = active_singleton
        if current_singleton is None and registration.lifespan == Lifespan.singleton:
            current_singleton = registration

        core_node = DependencyNode(
            service_type=registration.service_type,
            implementation=registration.implementation,
            lifespan=registration.lifespan,
            registration_name=registration.name,
            registration_tags=registration.tags,
        )
        parent_node.add_child(core_node)
        next_stack = (*stack, registration)

        children: list[DependencyPlanNode] = []
        for pre_configuration in self.scope.find_pre_configurations(registration=registration):
            if not self.allow_async and _requires_async(
                pre_configuration.activator_class,
                pre_configuration.configuration_fn,
            ):
                self._issue(
                    "async-required",
                    "Pre-configuration "
                    f"{_implementation_name(pre_configuration.configuration_fn)} requires async resolution",
                    registration_path,
                )
            pre_core_node = DependencyNode(
                service_type=registration.service_type,
                implementation=pre_configuration.configuration_fn,
                lifespan=Lifespan.singleton,
            )
            core_node.add_pre_configuration(pre_core_node)
            pre_children = tuple(
                self._plan_dependency(
                    dependency,
                    pre_core_node,
                    argument=name,
                    stack=next_stack,
                    path=registration_path,
                    active_singleton=current_singleton,
                )
                for name, dependency in pre_configuration.dependencies.items()
            )
            children.append(
                DependencyPlanNode(
                    service_type=registration.service_type,
                    implementation=pre_configuration.configuration_fn,
                    lifespan=Lifespan.singleton,
                    kind="pre-configuration",
                    children=pre_children,
                )
            )

        children.extend(
            self._plan_dependency(
                dependency,
                core_node,
                argument=name,
                stack=next_stack,
                path=registration_path,
                active_singleton=current_singleton,
            )
            for name, dependency in registration.dependencies.items()
        )

        decorated_core_node = core_node
        for decorator in self.scope.find_decorators(
            registration=registration,
            decorated_instance_node=core_node,
        ):
            if not self.allow_async and _requires_async(decorator.activator_class, decorator.decorator_type):
                self._issue(
                    "async-required",
                    f"Decorator {_implementation_name(decorator.decorator_type)} requires async resolution",
                    registration_path,
                )
            decorator_core_node = DependencyNode(
                service_type=registration.service_type,
                implementation=decorator.decorator_type,
                lifespan=registration.lifespan,
            )
            decorated_core_node.add_decorator(decorator_core_node)
            decorator_children = tuple(
                self._plan_dependency(
                    dependency,
                    decorator_core_node,
                    argument=name,
                    stack=next_stack,
                    path=registration_path,
                    active_singleton=current_singleton,
                )
                for name, dependency in decorator.dependencies.items()
            )
            children.append(
                DependencyPlanNode(
                    service_type=registration.service_type,
                    implementation=decorator.decorator_type,
                    lifespan=registration.lifespan,
                    kind="decorator",
                    argument=decorator.decorated_arg,
                    children=decorator_children,
                )
            )
            decorated_core_node = decorator_core_node

        return DependencyPlanNode(
            service_type=registration.service_type,
            implementation=registration.implementation,
            lifespan=registration.lifespan,
            argument=argument,
            registration_id=registration.id,
            registration_name=registration.name,
            children=tuple(children),
        )


def explain(
    scope: Scope,
    service_type: type,
    registration_filter: RegistrationFilter = default_registration_filter,
    *,
    allow_async: bool = True,
) -> DependencyPlan:
    """Return a dependency plan without creating any service instances."""

    return _Planner(scope, allow_async=allow_async).explain(service_type, registration_filter)


def _iter_registrations(scope: Scope) -> Iterable[_Registration]:
    seen: set[str] = set()
    current: Scope | None = scope
    while current is not None:
        for registrations in current._registry._registrations.values():
            for registration in registrations:
                if registration.id not in seen:
                    seen.add(registration.id)
                    yield registration
        current = getattr(current, "_parent_scope", None)


def validate(
    scope: Scope,
    *service_types: type,
    allow_async: bool = True,
) -> ValidationReport:
    """Validate requested roots, or every registration when no roots are supplied.

    The check is static: factories, constructors, value providers, decorators, and
    pre-configurations are never invoked. A :class:`ContainerValidationError` contains
    every issue when validation fails.
    """

    if service_types:
        plans = tuple(explain(scope, service_type, allow_async=allow_async) for service_type in service_types)
    else:
        plans = tuple(
            _Planner(scope, allow_async=allow_async).explain_registration(registration)
            for registration in _iter_registrations(scope)
        )

    report = ValidationReport(plans=plans)
    if not report.is_valid:
        raise ContainerValidationError(report)
    return report
