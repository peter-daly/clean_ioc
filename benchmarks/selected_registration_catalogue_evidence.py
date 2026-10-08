"""Fresh-process installed-wheel evidence for selected route discovery metadata."""

import argparse
import gc
import hashlib
import json
import platform
import resource
import sys
import time
import tracemalloc
import types
from pathlib import Path

import clean_ioc
from clean_ioc import ContainerBuilder


def source_fingerprint(package):
    root = Path(package.__file__).parent
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*.py")):
        digest.update(str(path.relative_to(root)).encode())
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def builder_for(count):
    from bark_core.application import (  # ty: ignore[unresolved-import]
        Saga,
        SagaFindingConfigurer,
        SagaState,
        SagaStorage,
    )
    from bark_core.bundles import (  # ty: ignore[unresolved-import]
        RegisterCommandDispatcherBundle,
        RegisterEventDispatcherBundle,
        RegisterQueryDispatcherBundle,
        RegisterQueryResultDispatcherBundle,
        RegisterReplyDispatcherBundle,
        RegisterSagaBundle,
    )
    from bark_core.domain import Command, Event, Query, QueryResult, Reply  # ty: ignore[unresolved-import]
    from bark_core.messaging import messaging_type  # ty: ignore[unresolved-import]

    class State(SagaState):
        key: str = ""

    builder = ContainerBuilder()
    # Compilation never invokes storage, handlers, or sagas.
    builder.register(SagaStorage[State], instance=object())
    for bundle in (
        RegisterCommandDispatcherBundle,
        RegisterQueryDispatcherBundle,
        RegisterEventDispatcherBundle,
        RegisterReplyDispatcherBundle,
        RegisterQueryResultDispatcherBundle,
    ):
        builder.apply_bundle(bundle())
    retained_types = []
    for index in range(count):
        result = type(f"Result{index}", (QueryResult,), {"__annotations__": {"key": str}, "key": "sample"})
        command = messaging_type(name_override=f"command-{index}")(
            type(f"Command{index}", (Command,), {"__annotations__": {"key": str}, "key": "sample"})
        )
        reply = messaging_type(name_override=f"reply-{index}")(
            type(f"Reply{index}", (Reply,), {"__annotations__": {"key": str}, "key": "sample"})
        )
        event = type(f"Event{index}", (Event,), {"__annotations__": {"key": str}, "key": "sample"})
        query = types.new_class(
            f"Query{index}", (Query[result],), {}, lambda ns: ns.update(__annotations__={"key": str}, key="sample")
        )
        operations = (command, query, event, reply, result)
        retained_types.extend(operations)

        def saga_for(operations, label):
            def configure(cls, mapper: SagaFindingConfigurer[State]):
                for operation in operations:
                    mapper.on(operation).match("key", "key").starts_new_saga()

            def namespace(ns):
                ns.update(__module__=__name__, configure_how_to_find_saga=classmethod(configure))
                for family, operation in zip(("command", "query", "event", "reply", "result"), operations, strict=True):

                    async def handle(self, message):
                        raise AssertionError("Build/discovery must not activate sagas")

                    handle.__name__ = f"handle_{family}"
                    handle.__annotations__ = {
                        "message": operation,
                        "return": operations[-1] if family == "query" else None,
                    }
                    ns[handle.__name__] = handle

            return types.new_class(f"Saga{label}", (Saga[State],), {}, namespace)

        for saga_index in range(2):
            builder.apply_bundle(
                RegisterSagaBundle(saga_for(operations, f"{index}_{saga_index}"), autoregister_storage=False)
            )
    return builder, retained_types


def main():
    import bark_core  # ty: ignore[unresolved-import]
    from bark_core.application.commands.messaging import (  # ty: ignore[unresolved-import]
        create_command_consumer_registry,
        create_reply_consumer_registry,
    )
    from bark_core.application.compiled_dispatchers import (  # ty: ignore[unresolved-import]
        _CommandRoute,
        _EventRoute,
        _QueryResultRoute,
        _QueryRoute,
        _ReplyRoute,
    )

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--routes", type=int, default=8)
    parser.add_argument("--heap", action="store_true")
    args = parser.parse_args()
    builder, retained_types = builder_for(args.routes)
    gc.collect()
    if args.heap:
        tracemalloc.start()
    started = time.monotonic()
    container = builder.build(provider_roots=())
    seconds = time.monotonic() - started
    route_types = (_CommandRoute, _QueryRoute, _EventRoute, _ReplyRoute, _QueryResultRoute)
    catalogue = getattr(container, "selected_registrations", ())
    result = {
        "python": platform.python_version(),
        "platform": platform.platform(),
        "routes_per_family": args.routes,
        "sagas": 2 * args.routes,
        "message_types": len(retained_types),
        "diagnostics": False,
        "provider_roots": [],
        "instrumentation": "tracemalloc" if args.heap else "none",
        "seconds": seconds,
        "peak_rss_bytes": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        * (1 if sys.platform == "darwin" else 1024),
        "physical_records": len(container._plan.graph._records or ()),
        "provider_view_contexts": len(container._plan.graph._views),
        "public_roots": len(container.components),
        "public_route_roots": sum(component.service_type in route_types for component in container.components),
        "catalogue_entries": len(catalogue),
        "catalogue_route_entries": sum(item.service_type in route_types for item in catalogue),
        "catalogue_shallow_bytes": sys.getsizeof(catalogue) + sum(sys.getsizeof(item) for item in catalogue),
    }
    if args.heap:
        gc.collect()
        retained, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        result.update(traced_retained_bytes=retained, traced_peak_bytes=peak)
    commands = create_command_consumer_registry(container).command_types
    replies = create_reply_consumer_registry(container).reply_types
    if len(commands) != args.routes or len(replies) != args.routes:
        raise RuntimeError("Consumer discovery differed from selected routes")
    result.update(command_consumers=len(commands), reply_consumers=len(replies))
    result["clean_source_fingerprint"] = source_fingerprint(clean_ioc)
    result["bark_source_fingerprint"] = source_fingerprint(bark_core)
    print(json.dumps(result, sort_keys=True))
    container.__exit__()


if __name__ == "__main__":
    main()
