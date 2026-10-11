# ruff: noqa: S603
"""Serial comparison controls; execute only after the main matrix completes."""

import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).parent
escaped = []
for mode in ("run", "analysis"):
    for repeat in range(3):
        for kind in ("normal", "heap"):
            for policy in ("before", "after") if repeat % 2 == 0 else ("after", "before"):
                args = [sys.executable, str(HERE / "escaped.py"), policy, mode, kind]
                item = json.loads(subprocess.check_output(args, text=True))
                item["repeat"] = repeat
                escaped.append(item)
                (HERE / "escaped.json").write_text(json.dumps(escaped, indent=2) + "\n")
                print("escaped", mode, repeat, kind, policy, flush=True)
for variant in ("run", "rich-run", "analysis"):
    for policy in ("before", "after"):
        args = [sys.executable, str(HERE / "census.py"), policy, variant]
        output = subprocess.check_output(args, text=True)
        (HERE / f"census-{policy}-{variant}.json").write_text(output)
        print("census", variant, policy, flush=True)
for policy in ("before", "after"):
    output = subprocess.check_output([sys.executable, str(HERE / "phases.py"), policy], text=True)
    (HERE / f"phases-{policy}.json").write_text(output)
    print("phases", policy, flush=True)
