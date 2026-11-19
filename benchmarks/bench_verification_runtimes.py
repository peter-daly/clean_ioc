"""Measure verification runtime cleanup and retained Python allocations."""

import gc
import json
import tracemalloc
import weakref

from benchbro import Case

from clean_ioc import ContainerBuilder

case = Case(name="verification_runtime_lifetimes", gc_control="inherit")


class Payload:
    def __init__(self):
        self.data = bytearray(1024 * 1024)


@case.benchmark()
def empty_verification_runtimes():
    with ContainerBuilder().verify() as report:
        for _ in range(200):
            with report.create_runtime():
                pass


@case.benchmark()
def normal_build_and_scopes():
    builder = ContainerBuilder().set_provider_roots(())
    builder.register(Payload)
    with builder.build() as container:
        for _ in range(200):
            with container.new_scope():
                pass


def retained_payloads() -> dict[str, int]:
    builder = ContainerBuilder().set_provider_roots(())
    builder.register(Payload, lifespan="singleton")
    report = builder.verify()
    payloads = []
    gc.collect()
    tracemalloc.start()
    try:
        for _ in range(20):
            with report.create_runtime() as runtime:
                payloads.append(weakref.ref(runtime.resolve(Payload)))
        del runtime
        gc.collect()
        retained_open, peak = tracemalloc.get_traced_memory()
        payloads_open = sum(ref() is not None for ref in payloads)
        report.close()
        gc.collect()
        retained_closed, _ = tracemalloc.get_traced_memory()
        return {
            "retained_with_open_report_bytes": retained_open,
            "peak_through_runtime_closes_bytes": peak,
            "payloads_with_open_report": payloads_open,
            "retained_with_closed_report_bytes": retained_closed,
            "payloads_with_closed_report": sum(ref() is not None for ref in payloads),
        }
    finally:
        tracemalloc.stop()
        report.close()


if __name__ == "__main__":
    print(json.dumps([retained_payloads() for _ in range(5)], indent=2))
