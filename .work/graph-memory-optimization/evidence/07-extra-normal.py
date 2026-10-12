"""Two additional counterbalanced normal processes per measured candidate."""

import json
import statistics
import subprocess
import sys
from pathlib import Path

root = Path(__file__).parent
names = ("baseline", "slots", "prelookup", "indexes")
runs = {name: json.loads((root / f"07-repeat-{name}.json").read_text())["runs"] for name in names}
for iteration in range(2):
    for name in names:
        command = [sys.executable, str(root / "07-probe.py"), "measure", "--probe", name]
        run = json.loads(subprocess.check_output(command, text=True))  # noqa: S603
        run["repeat"] = iteration + 4
        runs[name].append(run)
        print(f"extra normal {iteration + 1}: {name}", file=sys.stderr)
result = {"runs": runs, "medians": {}, "ranges": {}}
for name, values in runs.items():
    normal = [value for value in values if value["instrumentation"] == "none"]
    traced = [value for value in values if value["instrumentation"] == "tracemalloc"]
    result["medians"][name] = {
        **{key: statistics.median(value[key] for value in normal) for key in ("build_seconds", "resolve_seconds")},
        "prepared": {
            key: statistics.median(value["prepared"][key] for value in group)
            for group, keys in (
                (normal, ("rss_bytes", "peak_rss_bytes")),
                (traced, ("traced_retained_bytes", "traced_peak_bytes")),
            )
            for key in keys
        },
    }
    result["ranges"][name] = {
        "build_seconds": [
            min(value["build_seconds"] for value in normal),
            max(value["build_seconds"] for value in normal),
        ],
        "rss_bytes": [
            min(value["prepared"]["rss_bytes"] for value in normal),
            max(value["prepared"]["rss_bytes"] for value in normal),
        ],
    }
(root / "07-extended-comparison.json").write_text(json.dumps(result, indent=2) + "\n")
