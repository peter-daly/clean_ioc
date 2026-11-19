#!/bin/sh
set -eu
TASK09_HERE=.work/graph-memory-optimization/evidence
.venv/bin/ruff check . --extend-per-file-ignores '.work/graph-memory-optimization/evidence/08-hash-counterexamples.py:E501' > "$TASK09_HERE/09-lint-existing-evidence-exception.txt" 2>&1
if .venv/bin/ruff format --check . > "$TASK09_HERE/09-format.txt" 2>&1; then
  :
else
  .venv/bin/ruff format --check . --extend-exclude '.work/graph-memory-optimization/evidence/08-hash-counterexamples.py' > "$TASK09_HERE/09-format-existing-evidence-exception.txt" 2>&1
fi
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
