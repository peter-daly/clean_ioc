#!/bin/sh
set -eu
TASK08_HERE=.work/graph-memory-optimization/evidence
.venv/bin/ruff check . > "$TASK08_HERE/08-lint.txt" 2>&1
.venv/bin/ruff format --check . > "$TASK08_HERE/08-format.txt" 2>&1
.venv/bin/ty check . > "$TASK08_HERE/08-typecheck.txt" 2>&1
.venv/bin/python scripts/validate_docs_examples.py > "$TASK08_HERE/08-docs-examples.txt" 2>&1
.venv/bin/benchbro list --verbose > "$TASK08_HERE/08-benchmark-discovery.txt" 2>&1
.venv/bin/ruff check --ignore E501 "$TASK08_HERE"/08-*.py > "$TASK08_HERE/08-probe-lint.txt" 2>&1
.venv/bin/ruff format --check "$TASK08_HERE"/08-*.py > "$TASK08_HERE/08-probe-format.txt" 2>&1
.venv/bin/ty check "$TASK08_HERE"/08-*.py > "$TASK08_HERE/08-probe-typecheck.txt" 2>&1
TASK08_SITE=/Users/peter.daly/WS/pete/clean_ioc/.venv/lib/python3.14/site-packages
for TASK08_PYTHON in /Users/peter.daly/.local/share/uv/python/cpython-3.11.13-macos-aarch64-none/bin/python3.11 /Users/peter.daly/.local/share/uv/python/cpython-3.12.11-macos-aarch64-none/bin/python3.12 /opt/homebrew/opt/python@3.13/bin/python3.13; do
  TASK08_VERSION=$("$TASK08_PYTHON" -c 'import platform; print(platform.python_version())')
  PYTHONPATH="$TASK08_SITE" PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 "$TASK08_PYTHON" "$TASK08_HERE/08-probe.py" pytest --probe both -p pytest_asyncio.plugin -q tests/test_graph_artifact_experiment.py tests/test_resolution_profiler.py tests/test_compilation_profile.py tests/test_optional_explanation_metadata.py > "$TASK08_HERE/08-python-$TASK08_VERSION-tests.txt" 2>&1
  PYTHONPATH="$TASK08_SITE" "$TASK08_PYTHON" "$TASK08_HERE/08-mapping-checks.py" > "$TASK08_HERE/08-python-$TASK08_VERSION-mapping.json"
done
