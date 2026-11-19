"""Focused ordinary-build/scope/resolution cost probe; run from repository root."""

import gc
import json
import statistics
import timeit

from clean_ioc import ContainerBuilder


class Value:
    pass


class Consumer:
    def __init__(self, value: Value):
        self.value = value


def build(slots=False):
    builder = ContainerBuilder()
    if slots:
        builder.declare_scope_slot(Value)
    else:
        builder.register(Value, lifespan="singleton")
    builder.register(Consumer)
    return builder.build()


def measure(action, number):
    samples = timeit.repeat(action, repeat=7, number=number)
    return {
        "median_us": statistics.median(samples) * 1e6 / number,
        "min_us": min(samples) * 1e6 / number,
        "max_us": max(samples) * 1e6 / number,
    }


def main():
    gc.collect()
    runtime = build()
    scoped = build(True)
    scoped.provide(Value, Value())
    runtime.resolve(Consumer)
    scoped.resolve(Consumer)
    print(
        json.dumps(
            {
                "build_no_slots": measure(build, 100),
                "build_scoped_slot": measure(lambda: build(True), 100),
                "new_scope_no_slots": measure(runtime.new_scope, 10000),
                "resolve_no_slots": measure(lambda: runtime.resolve(Consumer), 10000),
                "resolve_scoped_slot": measure(lambda: scoped.resolve(Consumer), 10000),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
