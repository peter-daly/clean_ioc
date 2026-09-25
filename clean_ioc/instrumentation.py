"""Opt-in, bounded measurements of compiled runtime resolution."""

from __future__ import annotations

import json
import logging
import math
import threading
import time
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any, Literal

logger = logging.getLogger(__name__)

_TIMED: ContextVar[bool] = ContextVar("clean_ioc_resolution_timed", default=False)
_METRICS = ("request", "activation", "dependencies", "body", "wait", "cleanup", "pre_configuration", "decoration")


@dataclass(frozen=True, slots=True)
class Instrumentation:
    """Choose runtime profiling when building a container or overlay."""

    profiler: ResolutionProfiler

    def __post_init__(self) -> None:
        if not isinstance(self.profiler, ResolutionProfiler):
            raise TypeError("instrumentation.profiler must be a ResolutionProfiler")


@dataclass(frozen=True, slots=True)
class DurationSummary:
    samples: int
    sampled_total_ns: int
    maximum_ns: int
    approximate_p95_ns: int | None

    def to_dict(self) -> dict[str, int | None]:
        return {
            "samples": self.samples,
            "sampled_total_ns": self.sampled_total_ns,
            "maximum_ns": self.maximum_ns,
            "approximate_p95_ns": self.approximate_p95_ns,
        }


@dataclass(frozen=True, slots=True)
class ProfileRecord:
    graph_fingerprint: str
    path: str
    registration: str | None
    sharing_group: str | None
    kind: str
    attempts: int
    completed: int
    failed: int
    cancelled: int
    cache_hits: int
    cache_misses: int
    cache_waits: int
    durations: tuple[tuple[str, DurationSummary], ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "graph_fingerprint": self.graph_fingerprint,
            "path": self.path,
            "registration": self.registration,
            "sharing_group": self.sharing_group,
            "kind": self.kind,
            "attempts": self.attempts,
            "completed": self.completed,
            "failed": self.failed,
            "cancelled": self.cancelled,
            "cache_hits": self.cache_hits,
            "cache_misses": self.cache_misses,
            "cache_waits": self.cache_waits,
            "durations": {key: value.to_dict() for key, value in self.durations},
        }


@dataclass(frozen=True, slots=True)
class ResolutionProfile:
    """Immutable, deterministic view of completed operations at snapshot time."""

    graphs: tuple[str, ...]
    started_ns: int
    captured_ns: int
    sample_durations: float
    incomplete: bool
    dropped_updates: int
    in_flight: int
    records: tuple[ProfileRecord, ...]
    groups: tuple[ProfileRecord, ...]
    sharing_groups: tuple[ProfileRecord, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "evidence": "runtime observations",
            "graphs": list(self.graphs),
            "started_ns": self.started_ns,
            "captured_ns": self.captured_ns,
            "sample_durations": self.sample_durations,
            "incomplete": self.incomplete,
            "dropped_updates": self.dropped_updates,
            "in_flight": self.in_flight,
            "records": [record.to_dict() for record in self.records],
            "registration_groups": [record.to_dict() for record in self.groups],
            "sharing_groups": [record.to_dict() for record in self.sharing_groups],
        }

    def to_json(self, *, indent: int | None = 2) -> str:
        return json.dumps(self.to_dict(), sort_keys=True, indent=indent)

    def to_text(self) -> str:
        lines = [
            "Runtime resolution profile (observations)",
            f"Graphs: {', '.join(self.graphs)}",
            f"Duration sampling: {self.sample_durations:g}; in flight: {self.in_flight}; "
            f"incomplete: {self.incomplete}; dropped updates: {self.dropped_updates}",
        ]
        unobserved = sum(
            1
            for record in self.records
            if record.registration is not None
            and record.attempts == record.cache_hits == record.cache_misses == record.cache_waits == 0
        )
        lines.append(f"Compiled component paths not observed: {unobserved}")
        for record in self.records:
            if record.attempts == record.cache_hits == record.cache_misses == record.cache_waits == 0:
                continue
            lines.append(
                f"{record.path} [{record.kind}]: {record.attempts} attempts, "
                f"{record.completed} completed, {record.failed} failed, "
                f"{record.cache_hits} hits, {record.cache_misses} misses, {record.cache_waits} waits"
            )
            for category, summary in record.durations:
                if summary.samples:
                    lines.append(
                        f"  {category}: {summary.sampled_total_ns} ns across {summary.samples} timed samples; "
                        f"approximate p95 {summary.approximate_p95_ns} ns"
                    )
        activations = sorted(
            (record for record in self.groups if record.attempts),
            key=lambda record: (-record.attempts, record.path),
        )[:5]
        if activations:
            lines.append("Most frequent activations (exact counts):")
            lines.extend(f"  {record.path}: {record.attempts} attempts" for record in activations)
        requests = sorted(
            (record for record in self.records if record.kind == "request" and
             dict(record.durations)["request"].samples),
            key=lambda record: (-dict(record.durations)["request"].maximum_ns, record.path),
        )[:5]
        if requests:
            lines.append("Slowest sampled requests (maximum measured inclusive duration):")
            lines.extend(
                f"  {record.path}: {dict(record.durations)['request'].maximum_ns} ns maximum "
                f"across {dict(record.durations)['request'].samples} timed samples"
                for record in requests
            )
        waits = sorted(
            (record for record in self.records if dict(record.durations)["wait"].samples),
            key=lambda record: (-dict(record.durations)["wait"].sampled_total_ns, record.path),
        )[:5]
        if waits:
            lines.append("Largest measured cache-wait totals (timed samples only; wait counts exact):")
            lines.extend(
                f"  {record.path}: {dict(record.durations)['wait'].sampled_total_ns} ns "
                f"across {dict(record.durations)['wait'].samples} timed samples; "
                f"{record.cache_waits} exact waits"
                for record in waits
            )
        factories = sorted(
            (record for record in self.groups if dict(record.durations)["body"].samples),
            key=lambda record: (-dict(record.durations)["body"].sampled_total_ns, record.path),
        )[:5]
        if factories:
            lines.append("Largest measured constructor/factory body totals (timed samples only):")
            lines.extend(
                f"  {record.path}: {dict(record.durations)['body'].sampled_total_ns} ns "
                f"across {dict(record.durations)['body'].samples} samples"
                for record in factories
            )
        return "\n".join(lines)

    def ranked(
        self, by: Literal["activations", "factory_time", "slow_requests", "waits", "failures"] = "activations"
    ) -> tuple[ProfileRecord, ...]:
        """Sort records by exact counts or explicitly sampled time."""

        if by not in ("activations", "factory_time", "slow_requests", "waits", "failures"):
            raise ValueError(f"Unknown ranking: {by}")

        def score(record: ProfileRecord) -> int:
            if by == "activations":
                return record.attempts if record.kind != "request" else 0
            if by == "factory_time":
                return dict(record.durations)["body"].sampled_total_ns
            if by == "slow_requests":
                return dict(record.durations)["request"].maximum_ns if record.kind == "request" else 0
            if by == "waits":
                return record.cache_waits
            return record.failed

        return tuple(sorted(self.records, key=lambda record: (-score(record), record.graph_fingerprint, record.path)))


