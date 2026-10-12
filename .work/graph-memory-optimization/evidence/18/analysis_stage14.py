"""Bounded stage14/final analysis resolution diagnostic with original workload boundary."""

# ruff: noqa: S603
import asyncio
import gc
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import grid
from source_loader import HERE, LOADED


async def sample(policy, control):
    if control == "disabled":
        original = grid.prepare

        def prepare(*args):
            original(*args)
            from benchmarks import graph_memory_fixture as fixture

            resolve = fixture.resolve_workload

            async def without_collection(*args, **kwargs):
                enabled = gc.isenabled()
                gc.disable()
                try:
                    return await resolve(*args, **kwargs)
                finally:
                    if enabled:
                        gc.enable()

            fixture.resolve_workload = without_collection  # ty: ignore[invalid-assignment]

        grid.prepare = prepare  # ty: ignore[invalid-assignment]
    result = await grid.sample(policy, "analysis", "normal", "resolution")
    result.update(policy=policy, control=control, executed_source=LOADED)
    return result


if __name__ == "__main__":
    if sys.argv[1] == "sample":
        print(json.dumps(asyncio.run(sample(*sys.argv[2:]))))
    else:
        if len(sys.argv) != 3:
            raise SystemExit("Usage: analysis_stage14.py repeat OUTPUT_DIRECTORY")
        output = Path(sys.argv[2])
        output.mkdir(parents=True, exist_ok=True)
        if (output / "analysis-stage14.json").exists():
            raise FileExistsError("Use a fresh diagnostic output file")
        (output / "analysis-stage14-harness.json").write_text(
            json.dumps(
                {
                    "analysis_stage14.py": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                    "grid.py": hashlib.sha256((HERE / "grid.py").read_bytes()).hexdigest(),
                    "source_loader.py": hashlib.sha256((HERE / "source_loader.py").read_bytes()).hexdigest(),
                },
                indent=2,
            )
            + "\n"
        )
        rows = []
        for control in ("normal", "disabled"):
            for repeat in range(3):
                for policy in ("stage14", "after") if repeat % 2 == 0 else ("after", "stage14"):
                    row = json.loads(
                        subprocess.check_output([sys.executable, __file__, "sample", policy, control], text=True)
                    )
                    row["repeat"] = repeat + 1
                    rows.append(row)
                    (output / "analysis-stage14.json").write_text(json.dumps(rows, indent=2) + "\n")
                    print(control, repeat, policy, row["cold_seconds"], row["steady_median_seconds"], flush=True)
