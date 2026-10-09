#!/bin/sh
set -eu
TASK09_HERE=.work/graph-memory-optimization/evidence
ps -axo pid,command > "$TASK09_HERE/09-concurrency-check.txt"
for TASK09_SUITE in build full diagnostics failure artifact; do
  .venv/bin/python "$TASK09_HERE/09-run.py" --suite "$TASK09_SUITE"
done
.venv/bin/python "$TASK09_HERE/09-summarize.py" > "$TASK09_HERE/09-summary.log"
/bin/sh "$TASK09_HERE/09-checks.sh"
