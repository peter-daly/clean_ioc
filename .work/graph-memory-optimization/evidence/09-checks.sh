#!/bin/sh
# Execute only when the serial measurement suites have finished.
set -eu
TASK09_HERE=.work/graph-memory-optimization/evidence
for TASK09_CANDIDATE in baseline both; do
  .venv/bin/python "$TASK09_HERE/09-screens.py" inventory --probe "$TASK09_CANDIDATE" > "$TASK09_HERE/09-inventory-$TASK09_CANDIDATE.json"
  .venv/bin/python "$TASK09_HERE/09-screens.py" inspection --probe "$TASK09_CANDIDATE" > "$TASK09_HERE/09-inspection-$TASK09_CANDIDATE.json"
  .venv/bin/python "$TASK09_HERE/09-screens.py" inspection --probe "$TASK09_CANDIDATE" --routes 2 --diagnostics > "$TASK09_HERE/09-inspection-diagnostics-$TASK09_CANDIDATE.json"
  .venv/bin/python "$TASK09_HERE/09-semantics.py" "$TASK09_CANDIDATE" --routes 2 --full > "$TASK09_HERE/09-semantics-full-$TASK09_CANDIDATE.json"
  .venv/bin/python "$TASK09_HERE/09-semantics.py" "$TASK09_CANDIDATE" --routes 8 > "$TASK09_HERE/09-semantics-reduced-$TASK09_CANDIDATE.json"
done
.venv/bin/python "$TASK09_HERE/09-screens.py" storage > "$TASK09_HERE/09-storage.json"
.venv/bin/python "$TASK09_HERE/09-mapping-checks.py" > "$TASK09_HERE/09-mapping-checks.json"
.venv/bin/python "$TASK09_HERE/09-lifetimes.py" > "$TASK09_HERE/09-lifetimes.json"
.venv/bin/python "$TASK09_HERE/09-probe.py" pytest --probe both -q tests examples > "$TASK09_HERE/09-tests.log" 2>&1
.venv/bin/python "$TASK09_HERE/09-hash-counterexamples.py" > "$TASK09_HERE/09-hash-counterexamples.json"
.venv/bin/python "$TASK09_HERE/09-operation-audit.py" > "$TASK09_HERE/09-operation-audit.json"
.venv/bin/python "$TASK09_HERE/09-policy-checks.py" > "$TASK09_HERE/09-policy-checks.json"
.venv/bin/python "$TASK09_HERE/09-artifact-checks.py" > "$TASK09_HERE/09-artifact-checks.json"
if .venv/bin/ruff check . > "$TASK09_HERE/09-lint.txt" 2>&1; then
  :
else
  .venv/bin/ruff check . --extend-per-file-ignores ".work/graph-memory-optimization/evidence/08-hash-counterexamples.py:E501" > "$TASK09_HERE/09-lint-existing-evidence-exception.txt" 2>&1
fi
.venv/bin/ruff format --check . > "$TASK09_HERE/09-format.txt" 2>&1
.venv/bin/ty check . > "$TASK09_HERE/09-typecheck.txt" 2>&1
.venv/bin/python scripts/validate_docs_examples.py > "$TASK09_HERE/09-docs-examples.txt" 2>&1
.venv/bin/benchbro list --verbose > "$TASK09_HERE/09-benchmark-discovery.txt" 2>&1
.venv/bin/ruff check --ignore E501 "$TASK09_HERE"/09-*.py > "$TASK09_HERE/09-probe-lint.txt" 2>&1
.venv/bin/ruff format --check "$TASK09_HERE"/09-*.py > "$TASK09_HERE/09-probe-format.txt" 2>&1
.venv/bin/ty check "$TASK09_HERE"/09-*.py > "$TASK09_HERE/09-probe-typecheck.txt" 2>&1
TASK09_SITE=/Users/peter.daly/WS/pete/clean_ioc/.venv/lib/python3.14/site-packages
for TASK09_PYTHON in /Users/peter.daly/.local/share/uv/python/cpython-3.11.13-macos-aarch64-none/bin/python3.11 /Users/peter.daly/.local/share/uv/python/cpython-3.12.11-macos-aarch64-none/bin/python3.12 /opt/homebrew/opt/python@3.13/bin/python3.13; do
  TASK09_VERSION=$("$TASK09_PYTHON" -c 'import platform; print(platform.python_version())')
  PYTHONPATH="$TASK09_SITE" PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 "$TASK09_PYTHON" "$TASK09_HERE/09-probe.py" pytest --probe both -p pytest_asyncio.plugin -q tests/test_graph_artifact_experiment.py tests/test_resolution_profiler.py tests/test_compilation_profile.py tests/test_optional_explanation_metadata.py > "$TASK09_HERE/09-python-$TASK09_VERSION-tests.txt" 2>&1
  PYTHONPATH="$TASK09_SITE" "$TASK09_PYTHON" "$TASK09_HERE/09-mapping-checks.py" > "$TASK09_HERE/09-python-$TASK09_VERSION-mapping.json"
  PYTHONPATH="$TASK09_SITE" "$TASK09_PYTHON" "$TASK09_HERE/09-operation-audit.py" > "$TASK09_HERE/09-python-$TASK09_VERSION-audit.json"
  PYTHONPATH="$TASK09_SITE" "$TASK09_PYTHON" "$TASK09_HERE/09-hash-counterexamples.py" > "$TASK09_HERE/09-python-$TASK09_VERSION-hash.json"
done
