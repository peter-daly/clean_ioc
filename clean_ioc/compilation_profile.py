"""Optional, bounded observations of one actual composition build.

Records contain compiler-owned labels only.  They never hold application objects.
"""

from __future__ import annotations

import json
import time
import types
from dataclasses import dataclass
from typing import Any, Callable, get_args, get_origin


def safe_definition(value: Any) -> str:
    """Use only class/function metadata, never application repr or configured values."""
    try:
        return _safe_definition(value, 0)
    except Exception:
        return "unlabelled definition"


def _safe_definition(value: Any, depth: int) -> str:
    if depth >= 8:
        return "nested type"
    origin = get_origin(value)
    if origin is not None:
        arguments = get_args(value)
        label = _safe_definition(origin, depth + 1)
        if arguments:
            label += "[" + ", ".join(_safe_definition(item, depth + 1) for item in arguments[:8])
            if len(arguments) > 8:
                label += ", …"
            label += "]"
        return label[:240]
    if isinstance(value, (type, types.FunctionType, types.BuiltinFunctionType)):
        module = getattr(value, "__module__", "")
        name = getattr(value, "__qualname__", "")
        if isinstance(module, str) and isinstance(name, str):
            return f"{module}.{name}"[:240]
    cls = type(value)
    return f"{cls.__module__}.{cls.__qualname__}"[:240]


@dataclass(frozen=True)
class CompilationSpan:
    sequence: int
    parent: int | None
    phase: str
    operation: str
    attempt: str | None
    definition: str | None
    definition_ref: str | None
    inclusive_ns: int
    self_ns: int
    state: str

    def to_dict(self) -> dict[str, Any]:
        return dict(
            sequence=self.sequence,
            parent=self.parent,
            phase=self.phase,
            operation=self.operation,
            attempt=self.attempt,
            definition=self.definition,
            definition_ref=self.definition_ref,
            inclusive_ns=self.inclusive_ns,
            self_ns=self.self_ns,
            state=self.state,
        )


@dataclass(frozen=True)
class CompilationCounters:
    values: tuple[tuple[str, int], ...]

    def to_dict(self) -> dict[str, int]:
        return dict(self.values)


@dataclass(frozen=True)
class CompilationHotspot:
    operation: str
    definition: str
    definition_ref: str | None
    samples: int
    self_ns: int
    inclusive_ns: int

    def to_dict(self) -> dict[str, Any]:
        return dict(
            operation=self.operation,
            definition=self.definition,
            definition_ref=self.definition_ref,
            samples=self.samples,
            self_ns=self.self_ns,
            inclusive_ns=self.inclusive_ns,
        )


@dataclass(frozen=True)
class CompilationProfile:
    elapsed_ns: int
    state: str
    phases_ns: tuple[tuple[str, int], ...]
    spans: tuple[CompilationSpan, ...]
    counters: CompilationCounters
    max_records: int
    omitted_records: int
    diagnostics: tuple[str, ...]

    @property
    def costly_definitions(self) -> tuple[CompilationHotspot, ...]:
        totals: dict[tuple[str, str, str | None], tuple[int, int, int]] = {}
        for span in self.spans:
            if span.definition is None:
                continue
            key = (span.operation, span.definition, span.definition_ref)
            count, self_ns, inclusive_ns = totals.get(key, (0, 0, 0))
            totals[key] = (count + 1, self_ns + span.self_ns, inclusive_ns + span.inclusive_ns)
        return tuple(
            sorted(
                (
                    CompilationHotspot(operation, definition, reference,
                                       *totals[(operation, definition, reference)])
                    for operation, definition, reference in totals
                ),
                key=lambda item: (-item.self_ns, item.operation, item.definition, item.definition_ref or ""),
            )
        )

    def to_dict(self) -> dict[str, Any]:
        return dict(
            elapsed_ns=self.elapsed_ns,
            state=self.state,
            phases_ns=dict(self.phases_ns),
            spans=[span.to_dict() for span in self.spans],
            costly_definitions=[item.to_dict() for item in self.costly_definitions],
            counters=self.counters.to_dict(),
            max_records=self.max_records,
            omitted_records=self.omitted_records,
            attribution_complete=self.omitted_records == 0 and not self.diagnostics,
            diagnostics=list(self.diagnostics),
            measurement=(
                "Instrumented elapsed wall time; imports, registration, factory setup, activation, "
                "validation-only rules and parent builds are excluded."
            ),
        )

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, sort_keys=True)

    def to_text(self) -> str:
        lines = [
            f"Compilation profile — {self.state}, {self.elapsed_ns / 1_000_000_000:.6f} s elapsed",
            "Phases (non-overlapping):",
        ]
        lines.extend(f"  {name}: {duration / 1_000_000_000:.6f} s" for name, duration in self.phases_ns)
        lines.append("Work counts:")
        lines.extend(f"  {name}: {count}" for name, count in self.counters.values)
        lines.append(
            f"Detailed spans: {len(self.spans)} retained, {self.omitted_records} omitted (limit {self.max_records})"
        )
        lines.append("Costly definitions (retained spans only):")
        for item in self.costly_definitions[:10]:
            lines.append(
                f"  {item.operation} {item.definition} [{item.definition_ref or 'unattributed'}]: "
                f"{item.samples} samples, "
                f"self {item.self_ns / 1_000_000_000:.6f} s, "
                f"inclusive {item.inclusive_ns / 1_000_000_000:.6f} s"
            )
        retries = tuple(span for span in self.spans if span.operation == "diagnostic root")
        if retries:
            lines.append("Diagnostic root attempts (retained spans only):")
            lines.extend(
                f"  {span.attempt}: {span.definition}, {span.inclusive_ns / 1_000_000_000:.6f} s [{span.state}]"
                for span in retries[:10]
            )
        if self.omitted_records:
            lines.append(
                "Hotspots are retained samples only; omitted child time remains excluded from parent self time."
            )
        lines.extend(f"Profiler diagnostic: {item}" for item in self.diagnostics)
        lines.append(
            "Instrumented elapsed wall time; excludes imports, registration, factory setup, activation, "
            "validation-only rules and parent builds."
        )
        return "\n".join(lines)


