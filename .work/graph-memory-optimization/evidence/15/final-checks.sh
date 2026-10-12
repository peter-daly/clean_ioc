#!/bin/sh
set -eu
TASK15_HERE=.work/graph-memory-optimization/evidence/15
.venv/bin/python "$TASK15_HERE/inspection-full.py" before > "$TASK15_HERE/inspection-full-before.json"
.venv/bin/python "$TASK15_HERE/inspection-full.py" after > "$TASK15_HERE/inspection-full-after.json"
.venv/bin/python "$TASK15_HERE/opaque-lifetimes.py" > "$TASK15_HERE/opaque-lifetimes.json"
make ci > "$TASK15_HERE/make-ci.txt" 2>&1
.venv/bin/mkdocs build --strict > "$TASK15_HERE/docs-strict.txt" 2>&1
for TASK15_VERSION in 3.11 3.12 3.13; do
  PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 uv run --isolated --no-project --python "$TASK15_VERSION" --with 'pytest>=8,<10' --with pytest-asyncio --with funcie --with typetoolbox --with typing_extensions --with assertive python -m pytest -p pytest_asyncio.plugin -q tests/test_compact_compilation_indexes.py tests/test_graph_artifact_experiment.py tests/test_build_modes.py tests/test_validation_evidence_lifetime.py tests/test_activation_cache_lifetimes.py tests/test_shared_draft_definitions.py tests/test_resolution_profiler.py tests/test_compilation_profile.py > "$TASK15_HERE/python$TASK15_VERSION.txt" 2>&1
  uv run --isolated --no-project --python "$TASK15_VERSION" --with funcie --with typetoolbox --with typing_extensions python "$TASK15_HERE/mapping-checks.py" > "$TASK15_HERE/python$TASK15_VERSION-mapping.json" 2> "$TASK15_HERE/python$TASK15_VERSION-mapping.stderr"
  uv run --isolated --no-project --python "$TASK15_VERSION" --with funcie --with typetoolbox --with typing_extensions python "$TASK15_HERE/operation-audit.py" > "$TASK15_HERE/python$TASK15_VERSION-audit.json" 2> "$TASK15_HERE/python$TASK15_VERSION-audit.stderr"
done
git diff --check > "$TASK15_HERE/diff-check.txt"