class _MutableRecord:
    __slots__ = (
        "attempts",
        "completed",
        "failed",
        "cancelled",
        "cache_hits",
        "cache_misses",
        "cache_waits",
        "durations",
    )

    def __init__(self) -> None:
        self.attempts = self.completed = self.failed = self.cancelled = 0
        self.cache_hits = self.cache_misses = self.cache_waits = 0
        self.durations: dict[str, list[int]] = {name: [0, 0, 0, *([0] * 64)] for name in _METRICS}


class ResolutionProfiler:
    """Thread-safe exact counters with fixed-size logarithmic duration histograms."""

    def __init__(self, *, sample_durations: float = 1.0) -> None:
        if (
            not isinstance(sample_durations, (int, float))
            or not math.isfinite(sample_durations)
            or not 0 <= sample_durations <= 1
        ):
            raise ValueError("sample_durations must be a finite number from 0 to 1")
        self.sample_durations = float(sample_durations)
        self._lock = threading.Lock()
        self._started_ns = time.time_ns()
        self._catalog: dict[tuple[str, str], tuple[str | None, str]] = {}
        self._sharing: dict[tuple[str, str], str] = {}
        self._ambiguous: dict[str, frozenset[str]] = {}
        self._bindings: dict[str, str] = {}
        self._records: dict[tuple[str, str], _MutableRecord] = {}
        self._graphs: set[str] = set()
        self._incomplete = False
        self._dropped = 0
        self._in_flight = 0
        self._sample_index = 0

    def _bind(
        self,
        fingerprint: str,
        catalog: dict[str, tuple[str | None, str]],
        sharing: dict[str, str],
        ambiguous: frozenset[str],
        binding_token: str,
    ) -> None:
        with self._lock:
            bound = self._bindings.get(fingerprint)
            if bound is not None and bound != binding_token:
                raise ValueError("resolution profiler is already bound to a different runtime with this graph")
            if bound is not None:
                existing_catalog = {path: detail for (graph, path), detail in self._catalog.items()
                                    if graph == fingerprint}
                existing_sharing = {path: reference for (graph, path), reference in self._sharing.items()
                                    if graph == fingerprint}
                if (existing_catalog != catalog or existing_sharing != sharing
                        or self._ambiguous[fingerprint] != ambiguous):
                    raise ValueError("resolution profiler has conflicting catalogs for the same graph")
            for path, detail in catalog.items():
                key = (fingerprint, path)
                self._catalog.setdefault(key, detail)
                self._records.setdefault(key, _MutableRecord())
                if path in sharing:
                    self._sharing[key] = sharing[path]
            self._graphs.add(fingerprint)
            self._ambiguous[fingerprint] = ambiguous
            self._bindings[fingerprint] = binding_token

    def _choose_timing(self) -> bool:
        if self._incomplete:
            return False
        try:
            with self._lock:
                self._sample_index += 1
                return math.floor(self._sample_index * self.sample_durations) > math.floor(
                    (self._sample_index - 1) * self.sample_durations
                )
        except Exception:
            self._disable()
            return False

    def _record(self, key: tuple[str, str], field: str, amount: int = 1) -> None:
        try:
            with self._lock:
                if self._incomplete:
                    self._dropped += 1
                    return
                setattr(self._records[key], field, getattr(self._records[key], field) + amount)
        except Exception:
            self._disable()

    def _duration(self, key: tuple[str, str], category: str, start: int | None) -> None:
        if start is None:
            return
        try:
            elapsed = max(0, time.perf_counter_ns() - start)
            with self._lock:
                if self._incomplete:
                    self._dropped += 1
                    return
                data = self._records[key].durations[category]
                data[0] += 1
                data[1] += elapsed
                data[2] = max(data[2], elapsed)
                data[3 + min(63, elapsed.bit_length())] += 1
        except Exception:
            self._disable()

    def _clock(self) -> int | None:
        if not _TIMED.get() or self._incomplete:
            return None
        try:
            return time.perf_counter_ns()
        except Exception:
            self._disable()
            return None

    def _disable(self) -> None:
        with self._lock:
            self._dropped += 1
            if not self._incomplete:
                self._incomplete = True
                logger.error("Runtime resolution profiler disabled after recording failure")

    def _safe_record(self, key: tuple[str, str], field: str, amount: int = 1) -> None:
        try:
            self._record(key, field, amount)
        except Exception:
            self._disable()

    def _safe_choose_timing(self) -> bool:
        try:
            return self._choose_timing()
        except Exception:
            self._disable()
            return False

    def _safe_clock(self) -> int | None:
        try:
            return self._clock()
        except Exception:
            self._disable()
            return None

    def _safe_duration(self, key: tuple[str, str], category: str, start: int | None) -> None:
        try:
            self._duration(key, category, start)
        except Exception:
            self._disable()

    def _safe_in_flight(self, delta: int) -> None:
        try:
            with self._lock:
                self._in_flight += delta
        except Exception:
            self._disable()

    def report(self) -> ResolutionProfile:
        with self._lock:
            if not self._graphs:
                raise RuntimeError("resolution profiler is not bound to a successfully built runtime")
            records: list[ProfileRecord] = []
            groups: dict[tuple[str, str], _MutableRecord] = {}
            sharing_groups: dict[tuple[str, str], _MutableRecord] = {}

            def snapshot(
                key: tuple[str, str],
                registration: str | None,
                sharing_group: str | None,
                kind: str,
                item: _MutableRecord,
            ) -> ProfileRecord:
                durations = []
                for name in _METRICS:
                    data = item.durations[name]
                    threshold = math.ceil(data[0] * 0.95)
                    seen = 0
                    p95 = None
                    for index, count in enumerate(data[3:]):
                        seen += count
                        if threshold and seen >= threshold:
                            p95 = 1 << index
                            break
                    durations.append((name, DurationSummary(data[0], data[1], data[2], p95)))
                return ProfileRecord(
                    key[0],
                    key[1],
                    registration,
                    sharing_group,
                    kind,
                    item.attempts,
                    item.completed,
                    item.failed,
                    item.cancelled,
                    item.cache_hits,
                    item.cache_misses,
                    item.cache_waits,
                    tuple(durations),
                )

            def merge(target: _MutableRecord, source: _MutableRecord) -> None:
                for field in (
                    "attempts",
                    "completed",
                    "failed",
                    "cancelled",
                    "cache_hits",
                    "cache_misses",
                    "cache_waits",
                ):
                    setattr(target, field, getattr(target, field) + getattr(source, field))
                for name in _METRICS:
                    source_duration = source.durations[name]
                    target_duration = target.durations[name]
                    target_duration[0] += source_duration[0]
                    target_duration[1] += source_duration[1]
                    target_duration[2] = max(target_duration[2], source_duration[2])
                    for index in range(3, len(source_duration)):
                        target_duration[index] += source_duration[index]

            for key in sorted(self._catalog):
                registration, kind = self._catalog[key]
                item = self._records[key]
                sharing_group = self._sharing.get(key)
                records.append(snapshot(key, registration, sharing_group, kind, item))
                if registration is not None and kind != "cleanup":
                    group = groups.setdefault((key[0], registration), _MutableRecord())
                    merge(group, item)
                if sharing_group is not None:
                    group = sharing_groups.setdefault((key[0], sharing_group), _MutableRecord())
                    merge(group, item)
            group_records = tuple(
                snapshot((graph, "registration " + registration), registration, None, "registration group", item)
                for (graph, registration), item in sorted(groups.items())
            )
            sharing_records = tuple(
                snapshot((graph, "sharing " + reference), None, reference, "sharing group", item)
                for (graph, reference), item in sorted(sharing_groups.items())
            )
            return ResolutionProfile(
                tuple(sorted(self._graphs)),
                self._started_ns,
                time.time_ns(),
                self.sample_durations,
                self._incomplete,
                self._dropped,
                self._in_flight,
                tuple(records),
                group_records,
                sharing_records,
            )