class _Frame:
    __slots__ = ("sequence", "parent", "phase", "operation", "attempt", "definition",
                 "definition_ref", "start", "child_ns", "retained")

    def __init__(
        self,
        sequence: int,
        parent: int | None,
        phase: str,
        operation: str,
        attempt: str | None,
        definition: str | None,
        definition_ref: str | None,
        start: int,
        retained: bool,
    ) -> None:
        self.sequence = sequence
        self.parent = parent
        self.phase = phase
        self.operation = operation
        self.attempt = attempt
        self.definition = definition
        self.definition_ref = definition_ref
        self.start = start
        self.child_ns = 0
        self.retained = retained


class CompilationProfiler:
    """Single-use collector. max_records bounds detailed spans; aggregate counts continue."""

    def __init__(self, max_records: int = 10_000, *, _clock: Callable[[], int] = time.perf_counter_ns) -> None:
        if isinstance(max_records, bool) or not isinstance(max_records, int) or max_records < 0:
            raise ValueError("max_records must be a non-negative integer")
        self.max_records = max_records
        self._clock = _clock
        self._started = False
        self._finished = False
        self._begin_ns = 0
        self._begin_ok = False
        self._elapsed_ns = 0
        self._state = "not started"
        self._stack: list[_Frame] = []
        self._spans: list[CompilationSpan] = []
        self._sequence = 0
        self._omitted = 0
        self._counters: dict[str, int] = {}
        self._phases: dict[str, int] = {}
        self._diagnostics: list[str] = []
        self._definition_refs: dict[str, str] = {}

    def _problem(self) -> None:
        if not self._diagnostics:
            self._diagnostics.append("Recording failed; durations or counts may be incomplete")

    def _begin(self) -> None:
        if self._started:
            raise ValueError("CompilationProfiler is single-use")
        self._started = True
        self._state = "interrupted"
        try:
            self._begin_ns = self._clock()
            self._begin_ok = True
        except Exception:
            self._problem()

    def _finish(self, state: str) -> None:
        if self._finished:
            return
        if self._begin_ok:
            try:
                now = self._clock()
                self._elapsed_ns = max(0, now - self._begin_ns)
            except Exception:
                self._problem()
        self._state = state
        self._finished = True
        self._definition_refs.clear()

    def count(self, unit: str, amount: int = 1) -> None:
        try:
            self._counters[unit] = self._counters.get(unit, 0) + amount
        except Exception:
            self._problem()

    def call(
        self,
        phase: str,
        operation: str,
        function: Callable[..., Any],
        *args: Any,
        attempt: str | None = None,
        definition: str | None = None,
        definition_key: str | None = None,
        **kwargs: Any,
    ) -> Any:
        """Measure a normal call once, preserving its return and original exception."""
        frame: _Frame | None = None
        try:
            start = self._clock()
            self._sequence += 1
            parent = self._stack[-1].sequence if self._stack else None
            retained = len(self._spans) + sum(item.retained for item in self._stack) < self.max_records
            reference = None
            if retained and definition_key is not None:
                reference = self._definition_refs.get(definition_key)
                if reference is None:
                    reference = f"definition:{len(self._definition_refs) + 1}"
                    self._definition_refs[definition_key] = reference
            frame = _Frame(self._sequence, parent, phase, operation, attempt, definition,
                           reference, start, retained)
            self._stack.append(frame)
        except Exception:
            self._problem()
            frame = None
        state = "completed"
        try:
            return function(*args, **kwargs)
        except BaseException as error:
            state = "interrupted" if not isinstance(error, Exception) else "failed"
            raise
        finally:
            if frame is not None:
                inclusive: int | None = None
                try:
                    inclusive = max(0, self._clock() - frame.start)
                except Exception:
                    self._problem()
                try:
                    self._stack.pop()
                    if inclusive is not None:
                        if self._stack:
                            self._stack[-1].child_ns += inclusive
                        if frame.operation == "phase":
                            self._phases[frame.phase] = self._phases.get(frame.phase, 0) + inclusive
                        if frame.retained:
                            self._spans.append(
                                CompilationSpan(
                                    frame.sequence,
                                    frame.parent,
                                    frame.phase,
                                    frame.operation,
                                    frame.attempt,
                                    frame.definition,
                                    frame.definition_ref,
                                    inclusive,
                                    max(0, inclusive - frame.child_ns),
                                    state,
                                )
                            )
                        else:
                            self._omitted += 1
                except Exception:
                    self._problem()

    def report(self) -> CompilationProfile:
        phases = dict(self._phases)
        if self._finished:
            phases["other build work"] = max(0, self._elapsed_ns - sum(phases.values()))
        return CompilationProfile(
            self._elapsed_ns,
            self._state,
            tuple(phases.items()),
            tuple(sorted(self._spans, key=lambda item: item.sequence)),
            CompilationCounters(tuple(sorted(self._counters.items()))),
            self.max_records,
            self._omitted,
            tuple(self._diagnostics),
        )
