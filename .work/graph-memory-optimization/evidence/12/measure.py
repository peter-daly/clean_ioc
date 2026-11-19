"""Serial public-mode controls; instrumentation only in separate census runs."""

import asyncio
import json
import statistics
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))
from benchmarks.graph_memory_evidence import measure  # noqa: E402
from clean_ioc import ContainerBuilder  # noqa: E402


def rich_rule(graph):
    # Unknown arbitrary graph consumers require the complete captured history.
    assert graph.graph.diagnostics_enabled  # noqa: S101
    return ()


def sample(variant, heap):
    if variant == "rich-run":
        original = ContainerBuilder.build

        def build(self, **kwargs):
            self.add_validation_rule(rich_rule)
            return original(self, **kwargs)

        ContainerBuilder.build = build
    return asyncio.run(
        measure(
            2 if variant == "analysis" else 8, heap, False, build_mode="analysis" if variant == "analysis" else "run"
        )
    )


if __name__ == "__main__":
    if sys.argv[1] == "sample":
        print(json.dumps(sample(sys.argv[2], sys.argv[3] == "heap")))
    else:
        output = {}
        for variant in ("run", "rich-run", "analysis"):
            runs = []
            for repeat in range(3):
                for kind in ("normal", "heap"):
                    run = json.loads(
                        subprocess.check_output([sys.executable, __file__, "sample", variant, kind], text=True)  # noqa: S603
                    )
                    runs.append(run)
                    print(variant, repeat + 1, kind, run["build_seconds"], flush=True)
            normal = [r for r in runs if r["instrumentation"] == "none"]
            heap = [r for r in runs if r["instrumentation"] == "tracemalloc"]
            output[variant] = {
                "runs": runs,
                "medians": {
                    "build_seconds": statistics.median(r["build_seconds"] for r in normal),
                    "resolve_seconds": statistics.median(r["resolve_seconds"] for r in normal),
                    "prepared": {
                        **{
                            k: statistics.median(r["prepared"][k] for r in normal)
                            for k in ("rss_bytes", "peak_rss_bytes")
                        },
                        **{
                            k: statistics.median(r["prepared"][k] for r in heap)
                            for k in ("traced_retained_bytes", "traced_peak_bytes")
                        },
                    },
                },
            }
            Path(sys.argv[2]).write_text(json.dumps(output, indent=2) + "\n")
