"""Static activation reports over a frozen :class:`CompiledGraph`.

The reports in this module deliberately describe the compiler's plan, rather
than a live scope.  They never inspect a cache or execute application code.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Any

from .components import Component, ComponentActivation, ComponentKind

if TYPE_CHECKING:
    from .tooling import CompiledGraph


class ActivationScenario(str, Enum):
    """Named cache assumptions used by :meth:`CompiledGraph.activation_report`."""

    cold = "cold"
    warm_singletons = "warm_singletons"
    warm_scope = "warm_scope"


@dataclass(frozen=True, slots=True)
class ActivationObligation:
    """One static requirement or possible operation with a witness path."""

    kind: str
    component: str
    path: str
    phase: str
    description: str
    async_required: bool = False
    cache_owner: str | None = None
    cleanup_owner: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "kind": self.kind,
            "component": self.component,
            "path": self.path,
            "phase": self.phase,
            "description": self.description,
            "async_required": self.async_required,
            "cache_owner": self.cache_owner,
            "cleanup_owner": self.cleanup_owner,
        }


@dataclass(frozen=True, slots=True)
class ExecutionRelationship:
    """A plan relationship; ``ordering`` is intentionally not a total order."""

    source: str
    target: str
    kind: str
    phase: str
    ordering: str

    def to_dict(self) -> dict[str, str]:
        return {
            "source": self.source,
            "target": self.target,
            "kind": self.kind,
            "phase": self.phase,
            "ordering": self.ordering,
        }


@dataclass(frozen=True, slots=True)
class ActivationReport:
    """A value-free, activation-free projection of one compiled root plan."""

    root: str
    root_path: str
    scenario: ActivationScenario
    assumptions: tuple[str, ...]
    immediate_obligations: tuple[ActivationObligation, ...]
    deferred_obligations: tuple[ActivationObligation, ...]
    async_causes: tuple[ActivationObligation, ...]
    potential_acquisitions: tuple[ActivationObligation, ...]
    execution_relationships: tuple[ExecutionRelationship, ...]
    cleanup_owners: tuple[ActivationObligation, ...]
    unknown_runtime_work: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "root": self.root,
            "root_path": self.root_path,
            "scenario": self.scenario.value,
            "assumptions": list(self.assumptions),
            "immediate_obligations": [item.to_dict() for item in self.immediate_obligations],
            "deferred_obligations": [item.to_dict() for item in self.deferred_obligations],
            "async_causes": [item.to_dict() for item in self.async_causes],
            "potential_acquisitions": [item.to_dict() for item in self.potential_acquisitions],
            "execution_relationships": [item.to_dict() for item in self.execution_relationships],
            "cleanup_owners": [item.to_dict() for item in self.cleanup_owners],
            "unknown_runtime_work": list(self.unknown_runtime_work),
        }

    def to_json(self, *, indent: int | None = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, sort_keys=True)

    def to_text(self) -> str:
        lines = [f"Activation report: {self.root}", f"Scenario: {self.scenario.value}"]
        lines.extend(f"Assumption: {item}" for item in self.assumptions)
        for title, values in (
            ("Immediate obligations", self.immediate_obligations),
            ("Deferred obligations", self.deferred_obligations),
            ("Async causes", self.async_causes),
            ("Potential acquisitions", self.potential_acquisitions),
            ("Cleanup owners", self.cleanup_owners),
        ):
            lines.append(f"{title}:")
            lines.extend(f"- {item.component}: {item.description} ({item.path})" for item in values)
            if not values:
                lines.append("- none")
        if self.unknown_runtime_work:
            lines.append("Unknown runtime work:")
            lines.extend(f"- {item}" for item in self.unknown_runtime_work)
        return "\n".join(lines)

    def to_mermaid(self) -> str:
        lines = ["flowchart TD"]
        ids: dict[str, str] = {self.root_path: "n0"}
        lines.append(f'    n0["{self.root}"]')
        for relationship in self.execution_relationships:
            source = ids.setdefault(relationship.source, f"n{len(ids)}")
            target = ids.setdefault(relationship.target, f"n{len(ids)}")
            if relationship.source != self.root_path:
                lines.append(f'    {source}["{relationship.source.rsplit("/", 1)[-1]}"]')
            lines.append(f'    {target}["{relationship.target.rsplit("/", 1)[-1]}"]')
            arrow = "-.->" if relationship.phase == "deferred" else "-->"
            lines.append(f"    {source} {arrow}|{relationship.kind}| {target}")
        return "\n".join(dict.fromkeys(lines))


def _name(component: Component) -> str:
    from .tooling import qualified_name

    return qualified_name(component.service_type)


def _assumptions(scenario: ActivationScenario) -> tuple[str, ...]:
    base = ("Static analysis only; it does not inspect runtime cache or provision state.",)
    if scenario is ActivationScenario.cold:
        return (*base, "Relevant caches and shared pre-configurations are assumed incomplete.")
    if scenario is ActivationScenario.warm_singletons:
        return (
            *base,
            "Relevant singleton caches and shared pre-configurations are assumed complete; scoped caches are cold.",
        )
    return (*base, "Relevant singleton and scoped caches and shared pre-configurations are assumed complete.")


def activation_report(
    graph: CompiledGraph, subject: Component | Any, *, scenario: str | ActivationScenario = "cold"
) -> ActivationReport:
    """Return a report for one exact occurrence or unambiguous compiled root.

    Type selection uses only frozen roots and never re-evaluates component
    filters.  Collection roots must be selected by passing the exact root
    occurrence, avoiding a misleading collapse of multiple members.
    """

    try:
        selected_scenario = ActivationScenario(scenario)
    except ValueError as error:
        choices = ", ".join(item.value for item in ActivationScenario)
        raise ValueError(f"activation-invalid-scenario: choose one of {choices}") from error
    if isinstance(subject, Component):
        root = subject
        root_path = "/".join(graph._path_for_component(root))
    else:
        matches = [root for root in graph.roots if root.requested_type == subject and root.component.name is None]
        if not matches:
            raise ValueError(f"activation-service-not-found: {_name_for(subject)} is not an unambiguous compiled root")
        if len(matches) != 1:
            raise ValueError(f"activation-ambiguous-root: {_name_for(subject)} matches {len(matches)} compiled roots")
        root = matches[0].component
        root_path = next(
            path
            for path, item in graph._component_paths(all_roots=True).items()
            if item.occurrence_id == root.occurrence_id
        )

    immediate: list[ActivationObligation] = []
    deferred: list[ActivationObligation] = []
    async_causes: list[ActivationObligation] = []
    acquisitions: list[ActivationObligation] = []
    cleanup: list[ActivationObligation] = []
    relationships: list[ExecutionRelationship] = []
    unknown: list[str] = []

    def obligation(component: Component, path: str, phase: str, kind: str, description: str) -> ActivationObligation:
        return ActivationObligation(
            kind,
            _name(component),
            path,
            phase,
            description,
            component.requires_async,
            component.cache_owner.value,
            component.cleanup_owner.value,
        )

    def cache_hit(component: Component) -> bool:
        return (
            selected_scenario is ActivationScenario.warm_singletons and component.cache_owner.value == "singleton"
        ) or (
            selected_scenario is ActivationScenario.warm_scope and component.cache_owner.value in {"singleton", "scope"}
        )

    def visit(component: Component, path: str, phase: str) -> None:
        if component.kind is ComponentKind.provider:
            # Provider acquisition is immediate; its target has a separate context.
            immediate.append(
                obligation(
                    component,
                    path,
                    "eager",
                    "provider",
                    "Acquire a provider handle; invoking its target is deferred",
                )
            )
            for index, child in enumerate(component.dependencies):
                child_path = f"{path}/dependency:{child.argument or index}:{index}"
                relationships.append(
                    ExecutionRelationship(path, child_path, "provider-target", "deferred", "on demand")
                )
                visit(child, child_path, "deferred")
            return
        if component.kind is ComponentKind.scope_slot:
            target = deferred if phase == "deferred" else immediate
            target.append(
                obligation(
                    component,
                    path,
                    phase,
                    "scope_slot",
                    "A matching value must be supplied by the active scope",
                )
            )
            return
        if component.kind is ComponentKind.runtime_context:
            unknown.append(f"{path}: runtime context can perform declared or unrestricted resolution at runtime")
        if component.requires_async:
            async_causes.append(
                obligation(
                    component,
                    path,
                    phase,
                    "async",
                    "This compiled operation requires asynchronous activation",
                )
            )
        if component.activation in (ComponentActivation.constructor, ComponentActivation.factory) and not cache_hit(
            component
        ):
            acquisitions.append(
                obligation(
                    component,
                    path,
                    phase,
                    "construction",
                    "May construct or invoke the registered factory",
                )
            )
        if component.manages_cleanup:
            cleanup.append(
                obligation(
                    component,
                    path,
                    phase,
                    "resource",
                    "Cleanup is retained by the compiled cleanup owner",
                )
            )
        if cache_hit(component):
            return
        for index, configuration in enumerate(component.pre_configurations):
            child_path = f"{path}/pre_configuration:{index}"
            relationships.append(
                ExecutionRelationship(path, child_path, "pre-configuration", phase, "before core activation")
            )
            visit(configuration, child_path, phase)
        for index, child in enumerate(component.dependencies):
            child_path = f"{path}/dependency:{child.argument or index}:{index}"
            ordering = (
                "potentially concurrent collection member"
                if component.kind is ComponentKind.collection
                else "before core activation"
            )
            relationships.append(ExecutionRelationship(path, child_path, "dependency", phase, ordering))
            visit(child, child_path, phase)
        for index, decorator in enumerate(component.decorators):
            child_path = f"{path}/decorator:{index}"
            relationships.append(ExecutionRelationship(path, child_path, "decorator", phase, "after core activation"))
            visit(decorator, child_path, phase)

    visit(root, root_path, "eager")
    return ActivationReport(
        _name(root),
        root_path,
        selected_scenario,
        _assumptions(selected_scenario),
        tuple(immediate),
        tuple(deferred),
        tuple(async_causes),
        tuple(acquisitions),
        tuple(relationships),
        tuple(cleanup),
        tuple(dict.fromkeys(unknown)),
    )


def _name_for(value: Any) -> str:
    from .tooling import qualified_name

    return qualified_name(value)
