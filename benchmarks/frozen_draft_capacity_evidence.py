"""Installed-wheel draft-table capacity evidence; run separately per wheel.

Allocation tracing surrounds composition/compilation and stops before graph
serialization. Run with identical route counts and support dependencies.
"""

import argparse
import gc
import hashlib
import json
import platform
import resource
import sys
import tracemalloc

from selected_registration_catalogue_evidence import builder_for, source_fingerprint

import clean_ioc


def main():
    import bark_core  # ty: ignore[unresolved-import]
    from bark_core.application.commands.messaging import (  # ty: ignore[unresolved-import]
        create_command_consumer_registry,
        create_reply_consumer_registry,
    )

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--routes", type=int, default=64)
    parser.add_argument("--heap", action="store_true")
    parser.add_argument("--diagnostics", action="store_true")
    args = parser.parse_args()
    warm_builder, _ = builder_for(0)
    del warm_builder
    gc.collect()
    baseline_rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    if args.heap:
        tracemalloc.start()
    builder, retained_types = builder_for(args.routes)
    container = builder.build(
        provider_roots=(),
        allow_scope_builders=False,
        check_unreachable=False,
        aggregate_errors=False,
        diagnostics=args.diagnostics,
    )
    del builder
    gc.collect()
    graph = container._plan.graph
    result = {
        "python": platform.python_version(),
        "platform": platform.platform(),
        "routes_per_family": args.routes,
        "message_types": len(retained_types),
        "diagnostics": args.diagnostics,
        "instrumentation": "tracemalloc" if args.heap else "none",
        "baseline_peak_rss_bytes": baseline_rss * (1 if sys.platform == "darwin" else 1024),
        "peak_rss_bytes": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        * (1 if sys.platform == "darwin" else 1024),
        "physical_records": len(graph._records or ()),
        "frozen_record_shallow_bytes": sum(sys.getsizeof(record) for record in (graph._records or {}).values()),
        "draft_count": len(graph._drafts),
        "draft_table_bytes": sys.getsizeof(graph._drafts),
        "provider_view_contexts": len(graph._views),
        "public_roots": len(container.components),
        "catalogue_entries": len(container.selected_registrations),
    }
    if args.heap:
        retained, peak = tracemalloc.get_traced_memory()
        result.update(traced_retained_bytes=retained, traced_peak_bytes=peak)
        tracemalloc.stop()
    commands = create_command_consumer_registry(container).command_types
    replies = create_reply_consumer_registry(container).reply_types
    if len(commands) != args.routes or len(replies) != args.routes:
        raise RuntimeError("Consumer discovery differed from selected routes")
    result.update(command_consumers=len(commands), reply_consumers=len(replies))
    result["manifest_fingerprint"] = container.graph.manifest(all_roots=True).fingerprint
    result["validation_fingerprint"] = hashlib.sha256(container.validation_report().to_json().encode()).hexdigest()
    result["clean_source_fingerprint"] = source_fingerprint(clean_ioc)
    result["bark_source_fingerprint"] = source_fingerprint(bark_core)
    print(json.dumps(result, sort_keys=True))
    container.__exit__()


if __name__ == "__main__":
    main()
