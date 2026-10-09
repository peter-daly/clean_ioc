"""Fresh-process installed-wheel evidence for minimal histories/deferred reachability.

Compare the frozen step-4 baseline, step-5 eager compatibility setting and step-5
production deferral using the same Bark route fixture. No source path overrides.
"""

import argparse
import gc
import hashlib
import json
import platform
import resource
import sys
import time
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
    parser.add_argument("--routes", type=int, default=24)
    parser.add_argument("--mode", choices=("baseline", "eager", "deferred"), required=True)
    parser.add_argument("--heap", action="store_true")
    parser.add_argument("--diagnostics", action="store_true")
    args = parser.parse_args()
    warm_builder, _ = builder_for(0)
    del warm_builder
    gc.collect()
    if args.heap:
        tracemalloc.start()
    builder, retained_types = builder_for(args.routes)
    kwargs = {} if args.mode == "baseline" else {"check_unreachable": args.mode == "eager"}
    started = time.monotonic()
    container = builder.build(allow_scope_builders=False, diagnostics=args.diagnostics, provider_roots=(), **kwargs)
    seconds = time.monotonic() - started
    del builder
    gc.collect()
    result = {
        "mode": args.mode,
        "python": platform.python_version(),
        "platform": platform.platform(),
        "routes_per_family": args.routes,
        "sagas": 2 * args.routes,
        "message_types": len(retained_types),
        "diagnostics": args.diagnostics,
        "provider_roots": [],
        "allow_scope_builders": False,
        "check_unreachable": args.mode != "deferred",
        "instrumentation": "tracemalloc" if args.heap else "none",
        "seconds": seconds,
        "peak_rss_bytes": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        * (1 if sys.platform == "darwin" else 1024),
        "physical_records": len(container._plan.graph._records or ()),
        "provider_view_contexts": len(container._plan.graph._views),
        "public_roots": len(container.components),
        "entrypoints": len(container.graph.entrypoints),
        "catalogue_entries": len(container.selected_registrations),
        "known_selection_histories": len(container.graph._known_root_selections),
        "census_selection_histories": len(container.graph._census_root_selections),
        "build_warnings": len(container.build_report.warnings),
    }
    if args.heap:
        retained, peak = tracemalloc.get_traced_memory()
        result.update(traced_retained_bytes=retained, traced_peak_bytes=peak)
        tracemalloc.stop()
    started = time.monotonic()
    validation = container.validation_report()
    result["validation_seconds_untraced"] = time.monotonic() - started
    result["validation_warnings"] = len(validation.warnings)
    result["validation_fingerprint"] = hashlib.sha256(
        json.dumps([issue.to_dict() for issue in validation.issues], sort_keys=True).encode()
    ).hexdigest()
    commands = create_command_consumer_registry(container).command_types
    replies = create_reply_consumer_registry(container).reply_types
    if len(commands) != args.routes or len(replies) != args.routes:
        raise RuntimeError("Consumer discovery differed from selected routes")
    result.update(command_consumers=len(commands), reply_consumers=len(replies))
    result["manifest_fingerprint"] = container.graph.manifest(all_roots=True).fingerprint
    result["clean_source_fingerprint"] = source_fingerprint(clean_ioc)
    result["bark_source_fingerprint"] = source_fingerprint(bark_core)
    print(json.dumps(result, sort_keys=True))
    container.__exit__()


if __name__ == "__main__":
    main()
