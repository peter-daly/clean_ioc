"""Wait for the owned build driver, then run all remaining stages serially."""

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).parent
parser = argparse.ArgumentParser()
parser.add_argument("--after-pid", type=int, required=True)
args = parser.parse_args()
while True:
    try:
        os.kill(args.after_pid, 0)
    except ProcessLookupError:
        break
    time.sleep(2)
print("Build matrix finished; starting compatibility/observer checks", flush=True)
subprocess.run(["/bin/sh", str(HERE / "08-checks.sh")], check=True)  # noqa: S603
for suite in ("full", "diagnostics", "failure", "artifact"):
    print(f"Starting {suite}", flush=True)
    subprocess.run([sys.executable, str(HERE / "08-run.py"), "--suite", suite], check=True)  # noqa: S603
print("All serial stages completed", flush=True)
