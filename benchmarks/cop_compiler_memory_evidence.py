"""Measure a pinned Cop builder using the selected interpreter's installed library.

Run with the Cop environment's Python and --project pointing at its source checkout.
A candidate wheel must be installed in a disposable environment. --settings-json
loads environment strings without displaying configured values. Normal elapsed time
covers get_container only; configuration and imports precede it. RSS includes them.
"""

import argparse
import importlib
import importlib.metadata
import json
import os
import platform
import resource
import sys
import time
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("app", choices=("api", "worker"))
    parser.add_argument("--project", type=Path, required=True)
    parser.add_argument("--settings-json", type=Path)
    parser.add_argument("--profile", action="store_true")
    args = parser.parse_args()
    if args.settings_json is not None:
        os.environ.update(json.loads(args.settings_json.read_text()))
    sys.path.insert(0, str(args.project.resolve()))
    import clean_ioc

    config_module = importlib.import_module(f"data_protection_cop.apps.{args.app}.config")
    container_module = importlib.import_module(f"data_protection_cop.apps.{args.app}.container")
    config_type = config_module.ApiConfig if args.app == "api" else config_module.WorkerConfig
    config = config_type()
    profile = None
    if args.profile:
        profile = clean_ioc.CompilationProfiler(max_records=0)
        builder = container_module.get_builder(config)
        started = time.monotonic()
        container = builder.build(profile=profile)
    else:
        started = time.monotonic()
        container = container_module.get_container(config)
    elapsed = time.monotonic() - started
    rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    result = {
        "app": args.app,
        "seconds": elapsed,
        "peak_rss_bytes": rss if sys.platform == "darwin" else rss * 1024,
        "python": platform.python_version(),
        "platform": platform.platform(),
        "clean_ioc": importlib.metadata.version("clean-ioc"),
        "clean_ioc_module": clean_ioc.__file__,
        "bark_core": importlib.metadata.version("bark-core"),
        "instrumentation": "CompilationProfiler(max_records=0)" if args.profile else "none",
    }
    if profile is not None:
        report = profile.report()
        result.update(counters=report.counters.to_dict(), phases_seconds={k: v / 1e9 for k, v in report.phases_ns})
    graph = container._plan.graph
    result.update(
        physical_component_records=len(graph._records),
        provider_view_contexts=len(getattr(graph, "_views", ())),
        provider_root_keys=len(container._plan.provider_roots),
    )
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
