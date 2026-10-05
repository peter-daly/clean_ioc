"""Deterministic, optional limits on work admitted by one composition build."""

from __future__ import annotations

from dataclasses import dataclass, fields
from typing import Any, Callable, cast


@dataclass(frozen=True, slots=True)
class CompilationBudget:
    """Per-build operation limits; ``None`` is unlimited and zero forbids work.

    Limits count admitted operation starts, including operations that fail.
    Depth is a maximum active component parent path, including synthetic paths.
    See the compilation-budget guide for the exact operation boundaries.
    """

    graph_occurrences: int | None = None
    active_dependency_depth: int | None = None
    specialization_materializations: int | None = None
    generated_template_outputs: int | None = None
    diagnostic_attempts: int | None = None
    preparation_operations: int | None = None

    def __post_init__(self) -> None:
        for definition in fields(self):
            value = getattr(self, definition.name)
            if value is not None and (type(value) is not int or value < 0):  # noqa: E721 -- exact builtin integers only
                raise ValueError(f"{definition.name} must be a non-negative integer or None")


@dataclass(frozen=True, slots=True)
class CompilationBudgetExhaustion:
    """Safe immutable facts about a refused compiler operation."""

    kind: str
    maximum: int
    admitted: int
    attempted: int
    phase: str
    usage: tuple[tuple[str, int], ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "maximum": self.maximum,
            "admitted": self.admitted,
            "attempted": self.attempted,
            "phase": self.phase,
            "usage": dict(self.usage),
        }


class _BudgetStop(BaseException):
    """Internal control flow: ordinary callback error wrappers cannot erase it."""

    def __init__(self, fact: CompilationBudgetExhaustion, path: tuple[str, ...], origin: Any):
        self.fact = fact
        self.path = path
        self.origin = origin
        self.compiler: Any = None
        self.original: BaseException | None = None
        self.issues: list[Any] = []
        self.evidence: list[Any] = []
        self.attempts: list[Any] = []
        self.total_roots = 0
        super().__init__("Compilation allowance exhausted")


class _BudgetState:
    def __init__(self, budget: CompilationBudget):
        # Normalize subclass inputs into this exact immutable public configuration.
        self.budget = CompilationBudget(
            **{definition.name: getattr(budget, definition.name) for definition in fields(CompilationBudget)}
        )
        self.usage = {definition.name: 0 for definition in fields(CompilationBudget)}
        self.exhaustion: _BudgetStop | None = None
        self.primary: Any = None
        self.compilation_attempts = 0
        self.findings: list[Any] = []
        self.preparation_findings: list[Any] = []
        self.finding_evidence: dict[int, Any] = {}
        self.callback_errors: set[int] = set()

    def check(self) -> None:
        if self.exhaustion is not None:
            raise self.exhaustion

    def admit(
        self,
        kind: str,
        phase: str,
        *,
        path: tuple[str, ...] | Callable[[], tuple[str, ...]] = (),
        origin: Any = None,
        compiler: Any = None,
        depth: int | None = None,
    ) -> None:
        self.check()
        current = self.usage[kind]
        attempted = current + 1 if depth is None else depth
        maximum = getattr(self.budget, kind)
        if maximum is not None and attempted > maximum:
            self.exhaustion = _BudgetStop(
                CompilationBudgetExhaustion(kind, maximum, current, attempted, phase, tuple(self.usage.items())),
                cast(tuple[str, ...], path) if isinstance(path, tuple) else cast(Callable[[], tuple[str, ...]], path)(),
                origin,
            )
            self.exhaustion.compiler = compiler
            raise self.exhaustion
        self.usage[kind] = attempted if depth is None else max(current, depth)

    def occurrence(
        self,
        phase: str,
        *,
        depth: int,
        path: tuple[str, ...] | Callable[[], tuple[str, ...]],
        origin: Any = None,
        compiler: Any = None,
    ) -> None:
        # Both limits preflight the same operation before either count advances.
        previous_depth = self.usage["active_dependency_depth"]
        self.admit("active_dependency_depth", phase, depth=depth, path=path, origin=origin, compiler=compiler)
        try:
            self.admit("graph_occurrences", phase, path=path, origin=origin, compiler=compiler)
        except _BudgetStop as stop:
            self.usage["active_dependency_depth"] = previous_depth
            fact = stop.fact
            stop.fact = CompilationBudgetExhaustion(
                fact.kind, fact.maximum, fact.admitted, fact.attempted, fact.phase, tuple(self.usage.items())
            )
            raise

    def output(self, phase: str, *, path: tuple[str, ...], origin: Any) -> None:
        previous = self.usage["generated_template_outputs"]
        self.admit("generated_template_outputs", phase, path=path, origin=origin)
        try:
            self.admit("preparation_operations", phase, path=path, origin=origin)
        except _BudgetStop as stop:
            self.usage["generated_template_outputs"] = previous
            fact = stop.fact
            stop.fact = CompilationBudgetExhaustion(
                fact.kind, fact.maximum, fact.admitted, fact.attempted, fact.phase, tuple(self.usage.items())
            )
            raise
