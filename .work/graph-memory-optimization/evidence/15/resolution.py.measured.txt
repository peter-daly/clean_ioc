"""Matched task14/task15 cold and steady resolution controls."""

# ruff: noqa: E402, S603
import contextlib
import io
import json
import runpy
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).parent
if sys.argv[1] == "sample":
    from source_loader import LOADED, install

    policy = sys.argv[2]
    install(policy)
    # Reuse the original eight resolves; suppress its task13 cache replacement.
    sys.argv[2] = "after"
    captured = io.StringIO()
    with contextlib.redirect_stdout(captured):
        runpy.run_path(str(HERE.parent / "13/resolution.py"), run_name="__main__")
    row = json.loads(captured.getvalue())
    row["loaded"] = LOADED
    print(json.dumps(row))
else:
    rows = []
    for variant in ("run", "rich-run", "analysis"):
        for repeat in range(3):
            for policy in ("before", "after"):
                row = json.loads(
                    subprocess.check_output([sys.executable, __file__, "sample", policy, variant], text=True)
                )
                row["task15_policy"] = policy
                rows.append(row)
                (HERE / "resolution.json").write_text(json.dumps(rows, indent=2) + "\n")
                print(variant, repeat, policy, row["cold_seconds"], row["steady_median_seconds"], flush=True)
