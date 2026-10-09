"""Fresh-process compiler growth probe; counts and timings are separate modes.

Example: uv run python -m benchmarks.compiler_memory_evidence chain --size 32 --profile
Compare a baseline checkout by running the same saved file with that checkout's
PYTHONPATH and interpreter. Never compare profiled timings to normal build times.
"""

import argparse
import json
import platform
import resource
import sys
import time
from dataclasses import fields, is_dataclass

from clean_ioc import CompilationProfiler, ContainerBuilder
from clean_ioc import component_filters as cf
from clean_ioc.container import _RegistrationStep, _Step


def dependent(name, argument, annotation, base=object):
    def init(self, value):
        setattr(self, argument, value)

    init.__annotations__ = {"value": annotation}
    return type(name, (base,), {"__init__": init})


def declarations(shape, size, early):
    builder = ContainerBuilder()
    leaf = type("Leaf", (), {})
    if shape == "small-chain":
        middle = dependent("Middle", "leaf", leaf)
        root = dependent("Root", "middle", middle)
        for service in (leaf, middle, root):
            builder.register(service)
        return builder
    if shape == "two-transports":
        transport = type("Transport", (), {})
        sqs_client, http_client = type("SqsClient", (), {}), type("HttpClient", (), {})
        sqs = dependent("SqsTransport", "client", sqs_client, transport)
        http = dependent("HttpTransport", "client", http_client, transport)
        queue = dependent("QueueSender", "transport", transport)
        webhook = dependent("WebhookSender", "transport", transport)
        queue_id, webhook_id = builder.register(queue), builder.register(webhook)
        builder.register(sqs_client, root_policy="dependency_only")
        builder.register(http_client, root_policy="dependency_only")
        for implementation, parent in ((sqs, queue_id), (http, webhook_id)):
            builder.register(
                transport, implementation, when=cf.parent(cf.with_id(parent)), root_policy="dependency_only"
            )
        return builder
    builder.register(leaf, root_policy="dependency_only")
    previous = leaf
    if shape == "chain":
        for index in range(size):
            service = dependent(f"Node{index}", "child", previous)
            builder.register(service, root_policy="resolvable" if index == size - 1 else "dependency_only")
            previous = service
        return builder
    for index in range(3):
        service = dependent(f"Infrastructure{index}", "child", previous)
        builder.register(service, root_policy="dependency_only")
        previous = service
    if shape == "routes":
        for index in range(size):
            builder.register(dependent(f"Route{index}", "infrastructure", previous))
        return builder
    transport = type("Transport", (), {})
    for index in range(size):
        sender_id = builder.register(dependent(f"Sender{index}", "transport", transport))
        implementation = dependent(f"Transport{index}", "infrastructure", previous, transport)
        builder.register(
            transport,
            implementation,
            root_policy="dependency_only",
            **{
                "candidate_when" if early else "when": cf.parent(cf.with_id(sender_id)),
            },
        )
    return builder


def retained_templates(owner):
    pending = [root for roots in (*owner._plan.roots.values(), *owner._plan.provider_roots.values()) for root in roots]
    seen = set()
    registrations = 0
    steps = 0
    links = {
        "step",
        "target",
        "inner",
        "dependencies",
        "pre_configurations",
        "decorators",
        "members",
        "resolution_requests",
        "targets",
        "plans",
    }
    while pending:
        value = pending.pop()
        if id(value) in seen:
            continue
        seen.add(id(value))
        if isinstance(value, tuple):
            pending.extend(value)
        elif is_dataclass(value) and type(value).__module__ == "clean_ioc.container":
            registrations += isinstance(value, _RegistrationStep)
            steps += isinstance(value, _Step)
            pending.extend(getattr(value, item.name) for item in fields(value) if item.name in links)
    return registrations, steps


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("shape", choices=("small-chain", "two-transports", "chain", "routes", "senders"))
    parser.add_argument("--size", type=int, default=4)
    parser.add_argument("--early", action="store_true")
    parser.add_argument("--profile", action="store_true")
    args = parser.parse_args()
    builder = declarations(args.shape, args.size, args.early)
    profile = CompilationProfiler(max_records=0) if args.profile else None
    started = time.monotonic()
    owner = builder.build(**({"profile": profile} if profile is not None else {}))
    elapsed = time.monotonic() - started
    rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    graph = owner._plan.graph
    registrations, steps = retained_templates(owner)
    result = {
        "shape": args.shape,
        "size": args.size,
        "early": args.early,
        "python": platform.python_version(),
        "platform": platform.platform(),
        "instrumentation": "CompilationProfiler(max_records=0)" if args.profile else "none",
        "seconds": elapsed,
        "peak_rss_bytes": rss if sys.platform == "darwin" else rss * 1024,
        "retained_registration_templates": registrations,
        "retained_step_records": steps,
        "physical_component_records": len(graph._records),
        "provider_view_contexts": len(getattr(graph, "_views", ())),
        "provider_root_keys": len(owner._plan.provider_roots),
        "record_shallow_bytes": sum(sys.getsizeof(record) for record in graph._records.values()),
        "view_context_shallow_bytes": sum(sys.getsizeof(view) for view in getattr(graph, "_views", ())),
    }
    if profile is not None:
        result["counters"] = profile.report().counters.to_dict()
        result["definition_counts"] = dict(getattr(profile.report(), "definition_counts", ()))
    print(json.dumps(result, sort_keys=True))
    owner.__exit__()


if __name__ == "__main__":
    main()
