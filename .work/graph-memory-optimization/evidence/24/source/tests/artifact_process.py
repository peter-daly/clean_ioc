"""Correctness-only process driver for the parked, private artifact experiment."""

import asyncio
import hashlib
import json
import os
import sys
from pathlib import Path

from benchmarks import graph_artifact_fixture as small
from benchmarks import graph_memory_fixture as rich
from benchmarks.graph_artifact import dump_graph, load_graph
from clean_ioc import ContainerBuilder, _legacy, container


def forbidden(*args, **kwargs):
    raise AssertionError("Loading must not compile, inspect constructors, or expand templates")


async def main():
    mode, scenario, target = sys.argv[1:]
    path = Path(target)
    if mode == "export":
        case = rich.build(2) if scenario == "rich" else None
        runtime = case.runtime if case is not None else small.build(2)
        dump_graph(runtime, path)
    else:
        ContainerBuilder.build = forbidden
        container._Compiler.__init__ = forbidden
        setattr(_legacy, "_set_up_dependencies", forbidden)
        _legacy._Registration.__init__ = forbidden
        for name in ("dependency_for", "worker_for", "worker_decorator_for", "endpoint_decorator_for"):
            setattr(rich, name, forbidden)
        runtime = load_graph(path)
        case = rich.Fixture(runtime, {}, {}, {}) if scenario == "rich" else None
    callbacks = dict(rich.TEMPLATE_CALLS)
    async with runtime:
        catalogue = [
            (r.service_type.__qualname__, r.name, r.implementation_type.__qualname__ if r.implementation_type else None)
            for r in runtime.selected_registrations
        ]
        if case is not None:
            case.source_ids = {
                r.name: r.id
                for r in runtime.selected_registrations
                if r.service_type is rich.RouteSource and r.name is not None
            }
            held = await rich.resolve_workload(case)
            try:
                # Source IDs belong to the serialized catalogue; discover them without callbacks.
                case.source_ids = {
                    r.name: r.id
                    for r in runtime.selected_registrations
                    if r.service_type is rich.RouteSource and r.name is not None
                }
                validated = rich.validate(case, held)
            finally:
                await held.scope.__aexit__(None, None, None)
            activations = dict(rich.ACTIVATIONS)
        else:
            validated = small.inspect_instances([runtime.resolve(root) for root in small.ROOTS[:2]])
            activations = small.ACTIVATIONS
        print(
            json.dumps(
                {
                    "pid": os.getpid(),
                    "artifact_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                    "catalogue": catalogue,
                    "records": len(runtime._plan.graph._records or {}),
                    "validated": validated,
                    "activations": activations,
                    "template_calls": callbacks,
                    "compilation_disabled": mode == "load",
                },
                sort_keys=True,
            )
        )


if __name__ == "__main__":
    asyncio.run(main())
