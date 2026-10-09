"""Serial fresh-process evidence collection; checkpoint every completed run."""

import argparse
import hashlib
import json
import platform
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).parent
parser = argparse.ArgumentParser()
parser.add_argument("--suite", choices=("build", "full", "diagnostics", "artifact", "failure"), default="build")
args = parser.parse_args()
output = HERE / f"09-{args.suite}-runs.json"
probe_artifacts = HERE.parents[2] / ".cache/graph-memory-task09"
runs = []
output.write_text("[]\n")
for heap, repeats in ((False, 5 if args.suite in ("build", "full") else 3), (True, 3)):
    for repeat in range(repeats):
        candidates = ["baseline", "both"]
        if repeat % 2:
            candidates.reverse()
        for candidate in candidates:
            variants = (False, True) if args.suite == "artifact" else (args.suite == "full",)
            for full in variants:
                modes = ("export", "load") if args.suite == "artifact" else ("measure",)
                artifact = probe_artifacts / f"09-{candidate}-{'full' if full else 'reduced'}-graph.jsonl"
                for mode in modes:
                    command = [
                        sys.executable,
                        str(HERE / "09-probe.py"),
                        mode,
                        "--probe",
                        candidate,
                        "--routes",
                        "2" if args.suite == "diagnostics" else "8",
                    ]
                    command += [
                        flag
                        for enabled, flag in (
                            (heap, "--heap"),
                            (full, "--full"),
                            (args.suite == "diagnostics", "--diagnostics"),
                        )
                        if enabled
                    ]
                    if args.suite == "failure":
                        command = [sys.executable, str(HERE / "09-failure.py"), "--probe", candidate]
                        if heap:
                            command.append("--heap")
                    if args.suite == "artifact":
                        command += ["--artifact", str(artifact)]
                    child = subprocess.Popen(command, text=True, stdout=subprocess.PIPE)  # noqa: S603
                    payload, _ = child.communicate()
                    if child.returncode:
                        raise RuntimeError(f"Measurement failed: {command}")
                    result = json.loads(payload)
                    result.setdefault("pid", child.pid)
                    result.setdefault("python", platform.python_version())
                    result.setdefault("platform", platform.platform())
                    result.setdefault("machine", platform.machine())
                    result["command"] = command
                    result.setdefault("ownership", {"retained_builder": False, "captured_selection_views": False})
                    result["repeat"] = repeat + 1
                    runs.append(result)
                    output.write_text(
                        json.dumps(
                            {
                                "suite": args.suite,
                                "driver_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                                "runs": runs,
                            },
                            indent=2,
                            sort_keys=True,
                        )
                        + "\n"
                    )
                    print(
                        f"{args.suite}: {candidate}, {mode}, full={full}, heap={heap}, repeat={repeat + 1}", flush=True
                    )
