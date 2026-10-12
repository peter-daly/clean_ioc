"""Local comparative observations for item 12; run with ``uv run python benchmarks/bench_resolution_profiler.py``."""

from __future__ import annotations

import gc
import statistics
import time
import tracemalloc
from contextlib import contextmanager
from typing import Any

from clean_ioc import ContainerBuilder, Instrumentation, Provider, ResolutionProfiler


class Service:
    pass


class Transient:
    pass


class Resource:
    pass


@contextmanager
def resource_factory():
    yield Resource()


def build(enabled: bool):
    builder = ContainerBuilder()
    builder.register(Service, lifespan="singleton")
    builder.register(Transient)
    builder.register(Resource, factory=resource_factory, lifespan="scoped")
    profiler = ResolutionProfiler() if enabled else None
    return builder.build(instrumentation=Instrumentation(profiler) if profiler is not None else None)


def measure(action, repetitions: int, *, rounds: int = 5) -> float:
    values = []
    for _ in range(rounds):
        gc.collect()
        started = time.perf_counter_ns()
        for _ in range(repetitions):
            action()
        values.append((time.perf_counter_ns() - started) / repetitions)
    return statistics.median(values)


def allocated(action, repetitions: int) -> float:
    gc.collect()
    tracemalloc.start()
    before, _ = tracemalloc.get_traced_memory()
    for _ in range(repetitions):
        action()
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    return max(0, peak - before) / repetitions


def run() -> None:
    print("Median nanoseconds per operation, five local rounds; observations vary with machine load")
    cases: list[tuple[str, int, Any, Any]] = []
    plain = build(False)
    observed = build(True)
    plain.resolve(Service)
    observed.resolve(Service)
    plain_provider = plain.resolve(Provider[Service])
    observed_provider = observed.resolve(Provider[Service])
    cases.append(("build", 100, lambda: build(False), lambda: build(True)))
    cases.append(
        ("cold transient resolve", 10_000, lambda: plain.resolve(Transient), lambda: observed.resolve(Transient))
    )
    cases.append(("cached singleton hit", 10_000, lambda: plain.resolve(Service), lambda: observed.resolve(Service)))
    plain_scope = plain.new_scope()
    observed_scope = observed.new_scope()
    plain_scope.resolve(Resource)
    observed_scope.resolve(Resource)
    cases.append(
        ("cached scoped hit", 10_000, lambda: plain_scope.resolve(Resource), lambda: observed_scope.resolve(Resource))
    )
    cases.append(("provider call", 10_000, plain_provider, observed_provider))
    cases.append(("new scope", 10_000, plain.new_scope, observed.new_scope))

    def cold(container):
        scope = container.new_scope()
        scope.resolve(Resource)
        scope._close()

    cases.append(("cold scoped acquire and cleanup", 1_000, lambda: cold(plain), lambda: cold(observed)))

    def prepared(container):
        scopes = []
        for _ in range(1_000):
            scope = container.new_scope()
            scope.resolve(Resource)
            scopes.append(scope)
        return scopes

    for label, repetitions, baseline, instrumented in cases:
        baseline_ns = measure(baseline, repetitions)
        enabled_ns = measure(instrumented, repetitions)
        print(
            f"{label}: disabled {baseline_ns:,.0f} ns; enabled {enabled_ns:,.0f} ns; "
            f"ratio {enabled_ns / baseline_ns:.2f}x"
        )
    plain_scope._close()
    observed_scope._close()

    plain_cold_scopes = [plain.new_scope() for _ in range(1_000)]
    observed_cold_scopes = [observed.new_scope() for _ in range(1_000)]
    plain_cold_iter = iter(plain_cold_scopes)
    observed_cold_iter = iter(observed_cold_scopes)
    baseline_ns = measure(lambda: next(plain_cold_iter).resolve(Resource), 200, rounds=5)
    enabled_ns = measure(lambda: next(observed_cold_iter).resolve(Resource), 200, rounds=5)
    print(
        f"cold scoped acquisition: disabled {baseline_ns:,.0f} ns; enabled {enabled_ns:,.0f} ns; "
        f"ratio {enabled_ns / baseline_ns:.2f}x"
    )
    for scope in plain_cold_scopes:
        scope._close()
    for scope in observed_cold_scopes:
        scope._close()
    plain_scopes = prepared(plain)
    observed_scopes = prepared(observed)
    plain_iter = iter(plain_scopes)
    observed_iter = iter(observed_scopes)
    baseline_ns = measure(lambda: next(plain_iter)._close(), 200, rounds=5)
    enabled_ns = measure(lambda: next(observed_iter)._close(), 200, rounds=5)
    print(
        f"prepared scope cleanup: disabled {baseline_ns:,.0f} ns; enabled {enabled_ns:,.0f} ns; "
        f"ratio {enabled_ns / baseline_ns:.2f}x"
    )
    print("Approximate peak traced bytes per operation over 1,000 calls (includes measurement noise):")
    print(
        f"cached hit: disabled {allocated(lambda: plain.resolve(Service), 1_000):,.1f}; "
        f"enabled {allocated(lambda: observed.resolve(Service), 1_000):,.1f}"
    )
    print(
        f"new scope: disabled {allocated(plain.new_scope, 1_000):,.1f}; "
        f"enabled {allocated(observed.new_scope, 1_000):,.1f}"
    )


if __name__ == "__main__":
    run()
